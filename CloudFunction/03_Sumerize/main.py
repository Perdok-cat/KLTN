from __future__ import annotations

import functions_framework
import os
import re
import json
import time
import uuid
import logging
from datetime import datetime, timezone

from google.cloud import bigquery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration  (override via Cloud Function environment variables)
# ---------------------------------------------------------------------------

GCP_PROJECT     = os.environ.get("GCP_PROJECT",     "project-e5ef1531-7ef9-4232-b30")
BQ_DATASET      = os.environ.get("BQ_DATASET",      "ai_news_data")
BQ_SOURCE_TABLE = os.environ.get("BQ_SOURCE_TABLE", "labeled_articles")
BQ_OUTPUT_TABLE = os.environ.get("BQ_OUTPUT_TABLE", "summarized_articles")
BQ_FAILED_TABLE = os.environ.get("BQ_FAILED_TABLE", "failed_summaries")

# Backend selection:
#   USE_VERTEX=true  → Vertex AI (production, uses ADC / service account, no API key needed)
#   USE_VERTEX=false → Gemini Developer API (development, requires GEMINI_API_KEY)
USE_VERTEX      = os.environ.get("USE_VERTEX", "false").lower() == "true"
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "us-central1")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL",   "gemini-2.5-flash")
PROMPT_VERSION = os.environ.get("PROMPT_VERSION", "v2.0")

MAX_ARTICLES_PER_RUN = int(os.environ.get("MAX_ARTICLES_PER_RUN", "50"))
GEMINI_DELAY         = float(os.environ.get("GEMINI_DELAY",         "7"))
MAX_RETRIES          = int(os.environ.get("MAX_RETRIES",            "3"))
MAX_CONTENT_CHARS    = int(os.environ.get("MAX_CONTENT_CHARS",      "12000"))

SKIP_LABELS = {"NOISE"}

# ---------------------------------------------------------------------------
# Response schema  (enforced by model; used by both backends)
# Vertex AI expects uppercase type names; genai SDK accepts both.
# ---------------------------------------------------------------------------

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary":    {"type": "STRING"},
        "key_points": {"type": "ARRAY", "items": {"type": "STRING"}},
        "keywords":   {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["summary", "key_points", "keywords"],
}

# ---------------------------------------------------------------------------
# Prompts  (system role separated from user turn)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """Bạn là biên tập viên công nghệ AI chuyên nghiệp tại một tòa soạn tin tức Việt Nam.
Nhiệm vụ: Tóm tắt bài báo công nghệ AI một cách chính xác, trung lập, dễ hiểu cho độc giả phổ thông.

Nguyên tắc:
- KHÔNG bịa đặt thông tin không có trong bài gốc.
- KHÔNG đưa ra quan điểm cá nhân.
- Viết bằng tiếng Việt, rõ ràng, súc tích.
- summary: 3–5 câu, tóm tắt ý chính.
- key_points: 3–5 gạch đầu dòng, mỗi gạch 1 câu ngắn.
- keywords: 3–7 từ/cụm từ quan trọng nhất trong bài.
- Nếu nội dung thiếu thông tin, tóm tắt những gì có và ghi chú "thông tin hạn chế"."""

_USER_PROMPT_TEMPLATE = """Tóm tắt bài báo dưới đây.

TIÊU ĐỀ: {title}
LOẠI BÀI: {label}

NỘI DUNG:
{content}"""

_RETRY_SUFFIX = """

---
Output lần trước không hợp lệ vì: {errors}
Hãy trả lại JSON với đầy đủ các trường: summary, key_points, keywords."""

# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------

_FIELD_RULES: dict[str, tuple] = {
    #  field        expected_type   validator                           human-readable rule
    "summary":    (str,  lambda v: 30  <= len(v) <= 3000, "30–3000 ký tự"),
    "key_points": (list, lambda v: 2   <= len(v) <= 7,    "2–7 phần tử"),
    "keywords":   (list, lambda v: 2   <= len(v) <= 10,   "2–10 phần tử"),
}


def validate_output(result: dict) -> tuple[bool, list[str]]:
    """Validate LLM structured output. Returns (is_valid, error_messages)."""
    errors: list[str] = []
    for field, (expected_type, validator, rule_desc) in _FIELD_RULES.items():
        val = result.get(field)
        if val is None:
            errors.append(f"Thiếu trường '{field}'")
        elif not isinstance(val, expected_type):
            errors.append(f"'{field}' sai kiểu (cần {expected_type.__name__})")
        elif not validator(val):
            errors.append(f"'{field}' ngoài phạm vi ({rule_desc})")
    return len(errors) == 0, errors

# ---------------------------------------------------------------------------
# Model singleton
# ---------------------------------------------------------------------------

_model = None


def _get_model():
    global _model
    if _model is not None:
        return _model

    if USE_VERTEX:
        import vertexai
        from vertexai.generative_models import GenerativeModel
        vertexai.init(project=GCP_PROJECT, location=VERTEX_LOCATION)
        _model = GenerativeModel(GEMINI_MODEL, system_instruction=_SYSTEM_PROMPT)
        logger.info(
            "Vertex AI model '%s' initialised (location=%s, prompt=%s).",
            GEMINI_MODEL, VERTEX_LOCATION, PROMPT_VERSION,
        )
    else:
        import google.generativeai as genai
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Set USE_VERTEX=true for production or provide GEMINI_API_KEY for development."
            )
        genai.configure(api_key=GEMINI_API_KEY)
        _model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=_SYSTEM_PROMPT)
        logger.info(
            "Gemini API model '%s' initialised (prompt=%s).", GEMINI_MODEL, PROMPT_VERSION
        )
    return _model


def _build_generation_config():
    """Return a GenerationConfig with temperature, output limit, and JSON schema enforcement."""
    if USE_VERTEX:
        from vertexai.generative_models import GenerationConfig
        return GenerationConfig(
            temperature=0.2,
            max_output_tokens=1024,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
        )
    else:
        import google.generativeai as genai
        return genai.GenerationConfig(
            temperature=0.2,
            max_output_tokens=1024,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
        )

# ---------------------------------------------------------------------------
# Summarisation logic
# ---------------------------------------------------------------------------

def _parse_response(raw: str) -> dict:
    """Strip markdown fences if present and parse JSON."""
    text = raw.strip()
    text = re.sub(r"^```json?\s*", "", text)
    text = re.sub(r"\s*```$",      "", text)
    return json.loads(text.strip())


def _classify_error(err: str) -> str:
    err_lower = err.lower()
    if "429" in err or "quota" in err_lower or "rate" in err_lower:
        return "rate_limit"
    if "safety" in err_lower or "blocked" in err_lower:
        return "safety_block"
    if "timeout" in err_lower or "deadline" in err_lower:
        return "timeout"
    return "api_error"


def summarize_article(
    title: str,
    content: str,
    label: str,
    source_id: str = "",
    link: str = "",
    bq_client: bigquery.Client | None = None,
) -> dict:
    """
    Call Gemini/Vertex AI to produce a structured summary with output validation.

    - Uses GenerationConfig (temperature=0.2, JSON mode, response schema).
    - Validates required fields after each attempt.
    - Re-submits with a corrective prompt suffix if validation fails.
    - Logs persistent failures to the failed_summaries BQ table.

    Returns:
        {
          "summary":    str,
          "key_points": list[str],
          "keywords":   list[str],
          "model_used": str,          # e.g. "gemini-2.5-flash@prompt-v2.0"
          "prompt_ver": str,
          "success":    bool,
          "error_type": str | None,
        }
    """
    if not content or len(content.strip()) < 100:
        return {
            "summary":    title,
            "key_points": [],
            "keywords":   [],
            "model_used": "rule:content_too_short",
            "prompt_ver": PROMPT_VERSION,
            "success":    False,
            "error_type": "content_too_short",
        }

    model      = _get_model()
    gen_cfg    = _build_generation_config()
    model_tag  = f"{GEMINI_MODEL}@prompt-{PROMPT_VERSION}"
    short_link = link[:60]

    last_error_type       = "unknown"
    last_error_msg        = ""
    last_validation_errors: list[str] = []

    for attempt in range(MAX_RETRIES):
        # Build prompt — append corrective suffix on retries caused by validation failure
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            title=title,
            label=label,
            content=content[:MAX_CONTENT_CHARS],
        )
        if attempt > 0 and last_validation_errors:
            user_prompt += _RETRY_SUFFIX.format(errors="; ".join(last_validation_errors))

        response = None
        try:
            response = model.generate_content(user_prompt, generation_config=gen_cfg)

            # Check for safety block before parsing
            if hasattr(response, "candidates") and response.candidates:
                finish_reason = str(response.candidates[0].finish_reason)
                if "SAFETY" in finish_reason:
                    last_error_type = "safety_block"
                    last_error_msg  = f"finish_reason={finish_reason}"
                    logger.warning("[%s] Safety block on attempt %d.", short_link, attempt + 1)
                    break  # safety blocks won't improve with retries

            parsed = _parse_response(response.text)

            is_valid, validation_errors = validate_output(parsed)
            if not is_valid:
                last_validation_errors = validation_errors
                last_error_type = "validation_failed"
                last_error_msg  = "; ".join(validation_errors)
                logger.warning(
                    "[%s] Validation failed (attempt %d/%d): %s",
                    short_link, attempt + 1, MAX_RETRIES, last_error_msg,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2)
                continue

            # All checks passed
            return {
                "summary":    str(parsed["summary"]),
                "key_points": parsed["key_points"] if isinstance(parsed["key_points"], list) else [],
                "keywords":   parsed["keywords"]   if isinstance(parsed["keywords"],   list) else [],
                "model_used": model_tag,
                "prompt_ver": PROMPT_VERSION,
                "success":    True,
                "error_type": None,
            }

        except json.JSONDecodeError:
            raw_text = response.text if response and hasattr(response, "text") else ""
            last_validation_errors = ["JSON parse error"]
            last_error_type = "json_parse_error"
            last_error_msg  = f"Raw snippet: {raw_text[:200]}"
            logger.warning("[%s] JSON parse failed (attempt %d/%d).", short_link, attempt + 1, MAX_RETRIES)
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)

        except Exception as exc:
            err = str(exc)
            last_error_type = _classify_error(err)
            last_error_msg  = err[:500]
            logger.warning(
                "[%s] API error attempt %d/%d [%s]: %s",
                short_link, attempt + 1, MAX_RETRIES, last_error_type, err[:200],
            )

            if last_error_type == "rate_limit":
                wait = 10.0
                m = re.search(r"retry[_ ]in ([\d.]+)s", err)
                if m:
                    wait = float(m.group(1)) + 2
                logger.info("Rate-limited — waiting %.1f s …", wait)
                time.sleep(wait)
            elif last_error_type == "safety_block":
                break
            elif attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)

    # All retries exhausted — persist failure record
    if bq_client:
        log_failure(bq_client, source_id, link, last_error_type, last_error_msg, MAX_RETRIES)

    return {
        "summary":    title,
        "key_points": [],
        "keywords":   [],
        "model_used": f"error:{last_error_type}",
        "prompt_ver": PROMPT_VERSION,
        "success":    False,
        "error_type": last_error_type,
    }

# ---------------------------------------------------------------------------
# BigQuery helpers
# ---------------------------------------------------------------------------

def _full(table: str) -> str:
    return f"`{GCP_PROJECT}.{BQ_DATASET}.{table}`"


def ensure_output_table(client: bigquery.Client) -> None:
    """Create summarized_articles and failed_summaries tables if they do not exist."""
    dataset_ref = bigquery.DatasetReference(GCP_PROJECT, BQ_DATASET)
    try:
        client.get_dataset(dataset_ref)
    except Exception:
        ds = bigquery.Dataset(dataset_ref)
        ds.location = "US"
        client.create_dataset(ds, exists_ok=True)

    # summarized_articles
    summary_schema = [
        bigquery.SchemaField("id",             "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("source_id",      "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("title",          "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("link",           "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("source",         "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("pub_date",       "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("label",          "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("summary",        "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("key_points",     "STRING",    mode="NULLABLE"),  # JSON array string
        bigquery.SchemaField("keywords",       "STRING",    mode="NULLABLE"),  # comma-separated
        bigquery.SchemaField("model_used",     "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("prompt_version", "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("summarized_at",  "TIMESTAMP", mode="REQUIRED"),
    ]
    table_ref = bigquery.TableReference(dataset_ref, BQ_OUTPUT_TABLE)
    client.create_table(bigquery.Table(table_ref, summary_schema), exists_ok=True)

    # failed_summaries — records every article that exhausted all retries
    failed_schema = [
        bigquery.SchemaField("id",             "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("source_id",      "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("link",           "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("error_type",     "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("error_message",  "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("attempt_count",  "INTEGER",   mode="NULLABLE"),
        bigquery.SchemaField("model_used",     "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("prompt_version", "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("failed_at",      "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("resolved",       "BOOLEAN",   mode="NULLABLE"),
    ]
    failed_ref = bigquery.TableReference(dataset_ref, BQ_FAILED_TABLE)
    client.create_table(bigquery.Table(failed_ref, failed_schema), exists_ok=True)

    logger.info("BQ tables ready: %s, %s.", BQ_OUTPUT_TABLE, BQ_FAILED_TABLE)


def log_failure(
    client: bigquery.Client,
    source_id: str,
    link: str,
    error_type: str,
    error_message: str,
    attempt_count: int,
) -> None:
    """Stream-insert one failure record into failed_summaries for later inspection/retry."""
    row = {
        "id":             str(uuid.uuid4()),
        "source_id":      source_id or "",
        "link":           link      or "",
        "error_type":     error_type,
        "error_message":  error_message[:500],
        "attempt_count":  attempt_count,
        "model_used":     f"{GEMINI_MODEL}@prompt-{PROMPT_VERSION}",
        "prompt_version": PROMPT_VERSION,
        "failed_at":      datetime.now(timezone.utc).isoformat(),
        "resolved":       False,
    }
    table_id = f"{GCP_PROJECT}.{BQ_DATASET}.{BQ_FAILED_TABLE}"
    errors = client.insert_rows_json(table_id, [row])
    if errors:
        logger.error("Could not write failure record to BQ: %s", errors)
    else:
        logger.info("Failure logged → %s [%s]", (link or "")[:60], error_type)


def fetch_unsummarized(client: bigquery.Client) -> list[dict]:
    """
    Return up to MAX_ARTICLES_PER_RUN articles from labeled_articles whose link
    does not yet appear in summarized_articles, excluding NOISE.
    """
    skip_clause = " AND ".join(f"l.label != '{lbl}'" for lbl in SKIP_LABELS)
    query = f"""
        SELECT
            l.id  AS source_id,
            l.title,
            l.link,
            l.source,
            l.pub_date,
            l.content,
            l.label
        FROM {_full(BQ_SOURCE_TABLE)} AS l
        LEFT JOIN {_full(BQ_OUTPUT_TABLE)} AS s
            ON l.link = s.link
        WHERE s.link IS NULL
          AND LENGTH(COALESCE(l.content, '')) >= 100
          AND {skip_clause}
        ORDER BY l.labeled_at DESC
        LIMIT {MAX_ARTICLES_PER_RUN}
    """
    try:
        rows = list(client.query(query).result())
    except Exception as exc:
        logger.warning("JOIN query failed (%s) — falling back to full scan.", exc)
        query = f"""
            SELECT id AS source_id, title, link, source, pub_date, content, label
            FROM {_full(BQ_SOURCE_TABLE)}
            WHERE LENGTH(COALESCE(content, '')) >= 100
              AND {skip_clause}
            ORDER BY labeled_at DESC
            LIMIT {MAX_ARTICLES_PER_RUN}
        """
        rows = list(client.query(query).result())

    logger.info("Fetched %d articles to summarize.", len(rows))
    return [dict(row) for row in rows]


def insert_rows(client: bigquery.Client, rows: list[dict]) -> int:
    """Stream-insert a batch; returns the count successfully inserted."""
    if not rows:
        return 0
    table_id = f"{GCP_PROJECT}.{BQ_DATASET}.{BQ_OUTPUT_TABLE}"
    errors   = client.insert_rows_json(table_id, rows)
    if errors:
        logger.error("BigQuery insert errors: %s", errors)
        return max(0, len(rows) - len(errors))
    return len(rows)

# ---------------------------------------------------------------------------
# Cloud Function entry point
# ---------------------------------------------------------------------------

@functions_framework.http
def run_summarize(request):
    """
    HTTP-triggered Cloud Function — Summarisation pipeline v2.

    Flow:
      1. Fetch articles from labeled_articles not yet in summarized_articles
      2. Call Gemini/Vertex AI with GenerationConfig (temperature=0.2, JSON schema enforcement)
      3. Validate structured output; re-submit with corrective prompt if invalid
      4. Log exhausted failures to failed_summaries BQ table
      5. Stream-insert successful results into summarized_articles

    Backend selection (env var USE_VERTEX):
      true  → Vertex AI SDK — uses ADC/service account, no API key (production)
      false → Gemini Developer API — uses GEMINI_API_KEY (development)

    Env vars: GCP_PROJECT, USE_VERTEX, VERTEX_LOCATION, GEMINI_API_KEY,
              GEMINI_MODEL, PROMPT_VERSION, BQ_DATASET, BQ_SOURCE_TABLE,
              BQ_OUTPUT_TABLE, BQ_FAILED_TABLE, MAX_ARTICLES_PER_RUN,
              GEMINI_DELAY, MAX_RETRIES, MAX_CONTENT_CHARS
    """
    run_start     = datetime.now(timezone.utc)
    summarized_at = run_start.isoformat()
    logger.info(
        "=== run_summarize started | prompt=%s | backend=%s | model=%s ===",
        PROMPT_VERSION,
        "vertex" if USE_VERTEX else "gemini-api",
        GEMINI_MODEL,
    )

    bq = bigquery.Client(project=GCP_PROJECT)
    ensure_output_table(bq)

    # ── 1. Fetch ──────────────────────────────────────────────────────────────
    articles = fetch_unsummarized(bq)
    if not articles:
        return {"status": "ok", "message": "No articles to summarize.", "summarized": 0}, 200

    # ── 2. Summarize ─────────────────────────────────────────────────────────
    rows_to_insert: list[dict] = []
    total_inserted  = 0
    success_count   = 0
    error_count     = 0
    error_breakdown: dict[str, int] = {}

    for i, article in enumerate(articles):
        title     = article.get("title",     "") or ""
        content   = article.get("content",   "") or ""
        label     = article.get("label",     "") or ""
        link      = article.get("link",      "") or ""
        source_id = article.get("source_id", "") or ""

        logger.info("[%d/%d] Summarizing: %s", i + 1, len(articles), title[:80])

        result = summarize_article(
            title=title,
            content=content,
            label=label,
            source_id=source_id,
            link=link,
            bq_client=bq,
        )

        if result["success"]:
            success_count += 1
        else:
            error_count += 1
            et = result.get("error_type") or "unknown"
            error_breakdown[et] = error_breakdown.get(et, 0) + 1

        rows_to_insert.append({
            "id":             str(uuid.uuid4()),
            "source_id":      source_id,
            "title":          title,
            "link":           link,
            "source":         article.get("source",   ""),
            "pub_date":       article.get("pub_date", ""),
            "label":          label,
            "summary":        result["summary"],
            "key_points":     json.dumps(result["key_points"], ensure_ascii=False),
            "keywords":       ", ".join(result["keywords"]),
            "model_used":     result["model_used"],
            "prompt_version": result["prompt_ver"],
            "summarized_at":  summarized_at,
        })

        # Batch-insert every 20 rows to avoid memory build-up
        if len(rows_to_insert) >= 20:
            batch = insert_rows(bq, rows_to_insert)
            total_inserted += batch
            logger.info("Batch inserted %d rows (total: %d)", batch, total_inserted)
            rows_to_insert = []

        if i < len(articles) - 1:
            time.sleep(GEMINI_DELAY)

    # ── 3. Flush remaining rows ───────────────────────────────────────────────
    if rows_to_insert:
        batch = insert_rows(bq, rows_to_insert)
        total_inserted += batch
        logger.info("Final batch: %d rows (total: %d)", batch, total_inserted)

    elapsed = round((datetime.now(timezone.utc) - run_start).total_seconds(), 1)
    run_summary = {
        "status":           "ok",
        "prompt_version":   PROMPT_VERSION,
        "backend":          "vertex" if USE_VERTEX else "gemini-api",
        "model":            GEMINI_MODEL,
        "articles_fetched": len(articles),
        "summarized":       total_inserted,
        "success":          success_count,
        "errors":           error_count,
        "error_breakdown":  error_breakdown,
        "elapsed_seconds":  elapsed,
        "run_at":           summarized_at,
    }
    logger.info("Run complete: %s", run_summary)
    return run_summary, 200
