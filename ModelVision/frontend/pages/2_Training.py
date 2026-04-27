import os

import plotly.graph_objects as go
import requests
import streamlit as st

from utils.gcp_auth import auth_headers

MV_API_URL = os.getenv("MV_API_URL", "http://localhost:5001")

st.set_page_config(page_title="Training History · ModelVision", page_icon="📈", layout="wide")

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/artificial-intelligence.png", width=80)
    st.title("ModelVision")
    st.divider()
    st.page_link("app.py",               label="🏠 Tổng quan")
    st.page_link("pages/1_HITL.py",      label="🛡️ HITL Review")
    st.page_link("pages/2_Training.py",  label="📈 Training History")
    st.page_link("pages/3_Drift.py",     label="📊 Data Drift")
    st.page_link("pages/4_Models.py",    label="🤖 Model Management")

st.title("📈 Training History")
st.divider()

STATUS_COLOR = {
    "COMPLETED":            "#27AE60",
    "RUNNING":              "#2980B9",
    "FAILED":               "#E74C3C",
    "SKIPPED_LOW_ACCURACY": "#F39C12",
    "SUBMITTED":            "#95A5A6",
}

@st.cache_data(ttl=30, show_spinner=False)
def fetch_history(limit: int) -> list:
    r = requests.get(f"{MV_API_URL}/api/training/history", headers=auth_headers(), params={"limit": limit}, timeout=15)
    r.raise_for_status()
    return r.json().get("history", [])

limit = st.slider("Số lần training hiển thị", min_value=5, max_value=100, value=20, step=5)

with st.spinner("Đang tải lịch sử training…"):
    try:
        history = fetch_history(limit)
    except Exception as exc:
        st.error(f"Không tải được dữ liệu: {exc}")
        st.stop()

if not history:
    st.info("Chưa có lần training nào được ghi nhận.")
    st.stop()

# ── Summary metrics ────────────────────────────────────────────────────────────
completed = [h for h in history if h["status"] == "COMPLETED"]
latest    = history[0]

m1, m2, m3, m4 = st.columns(4)
m1.metric("📋 Tổng số lần training", len(history))
m2.metric("✅ Thành công",           len(completed))

best_acc = max((h["accuracy"] for h in completed if h.get("accuracy")), default=None)
m3.metric("🎯 Accuracy cao nhất",    f"{best_acc:.2%}" if best_acc else "—")

latest_acc = latest.get("accuracy")
m4.metric(
    "🕐 Lần cuối",
    f"{latest_acc:.2%}" if latest_acc else latest.get("status", "—"),
)

st.divider()

# ── Accuracy trend chart ───────────────────────────────────────────────────────
completed_sorted = sorted(
    [h for h in completed if h.get("accuracy") and h.get("triggered_at")],
    key=lambda x: x["triggered_at"],
)

if completed_sorted:
    st.subheader("📉 Accuracy theo thời gian")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[h["triggered_at"][:10] for h in completed_sorted],
        y=[h["accuracy"]          for h in completed_sorted],
        mode="lines+markers+text",
        text=[f"{h['accuracy']:.2%}" for h in completed_sorted],
        textposition="top center",
        line=dict(color="#2980B9", width=2),
        marker=dict(size=8, color="#2980B9"),
        hovertemplate="<b>%{x}</b><br>Accuracy: %{y:.2%}<br><extra></extra>",
    ))
    fig.update_layout(
        yaxis=dict(tickformat=".0%", range=[0, 1.05], gridcolor="rgba(128,128,128,0.15)"),
        xaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
        height=320,
        margin=dict(t=20, b=40, l=50, r=20),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.divider()

# ── Trigger manual retrain ─────────────────────────────────────────────────────
st.subheader("🚀 Trigger Training thủ công")
force = st.checkbox("Bỏ qua cooldown guard", value=False)
if st.button("🚀 Trigger Retrain", type="primary"):
    with st.spinner("Đang gửi yêu cầu training…"):
        try:
            resp = requests.post(
                f"{MV_API_URL}/api/training/trigger",
                headers=auth_headers(),
                json={"force": force},
                timeout=35,
            )
            data = resp.json()
            if data.get("status") in ("submitted", "SUBMITTED"):
                st.success(f"Training job đã được submit! Status: {data.get('status')}")
            else:
                st.warning(f"Phản hồi: {data}")
        except Exception as exc:
            st.error(f"Lỗi: {exc}")

st.divider()

# ── Detail table ───────────────────────────────────────────────────────────────
st.subheader("📋 Chi tiết các lần training")
for h in history:
    status  = h.get("status", "")
    color   = STATUS_COLOR.get(status, "#95A5A6")
    acc_str = f"{h['accuracy']:.2%}" if h.get("accuracy") else "—"
    date    = (h.get("triggered_at") or "")[:16]

    with st.expander(f"`{date}` — **{status}** — Accuracy: {acc_str}  |  {h.get('best_model', '—')}"):
        c1, c2, c3 = st.columns(3)
        c1.metric("Accuracy",    acc_str)
        c2.metric("Best model",  h.get("best_model") or "—")
        c3.metric("Status",      status)

        c4, c5 = st.columns(2)
        c4.metric("Rows original", h.get("rows_original") or "—")
        c5.metric("Rows HITL",     h.get("rows_hitl")     or "—")

        if h.get("model_resource_name"):
            st.caption(f"Model: `{h['model_resource_name']}`")
        if h.get("endpoint_resource_name"):
            st.caption(f"Endpoint: `{h['endpoint_resource_name']}`")
        if h.get("completed_at"):
            st.caption(f"Hoàn thành: {h['completed_at'][:16]}")
