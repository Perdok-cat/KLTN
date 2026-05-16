import os

import plotly.graph_objects as go
import requests
import streamlit as st

from utils.gcp_auth import auth_headers

MV_API_URL = os.getenv("MV_API_URL", "http://localhost:5001")

st.set_page_config(page_title="Model Management · ModelVision", page_icon="🤖", layout="wide")

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/artificial-intelligence.png", width=80)
    st.title("ModelVision")
    st.divider()
    st.page_link("app.py",               label="🏠 Tổng quan")
    st.page_link("pages/1_HITL.py",      label="🛡️ HITL Review")
    st.page_link("pages/2_Training.py",  label="📈 Training History")
    st.page_link("pages/3_Drift.py",     label="📊 Data Drift")
    st.page_link("pages/4_Models.py",    label="🤖 Model Management")
    st.page_link("pages/5_LLM_Monitor.py", label="🧠 LLM Monitor")

st.title("🤖 Model Management")
st.caption("Theo dõi trạng thái Vertex AI Endpoint, model registry, training metadata và traffic split")
st.divider()


@st.cache_data(ttl=30, show_spinner=False)
def fetch_overview() -> dict:
    r = requests.get(f"{MV_API_URL}/api/model/overview", headers=auth_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def post_traffic_split(split: dict) -> requests.Response:
    return requests.post(
        f"{MV_API_URL}/api/model/traffic",
        headers=auth_headers(),
        json={"traffic_split": split},
        timeout=30,
    )


def model_key(resource_name: str | None) -> str:
    return (resource_name or "").split("@", 1)[0].strip()


def short_id(value: str | None, size: int = 20) -> str:
    if not value:
        return "—"
    return value if len(value) <= size else f"{value[:size]}…"


def fmt_time(value: str | None) -> str:
    return (value or "—")[:16].replace("T", " ")


def fmt_accuracy(value) -> str:
    return f"{value:.2%}" if value is not None else "Không có training metadata khớp"


refresh_col, source_col = st.columns([1, 5])
with refresh_col:
    if st.button("🔄 Làm mới"):
        st.cache_data.clear()
        st.rerun()
with source_col:
    st.caption(f"Nguồn dữ liệu: `{MV_API_URL}/api/model/overview`")

with st.spinner("Đang tải trạng thái model…"):
    try:
        overview = fetch_overview()
    except Exception as exc:
        st.error(f"Không tải được Model Management overview: {exc}")
        st.info("Kiểm tra backend, cấu hình VERTEX_ENDPOINT_ID, GCP_PROJECT/GCP_LOCATION và quyền đọc Vertex AI/BigQuery.")
        st.stop()

endpoint = overview.get("endpoint", {})
deployed_models = overview.get("deployed_models", [])
traffic_split = overview.get("traffic_split", {})
registry_models = overview.get("registry_models", [])
latest_training = overview.get("latest_training")

registry_by_resource = {
    model_key(model.get("resource_name")): model
    for model in registry_models
}

serving_model = max(deployed_models, key=lambda dm: dm.get("traffic_pct", 0), default=None)
serving_registry = registry_by_resource.get(model_key(serving_model.get("model_resource_name") if serving_model else None))
serving_training = serving_registry.get("latest_training") if serving_registry else None

h1, h2, h3, h4 = st.columns(4)
h1.metric("Endpoint", endpoint.get("status", "UNKNOWN"), delta=short_id(endpoint.get("id"), 18))
h2.metric("Models deployed", len(deployed_models))
h3.metric("Registry versions", len(registry_models))
h4.metric(
    "Current serving",
    serving_model.get("display_name", "—") if serving_model else "—",
    delta=f"{serving_model.get('traffic_pct', 0)}% traffic" if serving_model else "no traffic",
)

st.caption(
    f"Project `{endpoint.get('project', '—')}` · Location `{endpoint.get('location', '—')}` · "
    f"Endpoint `{endpoint.get('id', '—')}`"
)

if latest_training:
    st.caption(
        "Lần training mới nhất: "
        f"`{latest_training.get('status', '—')}` · "
        f"Accuracy {fmt_accuracy(latest_training.get('accuracy'))} · "
        f"{fmt_time(latest_training.get('completed_at') or latest_training.get('triggered_at'))}"
    )

st.divider()

if not deployed_models:
    st.info("Chưa có model nào được deploy lên endpoint này.")
else:
    st.subheader("🚦 Traffic hiện tại")
    traffic_left, traffic_right = st.columns([1, 1])

    labels = [dm.get("display_name") or dm.get("id") for dm in deployed_models]
    values = [int(dm.get("traffic_pct", 0)) for dm in deployed_models]

    with traffic_left:
        if sum(values) > 0:
            pie = go.Figure(data=go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>Traffic: %{value}%<extra></extra>",
            ))
            pie.update_layout(height=340, margin=dict(t=20, b=20, l=20, r=20), showlegend=False)
            st.plotly_chart(pie, use_container_width=True)
        else:
            st.info("Endpoint chưa route traffic đến model nào.")

    with traffic_right:
        bar = go.Figure(go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=["#2E9D64" if value > 0 else "#94A3B8" for value in values],
            text=[f"{value}%" for value in values],
            textposition="auto",
            hovertemplate="<b>%{y}</b><br>Traffic: %{x}%<extra></extra>",
        ))
        bar.update_layout(
            height=340,
            xaxis=dict(title="Traffic (%)", range=[0, 100], gridcolor="rgba(128,128,128,0.16)"),
            yaxis=dict(title=""),
            margin=dict(t=20, b=45, l=20, r=20),
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
        )
        st.plotly_chart(bar, use_container_width=True)

    st.subheader("🧭 Trạng thái model đang deploy")
    card_cols = st.columns(min(len(deployed_models), 3))
    for idx, dm in enumerate(deployed_models):
        registry_match = registry_by_resource.get(model_key(dm.get("model_resource_name")))
        training = registry_match.get("latest_training") if registry_match else None
        with card_cols[idx % len(card_cols)]:
            with st.container(border=True):
                st.metric(
                    dm.get("display_name", dm.get("id", "—")),
                    f"{dm.get('traffic_pct', 0)}%",
                    delta=dm.get("serving_status", "UNKNOWN"),
                )
                st.progress(min(max(dm.get("traffic_pct", 0), 0), 100) / 100)
                st.caption(f"Deployed ID: `{short_id(dm.get('id'), 28)}`")
                st.caption(f"Model: `{short_id(dm.get('model_resource_name'), 44)}`")
                if registry_match:
                    st.caption(f"Registry version: `{registry_match.get('version_id') or '—'}`")
                    st.caption(f"Created: {fmt_time(registry_match.get('create_time'))}")
                else:
                    st.caption("Registry: không tìm thấy model registry khớp")
                if training:
                    st.caption(
                        f"Training: `{training.get('status', '—')}` · "
                        f"Accuracy {fmt_accuracy(training.get('accuracy'))}"
                    )
                else:
                    st.caption("Training: Không có training metadata khớp")

st.divider()

if len(deployed_models) >= 2:
    st.subheader("⚖️ Điều chỉnh Traffic Split")
    st.caption("Thay đổi tỉ lệ traffic giữa các model đang deploy. Tổng phải bằng 100%.")

    new_split = {}
    total_set = 0
    split_cols = st.columns(min(len(deployed_models), 4))
    for idx, dm in enumerate(deployed_models):
        with split_cols[idx % len(split_cols)]:
            dm_id = dm["id"]
            value = st.number_input(
                dm.get("display_name", dm_id),
                min_value=0,
                max_value=100,
                value=int(traffic_split.get(dm_id, dm.get("traffic_pct", 0))),
                step=5,
                key=f"split_{dm_id}",
                help=f"Deployed model ID: {dm_id}",
            )
            new_split[dm_id] = value
            total_set += value

    if total_set == 100:
        st.success("Tổng traffic split = 100%. Có thể áp dụng.")
    else:
        st.warning(f"Tổng traffic split hiện là {total_set}. Cần đúng 100 để áp dụng.")

    dm_ids = [dm["id"] for dm in deployed_models]
    col_apply, col_full, col_rollback = st.columns(3)

    with col_apply:
        if st.button("💾 Áp dụng split", type="primary", disabled=(total_set != 100)):
            with st.spinner("Đang cập nhật traffic split…"):
                try:
                    resp = post_traffic_split(new_split)
                    data = resp.json() if resp.content else {}
                    if resp.ok:
                        st.success("Đã cập nhật traffic split.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(f"Lỗi: {data.get('error', resp.text)}")
                except Exception as exc:
                    st.error(f"Lỗi: {exc}")

    with col_full:
        latest_deployed_id = dm_ids[-1] if dm_ids else None
        if latest_deployed_id and st.button("🚀 Promote latest 100%"):
            full_split = {dm_id: (100 if dm_id == latest_deployed_id else 0) for dm_id in dm_ids}
            with st.spinner("Đang promote model mới nhất…"):
                try:
                    resp = post_traffic_split(full_split)
                    if resp.ok:
                        st.success("Đã promote model mới nhất lên 100% traffic.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(f"Lỗi: {resp.json().get('error', resp.text)}")
                except Exception as exc:
                    st.error(f"Lỗi: {exc}")

    with col_rollback:
        oldest_deployed_id = dm_ids[0] if dm_ids else None
        if oldest_deployed_id and st.button("⏪ Rollback v1 100%"):
            rollback_split = {dm_id: (100 if dm_id == oldest_deployed_id else 0) for dm_id in dm_ids}
            with st.spinner("Đang rollback…"):
                try:
                    resp = post_traffic_split(rollback_split)
                    if resp.ok:
                        st.success("Đã rollback về model đầu tiên.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(f"Lỗi: {resp.json().get('error', resp.text)}")
                except Exception as exc:
                    st.error(f"Lỗi: {exc}")
elif len(deployed_models) == 1:
    st.info("Hiện chỉ có 1 model được deploy. Cần deploy thêm version mới để dùng canary traffic split.")

st.divider()

st.subheader("📦 Model Registry")
filter_mode = st.radio(
    "Bộ lọc registry",
    ["Tất cả", "Đang deploy", "Chưa deploy"],
    horizontal=True,
    label_visibility="collapsed",
)

filtered_registry = registry_models
if filter_mode == "Đang deploy":
    filtered_registry = [m for m in registry_models if m.get("is_deployed")]
elif filter_mode == "Chưa deploy":
    filtered_registry = [m for m in registry_models if not m.get("is_deployed")]

if not filtered_registry:
    st.info("Không có model registry phù hợp với bộ lọc hiện tại.")
else:
    registry_rows = []
    for model in filtered_registry:
        training = model.get("latest_training")
        registry_rows.append({
            "Model": model.get("display_name", "—"),
            "Version": model.get("version_id") or "—",
            "Created": fmt_time(model.get("create_time")),
            "Deployed": "Có" if model.get("is_deployed") else "Không",
            "Traffic": f"{model.get('traffic_pct', 0)}%",
            "Serving status": model.get("serving_status", "—"),
            "Training status": training.get("status") if training else "Không có training metadata khớp",
            "Accuracy": fmt_accuracy(training.get("accuracy")) if training else "Không có training metadata khớp",
            "Resource": model.get("resource_name", "—"),
        })

    st.dataframe(registry_rows, use_container_width=True, hide_index=True)
