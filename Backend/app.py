"""
Flask Backend – AI News Pipeline API
Nguồn dữ liệu: Google BigQuery (bảng labeled_articles + summarized_articles).
Dự đoán nhãn: TF-IDF + LinearSVC (sklearn) được load từ đĩa.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from pathlib import Path
from threading import Lock

import joblib
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import bigquery
s
load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────
GCP_PROJECT = os.getenv("GCP_PROJECT", "helo")
BQ_DATASET  = os.getenv("BQ_DATASET",  "ai_news")
BQ_LABELED  = os.getenv("BQ_LABELED_TABLE",  "labeled_articles")
BQ_SUMMARY  = os.getenv("BQ_SUMMARY_TABLE",  "summarized_articles")

# Thời gian cache tĩnh (giây) – tránh query BQ liên tục cho stats/labels
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

BASE_DIR   = Path(__file__).parent.parent
TFIDF_PATH = os.getenv("TFIDF_PATH", str(BASE_DIR / "src" / "ML" / "Training" / "tfidf_vectorizer.pkl"))
MODEL_PATH = os.getenv("MODEL_PATH", str(BASE_DIR / "src" / "ML" / "Training" / "LinearSVC.pkl"))

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

# ── Flask app ──────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

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


# ── TTL cache đơn giản (in-memory) ────────────────────────────────────────────
_cache: dict[str, tuple[float, object]] = {}


def cache_get(key: str) -> object | None:
    entry = _cache.get(key)
    if entry and (time.monotonic() - entry[0]) < CACHE_TTL:
        return entry[1]
    return None


def cache_set(key: str, value: object) -> None:
    _cache[key] = (time.monotonic(), value)


# ── ML model (TF-IDF + sklearn) ───────────────────────────────────────────────
tfidf = None
clf   = None


def load_model() -> None:
    global tfidf, clf
    tfidf = joblib.load(TFIDF_PATH)
    clf   = joblib.load(MODEL_PATH)
    print(f"[INFO] ML model loaded: {Path(MODEL_PATH).name}")


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text))
    text = text.lower()
    text = re.sub(r"http\S+|www\.\S+",    " ", text)
    text = re.sub(r"\S+@\S+\.\S+",        " ", text)
    text = re.sub(r"<.*?>",               " ", text)
    text = re.sub(r"[^a-zA-ZÀ-ỹà-ỹ\s]", " ", text)
    text = re.sub(r"\s+",                 " ", text).strip()
    return text


# Khởi động: load model khi app khởi tạo
with app.app_context():
    load_model()


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
    """Dự đoán nhãn bài viết bằng TF-IDF + LinearSVC."""
    body = request.get_json(silent=True)
    if not body or "text" not in body:
        return jsonify({"error": "Thiếu trường 'text'"}), 400

    raw_text = body["text"]
    if not raw_text.strip():
        return jsonify({"error": "Văn bản không được để trống"}), 400

    cleaned = clean_text(raw_text)

    try:
        from underthesea import word_tokenize  # noqa: PLC0415
        text_tok = word_tokenize(cleaned, format="text")
    except Exception:
        text_tok = cleaned

    vec  = tfidf.transform([text_tok])
    pred = clf.predict(vec)[0]

    if isinstance(pred, (int, float)):
        label = LABEL_MAP.get(int(pred), str(pred))
    else:
        label = str(pred)

    result: dict = {
        "label": label,
        "icon":  LABEL_ICONS.get(label, ""),
        "color": LABEL_COLORS.get(label, "#000"),
    }

    if hasattr(clf, "predict_proba"):
        proba = clf.predict_proba(vec)[0]
        result["confidence"] = {
            LABEL_MAP.get(i, str(i)): round(float(p), 4)
            for i, p in enumerate(proba)
        }
    elif hasattr(clf, "decision_function"):
        scores = clf.decision_function(vec)[0]
        scores = [float(scores)] if not hasattr(scores, "__iter__") else list(scores)
        result["decision_scores"] = {
            LABEL_MAP.get(i, str(i)): round(s, 4)
            for i, s in enumerate(scores)
        }

    return jsonify(result)


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
