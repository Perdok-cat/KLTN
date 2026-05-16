import os

import requests
import streamlit as st

from utils.gcp_auth import auth_headers

MV_API_URL = os.getenv("MV_API_URL", "http://localhost:5001")

st.set_page_config(
    page_title="ModelVision",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/artificial-intelligence.png", width=80)
    st.title("ModelVision")
    st.caption("Internal MLOps Dashboard · AI News Pipeline")
    st.divider()
    st.page_link("app.py",                                   label="🏠 Tổng quan")
    st.page_link("pages/1_HITL.py",                          label="🛡️ HITL Review")
    st.page_link("pages/2_Training.py",                      label="📈 Training History")
    st.page_link("pages/3_Drift.py",                         label="📊 Data Drift")
    st.page_link("pages/4_Models.py",                        label="🤖 Model Management")
    st.page_link("pages/5_LLM_Monitor.py",                   label="🧠 LLM Monitor")
    st.divider()
    api_badge = st.empty()

try:
    r = requests.get(f"{MV_API_URL}/api/health", headers=auth_headers(), timeout=3)
    if r.ok:
        api_badge.success("✅ Backend kết nối")
    else:
        api_badge.error("❌ Backend lỗi")
except Exception:
    api_badge.error("❌ Không kết nối được Backend")

st.title("🔭 ModelVision – Tổng quan hệ thống")
st.caption("Theo dõi HITL, training, data drift và model deployment")
st.divider()

col1, col2, col3, col4 = st.columns(4)

# ── HITL stats ─────────────────────────────────────────────────────────────────
try:
    hitl = requests.get(f"{MV_API_URL}/api/hitl/stats", headers=auth_headers(), timeout=10).json()
except Exception:
    hitl = {}

with col1:
    st.metric("⏳ Chờ HITL duyệt",    hitl.get("pending_count", "—"))
with col2:
    st.metric("✅ Đã duyệt hôm nay",  hitl.get("reviewed_today", "—"))

# ── Latest training run ────────────────────────────────────────────────────────
try:
    hist = requests.get(f"{MV_API_URL}/api/training/history", headers=auth_headers(), params={"limit": 1}, timeout=10).json()
    latest = hist.get("history", [{}])[0]
except Exception:
    latest = {}

with col3:
    acc = latest.get("accuracy")
    st.metric("🎯 Accuracy (lần cuối)", f"{acc:.2%}" if acc else "—")
with col4:
    st.metric("📋 Training status", latest.get("status", "—"))

st.divider()

# ── Drift quick view ───────────────────────────────────────────────────────────
try:
    drift = requests.get(f"{MV_API_URL}/api/drift/summary", headers=auth_headers(), timeout=15).json()
    d_pct = drift.get("drift_pct", {})
    if d_pct:
        st.subheader("📊 Drift nhanh (HITL vs Original, %)")
        drift_cols = st.columns(len(d_pct))
        for i, (label, pct) in enumerate(d_pct.items()):
            color   = "normal" if abs(pct) < 5 else ("inverse" if pct < 0 else "off")
            with drift_cols[i]:
                st.metric(label, f"{pct:+.1f}%", delta_color=color)
except Exception:
    st.info("Chưa tải được dữ liệu drift. Xem chi tiết tại trang Data Drift.")

st.divider()
st.caption("🔭 ModelVision · KLTN 2026")
