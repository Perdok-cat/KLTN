"""Shared UI helpers for the Streamlit frontend."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape
from typing import Iterable, Mapping

import streamlit as st


ALL_OPTION = "Tất cả"
DATE_RANGE_OPTIONS = ["all", "7d", "30d", "90d"]
DATE_RANGE_LABELS = {
    "all": "Tất cả thời gian",
    "7d": "7 ngày qua",
    "30d": "30 ngày qua",
    "90d": "90 ngày qua",
}

LABEL_ORDER = ["MARKET SIGNALS", "SOLUTIONS & USE CASES", "DEEP DIVE", "NOISE"]

LABEL_VI = {
    "MARKET SIGNALS": "Tín hiệu thị trường",
    "SOLUTIONS & USE CASES": "Giải pháp & Ứng dụng",
    "DEEP DIVE": "Phân tích chuyên sâu",
    "NOISE": "Nhiễu",
}

LABEL_ICONS = {
    "MARKET SIGNALS": "📈",
    "SOLUTIONS & USE CASES": "🛠️",
    "DEEP DIVE": "🔬",
    "NOISE": "🔇",
}

LABEL_COLORS = {
    "MARKET SIGNALS": "#ef4444",
    "SOLUTIONS & USE CASES": "#16a34a",
    "DEEP DIVE": "#2563eb",
    "NOISE": "#64748b",
}

CONFIDENCE_META = {
    "high": ("Cao", "#16a34a", "●"),
    "medium": ("Trung bình", "#d97706", "●"),
    "low": ("Thấp", "#dc2626", "●"),
}

DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %B %Y %H:%M:%S %z",
    "%a, %d %b %Y",
    "%a, %d %B %Y",
)


def apply_global_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ai-bg: #f6f8fb;
            --ai-panel: #ffffff;
            --ai-panel-soft: #f8fafc;
            --ai-text: #0f172a;
            --ai-muted: #64748b;
            --ai-line: #d9e2ef;
            --ai-line-soft: #e7edf6;
            --ai-accent: #2563eb;
            --ai-accent-soft: #dbeafe;
            --ai-success: #16a34a;
            --ai-warning: #d97706;
            --ai-danger: #dc2626;
            --ai-shadow: 0 14px 34px rgba(15, 23, 42, 0.08);
            --ai-radius: 18px;
        }

        #MainMenu, footer { visibility: hidden; }

        .stApp {
            background: var(--ai-bg);
            color: var(--ai-text);
        }

        header[data-testid="stHeader"] {
            background: rgba(246, 248, 251, 0.86);
            backdrop-filter: blur(14px);
            border-bottom: 1px solid rgba(217, 226, 239, 0.72);
        }

        .block-container {
            max-width: 1520px;
            padding: 2.2rem 2.6rem 3.2rem;
        }

        [data-testid="stSidebar"] {
            background: #edf3f8;
            border-right: 1px solid #d8e2ee;
        }

        [data-testid="stSidebar"] .block-container {
            padding: 1.35rem 0.95rem 2rem;
        }

        [data-testid="stSidebar"] hr,
        .main hr {
            border-color: rgba(148, 163, 184, 0.28);
        }

        h1, h2, h3, p, label, span, div {
            letter-spacing: 0;
        }

        h1 {
            color: var(--ai-text);
            font-weight: 850;
            line-height: 1.08;
        }

        h2, h3 {
            color: var(--ai-text);
            font-weight: 780;
        }

        .sidebar-brand {
            display: flex;
            gap: 0.78rem;
            align-items: center;
            padding: 0.1rem 0.15rem 1rem;
        }

        .sidebar-brand__mark {
            display: grid;
            place-items: center;
            width: 44px;
            height: 44px;
            flex: 0 0 44px;
            border-radius: 14px;
            background: #0f172a;
            color: #fff;
            font-size: 1.34rem;
            box-shadow: 0 10px 22px rgba(15, 23, 42, 0.18);
        }

        .sidebar-brand__title {
            color: #0f172a;
            font-size: 1.02rem;
            font-weight: 850;
            line-height: 1.15;
        }

        .sidebar-brand__caption {
            color: #64748b;
            font-size: 0.78rem;
            line-height: 1.32;
            margin-top: 0.18rem;
        }

        .sidebar-status {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-top: 0.8rem;
            padding: 0.72rem 0.78rem;
            border: 1px solid #d8e2ee;
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.72);
            color: #334155;
            font-size: 0.82rem;
            font-weight: 720;
        }

        .sidebar-status__dot {
            width: 0.62rem;
            height: 0.62rem;
            border-radius: 999px;
            background: var(--status-color);
            box-shadow: 0 0 0 4px var(--status-soft);
        }

        .sidebar-section-title {
            color: #0f172a;
            font-size: 0.92rem;
            font-weight: 820;
            margin: 0.2rem 0 0.75rem;
        }

        div[data-testid="stPageLink"] a {
            min-height: 2.45rem;
            border-radius: 12px;
            padding: 0.35rem 0.55rem;
            font-weight: 700;
        }

        div[data-testid="stPageLink"] a:hover {
            background: #ffffff;
            color: var(--ai-accent);
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid rgba(148, 163, 184, 0.30);
            border-radius: var(--ai-radius);
            background: var(--ai-panel);
            box-shadow: 0 10px 26px rgba(15, 23, 42, 0.055);
            transition: border-color 150ms ease, box-shadow 150ms ease, transform 150ms ease;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            border-color: rgba(37, 99, 235, 0.28);
            box-shadow: var(--ai-shadow);
            transform: translateY(-1px);
        }

        div[data-testid="stButton"] button,
        div[data-testid="stLinkButton"] a {
            border-radius: 12px;
            border: 1px solid #cbd5e1;
            background: #ffffff;
            color: #0f172a;
            font-weight: 760;
            box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
            min-height: 2.45rem;
        }

        div[data-testid="stButton"] button:hover,
        div[data-testid="stLinkButton"] a:hover {
            border-color: var(--ai-accent);
            color: #1d4ed8;
            background: #eff6ff;
        }

        div[data-testid="stButton"] button[kind="primary"],
        div[data-testid="stLinkButton"] a[kind="primary"] {
            background: #2563eb;
            border-color: #2563eb;
            color: #ffffff;
        }

        div[data-testid="stButton"] button[kind="primary"]:hover,
        div[data-testid="stLinkButton"] a[kind="primary"]:hover {
            background: #1d4ed8;
            border-color: #1d4ed8;
            color: #ffffff;
        }

        div[data-testid="stTextInput"] input,
        div[data-baseweb="select"] > div {
            border-radius: 12px;
            border-color: #cbd5e1;
            background: #ffffff;
        }

        div[data-testid="stSlider"] [data-baseweb="slider"] > div {
            color: #2563eb;
        }

        .hero-band {
            width: 100%;
            min-height: 220px;
            max-height: 260px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: 1.25rem 1.55rem;
            margin: 0 0 1.35rem;
            border: 1px solid #1f2a44;
            border-radius: 18px;
            background: #101827;
            color: #ffffff;
            overflow: hidden;
        }

        .hero-band h1 {
            color: #ffffff;
            font-size: clamp(1.75rem, 2.35vw, 2.35rem);
            margin: 0.08rem 0 0.48rem;
        }

        .hero-band p {
            color: #cbd5e1;
            max-width: 860px;
            margin: 0;
            font-size: 0.98rem;
            line-height: 1.48;
        }

        .page-kicker {
            color: #bfdbfe;
            font-size: 0.78rem;
            font-weight: 820;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .hero-meta {
            margin-top: 0.72rem;
            color: #dbeafe;
            font-size: 0.84rem;
            font-weight: 720;
        }

        .hero-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 0.86rem;
        }

        .filter-panel {
            padding: 1rem 1.08rem 1.1rem;
            margin: 0 0 1.1rem;
            border: 1px solid var(--ai-line-soft);
            border-radius: var(--ai-radius);
            background: #ffffff;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.055);
        }

        .filter-panel__title {
            margin-bottom: 0.72rem;
            color: #0f172a;
            font-size: 0.95rem;
            font-weight: 820;
        }

        .filter-panel .stSelectbox label {
            color: #475569;
            font-size: 0.78rem;
            font-weight: 760;
        }

        .section-head {
            margin: 1.2rem 0 0.85rem;
        }

        .section-head h2 {
            margin: 0;
            font-size: 1.2rem;
        }

        .section-head p {
            margin: 0.28rem 0 0;
            color: var(--ai-muted);
            line-height: 1.5;
        }

        .metric-card {
            position: relative;
            min-height: 152px;
            overflow: hidden;
            padding: 1.08rem 1.12rem 1rem;
            border: 1px solid var(--ai-line-soft);
            border-radius: var(--ai-radius);
            background: #ffffff;
            box-shadow: 0 12px 26px rgba(15, 23, 42, 0.06);
        }

        .metric-card:before {
            content: "";
            position: absolute;
            inset: 0 auto 0 0;
            width: 5px;
            background: var(--accent);
        }

        .metric-card__top {
            display: flex;
            align-items: center;
            gap: 0.62rem;
            color: #475569;
            font-size: 0.82rem;
            font-weight: 760;
        }

        .metric-card__icon {
            display: inline-grid;
            place-items: center;
            width: 2rem;
            height: 2rem;
            border-radius: 11px;
            background: var(--accent-soft);
            color: var(--accent);
            font-size: 1rem;
        }

        .metric-card__value {
            margin-top: 0.68rem;
            color: #0f172a;
            font-size: clamp(1.65rem, 2.4vw, 2.25rem);
            font-weight: 880;
            line-height: 1;
        }

        .metric-card__detail {
            margin-top: 0.52rem;
            color: #64748b;
            font-size: 0.82rem;
            line-height: 1.42;
        }

        .metric-card__delta {
            display: inline-flex;
            align-items: center;
            margin-top: 0.62rem;
            padding: 0.28rem 0.48rem;
            border-radius: 999px;
            background: var(--delta-bg);
            color: var(--delta-color);
            font-size: 0.76rem;
            font-weight: 780;
        }

        .ai-chip,
        .keyword-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.34rem;
            max-width: 100%;
            border-radius: 999px;
            white-space: nowrap;
            line-height: 1;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .ai-chip {
            padding: 0.42rem 0.62rem;
            border: 1px solid var(--chip-border);
            background: var(--chip-bg);
            color: var(--chip-color);
            font-size: 0.76rem;
            font-weight: 780;
        }

        .keyword-chip {
            padding: 0.32rem 0.52rem;
            border: 1px solid #e2e8f0;
            background: #f8fafc;
            color: #166534;
            font-size: 0.72rem;
            font-weight: 720;
        }

        .meta-row,
        .keywords {
            display: flex;
            flex-wrap: wrap;
            gap: 0.44rem;
            align-items: center;
            min-width: 0;
        }

        .keywords {
            margin-top: 0.72rem;
        }

        .article-title,
        .feature-title {
            margin-top: 0.7rem;
            color: #0f172a;
            font-weight: 820;
            line-height: 1.35;
            overflow-wrap: anywhere;
        }

        .article-title {
            font-size: 1.04rem;
        }

        .recent-card__body {
            min-height: 14rem;
        }

        .recent-card__title {
            margin-top: 0.72rem;
            color: #0f172a;
            font-size: 1.04rem;
            font-weight: 820;
            line-height: 1.35;
            min-height: 2.7em;
            overflow: hidden;
            overflow-wrap: anywhere;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
        }

        .recent-card__preview {
            margin-top: 0.62rem;
            color: #475569;
            font-size: 0.92rem;
            line-height: 1.62;
            min-height: 4.86em;
            overflow: hidden;
            overflow-wrap: anywhere;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
        }

        .recent-card__keywords {
            min-height: 2.3rem;
            max-height: 2.3rem;
            margin-top: 0.72rem;
            overflow: hidden;
        }

        .recent-card__keywords .keywords {
            margin-top: 0;
            flex-wrap: nowrap;
        }

        .article-list {
            display: grid;
            gap: 0.75rem;
        }

        .article-row {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: 1rem;
            align-items: center;
            padding: 0.95rem 1rem;
            border: 1px solid rgba(148, 163, 184, 0.28);
            border-radius: 14px;
            background: #ffffff;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.045);
        }

        .article-row__title {
            margin-top: 0.54rem;
            color: #0f172a;
            font-size: 1.01rem;
            font-weight: 820;
            line-height: 1.35;
            overflow-wrap: anywhere;
        }

        .article-row__preview {
            margin-top: 0.36rem;
            color: #475569;
            font-size: 0.89rem;
            line-height: 1.5;
            overflow-wrap: anywhere;
        }

        .article-row__action {
            min-width: 116px;
        }

        .feature-title {
            font-size: clamp(1.25rem, 2vw, 1.7rem);
        }

        .article-preview {
            margin-top: 0.62rem;
            color: #475569;
            font-size: 0.92rem;
            line-height: 1.62;
            overflow-wrap: anywhere;
        }

        .reader-body {
            color: #1e293b;
            font-size: 1rem;
            line-height: 1.8;
            overflow-wrap: anywhere;
        }

        .detail-title {
            color: #0f172a;
            font-size: clamp(1.75rem, 3vw, 2.7rem);
            line-height: 1.12;
            font-weight: 860;
            margin: 0.2rem 0 0.85rem;
        }

        .info-row {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 0.8rem;
            padding: 0.62rem 0;
            border-bottom: 1px solid #e2e8f0;
            color: #475569;
            font-size: 0.87rem;
            min-width: 0;
        }

        .info-row:last-child {
            border-bottom: 0;
        }

        .info-row b {
            color: #0f172a;
            max-width: 68%;
            text-align: right;
            line-height: 1.42;
            overflow-wrap: anywhere;
        }

        .detail-rail {
            position: sticky;
            top: 5.2rem;
            padding: 1rem;
            border: 1px solid rgba(148, 163, 184, 0.30);
            border-radius: var(--ai-radius);
            background: #ffffff;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.07);
        }

        .detail-rail__section + .detail-rail__section {
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid #e2e8f0;
        }

        .detail-rail__title {
            margin: 0 0 0.65rem;
            color: #0f172a;
            font-size: 0.94rem;
            font-weight: 820;
            line-height: 1.3;
        }

        .detail-rail__chips {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-bottom: 0.35rem;
        }

        .detail-link {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            min-height: 2.55rem;
            margin-top: 0.85rem;
            border: 1px solid #2563eb;
            border-radius: 12px;
            background: #2563eb;
            color: #ffffff;
            font-weight: 780;
            text-decoration: none;
            box-shadow: 0 10px 20px rgba(37, 99, 235, 0.18);
        }

        .detail-link:hover {
            background: #1d4ed8;
            border-color: #1d4ed8;
            color: #ffffff;
        }

        .pager-label {
            min-height: 2.45rem;
            display: grid;
            place-items: center;
            color: #475569;
            font-weight: 760;
        }

        .empty-state {
            padding: 2rem;
            border: 1px dashed #cbd5e1;
            border-radius: 18px;
            background: #ffffff;
            color: #475569;
            text-align: center;
        }

        @media (max-width: 760px) {
            .block-container {
                padding: 1.35rem 1rem 2rem;
            }

            .hero-band {
                min-height: auto;
                max-height: none;
                padding: 1.2rem;
            }

            .hero-band h1 {
                font-size: 2rem;
            }

            .article-row {
                grid-template-columns: 1fr;
            }

            .article-row__action {
                min-width: 0;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(active_page: str, api_url: str = "", api_online: bool | None = None) -> None:
    active_label = "Dashboard" if active_page == "dashboard" else "Tin tức"

    with st.sidebar:
        st.markdown(
            f"""
            <div class="sidebar-brand">
                <div class="sidebar-brand__mark">AI</div>
                <div>
                    <div class="sidebar-brand__title">Tin tức AI</div>
                    <div class="sidebar-brand__caption">Theo dõi chủ đề và bài viết mới</div>
                </div>
            </div>
            <div class="ai-chip" style="--chip-bg:#ffffff;--chip-color:#334155;--chip-border:#d8e2ee;">
                Đang mở · {escape_html(active_label)}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()
        st.page_link("app.py", label="Dashboard", icon="📊")
        st.page_link("pages/1_Tin_Tức.py", label="Tin tức", icon="📰")


def escape_html(value: object) -> str:
    return escape(str(value or ""), quote=True)


def css_color(value: str | None, fallback: str = "#64748b") -> str:
    raw = str(value or "").strip()
    if re.match(r"^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$", raw):
        return raw
    return fallback


def compact_number(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def percent_text(part: object, total: object) -> str:
    try:
        part_i = int(part)
        total_i = int(total)
        if total_i <= 0:
            return "0.0%"
        return f"{part_i / total_i * 100:.1f}%"
    except (TypeError, ValueError, ZeroDivisionError):
        return "0.0%"


def trim_text(value: object, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(".,;: ")
    return f"{cut}..."


def format_date(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    normalized = raw.replace("Z", "+00:00")
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(normalized, fmt)
            return parsed.strftime("%d/%m/%Y")
        except ValueError:
            continue

    return raw[:32]


def format_datetime(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    normalized = raw.replace("Z", "+00:00")
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(normalized, fmt)
            return parsed.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            continue

    return raw[:32]


def normalize_option(value: object) -> str:
    raw = str(value or "").strip()
    return "" if raw in {"", ALL_OPTION, "all"} else raw


def init_global_filters() -> None:
    st.session_state.setdefault("global_date_range", "all")
    st.session_state.setdefault("global_source", ALL_OPTION)
    st.session_state.setdefault("global_label", ALL_OPTION)
    pending_label = st.session_state.pop("_pending_global_label", None)
    pending_source = st.session_state.pop("_pending_global_source", None)
    if pending_label is not None:
        st.session_state["global_label"] = pending_label or ALL_OPTION
    if pending_source is not None:
        st.session_state["global_source"] = pending_source or ALL_OPTION


def filter_request_params() -> dict[str, str]:
    init_global_filters()
    params: dict[str, str] = {"date_range": str(st.session_state["global_date_range"])}
    source = normalize_option(st.session_state["global_source"])
    label = normalize_option(st.session_state["global_label"])
    if source:
        params["source"] = source
    if label:
        params["label"] = label
    return params


def render_global_filter_bar(labels: list[str], sources: list[str]) -> None:
    init_global_filters()

    label_options = [ALL_OPTION] + [label for label in labels if label]
    source_options = [ALL_OPTION] + [source for source in sources if source]

    if st.session_state["global_label"] not in label_options:
        st.session_state["global_label"] = ALL_OPTION
    if st.session_state["global_source"] not in source_options:
        st.session_state["global_source"] = ALL_OPTION
    if st.session_state["global_date_range"] not in DATE_RANGE_OPTIONS:
        st.session_state["global_date_range"] = "all"

    st.markdown('<div class="filter-panel"><div class="filter-panel__title">Bộ lọc chung</div>', unsafe_allow_html=True)
    cols = st.columns([1, 1, 1])
    with cols[0]:
        st.selectbox(
            "Thời gian",
            options=DATE_RANGE_OPTIONS,
            key="global_date_range",
            format_func=lambda value: DATE_RANGE_LABELS.get(value, value),
        )
    with cols[1]:
        st.selectbox(
            "Nguồn",
            options=source_options,
            key="global_source",
            format_func=lambda value: "Tất cả nguồn" if value == ALL_OPTION else value,
        )
    with cols[2]:
        st.selectbox(
            "Nhãn",
            options=label_options,
            key="global_label",
            format_func=lambda value: "Tất cả nhãn" if value == ALL_OPTION else f"{label_icon(value)} {label_name(value)}",
        )
    st.markdown("</div>", unsafe_allow_html=True)


def set_label_filter(label: str) -> None:
    st.session_state["_pending_global_label"] = label or ALL_OPTION


def label_name(label: str) -> str:
    if not label:
        return "Chưa phân loại"
    return LABEL_VI.get(label, label)


def label_color(label: str, colors: Mapping[str, str] | None = None) -> str:
    merged = {**LABEL_COLORS, **(colors or {})}
    return css_color(merged.get(label), "#64748b")


def label_icon(label: str) -> str:
    return LABEL_ICONS.get(label, "•")


def label_chip(label: str, colors: Mapping[str, str] | None = None) -> str:
    color = label_color(label, colors)
    text = f"{label_icon(label)} {label_name(label)}"
    return (
        f'<span class="ai-chip" style="--chip-bg:{color};'
        f'--chip-color:#fff;--chip-border:{color};">{escape_html(text)}</span>'
    )


def neutral_chip(text: object, icon: str = "", tone: str = "slate") -> str:
    tones = {
        "blue": ("#eff6ff", "#1d4ed8", "#bfdbfe"),
        "green": ("#ecfdf5", "#047857", "#bbf7d0"),
        "amber": ("#fffbeb", "#b45309", "#fde68a"),
        "red": ("#fef2f2", "#b91c1c", "#fecaca"),
        "slate": ("#f8fafc", "#334155", "#dbe3ef"),
    }
    bg, color, border = tones.get(tone, tones["slate"])
    value = f"{icon} {text}".strip()
    return (
        f'<span class="ai-chip" style="--chip-bg:{bg};'
        f'--chip-color:{color};--chip-border:{border};">{escape_html(value)}</span>'
    )


def confidence_chip(confidence: str) -> str:
    key = str(confidence or "").strip().lower()
    label, color, icon = CONFIDENCE_META.get(key, ("Không rõ", "#64748b", "●"))
    return neutral_chip(f"{icon} Tin cậy {label}", tone="green" if key == "high" else "amber" if key == "medium" else "red" if key == "low" else "slate")


def keyword_chips(keywords: str | Iterable[str], limit: int = 8) -> str:
    if isinstance(keywords, str):
        raw_items = re.split(r"[,;]", keywords)
    else:
        raw_items = list(keywords or [])

    items = [str(item).strip() for item in raw_items if str(item).strip()]
    if not items:
        return ""

    chips = [
        f'<span class="keyword-chip">{escape_html(item)}</span>'
        for item in items[:limit]
    ]
    hidden = len(items) - limit
    if hidden > 0:
        chips.append(f'<span class="keyword-chip">+{hidden}</span>')
    return f'<div class="keywords">{"".join(chips)}</div>'


def article_meta_html(article: Mapping[str, object], colors: Mapping[str, str] | None = None) -> str:
    chips = [label_chip(str(article.get("label") or ""), colors)]
    confidence = str(article.get("confidence") or "").strip()
    if confidence:
        chips.append(confidence_chip(confidence))

    source = str(article.get("source") or "").strip()
    if source:
        chips.append(neutral_chip(source, "🌐", "slate"))

    pub_date = format_date(article.get("pub_date"))
    if pub_date:
        chips.append(neutral_chip(pub_date, "📅", "slate"))

    return f'<div class="meta-row">{"".join(chips)}</div>'


def metric_card(
    title: str,
    value: str,
    detail: str,
    color: str,
    icon: str,
    delta: str = "",
    tooltip: str = "",
    delta_tone: str = "neutral",
) -> str:
    safe_color = css_color(color, "#2563eb")
    delta_colors = {
        "up": ("#ecfdf5", "#047857"),
        "down": ("#fef2f2", "#b91c1c"),
        "neutral": ("#f8fafc", "#475569"),
    }
    delta_bg, delta_color = delta_colors.get(delta_tone, delta_colors["neutral"])
    delta_html = (
        f'<div class="metric-card__delta" style="--delta-bg:{delta_bg};--delta-color:{delta_color};">{escape_html(delta)}</div>'
        if delta
        else ""
    )
    tooltip_attr = f' title="{escape_html(tooltip)}"' if tooltip else ""
    return f"""
    <div class="metric-card" style="--accent:{safe_color};--accent-soft:{safe_color}18;"{tooltip_attr}>
        <div class="metric-card__top">
            <span class="metric-card__icon">{escape_html(icon)}</span>
            <span>{escape_html(title)}</span>
        </div>
        <div class="metric-card__value">{escape_html(value)}</div>
        <div class="metric-card__detail">{escape_html(detail)}</div>
        {delta_html}
    </div>
    """


def section_header(title: str, subtitle: str = "") -> str:
    desc = f"<p>{escape_html(subtitle)}</p>" if subtitle else ""
    return f"""
    <div class="section-head">
        <h2>{escape_html(title)}</h2>
        {desc}
    </div>
    """


def hero_html(kicker: str, title: str, subtitle: str, chips: Iterable[str] = (), meta: str = "") -> str:
    chip_html = "".join(chips)
    chip_block = f'<div class="hero-chips">{chip_html}</div>' if chip_html else ""
    meta_block = f'<div class="hero-meta">{escape_html(meta)}</div>' if meta else ""
    return (
        '<div class="hero-band">'
        f'<div class="page-kicker">{escape_html(kicker)}</div>'
        f'<h1>{escape_html(title)}</h1>'
        f'<p>{escape_html(subtitle)}</p>'
        f'{meta_block}'
        f'{chip_block}'
        '</div>'
    )
