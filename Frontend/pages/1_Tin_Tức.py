"""
Streamlit - Trang trình duyệt bài viết.
Dữ liệu lấy từ Backend Flask (BigQuery labeled_articles + summarized_articles).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
import streamlit as st

CURRENT_DIR = Path(__file__).resolve().parents[1]
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from ui import (  # noqa: E402
    LABEL_COLORS,
    LABEL_VI,
    apply_global_styles,
    article_meta_html,
    compact_number,
    confidence_chip,
    escape_html,
    format_date,
    hero_html,
    keyword_chips,
    label_chip,
    label_color,
    label_icon,
    label_name,
    neutral_chip,
    percent_text,
    render_sidebar,
    section_header,
    trim_text,
)


API_URL = os.getenv("API_URL", "http://localhost:5000")

st.set_page_config(
    page_title="Tin tức AI",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_global_styles()


@st.cache_data(ttl=30, show_spinner=False)
def fetch_labels() -> list[str]:
    resp = requests.get(f"{API_URL}/api/labels", timeout=5)
    resp.raise_for_status()
    return resp.json().get("labels", [])


@st.cache_data(ttl=30, show_spinner=False)
def fetch_articles(page: int, limit: int, label: str, search: str) -> dict:
    params = {"page": page, "limit": limit}
    if label and label != "Tất cả":
        params["label"] = label
    if search:
        params["search"] = search
    resp = requests.get(f"{API_URL}/api/articles", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=60, show_spinner=False)
def fetch_detail(article_id: str) -> dict:
    resp = requests.get(f"{API_URL}/api/articles/{article_id}", timeout=15)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=20, show_spinner=False)
def check_api() -> bool:
    try:
        resp = requests.get(f"{API_URL}/api/health", timeout=3)
        return resp.ok
    except Exception:
        return False


api_online = check_api()

label_options = ["Tất cả"]
if api_online:
    try:
        label_options += fetch_labels()
    except Exception:
        pass

render_sidebar("news", API_URL, api_online)

with st.sidebar:
    st.divider()
    st.markdown('<div class="sidebar-section-title">Bộ lọc</div>', unsafe_allow_html=True)

    selected_label = st.selectbox(
        "Nhãn phân loại",
        options=label_options,
        format_func=lambda value: "📂 Tất cả" if value == "Tất cả" else f"{label_icon(value)} {label_name(value)}",
    )
    search_query = st.text_input("Tìm kiếm", placeholder="Nhập từ khóa...")
    page_size = st.select_slider("Số bài mỗi trang", options=[10, 20, 30, 50], value=20)

st.session_state.setdefault("current_page", 1)

query_article = st.query_params.get("article_id")
if isinstance(query_article, list):
    query_article = query_article[0] if query_article else None
if "view_article" not in st.session_state:
    st.session_state["view_article"] = query_article
elif query_article and st.session_state["view_article"] != query_article:
    st.session_state["view_article"] = query_article

filter_key = f"{selected_label}|{search_query}|{page_size}"
if st.session_state.get("_filter_key") != filter_key:
    st.session_state["current_page"] = 1
    st.session_state["_filter_key"] = filter_key


def clear_detail() -> None:
    st.session_state["view_article"] = None
    st.query_params.clear()


def open_detail(article_id: str) -> None:
    st.session_state["view_article"] = article_id
    st.query_params["article_id"] = article_id
    st.rerun()


if not api_online:
    st.error(
        f"Không thể kết nối tới Backend tại **{API_URL}**.\n\n"
        "Chạy Backend trước: `cd Backend && python app.py`"
    )
    st.stop()


if st.session_state["view_article"] is not None:
    art_id = str(st.session_state["view_article"])

    top_left, top_right = st.columns([1, 1.2])
    with top_left:
        if st.button("← Danh sách", use_container_width=True):
            clear_detail()
            st.rerun()
    with top_right:
        st.caption("Bài viết chi tiết")

    try:
        article = fetch_detail(art_id)
    except Exception as exc:
        st.error(f"Không tải được bài viết: {exc}")
        st.stop()

    label = str(article.get("label") or "")
    confidence = str(article.get("confidence") or "")
    summary = article.get("summary") or ""
    key_points = article.get("key_points") or []
    keywords = article.get("keywords") or ""
    content = article.get("content") or ""

    st.markdown(
        hero_html(
            "Bài viết chi tiết",
            str(article.get("title", "—")),
            "Tóm tắt, metadata và nội dung gốc trong cùng một màn hình đọc.",
            [
                label_chip(label, LABEL_COLORS),
                confidence_chip(confidence) if confidence else neutral_chip("Tin cậy chưa có", "●", "slate"),
                neutral_chip(str(article.get("source") or "Nguồn chưa có"), "🌐", "slate"),
                neutral_chip(format_date(article.get("pub_date")) or "Ngày chưa rõ", "📅", "slate"),
            ],
        ),
        unsafe_allow_html=True,
    )

    left_col, right_col = st.columns([2.1, 1])

    with left_col:
        with st.container(border=True):
            st.markdown(section_header("Tóm tắt AI", "Điểm chính từ mô hình tóm tắt."), unsafe_allow_html=True)
            if summary:
                st.markdown(summary)
            else:
                st.info("Không có tóm tắt.")

            if key_points:
                st.markdown("**Điểm chính**")
                for point in key_points:
                    st.markdown(f"- {point}")

            if keywords:
                st.markdown(keyword_chips(keywords), unsafe_allow_html=True)

        st.markdown(section_header("Nội dung đầy đủ", "Văn bản đã làm sạch từ backend."), unsafe_allow_html=True)
        with st.container(border=True):
            if content:
                body_html = escape_html(content).replace("\n", "<br>")
                st.markdown(
                    f'<div class="reader-body">{body_html}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.info("Không có nội dung.")

    with right_col:
        with st.container(border=True):
            st.markdown(section_header("Thông tin bài viết", "Metadata và tín hiệu hệ thống."), unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="info-row"><span>Nhãn</span><b>{escape_html(label_name(label))}</b></div>
                <div class="info-row"><span>Độ tin cậy</span><b>{escape_html(confidence or "—")}</b></div>
                <div class="info-row"><span>Model</span><b>{escape_html(article.get("model_used") or "—")}</b></div>
                <div class="info-row"><span>Nguồn</span><b>{escape_html(article.get("source") or "—")}</b></div>
                <div class="info-row"><span>Ngày đăng</span><b>{escape_html(article.get("pub_date") or "—")}</b></div>
                <div class="info-row"><span>Labeled at</span><b>{escape_html(article.get("labeled_at") or "—")}</b></div>
                """,
                unsafe_allow_html=True,
            )

            if article.get("link"):
                st.link_button("Mở bài gốc ↗", url=article["link"], use_container_width=True, type="primary")

        with st.container(border=True):
            st.markdown(section_header("Từ khóa", "Từ khóa được hệ thống trích xuất."), unsafe_allow_html=True)
            if keywords:
                st.markdown(keyword_chips(keywords, limit=12), unsafe_allow_html=True)
            else:
                st.info("Không có từ khóa.")

        with st.container(border=True):
            st.markdown(section_header("Trạng thái", "Tín hiệu nhanh để đọc bài."), unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="info-row"><span>Tin cậy</span><b>{escape_html(confidence or "—")}</b></div>
                <div class="info-row"><span>Ngôn ngữ</span><b>Tiếng Việt</b></div>
                <div class="info-row"><span>ID</span><b>{escape_html(article.get("id") or "—")}</b></div>
                """,
                unsafe_allow_html=True,
            )

    st.stop()


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

articles = result.get("articles", []) or []
total = int(result.get("total", 0) or 0)
cur_page = int(result.get("page", 1) or 1)
total_pages = max(1, -(-total // page_size))

st.markdown(
    hero_html(
        "Tin tức AI",
        "Duyệt bài đã gắn nhãn",
        "Kho bài viết từ BigQuery, có lọc theo nhãn, tìm kiếm theo từ khóa và phân trang rõ ràng.",
        [
            neutral_chip(f"{compact_number(total)} bài", "🧾", "slate"),
            neutral_chip(f"Trang {cur_page}/{total_pages}", "📄", "blue"),
            neutral_chip(f"{page_size}/trang", "▦", "green"),
        ],
    ),
    unsafe_allow_html=True,
)

toolbar_cols = st.columns([2.2, 1.1])
with toolbar_cols[0]:
    chips = [
        neutral_chip(f"{compact_number(total)} bài viết", "🧾", "slate"),
        neutral_chip(f"Trang {cur_page}/{total_pages}", "📄", "blue"),
        neutral_chip(f"{page_size}/trang", "▦", "green"),
    ]
    if selected_label != "Tất cả":
        chips.append(label_chip(selected_label, LABEL_COLORS))
    if search_query:
        chips.append(neutral_chip(f'Từ khóa: "{search_query}"', "⌕", "amber"))
    st.markdown(f'<div class="meta-row">{"".join(chips)}</div>', unsafe_allow_html=True)

with toolbar_cols[1]:
    st.markdown(f'<div class="pager-label">{cur_page} / {total_pages}</div>', unsafe_allow_html=True)

st.markdown(section_header("Danh sách bài viết", "Chọn bài để đọc chi tiết."), unsafe_allow_html=True)

if not articles:
    st.markdown(
        '<div class="empty-state">Không tìm thấy bài viết nào phù hợp.</div>',
        unsafe_allow_html=True,
    )
else:
    for index in range(0, len(articles), 2):
        row = articles[index : index + 2]
        cols = st.columns(2)
        for col, article in zip(cols, row):
            article_id = str(article.get("id") or f"row_{index}")
            preview = article.get("summary") or article.get("snippet") or ""
            with col:
                with st.container(border=True):
                    st.markdown(article_meta_html(article, LABEL_COLORS), unsafe_allow_html=True)
                    st.markdown(
                        f'<div class="article-title">{escape_html(article.get("title", "—"))}</div>',
                        unsafe_allow_html=True,
                    )
                    if preview:
                        st.markdown(
                            f'<div class="article-preview">{escape_html(trim_text(preview, 240))}</div>',
                            unsafe_allow_html=True,
                        )
                    if article.get("keywords"):
                        st.markdown(keyword_chips(article["keywords"], limit=6), unsafe_allow_html=True)
                    if st.button("Đọc →", key=f"read_{article_id}", use_container_width=True):
                        open_detail(article_id)

st.divider()
p1, p2, p3 = st.columns([1, 2, 1])

with p1:
    if st.button("← Trang trước", disabled=cur_page <= 1, use_container_width=True):
        st.session_state["current_page"] = cur_page - 1
        st.rerun()

with p2:
    st.markdown(f'<div class="pager-label">Trang {cur_page} / {total_pages}</div>', unsafe_allow_html=True)

with p3:
    if st.button("Trang sau →", disabled=cur_page >= total_pages, use_container_width=True):
        st.session_state["current_page"] = cur_page + 1
        st.rerun()
