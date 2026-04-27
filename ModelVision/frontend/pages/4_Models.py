import os

import requests
import streamlit as st

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

st.title("🤖 Model Management")
st.caption("Quản lý phiên bản model và kiểm soát traffic trên Vertex AI Endpoint")
st.divider()

@st.cache_data(ttl=30, show_spinner=False)
def fetch_traffic() -> dict:
    r = requests.get(f"{MV_API_URL}/api/model/traffic", timeout=15)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=60, show_spinner=False)
def fetch_model_list() -> list:
    r = requests.get(f"{MV_API_URL}/api/model/list", timeout=20)
    r.raise_for_status()
    return r.json().get("models", [])

if st.button("🔄 Làm mới"):
    st.cache_data.clear()
    st.rerun()

# ── Current traffic split ──────────────────────────────────────────────────────
st.subheader("🚦 Traffic hiện tại trên Endpoint")
try:
    traffic_data     = fetch_traffic()
    deployed_models  = traffic_data.get("deployed_models", [])
    current_split    = traffic_data.get("traffic_split", {})
    endpoint_id      = traffic_data.get("endpoint_id", "—")

    st.caption(f"Endpoint: `{endpoint_id}`")

    if not deployed_models:
        st.info("Chưa có model nào được deploy lên endpoint này.")
    else:
        cols = st.columns(len(deployed_models))
        for i, dm in enumerate(deployed_models):
            with cols[i]:
                pct = dm.get("traffic_pct", 0)
                st.metric(
                    dm.get("display_name", dm.get("id", "—")),
                    f"{pct}%",
                    delta="active" if pct > 0 else "standby",
                    delta_color="normal" if pct > 0 else "off",
                )
                st.caption(f"`{dm.get('id', '')[:20]}…`")

except Exception as exc:
    st.error(f"Không tải được thông tin traffic: {exc}")
    deployed_models = []
    current_split   = {}

st.divider()

# ── Traffic split control ──────────────────────────────────────────────────────
if len(deployed_models) >= 2:
    st.subheader("⚖️ Điều chỉnh Traffic Split")
    st.caption("Thay đổi tỉ lệ traffic giữa các model version (tổng phải = 100%)")

    dm_ids    = [dm["id"]           for dm in deployed_models]
    dm_names  = [dm.get("display_name", dm["id"]) for dm in deployed_models]

    new_split = {}
    total_set  = 0
    split_cols = st.columns(len(dm_ids))
    for i, (dm_id, dm_name) in enumerate(zip(dm_ids, dm_names)):
        with split_cols[i]:
            current_val = current_split.get(dm_id, 0)
            val = st.number_input(
                f"{dm_name}",
                min_value=0, max_value=100,
                value=int(current_val),
                step=10,
                key=f"split_{dm_id}",
            )
            new_split[dm_id] = val
            total_set += val

    total_label = "✅ Tổng = 100" if total_set == 100 else f"⚠️ Tổng = {total_set} (phải = 100)"
    st.caption(total_label)

    col_apply, col_full, col_rollback = st.columns([2, 2, 2])

    with col_apply:
        if st.button("💾 Áp dụng Traffic Split", type="primary", disabled=(total_set != 100)):
            with st.spinner("Đang cập nhật…"):
                try:
                    resp = requests.post(
                        f"{MV_API_URL}/api/model/traffic",
                        json={"traffic_split": new_split},
                        timeout=30,
                    )
                    data = resp.json()
                    if resp.ok:
                        st.success(f"Đã cập nhật traffic split!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(f"Lỗi: {data.get('error')}")
                except Exception as exc:
                    st.error(f"Lỗi: {exc}")

    with col_full:
        latest_id = dm_ids[-1] if dm_ids else None
        if latest_id and st.button("🚀 Promote latest → 100%"):
            full_split = {dm_id: (100 if dm_id == latest_id else 0) for dm_id in dm_ids}
            with st.spinner("Đang promote…"):
                try:
                    resp = requests.post(
                        f"{MV_API_URL}/api/model/traffic",
                        json={"traffic_split": full_split},
                        timeout=30,
                    )
                    if resp.ok:
                        st.success("Đã promote model mới nhất lên 100% traffic!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(f"Lỗi: {resp.json().get('error')}")
                except Exception as exc:
                    st.error(f"Lỗi: {exc}")

    with col_rollback:
        oldest_id = dm_ids[0] if dm_ids else None
        if oldest_id and st.button("⏪ Rollback → 100% v1"):
            rollback_split = {dm_id: (100 if dm_id == oldest_id else 0) for dm_id in dm_ids}
            with st.spinner("Đang rollback…"):
                try:
                    resp = requests.post(
                        f"{MV_API_URL}/api/model/traffic",
                        json={"traffic_split": rollback_split},
                        timeout=30,
                    )
                    if resp.ok:
                        st.success("Đã rollback về model v1 (100%)!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(f"Lỗi: {resp.json().get('error')}")
                except Exception as exc:
                    st.error(f"Lỗi: {exc}")

elif len(deployed_models) == 1:
    st.info("Hiện chỉ có 1 model được deploy. Train thêm một phiên bản mới để sử dụng canary deployment.")

st.divider()

# ── Model Registry list ────────────────────────────────────────────────────────
st.subheader("📦 Model Registry (Vertex AI)")
try:
    models = fetch_model_list()
    if not models:
        st.info("Chưa có model nào trong registry.")
    else:
        for m in models:
            with st.expander(f"`{m.get('display_name', '—')}` — {(m.get('create_time') or '')[:16]}"):
                st.caption(f"Resource: `{m.get('resource_name', '—')}`")
                if m.get("version_id"):
                    st.caption(f"Version ID: `{m['version_id']}`")
except Exception as exc:
    st.error(f"Không tải được danh sách model: {exc}")
