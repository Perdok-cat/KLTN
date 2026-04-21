"""
Vertex AI Custom Training Job – train_vertex.py
================================================
Chiến lược: Data Flywheel + Sample Weight
  - Đọc dữ liệu gốc từ mlops_dataset.original_training_data  (weight = 1.0)
  - Đọc dữ liệu HITL từ mlops_dataset.hitl_staging_data       (weight = HITL_WEIGHT)
  - Merge → TF-IDF + LinearSVC Pipeline → đánh giá
  - Nếu accuracy >= MIN_ACCURACY: upload GCS → Vertex AI Model Registry → deploy Endpoint
  - Ghi kết quả vào mlops_dataset.training_metadata

Biến môi trường (bắt buộc):
  GCP_PROJECT          – Google Cloud Project ID
  GCS_BUCKET           – GCS bucket lưu model artifact
  VERTEX_ENDPOINT_ID   – Full resource name của Endpoint hiện tại

Biến môi trường (tuỳ chọn):
  GCP_LOCATION         – Vertex AI region           (default: us-central1)
  GCS_MODEL_PREFIX     – Prefix trong bucket        (default: models/)
  BQ_MLOPS_DATASET     – BQ dataset chứa ML tables  (default: mlops_dataset)
  BQ_ORIGINAL_TABLE    – Bảng dữ liệu gốc           (default: original_training_data)
  BQ_HITL_TABLE        – Bảng staging HITL          (default: hitl_staging_data)
  BQ_METADATA_TABLE    – Bảng ghi metadata training (default: training_metadata)
  MIN_ACCURACY         – Ngưỡng accuracy để deploy  (default: 0.80)
  HITL_WEIGHT          – Sample weight cho HITL data(default: 2.0)
  JOB_ID               – ID của training run        (default: auto-generated UUID)
"""

from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone

import joblib
import pandas as pd
from google.cloud import aiplatform, bigquery, storage
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Environment ───────────────────────────────────────────────────────────────
GCP_PROJECT        = os.environ["GCP_PROJECT"]
GCP_LOCATION       = os.environ.get("GCP_LOCATION",      "us-central1")
GCS_BUCKET         = os.environ["GCS_BUCKET"]
GCS_MODEL_PREFIX   = os.environ.get("GCS_MODEL_PREFIX",  "models/")

BQ_MLOPS_DATASET   = os.environ.get("BQ_MLOPS_DATASET",  "mlops_dataset")
BQ_ORIGINAL_TABLE  = os.environ.get("BQ_ORIGINAL_TABLE", "original_training_data")
BQ_HITL_TABLE      = os.environ.get("BQ_HITL_TABLE",     "hitl_staging_data")
BQ_METADATA_TABLE  = os.environ.get("BQ_METADATA_TABLE", "training_metadata")

VERTEX_ENDPOINT_ID = os.environ["VERTEX_ENDPOINT_ID"]
MIN_ACCURACY       = float(os.environ.get("MIN_ACCURACY", "0.80"))
HITL_WEIGHT        = float(os.environ.get("HITL_WEIGHT",  "2.0"))
JOB_ID             = os.environ.get("JOB_ID", str(uuid.uuid4()))

# Label encoding – phải khớp với CF 04 và notebook
LABEL_ENC: dict[str, int] = {
    "DEEP DIVE":             0,
    "MARKET SIGNALS":        1,
    "NOISE":                 2,
    "SOLUTIONS & USE CASES": 3,
}


# ══════════════════════════════════════════════════════════════════════════════
# 1. Load & merge data
# ══════════════════════════════════════════════════════════════════════════════

def load_data(bq: bigquery.Client) -> pd.DataFrame:
    """
    Load dữ liệu gốc (weight=1.0) + HITL (weight=HITL_WEIGHT) từ BigQuery.
    Trả về DataFrame với cột: text_tok, label_enc, data_source, weight.
    """
    logger.info("── Loading original training data ──────────────────────────")
    orig_sql = f"""
        SELECT text_tok, label_enc, 'original' AS data_source
        FROM `{GCP_PROJECT}.{BQ_MLOPS_DATASET}.{BQ_ORIGINAL_TABLE}`
        WHERE text_tok IS NOT NULL
          AND TRIM(text_tok) != ''
          AND label_enc IS NOT NULL
    """
    orig_df = bq.query(orig_sql).to_dataframe()
    logger.info("Original data: %d rows", len(orig_df))

    logger.info("── Loading HITL staging data ───────────────────────────────")
    hitl_sql = f"""
        SELECT text_tok, label_enc, 'HITL' AS data_source
        FROM `{GCP_PROJECT}.{BQ_MLOPS_DATASET}.{BQ_HITL_TABLE}`
        WHERE text_tok IS NOT NULL
          AND TRIM(text_tok) != ''
          AND label_enc IS NOT NULL
    """
    hitl_df = bq.query(hitl_sql).to_dataframe()
    logger.info("HITL data: %d rows", len(hitl_df))

    df = pd.concat([orig_df, hitl_df], ignore_index=True)
    df["weight"] = df["data_source"].map({"original": 1.0, "HITL": HITL_WEIGHT})

    logger.info(
        "Merged: %d rows total | original=%d | HITL=%d | HITL_weight=%.1f",
        len(df), len(orig_df), len(hitl_df), HITL_WEIGHT,
    )
    logger.info(
        "Label distribution:\n%s",
        df["label_enc"].value_counts().sort_index().to_string(),
    )
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 2. Train & evaluate
# ══════════════════════════════════════════════════════════════════════════════

def train_and_evaluate(df: pd.DataFrame) -> tuple[Pipeline, str, float, str]:
    """
    Train LinearSVC + LogisticRegression với sample weights, trả về best pipeline.

    Lý do dùng sample_weight qua Pipeline:
      - TF-IDF học vocabulary từ toàn bộ corpus (không cần weight ở bước này)
      - Classifier nhận `classifier__sample_weight` để ưu tiên HITL rows
    """
    X = df["text_tok"].fillna("").astype(str)
    y = df["label_enc"].astype(int)
    w = df["weight"].astype(float)

    X_train, X_test, y_train, y_test, w_train, _ = train_test_split(
        X, y, w, test_size=0.2, random_state=42, stratify=y
    )
    logger.info("Train: %d | Test: %d", len(X_train), len(X_test))

    candidates = {
        "LinearSVC": LinearSVC(max_iter=2000, random_state=42),
        "LogisticRegression": LogisticRegression(max_iter=1000, random_state=42, n_jobs=-1),
    }

    best_acc       = 0.0
    best_name      = ""
    best_pipeline  = None
    best_report    = ""

    for name, clf in candidates.items():
        logger.info("[%s] Training...", name)
        t0 = time.time()

        pipe = Pipeline([
            ("tfidf",      TfidfVectorizer(ngram_range=(1, 2), max_features=30_000)),
            ("classifier", clf),
        ])

        # Truyền sample_weight cho bước classifier (không cho tfidf)
        pipe.fit(X_train, y_train, classifier__sample_weight=w_train.values)
        elapsed = time.time() - t0

        preds  = pipe.predict(X_test)
        acc    = accuracy_score(y_test, preds)
        report = classification_report(y_test, preds)

        logger.info("[%s] %.2fs | Accuracy: %.4f", name, elapsed, acc)
        logger.info("[%s] Classification Report:\n%s", name, report)

        if acc > best_acc:
            best_acc      = acc
            best_name     = name
            best_pipeline = pipe
            best_report   = report

    logger.info("Best model: %s | Accuracy: %.4f", best_name, best_acc)
    return best_pipeline, best_name, best_acc, best_report


# ══════════════════════════════════════════════════════════════════════════════
# 3. Upload artifact to GCS
# ══════════════════════════════════════════════════════════════════════════════

def upload_model_to_gcs(pipeline: Pipeline) -> str:
    """
    Lưu model.joblib vào /tmp, upload lên GCS.
    Trả về gs:// URI của thư mục chứa model (dùng làm artifact_uri cho Vertex AI).
    Vertex AI sklearn serving container yêu cầu file tên là `model.joblib`
    nằm ngay trong thư mục artifact_uri.
    """
    version    = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    blob_path  = f"{GCS_MODEL_PREFIX.rstrip('/')}/{version}/model.joblib"
    local_path = "/tmp/model.joblib"

    joblib.dump(pipeline, local_path)
    logger.info("Model saved locally: %s", local_path)

    gcs_client = storage.Client(project=GCP_PROJECT)
    bucket     = gcs_client.bucket(GCS_BUCKET)
    blob       = bucket.blob(blob_path)
    blob.upload_from_filename(local_path)

    artifact_dir = f"gs://{GCS_BUCKET}/{GCS_MODEL_PREFIX.rstrip('/')}/{version}/"
    logger.info("Model artifact uploaded → %s", artifact_dir)
    return artifact_dir


# ══════════════════════════════════════════════════════════════════════════════
# 4. Register model & deploy to endpoint
# ══════════════════════════════════════════════════════════════════════════════

def register_and_deploy(artifact_uri: str) -> tuple[str, str]:
    """
    Upload model lên Vertex AI Model Registry, deploy lên Endpoint hiện có.
    Traffic mới được set 100% về model mới. Model cũ được undeploy tự động.
    Trả về (model_resource_name, endpoint_resource_name).
    """
    aiplatform.init(project=GCP_PROJECT, location=GCP_LOCATION)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    logger.info("Registering model to Vertex AI Model Registry...")
    model = aiplatform.Model.upload(
        display_name=f"ai-news-classifier-{ts}",
        artifact_uri=artifact_uri,
        # Pre-built sklearn serving container – tương thích sklearn >= 1.0
        serving_container_image_uri=(
            "us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-3:latest"
        ),
        # Khai báo input/output schema (tuỳ chọn – dùng cho monitoring)
        serving_container_predict_route="/predict",
        serving_container_health_route="/health",
    )
    logger.info("Model registered: %s", model.resource_name)

    logger.info("Deploying model to endpoint %s...", VERTEX_ENDPOINT_ID)
    endpoint = aiplatform.Endpoint(endpoint_name=VERTEX_ENDPOINT_ID)

    endpoint.deploy(
        model=model,
        deployed_model_display_name=f"ai-news-v{ts}",
        machine_type="n1-standard-2",
        # Chuyển 100% traffic về model mới
        traffic_percentage=100,
        sync=True,
    )
    logger.info("Deployed successfully. Endpoint: %s", endpoint.resource_name)
    return model.resource_name, endpoint.resource_name


# ══════════════════════════════════════════════════════════════════════════════
# 5. Metadata helpers
# ══════════════════════════════════════════════════════════════════════════════

def _ensure_metadata_table(bq: bigquery.Client) -> None:
    """Tạo bảng training_metadata nếu chưa tồn tại."""
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
    bq.create_table(table, exists_ok=True)
    logger.info("Metadata table ready: %s", table_id)


def record_metadata(bq: bigquery.Client, **kwargs) -> None:
    """Upsert một bản ghi vào training_metadata."""
    table_id = f"{GCP_PROJECT}.{BQ_MLOPS_DATASET}.{BQ_METADATA_TABLE}"
    # Chuyển None → null-safe, datetime → ISO string
    row = {
        k: (v.isoformat() if isinstance(v, datetime) else v)
        for k, v in kwargs.items()
    }
    errors = bq.insert_rows_json(table_id, [row])
    if errors:
        logger.warning("Metadata insert errors: %s", errors)
    else:
        logger.info("Metadata recorded | status=%s", kwargs.get("status"))


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    logger.info("=" * 60)
    logger.info("Vertex AI Training Job started | JOB_ID=%s", JOB_ID)
    logger.info("=" * 60)

    started_at = datetime.now(timezone.utc)
    bq = bigquery.Client(project=GCP_PROJECT)

    _ensure_metadata_table(bq)

    # Ghi trạng thái RUNNING ngay khi bắt đầu
    record_metadata(
        bq,
        job_id=JOB_ID,
        status="RUNNING",
        triggered_at=started_at,
        completed_at=None,
        accuracy=None,
        best_model=None,
        rows_original=None,
        rows_hitl=None,
        model_resource_name=None,
        endpoint_resource_name=None,
    )

    try:
        # ── Bước 1: Load data ──────────────────────────────────────────────
        df = load_data(bq)
        rows_original = int((df["data_source"] == "original").sum())
        rows_hitl     = int((df["data_source"] == "HITL").sum())

        if len(df) < 50:
            raise ValueError(
                f"Không đủ dữ liệu training: {len(df)} rows (cần tối thiểu 50)"
            )

        # ── Bước 2: Train ──────────────────────────────────────────────────
        pipeline, best_name, accuracy, report = train_and_evaluate(df)

        # ── Bước 3: Kiểm tra ngưỡng accuracy ──────────────────────────────
        if accuracy < MIN_ACCURACY:
            logger.warning(
                "Accuracy %.4f thấp hơn ngưỡng %.2f → bỏ qua deployment.",
                accuracy, MIN_ACCURACY,
            )
            record_metadata(
                bq,
                job_id=JOB_ID,
                status="SKIPPED_LOW_ACCURACY",
                triggered_at=started_at,
                completed_at=datetime.now(timezone.utc),
                accuracy=accuracy,
                best_model=best_name,
                rows_original=rows_original,
                rows_hitl=rows_hitl,
                model_resource_name=None,
                endpoint_resource_name=None,
            )
            sys.exit(0)

        # ── Bước 4: Upload model lên GCS ───────────────────────────────────
        artifact_uri = upload_model_to_gcs(pipeline)

        # ── Bước 5: Register + Deploy lên Vertex AI ────────────────────────
        model_resource, endpoint_resource = register_and_deploy(artifact_uri)

        # ── Bước 6: Ghi metadata thành công ───────────────────────────────
        record_metadata(
            bq,
            job_id=JOB_ID,
            status="COMPLETED",
            triggered_at=started_at,
            completed_at=datetime.now(timezone.utc),
            accuracy=accuracy,
            best_model=best_name,
            rows_original=rows_original,
            rows_hitl=rows_hitl,
            model_resource_name=model_resource,
            endpoint_resource_name=endpoint_resource,
        )

        logger.info("=" * 60)
        logger.info("Training job COMPLETED")
        logger.info("  Best model  : %s", best_name)
        logger.info("  Accuracy    : %.4f", accuracy)
        logger.info("  Original    : %d rows", rows_original)
        logger.info("  HITL        : %d rows", rows_hitl)
        logger.info("  Model       : %s", model_resource)
        logger.info("=" * 60)

    except Exception as exc:
        logger.exception("Training job FAILED: %s", exc)
        record_metadata(
            bq,
            job_id=JOB_ID,
            status="FAILED",
            triggered_at=started_at,
            completed_at=datetime.now(timezone.utc),
            accuracy=None,
            best_model=None,
            rows_original=None,
            rows_hitl=None,
            model_resource_name=None,
            endpoint_resource_name=None,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
