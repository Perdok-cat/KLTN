"""
Cloud Function: 05_Trigger_Training
-------------------------------------
Nhận HTTP trigger từ CF 04_HITL_Preprocess (hoặc Backend /api/admin/trigger-retrain).
Chạy 3 guard trước khi submit Vertex AI CustomJob:
  Guard 1 – Cooldown: có job nào đã chạy trong COOLDOWN_HOURS giờ qua chưa?
  Guard 2 – Running:  có Vertex AI custom job nào đang chạy không?
  Guard 3 – Data:     hitl_staging_data có đủ MIN_HITL_SAMPLES rows chưa?

Nếu vượt cả 3 guard → submit CustomJob → ghi SUBMITTED vào training_metadata.

Biến môi trường:
  GCP_PROJECT          – Google Cloud Project ID
  GCP_LOCATION         – Vertex AI region              (default: us-central1)
  GCS_BUCKET           – GCS bucket lưu model artifact
  GCS_MODEL_PREFIX     – Prefix trong bucket            (default: models/)
  TRAINING_IMAGE_URI   – Docker image URI trong Artifact Registry
  VERTEX_ENDPOINT_ID   – Full resource name của Endpoint hiện tại
  BQ_MLOPS_DATASET     – BQ dataset chứa ML tables     (default: mlops_dataset)
  BQ_HITL_TABLE        – Bảng staging HITL             (default: hitl_staging_data)
  BQ_METADATA_TABLE    – Bảng ghi metadata training    (default: training_metadata)
  BQ_ORIGINAL_TABLE    – Bảng dữ liệu gốc             (default: original_training_data)
  COOLDOWN_HOURS       – Thời gian chờ giữa 2 training (default: 6)
  MIN_HITL_SAMPLES     – Số HITL rows tối thiểu        (default: 50)
  MIN_ACCURACY         – Ngưỡng accuracy cho training  (default: 0.80)
  HITL_WEIGHT          – Sample weight cho HITL data   (default: 2.0)
  TRAINING_MACHINE     – Machine type cho training job (default: n1-standard-4)
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

import functions_framework
from google.cloud import aiplatform, bigquery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
GCP_PROJECT         = os.environ.get("GCP_PROJECT",         "your-gcp-project-id")
GCP_LOCATION        = os.environ.get("GCP_LOCATION",        "us-central1")
GCS_BUCKET          = os.environ.get("GCS_BUCKET",          "")
GCS_MODEL_PREFIX    = os.environ.get("GCS_MODEL_PREFIX",    "models/")
TRAINING_IMAGE_URI  = os.environ.get("TRAINING_IMAGE_URI",  "")
VERTEX_ENDPOINT_ID  = os.environ.get("VERTEX_ENDPOINT_ID",  "")

BQ_MLOPS_DATASET    = os.environ.get("BQ_MLOPS_DATASET",    "mlops_dataset")
BQ_HITL_TABLE       = os.environ.get("BQ_HITL_TABLE",       "hitl_staging_data")
BQ_METADATA_TABLE   = os.environ.get("BQ_METADATA_TABLE",   "training_metadata")
BQ_ORIGINAL_TABLE   = os.environ.get("BQ_ORIGINAL_TABLE",   "original_training_data")

COOLDOWN_HOURS      = int(os.environ.get("COOLDOWN_HOURS",   "6"))
MIN_HITL_SAMPLES    = int(os.environ.get("MIN_HITL_SAMPLES", "50"))
MIN_ACCURACY        = os.environ.get("MIN_ACCURACY",         "0.80")
HITL_WEIGHT         = os.environ.get("HITL_WEIGHT",          "2.0")
TRAINING_MACHINE    = os.environ.get("TRAINING_MACHINE",     "n1-standard-4")

# Tên hiển thị của training job – dùng để filter khi check running jobs
_JOB_DISPLAY_NAME = "ai-news-classifier-training"

# ── BigQuery client singleton ──────────────────────────────────────────────────
_bq: bigquery.Client | None = None


def get_bq() -> bigquery.Client:
    global _bq
    if _bq is None:
        _bq = bigquery.Client(project=GCP_PROJECT)
    return _bq


# ── Ensure metadata table ──────────────────────────────────────────────────────
_metadata_table_ready = False


def ensure_metadata_table() -> None:
    global _metadata_table_ready
    if _metadata_table_ready:
        return
    table_id = f"{GCP_PROJECT}.{BQ_MLOPS_DATASET}.{BQ_METADATA_TABLE}"
    schema = [
        bigquery.SchemaField("job_id",                  "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("status",                  "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("triggered_at",            "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("completed_at",            "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("accuracy",                "FLOAT64",   mode="NULLABLE"),
        bigquery.SchemaField("best_model",              "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("rows_original",           "INT64",     mode="NULLABLE"),
        bigquery.SchemaField("rows_hitl",               "INT64",     mode="NULLABLE"),
        bigquery.SchemaField("model_resource_name",     "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("endpoint_resource_name",  "STRING",    mode="NULLABLE"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    get_bq().create_table(table, exists_ok=True)
    logger.info("Metadata table ready: %s", table_id)
    _metadata_table_ready = True


# ══════════════════════════════════════════════════════════════════════════════
# Guard functions
# ══════════════════════════════════════════════════════════════════════════════

def _guard_cooldown() -> tuple[bool, str]:
    """
    Guard 1: Kiểm tra xem có training job nào đã chạy trong COOLDOWN_HOURS qua.
    Tránh submit quá nhiều job khi HITL batch đến liên tục.
    """
    try:
        rows = list(get_bq().query(f"""
            SELECT triggered_at
            FROM `{GCP_PROJECT}.{BQ_MLOPS_DATASET}.{BQ_METADATA_TABLE}`
            WHERE status IN ('SUBMITTED', 'RUNNING', 'COMPLETED')
              AND triggered_at >= TIMESTAMP_SUB(
                    CURRENT_TIMESTAMP(),
                    INTERVAL {COOLDOWN_HOURS} HOUR
                  )
            ORDER BY triggered_at DESC
            LIMIT 1
        """).result())

        if rows:
            last = rows[0].triggered_at
            return False, f"Cooldown active – last run at {last} (cooldown={COOLDOWN_HOURS}h)"
        return True, "Cooldown OK"

    except Exception as exc:
        # Nếu bảng chưa tồn tại hoặc lỗi → cho qua, không block
        logger.warning("Cooldown check failed (proceeding): %s", exc)
        return True, "Cooldown check skipped (error)"


def _guard_running_jobs() -> tuple[bool, str]:
    """
    Guard 2: Kiểm tra có Vertex AI CustomJob nào đang ở trạng thái RUNNING.
    Tránh submit song song hai job cùng lúc.
    """
    try:
        aiplatform.init(project=GCP_PROJECT, location=GCP_LOCATION)
        jobs = aiplatform.CustomJob.list(
            filter=f'display_name="{_JOB_DISPLAY_NAME}" AND state="JOB_STATE_RUNNING"',
            project=GCP_PROJECT,
            location=GCP_LOCATION,
        )
        if jobs:
            return False, f"Job đang chạy: {jobs[0].resource_name}"
        return True, "Không có job nào đang chạy"

    except Exception as exc:
        logger.warning("Running jobs check failed (proceeding): %s", exc)
        return True, "Running jobs check skipped (error)"


def _guard_hitl_data() -> tuple[bool, str, int]:
    """
    Guard 3: Kiểm tra hitl_staging_data có đủ MIN_HITL_SAMPLES rows hợp lệ.
    Tránh train model trên quá ít dữ liệu HITL.
    """
    try:
        rows = list(get_bq().query(f"""
            SELECT COUNT(*) AS cnt
            FROM `{GCP_PROJECT}.{BQ_MLOPS_DATASET}.{BQ_HITL_TABLE}`
            WHERE text_tok IS NOT NULL
              AND TRIM(text_tok) != ''
              AND label_enc IS NOT NULL
        """).result())

        count = int(rows[0].cnt) if rows else 0
        if count < MIN_HITL_SAMPLES:
            return (
                False,
                f"HITL data chưa đủ: {count} rows < {MIN_HITL_SAMPLES} rows",
                count,
            )
        return True, f"HITL data đủ: {count} rows", count

    except Exception as exc:
        return False, f"HITL data check failed: {exc}", 0


# ══════════════════════════════════════════════════════════════════════════════
# Submit Vertex AI CustomJob
# ══════════════════════════════════════════════════════════════════════════════

def _submit_training_job(job_id: str) -> str:
    """
    Submit Vertex AI CustomJob với container training.
    Tất cả config được truyền qua biến môi trường vào container.
    Trả về resource_name của job.
    """
    aiplatform.init(project=GCP_PROJECT, location=GCP_LOCATION)

    job = aiplatform.CustomJob(
        display_name=_JOB_DISPLAY_NAME,
        worker_pool_specs=[{
            "machine_spec": {
                "machine_type": TRAINING_MACHINE,
            },
            "replica_count": 1,
            "container_spec": {
                "image_uri": TRAINING_IMAGE_URI,
                "env": [
                    {"name": "GCP_PROJECT",        "value": GCP_PROJECT},
                    {"name": "GCP_LOCATION",        "value": GCP_LOCATION},
                    {"name": "GCS_BUCKET",          "value": GCS_BUCKET},
                    {"name": "GCS_MODEL_PREFIX",    "value": GCS_MODEL_PREFIX},
                    {"name": "BQ_MLOPS_DATASET",    "value": BQ_MLOPS_DATASET},
                    {"name": "BQ_ORIGINAL_TABLE",   "value": BQ_ORIGINAL_TABLE},
                    {"name": "BQ_HITL_TABLE",       "value": BQ_HITL_TABLE},
                    {"name": "BQ_METADATA_TABLE",   "value": BQ_METADATA_TABLE},
                    {"name": "VERTEX_ENDPOINT_ID",  "value": VERTEX_ENDPOINT_ID},
                    {"name": "MIN_ACCURACY",        "value": MIN_ACCURACY},
                    {"name": "HITL_WEIGHT",         "value": HITL_WEIGHT},
                    {"name": "JOB_ID",              "value": job_id},
                ],
            },
        }],
    )

    # submit() là non-blocking – job chạy async trên Vertex AI
    job.submit()
    logger.info("CustomJob submitted: %s", job.resource_name)
    return job.resource_name


def _record_submitted(job_id: str) -> None:
    """Ghi bản ghi SUBMITTED vào training_metadata."""
    table_id = f"{GCP_PROJECT}.{BQ_MLOPS_DATASET}.{BQ_METADATA_TABLE}"
    now_utc  = datetime.now(timezone.utc)
    errors   = get_bq().insert_rows_json(table_id, [{
        "job_id":                job_id,
        "status":                "SUBMITTED",
        "triggered_at":          now_utc.isoformat(),
        "completed_at":          None,
        "accuracy":              None,
        "best_model":            None,
        "rows_original":         None,
        "rows_hitl":             None,
        "model_resource_name":   None,
        "endpoint_resource_name": None,
    }])
    if errors:
        logger.warning("Metadata insert errors: %s", errors)
    else:
        logger.info("Metadata SUBMITTED recorded | job_id=%s", job_id)


# ══════════════════════════════════════════════════════════════════════════════
# Cloud Function entry point
# ══════════════════════════════════════════════════════════════════════════════

@functions_framework.http
def trigger_training(request):
    """
    HTTP entry point.
    Được gọi từ:
      - CF 04_HITL_Preprocess (auto trigger sau mỗi batch)
      - Backend POST /api/admin/trigger-retrain (manual trigger)

    Response JSON:
      { "status": "submitted" | "skipped" | "error", "reason": "...", ... }
    """
    body = (request.get_json(silent=True) or {})
    caller = body.get("caller", "unknown")
    logger.info("trigger_training called | caller=%s", caller)

    # Kiểm tra cấu hình bắt buộc
    if not TRAINING_IMAGE_URI:
        return {"status": "error", "message": "TRAINING_IMAGE_URI chưa được cấu hình"}, 500
    if not GCS_BUCKET:
        return {"status": "error", "message": "GCS_BUCKET chưa được cấu hình"}, 500
    if not VERTEX_ENDPOINT_ID:
        return {"status": "error", "message": "VERTEX_ENDPOINT_ID chưa được cấu hình"}, 500

    ensure_metadata_table()

    # ── Guard 1: Cooldown ──────────────────────────────────────────────────
    ok, reason = _guard_cooldown()
    if not ok:
        logger.info("Skipped (cooldown): %s", reason)
        return {"status": "skipped", "reason": reason}, 200

    # ── Guard 2: Không có job đang chạy ───────────────────────────────────
    ok, reason = _guard_running_jobs()
    if not ok:
        logger.info("Skipped (running job): %s", reason)
        return {"status": "skipped", "reason": reason}, 200

    # ── Guard 3: Đủ HITL data ─────────────────────────────────────────────
    ok, reason, hitl_count = _guard_hitl_data()
    if not ok:
        logger.info("Skipped (insufficient data): %s", reason)
        return {"status": "skipped", "reason": reason, "hitl_count": hitl_count}, 200

    # ── Submit job ─────────────────────────────────────────────────────────
    job_id = str(uuid.uuid4())
    try:
        _record_submitted(job_id)
        resource_name = _submit_training_job(job_id)

        logger.info(
            "Training job submitted | job_id=%s | hitl_count=%d",
            job_id, hitl_count,
        )
        return {
            "status":        "submitted",
            "job_id":        job_id,
            "resource_name": resource_name,
            "hitl_count":    hitl_count,
        }, 200

    except Exception as exc:
        logger.exception("Failed to submit training job: %s", exc)
        return {"status": "error", "message": str(exc)}, 500
