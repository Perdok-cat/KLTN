from __future__ import annotations

import os
from html import escape

import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

from utils.gcp_auth import auth_headers

MV_API_URL = os.getenv("MV_API_URL", "http://localhost:5001")

st.set_page_config(page_title="LLM Monitor · ModelVision", page_icon="🧠", layout="wide")


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ops-bg: #f4f7fb;
            --ops-panel: #ffffff;
            --ops-line: #dce6f2;
            --ops-text: #0f172a;
            --ops-muted: #64748b;
            --ops-accent: #2563eb;
            --ops-success: #16a34a;
            --ops-warning: #d97706;
            --ops-danger: #dc2626;
        }

        .stApp {
            background:
                radial-gradient(circle at top right, rgba(37, 99, 235, 0.14), transparent 24%),
                linear-gradient(180deg, #f8fbff 0%, var(--ops-bg) 22%, #eef3f9 100%);
            color: var(--ops-text);
        }

        header[data-testid="stHeader"] {
            background: rgba(244, 247, 251, 0.72);
            backdrop-filter: blur(14px);
            border-bottom: 1px solid rgba(220, 230, 242, 0.8);
        }

        .block-container {
            max-width: 1540px;
            padding: 1.6rem 2rem 3rem;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #eef4fa 0%, #e8f0f7 100%);
            border-right: 1px solid #d8e4f0;
        }

        [data-testid="stSidebar"] .block-container {
            padding: 1.2rem 0.95rem 1.8rem;
        }

        div[data-testid="stPageLink"] a {
            min-height: 2.55rem;
            border-radius: 14px;
            padding: 0.35rem 0.55rem;
            font-weight: 720;
        }

        div[data-testid="stPageLink"] a:hover {
            background: rgba(255, 255, 255, 0.86);
            color: var(--ops-accent);
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 24px;
            border: 1px solid rgba(220, 230, 242, 0.95);
            background: rgba(255, 255, 255, 0.88);
            box-shadow: 0 14px 32px rgba(15, 23, 42, 0.05);
        }

        .ops-hero {
            position: relative;
            overflow: hidden;
            padding: 1.65rem 1.8rem 1.8rem;
            border-radius: 30px;
            background:
                radial-gradient(circle at top right, rgba(148, 197, 255, 0.42), transparent 22%),
                linear-gradient(135deg, #0f172a 0%, #123b8f 58%, #2563eb 100%);
            color: #ffffff;
            box-shadow: 0 24px 56px rgba(37, 99, 235, 0.26);
            margin-bottom: 1.1rem;
        }

        .ops-eyebrow {
            font-size: 0.86rem;
            font-weight: 760;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: rgba(219, 234, 254, 0.88);
            margin-bottom: 0.55rem;
        }

        .ops-title {
            margin: 0;
            font-size: clamp(2.2rem, 4vw, 3.6rem);
            line-height: 1.02;
            font-weight: 860;
        }

        .ops-subtitle {
            margin: 0.7rem 0 1.1rem;
            max-width: 760px;
            color: rgba(241, 245, 249, 0.92);
            font-size: 1rem;
            line-height: 1.55;
        }

        .ops-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
        }

        .ops-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.42rem;
            padding: 0.54rem 0.82rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.14);
            font-size: 0.86rem;
            font-weight: 720;
            color: #f8fafc;
        }

        .metric-card {
            min-height: 164px;
            padding: 1rem 1.05rem;
            border-radius: 22px;
            border: 1px solid rgba(220, 230, 242, 0.95);
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.94) 0%, rgba(248, 250, 252, 0.98) 100%);
            box-shadow: 0 16px 30px rgba(15, 23, 42, 0.06);
        }

        .metric-card__icon {
            display: inline-grid;
            place-items: center;
            width: 44px;
            height: 44px;
            border-radius: 15px;
            font-size: 1.1rem;
            color: #ffffff;
            background: var(--metric-accent);
        }

        .metric-card__label {
            margin-top: 0.9rem;
            color: var(--ops-muted);
            font-size: 0.88rem;
            font-weight: 700;
        }

        .metric-card__value {
            margin-top: 0.38rem;
            color: var(--ops-text);
            font-size: 1.74rem;
            font-weight: 840;
            line-height: 1.05;
        }

        .metric-card__meta {
            margin-top: 0.55rem;
            color: var(--ops-muted);
            font-size: 0.82rem;
            line-height: 1.45;
        }

        .section-heading__title {
            margin: 0;
            color: var(--ops-text);
            font-size: 1.18rem;
            font-weight: 820;
        }

        .section-heading__caption {
            margin: 0.14rem 0 0.85rem;
            color: var(--ops-muted);
            font-size: 0.88rem;
        }

        .snapshot-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 0.8rem;
        }

        .snapshot-card {
            padding: 0.9rem 0.95rem;
            border-radius: 18px;
            border: 1px solid rgba(220, 230, 242, 0.9);
            background: rgba(255, 255, 255, 0.92);
        }

        .snapshot-card__label {
            color: var(--ops-muted);
            font-size: 0.8rem;
            font-weight: 720;
            text-transform: uppercase;
        }

        .snapshot-card__value {
            margin-top: 0.45rem;
            color: var(--ops-text);
            font-size: 1.02rem;
            font-weight: 790;
            line-height: 1.3;
        }

        .ops-note {
            margin-top: 0.8rem;
            color: var(--ops-muted);
            font-size: 0.82rem;
            line-height: 1.55;
        }

        @media (max-width: 900px) {
            .block-container {
                padding: 1.1rem 0.95rem 2rem;
            }

            .ops-hero {
                padding: 1.3rem 1.15rem 1.35rem;
                border-radius: 24px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def fmt_int(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def fmt_float(value: object, digits: int = 1) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return f"{0:.{digits}f}"


def fmt_currency(value: object) -> str:
    try:
        return f"${float(value):,.4f}"
    except (TypeError, ValueError):
        return "$0.0000"


def provider_label(provider: str, use_vertex: bool) -> str:
    if use_vertex or provider == "vertex":
        return "Vertex AI"
    if provider == "gemini_api":
        return "Gemini API"
    return provider or "Chưa có dữ liệu"


def status_chip(icon: str, label: str, value: str) -> str:
    return f'<div class="ops-chip"><span>{escape(icon)}</span><span>{escape(label)}:</span><b>{escape(value)}</b></div>'


def metric_card(icon: str, accent: str, label: str, value: str, meta: str) -> str:
    return f"""
    <div class="metric-card" style="--metric-accent:{accent}">
        <div class="metric-card__icon">{escape(icon)}</div>
        <div class="metric-card__label">{escape(label)}</div>
        <div class="metric-card__value">{escape(value)}</div>
        <div class="metric-card__meta">{escape(meta)}</div>
    </div>
    """


def section_header(title: str, caption: str) -> str:
    return f"""
    <div class="section-heading__title">{escape(title)}</div>
    <div class="section-heading__caption">{escape(caption)}</div>
    """


def snapshot_card(label: str, value: str) -> str:
    return f"""
    <div class="snapshot-card">
        <div class="snapshot-card__label">{escape(label)}</div>
        <div class="snapshot-card__value">{escape(value)}</div>
    </div>
    """


@st.cache_data(ttl=30, show_spinner=False)
def fetch_overview(range_key: str) -> dict:
    response = requests.get(
        f"{MV_API_URL}/api/llm/overview",
        headers=auth_headers(),
        params={"range": range_key},
        timeout=25,
    )
    response.raise_for_status()
    return response.json()


def build_trend_chart(timeseries: list[dict]) -> go.Figure:
    x = [item.get("bucket", "") for item in timeseries]
    requests_series = [int(item.get("requests", 0) or 0) for item in timeseries]
    tokens_series = [int(item.get("total_tokens", 0) or 0) for item in timeseries]
    cost_series = [float(item.get("total_cost_usd", 0) or 0) for item in timeseries]

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("Requests", "Total tokens", "Estimated cost (USD)"),
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=requests_series,
            mode="lines+markers",
            line=dict(color="#2563eb", width=3),
            marker=dict(size=7, color="#2563eb"),
            fill="tozeroy",
            fillcolor="rgba(37, 99, 235, 0.10)",
            hovertemplate="<b>%{x}</b><br>Requests: %{y}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=tokens_series,
            mode="lines+markers",
            line=dict(color="#16a34a", width=3),
            marker=dict(size=7, color="#16a34a"),
            fill="tozeroy",
            fillcolor="rgba(22, 163, 74, 0.10)",
            hovertemplate="<b>%{x}</b><br>Tokens: %{y:,}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=cost_series,
            mode="lines+markers",
            line=dict(color="#d97706", width=3),
            marker=dict(size=7, color="#d97706"),
            fill="tozeroy",
            fillcolor="rgba(217, 119, 6, 0.10)",
            hovertemplate="<b>%{x}</b><br>Cost: $%{y:.4f}<extra></extra>",
        ),
        row=3,
        col=1,
    )
    fig.update_layout(
        height=560,
        margin=dict(t=70, b=20, l=10, r=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    fig.update_xaxes(gridcolor="rgba(148, 163, 184, 0.18)", tickfont=dict(color="#475569"))
    fig.update_yaxes(gridcolor="rgba(148, 163, 184, 0.18)", zeroline=False, tickfont=dict(color="#475569"))
    return fig


def build_error_charts(error_breakdown: list[dict]) -> tuple[go.Figure, go.Figure]:
    labels = [item.get("error_type", "unknown") for item in error_breakdown] or ["No errors"]
    values = [int(item.get("count", 0) or 0) for item in error_breakdown] or [1]
    colors = ["#dc2626", "#d97706", "#2563eb", "#64748b", "#7c3aed"][: len(labels)]

    donut = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.66,
                textinfo="label+percent",
                marker=dict(colors=colors),
                hovertemplate="<b>%{label}</b><br>Số lần lỗi: %{value}<extra></extra>",
            )
        ]
    )
    donut.update_layout(height=340, margin=dict(t=20, b=20, l=20, r=20), showlegend=False, paper_bgcolor="rgba(0,0,0,0)")

    bar = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker=dict(color=colors),
            text=values,
            textposition="auto",
            hovertemplate="<b>%{y}</b><br>Số lần lỗi: %{x}<extra></extra>",
        )
    )
    bar.update_layout(
        height=340,
        margin=dict(t=20, b=20, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(gridcolor="rgba(148, 163, 184, 0.18)"),
        yaxis=dict(title=""),
    )
    return donut, bar


inject_styles()

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/artificial-intelligence.png", width=80)
    st.title("ModelVision")
    st.caption("Internal MLOps Dashboard · AI News Pipeline")
    st.divider()
    st.page_link("app.py",               label="🏠 Tổng quan")
    st.page_link("pages/1_HITL.py",      label="🛡️ HITL Review")
    st.page_link("pages/2_Training.py",  label="📈 Training History")
    st.page_link("pages/3_Drift.py",     label="📊 Data Drift")
    st.page_link("pages/4_Models.py",    label="🤖 Model Management")
    st.page_link("pages/5_LLM_Monitor.py", label="🧠 LLM Monitor")
    st.divider()

toolbar_left, toolbar_right = st.columns([2.4, 1])
with toolbar_left:
    st.caption("Theo dõi Gemini/Vertex cho pipeline tóm tắt trong thời gian thực gần đây.")
with toolbar_right:
    range_key = st.radio(
        "Khung thời gian",
        options=["24h", "7d", "30d"],
        horizontal=True,
        label_visibility="collapsed",
    )

refresh_col, spacer_col = st.columns([1, 5])
with refresh_col:
    if st.button("Làm mới", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
with spacer_col:
    st.caption(f"Nguồn dữ liệu: `{MV_API_URL}/api/llm/overview?range={range_key}`")

with st.spinner("Đang tải dữ liệu LLM monitor…"):
    try:
        overview = fetch_overview(range_key)
    except Exception as exc:
        st.error(f"Không tải được dữ liệu monitor: {exc}")
        st.info("Kiểm tra backend ModelVision, bảng llm_usage_log và quyền đọc BigQuery.")
        st.stop()

config = overview.get("config_snapshot", {}) or {}
kpis = overview.get("kpis", {}) or {}
timeseries = overview.get("timeseries", []) or []
error_breakdown = overview.get("error_breakdown", []) or []
recent_logs = overview.get("recent_logs", []) or []

provider = provider_label(str(overview.get("provider") or ""), bool(config.get("use_vertex")))
model_name = str(overview.get("model_name") or "Chưa có dữ liệu")
prompt_version = str(overview.get("prompt_version") or "—")

st.markdown(
    f"""
    <div class="ops-hero">
        <div class="ops-eyebrow">AI Operations Dashboard</div>
        <h1 class="ops-title">LLM Monitor</h1>
        <p class="ops-subtitle">
            Theo dõi Gemini/Vertex cho pipeline tóm tắt bài báo với góc nhìn trực quan về request,
            token usage, chi phí ước lượng, độ trễ và các lỗi nổi bật theo từng khoảng thời gian.
        </p>
        <div class="ops-chip-row">
            {status_chip("⚙️", "Provider", provider)}
            {status_chip("🧠", "Model", model_name)}
            {status_chip("📝", "Prompt", prompt_version)}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

metric_specs = [
    ("📡", "#2563eb", "Total requests", fmt_int(kpis.get("total_requests")), f"{range_key} · Tổng số lần gọi model được ghi nhận."),
    ("✅", "#16a34a", "Success rate", f"{fmt_float(kpis.get('success_rate'), 1)}%", f"{fmt_int(kpis.get('success_count'))} request thành công."),
    ("🧮", "#0f766e", "Total tokens", fmt_int(kpis.get("total_tokens")), f"Input {fmt_int(kpis.get('input_tokens'))} · Output {fmt_int(kpis.get('output_tokens'))}."),
    ("💸", "#d97706", "Estimated cost", fmt_currency(kpis.get("total_cost_usd")), "Chi phí ước lượng từ usage log."),
    ("⚡", "#7c3aed", "Avg latency", f"{fmt_float(kpis.get('avg_latency_ms'), 0)} ms", "Độ trễ trung bình của mỗi lần gọi."),
    ("🚨", "#dc2626", "Error rate", f"{fmt_float(kpis.get('error_rate'), 1)}%", f"{fmt_int(kpis.get('error_count'))} request gặp lỗi."),
]
metric_cols = st.columns(len(metric_specs))
for col, spec in zip(metric_cols, metric_specs):
    with col:
        st.markdown(metric_card(*spec), unsafe_allow_html=True)

st.markdown(section_header("Xu hướng theo thời gian", "Ba tín hiệu chính để trình bày: số request, lượng token và chi phí ước lượng."), unsafe_allow_html=True)
with st.container(border=True):
    if timeseries:
        st.plotly_chart(build_trend_chart(timeseries), use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("Chưa có dữ liệu usage trong khoảng thời gian đã chọn.")

left_col, right_col = st.columns([1.15, 1])
with left_col:
    st.markdown(section_header("Runtime snapshot", "Ảnh chụp cấu hình runtime gần nhất lấy từ usage log."), unsafe_allow_html=True)
    with st.container(border=True):
        html = '<div class="snapshot-grid">'
        html += snapshot_card("Provider mode", "Vertex AI" if config.get("use_vertex") else "Gemini API")
        html += snapshot_card("Gemini model", model_name)
        html += snapshot_card("Vertex location", str(config.get("vertex_location") or "—"))
        html += snapshot_card("Max retries", str(config.get("max_retries") or 0))
        html += snapshot_card("Max content chars", fmt_int(config.get("max_content_chars")))
        html += snapshot_card("Gemini delay", f"{fmt_float(config.get('gemini_delay'), 1)} s")
        html += "</div>"
        html += """
        <div class="ops-note">
            Nếu <b>USE_VERTEX=true</b> thì đây là Gemini chạy qua Vertex AI Generative API,
            không phải Vertex Endpoint của model phân loại.
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)

with right_col:
    st.markdown(section_header("Phân bố lỗi", "Xác định nhanh lỗi nào đang chiếm ưu thế trong runtime."), unsafe_allow_html=True)
    with st.container(border=True):
        if error_breakdown:
            donut_fig, bar_fig = build_error_charts(error_breakdown)
            donut_col, bar_col = st.columns(2)
            with donut_col:
                st.plotly_chart(donut_fig, use_container_width=True, config={"displayModeBar": False})
            with bar_col:
                st.plotly_chart(bar_fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.success("Không ghi nhận lỗi nào trong khoảng thời gian đang xem.")

st.markdown(section_header("Recent logs", "Các request gần nhất để bạn trình bày trực tiếp token, độ trễ và trạng thái runtime."), unsafe_allow_html=True)
with st.container(border=True):
    if recent_logs:
        rows = []
        for item in recent_logs:
            rows.append(
                {
                    "Thời gian": str(item.get("started_at") or "").replace("T", " ")[:19],
                    "Provider": provider_label(str(item.get("provider") or ""), str(item.get("provider") or "") == "vertex"),
                    "Model": item.get("model_name") or "—",
                    "Total token": fmt_int(item.get("total_tokens")),
                    "Latency": f"{fmt_int(item.get('latency_ms'))} ms",
                    "Trạng thái": "Success" if item.get("success") else "Failed",
                    "Lỗi": item.get("error_type") or "—",
                    "Nguồn token": item.get("token_source") or "—",
                    "Cost": fmt_currency(item.get("cost_estimate_usd")),
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có request log nào để hiển thị.")
