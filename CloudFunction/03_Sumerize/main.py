from __future__ import annotations

import functions_framework
import os
import re
import json
import time
import uuid
import logging
from datetime import datetime, timezone

import google.generativeai as genai
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration  (override via Cloud Function environment variables)
# ---------------------------------------------------------------------------

GCP_PROJECT      = os.environ.get("GCP_PROJECT",      "project-e5ef1531-7ef9-4232-b30")
BQ_DATASET       = os.environ.get("BQ_DATASET",       "ai_news_data")
BQ_SOURCE_TABLE  = os.environ.get("BQ_SOURCE_TABLE",  "labeled_articles")
BQ_OUTPUT_TABLE  = os.environ.get("BQ_OUTPUT_TABLE",  "summarized_articles")

GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY",   "")
GEMINI_MODEL     = os.environ.get("GEMINI_MODEL",     "gemini-2.5-flash")

# Max articles per invocation (Gemini free tier: 10 req/min → keep ~50 safe)
MAX_ARTICLES_PER_RUN = int(os.environ.get("MAX_ARTICLES_PER_RUN", "50"))

# Delay between Gemini calls in seconds (free tier safe: 7 s)
GEMINI_DELAY = float(os.environ.get("GEMINI_DELAY", "7"))

# Labels to skip summarisation (no value in summarising noise)
SKIP_LABELS = {"NOISE"}

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROMPT = """Bạn là một biên tập viên công nghệ AI chuyên nghiệp. Hãy tóm tắt bài báo dưới đây bằng tiếng Việt.

TIÊU ĐỀ: {title}
LOẠI BÀI: {label}

NỘI DUNG:
{content}

---
Yêu cầu đầu ra JSON hợp lệ (không có markdown fence):
{{
  "summary": "Đoạn tóm tắt ngắn gọn 3-5 câu, súc tích, dễ hiểu cho người đọc phổ thông.",
  "key_points": [
    "Điểm chính 1",
    "Điểm chính 2",
    "Điểm chính 3"
  ],
  "keywords": ["từ khóa 1", "từ khóa 2", "từ khóa 3", "từ khóa 4", "từ khóa 5"]
}}

Quy tắc:
- Tóm tắt bằng tiếng Việt, rõ ràng, trung lập.
- key_points: 3-5 gạch đầu dòng, mỗi gạch 1 câu ngắn.
- keywords: 3-7 từ/cụm từ quan trọng nhất trong bài.
- Chỉ trả về JSON, không thêm bất kỳ text nào khác."""


# ---------------------------------------------------------------------------
# Gemini singleton
# ---------------------------------------------------------------------------

_gemini_model = None


def get_gemini():
    global _gemini_model
    if _gemini_model is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY environment variable is not set.")
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel(GEMINI_MODEL)
        logger.info("Gemini model '%s' initialised.", GEMINI_MODEL)
    return _gemini_model


# ---------------------------------------------------------------------------
# Summarisation logic
# ---------------------------------------------------------------------------

def _parse_response(raw: str) -> dict:
    """Strip markdown fences and parse JSON from Gemini response."""
    text = raw.strip()
    text = re.sub(r"^```json?\s*", "", text)
    text = re.sub(r"\s*```$",      "", text)
    return json.loads(text.strip())


def summarize_article(title: str, content: str, label: str, max_retries: int = 3) -> dict:
    """
    Call Gemini to produce a structured summary.
    Returns:
        {
          "summary":    str,
          "key_points": list[str],   # stored as JSON string in BQ
          "keywords":   list[str],   # stored as comma-separated string in BQ
          "model_used": str,
          "success":    bool,
        }
    """
    # Short-circuit for empty content
    if not content or len(content.strip()) < 100:
        return {
            "summary":    title,
            "key_points": [],
            "keywords":   [],
            "model_used": "rule",
            "success":    False,
        }

    model  = get_gemini()
    prompt = _PROMPT.format(
        title=title,
        label=label,
        content=content[:6000],   # stay well within token limits
    )

    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            result   = _parse_response(response.text)

            # Normalise types
            summary    = str(result.get("summary",    title))
            key_points = result.get("key_points", [])
            keywords   = result.get("keywords",   [])

            if not isinstance(key_points, list):
                key_points = []
            if not isinstance(keywords, list):
                keywords = []

            return {
                "summary":    summary,
                "key_points": key_points,
                "keywords":   keywords,
                "model_used": GEMINI_MODEL,
                "success":    True,
            }

        except json.JSONDecodeError:
            # Gemini sometimes wraps the output; try raw text as summary
            raw = getattr(response, "text", "") if "response" in dir() else ""
            logger.warning("JSON parse failed (attempt %d). Raw: %s…", attempt + 1, raw[:120])
            if attempt == max_retries - 1:
                return {
                    "summary":    raw[:1000] if raw else title,
                    "key_points": [],
                    "keywords":   [],
                    "model_used": GEMINI_MODEL,
                    "success":    False,
                }

        except Exception as exc:
            err = str(exc)
            logger.warning("Gemini attempt %d/%d: %s", attempt + 1, max_retries, err)

            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                wait = 10.0
                m = re.search(r"retry in ([\d.]+)s", err)
                if m:
                    wait = float(m.group(1)) + 2
                logger.info("Rate-limited — waiting %.1f s …", wait)
                time.sleep(wait)
            elif attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    return {
        "summary":    title,
        "key_points": [],
        "keywords":   [],
        "model_used": "error",
        "success":    False,
    }


# ---------------------------------------------------------------------------
# BigQuery helpers
# ---------------------------------------------------------------------------

def _full(table: str) -> str:
    return f"`{GCP_PROJECT}.{BQ_DATASET}.{table}`"


def ensure_output_table(client: bigquery.Client) -> None:
    """Create summarized_articles table if it does not exist."""
    dataset_ref = bigquery.DatasetReference(GCP_PROJECT, BQ_DATASET)
    try:
        client.get_dataset(dataset_ref)
    except Exception:
        ds = bigquery.Dataset(dataset_ref)
        ds.location = "US"
        client.create_dataset(ds, exists_ok=True)

    schema = [
        bigquery.SchemaField("id",             "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("source_id",      "STRING",    mode="NULLABLE"),  # FK → labeled_articles.id
        bigquery.SchemaField("title",          "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("link",           "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("source",         "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("pub_date",       "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("label",          "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("summary",        "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("key_points",     "STRING",    mode="NULLABLE"),  # JSON array string
        bigquery.SchemaField("keywords",       "STRING",    mode="NULLABLE"),  # comma-separated
        bigquery.SchemaField("model_used",     "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("summarized_at",  "TIMESTAMP", mode="REQUIRED"),
    ]
    table_ref = bigquery.TableReference(dataset_ref, BQ_OUTPUT_TABLE)
    client.create_table(bigquery.Table(table_ref, schema=schema), exists_ok=True)
    logger.info("Output table %s.%s.%s ready.", GCP_PROJECT, BQ_DATASET, BQ_OUTPUT_TABLE)


def fetch_unsummarized(client: bigquery.Client) -> list[dict]:
    """
    Return up to MAX_ARTICLES_PER_RUN articles from labeled_articles whose link
    does not yet appear in summarized_articles, excluding NOISE.
    """
    skip_clause = " AND ".join(
        f"l.label != '{lbl}'" for lbl in SKIP_LABELS
    )
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
            SELECT
                id AS source_id, title, link, source, pub_date, content, label
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
    HTTP-triggered Cloud Function — Summarisation pipeline.

    Flow:
      1. Fetch articles from labeled_articles not yet in summarized_articles
         (NOISE articles are automatically skipped)
      2. Call Gemini to produce: summary, key_points, keywords
      3. Stream-insert results into summarized_articles
      4. Return a JSON summary

    Required environment variables:
      GCP_PROJECT    – GCP project ID
      GEMINI_API_KEY – Gemini API key

    Optional environment variables:
      BQ_DATASET, BQ_SOURCE_TABLE, BQ_OUTPUT_TABLE
      GEMINI_MODEL, GEMINI_DELAY, MAX_ARTICLES_PER_RUN
    """
    run_start       = datetime.now(timezone.utc)
    summarized_at   = run_start.isoformat()
    logger.info("=== run_summarize started at %s ===", summarized_at)

    bq = bigquery.Client(project=GCP_PROJECT)
    ensure_output_table(bq)

    # ── 1. Fetch articles to summarize ────────────────────────────────────────
    articles = fetch_unsummarized(bq)
    if not articles:
        return {"status": "ok", "message": "No articles to summarize.", "summarized": 0}, 200

    # ── 2. Summarize ─────────────────────────────────────────────────────────
    rows_to_insert: list[dict] = []
    total_inserted = 0
    success_count  = 0
    error_count    = 0

    for i, article in enumerate(articles):
        title   = article.get("title",   "") or ""
        content = article.get("content", "") or ""
        label   = article.get("label",   "") or ""
        link    = article.get("link",    "") or ""

        logger.info("[%d/%d] Summarizing: %s", i + 1, len(articles), title[:80])

        result = summarize_article(title, content, label)

        if result["success"]:
            success_count += 1
        else:
            error_count += 1

        rows_to_insert.append({
            "id":            str(uuid.uuid4()),
            "source_id":     article.get("source_id", ""),
            "title":         title,
            "link":          link,
            "source":        article.get("source",   ""),
            "pub_date":      article.get("pub_date", ""),
            "label":         label,
            "summary":       result["summary"],
            "key_points":    json.dumps(result["key_points"],  ensure_ascii=False),
            "keywords":      ", ".join(result["keywords"]),
            "model_used":    result["model_used"],
            "summarized_at": summarized_at,
        })

        # Batch-insert every 20 rows
        if len(rows_to_insert) >= 20:
            batch = insert_rows(bq, rows_to_insert)
            total_inserted += batch
            logger.info("Batch inserted %d rows (total: %d)", batch, total_inserted)
            rows_to_insert = []

        # Rate-limit delay
        if i < len(articles) - 1:
            time.sleep(GEMINI_DELAY)

    # ── 3. Insert remaining rows ──────────────────────────────────────────────
    if rows_to_insert:
        batch = insert_rows(bq, rows_to_insert)
        total_inserted += batch
        logger.info("Final batch: %d rows (total: %d)", batch, total_inserted)

    elapsed = round((datetime.now(timezone.utc) - run_start).total_seconds(), 1)

    summary = {
        "status":           "ok",
        "articles_fetched": len(articles),
        "summarized":       total_inserted,
        "success":          success_count,
        "errors":           error_count,
        "elapsed_seconds":  elapsed,
        "run_at":           summarized_at,
    }
    logger.info("Run summary: %s", summary)
    return summary, 200
