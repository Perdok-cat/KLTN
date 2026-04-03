from __future__ import annotations

import functions_framework
import os
import re
import uuid
import logging
import unicodedata
import tempfile
from datetime import datetime, timezone

import joblib
from google.cloud import bigquery, storage
from underthesea import word_tokenize

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration  (override via Cloud Function environment variables)
# ---------------------------------------------------------------------------

GCP_PROJECT     = os.environ.get("GCP_PROJECT",     "your-gcp-project-id")
BQ_DATASET      = os.environ.get("BQ_DATASET",      "ai_news")
BQ_SOURCE_TABLE = os.environ.get("BQ_SOURCE_TABLE", "raw_articles")
BQ_OUTPUT_TABLE = os.environ.get("BQ_OUTPUT_TABLE", "labeled_articles")

# GCS paths for model artefacts
GCS_BUCKET  = os.environ.get("GCS_BUCKET",  "your-bucket-name")
TFIDF_BLOB  = os.environ.get("TFIDF_BLOB",  "models/tfidf_vectorizer.pkl")
MODEL_BLOB  = os.environ.get("MODEL_BLOB",  "models/LinearSVC.pkl")

# How many articles to process per invocation
MAX_ARTICLES_PER_RUN = int(os.environ.get("MAX_ARTICLES_PER_RUN", "200"))

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

_tfidf    = None
_ml_model = None
_model_name = ""


def load_models() -> None:
    """
    Download TF-IDF vectorizer and classifier from GCS into /tmp,
    then load them into module-level singletons.
    Called once on cold start (and again if somehow they become None).
    """
    global _tfidf, _ml_model, _model_name

    logger.info("Downloading model artefacts from gs://%s …", GCS_BUCKET)
    gcs    = storage.Client()
    bucket = gcs.bucket(GCS_BUCKET)

    tmp_dir    = tempfile.mkdtemp()
    tfidf_path = os.path.join(tmp_dir, "tfidf.pkl")
    model_path = os.path.join(tmp_dir, "model.pkl")

    bucket.blob(TFIDF_BLOB).download_to_filename(tfidf_path)
    bucket.blob(MODEL_BLOB).download_to_filename(model_path)

    _tfidf      = joblib.load(tfidf_path)
    _ml_model   = joblib.load(model_path)
    _model_name = os.path.splitext(os.path.basename(MODEL_BLOB))[0]
    logger.info("Models loaded: tfidf=%s  model=%s", TFIDF_BLOB, _model_name)


def get_models():
    """Return (tfidf, model) — loading from GCS on first call."""
    if _tfidf is None or _ml_model is None:
        load_models()
    return _tfidf, _ml_model


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
    """
    Title is repeated twice to weight it more heavily — mirrors the
    training pipeline in src/ML/inference.py:
        df["text"] = df["title"] + " " + df["title"] + " " + df["content"]
    """
    raw = f"{title} {title} {content}"
    return tokenize(clean_text(raw))


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def score_to_confidence(score: float) -> str:
    """Convert a normalised [0, 1] score to a human-readable confidence level."""
    if score >= 0.75:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"


def predict_single(title: str, content: str) -> dict:
    """
    Run the full ML pipeline on one article.
    Returns {"label", "confidence", "model_used"}.
    """
    if not content or len(content.strip()) < 50:
        return {"label": "NOISE", "confidence": "high", "model_used": "rule"}

    tfidf, model = get_models()

    text = build_feature_text(title, content)
    X    = tfidf.transform([text])
    pred = int(model.predict(X)[0])
    label = LABEL_MAP.get(pred, "NOISE")

    # Derive confidence from decision scores / probabilities
    confidence = "medium"
    try:
        if hasattr(model, "predict_proba"):
            proba      = model.predict_proba(X)[0]
            max_prob   = float(proba.max())
            confidence = score_to_confidence(max_prob)
        elif hasattr(model, "decision_function"):
            scores     = model.decision_function(X)[0]
            # Normalise so the winning margin ≈ probability
            exp_scores = [2 ** s for s in scores]
            total      = sum(exp_scores)
            max_norm   = max(exp_scores) / total if total > 0 else 0.5
            confidence = score_to_confidence(max_norm)
    except Exception:
        pass

    return {"label": label, "confidence": confidence, "model_used": _model_name}


# ---------------------------------------------------------------------------
# BigQuery helpers
# ---------------------------------------------------------------------------

def _full_table(table: str) -> str:
    return f"`{GCP_PROJECT}.{BQ_DATASET}.{table}`"


def ensure_output_table(client: bigquery.Client) -> None:
    """Create the labeled_articles table if it does not exist yet."""
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
    logger.info("Output table %s.%s.%s is ready.", GCP_PROJECT, BQ_DATASET, BQ_OUTPUT_TABLE)


def fetch_unlabeled_articles(client: bigquery.Client) -> list[dict]:
    """
    Return up to MAX_ARTICLES_PER_RUN articles from raw_articles whose link
    does not yet appear in labeled_articles.
    """
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
        # labeled_articles may not exist on the very first run
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

    logger.info("Fetched %d unlabeled articles.", len(rows))
    return [dict(row) for row in rows]


def insert_rows(client: bigquery.Client, rows: list[dict]) -> int:
    """Stream-insert a batch of rows; returns the number successfully inserted."""
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
    """
    HTTP-triggered Cloud Function — ML-only inference pipeline.

    Flow:
      1. Load TF-IDF + sklearn model from GCS (cached after first call)
      2. Fetch articles from raw_articles that are not yet in labeled_articles
      3. Preprocess text (clean → underthesea tokenize) and predict label
      4. Stream-insert results into labeled_articles
      5. Return a JSON summary

    Required environment variables:
      GCP_PROJECT   – GCP project ID
      GCS_BUCKET    – GCS bucket name containing model .pkl files
      TFIDF_BLOB    – path inside bucket for TF-IDF vectorizer  (default: models/tfidf_vectorizer.pkl)
      MODEL_BLOB    – path inside bucket for classifier          (default: models/LinearSVC.pkl)

    Optional environment variables:
      BQ_DATASET, BQ_SOURCE_TABLE, BQ_OUTPUT_TABLE, MAX_ARTICLES_PER_RUN
    """
    run_start      = datetime.now(timezone.utc)
    labeled_at_str = run_start.isoformat()
    logger.info("=== run_inference (ML) started at %s ===", labeled_at_str)

    bq = bigquery.Client(project=GCP_PROJECT)
    ensure_output_table(bq)

    # ── 1. Fetch unlabeled articles ───────────────────────────────────────────
    articles = fetch_unlabeled_articles(bq)
    if not articles:
        return {"status": "ok", "message": "No unlabeled articles found.", "labeled": 0}, 200

    # ── 2. Classify ──────────────────────────────────────────────────────────
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

        rows_to_insert.append({
            "id":          str(uuid.uuid4()),
            "title":       title,
            "link":        link,
            "source":      article.get("source",     ""),
            "pub_date":    article.get("pub_date",   ""),
            "content":     content,
            "crawl_date":  article.get("crawl_date", None),
            "label":       label,
            "confidence":  result.get("confidence",  ""),
            "model_used":  result.get("model_used",  ""),
            "labeled_at":  labeled_at_str,
        })

        # Batch-insert every 50 rows
        if len(rows_to_insert) >= 50:
            batch = insert_rows(bq, rows_to_insert)
            total_labeled += batch
            logger.info("Batch inserted %d rows (total: %d)", batch, total_labeled)
            rows_to_insert = []

    # ── 3. Insert remaining rows ──────────────────────────────────────────────
    if rows_to_insert:
        batch = insert_rows(bq, rows_to_insert)
        total_labeled += batch
        logger.info("Final batch: %d rows (total: %d)", batch, total_labeled)

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
