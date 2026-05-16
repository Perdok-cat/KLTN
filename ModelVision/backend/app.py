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
BQ_LLM_USAGE     = os.getenv("BQ_LLM_USAGE_TABLE", "llm_usage_log")

HITL_PREPROCESS_CF_URL  = os.getenv("HITL_PREPROCESS_CF_URL",  "")
TRIGGER_TRAINING_CF_URL = os.getenv("TRIGGER_TRAINING_CF_URL", "")
HITL_BATCH_THRESHOLD    = int(os.getenv("HITL_BATCH_THRESHOLD", "10"))
VERTEX_ENDPOINT_ID      = os.getenv("VERTEX_ENDPOINT_ID", "").strip()
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


def _normalized_endpoint_id(value: str | None) -> str:
    raw = str(value or "").strip()
    if raw.lower() in {"", "none", "null"}:
        return ""
    return raw


def _parse_range(value: str) -> tuple[str, str, str]:
    raw = str(value or "24h").strip().lower()
    if raw == "30d":
        return raw, "TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)", "DAY"
    if raw == "7d":
        return raw, "TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)", "DAY"
    return "24h", "TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)", "HOUR"


def _empty_llm_payload(range_key: str, runtime: str) -> dict:
    return {
        "runtime": runtime,
        "range": range_key,
        "provider": "",
        "model_name": "",
        "prompt_version": "",
        "config_snapshot": {},
        "kpis": {
            "total_requests": 0,
            "success_count": 0,
            "error_count": 0,
            "success_rate": 0.0,
            "error_rate": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "avg_latency_ms": 0.0,
            "total_cost_usd": 0.0,
        },
        "timeseries": [],
        "error_breakdown": [],
        "recent_logs": [],
    }


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


@app.get("/api/llm/overview")
def llm_overview():
    runtime = request.args.get("runtime", "summarize_articles").strip() or "summarize_articles"
    range_key, start_expr, bucket_unit = _parse_range(request.args.get("range", "24h"))
    bucket_expr = f"TIMESTAMP_TRUNC(started_at, {bucket_unit})"

    try:
        summary_rows = run_query(f"""
            SELECT
                COUNT(*) AS total_requests,
                COUNTIF(success) AS success_count,
                COUNTIF(NOT success) AS error_count,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                COALESCE(SUM(cost_estimate_usd), 0) AS total_cost_usd
            FROM {ml_tbl(BQ_LLM_USAGE)}
            WHERE runtime_name = '{_escape(runtime)}'
              AND started_at >= {start_expr}
        """)
        latest_rows = run_query(f"""
            SELECT
                provider,
                model_name,
                prompt_version,
                use_vertex,
                vertex_location,
                max_retries,
                max_content_chars,
                gemini_delay,
                input_token_price_usd_per_1k,
                output_token_price_usd_per_1k
            FROM {ml_tbl(BQ_LLM_USAGE)}
            WHERE runtime_name = '{_escape(runtime)}'
            ORDER BY started_at DESC
            LIMIT 1
        """)
        timeseries_rows = run_query(f"""
            SELECT
                CAST({bucket_expr} AS STRING) AS bucket,
                COUNT(*) AS requests,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(cost_estimate_usd), 0) AS total_cost_usd,
                COUNTIF(NOT success) AS error_count
            FROM {ml_tbl(BQ_LLM_USAGE)}
            WHERE runtime_name = '{_escape(runtime)}'
              AND started_at >= {start_expr}
            GROUP BY bucket
            ORDER BY bucket
        """)
        error_rows = run_query(f"""
            SELECT
                COALESCE(NULLIF(error_type, ''), 'unknown') AS error_type,
                COUNT(*) AS count
            FROM {ml_tbl(BQ_LLM_USAGE)}
            WHERE runtime_name = '{_escape(runtime)}'
              AND started_at >= {start_expr}
              AND success = FALSE
            GROUP BY error_type
            ORDER BY count DESC, error_type
        """)
        recent_rows = run_query(f"""
            SELECT
                CAST(started_at AS STRING) AS started_at,
                provider,
                model_name,
                total_tokens,
                latency_ms,
                success,
                COALESCE(NULLIF(error_type, ''), '—') AS error_type,
                token_source,
                cost_estimate_usd
            FROM {ml_tbl(BQ_LLM_USAGE)}
            WHERE runtime_name = '{_escape(runtime)}'
            ORDER BY started_at DESC
            LIMIT 12
        """)
    except Exception as exc:
        msg = str(exc)
        if "Not found" in msg or "404" in msg:
            return jsonify(_empty_llm_payload(range_key, runtime))
        return jsonify({"error": msg}), 503

    payload = _empty_llm_payload(range_key, runtime)
    summary = summary_rows[0] if summary_rows else None
    latest = latest_rows[0] if latest_rows else None

    total_requests = int(summary.total_requests or 0) if summary else 0
    success_count = int(summary.success_count or 0) if summary else 0
    error_count = int(summary.error_count or 0) if summary else 0

    payload["provider"] = latest.provider if latest else ""
    payload["model_name"] = latest.model_name if latest else ""
    payload["prompt_version"] = latest.prompt_version if latest else ""
    payload["config_snapshot"] = {
        "use_vertex": bool(latest.use_vertex) if latest else False,
        "vertex_location": latest.vertex_location if latest else "",
        "max_retries": int(latest.max_retries or 0) if latest else 0,
        "max_content_chars": int(latest.max_content_chars or 0) if latest else 0,
        "gemini_delay": float(latest.gemini_delay or 0) if latest else 0.0,
        "input_token_price_usd_per_1k": float(latest.input_token_price_usd_per_1k or 0) if latest else 0.0,
        "output_token_price_usd_per_1k": float(latest.output_token_price_usd_per_1k or 0) if latest else 0.0,
    }
    payload["kpis"] = {
        "total_requests": total_requests,
        "success_count": success_count,
        "error_count": error_count,
        "success_rate": round((success_count / total_requests * 100) if total_requests else 0.0, 2),
        "error_rate": round((error_count / total_requests * 100) if total_requests else 0.0, 2),
        "input_tokens": int(summary.input_tokens or 0) if summary else 0,
        "output_tokens": int(summary.output_tokens or 0) if summary else 0,
        "total_tokens": int(summary.total_tokens or 0) if summary else 0,
        "avg_latency_ms": round(float(summary.avg_latency_ms or 0), 1) if summary else 0.0,
        "total_cost_usd": round(float(summary.total_cost_usd or 0), 6) if summary else 0.0,
    }
    payload["timeseries"] = [
        {
            "bucket": r.bucket,
            "requests": int(r.requests or 0),
            "total_tokens": int(r.total_tokens or 0),
            "total_cost_usd": float(r.total_cost_usd or 0),
            "error_count": int(r.error_count or 0),
        }
        for r in timeseries_rows
    ]
    payload["error_breakdown"] = [
        {"error_type": r.error_type, "count": int(r.count or 0)}
        for r in error_rows
    ]
    payload["recent_logs"] = [
        {
            "started_at": r.started_at,
            "provider": r.provider,
            "model_name": r.model_name,
            "total_tokens": int(r.total_tokens or 0),
            "latency_ms": int(r.latency_ms or 0),
            "success": bool(r.success),
            "error_type": r.error_type,
            "token_source": r.token_source,
            "cost_estimate_usd": float(r.cost_estimate_usd or 0),
        }
        for r in recent_rows
    ]
    return jsonify(payload)


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
    endpoint_id = _normalized_endpoint_id(VERTEX_ENDPOINT_ID)
    if not endpoint_id:
        raise RuntimeError("VERTEX_ENDPOINT_ID chưa cấu hình")
    aiplatform.init(project=GCP_PROJECT, location=GCP_LOCATION)
    return aiplatform.Endpoint(endpoint_id)


def _model_resource_key(resource_name: str | None) -> str:
    return (resource_name or "").split("@", 1)[0].strip()


def _list_registry_models(prefix: str = "ai-news-classifier", limit: int = 20) -> list[dict]:
    aiplatform.init(project=GCP_PROJECT, location=GCP_LOCATION)
    models = aiplatform.Model.list(order_by="create_time desc")
    matched = []
    for m in models:
        display_name = getattr(m, "display_name", "") or ""
        if display_name == prefix or display_name.startswith(f"{prefix}-"):
            matched.append(
                {
                    "resource_name": m.resource_name,
                    "display_name": display_name,
                    "create_time": m.create_time.isoformat() if m.create_time else None,
                    "version_id": getattr(m, "version_id", None),
                }
            )
        if len(matched) >= limit:
            break
    return matched


def _serialize_deployed_model(dm, traffic_split: dict) -> dict:
    traffic_pct = int(traffic_split.get(dm.id, 0))
    return {
        "id": dm.id,
        "display_name": dm.display_name,
        "model_resource_name": dm.model,
        "traffic_pct": traffic_pct,
        "serving_status": "ACTIVE" if traffic_pct > 0 else "STANDBY",
    }


def _list_active_endpoints(limit: int = 10) -> list[dict]:
    aiplatform.init(project=GCP_PROJECT, location=GCP_LOCATION)
    endpoints = aiplatform.Endpoint.list(order_by="create_time desc")
    results: list[dict] = []
    for ep in endpoints:
        endpoint_ref = aiplatform.Endpoint(getattr(ep, "resource_name", None) or getattr(ep, "name", None))
        ep_res = endpoint_ref.gca_resource
        traffic_split = dict(getattr(ep_res, "traffic_split", {}) or {})
        deployed_models = [
            _serialize_deployed_model(dm, traffic_split)
            for dm in getattr(ep_res, "deployed_models", []) or []
        ]
        if not deployed_models:
            continue
        results.append(
            {
                "id": getattr(ep_res, "name", "").split("/")[-1] or getattr(ep, "name", ""),
                "resource_name": getattr(ep_res, "name", "") or getattr(ep, "resource_name", ""),
                "display_name": getattr(ep_res, "display_name", "") or getattr(ep, "display_name", "") or "Vertex Endpoint",
                "create_time": ep.create_time.isoformat() if getattr(ep, "create_time", None) else None,
                "traffic_split": traffic_split,
                "deployed_models": deployed_models,
                "deployed_model_count": len(deployed_models),
                "total_traffic_pct": sum(item["traffic_pct"] for item in deployed_models),
                "status": "ACTIVE" if any(item["traffic_pct"] > 0 for item in deployed_models) else "IDLE",
            }
        )
        if len(results) >= limit:
            break
    return results


def _serialize_training_row(r) -> dict:
    return {
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
        return jsonify({"models": _list_registry_models(limit=20)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@app.get("/api/model/overview")
def model_overview():
    """Tổng hợp active endpoints, deployed models, registry và training metadata cho dashboard."""
    try:
        endpoints = _list_active_endpoints(limit=10)
        registry = _list_registry_models(limit=20)
        configured_endpoint_error = None
        configured_endpoint_res = None
        try:
            configured_endpoint = _get_endpoint()
            configured_endpoint_res = configured_endpoint.gca_resource
        except Exception as exc:
            configured_endpoint_error = str(exc)

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
            LIMIT 50
        """)
        training_history = [_serialize_training_row(r) for r in rows]
        training_by_model = {}
        for item in training_history:
            key = _model_resource_key(item.get("model_resource_name"))
            if key and key not in training_by_model:
                training_by_model[key] = item

        deployed = []
        for endpoint_item in endpoints:
            for dm in endpoint_item.get("deployed_models", []):
                training = training_by_model.get(_model_resource_key(dm.get("model_resource_name")))
                dm["latest_training"] = training
                deployed.append(dm)

        deployed_by_model = {}
        for dm in deployed:
            deployed_by_model[_model_resource_key(dm.get("model_resource_name"))] = dm

        enriched_registry = []
        for m in registry:
            key = _model_resource_key(m.get("resource_name"))
            deployed_match = deployed_by_model.get(key)
            latest_training = training_by_model.get(key)
            enriched_registry.append({
                **m,
                "is_deployed":     deployed_match is not None,
                "deployed_id":     deployed_match.get("id") if deployed_match else None,
                "traffic_pct":     deployed_match.get("traffic_pct", 0) if deployed_match else 0,
                "serving_status":  deployed_match.get("serving_status") if deployed_match else "NOT_DEPLOYED",
                "latest_training": latest_training,
            })

        return jsonify({
            "endpoint": {
                "id":       (
                    getattr(configured_endpoint_res, "name", "").split("/")[-1]
                    if configured_endpoint_res else _normalized_endpoint_id(VERTEX_ENDPOINT_ID) or None
                ),
                "project":  GCP_PROJECT,
                "location": GCP_LOCATION,
                "status":   "CONNECTED" if configured_endpoint_res else "UNCONFIGURED",
            },
            "active_endpoint_count": len(endpoints),
            "endpoints": endpoints,
            "traffic_split":   dict(getattr(configured_endpoint_res, "traffic_split", {}) or {}),
            "deployed_models": deployed,
            "registry_models": enriched_registry,
            "latest_training": training_history[0] if training_history else None,
            "configured_endpoint_error": configured_endpoint_error,
        })
    except Exception as exc:
        return jsonify({
            "endpoint": {
                "id":       _normalized_endpoint_id(VERTEX_ENDPOINT_ID) or None,
                "project":  GCP_PROJECT,
                "location": GCP_LOCATION,
                "status":   "ERROR",
            },
            "error": str(exc),
        }), 503


if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
