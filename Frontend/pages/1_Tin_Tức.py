"""
Streamlit – Trang trình duyệt bài viết
Dữ liệu lấy từ Backend Flask (nguồn: BigQuery labeled_articles + summarized_articles).
"""

import json
import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:5000")

st.set_page_config(
    page_title="Tin tức AI",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://img.icons8.com/fluency/96/artificial-intelligence.png",
        width=80,
    )
    st.title("AI News Pipeline")
    st.divider()
    st.page_link("app.py",                    label="📊 Dashboard",     icon="📊")
    st.page_link("pages/1_Tin_Tức.py",        label="📰 Tin tức",       icon="📰")
    st.page_link("pages/2_Dự_Đoán.py",        label="🔍 Dự đoán nhãn", icon="🔍")
    st.divider()

    st.subheader("🔎 Bộ lọc")

    label_options = ["Tất cả"]
    try:
        resp = requests.get(f"{API_URL}/api/labels", timeout=5)
        if resp.ok:
            label_options += resp.json().get("labels", [])
    except Exception:
        pass

    LABEL_VI = {
        "MARKET SIGNALS":        "📈 Tín hiệu thị trường",
        "SOLUTIONS & USE CASES": "🛠️ Giải pháp & Ứng dụng",
        "DEEP DIVE":             "🔬 Phân tích chuyên sâu",
        "NOISE":                 "🔇 Nhiễu",
    }

    selected_label = st.selectbox(
        "Nhãn phân loại",
        options=label_options,
        format_func=lambda l: "📂 Tất cả" if l == "Tất cả" else LABEL_VI.get(l, l),
    )
    search_query = st.text_input("Tìm kiếm", placeholder="Nhập từ khóa…")
    page_size    = st.select_slider("Số bài mỗi trang", options=[10, 20, 30, 50], value=20)


# ── Constants ─────────────────────────────────────────────────────────────────
LABEL_COLORS = {
    "MARKET SIGNALS":        "#E74C3C",
    "SOLUTIONS & USE CASES": "#27AE60",
    "DEEP DIVE":             "#2980B9",
    "NOISE":                 "#95A5A6",
}
CONF_ICONS = {"high": "🟢", "medium": "🟡", "low": "🔴"}


def label_badge(label: str) -> str:
    color = LABEL_COLORS.get(label, "#999")
    vi    = LABEL_VI.get(label, label)
    return (
        f'<span style="background:{color};color:white;padding:2px 10px;'
        f'border-radius:12px;font-size:0.75rem;font-weight:600">{vi}</span>'
    )


# ── API helpers ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def fetch_articles(page, limit, label, search):
    params = {"page": page, "limit": limit}
    if label and label != "Tất cả":
        params["label"] = label
    if search:
        params["search"] = search
    resp = requests.get(f"{API_URL}/api/articles", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=60, show_spinner=False)
def fetch_detail(article_id: str):
    resp = requests.get(f"{API_URL}/api/articles/{article_id}", timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── Session state ─────────────────────────────────────────────────────────────
if "current_page" not in st.session_state:
    st.session_state["current_page"] = 1

if "view_article" not in st.session_state:
    # Nhận article_id từ URL param (khi click từ Dashboard)
    qp = st.query_params.get("article_id")
    st.session_state["view_article"] = qp  # UUID string hoặc None

# Reset trang khi bộ lọc thay đổi
filter_key = f"{selected_label}|{search_query}|{page_size}"
if st.session_state.get("_filter_key") != filter_key:
    st.session_state["current_page"] = 1
    st.session_state["_filter_key"]  = filter_key


# ══════════════════════════════════════════════════════════════════════════════
# CHẾ ĐỘ XEM CHI TIẾT
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state["view_article"] is not None:
    art_id = st.session_state["view_article"]

    if st.button("← Quay lại danh sách"):
        st.session_state["view_article"] = None
        st.query_params.clear()
        st.rerun()

    try:
        article = fetch_detail(art_id)
    except Exception as exc:
        st.error(f"Không tải được bài viết: {exc}")
        st.stop()

    label      = article.get("label", "")
    confidence = article.get("confidence", "")
    conf_icon  = CONF_ICONS.get(confidence, "")

    # Header
    st.title(article.get("title", "—"))

    meta_col1, meta_col2, meta_col3 = st.columns([3, 2, 2])
    with meta_col1:
        st.markdown(label_badge(label), unsafe_allow_html=True)
        if confidence:
            st.caption(f"{conf_icon} Độ tin cậy: **{confidence}**  ·  Model: {article.get('model_used','—')}")
    with meta_col2:
        if article.get("source"):
            st.caption(f"🌐 Nguồn: **{article['source']}**")
        if article.get("pub_date"):
            st.caption(f"📅 {article['pub_date']}")
    with meta_col3:
        if article.get("link"):
            st.link_button("🔗 Đọc bài gốc", url=article["link"])

    st.divider()

    # Tóm tắt AI (nếu có)
    if article.get("summary"):
        with st.container(border=True):
            st.subheader("📝 Tóm tắt AI")
            st.markdown(article["summary"])

            key_points = article.get("key_points", [])
            if key_points:
                st.markdown("**Điểm chính:**")
                for pt in key_points:
                    st.markdown(f"- {pt}")

            keywords = article.get("keywords", "")
            if keywords:
                st.caption(
                    "🏷️ Từ khóa: "
                    + "  ".join(
                        f'`{kw.strip()}`'
                        for kw in keywords.split(",")
                        if kw.strip()
                    )
                )

        st.divider()

    # Nội dung đầy đủ
    with st.expander("📄 Nội dung đầy đủ", expanded=not article.get("summary")):
        content = article.get("content", "")
        if content:
            st.markdown(content)
        else:
            st.info("Không có nội dung.")

    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# CHẾ ĐỘ DANH SÁCH
# ══════════════════════════════════════════════════════════════════════════════
st.title("📰 Tin tức AI")
st.caption("Dữ liệu từ BigQuery – labeled_articles × summarized_articles")

try:
    result = fetch_articles(
        st.session_state["current_page"],
        page_size,
        selected_label,
        search_query,
    )
except Exception as exc:
    st.error(f"Không kết nối được Backend: {exc}")
    st.stop()

articles    = result.get("articles", [])
total       = result.get("total", 0)
cur_page    = result.get("page", 1)
total_pages = max(1, -(-total // page_size))

st.markdown(f"**{total:,}** bài viết · Trang {cur_page}/{total_pages}")
st.divider()

if not articles:
    st.info("Không tìm thấy bài viết nào phù hợp.")
else:
    for art in articles:
        label      = art.get("label", "")
        confidence = art.get("confidence", "")
        summary    = art.get("summary", "")
        keywords   = art.get("keywords", "")
        source     = art.get("source", "")
        pub_date   = art.get("pub_date", "")

        with st.container(border=True):
            top_col, btn_col = st.columns([7, 1])

            with top_col:
                # Tiêu đề + badge
                st.markdown(f"**{art.get('title', '—')}**")

                badge_row = label_badge(label)
                if source:
                    badge_row += (
                        f'&nbsp;&nbsp;<span style="color:#888;font-size:0.8rem">'
                        f'🌐 {source}</span>'
                    )
                if pub_date:
                    badge_row += (
                        f'&nbsp;&nbsp;<span style="color:#aaa;font-size:0.75rem">'
                        f'📅 {pub_date[:16]}</span>'
                    )
                st.markdown(badge_row, unsafe_allow_html=True)

                # Tóm tắt AI ưu tiên, fallback snippet
                preview = summary if summary else art.get("snippet", "")
                if preview:
                    st.caption(preview[:250])

                # Keywords
                if keywords:
                    kw_html = " ".join(
                        f'<code style="font-size:0.7rem;padding:1px 6px">{kw.strip()}</code>'
                        for kw in keywords.split(",")
                        if kw.strip()
                    )
                    st.markdown(kw_html, unsafe_allow_html=True)

            with btn_col:
                if st.button("Đọc →", key=f"read_{art['id']}"):
                    st.session_state["view_article"] = art["id"]
                    st.rerun()

# ── Phân trang ────────────────────────────────────────────────────────────────
st.divider()
p1, p2, p3 = st.columns([1, 2, 1])

with p1:
    if st.button("⬅ Trang trước", disabled=cur_page <= 1):
        st.session_state["current_page"] = cur_page - 1
        st.rerun()

with p2:
    st.markdown(
        f"<div style='text-align:center'>Trang {cur_page} / {total_pages}</div>",
        unsafe_allow_html=True,
    )

with p3:
    if st.button("Trang sau ➡", disabled=cur_page >= total_pages):
        st.session_state["current_page"] = cur_page + 1
        st.rerun()
