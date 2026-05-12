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
st.caption("Phân tích chi tiết phân phối nhãn giữa dữ liệu gốc, HITL staging và inference 7 ngày gần đây")
st.divider()

LABEL_ORDER = ["DEEP DIVE", "MARKET SIGNALS", "NOISE", "SOLUTIONS & USE CASES"]
LABEL_VI = {
    "MARKET SIGNALS":        "Tín hiệu thị trường",
    "SOLUTIONS & USE CASES": "Giải pháp & Ứng dụng",
    "DEEP DIVE":             "Phân tích chuyên sâu",
    "NOISE":                 "Nhiễu",
}
LABEL_COLORS = {
    "MARKET SIGNALS":        "#D94A3A",
    "SOLUTIONS & USE CASES": "#2E9D64",
    "DEEP DIVE":             "#2F6FDB",
    "NOISE":                 "#8A949E",
}
DATASET_COLORS = {
    "Original":      "#2F6FDB",
    "HITL staging":  "#D9822B",
    "Inference 7d":  "#2E9D64",
}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_drift() -> dict:
    r = requests.get(f"{MV_API_URL}/api/drift/summary", headers=auth_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def ordered_labels(*distributions: dict) -> list:
    present = set()
    for dist in distributions:
        present.update(dist.keys())
    known = [label for label in LABEL_ORDER if label in present]
    unknown = sorted(label for label in present if label not in LABEL_ORDER)
    return known + unknown


def pct(dist: dict, label: str) -> float:
    total = sum(dist.values()) or 1
    return round(dist.get(label, 0) / total * 100, 2)


def drift_level(value: float) -> str:
    abs_value = abs(value)
    if abs_value < 5:
        return "Ổn định"
    if abs_value <= 10:
        return "Cần theo dõi"
    return "Lệch mạnh"


def drift_note(value: float) -> str:
    if abs(value) < 5:
        return "Trong ngưỡng"
    if value > 0:
        return "HITL đang cao hơn dữ liệu gốc"
    return "HITL đang thấp hơn dữ liệu gốc"


def drift_color(value: float) -> str:
    if abs(value) < 5:
        return "#2E9D64"
    if abs(value) <= 10:
        return "#D9822B"
    return "#C0392B"


refresh_col, status_col = st.columns([1, 5])
with refresh_col:
    if st.button("🔄 Làm mới"):
        st.cache_data.clear()
        st.rerun()
with status_col:
    st.caption(f"Nguồn dữ liệu: `{MV_API_URL}/api/drift/summary`")

with st.spinner("Đang tải dữ liệu drift…"):
    try:
        data = fetch_drift()
    except Exception as exc:
        st.error(f"Không tải được dữ liệu drift: {exc}")
        st.stop()

orig_dist = data.get("original_distribution", {})
hitl_dist = data.get("hitl_distribution", {})
recent_dist = data.get("recent_7d_distribution", {})
drift_pct = data.get("drift_pct", {})
total_orig = data.get("total_original", 0)
total_hitl = data.get("total_hitl", 0)
total_recent = sum(recent_dist.values())

labels = ordered_labels(orig_dist, hitl_dist, recent_dist)
if not labels:
    st.info("Chưa có dữ liệu phân phối nhãn để phân tích drift.")
    st.stop()

rows = []
for label in labels:
    original_pct = pct(orig_dist, label)
    hitl_pct = pct(hitl_dist, label)
    recent_pct = pct(recent_dist, label)
    drift_value = drift_pct.get(label, round(hitl_pct - original_pct, 2))
    rows.append({
        "Nhãn": LABEL_VI.get(label, label),
        "Original count": orig_dist.get(label, 0),
        "Original %": original_pct,
        "HITL count": hitl_dist.get(label, 0),
        "HITL %": hitl_pct,
        "Inference 7d count": recent_dist.get(label, 0),
        "Inference 7d %": recent_pct,
        "Drift điểm %": drift_value,
        "Mức drift": drift_level(drift_value),
        "Nhận định": drift_note(drift_value),
    })

risky_labels = [row for row in rows if abs(row["Drift điểm %"]) >= 5]
strong_labels = [row for row in rows if abs(row["Drift điểm %"]) > 10]
max_row = max(rows, key=lambda row: abs(row["Drift điểm %"]))

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("📦 Original", f"{total_orig:,}")
k2.metric("🔖 HITL staging", f"{total_hitl:,}")
k3.metric("🕐 Inference 7d", f"{total_recent:,}")
k4.metric("⚠️ Nhãn cần theo dõi", f"{len(risky_labels)}", delta=f"{len(strong_labels)} lệch mạnh")
k5.metric("📌 Lệch lớn nhất", max_row["Nhãn"], delta=f"{max_row['Drift điểm %']:+.1f} điểm %")

st.divider()

st.subheader("📊 So sánh tỷ lệ nhãn")
labels_vi = [LABEL_VI.get(label, label) for label in labels]

fig = go.Figure()
for dataset_name, dist in (
    ("Original", orig_dist),
    ("HITL staging", hitl_dist),
    ("Inference 7d", recent_dist),
):
    values = [pct(dist, label) for label in labels]
    fig.add_trace(go.Bar(
        name=dataset_name,
        x=labels_vi,
        y=values,
        marker_color=DATASET_COLORS[dataset_name],
        text=[f"{value:.1f}%" for value in values],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{y:.2f}%<extra></extra>",
    ))

fig.update_layout(
    barmode="group",
    height=420,
    yaxis=dict(title="Tỷ lệ trong từng dataset (%)", gridcolor="rgba(128,128,128,0.16)", rangemode="tozero"),
    xaxis=dict(title=""),
    margin=dict(t=20, b=70, l=50, r=20),
    plot_bgcolor="rgba(0,0,0,0)",
    legend=dict(orientation="h", y=1.1),
)
st.plotly_chart(fig, use_container_width=True)

left, right = st.columns([1.1, 1])

with left:
    st.subheader("⚡ Mức lệch HITL so với Original")
    sorted_rows = sorted(rows, key=lambda row: abs(row["Drift điểm %"]), reverse=True)
    delta_fig = go.Figure()
    delta_fig.add_trace(go.Bar(
        x=[row["Drift điểm %"] for row in sorted_rows],
        y=[row["Nhãn"] for row in sorted_rows],
        orientation="h",
        marker_color=[drift_color(row["Drift điểm %"]) for row in sorted_rows],
        text=[f"{row['Drift điểm %']:+.1f}" for row in sorted_rows],
        textposition="auto",
        hovertemplate="<b>%{y}</b><br>Drift: %{x:+.2f} điểm %<extra></extra>",
    ))
    delta_fig.add_vline(x=0, line_width=1, line_dash="dash", line_color="#64748B")
    delta_fig.update_layout(
        height=340,
        xaxis=dict(title="Điểm phần trăm", gridcolor="rgba(128,128,128,0.16)"),
        yaxis=dict(title="", autorange="reversed"),
        margin=dict(t=20, b=45, l=20, r=20),
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    st.plotly_chart(delta_fig, use_container_width=True)

with right:
    st.subheader("🌡️ Heatmap phân phối")
    heatmap_values = [
        [pct(orig_dist, label) for label in labels],
        [pct(hitl_dist, label) for label in labels],
        [pct(recent_dist, label) for label in labels],
    ]
    heatmap_fig = go.Figure(data=go.Heatmap(
        z=heatmap_values,
        x=labels_vi,
        y=["Original", "HITL staging", "Inference 7d"],
        colorscale=[
            [0.0, "#F8FAFC"],
            [0.45, "#93C5FD"],
            [1.0, "#1D4ED8"],
        ],
        text=[[f"{value:.1f}%" for value in row] for row in heatmap_values],
        texttemplate="%{text}",
        hovertemplate="<b>%{y}</b><br>%{x}: %{z:.2f}%<extra></extra>",
        colorbar=dict(title="%"),
    ))
    heatmap_fig.update_layout(
        height=340,
        margin=dict(t=20, b=70, l=20, r=20),
        xaxis=dict(title=""),
        yaxis=dict(title=""),
    )
    st.plotly_chart(heatmap_fig, use_container_width=True)

st.divider()

st.subheader("📋 Bảng phân tích chi tiết theo nhãn")
st.dataframe(
    rows,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Original %": st.column_config.NumberColumn("Original %", format="%.2f%%"),
        "HITL %": st.column_config.NumberColumn("HITL %", format="%.2f%%"),
        "Inference 7d %": st.column_config.NumberColumn("Inference 7d %", format="%.2f%%"),
        "Drift điểm %": st.column_config.NumberColumn("Drift điểm %", format="%+.2f"),
    },
)

st.caption("Ngưỡng drift: dưới 5 điểm % là ổn định, 5-10 điểm % cần theo dõi, trên 10 điểm % là lệch mạnh.")
