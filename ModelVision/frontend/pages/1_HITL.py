from __future__ import annotations

import math
import os

import plotly.graph_objects as go
import requests
import streamlit as st

MV_API_URL = os.getenv("MV_API_URL", "http://localhost:5001")

st.set_page_config(
    page_title="HITL Review · ModelVision",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

LABEL_COLORS = {
    "MARKET SIGNALS":        "#E74C3C",
    "SOLUTIONS & USE CASES": "#27AE60",
    "DEEP DIVE":             "#2980B9",
    "NOISE":                 "#95A5A6",
}
LABEL_VI = {
    "MARKET SIGNALS":        "Tín hiệu thị trường",
    "SOLUTIONS & USE CASES": "Giải pháp & Ứng dụng",
    "DEEP DIVE":             "Phân tích chuyên sâu",
    "NOISE":                 "Nhiễu",
}
LABEL_ORDER = ["MARKET SIGNALS", "SOLUTIONS & USE CASES", "DEEP DIVE", "NOISE"]
ALL_LABELS  = ["DEEP DIVE", "MARKET SIGNALS", "NOISE", "SOLUTIONS & USE CASES"]
CONF_NUM    = {"low": 0.20, "medium": 0.55, "high": 0.90}
CONF_COLOR  = {"low": "#E74C3C", "medium": "#F39C12", "high": "#27AE60"}
CONF_ICON   = {"low": "🔴", "medium": "🟡", "high": "🟢"}

st.markdown("""
<style>
footer {visibility: hidden;}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 4px 18px rgba(0,0,0,0.12);
    transition: box-shadow 0.25s ease;
}
</style>
""", unsafe_allow_html=True)

# ── Auth gate ──────────────────────────────────────────────────────────────────
try:
    _cfg          = st.secrets["admin"]
    ADMIN_USERNAME = str(_cfg["username"])
    ADMIN_PASSWORD = str(_cfg["password"])
except Exception:
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1")

if not st.session_state.get("mv_authenticated"):
    st.markdown("<br><br>", unsafe_allow_html=True)
    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.markdown("""
        <div style="text-align:center;padding:8px 0 24px">
            <div style="font-size:3.5rem">🛡️</div>
            <h2 style="margin:8px 0 4px">ModelVision – HITL Review</h2>
            <p style="color:#888;margin:0">Khu vực nội bộ · Yêu cầu xác thực</p>
        </div>
        """, unsafe_allow_html=True)
        with st.form("mv_login_form"):
            username  = st.text_input("Tên đăng nhập", placeholder="admin")
            password  = st.text_input("Mật khẩu", type="password")
            submitted = st.form_submit_button("🔐 Đăng nhập", use_container_width=True, type="primary")
        if submitted:
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                st.session_state["mv_authenticated"] = True
                st.session_state["mv_user"]          = username
                st.rerun()
            else:
                st.error("Sai tên đăng nhập hoặc mật khẩu.", icon="🚫")
    st.stop()

# ── Session defaults ───────────────────────────────────────────────────────────
for k, v in {"hitl_page": 1, "hitl_actioned": set(), "hitl_cache": None, "main_cache": None}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/artificial-intelligence.png", width=80)
    st.title("ModelVision")
    st.caption(f"👤 {st.session_state.get('mv_user', 'Admin')}")
    st.divider()
    st.page_link("app.py",               label="🏠 Tổng quan")
    st.page_link("pages/1_HITL.py",      label="🛡️ HITL Review")
    st.page_link("pages/2_Training.py",  label="📈 Training History")
    st.page_link("pages/3_Drift.py",     label="📊 Data Drift")
    st.page_link("pages/4_Models.py",    label="🤖 Model Management")
    st.divider()
    page_size = st.select_slider("Bài/trang", options=[5, 10, 20], value=10)
    st.divider()
    if st.button("🚪 Đăng xuất", use_container_width=True):
        st.session_state["mv_authenticated"] = False
        st.rerun()

# ── API helpers ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def fetch_hitl_stats() -> dict:
    return requests.get(f"{MV_API_URL}/api/hitl/stats", timeout=10).json()

@st.cache_data(ttl=30, show_spinner=False)
def fetch_pending(page: int, limit: int) -> dict:
    return requests.get(f"{MV_API_URL}/api/hitl/pending", params={"page": page, "limit": limit}, timeout=15).json()

def post_review(article_id: str, action: str, corrected_label: str | None = None) -> dict:
    payload: dict = {"action": action}
    if corrected_label:
        payload["corrected_label"] = corrected_label
    r = requests.post(f"{MV_API_URL}/api/hitl/review/{article_id}", json=payload, timeout=10)
    r.raise_for_status()
    return r.json()

# ── Render helpers ─────────────────────────────────────────────────────────────
def label_badge(label: str) -> str:
    color = LABEL_COLORS.get(label, "#999")
    vi    = LABEL_VI.get(label, label)
    return (
        f'<span style="background:{color};color:#fff;padding:3px 11px;'
        f'border-radius:12px;font-size:0.73rem;font-weight:600">{vi}</span>'
    )

def conf_to_float(raw: str | None) -> float:
    if not raw:
        return 0.5
    k = str(raw).lower()
    if k in CONF_NUM:
        return CONF_NUM[k]
    try:
        return min(max(float(raw), 0.0), 1.0)
    except ValueError:
        return 0.5

def progress_bar_html(conf_raw: str | None) -> str:
    val   = conf_to_float(conf_raw)
    key   = str(conf_raw or "").lower()
    color = CONF_COLOR.get(key, "#F39C12")
    icon  = CONF_ICON.get(key, "🟡")
    pct   = val * 100
    return f"""
    <div style="margin:6px 0 10px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="font-size:0.75rem;color:#555">Độ tin cậy AI:</span>
            <span style="font-size:0.75rem;font-weight:700;color:{color}">{icon} {str(conf_raw or "—").upper()}</span>
        </div>
        <div style="background:#e9ecef;border-radius:6px;height:8px;overflow:hidden">
            <div style="width:{pct:.0f}%;background:{color};height:100%;border-radius:6px"></div>
        </div>
    </div>"""

# ── Page header ────────────────────────────────────────────────────────────────
st.title("🛡️ HITL Review")

try:
    hitl = fetch_hitl_stats()
    st.session_state["hitl_cache"] = hitl
except Exception as exc:
    st.warning(f"Không tải được HITL stats: {exc}")
    hitl = st.session_state["hitl_cache"] or {}

pending_count  = hitl.get("pending_count",  0)
reviewed_today = hitl.get("reviewed_today", 0)
approved_total = hitl.get("approved_total", 0)
rejected_total = hitl.get("rejected_total", 0)
total_articles = hitl.get("total_articles", 0)
reviewed_all   = approved_total + rejected_total
noise_ratio    = rejected_total / reviewed_all * 100 if reviewed_all else 0.0
coverage_pct   = reviewed_all / total_articles * 100 if total_articles else 0.0

tab_overview, tab_queue = st.tabs(["📊 Tổng quan", "📋 Hàng chờ duyệt"])

# ════════════════════════════════════════════════
# TAB 1 – TỔNG QUAN
# ════════════════════════════════════════════════
with tab_overview:
    st.divider()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("⏳ Chờ duyệt",         f"{pending_count:,}")
    m2.metric("✅ Đã duyệt hôm nay",  f"{reviewed_today:,}")
    m3.metric("🗑️ Tỉ lệ Nhiễu",       f"{noise_ratio:.1f}%")
    m4.metric("👍 Tổng Approved",     f"{approved_total:,}")
    m5.metric("📰 Tổng bài viết",     f"{total_articles:,}")
    st.divider()

    gc, rc, lc = st.columns(3)

    with gc:
        st.subheader("Độ phủ duyệt")
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=coverage_pct,
            number={"suffix": "%", "font": {"size": 44}},
            gauge={
                "axis":      {"range": [0, 100], "ticksuffix": "%"},
                "bar":       {"color": "#2980B9", "thickness": 0.28},
                "bgcolor":   "white",
                "steps": [
                    {"range": [0,  40], "color": "#FADBD8"},
                    {"range": [40, 75], "color": "#FAD7A0"},
                    {"range": [75, 100],"color": "#D5F5E3"},
                ],
                "threshold": {"line": {"color": "#27AE60", "width": 3}, "thickness": 0.8, "value": 80},
            },
        ))
        fig.update_layout(height=260, margin=dict(t=30, b=10, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"**{reviewed_all:,}** / {total_articles:,} bài đã được xem xét")

    with rc:
        st.subheader("Trạng thái duyệt")
        fig = go.Figure(go.Pie(
            labels=["⏳ Chờ duyệt", "✅ Approved", "🗑️ Rejected"],
            values=[pending_count, approved_total, rejected_total],
            marker_colors=["#95A5A6", "#27AE60", "#E74C3C"],
            hole=0.52, textinfo="percent+value",
        ))
        fig.update_layout(height=260, margin=dict(t=10, b=10, l=0, r=0), showlegend=True,
                          legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"))
        st.plotly_chart(fig, use_container_width=True)

    with lc:
        st.subheader("Tiến độ hôm nay")
        daily_pct = min(reviewed_today / pending_count * 100, 100) if pending_count > 0 else 100.0
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=daily_pct,
            number={"suffix": "%", "font": {"size": 44}},
            gauge={
                "axis":    {"range": [0, 100]},
                "bar":     {"color": "#27AE60", "thickness": 0.28},
                "bgcolor": "white",
            },
        ))
        fig.update_layout(height=260, margin=dict(t=30, b=10, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Đã duyệt **{reviewed_today:,}** / {pending_count:,} bài chờ")

    st.divider()
    st.caption(f"🛡️ HITL Review · ModelVision · KLTN 2026  |  Tổng bài: **{total_articles:,}**")

# ════════════════════════════════════════════════
# TAB 2 – HÀNG CHỜ DUYỆT
# ════════════════════════════════════════════════
with tab_queue:
    st.divider()
    with st.spinner("Đang tải danh sách bài chờ duyệt…"):
        try:
            result = fetch_pending(st.session_state["hitl_page"], page_size)
        except Exception as exc:
            st.error(f"Không tải được danh sách: {exc}")
            result = {"articles": [], "total": 0, "page": 1}

    all_articles  = result.get("articles", [])
    total_pending = result.get("total",    0)
    cur_page      = result.get("page",     1)
    total_pages   = max(1, math.ceil(total_pending / page_size))
    visible       = [a for a in all_articles if a["id"] not in st.session_state["hitl_actioned"]]

    hdr_c, ref_c = st.columns([7, 1])
    with hdr_c:
        st.subheader(f"📋 Hàng chờ duyệt · {total_pending:,} bài · Trang {cur_page}/{total_pages}")
    with ref_c:
        if st.button("🔄 Làm mới", use_container_width=True):
            st.session_state["hitl_actioned"] = set()
            st.session_state["hitl_page"]     = 1
            st.cache_data.clear()
            st.rerun()

    if not visible:
        if total_pending == 0:
            st.success("🎉 Không còn bài nào chờ duyệt.")
        else:
            st.info("Tất cả bài trang này đã xử lý. Nhấn **Trang sau** hoặc **Làm mới**.")

    for art in visible:
        article_id = art["id"]
        ai_label   = art.get("ai_predicted_label", "")
        conf_raw   = art.get("ai_confidence_score", "")
        title      = art.get("title") or "—"
        source_url = art.get("source_url", "")

        with st.container(border=True):
            left_col, right_col = st.columns([6, 2], gap="large")
            with left_col:
                if source_url:
                    st.markdown(f"#### [{title}]({source_url})")
                else:
                    st.markdown(f"#### {title}")
                parts = [label_badge(ai_label)]
                if art.get("source"):
                    parts.append(f'<span style="color:#888;font-size:0.78rem;margin-left:8px">🌐 {art["source"]}</span>')
                if art.get("pub_date"):
                    parts.append(f'<span style="color:#aaa;font-size:0.73rem;margin-left:8px">📅 {str(art["pub_date"])[:16]}</span>')
                st.markdown(" ".join(parts), unsafe_allow_html=True)
                if art.get("content_snippet"):
                    st.caption(art["content_snippet"][:220])
                st.markdown(progress_bar_html(conf_raw), unsafe_allow_html=True)

            with right_col:
                st.markdown("**Hành động:**")
                if st.button("✅ Approve", key=f"a_{article_id}", type="primary", use_container_width=True):
                    with st.spinner("Đang ghi nhận…"):
                        try:
                            post_review(article_id, "Accept")
                            st.session_state["hitl_actioned"].add(article_id)
                            fetch_pending.clear()
                            st.toast(f"✅ Approved: {title[:45]}…", icon="✅")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Lỗi: {exc}")

                if st.button("🗑️ Reject as Noise", key=f"r_{article_id}", use_container_width=True):
                    with st.spinner("Đang ghi nhận…"):
                        try:
                            post_review(article_id, "Reject")
                            st.session_state["hitl_actioned"].add(article_id)
                            fetch_pending.clear()
                            st.toast(f"🗑️ Rejected: {title[:45]}…", icon="🗑️")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Lỗi: {exc}")

                st.markdown("**Sửa nhãn:**")
                corrected = st.selectbox(
                    "Chọn nhãn đúng",
                    options=ALL_LABELS,
                    index=ALL_LABELS.index(ai_label) if ai_label in ALL_LABELS else 0,
                    format_func=lambda lb: LABEL_VI.get(lb, lb),
                    key=f"s_{article_id}",
                    label_visibility="collapsed",
                )
                if st.button("💾 Lưu nhãn mới", key=f"c_{article_id}", use_container_width=True):
                    with st.spinner("Đang ghi nhận…"):
                        try:
                            post_review(article_id, "Correct", corrected_label=corrected)
                            st.session_state["hitl_actioned"].add(article_id)
                            fetch_pending.clear()
                            st.toast(f"✏️ Sửa → {LABEL_VI.get(corrected, corrected)}: {title[:35]}…", icon="✏️")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Lỗi: {exc}")

    st.divider()
    pg_prev, pg_info, pg_next = st.columns([1, 2, 1])
    with pg_prev:
        if st.button("⬅ Trang trước", disabled=cur_page <= 1, use_container_width=True):
            st.session_state["hitl_page"]     = cur_page - 1
            st.session_state["hitl_actioned"] = set()
            st.rerun()
    with pg_info:
        st.markdown(
            f"<div style='text-align:center;padding:8px 0'>Trang <b>{cur_page}</b> / <b>{total_pages}</b>"
            f" &nbsp;·&nbsp; <span style='color:#888'>{total_pending:,} bài chờ</span></div>",
            unsafe_allow_html=True,
        )
    with pg_next:
        if st.button("Trang sau ➡", disabled=cur_page >= total_pages, use_container_width=True):
            st.session_state["hitl_page"]     = cur_page + 1
            st.session_state["hitl_actioned"] = set()
            st.rerun()
