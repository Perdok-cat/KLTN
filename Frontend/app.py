"""
Streamlit Frontend - Dashboard chính.
Hiển thị thống kê tổng quan về bộ dữ liệu tin tức AI.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import plotly.graph_objects as go
import requests
import streamlit as st

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from ui import (  # noqa: E402
    LABEL_ORDER,
    LABEL_VI,
    article_meta_html,
    compact_number,
    escape_html,
    hero_html,
    keyword_chips,
    label_chip,
    label_color,
    label_icon,
    label_name,
    metric_card,
    neutral_chip,
    percent_text,
    render_sidebar,
    section_header,
    trim_text,
    apply_global_styles,
)


API_URL = os.getenv("API_URL", "http://localhost:5000")

st.set_page_config(
    page_title="AI News Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_global_styles()


@st.cache_data(ttl=60, show_spinner=False)
def fetch_stats() -> dict:
    resp = requests.get(f"{API_URL}/api/stats", timeout=10)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=60, show_spinner=False)
def fetch_recent(limit: int = 8) -> dict:
    resp = requests.get(f"{API_URL}/api/articles", params={"limit": limit}, timeout=10)
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
render_sidebar("dashboard", API_URL, api_online)

if not api_online:
    st.error(
        f"Không thể kết nối tới Backend tại **{API_URL}**.\n\n"
        "Chạy Backend trước: `cd Backend && python app.py`"
    )
    st.stop()

try:
    data = fetch_stats()
    recent_result = fetch_recent(limit=7)
except Exception as exc:
    st.error(f"Lỗi khi tải dữ liệu: {exc}")
    st.stop()

label_dist = data.get("label_distribution", {}) or {}
label_colors = data.get("label_colors", {}) or {}
total = int(data.get("total", 0) or 0)
recent_articles = recent_result.get("articles", []) or []

sorted_labels = sorted(
    ((label, int(count or 0)) for label, count in label_dist.items()),
    key=lambda item: item[1],
    reverse=True,
)
ordered_labels = [label for label, _ in sorted_labels] or [
    label for label in LABEL_ORDER if label in label_dist
]
if not ordered_labels:
    ordered_labels = ["Chưa có dữ liệu"]
values_sorted = [int(label_dist.get(label, 0) or 0) for label in ordered_labels]
colors_sorted = [label_color(label, label_colors) for label in ordered_labels] or ["#cbd5e1"]
labels_vi = [f"{label_icon(label)} {LABEL_VI.get(label, label)}" for label in ordered_labels]

top_label, top_count = (sorted_labels[0] if sorted_labels else ("", 0))
top_share = percent_text(top_count, total)

hero_chips = [
    neutral_chip("Backend live", "●", "green"),
    neutral_chip("BigQuery", "▦", "blue"),
    neutral_chip(f"{compact_number(total)} bài đã gắn nhãn", "📰", "slate"),
]
st.markdown(
    hero_html(
        "AI News Pipeline",
        "Bảng điều khiển tin tức AI",
        "Theo dõi phân bố nhãn, bài mới và tín hiệu nổi bật trong kho tin tức AI đã gắn nhãn.",
        hero_chips,
    ),
    unsafe_allow_html=True,
)

metric_specs = [
    (
        "Tổng bài viết",
        compact_number(total),
        "Dữ liệu từ labeled_articles",
        "#2563eb",
        "📰",
    ),
    (
        "Nhãn chủ đạo",
        label_name(top_label),
        f"{compact_number(top_count)} bài · {top_share}",
        label_color(top_label, label_colors),
        label_icon(top_label),
    ),
    (
        "Bài mới hiển thị",
        compact_number(len(recent_articles)),
        "Dòng bài gần nhất theo labeled_at",
        "#0f766e",
        "⚡",
    ),
    (
        "Nguồn ghép nối",
        "2 bảng",
        "labeled_articles + summarized_articles",
        "#475569",
        "▦",
    ),
]

metric_cols = st.columns(4)
for col, spec in zip(metric_cols, metric_specs):
    with col:
        st.markdown(metric_card(*spec), unsafe_allow_html=True)

st.markdown(
    section_header(
        "Phân bố nhãn",
        "Tỷ trọng nhãn giúp nhìn nhanh bộ dữ liệu đang thiên về tín hiệu, ứng dụng, phân tích sâu hay nhiễu.",
    ),
    unsafe_allow_html=True,
)

chart_left, chart_right = st.columns([1, 1.15])

with chart_left:
    fig_donut = go.Figure(
        go.Pie(
            labels=labels_vi,
            values=values_sorted,
            marker=dict(colors=colors_sorted, line=dict(color="#ffffff", width=3)),
            hole=0.58,
            sort=False,
            textinfo="percent",
            hovertemplate="<b>%{label}</b><br>Số bài: %{value}<br>Tỷ lệ: %{percent}<extra></extra>",
        )
    )
    fig_donut.add_annotation(
        text=f"<b>{compact_number(total)}</b><br><span style='font-size:12px'>bài viết</span>",
        showarrow=False,
        font=dict(size=22, color="#0f172a"),
    )
    fig_donut.update_layout(
        height=365,
        margin=dict(t=16, b=16, l=16, r=16),
        showlegend=True,
        legend=dict(orientation="h", y=-0.12, x=0, font=dict(size=12)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#0f172a"),
    )
    st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})

with chart_right:
    fig_bar = go.Figure(
        go.Bar(
            x=values_sorted,
            y=labels_vi,
            orientation="h",
            marker=dict(color=colors_sorted, line=dict(color="#ffffff", width=1)),
            text=[compact_number(value) for value in values_sorted],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Số bài: %{x}<extra></extra>",
        )
    )
    fig_bar.update_layout(
        height=365,
        margin=dict(t=18, b=30, l=12, r=42),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#0f172a"),
        xaxis=dict(showgrid=True, gridcolor="rgba(148,163,184,.22)", title="Số bài"),
        yaxis=dict(autorange="reversed", title=""),
    )
    st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

st.markdown(
    section_header(
        "Bài mới nổi bật",
        "Mở nhanh bài mới nhất hoặc chuyển sang trang Tin tức để lọc sâu hơn.",
    ),
    unsafe_allow_html=True,
)

if recent_articles:
    featured = recent_articles[0]
    featured_preview = featured.get("summary") or featured.get("snippet") or ""
    with st.container(border=True):
        content_col, action_col = st.columns([5.4, 1])
        with content_col:
            st.markdown(article_meta_html(featured, label_colors), unsafe_allow_html=True)
            st.markdown(
                f'<div class="feature-title">{escape_html(featured.get("title", "—"))}</div>',
                unsafe_allow_html=True,
            )
            if featured_preview:
                st.markdown(
                    f'<div class="article-preview">{escape_html(trim_text(featured_preview, 420))}</div>',
                    unsafe_allow_html=True,
                )
            if featured.get("keywords"):
                st.markdown(keyword_chips(featured["keywords"]), unsafe_allow_html=True)
        with action_col:
            if st.button("Đọc →", key=f"feature_{featured.get('id')}", use_container_width=True, type="primary"):
                st.session_state["_pending_article_id"] = str(featured.get("id") or "")
                st.query_params["article_id"] = str(featured["id"])
                st.switch_page("pages/1_Tin_Tức.py")

    if len(recent_articles) > 1:
        st.markdown(
            section_header("Luồng bài gần đây", "Các bài vừa được đưa vào kho phân loại."),
            unsafe_allow_html=True,
        )
        recent_rows = recent_articles[1:]

        for row_start in range(0, len(recent_rows), 2):
            row_articles = recent_rows[row_start:row_start + 2]
            row_cols = st.columns(2)
            for col, article in zip(row_cols, row_articles):
                article_id = str(article.get("id") or f"recent_{row_start}")
                preview = article.get("summary") or article.get("snippet") or ""
                keywords_html = (
                    keyword_chips(article["keywords"], limit=5)
                    if article.get("keywords")
                    else '<div class="keywords keywords--empty"></div>'
                )
                with col:
                    with st.container(border=True):
                        st.markdown(
                            f"""
                            <div class="recent-card__body">
                                {article_meta_html(article, label_colors)}
                                <div class="recent-card__title">{escape_html(article.get("title", "—"))}</div>
                                <div class="recent-card__preview">{escape_html(trim_text(preview, 190))}</div>
                                <div class="recent-card__keywords">{keywords_html}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if st.button("Mở chi tiết", key=f"recent_{article_id}", use_container_width=True):
                            st.session_state["_pending_article_id"] = article_id
                            st.query_params["article_id"] = article_id
                            st.switch_page("pages/1_Tin_Tức.py")
else:
    st.markdown(
        '<div class="empty-state">Chưa có bài viết nào để hiển thị.</div>',
        unsafe_allow_html=True,
    )

st.divider()
st.caption("AI News Pipeline · KLTN 2026")
