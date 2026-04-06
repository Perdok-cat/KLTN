"""
Streamlit Frontend – Dashboard chính
Hiển thị thống kê tổng quan về bộ dữ liệu tin tức AI.
"""

import os

import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:5000")

st.set_page_config(
    page_title="AI News Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://img.icons8.com/fluency/96/artificial-intelligence.png",
        width=80,
    )
    st.title("AI News Pipeline")
    st.caption("Hệ thống phân loại & phân tích tin tức trí tuệ nhân tạo")
    st.divider()
    st.page_link("app.py",                    label="📊 Dashboard",      icon="📊")
    st.page_link("pages/1_Tin_Tức.py",        label="📰 Tin tức",        icon="📰")
    st.page_link("pages/2_Dự_Đoán.py",        label="🔍 Dự đoán nhãn",  icon="🔍")
    st.divider()
    api_status = st.empty()


# ── Helper ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def fetch_stats():
    resp = requests.get(f"{API_URL}/api/stats", timeout=10)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=60)
def fetch_recent(limit: int = 6):
    resp = requests.get(f"{API_URL}/api/articles", params={"limit": limit}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def check_api() -> bool:
    try:
        requests.get(f"{API_URL}/api/health", timeout=3)
        return True
    except Exception:
        return False


# ── API status badge ──────────────────────────────────────────────────────────
if check_api():
    api_status.success("✅ Backend đang hoạt động")
else:
    api_status.error("❌ Không kết nối được Backend")
    st.error(
        f"Không thể kết nối tới Backend tại **{API_URL}**.\n\n"
        "Vui lòng chạy: `cd Backend && python app.py`"
    )
    st.stop()


# ── Main content ──────────────────────────────────────────────────────────────
st.title("📊 Bảng điều khiển – AI News Pipeline")
st.caption("Tổng quan về hệ thống phân loại tin tức trí tuệ nhân tạo")
st.divider()

try:
    data = fetch_stats()
except Exception as e:
    st.error(f"Lỗi khi tải dữ liệu: {e}")
    st.stop()

label_dist   = data.get("label_distribution", {})
label_colors = data.get("label_colors", {})
label_icons  = data.get("label_icons", {})
total        = data.get("total", 0)

LABEL_ORDER = ["MARKET SIGNALS", "SOLUTIONS & USE CASES", "DEEP DIVE", "NOISE"]
LABEL_VI = {
    "MARKET SIGNALS":        "Tín hiệu thị trường",
    "SOLUTIONS & USE CASES": "Giải pháp & Ứng dụng",
    "DEEP DIVE":             "Phân tích chuyên sâu",
    "NOISE":                 "Nhiễu",
}

# ── Metric cards ──────────────────────────────────────────────────────────────
cols = st.columns([1.5] + [1] * len(LABEL_ORDER))
with cols[0]:
    st.metric("📰 Tổng số bài viết", f"{total:,}")

for i, label in enumerate(LABEL_ORDER):
    count = label_dist.get(label, 0)
    pct   = f"{count / total * 100:.1f}%" if total else "—"
    icon  = label_icons.get(label, "")
    with cols[i + 1]:
        st.metric(
            f"{icon} {LABEL_VI.get(label, label)}",
            f"{count:,}",
            delta=pct,
            delta_color="off",
        )

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Phân bố nhãn")
    labels_sorted  = [l for l in LABEL_ORDER if l in label_dist]
    values_sorted  = [label_dist[l] for l in labels_sorted]
    colors_sorted  = [label_colors.get(l, "#999") for l in labels_sorted]
    labels_vi      = [f"{label_icons.get(l,'')} {LABEL_VI.get(l, l)}" for l in labels_sorted]

    fig_pie = go.Figure(go.Pie(
        labels=labels_vi,
        values=values_sorted,
        marker_colors=colors_sorted,
        hole=0.4,
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>Số bài: %{value}<br>Tỉ lệ: %{percent}<extra></extra>",
    ))
    fig_pie.update_layout(
        margin=dict(t=20, b=20, l=20, r=20),
        showlegend=False,
        height=300,
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col_right:
    st.subheader("Số bài theo nhãn")
    fig_bar = go.Figure(go.Bar(
        x=labels_vi,
        y=values_sorted,
        marker_color=colors_sorted,
        text=values_sorted,
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Số bài: %{y}<extra></extra>",
    ))
    fig_bar.update_layout(
        yaxis_title="Số bài viết",
        xaxis_tickangle=-15,
        margin=dict(t=20, b=60, l=40, r=20),
        height=300,
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(gridcolor="rgba(128,128,128,0.2)"),
    )
    st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ── Recent articles ───────────────────────────────────────────────────────────
st.subheader("📌 Bài viết gần đây")

try:
    recent = fetch_recent(limit=6)
    articles = recent.get("articles", [])
except Exception as e:
    st.warning(f"Không tải được bài viết: {e}")
    articles = []

if articles:
    card_cols = st.columns(3)
    for i, art in enumerate(articles):
        label  = art.get("label", "")
        color  = label_colors.get(label, "#999")
        icon   = label_icons.get(label, "")
        vi     = LABEL_VI.get(label, label)

        with card_cols[i % 3]:
            with st.container(border=True):
                st.markdown(
                    f'<span style="background:{color};color:white;padding:2px 8px;'
                    f'border-radius:12px;font-size:0.75rem">{icon} {vi}</span>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**{art.get('title', '—')}**")
                st.caption(art.get("snippet", "")[:200])
                if st.button("Xem chi tiết", key=f"btn_{art['id']}"):
                    st.query_params["article_id"] = str(art["id"])
                    st.switch_page("pages/1_Tin_Tức.py")
else:
    st.info("Không có bài viết nào.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("🤖 AI News Pipeline · KLTN 2026")
