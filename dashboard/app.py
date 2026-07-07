"""
dashboard/app.py — Responsive Research Dashboard (thin router)
電腦：寬版多欄  |  手機：窄版單欄（CSS 自動適應）

頁面邏輯已拆分至 dashboard/pages/：
  overview.py   — 今日分析
  reports.py    — 個股查詢 + 歷史記錄
  position.py   — 模型持倉追蹤
  backtest.py   — 模型驗證
  my_trades.py  — 我的實際交易紀錄
  guide.py      — 評分說明 + 設定

資料載入函數位於 dashboard/loaders.py
DB 啟動邏輯位於 dashboard/db.py
"""

import logging
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 載入 .env（本機開發）；Streamlit Cloud 用 st.secrets
try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

# Streamlit secrets → 環境變數（雲端部署）
try:
    import streamlit as _st

    if hasattr(_st, "secrets") and "NEON_URL" in _st.secrets:
        os.environ.setdefault("NEON_URL", _st.secrets["NEON_URL"])
except Exception:
    pass

import streamlit as st  # noqa: E402

# DB bootstrap（必須在所有 page import 之前）
import dashboard.db  # noqa: F401,E402 — registers src.database in sys.modules

logger = logging.getLogger(__name__)

# ── 頁面設定 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="台股 AI 研究平台 v6.8",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 響應式 CSS ────────────────────────────────────────────────
st.markdown(
    """
<style>
* { box-sizing: border-box; }
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
#MainMenu, footer { visibility: hidden; }

/* ══ 電腦版（≥ 769px）══ */
@media (min-width: 769px) {
    .block-container { padding: 1.5rem 2rem 2rem 2rem !important; max-width: 100% !important; }
    .top-bar { display: none !important; }
    .stat-grid { grid-template-columns: repeat(4, 1fr) !important; }
    .rec-grid  { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    .stTabs [data-baseweb="tab-list"] {
        background: transparent !important; border-bottom: 2px solid #f0f0f0 !important;
        border-radius: 0 !important; padding: 0 !important; gap: 0 !important; margin-bottom: 1.5rem;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 0 !important; font-size: 0.95rem !important; font-weight: 600 !important;
        padding: 10px 20px !important; height: auto !important;
        border-bottom: 3px solid transparent !important;
    }
    .stTabs [aria-selected="true"] {
        background: transparent !important; box-shadow: none !important;
        color: #667eea !important; border-bottom: 3px solid #667eea !important;
    }
    .stat-box .stat-val { font-size: 2rem !important; }
    .market-card .index-val { font-size: 2.8rem !important; }
    section[data-testid="stSidebar"] {
        background: #f5f6fa !important;
        min-width: 210px !important; max-width: 220px !important;
        border-right: 1px solid #e8eaf0 !important;
    }
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] span { color: #444 !important; }
}

/* ══ 手機版（≤ 768px）══ */
@media (max-width: 768px) {
    .block-container { padding: 0 0.75rem 5rem 0.75rem !important; max-width: 100% !important; }
    section[data-testid="stSidebar"] { display: none !important; }
    button[data-testid="collapsedControl"] { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0 !important; background: #f8f9fa; border-radius: 12px; padding: 4px;
        margin-bottom: 1rem; display: flex !important;
    }
    .stTabs [data-baseweb="tab"] {
        flex: 1 !important; border-radius: 8px; font-size: 0.62rem !important;
        font-weight: 600 !important; padding: 6px 0px !important; height: 38px !important;
        min-width: 0 !important; overflow: hidden; text-align: center !important;
        white-space: nowrap !important; letter-spacing: -0.02em;
    }
    .stTabs [aria-selected="true"] {
        background: white !important; box-shadow: 0 2px 8px rgba(0,0,0,0.12) !important;
        color: #1a1a2e !important; border-bottom: none !important;
    }
    .rec-grid { display: block; }
    .stButton > button { width: 100%; height: 48px; border-radius: 12px; font-weight: 600; }
    [data-testid="metric-container"] {
        background: white; border-radius: 12px; padding: 10px 8px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        flex: 0 0 100% !important;
        min-width: 100% !important;
        width: 100% !important;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-size: 1.1rem !important;
    }
    [data-testid="metric-container"] [data-testid="stMetricLabel"] {
        font-size: 0.7rem !important;
    }
    .stExpander p { word-break: break-all; font-size: 0.82rem !important; }
    [data-testid="stDataFrame"] { overflow-x: auto !important; }
    .stDataFrame iframe { min-width: 100%; }
}

/* ══ 共用元件 ══ */
.top-bar {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: white; padding: 14px 16px; border-radius: 0 0 16px 16px;
    margin: -0.5rem -0.75rem 1rem -0.75rem; text-align: center;
}
.top-bar h1 { font-size: 1.1rem; margin: 0; font-weight: 700; }
.top-bar p  { font-size: 0.68rem; margin: 3px 0 0 0; opacity: 0.65; }

.market-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white; border-radius: 16px; padding: 22px; margin-bottom: 20px;
}
.market-card .index-val { font-size: 2.4rem; font-weight: 800; line-height: 1; }
.market-card .index-chg { font-size: 1.1rem; opacity: 0.9; margin-top: 4px; }
.market-card .market-meta { font-size: 0.75rem; opacity: 0.65; margin-top: 10px; }

.stat-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;
}
.stat-box {
    background: white; border-radius: 12px; padding: 18px; text-align: center;
    box-shadow: 0 2px 10px rgba(0,0,0,0.07); border: 1px solid #f0f0f0;
}
.stat-box .stat-val { font-size: 1.8rem; font-weight: 800; color: #1a1a2e; line-height: 1; }
.stat-box .stat-lbl { font-size: 0.72rem; color: #888; margin-top: 5px; }

.rec-card {
    background: white; border-radius: 16px; padding: 18px; margin-bottom: 14px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.08); border: 1px solid #f0f0f0;
    position: relative; overflow: hidden;
}
.rec-card::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0;
    width: 5px; border-radius: 16px 0 0 16px;
}
.rec-card.grade-Aplus::before { background: #00c851; }
.rec-card.grade-A::before     { background: #33b5e5; }
.rec-card.grade-B::before     { background: #ffbb33; }
.rec-card.grade-C::before     { background: #ff8800; }

.rec-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.rec-name   { font-size: 1.15rem; font-weight: 800; color: #1a1a2e; }
.rec-sid    { font-size: 0.8rem; color: #888; margin-top: 3px; }
.rec-badge  { display: inline-block; padding: 5px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 700; color: white; }
.badge-Aplus { background: #00c851; }
.badge-A     { background: #33b5e5; }
.badge-B     { background: #ffbb33; color: #333 !important; }
.badge-C     { background: #ff8800; }

.score-row  { display: flex; align-items: center; gap: 8px; margin: 5px 0; }
.score-lbl  { font-size: 0.72rem; color: #666; width: 52px; flex-shrink: 0; }
.score-bar  { flex: 1; height: 6px; background: #eee; border-radius: 3px; overflow: hidden; }
.score-fill { height: 100%; border-radius: 3px; }
.score-num  { font-size: 0.78rem; font-weight: 700; width: 30px; text-align: right; flex-shrink: 0; }

.tags { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 4px; }
.tag-good  { background: #e8f5e9; color: #2e7d32; border-radius: 20px; padding: 3px 10px; font-size: 0.72rem; font-weight: 500; }
.tag-risk  { background: #fff3e0; color: #e65100; border-radius: 20px; padding: 3px 10px; font-size: 0.72rem; font-weight: 500; }
.tag-watch { background: #e3f2fd; color: #1565c0; border-radius: 20px; padding: 3px 10px; font-size: 0.72rem; font-weight: 500; }

.confidence-row {
    display: flex; align-items: center; justify-content: space-between;
    background: #f8f9fa; border-radius: 8px; padding: 8px 12px; margin-top: 10px;
}
.confidence-lbl { font-size: 0.75rem; color: #666; }
.confidence-val { font-size: 0.9rem; font-weight: 800; }

.history-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 0; border-bottom: 1px solid #f0f0f0;
}
.history-item:last-child { border-bottom: none; }
.history-date { font-size: 0.75rem; color: #999; }
.history-sid  { font-size: 0.9rem; font-weight: 700; color: #1a1a2e; }

.search-result {
    background: white; border-radius: 12px; padding: 14px; margin: 8px 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-left: 4px solid #667eea;
}

.section-title {
    font-size: 1rem; font-weight: 700; color: #1a1a2e;
    margin: 0 0 16px 0; padding-bottom: 8px; border-bottom: 2px solid #f0f0f0;
}

.disclaimer { text-align: center; font-size: 0.65rem; color: #bbb; padding: 8px; margin-top: 16px; }
</style>
""",
    unsafe_allow_html=True,
)


# ── 主程式 ────────────────────────────────────────────────────


def main() -> None:
    from dashboard.pages.backtest import page_backtest
    from dashboard.pages.data_health import page_data_health
    from dashboard.pages.guide import page_guide, page_settings
    from dashboard.pages.my_trades import page_my_trades
    from dashboard.pages.overview import page_today
    from dashboard.pages.position import page_positions
    from dashboard.pages.reports import page_history, page_search

    if "selected_date" not in st.session_state:
        st.session_state["selected_date"] = date.today()
    sel_date = st.session_state["selected_date"]

    with st.sidebar:
        st.markdown(
            """
        <div style="text-align:center; padding:20px 0 24px 0">
          <div style="font-size:2.5rem">📈</div>
          <div style="font-size:1rem; font-weight:800; color:#1a1a2e; margin-top:6px">台股 AI 研究平台</div>
          <div style="font-size:0.7rem; color:#999; margin-top:3px">v6.8</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.caption(f"查看日期：{sel_date}")
        if st.button("🔄 重新整理資料", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        try:
            from sqlalchemy import func

            from src.database import DailyPrice, Recommendation, get_session

            s = get_session()
            cnt = s.query(func.count(DailyPrice.id)).scalar()
            newest = s.query(func.max(DailyPrice.date)).scalar()
            first_rec = s.query(func.min(Recommendation.date)).scalar()
            s.close()
            if cnt > 0:
                st.metric("股價資料", f"{cnt:,} 筆")
                if newest:
                    st.caption(f"最新：{newest}")
                if first_rec:
                    st.caption(f"研究起始：{first_rec}")
            else:
                st.caption("股價資料存於本機\n需在家中執行分析")
        except Exception as e:
            logger.debug(f"guide page stock info query failed: {e}")
        st.markdown("---")
        st.markdown(
            """
        <div style="font-size:0.65rem; color:#aaa; text-align:center; line-height:1.6">
          本工具為 AI 研究輔助<br>所有內容不構成投資建議
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
    <div class="top-bar">
      <h1>📈 台股 AI 研究平台</h1>
      <p>v6.8 · 研究輔助工具 · 不構成投資建議</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs(
        [
            "📊今日",
            "🔍個股",
            "📋歷史",
            "📈模型持倉",
            "🔬模型驗證",
            "💼我的交易",
            "🩺資料健康",
            "📖說明",
            "⚙️設定",
        ]
    )

    with tabs[0]:
        page_today(sel_date)
    with tabs[1]:
        page_search()
    with tabs[2]:
        page_history()
    with tabs[3]:
        page_positions()
    with tabs[4]:
        page_backtest()
    with tabs[5]:
        page_my_trades()
    with tabs[6]:
        page_data_health()
    with tabs[7]:
        page_guide()
    with tabs[8]:
        page_settings(sel_date)

    st.markdown(
        '<div class="disclaimer">本工具為 AI 研究輔助，所有內容不構成投資建議，投資人應自行評估風險</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
