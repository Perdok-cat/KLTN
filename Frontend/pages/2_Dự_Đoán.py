"""
Streamlit – Trang dự đoán nhãn
Nhập văn bản và nhận kết quả phân loại từ mô hình ML.
"""

import os

import plotly.graph_objects as go
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:5000")

st.set_page_config(
    page_title="Dự đoán nhãn",
    page_icon="🔍",
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
    st.divider()
    st.page_link("app.py",                    label="📊 Dashboard",     icon="📊")
    st.page_link("pages/1_Tin_Tức.py",        label="📰 Tin tức",       icon="📰")
    st.page_link("pages/2_Dự_Đoán.py",        label="🔍 Dự đoán nhãn", icon="🔍")
    st.divider()

    st.info(
        "**Cách sử dụng:**\n"
        "1. Dán tiêu đề hoặc nội dung bài báo vào ô văn bản\n"
        "2. Nhấn **Dự đoán**\n"
        "3. Xem nhãn phân loại và điểm tin cậy"
    )

# ── Constants ─────────────────────────────────────────────────────────────────
LABEL_COLORS = {
    "MARKET SIGNALS":       "#E74C3C",
    "SOLUTIONS & USE CASES":"#27AE60",
    "DEEP DIVE":            "#2980B9",
    "NOISE":                "#95A5A6",
}
LABEL_VI = {
    "MARKET SIGNALS":        "Tín hiệu thị trường",
    "SOLUTIONS & USE CASES": "Giải pháp & Ứng dụng",
    "DEEP DIVE":             "Phân tích chuyên sâu",
    "NOISE":                 "Nhiễu",
}
LABEL_DESC = {
    "MARKET SIGNALS":        "Bài viết phản ánh xu hướng thị trường, đầu tư, tác động kinh tế của AI.",
    "SOLUTIONS & USE CASES": "Bài viết mô tả ứng dụng cụ thể, sản phẩm hoặc giải pháp AI thực tế.",
    "DEEP DIVE":             "Bài viết phân tích chuyên sâu về kỹ thuật, nghiên cứu hoặc thuật toán AI.",
    "NOISE":                 "Bài viết không liên quan trực tiếp hoặc có giá trị thông tin thấp về AI.",
}

EXAMPLES = [
    {
        "title": "Ví dụ: Tín hiệu thị trường",
        "text":  (
            "OpenAI huy động thêm 10 tỷ USD trong vòng gọi vốn mới nhất, "
            "nâng định giá công ty lên 300 tỷ USD. Các nhà đầu tư bao gồm Microsoft "
            "và Thrive Capital đã tham gia vào vòng gọi vốn này."
        ),
    },
    {
        "title": "Ví dụ: Giải pháp & Ứng dụng",
        "text":  (
            "Bệnh viện Bạch Mai triển khai hệ thống AI hỗ trợ chẩn đoán ung thư "
            "phổi qua ảnh CT với độ chính xác 94%, giúp bác sĩ phát hiện sớm tổn thương "
            "và rút ngắn thời gian đọc kết quả từ 2 giờ xuống còn 10 phút."
        ),
    },
    {
        "title": "Ví dụ: Phân tích chuyên sâu",
        "text":  (
            "Nghiên cứu mới về kiến trúc Transformer cho thấy cơ chế attention "
            "multi-head có thể được tối ưu bằng cách giảm số lượng head từ 16 xuống 8 "
            "mà không ảnh hưởng đến hiệu suất, đồng thời giảm 30% chi phí tính toán."
        ),
    },
]

# ── Main content ──────────────────────────────────────────────────────────────
st.title("🔍 Dự đoán nhãn bài viết")
st.caption("Sử dụng mô hình TF-IDF + LinearSVC được huấn luyện trên dữ liệu tin tức AI tiếng Việt")
st.divider()

col_input, col_result = st.columns([1, 1], gap="large")

with col_input:
    st.subheader("📝 Nhập văn bản")

    # Quick example buttons
    ex_cols = st.columns(len(EXAMPLES))
    for i, ex in enumerate(EXAMPLES):
        with ex_cols[i]:
            if st.button(ex["title"], use_container_width=True):
                st.session_state["input_text"] = ex["text"]

    input_text = st.text_area(
        "Tiêu đề hoặc nội dung bài báo",
        value=st.session_state.get("input_text", ""),
        height=280,
        placeholder="Nhập hoặc dán nội dung bài viết tiếng Việt vào đây…",
        label_visibility="collapsed",
    )
    st.session_state["input_text"] = input_text

    char_count = len(input_text)
    st.caption(f"{char_count} ký tự")

    predict_btn = st.button(
        "🚀 Dự đoán",
        type="primary",
        disabled=char_count < 10,
        use_container_width=True,
    )

    if char_count < 10 and char_count > 0:
        st.warning("Văn bản quá ngắn. Vui lòng nhập ít nhất 10 ký tự.")


with col_result:
    st.subheader("📊 Kết quả dự đoán")

    result_placeholder = st.empty()

    if predict_btn and char_count >= 10:
        with st.spinner("Đang phân tích văn bản…"):
            try:
                resp = requests.post(
                    f"{API_URL}/api/predict",
                    json={"text": input_text},
                    timeout=30,
                )
                resp.raise_for_status()
                result = resp.json()
            except requests.exceptions.ConnectionError:
                result_placeholder.error(
                    "Không kết nối được Backend.\n\n"
                    "Vui lòng chạy: `cd Backend && python app.py`"
                )
                st.stop()
            except Exception as e:
                result_placeholder.error(f"Lỗi dự đoán: {e}")
                st.stop()

        label    = result.get("label", "NOISE")
        icon     = result.get("icon", "")
        color    = result.get("color", LABEL_COLORS.get(label, "#999"))
        label_vi = LABEL_VI.get(label, label)
        desc     = LABEL_DESC.get(label, "")

        with result_placeholder.container():
            # Main label badge
            st.markdown(
                f"""
                <div style="
                    background: {color}18;
                    border: 2px solid {color};
                    border-radius: 12px;
                    padding: 24px;
                    text-align: center;
                    margin-bottom: 16px;
                ">
                    <div style="font-size: 3rem">{icon}</div>
                    <div style="font-size: 1.4rem; font-weight: 700; color: {color}; margin: 8px 0">
                        {label_vi}
                    </div>
                    <div style="font-size: 0.8rem; color: #888; font-family: monospace">
                        {label}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(desc)

            # Decision scores chart
            scores_raw = result.get("confidence") or result.get("decision_scores")
            if scores_raw:
                is_proba = "confidence" in result
                score_label = "Xác suất" if is_proba else "Điểm quyết định"

                labels_list = list(LABEL_VI.keys())
                values      = [scores_raw.get(l, 0.0) for l in labels_list]
                labels_vi_list = [LABEL_VI.get(l, l) for l in labels_list]
                colors_list    = [LABEL_COLORS.get(l, "#999") for l in labels_list]
                highlight      = ["rgba(0,0,0,0.15)" if l != label else color for l in labels_list]

                fig = go.Figure(go.Bar(
                    x=labels_vi_list,
                    y=values,
                    marker_color=colors_list,
                    marker_line_color=highlight,
                    marker_line_width=3,
                    text=[f"{v:.3f}" for v in values],
                    textposition="outside",
                    hovertemplate="<b>%{x}</b><br>" + score_label + ": %{y:.4f}<extra></extra>",
                ))
                fig.update_layout(
                    title=f"{score_label} theo từng nhãn",
                    yaxis_title=score_label,
                    xaxis_tickangle=-15,
                    margin=dict(t=40, b=60, l=40, r=20),
                    height=280,
                    plot_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
                )
                st.plotly_chart(fig, use_container_width=True)

    elif not predict_btn:
        with result_placeholder.container():
            st.markdown(
                """
                <div style="
                    border: 2px dashed #ddd;
                    border-radius: 12px;
                    padding: 48px;
                    text-align: center;
                    color: #aaa;
                ">
                    <div style="font-size: 3rem">🤖</div>
                    <div style="margin-top: 12px">Nhập văn bản và nhấn <b>Dự đoán</b> để xem kết quả</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# ── Label legend ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("📖 Giải thích các nhãn")

leg_cols = st.columns(4)
for i, (label, desc) in enumerate(LABEL_DESC.items()):
    color = LABEL_COLORS[label]
    icon  = {"MARKET SIGNALS": "📈", "SOLUTIONS & USE CASES": "🛠️",
              "DEEP DIVE": "🔬", "NOISE": "🔇"}[label]
    with leg_cols[i]:
        with st.container(border=True):
            st.markdown(
                f'<span style="color:{color};font-size:1.5rem">{icon}</span>',
                unsafe_allow_html=True,
            )
            st.markdown(f"**{LABEL_VI[label]}**")
            st.caption(f"`{label}`")
            st.markdown(desc)
