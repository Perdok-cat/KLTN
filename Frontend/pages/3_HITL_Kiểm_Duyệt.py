"""
Streamlit – HITL Admin Dashboard
Kiểm duyệt bài báo AI phân loại có độ tin cậy thấp hoặc nghi ngờ là Nhiễu.
"""
from __future__ import annotations

import math
import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:5000")

st.set_page_config(
    page_title="Kiểm duyệt HITL",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ──────────────────────────────────────────────────────────────────
LABEL_COLORS = {
    "MARKET SIGNALS":        "#E74C3C",
    "SOLUTIONS & USE CASES": "#27AE60",
    "DEEP DIVE":             "#2980B9",
    "NOISE":                 "#95A5A6",
}
LABEL_VI = {
    "MARKET SIGNALS":        "Tín hiệu thị trường",
    "SOLUTIONS & USE CASES": "Giải pháp & Ứng dụng",
    "DEEP DIVE":             "Phân tích chuyên sâu",
    "NOISE":                 "Nhiễu",
}
ALL_LABELS = ["DEEP DIVE", "MARKET SIGNALS", "NOISE", "SOLUTIONS & USE CASES"]

# Categorical confidence → numeric [0, 1]
CONF_NUM = {"low": 0.20, "medium": 0.55, "high": 0.90}
CONF_COLOR = {
    "low":    "#E74C3C",
    "medium": "#F39C12",
    "high":   "#27AE60",
}
CONF_ICON = {"low": "🔴", "medium": "🟡", "high": "🟢"}

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://img.icons8.com/fluency/96/artificial-intelligence.png",
        width=80,
    )
    st.title("AI News Pipeline")
    st.divider()
    st.page_link("app.py",                          label="📊 Dashboard",        icon="📊")
    st.page_link("pages/1_Tin_Tức.py",              label="📰 Tin tức",          icon="📰")
    st.page_link("pages/2_Dự_Đoán.py",              label="🔍 Dự đoán nhãn",    icon="🔍")
    st.page_link("pages/3_HITL_Kiểm_Duyệt.py",     label="🛡️ Kiểm duyệt HITL", icon="🛡️")
    st.divider()

    page_size = st.select_slider(
        "Số bài mỗi trang",
        options=[5, 10, 20],
        value=10,
    )
    st.divider()
    st.info(
        "**Hướng dẫn:**\n"
        "- **Approve** – giữ nguyên nhãn AI\n"
        "- **Reject** – đánh dấu là Nhiễu\n"
        "- **Sửa nhãn** – chọn nhãn đúng rồi nhấn Lưu"
    )

# ── CSS injection ──────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Hover lift effect for article cards */
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow: 0 4px 16px rgba(0,0,0,0.10);
        transition: box-shadow 0.25s ease;
    }
    /* Tighten button spacing inside cards */
    [data-testid="stVerticalBlockBorderWrapper"] .stButton > button {
        border-radius: 8px;
    }
    /* Approve button – force green */
    button[kind="primary"] {
        background-color: #27AE60 !important;
        border-color: #27AE60 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state init ─────────────────────────────────────────────────────────
_defaults: dict = {
    "hitl_page":         1,
    "hitl_actioned":     set(),
    "hitl_stats_cache":  None,
    "hitl_data_cache":   None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── API helpers ────────────────────────────────────────────────────────────────
def fetch_stats() -> dict:
    resp = requests.get(f"{API_URL}/api/hitl/stats", timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_pending(page: int, limit: int) -> dict:
    resp = requests.get(
        f"{API_URL}/api/hitl/pending",
        params={"page": page, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def post_review(article_id: str, action: str, corrected_label: str | None = None) -> dict:
    payload: dict = {"action": action}
    if corrected_label:
        payload["corrected_label"] = corrected_label
    resp = requests.post(
        f"{API_URL}/api/hitl/review/{article_id}",
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# ── Render helpers ─────────────────────────────────────────────────────────────
def conf_to_float(raw: str | None) -> float:
    if not raw:
        return 0.5
    key = str(raw).lower()
    if key in CONF_NUM:
        return CONF_NUM[key]
    try:
        return min(max(float(raw), 0.0), 1.0)
    except ValueError:
        return 0.5


def label_badge(label: str) -> str:
    color = LABEL_COLORS.get(label, "#999")
    vi    = LABEL_VI.get(label, label)
    return (
        f'<span style="background:{color};color:#fff;padding:3px 11px;'
        f'border-radius:12px;font-size:0.73rem;font-weight:600">{vi}</span>'
    )


def progress_bar_html(conf_raw: str | None) -> str:
    val    = conf_to_float(conf_raw)
    key    = str(conf_raw or "").lower()
    color  = CONF_COLOR.get(key, "#F39C12")
    icon   = CONF_ICON.get(key, "🟡")
    label  = str(conf_raw or "—").upper()
    pct    = val * 100
    return f"""
    <div style="margin:6px 0 10px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="font-size:0.75rem;color:#555">Độ tin cậy AI:</span>
            <span style="font-size:0.75rem;font-weight:700;color:{color}">{icon} {label}</span>
        </div>
        <div style="background:#e9ecef;border-radius:6px;height:8px;overflow:hidden">
            <div style="width:{pct:.0f}%;background:{color};height:100%;
                        border-radius:6px;transition:width 0.4s ease"></div>
        </div>
    </div>
    """


# ── Page header ────────────────────────────────────────────────────────────────
st.title("🛡️ Kiểm duyệt HITL")
st.caption(
    "Xem xét và phê duyệt các bài báo AI phân loại có độ tin cậy thấp "
    "hoặc nghi ngờ là **Nhiễu** – Human-in-the-Loop"
)

# ── Load stats ─────────────────────────────────────────────────────────────────
try:
    stats = fetch_stats()
    st.session_state["hitl_stats_cache"] = stats
except Exception as exc:
    st.warning(f"Không tải được thống kê: {exc}")
    stats = st.session_state["hitl_stats_cache"] or {}

pending_count  = stats.get("pending_count",  0)
reviewed_today = stats.get("reviewed_today", 0)
approved_total = stats.get("approved_total", 0)
rejected_total = stats.get("rejected_total", 0)
total_articles = stats.get("total_articles", 0)
reviewed_all   = approved_total + rejected_total
noise_ratio    = rejected_total / reviewed_all * 100 if reviewed_all > 0 else 0.0

# ── Top Bar – 5 metrics ────────────────────────────────────────────────────────
st.divider()
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("⏳ Chờ duyệt",       f"{pending_count:,}")
m2.metric("✅ Đã duyệt hôm nay", f"{reviewed_today:,}")
m3.metric("🗑️ Tỉ lệ Nhiễu",     f"{noise_ratio:.1f}%")
m4.metric("👍 Tổng Approved",   f"{approved_total:,}")
m5.metric("📰 Tổng bài viết",   f"{total_articles:,}")
st.divider()

# ── Load pending articles ──────────────────────────────────────────────────────
with st.spinner("Đang tải danh sách bài chờ duyệt…"):
    try:
        result = fetch_pending(st.session_state["hitl_page"], page_size)
        st.session_state["hitl_data_cache"] = result
    except Exception as exc:
        st.error(f"Không tải được danh sách bài viết: {exc}")
        result = st.session_state["hitl_data_cache"] or {
            "articles": [], "total": 0, "page": 1
        }

all_articles = result.get("articles", [])
total_pending = result.get("total", 0)
cur_page      = result.get("page", 1)
total_pages   = max(1, math.ceil(total_pending / page_size))

# Filter out articles already actioned this session
visible = [a for a in all_articles if a["id"] not in st.session_state["hitl_actioned"]]

# ── Queue header ───────────────────────────────────────────────────────────────
hdr_col, refresh_col = st.columns([7, 1])
with hdr_col:
    st.subheader(
        f"📋 Hàng chờ duyệt · "
        f"{total_pending:,} bài · Trang {cur_page} / {total_pages}"
    )
with refresh_col:
    if st.button("🔄 Làm mới", use_container_width=True):
        st.session_state["hitl_actioned"] = set()
        st.session_state["hitl_page"]     = 1
        st.cache_data.clear()
        st.rerun()

# ── Empty states ───────────────────────────────────────────────────────────────
if not visible:
    if total_pending == 0:
        st.success("🎉 Tuyệt vời! Không còn bài nào chờ duyệt.")
    else:
        st.info(
            "Tất cả bài trên trang này đã được xử lý. "
            "Nhấn **Trang sau** hoặc **Làm mới** để tiếp tục."
        )

# ── Article cards ──────────────────────────────────────────────────────────────
for art in visible:
    article_id = art["id"]
    ai_label   = art.get("ai_predicted_label", "")
    conf_raw   = art.get("ai_confidence_score", "")
    title      = art.get("title") or "—"
    source     = art.get("source", "")
    pub_date   = art.get("pub_date", "")
    snippet    = art.get("content_snippet", "")
    source_url = art.get("source_url", "")

    with st.container(border=True):
        left_col, right_col = st.columns([6, 2], gap="large")

        # ── Left: article info ─────────────────────────────────────────────
        with left_col:
            # Title
            if source_url:
                st.markdown(f"#### [{title}]({source_url})")
            else:
                st.markdown(f"#### {title}")

            # Label badge + source meta
            badge_parts = [label_badge(ai_label)]
            if source:
                badge_parts.append(
                    f'<span style="color:#888;font-size:0.78rem;margin-left:8px">'
                    f'🌐 {source}</span>'
                )
            if pub_date:
                badge_parts.append(
                    f'<span style="color:#aaa;font-size:0.73rem;margin-left:8px">'
                    f'📅 {str(pub_date)[:16]}</span>'
                )
            st.markdown(" ".join(badge_parts), unsafe_allow_html=True)

            # Snippet preview
            if snippet:
                st.caption(snippet[:220])

            # Confidence progress bar
            st.markdown(progress_bar_html(conf_raw), unsafe_allow_html=True)

        # ── Right: action buttons ──────────────────────────────────────────
        with right_col:
            st.markdown("**Hành động:**")

            # Approve
            if st.button(
                "✅ Approve",
                key=f"approve_{article_id}",
                type="primary",
                use_container_width=True,
                help="Chấp nhận nhãn AI hiện tại",
            ):
                with st.spinner("Đang ghi nhận…"):
                    try:
                        post_review(article_id, "Accept")
                        st.session_state["hitl_actioned"].add(article_id)
                        st.toast(
                            f"✅ Đã approve: {title[:45]}…",
                            icon="✅",
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Lỗi: {exc}")

            # Reject as Noise
            if st.button(
                "🗑️ Reject as Noise",
                key=f"reject_{article_id}",
                use_container_width=True,
                help="Đánh dấu bài viết này là Nhiễu",
            ):
                with st.spinner("Đang ghi nhận…"):
                    try:
                        post_review(article_id, "Reject")
                        st.session_state["hitl_actioned"].add(article_id)
                        st.toast(
                            f"🗑️ Đã reject: {title[:45]}…",
                            icon="🗑️",
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Lỗi: {exc}")

            st.markdown("**Sửa nhãn:**")
            corrected = st.selectbox(
                "Chọn nhãn đúng",
                options=ALL_LABELS,
                index=ALL_LABELS.index(ai_label) if ai_label in ALL_LABELS else 0,
                format_func=lambda lb: f"{LABEL_VI.get(lb, lb)}",
                key=f"label_sel_{article_id}",
                label_visibility="collapsed",
            )
            if st.button(
                "💾 Lưu nhãn mới",
                key=f"correct_{article_id}",
                use_container_width=True,
                help="Lưu nhãn đã chỉnh sửa",
            ):
                with st.spinner("Đang ghi nhận…"):
                    try:
                        post_review(article_id, "Correct", corrected_label=corrected)
                        st.session_state["hitl_actioned"].add(article_id)
                        st.toast(
                            f"✏️ Đã sửa → {LABEL_VI.get(corrected, corrected)}: "
                            f"{title[:35]}…",
                            icon="✏️",
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Lỗi: {exc}")

# ── Pagination ─────────────────────────────────────────────────────────────────
st.divider()
pg_prev, pg_info, pg_next = st.columns([1, 2, 1])

with pg_prev:
    if st.button("⬅ Trang trước", disabled=cur_page <= 1, use_container_width=True):
        st.session_state["hitl_page"]    = cur_page - 1
        st.session_state["hitl_actioned"] = set()
        st.rerun()

with pg_info:
    st.markdown(
        f"<div style='text-align:center;padding:8px 0'>"
        f"Trang <b>{cur_page}</b> / <b>{total_pages}</b> &nbsp;·&nbsp; "
        f"<span style='color:#888'>{total_pending:,} bài chờ duyệt</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

with pg_next:
    if st.button("Trang sau ➡", disabled=cur_page >= total_pages, use_container_width=True):
        st.session_state["hitl_page"]    = cur_page + 1
        st.session_state["hitl_actioned"] = set()
        st.rerun()

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption("🛡️ HITL Dashboard · AI News Pipeline · KLTN 2026")
