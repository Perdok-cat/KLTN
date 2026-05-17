from __future__ import annotations

import os
from datetime import datetime
from html import escape

import plotly.graph_objects as go
import requests
import streamlit as st

from utils.gcp_auth import auth_headers

MV_API_URL = os.getenv("MV_API_URL", "http://localhost:5001")

st.set_page_config(
    page_title="ModelVision",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --mv-bg: #f6f8fb;
            --mv-panel: #ffffff;
            --mv-line: #dbe4ee;
            --mv-text: #111827;
            --mv-muted: #64748b;
            --mv-primary: #2563eb;
            --mv-success: #16a34a;
            --mv-warning: #d97706;
            --mv-danger: #dc2626;
            --mv-teal: #0f766e;
        }

        .stApp {
            background: linear-gradient(180deg, #f9fbfd 0%, var(--mv-bg) 36%, #eef3f8 100%);
            color: var(--mv-text);
        }

        header[data-testid="stHeader"] {
            background: rgba(246, 248, 251, 0.78);
            border-bottom: 1px solid rgba(219, 228, 238, 0.85);
            backdrop-filter: blur(12px);
        }

        .block-container {
            max-width: 1500px;
            padding: 1.45rem 2rem 3rem;
        }

        [data-testid="stSidebar"] {
            background: #eef3f8;
            border-right: 1px solid #d8e2ed;
        }

        div[data-testid="stPageLink"] a {
            min-height: 2.45rem;
            border-radius: 8px;
            padding: 0.35rem 0.55rem;
            font-weight: 680;
        }

        div[data-testid="stPageLink"] a:hover {
            background: rgba(255, 255, 255, 0.9);
            color: var(--mv-primary);
        }

        .mv-hero {
            padding: 1.25rem 1.35rem;
            border-radius: 8px;
            border: 1px solid var(--mv-line);
            background: linear-gradient(135deg, #ffffff 0%, #f5f8fc 58%, #eef6f4 100%);
            margin-bottom: 1rem;
        }

        .mv-eyebrow {
            color: var(--mv-muted);
            font-size: 0.78rem;
            font-weight: 760;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .mv-title {
            margin: 0.36rem 0 0.35rem;
            color: var(--mv-text);
            font-size: clamp(2rem, 3.2vw, 3rem);
            font-weight: 840;
            line-height: 1.08;
        }

        .mv-subtitle {
            margin: 0;
            color: var(--mv-muted);
            max-width: 820px;
            line-height: 1.55;
        }

        .mv-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 1rem;
        }

        .mv-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.38rem;
            padding: 0.42rem 0.62rem;
            border-radius: 8px;
            border: 1px solid var(--mv-line);
            background: #ffffff;
            color: var(--mv-muted);
            font-size: 0.84rem;
            font-weight: 680;
        }

        .mv-chip b {
            color: var(--mv-text);
        }

        .mv-kpi {
            height: 168px;
            padding: 0.95rem 1rem;
            border-radius: 8px;
            border: 1px solid var(--mv-line);
            border-top: 4px solid var(--accent);
            background: var(--mv-panel);
            display: flex;
            flex-direction: column;
        }

        .mv-kpi__label {
            color: var(--mv-muted);
            font-size: 0.84rem;
            font-weight: 720;
        }

        .mv-kpi__value {
            margin-top: 0.45rem;
            color: var(--mv-text);
            font-size: 1.86rem;
            font-weight: 840;
            line-height: 1.05;
        }

        .mv-kpi__meta {
            margin-top: auto;
            padding-top: 0.75rem;
            color: var(--mv-muted);
            font-size: 0.82rem;
            line-height: 1.45;
        }

        .mv-section-title {
            margin: 0.25rem 0 0.1rem;
            color: var(--mv-text);
            font-size: 1.12rem;
            font-weight: 800;
        }

        .mv-section-caption {
            margin: 0 0 0.65rem;
            color: var(--mv-muted);
            font-size: 0.88rem;
        }

        .mv-panel {
            padding: 0.95rem 1rem;
            border-radius: 8px;
            border: 1px solid var(--mv-line);
            background: rgba(255, 255, 255, 0.92);
        }

        .mv-action {
            display: grid;
            grid-template-columns: 118px 1fr;
            gap: 0.85rem;
            align-items: start;
            padding: 0.72rem 0;
            border-bottom: 1px solid #eef2f7;
        }

        .mv-action:last-child {
            border-bottom: 0;
        }

        .mv-badge {
            display: inline-flex;
            width: fit-content;
            padding: 0.24rem 0.5rem;
            border-radius: 999px;
            font-size: 0.74rem;
            font-weight: 780;
            border: 1px solid transparent;
        }

        .mv-badge--ok {
            color: var(--mv-success);
            background: rgba(22, 163, 74, 0.1);
            border-color: rgba(22, 163, 74, 0.2);
        }

        .mv-badge--warn {
            color: var(--mv-warning);
            background: rgba(217, 119, 6, 0.1);
            border-color: rgba(217, 119, 6, 0.2);
        }

        .mv-badge--bad {
            color: var(--mv-danger);
            background: rgba(220, 38, 38, 0.1);
            border-color: rgba(220, 38, 38, 0.2);
        }

        .mv-action__title {
            color: var(--mv-text);
            font-weight: 760;
            line-height: 1.35;
        }

        .mv-action__meta {
            margin-top: 0.18rem;
            color: var(--mv-muted);
            font-size: 0.82rem;
            line-height: 1.45;
        }

        @media (max-width: 900px) {
            .block-container {
                padding: 1rem 0.85rem 2rem;
            }

            .mv-kpi {
                height: auto;
                min-height: 148px;
            }

            .mv-action {
                grid-template-columns: 1fr;
                gap: 0.35rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def fmt_int(value: object, fallback: str = "—") -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return fallback


def fmt_pct(value: object, digits: int = 1, fallback: str = "—") -> str:
    try:
        return f"{float(value):.{digits}%}"
    except (TypeError, ValueError):
        return fallback


def fmt_delta(value: object, fallback: str = "—") -> str:
    try:
        return f"{float(value):+.1f} điểm %"
    except (TypeError, ValueError):
        return fallback


def short_text(value: object, limit: int = 64) -> str:
    text = str(value or "—")
    return text if len(text) <= limit else f"{text[:limit]}..."


def chip(label: str, value: str) -> str:
    return f'<div class="mv-chip"><span>{escape(label)}:</span><b>{escape(value)}</b></div>'


def kpi_card(label: str, value: str, meta: str, accent: str) -> str:
    return (
        f'<div class="mv-kpi" style="--accent:{accent}">'
        f'<div class="mv-kpi__label">{escape(label)}</div>'
        f'<div class="mv-kpi__value">{escape(value)}</div>'
        f'<div class="mv-kpi__meta">{escape(meta)}</div>'
        "</div>"
    )


def section_header(title: str, caption: str) -> str:
    return (
        f'<div class="mv-section-title">{escape(title)}</div>'
        f'<div class="mv-section-caption">{escape(caption)}</div>'
    )


def action_row(tone: str, status: str, title: str, meta: str) -> str:
    return (
        '<div class="mv-action">'
        f'<div><span class="mv-badge mv-badge--{escape(tone)}">{escape(status)}</span></div>'
        "<div>"
        f'<div class="mv-action__title">{escape(title)}</div>'
        f'<div class="mv-action__meta">{escape(meta)}</div>'
        "</div>"
        "</div>"
    )


def fetch_health() -> tuple[bool, str]:
    try:
        response = requests.get(f"{MV_API_URL}/api/health", headers=auth_headers(), timeout=3)
        return response.ok, "Backend kết nối" if response.ok else "Backend lỗi"
    except Exception:
        return False, "Không kết nối được Backend"


@st.cache_data(ttl=60, show_spinner=False)
def fetch_hitl_stats() -> dict:
    response = requests.get(f"{MV_API_URL}/api/hitl/stats", headers=auth_headers(), timeout=10)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=60, show_spinner=False)
def fetch_training_history(limit: int = 8) -> list[dict]:
    response = requests.get(
        f"{MV_API_URL}/api/training/history",
        headers=auth_headers(),
        params={"limit": limit},
        timeout=12,
    )
    response.raise_for_status()
    return response.json().get("history", [])


@st.cache_data(ttl=60, show_spinner=False)
def fetch_drift_summary() -> dict:
    response = requests.get(f"{MV_API_URL}/api/drift/summary", headers=auth_headers(), timeout=15)
    response.raise_for_status()
    return response.json()


def build_review_chart(pending: int, approved: int, rejected: int) -> go.Figure:
    fig = go.Figure(
        go.Pie(
            labels=["Chờ duyệt", "Approved", "Rejected"],
            values=[pending, approved, rejected],
            hole=0.62,
            marker_colors=["#94a3b8", "#16a34a", "#dc2626"],
            textinfo="percent",
            hovertemplate="<b>%{label}</b><br>%{value:,} bài<extra></extra>",
        )
    )
    fig.update_layout(
        height=300,
        margin=dict(t=10, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center"),
    )
    return fig


def build_training_chart(history: list[dict]) -> go.Figure:
    completed = [
        item for item in history
        if item.get("status") == "COMPLETED" and item.get("accuracy") is not None and item.get("triggered_at")
    ]
    completed = sorted(completed, key=lambda item: item["triggered_at"])

    fig = go.Figure()
    if completed:
        fig.add_trace(
            go.Scatter(
                x=[item["triggered_at"][:10] for item in completed],
                y=[float(item["accuracy"]) for item in completed],
                mode="lines+markers",
                line=dict(color="#2563eb", width=3),
                marker=dict(size=8, color="#2563eb"),
                fill="tozeroy",
                fillcolor="rgba(37, 99, 235, 0.08)",
                hovertemplate="<b>%{x}</b><br>Accuracy: %{y:.2%}<extra></extra>",
            )
        )
    fig.update_layout(
        height=300,
        margin=dict(t=20, b=40, l=45, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickformat=".0%", range=[0, 1.05], gridcolor="rgba(148,163,184,0.18)"),
        xaxis=dict(gridcolor="rgba(148,163,184,0.12)"),
        showlegend=False,
    )
    return fig


def build_drift_chart(drift_pct: dict) -> go.Figure:
    rows = sorted(drift_pct.items(), key=lambda item: abs(float(item[1] or 0)), reverse=True)
    labels = [str(label) for label, _ in rows]
    values = [float(value or 0) for _, value in rows]
    colors = [
        "#16a34a" if abs(value) < 5 else "#d97706" if abs(value) <= 10 else "#dc2626"
        for value in values
    ]

    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=colors,
            text=[f"{value:+.1f}" for value in values],
            textposition="auto",
            hovertemplate="<b>%{y}</b><br>Drift: %{x:+.2f} điểm %<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_width=1, line_dash="dash", line_color="#64748b")
    fig.update_layout(
        height=300,
        margin=dict(t=20, b=45, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="Điểm phần trăm", gridcolor="rgba(148,163,184,0.16)"),
        yaxis=dict(title="", autorange="reversed"),
        showlegend=False,
    )
    return fig


inject_styles()
health_ok, health_text = fetch_health()

with st.sidebar:
    st.title("ModelVision")
    st.caption("Internal MLOps Dashboard · AI News Pipeline")
    st.divider()
    st.page_link("app.py", label="Tổng quan")
    st.page_link("pages/1_HITL.py", label="HITL Review")
    st.page_link("pages/2_Training.py", label="Training History")
    st.page_link("pages/3_Drift.py", label="Data Drift")
    st.page_link("pages/4_Models.py", label="Model Management")
    st.page_link("pages/5_LLM_Monitor.py", label="LLM Monitor")
    st.divider()
    if health_ok:
        st.success(health_text)
    else:
        st.error(health_text)

hitl_error = training_error = drift_error = None
try:
    hitl = fetch_hitl_stats()
except Exception as exc:
    hitl = {}
    hitl_error = str(exc)

try:
    history = fetch_training_history()
except Exception as exc:
    history = []
    training_error = str(exc)

try:
    drift = fetch_drift_summary()
except Exception as exc:
    drift = {}
    drift_error = str(exc)

latest = history[0] if history else {}
pending_count = int(hitl.get("pending_count", 0) or 0)
reviewed_today = int(hitl.get("reviewed_today", 0) or 0)
approved_total = int(hitl.get("approved_total", 0) or 0)
rejected_total = int(hitl.get("rejected_total", 0) or 0)
total_articles = int(hitl.get("total_articles", 0) or 0)
reviewed_all = approved_total + rejected_total
coverage_pct = reviewed_all / total_articles if total_articles else 0.0

latest_acc = latest.get("accuracy")
latest_status = str(latest.get("status") or "—")
latest_model = short_text(latest.get("best_model") or latest.get("model_resource_name"), 48)

drift_pct = drift.get("drift_pct", {}) or {}
risky_drift = {label: value for label, value in drift_pct.items() if abs(float(value or 0)) >= 5}
strong_drift = {label: value for label, value in drift_pct.items() if abs(float(value or 0)) > 10}
max_drift_label, max_drift_value = ("—", None)
if drift_pct:
    max_drift_label, max_drift_value = max(drift_pct.items(), key=lambda item: abs(float(item[1] or 0)))

hero_chips = [
    chip("Backend", "Online" if health_ok else "Offline"),
    chip("API", MV_API_URL),
    chip("Cập nhật", datetime.now().strftime("%H:%M")),
]

st.markdown(
    f"""
    <div class="mv-hero">
        <div class="mv-eyebrow">ModelVision Overview</div>
        <h1 class="mv-title">Tổng quan hệ thống</h1>
        <p class="mv-subtitle">
            Theo dõi nhanh hàng chờ HITL, chất lượng training gần nhất, độ lệch dữ liệu và trạng thái backend
            trong một màn hình trình bày gọn cho vận hành.
        </p>
        <div class="mv-chip-row">{''.join(hero_chips)}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

kpis = [
    (
        "Hàng chờ HITL",
        fmt_int(pending_count),
        f"{fmt_int(reviewed_today, '0')} bài đã duyệt hôm nay.",
        "#2563eb",
    ),
    (
        "Độ phủ duyệt",
        fmt_pct(coverage_pct),
        f"{fmt_int(reviewed_all, '0')} / {fmt_int(total_articles, '0')} bài đã được xem xét.",
        "#16a34a",
    ),
    (
        "Accuracy gần nhất",
        fmt_pct(latest_acc),
        f"Status: {latest_status}. Model: {latest_model}.",
        "#0f766e",
    ),
    (
        "Nhãn cần theo dõi",
        fmt_int(len(risky_drift), "0"),
        f"Lệch lớn nhất: {max_drift_label} {fmt_delta(max_drift_value)}.",
        "#d97706" if not strong_drift else "#dc2626",
    ),
]

kpi_cols = st.columns(4)
for col, spec in zip(kpi_cols, kpis):
    with col:
        st.markdown(kpi_card(*spec), unsafe_allow_html=True)

st.divider()

left_col, right_col = st.columns([1, 1], gap="large")
with left_col:
    st.markdown(section_header("Tình trạng duyệt", "Tỷ trọng bài chờ, approved và rejected trong HITL."), unsafe_allow_html=True)
    if hitl_error:
        st.warning(f"Không tải được HITL stats: {hitl_error}")
    else:
        st.plotly_chart(build_review_chart(pending_count, approved_total, rejected_total), use_container_width=True, config={"displayModeBar": False})

with right_col:
    st.markdown(section_header("Accuracy training", "Các lần training hoàn tất gần đây theo thời gian."), unsafe_allow_html=True)
    if training_error:
        st.warning(f"Không tải được training history: {training_error}")
    elif not history:
        st.info("Chưa có lịch sử training để hiển thị.")
    else:
        st.plotly_chart(build_training_chart(history), use_container_width=True, config={"displayModeBar": False})

st.divider()

drift_col, action_col = st.columns([1.15, 0.85], gap="large")
with drift_col:
    st.markdown(section_header("Drift nhanh", "So sánh HITL với dữ liệu gốc theo điểm phần trăm."), unsafe_allow_html=True)
    if drift_error:
        st.warning(f"Không tải được dữ liệu drift: {drift_error}")
    elif not drift_pct:
        st.info("Chưa có dữ liệu drift để hiển thị.")
    else:
        st.plotly_chart(build_drift_chart(drift_pct), use_container_width=True, config={"displayModeBar": False})

with action_col:
    st.markdown(section_header("Cần chú ý", "Các tín hiệu vận hành được rút ra từ dữ liệu hiện tại."), unsafe_allow_html=True)

    rows = []
    rows.append(
        action_row(
            "ok" if health_ok else "bad",
            "Ổn định" if health_ok else "Lỗi",
            "Backend API",
            health_text,
        )
    )
    rows.append(
        action_row(
            "warn" if pending_count else "ok",
            "Cần xử lý" if pending_count else "Ổn định",
            "Hàng chờ HITL",
            f"{fmt_int(pending_count, '0')} bài đang chờ duyệt, {fmt_int(reviewed_today, '0')} bài đã xử lý hôm nay.",
        )
    )
    rows.append(
        action_row(
            "bad" if strong_drift else "warn" if risky_drift else "ok",
            "Lệch mạnh" if strong_drift else "Theo dõi" if risky_drift else "Ổn định",
            "Data drift",
            f"{fmt_int(len(risky_drift), '0')} nhãn vượt ngưỡng 5 điểm %. Lớn nhất: {max_drift_label} {fmt_delta(max_drift_value)}.",
        )
    )
    rows.append(
        action_row(
            "bad" if latest_status == "FAILED" else "warn" if latest_status in {"RUNNING", "SUBMITTED"} else "ok",
            latest_status if latest_status != "—" else "Chưa có",
            "Training gần nhất",
            f"Accuracy {fmt_pct(latest_acc)}. Model: {latest_model}.",
        )
    )

    st.markdown(f'<div class="mv-panel">{"".join(rows)}</div>', unsafe_allow_html=True)

st.divider()
st.caption("ModelVision · KLTN 2026")
