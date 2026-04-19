"""
Flask Backend – AI News Pipeline API
Nguồn dữ liệu: Google BigQuery (bảng labeled_articles + summarized_articles).
Dự đoán nhãn: gọi Vertex AI Endpoint.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from threading import Lock, Thread

import requests as http_requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import bigquery
from google.cloud import aiplatform

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────
GCP_PROJECT      = os.getenv("GCP_PROJECT",      "your-gcp-project-id")
GCP_LOCATION     = os.getenv("GCP_LOCATION",     "us-central1")
BQ_DATASET       = os.getenv("BQ_DATASET",       "ai_news")
BQ_LABELED       = os.getenv("BQ_LABELED_TABLE", "labeled_articles")
BQ_SUMMARY       = os.getenv("BQ_SUMMARY_TABLE", "summarized_articles")
BQ_HITL          = os.getenv("BQ_HITL_TABLE",    "hitl_reviews")

# HITL Preprocessing Cloud Function
HITL_PREPROCESS_CF_URL  = os.getenv("HITL_PREPROCESS_CF_URL", "")
HITL_BATCH_THRESHOLD    = int(os.getenv("HITL_BATCH_THRESHOLD", "10"))

# Vertex AI Endpoint ID (chỉ phần số, không phải full resource name)
VERTEX_ENDPOINT_ID = os.getenv("VERTEX_ENDPOINT_ID", "")

# Thời gian cache tĩnh (giây) – tránh query BQ liên tục cho stats/labels
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

# ── Label metadata ─────────────────────────────────────────────────────────────
LABEL_MAP = {
    0: "DEEP DIVE",
    1: "MARKET SIGNALS",
    2: "NOISE",
    3: "SOLUTIONS & USE CASES",
}
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

# ── HITL constants ─────────────────────────────────────────────────────────────
HITL_STATUS_PENDING  = "PENDING_REVIEW"
HITL_STATUS_APPROVED = "APPROVED"
HITL_STATUS_REJECTED = "REJECTED_NOISE"

HITL_ACTION_ACCEPT  = "Accept"
HITL_ACTION_CORRECT = "Correct"
HITL_ACTION_REJECT  = "Reject"
HITL_VALID_ACTIONS  = {HITL_ACTION_ACCEPT, HITL_ACTION_CORRECT, HITL_ACTION_REJECT}
HITL_VALID_LABELS   = {"DEEP DIVE", "MARKET SIGNALS", "NOISE", "SOLUTIONS & USE CASES"}

# ── Flask app ──────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# ── Vertex AI Endpoint (lazy singleton) ───────────────────────────────────────
_vertex_endpoint: aiplatform.Endpoint | None = None
_vertex_lock = Lock()


def get_vertex_endpoint() -> aiplatform.Endpoint:
    global _vertex_endpoint
    if _vertex_endpoint is None:
        with _vertex_lock:
            if _vertex_endpoint is None:
                if not VERTEX_ENDPOINT_ID:
                    raise RuntimeError("VERTEX_ENDPOINT_ID chưa được cấu hình.")
                aiplatform.init(project=GCP_PROJECT, location=GCP_LOCATION)
                _vertex_endpoint = aiplatform.Endpoint(VERTEX_ENDPOINT_ID)
                print(f"[INFO] Vertex AI Endpoint connected: {VERTEX_ENDPOINT_ID}")
    return _vertex_endpoint


# ── BigQuery client (lazy singleton) ──────────────────────────────────────────
_bq: bigquery.Client | None = None
_bq_lock = Lock()


def get_bq() -> bigquery.Client:
    global _bq
    if _bq is None:
        with _bq_lock:
            if _bq is None:
                _bq = bigquery.Client(project=GCP_PROJECT)
                print(f"[INFO] BigQuery client initialised (project={GCP_PROJECT})")
    return _bq


def tbl(name: str) -> str:
    """Trả về tên bảng BigQuery đầy đủ."""
    return f"`{GCP_PROJECT}.{BQ_DATASET}.{name}`"


def run_query(sql: str) -> list[bigquery.Row]:
    return list(get_bq().query(sql).result())


def run_dml(sql: str) -> int:
    """Thực thi DML (INSERT/UPDATE/MERGE) và trả về số dòng bị ảnh hưởng."""
    job = get_bq().query(sql)
    job.result()
    return job.num_dml_affected_rows or 0


# ── HITL table bootstrap ───────────────────────────────────────────────────────
_hitl_table_ready   = False
_hitl_table_lock    = Lock()


def ensure_hitl_table() -> None:
    """Tạo bảng hitl_reviews trên BigQuery nếu chưa tồn tại (idempotent)."""
    global _hitl_table_ready
    if _hitl_table_ready:
        return
    with _hitl_table_lock:
        if _hitl_table_ready:
            return
        full_id = f"{GCP_PROJECT}.{BQ_DATASET}.{BQ_HITL}"
        schema = [
            bigquery.SchemaField("article_id",            "STRING",    mode="REQUIRED"),
            bigquery.SchemaField("status",                "STRING",    mode="REQUIRED"),
            bigquery.SchemaField("action",                "STRING",    mode="NULLABLE"),
            bigquery.SchemaField("human_corrected_label", "STRING",    mode="NULLABLE"),
            bigquery.SchemaField("reviewed_at",           "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("is_used_for_retraining","BOOL",      mode="NULLABLE"),
        ]
        table = bigquery.Table(full_id, schema=schema)
        get_bq().create_table(table, exists_ok=True)
        print(f"[INFO] HITL table ready: {full_id}")
        _hitl_table_ready = True


# ── TTL cache đơn giản (in-memory) ────────────────────────────────────────────
_cache: dict[str, tuple[float, object]] = {}


def cache_get(key: str) -> object | None:
    entry = _cache.get(key)
    if entry and (time.monotonic() - entry[0]) < CACHE_TTL:
        return entry[1]
    return None


def cache_set(key: str, value: object) -> None:
    _cache[key] = (time.monotonic(), value)


# ── Text preprocessing ────────────────────────────────────────────────────────
def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text))
    text = text.lower()
    text = re.sub(r"http\S+|www\.\S+",    " ", text)
    text = re.sub(r"\S+@\S+\.\S+",        " ", text)
    text = re.sub(r"<.*?>",               " ", text)
    text = re.sub(r"[^a-zA-ZÀ-ỹà-ỹ\s]", " ", text)
    text = re.sub(r"\s+",                 " ", text).strip()
    return text


# ── SQL helpers ────────────────────────────────────────────────────────────────
def _escape(value: str) -> str:
    """Escape dấu nháy đơn cho BigQuery string literal."""
    return str(value or "").replace("'", "\\'")


def _build_where(label_filter: str, search: str, alias: str = "l") -> str:
    clauses: list[str] = []
    if label_filter:
        clauses.append(f"{alias}.label = '{_escape(label_filter)}'")
    if search:
        s = _escape(search).lower()
        clauses.append(
            f"(LOWER({alias}.title) LIKE '%{s}%' "
            f"OR LOWER({alias}.content) LIKE '%{s}%')"
        )
    return ("WHERE " + " AND ".join(clauses)) if clauses else ""


# ── HITL Preprocessing trigger ────────────────────────────────────────────────

def _count_unprocessed_reviewed() -> int:
    """Đếm số bài đã reviewed nhưng chưa được đẩy vào staging."""
    rows = run_query(f"""
        SELECT COUNT(*) AS cnt
        FROM {tbl(BQ_HITL)}
        WHERE status IN ('{HITL_STATUS_APPROVED}', '{HITL_STATUS_REJECTED}')
          AND (is_used_for_retraining IS NULL OR is_used_for_retraining = FALSE)
    """)
    return int(rows[0].cnt) if rows else 0


def _trigger_hitl_preprocess(count: int) -> None:
    """Gọi Cloud Function preprocessing bất đồng bộ (fire-and-forget).
    Nếu CF_URL chưa cấu hình thì bỏ qua."""
    if not HITL_PREPROCESS_CF_URL:
        print("[INFO] HITL_PREPROCESS_CF_URL chưa cấu hình – bỏ qua trigger.")
        return
    try:
        resp = http_requests.post(
            HITL_PREPROCESS_CF_URL,
            json={"trigger": "hitl_batch", "unprocessed_count": count},
            timeout=30,
        )
        print(f"[INFO] HITL preprocess CF triggered – status={resp.status_code}")
    except Exception as exc:
        print(f"[WARN] Không thể gọi HITL preprocess CF: {exc}")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    """Kiểm tra kết nối BigQuery và trả về tổng số bài viết."""
    try:
        rows  = run_query(f"SELECT COUNT(*) AS cnt FROM {tbl(BQ_LABELED)}")
        total = rows[0].cnt
        return jsonify({"status": "ok", "total_articles": total, "project": GCP_PROJECT})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503


@app.get("/api/stats")
def stats():
    """Thống kê phân bố nhãn (có cache)."""
    cached = cache_get("stats")
    if cached:
        return jsonify(cached)

    try:
        rows = run_query(f"""
            SELECT label, COUNT(*) AS cnt
            FROM   {tbl(BQ_LABELED)}
            WHERE  label IS NOT NULL
            GROUP  BY label
            ORDER  BY cnt DESC
        """)
    except GoogleAPICallError as exc:
        return jsonify({"error": str(exc)}), 503

    label_counts = {r.label: r.cnt for r in rows}
    result = {
        "total":              sum(label_counts.values()),
        "label_distribution": label_counts,
        "label_colors":       LABEL_COLORS,
        "label_icons":        LABEL_ICONS,
    }
    cache_set("stats", result)
    return jsonify(result)


@app.get("/api/labels")
def labels():
    """Danh sách nhãn phân loại (có cache)."""
    cached = cache_get("labels")
    if cached:
        return jsonify(cached)

    try:
        rows = run_query(f"""
            SELECT DISTINCT label
            FROM   {tbl(BQ_LABELED)}
            WHERE  label IS NOT NULL
            ORDER  BY label
        """)
    except GoogleAPICallError as exc:
        return jsonify({"error": str(exc)}), 503

    result = {"labels": [r.label for r in rows]}
    cache_set("labels", result)
    return jsonify(result)


@app.get("/api/articles")
def articles():
    """
    Danh sách bài viết từ labeled_articles, LEFT JOIN summarized_articles.
    Query params:
        page   (int)  – trang hiện tại, mặc định 1
        limit  (int)  – số bài mỗi trang, tối đa 100, mặc định 20
        label  (str)  – lọc theo nhãn
        search (str)  – tìm trong tiêu đề + nội dung
    """
    page         = request.args.get("page",   1,  type=int)
    limit        = min(request.args.get("limit", 20, type=int), 100)
    label_filter = request.args.get("label",  "").strip()
    search       = request.args.get("search", "").strip()
    offset       = (page - 1) * limit

    where = _build_where(label_filter, search)

    try:
        count_rows = run_query(f"""
            SELECT COUNT(*) AS total
            FROM   {tbl(BQ_LABELED)} l
            {where}
        """)
        total = count_rows[0].total

        rows = run_query(f"""
            SELECT
                l.id,
                l.title,
                l.link,
                l.source,
                l.pub_date,
                l.label,
                l.confidence,
                SUBSTR(REGEXP_REPLACE(COALESCE(l.content, ''), r'<[^>]+>', ''), 1, 300) AS snippet,
                s.summary,
                s.keywords
            FROM {tbl(BQ_LABELED)} l
            LEFT JOIN {tbl(BQ_SUMMARY)} s ON l.link = s.link
            {where}
            ORDER BY l.labeled_at DESC
            LIMIT  {limit}
            OFFSET {offset}
        """)
    except GoogleAPICallError as exc:
        return jsonify({"error": str(exc)}), 503

    items = [
        {
            "id":         r.id,
            "title":      r.title      or "",
            "link":       r.link       or "",
            "source":     r.source     or "",
            "pub_date":   r.pub_date   or "",
            "label":      r.label      or "",
            "confidence": r.confidence or "",
            "snippet":    (r.snippet   or "") + "…",
            "summary":    r.summary    or "",
            "keywords":   r.keywords   or "",
        }
        for r in rows
    ]

    return jsonify({
        "total":    total,
        "page":     page,
        "limit":    limit,
        "articles": items,
    })


@app.get("/api/articles/<article_id>")
def article_detail(article_id: str):
    """
    Chi tiết một bài viết theo id (UUID string từ BigQuery).
    Kết hợp dữ liệu từ labeled_articles và summarized_articles.
    """
    try:
        rows = run_query(f"""
            SELECT
                l.id,
                l.title,
                l.link,
                l.source,
                l.pub_date,
                l.content,
                l.label,
                l.confidence,
                l.model_used,
                CAST(l.labeled_at AS STRING) AS labeled_at,
                s.summary,
                s.key_points,
                s.keywords
            FROM {tbl(BQ_LABELED)} l
            LEFT JOIN {tbl(BQ_SUMMARY)} s ON l.link = s.link
            WHERE l.id = '{_escape(article_id)}'
            LIMIT 1
        """)
    except GoogleAPICallError as exc:
        return jsonify({"error": str(exc)}), 503

    if not rows:
        return jsonify({"error": "Not found"}), 404

    r = rows[0]

    key_points: list[str] = []
    try:
        if r.key_points:
            key_points = json.loads(r.key_points)
    except Exception:
        key_points = []

    content = re.sub(r"<[^>]+>", "", r.content or "")

    return jsonify({
        "id":         r.id,
        "title":      r.title      or "",
        "link":       r.link       or "",
        "source":     r.source     or "",
        "pub_date":   r.pub_date   or "",
        "content":    content,
        "label":      r.label      or "",
        "confidence": r.confidence or "",
        "model_used": r.model_used or "",
        "labeled_at": r.labeled_at or "",
        "summary":    r.summary    or "",
        "key_points": key_points,
        "keywords":   r.keywords   or "",
    })


@app.post("/api/predict")
def predict():
    """Dự đoán nhãn bài viết thông qua Vertex AI Endpoint."""
    body = request.get_json(silent=True)
    if not body or "text" not in body:
        return jsonify({"error": "Thiếu trường 'text'"}), 400

    raw_text = body["text"]
    if not raw_text.strip():
        return jsonify({"error": "Văn bản không được để trống"}), 400

    cleaned = clean_text(raw_text)

    try:
        endpoint = get_vertex_endpoint()
        # Vertex AI sklearn endpoint nhận list of instances
        # Mỗi instance là một string (text đã clean)
        response = endpoint.predict(instances=[cleaned])
        prediction = response.predictions[0]
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        return jsonify({"error": f"Vertex AI prediction failed: {exc}"}), 503

    # Prediction có thể là int (class index) hoặc string (class label)
    if isinstance(prediction, (int, float)):
        label = LABEL_MAP.get(int(prediction), str(prediction))
    else:
        label = str(prediction)

    return jsonify({
        "label": label,
        "icon":  LABEL_ICONS.get(label, ""),
        "color": LABEL_COLORS.get(label, "#000"),
    })


# ── HITL Endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/hitl/pending")
def hitl_pending():
    """
    Danh sách bài viết đang chờ duyệt (status = PENDING_REVIEW).
    Ưu tiên: nhãn NOISE trước, sau đó sắp xếp theo confidence tăng dần.
    Query params:
        page  (int) – mặc định 1
        limit (int) – mặc định 20, tối đa 100
    """
    ensure_hitl_table()

    page   = request.args.get("page",  1,  type=int)
    limit  = min(request.args.get("limit", 20, type=int), 100)
    offset = (page - 1) * limit

    base_filter = f"""
        FROM {tbl(BQ_LABELED)} l
        LEFT JOIN {tbl(BQ_HITL)} h ON l.id = h.article_id
        WHERE h.article_id IS NULL
           OR h.status = '{HITL_STATUS_PENDING}'
    """

    try:
        count_rows = run_query(f"SELECT COUNT(*) AS total {base_filter}")
        total = count_rows[0].total

        rows = run_query(f"""
            SELECT
                l.id,
                l.title,
                l.link                                                              AS source_url,
                l.source,
                l.pub_date,
                SUBSTR(REGEXP_REPLACE(COALESCE(l.content, ''), r'<[^>]+>', ''), 1, 300)
                                                                                    AS content_snippet,
                l.label                                                             AS ai_predicted_label,
                l.confidence                                                        AS ai_confidence_score,
                CAST(l.labeled_at AS STRING)                                        AS created_at,
                COALESCE(h.status, '{HITL_STATUS_PENDING}')                         AS status,
                h.human_corrected_label,
                CAST(h.reviewed_at AS STRING)                                       AS reviewed_at
            {base_filter}
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

    items = [
        {
            "id":                   r.id,
            "title":                r.title               or "",
            "source_url":           r.source_url          or "",
            "source":               r.source              or "",
            "pub_date":             r.pub_date            or "",
            "content_snippet":      (r.content_snippet or "") + "…",
            "ai_predicted_label":   r.ai_predicted_label  or "",
            "ai_confidence_score":  r.ai_confidence_score or "",
            "created_at":           r.created_at          or "",
            "status":               r.status,
            "human_corrected_label":r.human_corrected_label or None,
            "reviewed_at":          r.reviewed_at         or None,
        }
        for r in rows
    ]

    return jsonify({
        "total":    total,
        "page":     page,
        "limit":    limit,
        "articles": items,
    })


@app.post("/api/hitl/review/<article_id>")
def hitl_review(article_id: str):
    """
    Ghi nhận quyết định duyệt của reviewer.
    Payload JSON:
        action         (str) – "Accept" | "Correct" | "Reject"
        corrected_label(str) – bắt buộc khi action == "Correct"
    Mapping:
        Accept  → status APPROVED   (giữ nguyên nhãn AI)
        Correct → status APPROVED   (ghi đè bằng corrected_label)
        Reject  → status REJECTED_NOISE
    """
    ensure_hitl_table()

    body = request.get_json(silent=True) or {}
    action          = (body.get("action") or "").strip()
    corrected_label = (body.get("corrected_label") or "").strip() or None

    # ── Validation ──────────────────────────────────────────────────────────
    if action not in HITL_VALID_ACTIONS:
        return jsonify({
            "error": f"action không hợp lệ. Giá trị cho phép: {sorted(HITL_VALID_ACTIONS)}"
        }), 400

    if action == HITL_ACTION_CORRECT:
        if not corrected_label:
            return jsonify({"error": "corrected_label là bắt buộc khi action = 'Correct'"}), 400
        if corrected_label not in HITL_VALID_LABELS:
            return jsonify({
                "error": f"corrected_label không hợp lệ. Giá trị cho phép: {sorted(HITL_VALID_LABELS)}"
            }), 400

    # ── Kiểm tra bài viết tồn tại ───────────────────────────────────────────
    try:
        exists_rows = run_query(f"""
            SELECT id FROM {tbl(BQ_LABELED)}
            WHERE id = '{_escape(article_id)}'
            LIMIT 1
        """)
    except GoogleAPICallError as exc:
        return jsonify({"error": str(exc)}), 503

    if not exists_rows:
        return jsonify({"error": "Không tìm thấy bài viết"}), 404

    # ── Map action → status ──────────────────────────────────────────────────
    status = HITL_STATUS_REJECTED if action == HITL_ACTION_REJECT else HITL_STATUS_APPROVED
    label_sql = f"'{_escape(corrected_label)}'" if corrected_label else "NULL"

    # ── MERGE (upsert) vào hitl_reviews ─────────────────────────────────────
    merge_sql = f"""
        MERGE {tbl(BQ_HITL)} AS target
        USING (SELECT '{_escape(article_id)}' AS article_id) AS source
        ON target.article_id = source.article_id
        WHEN MATCHED THEN
            UPDATE SET
                status                = '{status}',
                action                = '{action}',
                human_corrected_label = {label_sql},
                reviewed_at           = CURRENT_TIMESTAMP(),
                is_used_for_retraining = FALSE
        WHEN NOT MATCHED THEN
            INSERT (article_id, status, action, human_corrected_label, reviewed_at, is_used_for_retraining)
            VALUES (
                '{_escape(article_id)}',
                '{status}',
                '{action}',
                {label_sql},
                CURRENT_TIMESTAMP(),
                FALSE
            )
    """

    try:
        run_dml(merge_sql)
    except GoogleAPICallError as exc:
        return jsonify({"error": str(exc)}), 503

    # ── Kiểm tra batch threshold và gọi Cloud Function preprocessing ────────
    # Chạy trong daemon thread để không block Flask worker
    unprocessed_count: int | None = None
    try:
        unprocessed_count = _count_unprocessed_reviewed()
        if unprocessed_count >= HITL_BATCH_THRESHOLD:
            Thread(
                target=_trigger_hitl_preprocess,
                args=(unprocessed_count,),
                daemon=True,
            ).start()
    except Exception as exc:
        print(f"[WARN] Lỗi khi kiểm tra batch threshold: {exc}")

    return jsonify({
        "article_id":              article_id,
        "action":                  action,
        "status":                  status,
        "human_corrected_label":   corrected_label,
        "message":                 "Duyệt bài viết thành công",
        "unprocessed_batch_count": unprocessed_count,
    })


@app.get("/api/hitl/stats")
def hitl_stats():
    """
    Thống kê nhanh cho HITL Dashboard:
    - pending_count    : số bài đang chờ duyệt
    - reviewed_today   : số bài đã duyệt hôm nay (UTC)
    - approved_total   : tổng số bài đã APPROVED
    - rejected_total   : tổng số bài đã REJECTED_NOISE
    - total_articles   : tổng số bài trong labeled_articles
    """
    ensure_hitl_table()

    cached = cache_get("hitl_stats")
    if cached:
        return jsonify(cached)

    try:
        rows = run_query(f"""
            SELECT
                COUNTIF(h.article_id IS NULL OR h.status = '{HITL_STATUS_PENDING}')
                                                                AS pending_count,
                COUNTIF(DATE(h.reviewed_at, 'UTC') = CURRENT_DATE('UTC'))
                                                                AS reviewed_today,
                COUNTIF(h.status = '{HITL_STATUS_APPROVED}')    AS approved_total,
                COUNTIF(h.status = '{HITL_STATUS_REJECTED}')    AS rejected_total,
                COUNT(DISTINCT l.id)                            AS total_articles
            FROM {tbl(BQ_LABELED)} l
            LEFT JOIN {tbl(BQ_HITL)} h ON l.id = h.article_id
        """)
    except GoogleAPICallError as exc:
        return jsonify({"error": str(exc)}), 503

    r = rows[0]
    result = {
        "pending_count":   r.pending_count,
        "reviewed_today":  r.reviewed_today,
        "approved_total":  r.approved_total,
        "rejected_total":  r.rejected_total,
        "total_articles":  r.total_articles,
    }
    cache_set("hitl_stats", result)
    return jsonify(result)


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
