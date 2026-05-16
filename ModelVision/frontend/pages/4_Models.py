import os
from html import escape

import requests
import streamlit as st

from utils.gcp_auth import auth_headers

MV_API_URL = os.getenv("MV_API_URL", "http://localhost:5001")

st.set_page_config(page_title="Model Management · ModelVision", page_icon="🤖", layout="wide")


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --mm-bg: #f4f7fb;
            --mm-panel: #ffffff;
            --mm-line: #dce6f2;
            --mm-text: #0f172a;
            --mm-muted: #64748b;
            --mm-accent: #2563eb;
            --mm-success: #16a34a;
            --mm-warning: #d97706;
            --mm-danger: #dc2626;
        }

        .stApp {
            background:
                radial-gradient(circle at top right, rgba(37, 99, 235, 0.12), transparent 24%),
                linear-gradient(180deg, #f8fbff 0%, var(--mm-bg) 28%, #eef3f9 100%);
            color: var(--mm-text);
        }

        header[data-testid="stHeader"] {
            background: rgba(244, 247, 251, 0.78);
            backdrop-filter: blur(14px);
            border-bottom: 1px solid rgba(220, 230, 242, 0.82);
        }

        .block-container {
            max-width: 1540px;
            padding: 1.45rem 2rem 3rem;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #eef4fa 0%, #e8f0f7 100%);
            border-right: 1px solid #d8e4f0;
        }

        div[data-testid="stPageLink"] a {
            min-height: 2.55rem;
            border-radius: 14px;
            padding: 0.35rem 0.55rem;
            font-weight: 720;
        }

        div[data-testid="stPageLink"] a:hover {
            background: rgba(255, 255, 255, 0.86);
            color: var(--mm-accent);
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 24px;
            border: 1px solid rgba(220, 230, 242, 0.95);
            background: rgba(255, 255, 255, 0.9);
            box-shadow: 0 14px 32px rgba(15, 23, 42, 0.05);
        }

        .mm-hero {
            padding: 1.6rem 1.8rem;
            border-radius: 30px;
            background:
                radial-gradient(circle at top right, rgba(148, 197, 255, 0.44), transparent 24%),
                linear-gradient(135deg, #0f172a 0%, #123b8f 58%, #2563eb 100%);
            color: #fff;
            box-shadow: 0 24px 56px rgba(37, 99, 235, 0.24);
            margin-bottom: 1rem;
        }

        .mm-eyebrow {
            font-size: 0.84rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: rgba(219, 234, 254, 0.88);
            font-weight: 760;
        }

        .mm-title {
            margin: 0.45rem 0 0;
            font-size: clamp(2.2rem, 4vw, 3.4rem);
            font-weight: 860;
            line-height: 1.02;
        }

        .mm-subtitle {
            margin: 0.7rem 0 1rem;
            color: rgba(241, 245, 249, 0.94);
            max-width: 760px;
            line-height: 1.55;
        }

        .mm-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
        }

        .mm-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.54rem 0.8rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.16);
            color: #f8fafc;
            font-size: 0.86rem;
            font-weight: 720;
        }

        .mm-chip b {
            color: #fff;
        }

        .mm-kpi {
            min-height: 152px;
            height: 100%;
            padding: 1rem 1.05rem;
            display: flex;
            flex-direction: column;
            border-radius: 22px;
            border: 1px solid rgba(220, 230, 242, 0.95);
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 252, 0.98) 100%);
            box-shadow: 0 16px 30px rgba(15, 23, 42, 0.06);
        }

        .mm-kpi__icon {
            display: inline-grid;
            place-items: center;
            width: 44px;
            height: 44px;
            border-radius: 15px;
            font-size: 1.15rem;
            color: #fff;
            background: var(--kpi-color);
        }

        .mm-kpi__label {
            margin-top: 0.9rem;
            color: var(--mm-muted);
            font-size: 0.88rem;
            font-weight: 720;
        }

        .mm-kpi__value {
            margin-top: 0.36rem;
            font-size: 1.72rem;
            font-weight: 840;
            line-height: 1.05;
        }

        .mm-kpi__meta {
            margin-top: auto;
            padding-top: 0.8rem;
            color: var(--mm-muted);
            font-size: 0.82rem;
            line-height: 1.45;
        }

        .mm-section-title {
            margin: 0.15rem 0 0.15rem;
            font-size: 1.18rem;
            font-weight: 820;
            color: var(--mm-text);
        }

        .mm-section-caption {
            margin: 0 0 0.95rem;
            color: var(--mm-muted);
            font-size: 0.88rem;
        }

        .endpoint-card {
            padding: 1.15rem 1.1rem 1.05rem;
            border-radius: 22px;
            border: 1px solid rgba(220, 230, 242, 0.95);
            background: rgba(255, 255, 255, 0.94);
            box-shadow: 0 16px 30px rgba(15, 23, 42, 0.06);
        }

        .endpoint-card--active {
            border-color: rgba(37, 99, 235, 0.22);
            box-shadow: 0 18px 34px rgba(37, 99, 235, 0.1);
        }

        .endpoint-card__top {
            display: flex;
            align-items: start;
            justify-content: space-between;
            gap: 0.8rem;
        }

        .endpoint-card__title {
            margin: 0;
            font-size: 1.08rem;
            font-weight: 820;
            color: var(--mm-text);
        }

        .endpoint-card__id {
            margin-top: 0.28rem;
            color: var(--mm-muted);
            font-size: 0.8rem;
            word-break: break-all;
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.36rem;
            padding: 0.42rem 0.72rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 760;
            white-space: nowrap;
        }

        .status-badge--active {
            background: rgba(22, 163, 74, 0.12);
            color: var(--mm-success);
        }

        .status-badge--idle {
            background: rgba(217, 119, 6, 0.12);
            color: var(--mm-warning);
        }

        .endpoint-card__metrics {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.7rem;
            margin-top: 1rem;
        }

        .mini-stat {
            padding: 0.75rem 0.8rem;
            border-radius: 18px;
            border: 1px solid rgba(220, 230, 242, 0.9);
            background: #f8fbff;
        }

        .mini-stat__label {
            color: var(--mm-muted);
            font-size: 0.76rem;
            text-transform: uppercase;
            font-weight: 720;
        }

        .mini-stat__value {
            margin-top: 0.34rem;
            font-size: 1.06rem;
            font-weight: 800;
            color: var(--mm-text);
        }

        .deployed-row {
            padding: 0.88rem 0.9rem;
            border-radius: 18px;
            border: 1px solid rgba(220, 230, 242, 0.9);
            background: rgba(248, 251, 255, 0.92);
            margin-top: 0.75rem;
        }

        .deployed-row__top {
            display: flex;
            justify-content: space-between;
            gap: 0.7rem;
            align-items: start;
        }

        .deployed-row__name {
            font-size: 0.98rem;
            font-weight: 790;
            color: var(--mm-text);
        }

        .deployed-row__sub {
            margin-top: 0.18rem;
            font-size: 0.79rem;
            color: var(--mm-muted);
            word-break: break-all;
        }

        .deployed-row__traffic {
            color: var(--mm-accent);
            font-size: 0.95rem;
            font-weight: 820;
            white-space: nowrap;
        }

        .deployed-row__meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-top: 0.6rem;
        }

        .meta-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.34rem;
            padding: 0.38rem 0.62rem;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 720;
            border: 1px solid rgba(220, 230, 242, 0.95);
            background: #fff;
            color: #334155;
        }

        @media (max-width: 900px) {
            .block-container {
                padding: 1.1rem 0.95rem 2rem;
            }

            .mm-hero {
                padding: 1.25rem 1.1rem 1.3rem;
                border-radius: 24px;
            }

            .endpoint-card__metrics {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def short_id(value: str | None, size: int = 28) -> str:
    if not value:
        return "—"
    return value if len(value) <= size else f"{value[:size]}…"


def fmt_int(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def fmt_time(value: str | None) -> str:
    return (value or "—")[:16].replace("T", " ")


def status_badge(status: str) -> str:
    tone = "active" if str(status).upper() == "ACTIVE" else "idle"
    icon = "●" if tone == "active" else "○"
    return f'<div class="status-badge status-badge--{tone}">{icon} {escape(status or "UNKNOWN")}</div>'


def chip(icon: str, label: str, value: str) -> str:
    return f'<div class="mm-chip"><span>{escape(icon)}</span><span>{escape(label)}:</span><b>{escape(value)}</b></div>'


def kpi_card(icon: str, color: str, label: str, value: str, meta: str) -> str:
    return (
        f'<div class="mm-kpi" style="--kpi-color:{color}">'
        f'<div class="mm-kpi__icon">{escape(icon)}</div>'
        f'<div class="mm-kpi__label">{escape(label)}</div>'
        f'<div class="mm-kpi__value">{escape(value)}</div>'
        f'<div class="mm-kpi__meta">{escape(meta)}</div>'
        "</div>"
    )


def mini_stat(label: str, value: str) -> str:
    return (
        '<div class="mini-stat">'
        f'<div class="mini-stat__label">{escape(label)}</div>'
        f'<div class="mini-stat__value">{escape(value)}</div>'
        "</div>"
    )


def meta_chip(icon: str, text: str) -> str:
    return f'<div class="meta-chip">{escape(icon)} {escape(text)}</div>'


@st.cache_data(ttl=30, show_spinner=False)
def fetch_overview() -> dict:
    response = requests.get(f"{MV_API_URL}/api/model/overview", headers=auth_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


inject_styles()

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/artificial-intelligence.png", width=80)
    st.title("ModelVision")
    st.divider()
    st.page_link("app.py", label="🏠 Tổng quan")
    st.page_link("pages/1_HITL.py", label="🛡️ HITL Review")
    st.page_link("pages/2_Training.py", label="📈 Training History")
    st.page_link("pages/3_Drift.py", label="📊 Data Drift")
    st.page_link("pages/4_Models.py", label="🤖 Model Management")
    st.page_link("pages/5_LLM_Monitor.py", label="🧠 LLM Monitor")

with st.spinner("Đang tải trạng thái endpoint…"):
    try:
        overview = fetch_overview()
    except Exception as exc:
        st.error(f"Không tải được Model Management overview: {exc}")
        st.info("Kiểm tra backend, cấu hình Vertex AI, region và quyền đọc Vertex AI/BigQuery.")
        st.stop()

endpoint = overview.get("endpoint", {}) or {}
endpoints = overview.get("endpoints", []) or []
registry_models = overview.get("registry_models", []) or []
latest_training = overview.get("latest_training")
configured_endpoint_error = overview.get("configured_endpoint_error")
configured_endpoint_id = str(endpoint.get("id") or "")
active_endpoint_count = int(overview.get("active_endpoint_count", len(endpoints)) or 0)
total_deployed = sum(int(item.get("deployed_model_count", 0) or 0) for item in endpoints)
active_traffic = sum(int(item.get("total_traffic_pct", 0) or 0) for item in endpoints)

hero_chips = [
    chip("📍", "Region", str(endpoint.get("location") or "—")),
    chip("🛰️", "Configured endpoint", configured_endpoint_id or "—"),
    chip("✅", "Status", str(endpoint.get("status") or "UNKNOWN")),
]

st.markdown(
    f"""
    <div class="mm-hero">
        <div class="mm-eyebrow">Vertex Overview</div>
        <div class="mm-title">Active Vertex Endpoints</div>
        <div class="mm-subtitle">
            Xem nhanh endpoint nào đang hoạt động, model nào đang được deploy và một snapshot ngắn của model registry.
        </div>
        <div class="mm-chip-row">
            {''.join(hero_chips)}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

toolbar_left, toolbar_right = st.columns([1, 5])
with toolbar_left:
    if st.button("🔄 Làm mới", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
with toolbar_right:
    st.caption(f"Nguồn dữ liệu: `{MV_API_URL}/api/model/overview`")

kpis = [
    ("🛰️", "#2563eb", "Active endpoints", fmt_int(active_endpoint_count), "Số endpoint có model đang được deploy."),
    ("🤖", "#16a34a", "Deployed models", fmt_int(total_deployed), "Tổng số model đang xuất hiện trong các endpoint hoạt động."),
    ("📦", "#0f766e", "Registry entries", fmt_int(len(registry_models)), "Các model mới nhất thấy trong Vertex Model Registry."),
    ("🚦", "#d97706", "Total traffic", f"{fmt_int(active_traffic)}%", "Tổng traffic hiện thấy trên các endpoint hoạt động."),
]
kpi_cols = st.columns(len(kpis))
for col, spec in zip(kpi_cols, kpis):
    with col:
        st.markdown(kpi_card(*spec), unsafe_allow_html=True)

if configured_endpoint_error:
    st.warning(f"Configured endpoint đang lỗi: {configured_endpoint_error}")

if latest_training:
    training_text = (
        "Training gần nhất: "
        f"`{latest_training.get('status', '—')}` · "
        f"{fmt_time(latest_training.get('completed_at') or latest_training.get('triggered_at'))}"
    )
    if latest_training.get("accuracy") is not None:
        training_text += f" · Accuracy {float(latest_training.get('accuracy')):.2%}"
    st.caption(training_text)

st.divider()
st.markdown('<div class="mm-section-title">Endpoint Overview</div>', unsafe_allow_html=True)
st.markdown('<div class="mm-section-caption">Mỗi card đại diện cho một endpoint đang có model được deploy.</div>', unsafe_allow_html=True)

if not endpoints:
    st.info("Chưa tìm thấy endpoint nào đang có model được deploy trong region hiện tại.")
else:
    endpoint_cols = st.columns(2)
    for idx, item in enumerate(endpoints):
        with endpoint_cols[idx % 2]:
            endpoint_html = (
                f'<div class="endpoint-card endpoint-card--{"active" if item.get("status") == "ACTIVE" else "idle"}">'
                '<div class="endpoint-card__top">'
                '<div>'
                f'<div class="endpoint-card__title">{escape(item.get("display_name") or "Vertex Endpoint")}</div>'
                f'<div class="endpoint-card__id">Endpoint ID: {escape(str(item.get("id") or "—"))}</div>'
                "</div>"
                f"{status_badge(str(item.get('status') or 'UNKNOWN'))}"
                "</div>"
                '<div class="endpoint-card__metrics">'
                f'{mini_stat("Deployed models", fmt_int(item.get("deployed_model_count")))}'
                f'{mini_stat("Traffic", f"{fmt_int(item.get("total_traffic_pct"))}%")}'
                f'{mini_stat("Created", fmt_time(item.get("create_time")))}'
                "</div>"
            )
            for dm in item.get("deployed_models", []):
                training = dm.get("latest_training")
                deployed_id_text = f"Deployed ID {dm.get('id') or '—'}"
                serving_status_text = str(dm.get("serving_status") or "UNKNOWN")
                endpoint_html += (
                    '<div class="deployed-row">'
                    '<div class="deployed-row__top">'
                    '<div>'
                    f'<div class="deployed-row__name">{escape(dm.get("display_name") or "Deployed model")}</div>'
                    f'<div class="deployed-row__sub">Model: {escape(short_id(dm.get("model_resource_name"), 52))}</div>'
                    "</div>"
                    f'<div class="deployed-row__traffic">{fmt_int(dm.get("traffic_pct"))}%</div>'
                    "</div>"
                    '<div class="deployed-row__meta">'
                    f'{meta_chip("🆔", deployed_id_text)}'
                    f'{meta_chip("📡", serving_status_text)}'
                )
                if training and training.get("accuracy") is not None:
                    endpoint_html += meta_chip("🎯", f"Accuracy {float(training.get('accuracy')):.2%}")
                if training and training.get("status"):
                    endpoint_html += meta_chip("📋", f"Training {training.get('status')}")
                endpoint_html += "</div></div>"
            endpoint_html += "</div>"
            st.markdown(endpoint_html, unsafe_allow_html=True)

st.divider()
st.markdown('<div class="mm-section-title">Registry Snapshot</div>', unsafe_allow_html=True)
st.markdown('<div class="mm-section-caption">Danh sách ngắn các model mới nhất trong Vertex Model Registry.</div>', unsafe_allow_html=True)

if not registry_models:
    st.info("Không tìm thấy model nào trong Vertex Model Registry khớp với prefix hiện tại.")
else:
    rows = []
    for model in registry_models:
        rows.append(
            {
                "Model": model.get("display_name", "—"),
                "Created": fmt_time(model.get("create_time")),
                "Version": model.get("version_id") or "—",
                "Deployed": "Có" if model.get("is_deployed") else "Không",
                "Traffic": f"{fmt_int(model.get('traffic_pct'))}%",
                "Status": model.get("serving_status", "—"),
                "Resource": model.get("resource_name", "—"),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
