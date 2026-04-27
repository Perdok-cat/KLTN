import os

import plotly.graph_objects as go
import requests
import streamlit as st

from utils.gcp_auth import auth_headers

MV_API_URL = os.getenv("MV_API_URL", "http://localhost:5001")

st.set_page_config(page_title="Data Drift · ModelVision", page_icon="📊", layout="wide")

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/artificial-intelligence.png", width=80)
    st.title("ModelVision")
    st.divider()
    st.page_link("app.py",               label="🏠 Tổng quan")
    st.page_link("pages/1_HITL.py",      label="🛡️ HITL Review")
    st.page_link("pages/2_Training.py",  label="📈 Training History")
    st.page_link("pages/3_Drift.py",     label="📊 Data Drift")
    st.page_link("pages/4_Models.py",    label="🤖 Model Management")

st.title("📊 Data Drift")
st.caption("So sánh phân phối nhãn giữa dữ liệu gốc, HITL staging và inference gần đây")
st.divider()

LABEL_VI = {
    "MARKET SIGNALS":        "Tín hiệu thị trường",
    "SOLUTIONS & USE CASES": "Giải pháp & Ứng dụng",
    "DEEP DIVE":             "Phân tích chuyên sâu",
    "NOISE":                 "Nhiễu",
}
LABEL_COLORS = {
    "MARKET SIGNALS":        "#E74C3C",
    "SOLUTIONS & USE CASES": "#27AE60",
    "DEEP DIVE":             "#2980B9",
    "NOISE":                 "#95A5A6",
}

@st.cache_data(ttl=60, show_spinner=False)
def fetch_drift() -> dict:
    r = requests.get(f"{MV_API_URL}/api/drift/summary", headers=auth_headers(), timeout=20)
    r.raise_for_status()
    return r.json()

if st.button("🔄 Làm mới"):
    st.cache_data.clear()
    st.rerun()

with st.spinner("Đang tải dữ liệu drift…"):
    try:
        data = fetch_drift()
    except Exception as exc:
        st.error(f"Không tải được dữ liệu: {exc}")
        st.stop()

orig_dist   = data.get("original_distribution",   {})
hitl_dist   = data.get("hitl_distribution",       {})
recent_dist = data.get("recent_7d_distribution",  {})
drift_pct   = data.get("drift_pct",               {})
total_orig  = data.get("total_original", 0)
total_hitl  = data.get("total_hitl",    0)

m1, m2 = st.columns(2)
m1.metric("📦 Tổng dữ liệu gốc",    f"{total_orig:,}")
m2.metric("🔖 Tổng HITL staging",   f"{total_hitl:,}")
st.divider()

# ── Drift indicators ───────────────────────────────────────────────────────────
st.subheader("⚡ Drift so với dữ liệu gốc (điểm % HITL - Original)")
drift_cols = st.columns(len(drift_pct) or 1)
for i, (label, pct) in enumerate(drift_pct.items()):
    with drift_cols[i]:
        delta_color = "normal" if abs(pct) < 5 else "inverse"
        st.metric(
            LABEL_VI.get(label, label),
            f"{pct:+.1f}%",
            delta=f"{pct:+.1f}% vs original",
            delta_color=delta_color,
        )

st.divider()

# ── Distribution comparison bar chart ─────────────────────────────────────────
st.subheader("📊 So sánh phân phối nhãn")
all_labels = list({*orig_dist.keys(), *hitl_dist.keys(), *recent_dist.keys()})

def to_pct(dist: dict, labels: list) -> list:
    total = sum(dist.values()) or 1
    return [round(dist.get(l, 0) / total * 100, 2) for l in labels]

labels_vi = [LABEL_VI.get(l, l) for l in all_labels]
colors    = [LABEL_COLORS.get(l, "#999") for l in all_labels]

fig = go.Figure()
fig.add_trace(go.Bar(
    name="Original", x=labels_vi, y=to_pct(orig_dist, all_labels),
    marker_color="#2980B9", opacity=0.85,
    text=[f"{v:.1f}%" for v in to_pct(orig_dist, all_labels)],
    textposition="outside",
))
fig.add_trace(go.Bar(
    name="HITL staging", x=labels_vi, y=to_pct(hitl_dist, all_labels),
    marker_color="#E67E22", opacity=0.85,
    text=[f"{v:.1f}%" for v in to_pct(hitl_dist, all_labels)],
    textposition="outside",
))
if recent_dist:
    fig.add_trace(go.Bar(
        name="Inference 7 ngày qua", x=labels_vi, y=to_pct(recent_dist, all_labels),
        marker_color="#27AE60", opacity=0.85,
        text=[f"{v:.1f}%" for v in to_pct(recent_dist, all_labels)],
        textposition="outside",
    ))
fig.update_layout(
    barmode="group",
    height=400,
    yaxis=dict(title="Tỉ lệ (%)", gridcolor="rgba(128,128,128,0.15)"),
    margin=dict(t=20, b=60, l=50, r=20),
    plot_bgcolor="rgba(0,0,0,0)",
    legend=dict(orientation="h", y=1.08),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Raw count table ────────────────────────────────────────────────────────────
st.subheader("📋 Số lượng tuyệt đối")
rows = []
for lbl in all_labels:
    rows.append({
        "Nhãn":           LABEL_VI.get(lbl, lbl),
        "Original":       orig_dist.get(lbl, 0),
        "HITL staging":   hitl_dist.get(lbl, 0),
        "Inference 7d":   recent_dist.get(lbl, 0),
        "Drift (%)":      f"{drift_pct.get(lbl, 0):+.1f}%",
    })
st.dataframe(rows, use_container_width=True, hide_index=True)
