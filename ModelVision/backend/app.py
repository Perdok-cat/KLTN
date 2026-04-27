from __future__ import annotations

import os
import time
from threading import Lock, Thread

import requests as http_requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import aiplatform, bigquery

load_dotenv()

GCP_PROJECT      = os.getenv("GCP_PROJECT",       "your-gcp-project-id")
GCP_LOCATION     = os.getenv("GCP_LOCATION",      "us-central1")

BQ_AI_DATASET    = os.getenv("BQ_AI_DATASET",     "ai_news")
BQ_LABELED       = os.getenv("BQ_LABELED_TABLE",  "labeled_articles")
BQ_HITL          = os.getenv("BQ_HITL_TABLE",     "hitl_reviews")

BQ_MLOPS_DATASET = os.getenv("BQ_MLOPS_DATASET",  "mlops_dataset")
BQ_HITL_STAGING  = os.getenv("BQ_HITL_STAGING",   "hitl_staging_data")
BQ_ORIGINAL      = os.getenv("BQ_ORIGINAL_TABLE", "original_training_data")
BQ_METADATA      = os.getenv("BQ_METADATA_TABLE", "training_metadata")

HITL_PREPROCESS_CF_URL  = os.getenv("HITL_PREPROCESS_CF_URL",  "")
TRIGGER_TRAINING_CF_URL = os.getenv("TRIGGER_TRAINING_CF_URL", "")
HITL_BATCH_THRESHOLD    = int(os.getenv("HITL_BATCH_THRESHOLD", "10"))
VERTEX_ENDPOINT_ID      = os.getenv("VERTEX_ENDPOINT_ID", "")
CACHE_TTL               = int(os.getenv("CACHE_TTL", "300"))

LABEL_MAP = {0: "DEEP DIVE", 1: "MARKET SIGNALS", 2: "NOISE", 3: "SOLUTIONS & USE CASES"}
LABEL_COLORS = {
    "MARKET SIGNALS":        "#E74C3C",
    "SOLUTIONS & USE CASES": "#27AE60",
    "DEEP DIVE":             "#2980B9",
    "NOISE":                 "#95A5A6",
}
LABEL_ICONS = {
    "MARKET SIGNALS":        "📈",
    "SOLUTIONS & USE CASES": "🛠️",
    "DEEP DIVE":             "🔬",
    "NOISE":                 "🔇",
}

HITL_STATUS_PENDING  = "PENDING_REVIEW"
HITL_STATUS_APPROVED = "APPROVED"
HITL_STATUS_REJECTED = "REJECTED_NOISE"
HITL_VALID_ACTIONS   = {"Accept", "Correct", "Reject"}
HITL_VALID_LABELS    = {"DEEP DIVE", "MARKET SIGNALS", "NOISE", "SOLUTIONS & USE CASES"}

app = Flask(__name__)
CORS(app)

# ── BigQuery singleton ─────────────────────────────────────────────────────────
_bq: bigquery.Client | None = None
_bq_lock = Lock()


def get_bq() -> bigquery.Client:
    global _bq
    if _bq is None:
        with _bq_lock:
            if _bq is None:
                _bq = bigquery.Client(project=GCP_PROJECT)
    return _bq


def ai_tbl(name: str) -> str:
    return f"`{GCP_PROJECT}.{BQ_AI_DATASET}.{name}`"


def ml_tbl(name: str) -> str:
    return f"`{GCP_PROJECT}.{BQ_MLOPS_DATASET}.{name}`"


def run_query(sql: str) -> list:
    return list(get_bq().query(sql).result())


def run_dml(sql: str) -> int:
    job = get_bq().query(sql)
    job.result()
    return job.num_dml_affected_rows or 0


def _escape(v: str) -> str:
    return str(v or "").replace("'", "\\'")


# ── Simple TTL cache ───────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, object]] = {}


def cache_get(key: str):
    e = _cache.get(key)
    if e and (time.monotonic() - e[0]) < CACHE_TTL:
        return e[1]
    return None


def cache_set(key: str, val: object) -> None:
    _cache[key] = (time.monotonic(), val)


# ── HITL table bootstrap ───────────────────────────────────────────────────────
_hitl_table_ready = False
_hitl_table_lock  = Lock()


def ensure_hitl_table() -> None:
    global _hitl_table_ready
    if _hitl_table_ready:
        return
    with _hitl_table_lock:
        if _hitl_table_ready:
            return
        full_id = f"{GCP_PROJECT}.{BQ_AI_DATASET}.{BQ_HITL}"
        schema = [
            bigquery.SchemaField("article_id",             "STRING",    mode="REQUIRED"),
            bigquery.SchemaField("status",                 "STRING",    mode="REQUIRED"),
            bigquery.SchemaField("action",                 "STRING",    mode="NULLABLE"),
            bigquery.SchemaField("human_corrected_label",  "STRING",    mode="NULLABLE"),
            bigquery.SchemaField("reviewed_at",            "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("is_used_for_retraining", "BOOL",      mode="NULLABLE"),
        ]
        get_bq().create_table(bigquery.Table(full_id, schema=schema), exists_ok=True)
        _hitl_table_ready = True


# ── HITL batch counter (in-memory) ────────────────────────────────────────────
_unprocessed_count: int | None = None
_unprocessed_lock  = Lock()


def _get_unprocessed_count() -> int:
    global _unprocessed_count
    if _unprocessed_count is None:
        with _unprocessed_lock:
            if _unprocessed_count is None:
                rows = run_query(f"""
                    SELECT COUNT(*) AS cnt FROM {ai_tbl(BQ_HITL)}
                    WHERE status IN ('{HITL_STATUS_APPROVED}', '{HITL_STATUS_REJECTED}')
                      AND (is_used_for_retraining IS NULL OR is_used_for_retraining = FALSE)
                """)
                _unprocessed_count = int(rows[0].cnt) if rows else 0
    return _unprocessed_count


def _increment_unprocessed() -> int:
    global _unprocessed_count
    if _unprocessed_count is None:
        _get_unprocessed_count()
    with _unprocessed_lock:
        _unprocessed_count += 1
        return _unprocessed_count


def _reset_unprocessed() -> None:
    global _unprocessed_count
    with _unprocessed_lock:
        _unprocessed_count = 0


def _trigger_hitl_preprocess(count: int) -> None:
    if not HITL_PREPROCESS_CF_URL:
        return
    try:
        headers = {"Content-Type": "application/json"}
        try:
            tok = http_requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity",
                params={"audience": HITL_PREPROCESS_CF_URL},
                headers={"Metadata-Flavor": "Google"},
                timeout=5,
            )
            if tok.ok:
                headers["Authorization"] = f"Bearer {tok.text}"
        except Exception:
            pass
        resp = http_requests.post(
            HITL_PREPROCESS_CF_URL,
            json={"trigger": "hitl_batch", "unprocessed_count": count},
            headers=headers,
            timeout=30,
        )
        if resp.ok:
            _reset_unprocessed()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "modelvision-backend"})


# ══════════════════════════════════════════════════════════════════════════════
# HITL
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/hitl/stats")
def hitl_stats():
    ensure_hitl_table()
    cached = cache_get("hitl_stats")
    if cached:
        return jsonify(cached)
    try:
        rows = run_query(f"""
            SELECT
                COUNTIF(h.article_id IS NULL OR h.status = '{HITL_STATUS_PENDING}') AS pending_count,
                COUNTIF(DATE(h.reviewed_at, 'UTC') = CURRENT_DATE('UTC'))           AS reviewed_today,
                COUNTIF(h.status = '{HITL_STATUS_APPROVED}')                        AS approved_total,
                COUNTIF(h.status = '{HITL_STATUS_REJECTED}')                        AS rejected_total,
                COUNT(DISTINCT l.id)                                                AS total_articles
            FROM {ai_tbl(BQ_LABELED)} l
            LEFT JOIN {ai_tbl(BQ_HITL)} h ON l.id = h.article_id
        """)
    except GoogleAPICallError as exc:
        return jsonify({"error": str(exc)}), 503
    r = rows[0]
    result = {
        "pending_count":  r.pending_count,
        "reviewed_today": r.reviewed_today,
        "approved_total": r.approved_total,
        "rejected_total": r.rejected_total,
        "total_articles": r.total_articles,
    }
    cache_set("hitl_stats", result)
    return jsonify(result)


@app.get("/api/hitl/pending")
def hitl_pending():
    ensure_hitl_table()
    page   = request.args.get("page",  1,  type=int)
    limit  = min(request.args.get("limit", 20, type=int), 100)
    offset = (page - 1) * limit

    base = f"""
        FROM {ai_tbl(BQ_LABELED)} l
        LEFT JOIN {ai_tbl(BQ_HITL)} h ON l.id = h.article_id
        WHERE h.article_id IS NULL OR h.status = '{HITL_STATUS_PENDING}'
    """
    try:
        total = run_query(f"SELECT COUNT(*) AS total {base}")[0].total
        rows  = run_query(f"""
            SELECT
                l.id,
                l.title,
                l.link                                                              AS source_url,
                l.source,
                l.pub_date,
                SUBSTR(REGEXP_REPLACE(COALESCE(l.content, ''), r'<[^>]+>', ''), 1, 300) AS content_snippet,
                l.label                                                             AS ai_predicted_label,
                l.confidence                                                        AS ai_confidence_score,
                CAST(l.labeled_at AS STRING)                                        AS created_at,
                COALESCE(h.status, '{HITL_STATUS_PENDING}')                         AS status,
                h.human_corrected_label,
                CAST(h.reviewed_at AS STRING)                                       AS reviewed_at
            {base}
            ORDER BY
                CASE WHEN l.label = 'NOISE' THEN 0 ELSE 1 END ASC,
                CASE LOWER(l.confidence)
                    WHEN 'low'    THEN 0
                    WHEN 'medium' THEN 1
                    WHEN 'high'   THEN 2
                    ELSE 1
                END ASC
            LIMIT  {limit}
            OFFSET {offset}
        """)
    except GoogleAPICallError as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify({
        "total":    total,
        "page":     page,
        "limit":    limit,
        "articles": [
            {
                "id":                    r.id,
                "title":                 r.title               or "",
                "source_url":            r.source_url          or "",
                "source":                r.source              or "",
                "pub_date":              r.pub_date            or "",
                "content_snippet":       (r.content_snippet or "") + "…",
                "ai_predicted_label":    r.ai_predicted_label  or "",
                "ai_confidence_score":   r.ai_confidence_score or "",
                "created_at":            r.created_at          or "",
                "status":                r.status,
                "human_corrected_label": r.human_corrected_label or None,
                "reviewed_at":           r.reviewed_at         or None,
            }
            for r in rows
        ],
    })


@app.post("/api/hitl/review/<article_id>")
def hitl_review(article_id: str):
    ensure_hitl_table()
    body            = request.get_json(silent=True) or {}
    action          = (body.get("action") or "").strip()
    corrected_label = (body.get("corrected_label") or "").strip() or None

    if action not in HITL_VALID_ACTIONS:
        return jsonify({"error": f"action phải là một trong: {sorted(HITL_VALID_ACTIONS)}"}), 400
    if action == "Correct":
        if not corrected_label:
            return jsonify({"error": "corrected_label là bắt buộc khi action = 'Correct'"}), 400
        if corrected_label not in HITL_VALID_LABELS:
            return jsonify({"error": f"corrected_label không hợp lệ"}), 400

    status    = HITL_STATUS_REJECTED if action == "Reject" else HITL_STATUS_APPROVED
    label_sql = f"'{_escape(corrected_label)}'" if corrected_label else "NULL"

    try:
        run_dml(f"""
            MERGE {ai_tbl(BQ_HITL)} AS target
            USING (SELECT '{_escape(article_id)}' AS article_id) AS source
            ON target.article_id = source.article_id
            WHEN MATCHED THEN
                UPDATE SET
                    status                 = '{status}',
                    action                 = '{action}',
                    human_corrected_label  = {label_sql},
                    reviewed_at            = CURRENT_TIMESTAMP(),
                    is_used_for_retraining = FALSE
            WHEN NOT MATCHED THEN
                INSERT (article_id, status, action, human_corrected_label, reviewed_at, is_used_for_retraining)
                VALUES ('{_escape(article_id)}', '{status}', '{action}', {label_sql}, CURRENT_TIMESTAMP(), FALSE)
        """)
    except GoogleAPICallError as exc:
        return jsonify({"error": str(exc)}), 503

    count = None
    try:
        count = _increment_unprocessed()
        if count >= HITL_BATCH_THRESHOLD:
            Thread(target=_trigger_hitl_preprocess, args=(count,), daemon=True).start()
    except Exception:
        pass

    return jsonify({
        "article_id":              article_id,
        "action":                  action,
        "status":                  status,
        "human_corrected_label":   corrected_label,
        "unprocessed_batch_count": count,
    })


# ══════════════════════════════════════════════════════════════════════════════
# Training
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/training/history")
def training_history():
    limit = min(int(request.args.get("limit", 20)), 100)
    try:
        rows = run_query(f"""
            SELECT
                job_id,
                status,
                triggered_at,
                completed_at,
                ROUND(accuracy, 4)  AS accuracy,
                best_model,
                rows_original,
                rows_hitl,
                model_resource_name,
                endpoint_resource_name
            FROM {ml_tbl(BQ_METADATA)}
            ORDER BY triggered_at DESC
            LIMIT {limit}
        """)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify({
        "history": [
            {
                "job_id":                r.job_id,
                "status":                r.status,
                "triggered_at":          r.triggered_at.isoformat() if r.triggered_at else None,
                "completed_at":          r.completed_at.isoformat()  if r.completed_at  else None,
                "accuracy":              float(r.accuracy)            if r.accuracy is not None else None,
                "best_model":            r.best_model,
                "rows_original":         r.rows_original,
                "rows_hitl":             r.rows_hitl,
                "model_resource_name":   r.model_resource_name,
                "endpoint_resource_name":r.endpoint_resource_name,
            }
            for r in rows
        ]
    })


@app.post("/api/training/trigger")
def training_trigger():
    if not TRIGGER_TRAINING_CF_URL:
        return jsonify({"status": "error", "message": "TRIGGER_TRAINING_CF_URL chưa cấu hình"}), 503
    body  = request.get_json(silent=True) or {}
    force = bool(body.get("force", False))
    try:
        headers = {"Content-Type": "application/json"}
        try:
            tok = http_requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity",
                params={"audience": TRIGGER_TRAINING_CF_URL},
                headers={"Metadata-Flavor": "Google"},
                timeout=5,
            )
            if tok.ok:
                headers["Authorization"] = f"Bearer {tok.text}"
        except Exception:
            pass
        resp = http_requests.post(
            TRIGGER_TRAINING_CF_URL,
            json={"caller": "modelvision", "force": force},
            headers=headers,
            timeout=30,
        )
        data = resp.json() if resp.content else {}
        return jsonify({"status": data.get("status", "unknown"), "cf_response": data}), 200
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503


# ══════════════════════════════════════════════════════════════════════════════
# Data Drift
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/drift/summary")
def drift_summary():
    cached = cache_get("drift_summary")
    if cached:
        return jsonify(cached)
    try:
        orig_rows = run_query(f"""
            SELECT label_enc, COUNT(*) AS cnt
            FROM {ml_tbl(BQ_ORIGINAL)}
            GROUP BY label_enc
        """)
        hitl_rows = run_query(f"""
            SELECT label_enc, COUNT(*) AS cnt
            FROM {ml_tbl(BQ_HITL_STAGING)}
            GROUP BY label_enc
        """)
        # Recent inference label distribution (last 7 days)
        recent_rows = run_query(f"""
            SELECT label, COUNT(*) AS cnt
            FROM {ai_tbl(BQ_LABELED)}
            WHERE labeled_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
            GROUP BY label
        """)
        # Total HITL staging rows count
        total_hitl_row = run_query(f"""
            SELECT COUNT(*) AS cnt FROM {ml_tbl(BQ_HITL_STAGING)}
        """)
        total_orig_row = run_query(f"""
            SELECT COUNT(*) AS cnt FROM {ml_tbl(BQ_ORIGINAL)}
        """)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503

    def to_label_dict(rows, use_enc: bool) -> dict:
        result = {}
        for r in rows:
            label = LABEL_MAP.get(int(r.label_enc), str(r.label_enc)) if use_enc else r.label
            result[label] = int(r.cnt)
        return result

    orig_dist   = to_label_dict(orig_rows,   use_enc=True)
    hitl_dist   = to_label_dict(hitl_rows,   use_enc=True)
    recent_dist = to_label_dict(recent_rows, use_enc=False)

    all_labels = sorted(set(list(orig_dist) + list(hitl_dist)))

    # Percentage shift per label
    drift = {}
    for lbl in all_labels:
        orig_pct  = orig_dist.get(lbl, 0)  / max(sum(orig_dist.values()),  1)
        hitl_pct  = hitl_dist.get(lbl, 0)  / max(sum(hitl_dist.values()),  1)
        drift[lbl] = round((hitl_pct - orig_pct) * 100, 2)

    result = {
        "original_distribution": orig_dist,
        "hitl_distribution":     hitl_dist,
        "recent_7d_distribution":recent_dist,
        "drift_pct":             drift,
        "total_original":        int(total_orig_row[0].cnt) if total_orig_row else 0,
        "total_hitl":            int(total_hitl_row[0].cnt) if total_hitl_row else 0,
    }
    cache_set("drift_summary", result)
    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════════════
# Model Management
# ══════════════════════════════════════════════════════════════════════════════

def _get_endpoint():
    if not VERTEX_ENDPOINT_ID:
        raise RuntimeError("VERTEX_ENDPOINT_ID chưa cấu hình")
    aiplatform.init(project=GCP_PROJECT, location=GCP_LOCATION)
    return aiplatform.Endpoint(VERTEX_ENDPOINT_ID)


@app.get("/api/model/traffic")
def model_traffic():
    try:
        endpoint = _get_endpoint()
        ep_res   = endpoint.gca_resource
        deployed = [
            {
                "id":           dm.id,
                "display_name": dm.display_name,
                "model":        dm.model,
                "traffic_pct":  ep_res.traffic_split.get(dm.id, 0),
            }
            for dm in ep_res.deployed_models
        ]
        return jsonify({
            "endpoint_id":     VERTEX_ENDPOINT_ID,
            "traffic_split":   dict(ep_res.traffic_split),
            "deployed_models": deployed,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@app.post("/api/model/traffic")
def model_traffic_update():
    """
    Body: {"traffic_split": {"<deployed_model_id>": <int_pct>, ...}}
    Values must sum to 100.
    """
    body  = request.get_json(silent=True) or {}
    split = body.get("traffic_split", {})
    if not split or sum(split.values()) != 100:
        return jsonify({"error": "traffic_split phải tổng = 100"}), 400
    try:
        endpoint = _get_endpoint()
        endpoint.update_traffic_split(traffic_split={k: int(v) for k, v in split.items()})
        return jsonify({"status": "updated", "traffic_split": split})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@app.get("/api/model/list")
def model_list():
    """Trả về danh sách model versions trong Vertex Model Registry có prefix ai-news-classifier."""
    try:
        aiplatform.init(project=GCP_PROJECT, location=GCP_LOCATION)
        models = aiplatform.Model.list(
            filter='display_name:"ai-news-classifier"',
            order_by="create_time desc",
        )
        return jsonify({
            "models": [
                {
                    "resource_name":  m.resource_name,
                    "display_name":   m.display_name,
                    "create_time":    m.create_time.isoformat() if m.create_time else None,
                    "version_id":     getattr(m, "version_id", None),
                }
                for m in models[:20]
            ]
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
