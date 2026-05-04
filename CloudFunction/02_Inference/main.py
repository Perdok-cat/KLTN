from __future__ import annotations

import functions_framework
import os
import re
import uuid
import logging
import unicodedata
from datetime import datetime, timezone

from google.cloud import bigquery, aiplatform
from underthesea import word_tokenize

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration  (override via Cloud Function environment variables)
# ---------------------------------------------------------------------------

GCP_PROJECT     = os.environ.get("GCP_PROJECT",     "project-e5ef1531-7ef9-4232-b30")
BQ_DATASET      = os.environ.get("BQ_DATASET",      "ai_news_data")
BQ_SOURCE_TABLE = os.environ.get("BQ_SOURCE_TABLE", "raw_articles")
BQ_OUTPUT_TABLE = os.environ.get("BQ_OUTPUT_TABLE", "labeled_articles")

# Vertex AI Configuration
VERTEX_LOCATION    = os.environ.get("VERTEX_LOCATION",    "us-central1")
VERTEX_ENDPOINT_ID = os.environ.get("VERTEX_ENDPOINT_ID", "3151060137473474560")

# How many articles to process per invocation
MAX_ARTICLES_PER_RUN = int(os.environ.get("MAX_ARTICLES_PER_RUN", "10"))

# ---------------------------------------------------------------------------
# Label mapping  (must match training encoding in src/ML/train.py)
# ---------------------------------------------------------------------------

LABEL_MAP: dict[int, str] = {
    0: "DEEP DIVE",
    1: "MARKET SIGNALS",
    2: "NOISE",
    3: "SOLUTIONS & USE CASES",
}

# ---------------------------------------------------------------------------
# Module-level singletons  (warm Cloud Function reuses these)
# ---------------------------------------------------------------------------

_endpoint = None
_model_name = "Vertex-AI-Pipeline"

def init_vertex_endpoint() -> None:
    """Initialize Vertex AI Endpoint connection on cold start."""
    global _endpoint
    logger.info("Initializing Vertex AI Endpoint connection...")
    aiplatform.init(project=GCP_PROJECT, location=VERTEX_LOCATION)
    _endpoint = aiplatform.Endpoint(endpoint_name=VERTEX_ENDPOINT_ID)
    logger.info("Vertex AI Endpoint ready.")

def get_endpoint():
    """Return endpoint — connecting on first call."""
    if _endpoint is None:
        init_vertex_endpoint()
    return _endpoint

# ---------------------------------------------------------------------------
# Text preprocessing  (identical to src/ML/inference.py)
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text))
    text = text.lower()
    text = re.sub(r"http\S+|www\.\S+", " ", text)
    text = re.sub(r"\S+@\S+\.\S+",     " ", text)
    text = re.sub(r"<.*?>",             " ", text)
    text = re.sub(r"[^a-zA-ZÀ-ỹà-ỹ\s]", " ", text)
    text = re.sub(r"\s+",               " ", text).strip()
    return text

def tokenize(text: str) -> str:
    """Vietnamese word tokenisation using underthesea."""
    return word_tokenize(text, format="text")

def build_feature_text(title: str, content: str) -> str:
    raw = f"{title} {title} {content}"
    return tokenize(clean_text(raw))

# ---------------------------------------------------------------------------
# Confidence scoring & Inference
# ---------------------------------------------------------------------------

def predict_single(title: str, content: str) -> dict:
    """
    Call Vertex AI Endpoint for inference.
    Returns {"label", "confidence", "model_used"}.
    """
    if not content or len(content.strip()) < 50:
        return {"label": "NOISE", "confidence": "high", "model_used": "rule"}

    endpoint = get_endpoint()

    # 1. Làm sạch và Tokenize (KHÔNG vector hóa ở đây nữa)
    text = build_feature_text(title, content)

    # 2. Gửi chuỗi văn bản trực tiếp sang Vertex AI
    # Container Scikit-Learn của Vertex AI sẽ tự động chạy text qua Pipeline (TF-IDF -> SVC)
    instances = [text]

    # 3. Gọi Vertex AI Endpoint
    response = endpoint.predict(instances=instances)

    # 4. Giải mã kết quả
    pred = int(response.predictions[0])
    label = LABEL_MAP.get(pred, "NOISE")

    # Điểm confidence tạm để mức mặc định với SVC qua Vertex API
    confidence = "medium"

    return {"label": label, "confidence": confidence, "model_used": _model_name}

# ---------------------------------------------------------------------------
# BigQuery helpers
# ---------------------------------------------------------------------------

def _full_table(table: str) -> str:
    return f"`{GCP_PROJECT}.{BQ_DATASET}.{table}`"

def ensure_output_table(client: bigquery.Client) -> None:
    dataset_ref = bigquery.DatasetReference(GCP_PROJECT, BQ_DATASET)
    try:
        client.get_dataset(dataset_ref)
    except Exception:
        ds = bigquery.Dataset(dataset_ref)
        ds.location = "US"
        client.create_dataset(ds, exists_ok=True)
        logger.info("Dataset %s.%s created.", GCP_PROJECT, BQ_DATASET)

    schema = [
        bigquery.SchemaField("id",          "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("title",       "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("link",        "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("source",      "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("pub_date",    "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("content",     "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("crawl_date",  "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("label",       "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("confidence",  "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("model_used",  "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("labeled_at",  "TIMESTAMP", mode="REQUIRED"),
    ]
    table_ref = bigquery.TableReference(dataset_ref, BQ_OUTPUT_TABLE)
    client.create_table(bigquery.Table(table_ref, schema=schema), exists_ok=True)

def fetch_unlabeled_articles(client: bigquery.Client) -> list[dict]:
    query = f"""
        SELECT
            r.id, r.title, r.link, r.source, r.pub_date, r.content,
            CAST(r.crawl_date AS STRING) AS crawl_date
        FROM {_full_table(BQ_SOURCE_TABLE)} AS r
        LEFT JOIN {_full_table(BQ_OUTPUT_TABLE)} AS l
            ON r.link = l.link
        WHERE l.link IS NULL
          AND LENGTH(COALESCE(r.content, '')) >= 50
        ORDER BY r.crawl_date DESC
        LIMIT {MAX_ARTICLES_PER_RUN}
    """
    try:
        rows = list(client.query(query).result())
    except Exception as exc:
        logger.warning("JOIN query failed (%s) — falling back to full scan.", exc)
        query = f"""
            SELECT
                id, title, link, source, pub_date, content,
                CAST(crawl_date AS STRING) AS crawl_date
            FROM {_full_table(BQ_SOURCE_TABLE)}
            WHERE LENGTH(COALESCE(content, '')) >= 50
            ORDER BY crawl_date DESC
            LIMIT {MAX_ARTICLES_PER_RUN}
        """
        rows = list(client.query(query).result())

    return [dict(row) for row in rows]

def insert_rows(client: bigquery.Client, rows: list[dict]) -> int:
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
def run_inference(request):
    run_start      = datetime.now(timezone.utc)
    labeled_at_str = run_start.isoformat()
    logger.info("=== run_inference (Vertex AI Pipeline) started at %s ===", labeled_at_str)

    bq = bigquery.Client(project=GCP_PROJECT)
    ensure_output_table(bq)

    articles = fetch_unlabeled_articles(bq)
    if not articles:
        return {"status": "ok", "message": "No unlabeled articles found.", "labeled": 0}, 200

    rows_to_insert: list[dict] = []
    label_counts: dict[str, int] = {}
    total_labeled = 0

    for i, article in enumerate(articles):
        title   = article.get("title",   "") or ""
        content = article.get("content", "") or ""
        link    = article.get("link",    "") or ""

        logger.info("[%d/%d] %s", i + 1, len(articles), title[:80])

        result = predict_single(title, content)
        label  = result["label"]
        label_counts[label] = label_counts.get(label, 0) + 1

        raw_crawl_date = article.get("crawl_date")
        clean_crawl_date = None

        if raw_crawl_date:
            clean_crawl_date = str(raw_crawl_date).split('+')[0].strip()

        rows_to_insert.append({
            "id":          str(uuid.uuid4()),
            "title":       title,
            "link":        link,
            "source":      article.get("source",     ""),
            "pub_date":    article.get("pub_date",   ""),
            "content":     content,
            "crawl_date":  clean_crawl_date,
            "label":       label,
            "confidence":  result.get("confidence",  ""),
            "model_used":  result.get("model_used",  ""),
            "labeled_at":  labeled_at_str,
        })

        if len(rows_to_insert) >= 50:
            batch = insert_rows(bq, rows_to_insert)
            total_labeled += batch
            rows_to_insert = []

    if rows_to_insert:
        batch = insert_rows(bq, rows_to_insert)
        total_labeled += batch

    elapsed = round((datetime.now(timezone.utc) - run_start).total_seconds(), 1)

    summary = {
        "status":             "ok",
        "articles_fetched":   len(articles),
        "labeled":            total_labeled,
        "label_distribution": label_counts,
        "model_used":         _model_name,
        "elapsed_seconds":    elapsed,
        "run_at":             labeled_at_str,
    }
    logger.info("Run summary: %s", summary)
    return summary, 200
