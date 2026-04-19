"""
Streamlit – Admin Dashboard (HITL Control Panel)
Khu vực dành riêng cho quản trị viên. Yêu cầu đăng nhập.
"""
from __future__ import annotations

import math
import os

import plotly.graph_objects as go
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:5000")

st.set_page_config(
    page_title="Admin Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Constants ──────────────────────────────────────────────────────────────────
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

# ── Load admin credentials (secrets → env → hardcoded fallback) ────────────────
try:
    _cfg          = st.secrets["admin"]
    ADMIN_USERNAME = str(_cfg["username"])
    ADMIN_PASSWORD = str(_cfg["password"])
except Exception:
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1")

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Hide the default Streamlit footer on this admin page */
    footer {visibility: hidden;}
    /* Hover lift for article cards */
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow: 0 4px 18px rgba(0,0,0,0.12);
        transition: box-shadow 0.25s ease;
    }
    [data-testid="stVerticalBlockBorderWrapper"] .stButton > button {
        border-radius: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ══════════════════════════════════════════════════════════════════════════════
# AUTH GATE – Phải đăng nhập mới thấy nội dung phía dưới
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("admin_authenticated"):
    # Full-page login card
    st.markdown("<br><br>", unsafe_allow_html=True)
    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.markdown(
            """
            <div style="text-align:center;padding:8px 0 24px">
                <div style="font-size:3.5rem">🛡️</div>
                <h2 style="margin:8px 0 4px">Admin Dashboard</h2>
                <p style="color:#888;margin:0">AI News Pipeline · Khu vực quản trị viên</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("admin_login_form", clear_on_submit=False):
            username = st.text_input("Tên đăng nhập", placeholder="admin")
            password = st.text_input("Mật khẩu", type="password", placeholder="••••••••")
            submitted = st.form_submit_button(
                "🔐 Đăng nhập",
                use_container_width=True,
                type="primary",
            )
        if submitted:
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                st.session_state["admin_authenticated"] = True
                st.session_state["admin_user"]          = username
                st.rerun()
            else:
                st.error("Sai tên đăng nhập hoặc mật khẩu.", icon="🚫")
        st.markdown(
            "<div style='text-align:center;margin-top:16px;color:#bbb;font-size:0.8rem'>"
            "Chỉ quản trị viên mới được phép truy cập trang này.</div>",
            unsafe_allow_html=True,
        )
    st.stop()  # Chặn toàn bộ nội dung phía dưới nếu chưa đăng nhập

# ══════════════════════════════════════════════════════════════════════════════
# NỘI DUNG ADMIN – Chỉ hiển thị sau khi đăng nhập thành công
# ══════════════════════════════════════════════════════════════════════════════

# ── Session state defaults ────────────────────────────────────────────────────
_defaults: dict = {
    "hitl_page":        1,
    "hitl_actioned":    set(),
    "hitl_stats_cache": None,
    "hitl_data_cache":  None,
    "main_stats_cache": None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar (admin only) ───────────────────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://img.icons8.com/fluency/96/artificial-intelligence.png",
        width=80,
    )
    st.title("AI News Pipeline")
    st.caption(f"👤 {st.session_state.get('admin_user', 'Admin')}")
    st.divider()
    st.page_link("app.py",                       label="📊 Dashboard",     icon="📊")
    st.page_link("pages/1_Tin_Tức.py",           label="📰 Tin tức",       icon="📰")
    st.page_link("pages/3_HITL_Kiểm_Duyệt.py",  label="🛡️ Admin HITL",   icon="🛡️")
    st.divider()
    page_size = st.select_slider("Bài/trang (Review Queue)", options=[5, 10, 20], value=10)
    st.divider()
    if st.button("🚪 Đăng xuất", use_container_width=True):
        st.session_state["admin_authenticated"] = False
        st.session_state["admin_user"]          = None
        st.rerun()

# ── API helpers ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def fetch_hitl_stats() -> dict:
    r = requests.get(f"{API_URL}/api/hitl/stats", timeout=10)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=60, show_spinner=False)
def fetch_main_stats() -> dict:
    r = requests.get(f"{API_URL}/api/stats", timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_pending(page: int, limit: int) -> dict:
    r = requests.get(
        f"{API_URL}/api/hitl/pending",
        params={"page": page, "limit": limit},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def post_review(article_id: str, action: str, corrected_label: str | None = None) -> dict:
    payload: dict = {"action": action}
    if corrected_label:
        payload["corrected_label"] = corrected_label
    r = requests.post(
        f"{API_URL}/api/hitl/review/{article_id}",
        json=payload,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


# ── Render helpers ─────────────────────────────────────────────────────────────
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


def label_badge(label: str) -> str:
    color = LABEL_COLORS.get(label, "#999")
    vi    = LABEL_VI.get(label, label)
    return (
        f'<span style="background:{color};color:#fff;padding:3px 11px;'
        f'border-radius:12px;font-size:0.73rem;font-weight:600">{vi}</span>'
    )


def progress_bar_html(conf_raw: str | None) -> str:
    val   = conf_to_float(conf_raw)
    key   = str(conf_raw or "").lower()
    color = CONF_COLOR.get(key, "#F39C12")
    icon  = CONF_ICON.get(key, "🟡")
    lbl   = str(conf_raw or "—").upper()
    pct   = val * 100
    return f"""
    <div style="margin:6px 0 10px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="font-size:0.75rem;color:#555">Độ tin cậy AI:</span>
            <span style="font-size:0.75rem;font-weight:700;color:{color}">{icon} {lbl}</span>
        </div>
        <div style="background:#e9ecef;border-radius:6px;height:8px;overflow:hidden">
            <div style="width:{pct:.0f}%;background:{color};height:100%;
                        border-radius:6px;transition:width 0.45s ease"></div>
        </div>
    </div>
    """


# ── Page header ────────────────────────────────────────────────────────────────
st.title("🛡️ Admin Dashboard – HITL Control Panel")
st.caption("Thống kê kiểm duyệt, phân bố nhãn AI và hàng chờ xét duyệt")

# ── Fetch data ─────────────────────────────────────────────────────────────────
try:
    hitl  = fetch_hitl_stats()
    st.session_state["hitl_stats_cache"] = hitl
except Exception as exc:
    st.warning(f"Không tải được HITL stats: {exc}")
    hitl = st.session_state["hitl_stats_cache"] or {}

try:
    main  = fetch_main_stats()
    st.session_state["main_stats_cache"] = main
except Exception as exc:
    st.warning(f"Không tải được label stats: {exc}")
    main = st.session_state["main_stats_cache"] or {}

pending_count  = hitl.get("pending_count",  0)
reviewed_today = hitl.get("reviewed_today", 0)
approved_total = hitl.get("approved_total", 0)
rejected_total = hitl.get("rejected_total", 0)
total_articles = hitl.get("total_articles", 0)
reviewed_all   = approved_total + rejected_total
noise_ratio    = rejected_total / reviewed_all * 100 if reviewed_all > 0 else 0.0
coverage_pct   = reviewed_all / total_articles * 100 if total_articles > 0 else 0.0

label_dist   = main.get("label_distribution", {})
label_colors = main.get("label_colors",       LABEL_COLORS)
label_icons  = main.get("label_icons",        {})
total_labeled = main.get("total",             0)

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab_overview, tab_queue = st.tabs(["📊 Tổng quan", "📋 Hàng chờ duyệt"])

# ════════════════════════════════════════════════
# TAB 1 – TỔNG QUAN
# ════════════════════════════════════════════════
with tab_overview:

    # ── KPI metric row ───────────────────────────────────────────────────────
    st.divider()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("⏳ Chờ duyệt",        f"{pending_count:,}")
    m2.metric("✅ Đã duyệt hôm nay", f"{reviewed_today:,}")
    m3.metric("🗑️ Tỉ lệ Nhiễu",      f"{noise_ratio:.1f}%")
    m4.metric("👍 Tổng Approved",    f"{approved_total:,}")
    m5.metric("📰 Tổng bài viết",    f"{total_articles:,}")
    st.divider()

    # ── Chart row 1: Gauge | Review Status donut | Label donut ──────────────
    gc, rc, lc = st.columns(3)

    # Gauge: Review coverage
    with gc:
        st.subheader("Độ phủ duyệt")
        fig_gauge = go.Figure(go.Indicator(
            mode  = "gauge+number",
            value = coverage_pct,
            number= {"suffix": "%", "font": {"size": 44}},
            gauge = {
                "axis":      {"range": [0, 100], "ticksuffix": "%"},
                "bar":       {"color": "#2980B9", "thickness": 0.28},
                "bgcolor":   "white",
                "steps": [
                    {"range": [0,  40], "color": "#FADBD8"},
                    {"range": [40, 75], "color": "#FAD7A0"},
                    {"range": [75, 100],"color": "#D5F5E3"},
                ],
                "threshold": {
                    "line":      {"color": "#27AE60", "width": 3},
                    "thickness": 0.8,
                    "value":     80,
                },
            },
        ))
        fig_gauge.update_layout(
            height=260,
            margin=dict(t=30, b=10, l=20, r=20),
        )
        st.plotly_chart(fig_gauge, use_container_width=True)
        st.caption(f"**{reviewed_all:,}** / {total_articles:,} bài đã được xem xét")

    # Donut: HITL review status
    with rc:
        st.subheader("Trạng thái duyệt")
        status_labels = ["⏳ Chờ duyệt", "✅ Approved", "🗑️ Rejected"]
        status_values = [pending_count, approved_total, rejected_total]
        status_colors = ["#95A5A6", "#27AE60", "#E74C3C"]
        fig_status = go.Figure(go.Pie(
            labels      = status_labels,
            values      = status_values,
            marker_colors= status_colors,
            hole        = 0.52,
            textinfo    = "percent+value",
            hovertemplate="<b>%{label}</b><br>Số bài: %{value:,}<br>Tỉ lệ: %{percent}<extra></extra>",
        ))
        fig_status.update_layout(
            height     = 260,
            margin     = dict(t=10, b=10, l=0, r=0),
            showlegend = True,
            legend     = dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
        )
        st.plotly_chart(fig_status, use_container_width=True)

    # Donut: AI label distribution
    with lc:
        st.subheader("Phân bố nhãn AI")
        ai_labels  = [l for l in LABEL_ORDER if l in label_dist]
        ai_values  = [label_dist[l] for l in ai_labels]
        ai_colors  = [label_colors.get(l, "#999") for l in ai_labels]
        ai_labels_vi = [
            f"{label_icons.get(l,'')} {LABEL_VI.get(l, l)}"
            for l in ai_labels
        ]
        fig_label = go.Figure(go.Pie(
            labels      = ai_labels_vi,
            values      = ai_values,
            marker_colors= ai_colors,
            hole        = 0.52,
            textinfo    = "percent",
            hovertemplate="<b>%{label}</b><br>Số bài: %{value:,}<br>Tỉ lệ: %{percent}<extra></extra>",
        ))
        fig_label.update_layout(
            height     = 260,
            margin     = dict(t=10, b=10, l=0, r=0),
            showlegend = True,
            legend     = dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
        )
        st.plotly_chart(fig_label, use_container_width=True)

    st.divider()

    # ── Chart row 2: Horizontal review bar | Label bar ──────────────────────
    bc1, bc2 = st.columns(2)

    # Horizontal bar: Approved vs Rejected vs Pending
    with bc1:
        st.subheader("Kết quả kiểm duyệt")
        fig_bar_h = go.Figure()
        fig_bar_h.add_trace(go.Bar(
            name            = "Approved",
            x               = [approved_total],
            y               = ["Kết quả"],
            orientation     = "h",
            marker_color    = "#27AE60",
            text            = [f"✅ {approved_total:,}"],
            textposition    = "inside",
            insidetextanchor= "middle",
            hovertemplate   = "Approved: %{x:,}<extra></extra>",
        ))
        fig_bar_h.add_trace(go.Bar(
            name            = "Rejected",
            x               = [rejected_total],
            y               = ["Kết quả"],
            orientation     = "h",
            marker_color    = "#E74C3C",
            text            = [f"🗑️ {rejected_total:,}"],
            textposition    = "inside",
            insidetextanchor= "middle",
            hovertemplate   = "Rejected: %{x:,}<extra></extra>",
        ))
        fig_bar_h.add_trace(go.Bar(
            name            = "Pending",
            x               = [pending_count],
            y               = ["Kết quả"],
            orientation     = "h",
            marker_color    = "#95A5A6",
            text            = [f"⏳ {pending_count:,}"],
            textposition    = "inside",
            insidetextanchor= "middle",
            hovertemplate   = "Pending: %{x:,}<extra></extra>",
        ))
        fig_bar_h.update_layout(
            barmode      = "stack",
            height       = 160,
            margin       = dict(t=10, b=30, l=10, r=10),
            showlegend   = True,
            legend       = dict(orientation="h", y=1.25, x=0, traceorder="normal"),
            xaxis_title  = "Số bài viết",
            plot_bgcolor = "rgba(0,0,0,0)",
            xaxis        = dict(gridcolor="rgba(128,128,128,0.15)"),
        )
        st.plotly_chart(fig_bar_h, use_container_width=True)

        # Daily progress indicator
        if pending_count > 0:
            daily_pct = min(reviewed_today / pending_count * 100, 100)
        else:
            daily_pct = 100.0
        st.markdown(
            f"""
            <div style="margin-top:8px">
                <div style="display:flex;justify-content:space-between;
                            font-size:0.82rem;margin-bottom:4px">
                    <span>📅 Tiến độ hôm nay</span>
                    <span style="font-weight:700;color:#2980B9">
                        {reviewed_today:,} duyệt · {daily_pct:.0f}%
                    </span>
                </div>
                <div style="background:#e9ecef;border-radius:8px;height:10px;overflow:hidden">
                    <div style="width:{daily_pct:.0f}%;background:#2980B9;height:100%;
                                border-radius:8px;transition:width 0.5s ease"></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Vertical bar: label count
    with bc2:
        st.subheader("Số bài theo nhãn AI")
        bar_labels = [l for l in LABEL_ORDER if l in label_dist]
        bar_values = [label_dist[l] for l in bar_labels]
        bar_colors = [label_colors.get(l, "#999") for l in bar_labels]
        bar_vi     = [
            f"{label_icons.get(l,'')} {LABEL_VI.get(l, l)}"
            for l in bar_labels
        ]
        fig_bar_v = go.Figure(go.Bar(
            x             = bar_vi,
            y             = bar_values,
            marker_color  = bar_colors,
            text          = bar_values,
            textposition  = "outside",
            hovertemplate = "<b>%{x}</b><br>Số bài: %{y:,}<extra></extra>",
        ))
        fig_bar_v.update_layout(
            height       = 280,
            margin       = dict(t=20, b=60, l=40, r=20),
            yaxis_title  = "Số bài viết",
            xaxis_tickangle=-10,
            plot_bgcolor = "rgba(0,0,0,0)",
            yaxis        = dict(gridcolor="rgba(128,128,128,0.15)"),
        )
        st.plotly_chart(fig_bar_v, use_container_width=True)

    st.divider()
    st.caption(f"🤖 AI News Pipeline · Admin Dashboard · KLTN 2026  |  Tổng bài đã gán nhãn: **{total_labeled:,}**")


# ════════════════════════════════════════════════
# TAB 2 – HÀNG CHỜ DUYỆT
# ════════════════════════════════════════════════
with tab_queue:
    st.divider()

    # Load pending
    with st.spinner("Đang tải danh sách bài chờ duyệt…"):
        try:
            result = fetch_pending(st.session_state["hitl_page"], page_size)
            st.session_state["hitl_data_cache"] = result
        except Exception as exc:
            st.error(f"Không tải được danh sách: {exc}")
            result = st.session_state["hitl_data_cache"] or {
                "articles": [], "total": 0, "page": 1
            }

    all_articles  = result.get("articles", [])
    total_pending = result.get("total",    0)
    cur_page      = result.get("page",     1)
    total_pages   = max(1, math.ceil(total_pending / page_size))
    visible       = [a for a in all_articles if a["id"] not in st.session_state["hitl_actioned"]]

    # Queue header
    hdr_c, ref_c = st.columns([7, 1])
    with hdr_c:
        st.subheader(
            f"📋 Hàng chờ duyệt · {total_pending:,} bài · Trang {cur_page}/{total_pages}"
        )
    with ref_c:
        if st.button("🔄 Làm mới", use_container_width=True):
            st.session_state["hitl_actioned"] = set()
            st.session_state["hitl_page"]     = 1
            st.cache_data.clear()
            st.rerun()

    # Empty states
    if not visible:
        if total_pending == 0:
            st.success("🎉 Tuyệt vời! Không còn bài nào chờ duyệt.")
        else:
            st.info("Tất cả bài trang này đã xử lý. Nhấn **Trang sau** hoặc **Làm mới**.")

    # Article cards
    for art in visible:
        article_id = art["id"]
        ai_label   = art.get("ai_predicted_label", "")
        conf_raw   = art.get("ai_confidence_score", "")
        title      = art.get("title") or "—"
        source     = art.get("source", "")
        pub_date   = art.get("pub_date", "")
        snippet    = art.get("content_snippet", "")
        source_url = art.get("source_url", "")

        with st.container(border=True):
            left_col, right_col = st.columns([6, 2], gap="large")

            with left_col:
                if source_url:
                    st.markdown(f"#### [{title}]({source_url})")
                else:
                    st.markdown(f"#### {title}")

                badge_parts = [label_badge(ai_label)]
                if source:
                    badge_parts.append(
                        f'<span style="color:#888;font-size:0.78rem;margin-left:8px">'
                        f'🌐 {source}</span>'
                    )
                if pub_date:
                    badge_parts.append(
                        f'<span style="color:#aaa;font-size:0.73rem;margin-left:8px">'
                        f'📅 {str(pub_date)[:16]}</span>'
                    )
                st.markdown(" ".join(badge_parts), unsafe_allow_html=True)

                if snippet:
                    st.caption(snippet[:220])

                st.markdown(progress_bar_html(conf_raw), unsafe_allow_html=True)

            with right_col:
                st.markdown("**Hành động:**")

                if st.button(
                    "✅ Approve",
                    key=f"approve_{article_id}",
                    type="primary",
                    use_container_width=True,
                    help="Chấp nhận nhãn AI hiện tại",
                ):
                    with st.spinner("Đang ghi nhận…"):
                        try:
                            post_review(article_id, "Accept")
                            st.session_state["hitl_actioned"].add(article_id)
                            st.toast(f"✅ Approved: {title[:45]}…", icon="✅")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Lỗi: {exc}")

                if st.button(
                    "🗑️ Reject as Noise",
                    key=f"reject_{article_id}",
                    use_container_width=True,
                    help="Đánh dấu bài viết này là Nhiễu",
                ):
                    with st.spinner("Đang ghi nhận…"):
                        try:
                            post_review(article_id, "Reject")
                            st.session_state["hitl_actioned"].add(article_id)
                            st.toast(f"🗑️ Rejected: {title[:45]}…", icon="🗑️")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Lỗi: {exc}")

                st.markdown("**Sửa nhãn:**")
                corrected = st.selectbox(
                    "Chọn nhãn đúng",
                    options     = ALL_LABELS,
                    index       = ALL_LABELS.index(ai_label) if ai_label in ALL_LABELS else 0,
                    format_func = lambda lb: LABEL_VI.get(lb, lb),
                    key         = f"label_sel_{article_id}",
                    label_visibility="collapsed",
                )
                if st.button(
                    "💾 Lưu nhãn mới",
                    key=f"correct_{article_id}",
                    use_container_width=True,
                ):
                    with st.spinner("Đang ghi nhận…"):
                        try:
                            post_review(article_id, "Correct", corrected_label=corrected)
                            st.session_state["hitl_actioned"].add(article_id)
                            st.toast(
                                f"✏️ Sửa → {LABEL_VI.get(corrected, corrected)}: {title[:35]}…",
                                icon="✏️",
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Lỗi: {exc}")

    # Pagination
    st.divider()
    pg_prev, pg_info, pg_next = st.columns([1, 2, 1])
    with pg_prev:
        if st.button("⬅ Trang trước", disabled=cur_page <= 1, use_container_width=True):
            st.session_state["hitl_page"]     = cur_page - 1
            st.session_state["hitl_actioned"] = set()
            st.rerun()
    with pg_info:
        st.markdown(
            f"<div style='text-align:center;padding:8px 0'>"
            f"Trang <b>{cur_page}</b> / <b>{total_pages}</b> &nbsp;·&nbsp; "
            f"<span style='color:#888'>{total_pending:,} bài chờ duyệt</span></div>",
            unsafe_allow_html=True,
        )
    with pg_next:
        if st.button("Trang sau ➡", disabled=cur_page >= total_pages, use_container_width=True):
            st.session_state["hitl_page"]     = cur_page + 1
            st.session_state["hitl_actioned"] = set()
            st.rerun()

    st.divider()
    st.caption("🛡️ HITL Admin · AI News Pipeline · KLTN 2026")
