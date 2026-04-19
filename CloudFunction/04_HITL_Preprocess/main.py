"""
Cloud Function: 04_HITL_Preprocess
-----------------------------------
Được gọi bởi Backend khi tích lũy đủ batch HITL reviews (mặc định 10 bài).

Pipeline preprocessing đồng bộ với Data_PreProcessing.ipynb:
  1. text = title + ' ' + content
  2. lowercase
  3. Xóa URL / email / HTML tags
  4. Xóa ký tự đặc biệt (giữ a-zA-ZÀ-ỹà-ỹ và khoảng trắng)
  5. Normalize whitespace + strip
  6. underthesea word_tokenize(text, format="text")
  7. unicodedata2.normalize('NFC', text_tok)
  8. Label encode: DEEP DIVE=0, MARKET SIGNALS=1, NOISE=2, SOLUTIONS & USE CASES=3

Luồng xử lý:
  1. Query hitl_reviews (is_used_for_retraining=FALSE) JOIN labeled_articles
  2. Preprocess text → text_tok
  3. INSERT vào mlops_dataset.hitl_staging_data
  4. UPDATE hitl_reviews SET is_used_for_retraining = TRUE

Biến môi trường:
  GCP_PROJECT           – Google Cloud Project ID
  SRC_BQ_DATASET        – Dataset nguồn (default: ai_news)
  SRC_LABELED_TABLE     – Bảng labeled_articles (default: labeled_articles)
  SRC_HITL_TABLE        – Bảng hitl_reviews (default: hitl_reviews)
  DST_BQ_DATASET        – Dataset đích (default: mlops_dataset)
  DST_STAGING_TABLE     – Bảng đích (default: hitl_staging_data)
  MAX_ROWS_PER_RUN      – Số bản ghi tối đa mỗi lần chạy (default: 500)
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone

import functions_framework
import unicodedata2
from google.cloud import bigquery
from underthesea import word_tokenize

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
GCP_PROJECT       = os.environ.get("GCP_PROJECT",         "your-gcp-project-id")
SRC_BQ_DATASET    = os.environ.get("SRC_BQ_DATASET",      "ai_news")
SRC_LABELED_TABLE = os.environ.get("SRC_LABELED_TABLE",   "labeled_articles")
SRC_HITL_TABLE    = os.environ.get("SRC_HITL_TABLE",      "hitl_reviews")
DST_BQ_DATASET    = os.environ.get("DST_BQ_DATASET",      "mlops_dataset")
DST_STAGING_TABLE = os.environ.get("DST_STAGING_TABLE",   "hitl_staging_data")
MAX_ROWS_PER_RUN  = int(os.environ.get("MAX_ROWS_PER_RUN", "500"))

# ── Label encoding – phải khớp với LabelEncoder trong notebook ─────────────────
# {'DEEP DIVE': 0, 'MARKET SIGNALS': 1, 'NOISE': 2, 'SOLUTIONS & USE CASES': 3}
LABEL_ENC: dict[str, int] = {
    "DEEP DIVE":             0,
    "MARKET SIGNALS":        1,
    "NOISE":                 2,
    "SOLUTIONS & USE CASES": 3,
}

HITL_STATUS_APPROVED = "APPROVED"
HITL_STATUS_REJECTED = "REJECTED_NOISE"

# ── BigQuery client singleton (tái sử dụng giữa các warm invocations) ──────────
_bq: bigquery.Client | None = None


def get_bq() -> bigquery.Client:
    global _bq
    if _bq is None:
        _bq = bigquery.Client(project=GCP_PROJECT)
    return _bq


def full_table(dataset: str, table: str) -> str:
    return f"`{GCP_PROJECT}.{dataset}.{table}`"


# ══════════════════════════════════════════════════════════════════════════════
# Preprocessing pipeline – đồng bộ với Data_PreProcessing.ipynb
# ══════════════════════════════════════════════════════════════════════════════

def _remove_urls_emails_html(text: str) -> str:
    """Cell 16: xóa URL, email, HTML tags."""
    text = re.sub(r"http\S+|www\.\S+", " ", text)   # URL
    text = re.sub(r"\S+@\S+\.\S+",    " ", text)    # email
    text = re.sub(r"<.*?>",            " ", text)   # HTML tags
    return text


def _remove_special_chars(text: str) -> str:
    """Cell 17: giữ lại chữ cái Latin, tiếng Việt và khoảng trắng."""
    return re.sub(r"[^a-zA-ZÀ-ỹà-ỹ\s]", " ", text)


def _normalize_whitespace(text: str) -> str:
    """Cell 18: chuẩn hóa khoảng trắng, strip đầu/cuối."""
    return re.sub(r"\s+", " ", text).strip()


def preprocess(title: str, content: str) -> str:
    """
    Pipeline preprocessing đồng bộ với notebook:
      Cell 14  – text = title + ' ' + content
      Cell 15  – lowercase
      Cell 16  – xóa URL/email/HTML
      Cell 17  – xóa ký tự đặc biệt
      Cell 18  – normalize whitespace
      Cell 19  – underthesea word_tokenize
      Cell 21  – unicodedata2 NFC normalize
    """
    # Cell 14: kết hợp title + content (fillna → '')
    text = (title or "") + " " + (content or "")

    # Cell 15: lowercase
    text = text.lower()

    # Cell 16: xóa URL / email / HTML
    text = _remove_urls_emails_html(text)

    # Cell 17: xóa ký tự đặc biệt
    text = _remove_special_chars(text)

    # Cell 18: normalize whitespace
    text = _normalize_whitespace(text)

    # Cell 19: Vietnamese word tokenize
    text_tok = word_tokenize(text, format="text")

    # Cell 21: unicodedata2 NFC normalize
    text_tok = unicodedata2.normalize("NFC", str(text_tok))

    return text_tok


# ── Ensure staging table exists ────────────────────────────────────────────────
def ensure_staging_table() -> None:
    """Tạo bảng hitl_staging_data nếu chưa tồn tại (schema khớp PROCESSED_DATA.csv)."""
    table_id = f"{GCP_PROJECT}.{DST_BQ_DATASET}.{DST_STAGING_TABLE}"
    schema = [
        bigquery.SchemaField("row_id",      "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("article_id",  "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("title",       "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("content",     "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("text_tok",    "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("label",       "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("label_enc",   "INT64",     mode="REQUIRED"),
        bigquery.SchemaField("action",      "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("reviewed_at", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("created_at",  "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("data_source", "STRING",    mode="REQUIRED"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    get_bq().create_table(table, exists_ok=True)
    logger.info("Staging table ready: %s", table_id)


# ── Main Cloud Function ────────────────────────────────────────────────────────
@functions_framework.http
def hitl_preprocess(request):
    """
    HTTP Cloud Function entry point.
    Được gọi từ Backend Flask sau khi đủ HITL_BATCH_THRESHOLD bài đã được duyệt.

    Request body (JSON, tùy chọn):
        trigger            (str) – "hitl_batch"
        unprocessed_count  (int) – số bài backend đếm được (chỉ để log)
    """
    body = (request.get_json(silent=True) or {})
    logger.info("hitl_preprocess triggered – body=%s", body)

    try:
        ensure_staging_table()

        # ── 1. Lấy bài đã review, chưa được xử lý ───────────────────────────
        src_labeled = full_table(SRC_BQ_DATASET, SRC_LABELED_TABLE)
        src_hitl    = full_table(SRC_BQ_DATASET, SRC_HITL_TABLE)

        fetch_sql = f"""
            SELECT
                h.article_id,
                h.action,
                h.reviewed_at,
                COALESCE(h.human_corrected_label, l.label) AS final_label,
                COALESCE(l.title,   '')                    AS title,
                COALESCE(l.content, '')                    AS content
            FROM {src_hitl} h
            JOIN {src_labeled} l ON h.article_id = l.id
            WHERE h.status IN ('{HITL_STATUS_APPROVED}', '{HITL_STATUS_REJECTED}')
              AND (h.is_used_for_retraining IS NULL OR h.is_used_for_retraining = FALSE)
            ORDER BY h.reviewed_at ASC
            LIMIT {MAX_ROWS_PER_RUN}
        """
        rows = list(get_bq().query(fetch_sql).result())
        logger.info("Fetched %d unprocessed reviewed articles.", len(rows))

        if not rows:
            return (
                {"status": "ok", "message": "Không có bài nào cần xử lý.", "processed": 0},
                200,
            )

        # ── 2. Preprocess và chuẩn bị rows để insert ────────────────────────
        now_utc = datetime.now(timezone.utc)
        staged_rows:    list[dict] = []
        processed_ids:  list[str]  = []
        skipped:        int        = 0

        for row in rows:
            # Xác định nhãn cuối cùng
            # – Correct → dùng human_corrected_label
            # – Accept  → giữ nhãn AI
            # – Reject  → label vẫn là nhãn AI (bài bị đánh dấu NOISE nhưng giữ label gốc)
            label = str(row.final_label or "").strip().upper()
            label_enc = LABEL_ENC.get(label)

            if label_enc is None:
                logger.warning(
                    "Bỏ qua article_id=%s – nhãn không xác định: %r", row.article_id, label
                )
                skipped += 1
                continue

            # Preprocessing đồng bộ với notebook
            try:
                text_tok = preprocess(row.title, row.content)
            except Exception as exc:
                logger.warning(
                    "Bỏ qua article_id=%s – lỗi preprocess: %s", row.article_id, exc
                )
                skipped += 1
                continue

            if not text_tok:
                logger.warning(
                    "Bỏ qua article_id=%s – text_tok rỗng sau preprocessing.", row.article_id
                )
                skipped += 1
                continue

            staged_rows.append({
                "row_id":      str(uuid.uuid4()),
                "article_id":  row.article_id,
                "title":       (row.title   or "")[:500],
                "content":     (row.content or "")[:5000],
                "text_tok":    text_tok,
                "label":       label,
                "label_enc":   label_enc,
                "action":      row.action or "",
                "reviewed_at": row.reviewed_at,
                "created_at":  now_utc,
                "data_source": "HITL",
            })
            processed_ids.append(row.article_id)

        if not staged_rows:
            return (
                {
                    "status":  "ok",
                    "message": "Tất cả bài đều bị lọc (nhãn/text không hợp lệ).",
                    "processed": 0,
                    "skipped":   skipped,
                },
                200,
            )

        # ── 3. INSERT vào hitl_staging_data ──────────────────────────────────
        dst_table_id = f"{GCP_PROJECT}.{DST_BQ_DATASET}.{DST_STAGING_TABLE}"
        errors = get_bq().insert_rows_json(dst_table_id, staged_rows)
        if errors:
            logger.error("BigQuery insert errors: %s", errors)
            return ({"status": "error", "message": str(errors)}, 500)

        logger.info("Inserted %d rows into %s", len(staged_rows), dst_table_id)

        # ── 4. Đánh dấu is_used_for_retraining = TRUE ────────────────────────
        ids_literal = ", ".join(f"'{aid}'" for aid in processed_ids)
        update_sql = f"""
            UPDATE {src_hitl}
            SET is_used_for_retraining = TRUE
            WHERE article_id IN ({ids_literal})
        """
        get_bq().query(update_sql).result()
        logger.info(
            "Marked %d articles as is_used_for_retraining=TRUE.", len(processed_ids)
        )

        return (
            {
                "status":    "ok",
                "processed": len(staged_rows),
                "skipped":   skipped,
                "message": (
                    f"Đã preprocess và lưu {len(staged_rows)} bài "
                    f"vào {DST_BQ_DATASET}.{DST_STAGING_TABLE}"
                ),
            },
            200,
        )

    except Exception as exc:
        logger.exception("hitl_preprocess failed: %s", exc)
        return ({"status": "error", "message": str(exc)}, 500)
