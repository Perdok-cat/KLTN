"""
Streamlit Frontend - Dashboard chính.
Hiển thị góc nhìn tổng quan cho người dùng cuối.
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
    ALL_OPTION,
    DATE_RANGE_LABELS,
    LABEL_ORDER,
    LABEL_VI,
    apply_global_styles,
    article_meta_html,
    compact_number,
    escape_html,
    filter_request_params,
    format_datetime,
    hero_html,
    label_color,
    label_icon,
    label_name,
    metric_card,
    neutral_chip,
    percent_text,
    render_global_filter_bar,
    render_sidebar,
    section_header,
    set_label_filter,
    set_source_filter,
    trim_text,
)


API_URL = os.getenv("API_URL", "http://localhost:5000")

st.set_page_config(
    page_title="Dashboard Tin tức AI",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_global_styles()


@st.cache_data(ttl=60, show_spinner=False)
def fetch_stats(date_range: str, source: str, label: str) -> dict:
    params = {"date_range": date_range}
    if source and source != ALL_OPTION:
        params["source"] = source
    if label and label != ALL_OPTION:
        params["label"] = label
    resp = requests.get(f"{API_URL}/api/stats", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=60, show_spinner=False)
def fetch_articles(limit: int, date_range: str, source: str, label: str) -> dict:
    params = {"limit": limit, "date_range": date_range}
    if source and source != ALL_OPTION:
        params["source"] = source
    if label and label != ALL_OPTION:
        params["label"] = label
    resp = requests.get(f"{API_URL}/api/articles", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=60, show_spinner=False)
def fetch_labels() -> list[str]:
    resp = requests.get(f"{API_URL}/api/labels", timeout=5)
    resp.raise_for_status()
    return resp.json().get("labels", [])


@st.cache_data(ttl=60, show_spinner=False)
def fetch_sources() -> list[str]:
    resp = requests.get(f"{API_URL}/api/sources", timeout=5)
    resp.raise_for_status()
    return resp.json().get("sources", [])


@st.cache_data(ttl=20, show_spinner=False)
def check_api() -> bool:
    try:
        resp = requests.get(f"{API_URL}/api/health", timeout=3)
        return resp.ok
    except Exception:
        return False


def delta_text(delta: dict | None, suffix: str = "") -> tuple[str, str]:
    value = None if not delta else delta.get("value")
    percent = None if not delta else delta.get("percent")
    if value is None:
        return "Chưa có kỳ trước", "neutral"

    value_i = int(value or 0)
    if value_i == 0:
        return "Không đổi so với kỳ trước", "neutral"

    direction = "Tăng" if value_i > 0 else "Giảm"
    tone = "up" if value_i > 0 else "down"
    abs_value = compact_number(abs(value_i))
    if percent is None:
        return f"{direction} {abs_value}{suffix}", tone
    return f"{direction} {abs_value}{suffix} ({abs(float(percent)):.1f}%)", tone


def label_delta(data: dict, label: str) -> tuple[str, str]:
    if not data.get("previous_period_available") or not label:
        return "Chưa có kỳ trước", "neutral"
    current = int((data.get("label_distribution") or {}).get(label, 0) or 0)
    previous = int((data.get("previous_label_distribution") or {}).get(label, 0) or 0)
    diff = current - previous
    if diff == 0:
        return "Không đổi so với kỳ trước", "neutral"
    direction = "Tăng" if diff > 0 else "Giảm"
    tone = "up" if diff > 0 else "down"
    return f"{direction} {compact_number(abs(diff))} bài", tone


api_online = check_api()
render_sidebar("dashboard", API_URL, api_online)

if not api_online:
    st.error("Không thể tải dữ liệu. Vui lòng kiểm tra dịch vụ dữ liệu và thử lại.")
    st.stop()

try:
    labels = fetch_labels()
    sources = fetch_sources()
except Exception:
    labels = []
    sources = []

render_global_filter_bar(labels, sources)
params = filter_request_params()

try:
    data = fetch_stats(
        params.get("date_range", "all"),
        params.get("source", ALL_OPTION),
        params.get("label", ALL_OPTION),
    )
    recent_result = fetch_articles(
        8,
        params.get("date_range", "all"),
        params.get("source", ALL_OPTION),
        params.get("label", ALL_OPTION),
    )
except Exception as exc:
    st.error(f"Không tải được dữ liệu: {exc}")
    st.stop()

label_dist = data.get("label_distribution", {}) or {}
label_colors = data.get("label_colors", {}) or {}
total = int(data.get("total", 0) or 0)
source_count = int(data.get("source_count", 0) or 0)
recent_count = int(data.get("recent_count", 0) or 0)
recent_articles = recent_result.get("articles", []) or []
last_updated = format_datetime(data.get("last_updated")) or "Chưa có dữ liệu"
date_label = DATE_RANGE_LABELS.get(params.get("date_range", "all"), "Tất cả thời gian")

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
    neutral_chip(f"{compact_number(total)} bài viết", "📰", "slate"),
    neutral_chip(date_label, "📅", "blue"),
]
if params.get("source"):
    hero_chips.append(neutral_chip(params["source"], "🌐", "green"))
if params.get("label"):
    hero_chips.append(neutral_chip(label_name(params["label"]), label_icon(params["label"]), "amber"))

st.markdown(
    hero_html(
        "Dashboard Tin tức AI",
        "Theo dõi tin AI mới nhất",
        "Nắm nhanh xu hướng nhãn, nguồn tin và các bài đáng chú ý theo bộ lọc đang chọn.",
        hero_chips,
        meta=f"Cập nhật lần cuối: {last_updated}",
    ),
    unsafe_allow_html=True,
)

cta_cols = st.columns([1, 4])
with cta_cols[0]:
    if st.button("Xem bài mới", use_container_width=True, type="primary"):
        st.switch_page("pages/1_Tin_Tức.py")

total_delta, total_tone = delta_text((data.get("deltas") or {}).get("total"), " bài")
source_delta, source_tone = delta_text((data.get("deltas") or {}).get("source_count"), " nguồn")
recent_delta, recent_tone = delta_text((data.get("deltas") or {}).get("recent_count"), " bài")
top_delta, top_tone = label_delta(data, top_label)

metric_specs = [
    (
        "Tổng bài viết",
        compact_number(total),
        "Số bài phù hợp với bộ lọc hiện tại.",
        "#2563eb",
        "📰",
        total_delta,
        "Đếm tất cả bài viết sau khi áp dụng thời gian, nguồn và nhãn.",
        total_tone,
    ),
    (
        "Nhãn nổi bật",
        label_name(top_label),
        f"{compact_number(top_count)} bài · {top_share}",
        label_color(top_label, label_colors),
        label_icon(top_label),
        top_delta,
        "Nhãn có số bài nhiều nhất trong tập dữ liệu đang lọc.",
        top_tone,
    ),
    (
        "Nguồn đang theo dõi",
        compact_number(source_count),
        "Số nguồn có bài viết trong bộ lọc hiện tại.",
        "#0f766e",
        "🌐",
        source_delta,
        "Đếm số nguồn khác nhau có ít nhất một bài phù hợp.",
        source_tone,
    ),
    (
        "Bài mới trong kỳ",
        compact_number(recent_count),
        f"Số bài trong mốc {date_label.lower()}.",
        "#d97706",
        "⚡",
        recent_delta,
        "Đếm bài theo ngày đăng trong khoảng thời gian đang chọn.",
        recent_tone,
    ),
]

metric_cols = st.columns(4)
for col, spec in zip(metric_cols, metric_specs):
    with col:
        st.markdown(metric_card(*spec), unsafe_allow_html=True)

if top_label:
    filter_cols = st.columns([1, 5])
    with filter_cols[0]:
        if st.button(f"Lọc {label_name(top_label)}", use_container_width=True):
            set_label_filter(top_label)
            st.rerun()

st.markdown(
    section_header(
        "Phân bố nhãn",
        "Tỷ trọng nhãn thay đổi theo thời gian, nguồn và nhãn đang chọn.",
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

if sorted_labels:
    st.markdown("**Lọc nhanh theo nhãn**")
    quick_cols = st.columns(min(4, len(sorted_labels)))
    for idx, (label, _) in enumerate(sorted_labels[:4]):
        with quick_cols[idx % len(quick_cols)]:
            if st.button(f"{label_icon(label)} {label_name(label)}", key=f"label_filter_{label}", use_container_width=True):
                set_label_filter(label)
                st.rerun()

st.markdown(
    section_header(
        "Bài mới và nổi bật",
        "Danh sách bài viết mới nhất theo bộ lọc hiện tại.",
    ),
    unsafe_allow_html=True,
)

if recent_articles:
    st.markdown('<div class="article-list">', unsafe_allow_html=True)
    for idx, article in enumerate(recent_articles):
        article_id = str(article.get("id") or f"article_{idx}")
        preview = trim_text(article.get("summary") or article.get("snippet") or "", 220)
        source = str(article.get("source") or "").strip()
        row_cols = st.columns([5.5, 1.25])
        with row_cols[0]:
            st.markdown(
                f"""
                <div class="article-row">
                    <div>
                        {article_meta_html(article, label_colors)}
                        <div class="article-row__title">{escape_html(article.get("title", "—"))}</div>
                        <div class="article-row__preview">{escape_html(preview or "Không có tóm tắt.")}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with row_cols[1]:
            if st.button("Mở", key=f"open_{article_id}", use_container_width=True, type="primary"):
                st.session_state["_pending_article_id"] = article_id
                st.query_params["article_id"] = article_id
                st.switch_page("pages/1_Tin_Tức.py")
            if source and st.button("Nguồn này", key=f"source_{article_id}", use_container_width=True):
                set_source_filter(source)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
else:
    st.markdown(
        '<div class="empty-state">Chưa có bài viết phù hợp với bộ lọc hiện tại.</div>',
        unsafe_allow_html=True,
    )
