"""
dashboard/app.py — Responsive Research Dashboard
電腦：寬版多欄  |  手機：窄版單欄（CSS 自動適應）
"""

import sys
import os
import re
import json
from datetime import date, timedelta
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

import logging
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

logger = logging.getLogger(__name__)

from config import REPORTS_DIR

# Force-load src.database from absolute path — bypasses sys.modules cache and CWD issues
import importlib.util as _ilu
_db_path = Path(__file__).resolve().parent.parent / "src" / "database.py"
_db_spec = _ilu.spec_from_file_location("src.database", str(_db_path))
_db_mod  = _ilu.module_from_spec(_db_spec)
sys.modules["src.database"] = _db_mod
_db_spec.loader.exec_module(_db_mod)

get_session    = _db_mod.get_session
UserTrade      = _db_mod.UserTrade
DailyPrice     = _db_mod.DailyPrice
Recommendation = _db_mod.Recommendation
AnalysisResult = _db_mod.AnalysisResult
PositionMonitor = _db_mod.PositionMonitor
Stock          = _db_mod.Stock


# ── 頁面設定 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="台股 AI 研究平台 v6.8",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 響應式 CSS ────────────────────────────────────────────────
st.markdown("""
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
    /* 所有 st.columns → 手機自動堆疊（推薦卡片 / 持倉詳情 / 搜尋結果皆適用）*/
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        flex: 0 0 100% !important;
        min-width: 100% !important;
        width: 100% !important;
    }
    /* 持倉總覽 metrics 字體縮放 */
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-size: 1.1rem !important;
    }
    [data-testid="metric-container"] [data-testid="stMetricLabel"] {
        font-size: 0.7rem !important;
    }
    /* Watch List 文字換行 */
    .stExpander p { word-break: break-all; font-size: 0.82rem !important; }
    /* 表格橫向可捲動 */
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
""", unsafe_allow_html=True)


# ── 資料載入 ──────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_report(report_date: date) -> str:
    try:
        from src.database import get_session, DailyReport
        s = get_session()
        r = s.query(DailyReport).filter_by(date=report_date).first()
        s.close()
        if r and r.content_md:
            return r.content_md
    except Exception as e:
        logger.warning(f"load_report({report_date}) DB failed: {e}")
    path = REPORTS_DIR / "daily" / f"{report_date.isoformat()}_report.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


@st.cache_data(ttl=300)
def load_exec_logs(limit: int = 90) -> pd.DataFrame:
    try:
        from src.database import get_session, ExecutionLog
        from sqlalchemy import select, func
        s = get_session()
        # subquery: max id per date → deduplicate multiple runs on same day
        subq = (
            select(func.max(ExecutionLog.id).label("max_id"))
            .group_by(ExecutionLog.date)
            .subquery()
        )
        rows = s.execute(
            select(ExecutionLog)
            .where(ExecutionLog.id.in_(select(subq.c.max_id)))
            .order_by(ExecutionLog.date.desc())
            .limit(limit)
        ).scalars().all()
        s.close()
        return pd.DataFrame([{
            "date": r.date, "status": r.status,
            "analyzed": r.total_stocks, "qualified": r.qualified_stocks,
            "recs": r.recommended_stocks,
        } for r in rows])
    except Exception as e:
        logger.warning(f"load_exec_logs failed: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_recent_recs(days: int = 60) -> pd.DataFrame:
    try:
        from src.database import get_session, Recommendation
        from sqlalchemy import select
        s = get_session()
        since = date.today() - timedelta(days=days)
        rows = s.execute(
            select(Recommendation)
            .where(Recommendation.date >= since)
            .order_by(Recommendation.date.desc())
        ).scalars().all()
        s.close()
        return pd.DataFrame([{
            "date": r.date, "stock_id": r.stock_id,
            "rec_level": r.rec_level, "confidence": r.confidence,
            "summary": r.summary,
            "advantages": json.loads(r.advantages) if r.advantages else [],
            "risks": json.loads(r.risks) if r.risks else [],
            "watch_points": json.loads(r.watch_points) if r.watch_points else [],
            "ai_conclusion": r.ai_conclusion or "",
        } for r in rows])
    except Exception as e:
        logger.warning(f"load_recent_recs failed: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=86400)
def load_stock_names() -> dict:
    """股票代號→名稱對照表：優先讀本地 DB，再從 TWSE API 補缺"""
    names = {}
    # 優先：本地 stocks 表（離線可用，最完整）
    try:
        from src.database import get_session, Stock
        s = get_session()
        rows = s.execute(select(Stock)).scalars().all()
        s.close()
        names = {r.stock_id: r.name for r in rows if r.name}
    except Exception as e:
        logger.warning(f"load_stock_names DB failed: {e}")
    # 補充：TWSE API（補本地沒有的股票）
    try:
        import requests
        r = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            timeout=8, headers={"Accept": "application/json"}
        )
        if r.ok:
            for item in r.json():
                sid = item.get("Code", "").strip()
                name = item.get("Name", "").strip()
                if sid and name and sid not in names:
                    names[sid] = name
    except Exception as e:
        logger.warning(f"load_stock_names TWSE API failed: {e}")
        pass
    return names


@st.cache_data(ttl=86400)
def load_stock_list() -> list:
    """回傳 [(顯示文字, stock_id), ...] 供 selectbox 搜尋用。"""
    names = load_stock_names()
    return sorted([(f"{name}（{sid}）", sid) for sid, name in names.items()], key=lambda x: x[1])


@st.cache_data(ttl=300)
def load_stock_prices() -> dict:
    """讀取 DB 最新一日收盤價。回傳 {stock_id: close_price}"""
    prices = {}
    try:
        from src.database import get_session, DailyPrice
        from sqlalchemy import func
        s = get_session()
        latest_date = s.query(func.max(DailyPrice.date)).scalar()
        if latest_date:
            rows = s.query(DailyPrice.stock_id, DailyPrice.close).filter_by(date=latest_date).all()
            prices = {sid: close for sid, close in rows if close}
        s.close()
    except Exception as e:
        logger.warning(f"load_stock_prices failed: {e}")
    return prices


@st.cache_data(ttl=300)
def load_db_recommendations(target_date: date) -> list:
    """從 DB recommendations 表讀取當日推薦，組成 render_rec_card 所需格式。"""
    try:
        from src.database import get_session, Recommendation, Stock, AnalysisResult
        from sqlalchemy import select
        s = get_session()
        recs_rows = s.execute(
            select(Recommendation).where(Recommendation.date == target_date)
            .order_by(Recommendation.confidence.desc())
        ).scalars().all()
        stock_name_map = {r.stock_id: r.name for r in s.execute(select(Stock)).scalars().all() if r.name}
        # 補充分析分數
        ar_map = {r.stock_id: r for r in s.execute(
            select(AnalysisResult).where(AnalysisResult.date == target_date)
        ).scalars().all()}
        # 補充 PositionMonitor（目標價 / 停損 / 部位）
        from src.database import PositionMonitor, DailyPrice
        from sqlalchemy import desc as _desc
        pm_map = {r.stock_id: r for r in s.execute(select(PositionMonitor)).scalars().all()}
        # 從 DB 拿推薦股票最新收盤價（比 TWSE API 更可靠）
        rec_ids = [r.stock_id for r in recs_rows]
        db_price_map = {}
        for sid in rec_ids:
            dp = s.execute(
                select(DailyPrice).where(DailyPrice.stock_id == sid)
                .order_by(_desc(DailyPrice.date)).limit(1)
            ).scalar_one_or_none()
            if dp:
                db_price_map[sid] = dp.close
        s.close()
        result = []
        for r in recs_rows:
            ar = ar_map.get(r.stock_id)
            pm = pm_map.get(r.stock_id)
            result.append({
                "name":            stock_name_map.get(r.stock_id, ""),
                "sid":             r.stock_id,
                "price":           db_price_map.get(r.stock_id),
                "level":           r.rec_level or "B",
                "scores": {
                    "quality":  ar.quality_score  if ar else 0,
                    "timing":   ar.timing_score   if ar else 0,
                    "behavior": ar.behavior_score if ar else 0,
                    "risk":     ar.risk_score     if ar else 0,
                    "total":    ar.total_score    if ar else 0,
                },
                "confidence":      r.confidence or 0,
                "advantages":      json.loads(r.advantages)   if r.advantages   else [],
                "risks":           json.loads(r.risks)        if r.risks        else [],
                "watch":           json.loads(r.watch_points) if r.watch_points else [],
                "conclusion":      r.ai_conclusion or "",
                "summary":         r.summary or "",
                "target_price":    pm.target_price    if pm else None,
                "stop_loss_price": pm.stop_loss_price if pm else None,
                "position_pct":    pm.position_pct    if pm else None,
            })
        return result
    except Exception as e:
        logger.warning(f"load_db_recommendations failed: {e}")
        return []


@st.cache_data(ttl=300)
def load_analysis_results(target_date: date) -> pd.DataFrame:
    try:
        from src.database import get_session, AnalysisResult
        from sqlalchemy import select
        s = get_session()
        rows = s.execute(
            select(AnalysisResult)
            .where(AnalysisResult.date == target_date)
            .order_by(AnalysisResult.total_score.desc())
        ).scalars().all()
        # 載入名稱對照
        from src.database import Stock
        stock_name_map = {r.stock_id: r.name for r in s.execute(select(Stock)).scalars().all() if r.name}
        s.close()
        return pd.DataFrame([{
            "stock_id": r.stock_id,
            "name": stock_name_map.get(r.stock_id, r.stock_id),
            "grade": r.quality_grade,
            "quality": r.quality_score, "timing": r.timing_score,
            "behavior": r.behavior_score, "risk": r.risk_score,
            "total": r.total_score, "confidence": r.confidence,
            "rec_level": r.rec_level,
        } for r in rows])
    except Exception as e:
        logger.warning(f"load_analysis_results failed: {e}")
        return pd.DataFrame()


# ── 解析報告 ─────────────────────────────────────────────────

def parse_market_summary(report: str) -> dict:
    result = {}
    for pattern, key in [
        (r'\| 加權指數 \| ([\d,.]+)', "index"),
        (r'\| 漲跌幅 \| ([+-]?[\d.]+%)', "change"),
        (r'\| 市場情緒 \| .* (Bullish|Neutral|Bearish)', "sentiment"),
        (r'\| 上漲家數 \| (\d+)', "up"),
        (r'\| 下跌家數 \| (\d+)', "down"),
    ]:
        m = re.search(pattern, report)
        if m: result[key] = m.group(1)
    return result


def parse_recs_from_report(report: str) -> list:
    results = []
    sections = re.split(r'(?=### \d+\.)', report)
    for sec in sections:
        if not sec.startswith("###"): continue
        m_title = re.search(r'### \d+\. (.+?)（(\d{4})）', sec)
        if not m_title: continue
        name, sid = m_title.group(1).strip(), m_title.group(2)
        level_m = re.search(r'—— ([A-Z+]+) 級', sec)
        level   = level_m.group(1) if level_m else "B"
        scores  = {}
        for label, key in [("公司品質","quality"),("技術時機","timing"),
                            ("市場行為","behavior"),("風險評估","risk"),("綜合評分","total")]:
            sm = re.search(rf'\| {label} \| \*\*(\d+)\*\*/100', sec)
            if sm: scores[key] = int(sm.group(1))
        conf_m = re.search(r'\| 分析信心 \| (\d+)%', sec)
        conf   = int(conf_m.group(1)) if conf_m else 0
        adv   = re.findall(r'- ✅ (.+)', sec)
        risks = re.findall(r'• (.+)', sec)
        watch = re.findall(r'- 🔍 (.+)', sec)
        conc_m = re.search(r'\*\*AI 結論\*\*\n\n> (.+)', sec)
        conclusion = conc_m.group(1) if conc_m else ""
        results.append({"name": name, "sid": sid, "level": level, "scores": scores,
                         "confidence": conf, "advantages": adv, "risks": risks,
                         "watch": watch, "conclusion": conclusion})
    return results


# ── 推薦卡片 ─────────────────────────────────────────────────

def render_rec_card(r: dict):
    level   = r.get("level", "B")
    grade_c = "Aplus" if level == "A+" else level
    scores  = r.get("scores", {})
    conf    = r.get("confidence", 0)
    conf_color = "#00c851" if conf >= 80 else "#ffbb33" if conf >= 60 else "#ff4444"

    score_bars = ""
    for lbl, sub, key, color in [
        ("品質", "財務體質", "quality",  "#667eea"),
        ("時機", "技術進場", "timing",   "#33b5e5"),
        ("籌碼", "法人動向", "behavior", "#ff8800"),
        ("風險", "波動風險", "risk",     "#00c851"),
        ("綜合", "加權總分", "total",    "#764ba2"),
    ]:
        val = scores.get(key, 0)
        score_bars += (
            f'<div class="score-row">'
            f'<span class="score-lbl">{lbl}<span style="font-size:0.65rem;color:#aaa;display:block;line-height:1">{sub}</span></span>'
            f'<div class="score-bar"><div class="score-fill" style="width:{val}%;background:{color}"></div></div>'
            f'<span class="score-num" style="color:{color}">{val}</span>'
            f'</div>'
        )

    adv_tags   = "".join(f'<span class="tag-good">✓ {a[:18]}</span>' for a in r.get("advantages", [])[:3])
    risk_tags  = "".join(f'<span class="tag-risk">⚠ {r2[:18]}</span>' for r2 in r.get("risks", [])[:2])
    watch_tags = "".join(f'<span class="tag-watch">👁 {w[:20]}</span>' for w in r.get("watch", [])[:2])

    price     = r.get("price")
    price_str = f"　NT$ {price:,.1f}" if price else ""

    # 目標價 / 停損價：優先用 PositionMonitor，其次用當前價格估算
    target_price    = r.get("target_price")
    stop_loss_price = r.get("stop_loss_price")
    position_pct    = r.get("position_pct")
    target_is_est   = False
    if price and not target_price:
        target_price    = round(price * 1.10, 1)
        stop_loss_price = round(price * 0.93, 1)
        target_is_est   = True
    price_block = ""
    if price and target_price:
        target_pct   = round((target_price    - price) / price * 100, 1)
        stoploss_pct = round((stop_loss_price - price) / price * 100, 1)
        pos_str = f"　建議部位 {position_pct:.0f}%" if position_pct else ""
        tp_label = "目標價 (估)" if target_is_est else "目標價"
        sl_label = "停損價 (估)" if target_is_est else "停損價"
        price_block = f"""
      <div style="display:flex;gap:8px;margin:8px 0 4px;flex-wrap:wrap">
        <div style="flex:1;min-width:80px;background:#e8f5e9;border-radius:6px;padding:6px 10px;text-align:center">
          <div style="font-size:0.65rem;color:#2e7d32;font-weight:600">{tp_label}</div>
          <div style="font-size:0.95rem;font-weight:800;color:#2e7d32">{target_price:,.1f}</div>
          <div style="font-size:0.65rem;color:#2e7d32">+{target_pct}%</div>
        </div>
        <div style="flex:1;min-width:80px;background:#fce4ec;border-radius:6px;padding:6px 10px;text-align:center">
          <div style="font-size:0.65rem;color:#c62828;font-weight:600">{sl_label}</div>
          <div style="font-size:0.95rem;font-weight:800;color:#c62828">{stop_loss_price:,.1f}</div>
          <div style="font-size:0.65rem;color:#c62828">{stoploss_pct}%</div>
        </div>
        <div style="flex:1;min-width:80px;background:#f3e5f5;border-radius:6px;padding:6px 10px;text-align:center">
          <div style="font-size:0.65rem;color:#6a1b9a;font-weight:600">現價</div>
          <div style="font-size:0.95rem;font-weight:800;color:#6a1b9a">{price:,.1f}</div>
          <div style="font-size:0.65rem;color:#6a1b9a">{pos_str.strip() or '—'}</div>
        </div>
      </div>"""

    name = r.get("name", "")
    sid  = r.get("sid", "")
    name_html = (
        f'<div class="rec-name">{name}</div><div class="rec-sid">{sid} · TWSE{price_str}</div>'
        if name and name != sid
        else f'<div class="rec-name">{sid}</div><div class="rec-sid">TWSE{price_str}</div>'
    )
    st.markdown(f"""
    <div class="rec-card grade-{grade_c}">
      <div class="rec-header">
        <div>
          {name_html}
        </div>
        <span class="rec-badge badge-{grade_c}">{level} 級</span>
      </div>
      {score_bars}
      {price_block}
      <div class="tags">{adv_tags}{risk_tags}</div>
      {f'<div class="tags">{watch_tags}</div>' if watch_tags else ''}
      <div class="confidence-row">
        <span class="confidence-lbl">分析信心度</span>
        <span class="confidence-val" style="color:{conf_color}">{conf}%</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if r.get("conclusion"):
        with st.expander("📝 AI 結論"):
            st.markdown(f"> {r['conclusion']}")


# ── 今日分析 ─────────────────────────────────────────────────

def page_today(selected_date: date):
    report     = load_report(selected_date)
    logs       = load_exec_logs()
    results_df = load_analysis_results(selected_date)
    mkt        = parse_market_summary(report) if report else {}

    idx_val   = mkt.get("index", "—")
    idx_chg   = mkt.get("change", "—")
    sentiment = mkt.get("sentiment", "—")
    try:
        _chg_val = float(str(idx_chg).replace("%","").replace("+",""))
        chg_color = "#00c851" if _chg_val > 0 else "#ff4444" if _chg_val < 0 else "#aaaaaa"
    except Exception as e:
        logger.debug(f"index change color parse failed: {e}")
        chg_color = "#aaaaaa"

    today_log = logs[logs["date"] == selected_date] if not logs.empty else pd.DataFrame()
    if today_log.empty:
        # 超出最近 90 筆快取範圍，直接查 DB
        try:
            from src.database import get_session, ExecutionLog
            _s = get_session()
            _el = _s.query(ExecutionLog).filter_by(date=selected_date).order_by(ExecutionLog.id.desc()).first()
            _s.close()
            if _el:
                today_log = pd.DataFrame([{
                    "date": _el.date, "status": _el.status,
                    "analyzed": _el.total_stocks, "qualified": _el.qualified_stocks,
                    "recs": _el.recommended_stocks,
                }])
        except Exception as e:
            logger.debug(f"today_log DB fallback failed: {e}")
    analyzed  = int(today_log.iloc[0]["analyzed"])  if not today_log.empty else 0
    qualified = int(today_log.iloc[0]["qualified"]) if not today_log.empty else 0
    recs_cnt  = int(today_log.iloc[0]["recs"])      if not today_log.empty else 0
    status    = today_log.iloc[0]["status"]          if not today_log.empty else "—"

    # 市場摘要
    st.markdown(f"""
    <div class="market-card">
      <div style="display:flex; justify-content:space-between; align-items:flex-start">
        <div>
          <div style="font-size:0.75rem; opacity:0.7">加權指數</div>
          <div class="index-val">{idx_val}</div>
          <div class="index-chg" style="color:{chg_color}">{idx_chg}</div>
        </div>
        <div style="text-align:right">
          <div style="font-size:0.75rem; opacity:0.7">市場情緒</div>
          <div style="font-size:1.1rem; font-weight:700; margin-top:4px">{
            '🟢 偏多' if sentiment=='Bullish' else '🔴 偏空' if sentiment=='Bearish' else '⚪ 中性'
          }</div>
          <div style="font-size:0.75rem; opacity:0.7; margin-top:4px">漲 {mkt.get('up','—')} / 跌 {mkt.get('down','—')}</div>
        </div>
      </div>
      <div class="market-meta">{selected_date} · AI Taiwan Equity Research v6.8</div>
    </div>
    """, unsafe_allow_html=True)

    # 統計
    st.markdown(f"""
    <div class="stat-grid">
      <div class="stat-box">
        <div class="stat-val">{analyzed}</div>
        <div class="stat-lbl">分析股票</div>
      </div>
      <div class="stat-box">
        <div class="stat-val">{qualified}</div>
        <div class="stat-lbl">通過篩選</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:#764ba2">{recs_cnt}</div>
        <div class="stat-lbl">今日推薦</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="font-size:1.4rem">{'✅' if status=='success' else '❌' if status=='failed' else '—'}</div>
        <div class="stat-lbl">執行狀態</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not report:
        st.warning(f"尚無 {selected_date} 的分析報告，請先執行分析。")
        return

    stock_names  = load_stock_names()
    stock_prices = load_stock_prices()

    # 優先從 DB 讀推薦（有完整名稱 + AI 結論）
    recs = load_db_recommendations(selected_date)

    # 填入即時股價
    for r in recs:
        if r["price"] is None:
            r["price"] = stock_prices.get(r["sid"])

    # 確保每筆推薦都有目標價 / 停損價（無論來源為何）
    for r in recs:
        p = r.get("price")
        if p and not r.get("target_price"):
            r["target_price"]    = round(p * 1.10, 1)
            r["stop_loss_price"] = round(p * 0.93, 1)

    # DB 無推薦時降級到 markdown 解析
    if not recs:
        recs_section = re.search(r'## ③ Research Candidates.*?\n(.*?)(?=## ④|## 免責)', report, re.DOTALL)
        content = recs_section.group(1) if recs_section else ""
        recs = parse_recs_from_report(content)
        for r in recs:
            if r.get("price") is None:
                r["price"] = stock_prices.get(r.get("sid", ""))
            p = r.get("price")
            if p and not r.get("target_price"):
                r["target_price"]    = round(p * 1.10, 1)
                r["stop_loss_price"] = round(p * 0.93, 1)

    # 仍無推薦：用分析結果補卡片（前 8 名），並標記為「未達門檻」
    is_fallback = False
    if not recs and not results_df.empty:
        is_fallback = True
        top_df = results_df.head(8)
        for _, row in top_df.iterrows():
            sid = row["stock_id"]
            name = row.get("name") or stock_names.get(sid) or ""
            recs.append({
                "name":  name,
                "sid":   sid,
                "price": stock_prices.get(sid),
                "level": row.get("rec_level", "C") or "C",
                "scores": {
                    "quality":  row.get("quality", 0),
                    "timing":   row.get("timing", 0),
                    "behavior": row.get("behavior", 0),
                    "risk":     row.get("risk", 0),
                    "total":    row.get("total", 0),
                },
                "confidence": row.get("confidence", 0),
                "advantages": [], "risks": [], "watch": [], "conclusion": "",
            })

    if recs:
        if is_fallback:
            st.markdown(f'<div class="section-title">分析宇宙（{len(recs)} 檔，未達推薦門檻）</div>', unsafe_allow_html=True)
            st.caption("⚠️ 本日無符合條件的推薦標的（total_score < 65 或 confidence < 70%），以下為分析分數最高的股票，僅供參考。")
        else:
            st.markdown(f'<div class="section-title">今日研究候選（{len(recs)} 檔）</div>', unsafe_allow_html=True)
        cols_data = [recs[i::2] for i in range(2)]
        col_left, col_right = st.columns(2)
        for rec in cols_data[0]:
            with col_left:
                render_rec_card(rec)
        for rec in cols_data[1]:
            with col_right:
                render_rec_card(rec)
    else:
        st.info("今日尚無分析資料，請先執行分析。")

    watch_df = results_df[(results_df["total"] >= 55) & (results_df["total"] < 65)] if not results_df.empty else pd.DataFrame()
    if not watch_df.empty:
        with st.expander(f"📋 Watch List（{len(watch_df)} 檔，待觀察）"):
            for _, row in watch_df.iterrows():
                display_name = f"{row.get('name', row['stock_id'])}（{row['stock_id']}）"
                st.markdown(f"**{display_name}** — 綜合分 {row['total']:.0f} | 品質 {row.get('quality',0):.0f} | 時機 {row.get('timing',0):.0f}")


# ── 個股查詢 ─────────────────────────────────────────────────

def page_search():
    st.markdown('<div class="section-title">個股查詢</div>', unsafe_allow_html=True)
    sid = st.text_input("股票代號", placeholder="輸入 4 位數代號，例：2330",
                        max_chars=6, label_visibility="collapsed")

    if not sid:
        st.markdown("""
        <div style="text-align:center; color:#bbb; padding:60px 0">
          <div style="font-size:3rem">🔍</div>
          <div style="font-size:0.95rem; margin-top:10px">輸入股票代號查詢歷史研究記錄</div>
        </div>
        """, unsafe_allow_html=True)
        return

    try:
        from src.database import get_session, Recommendation, AnalysisResult
        from sqlalchemy import select
        s = get_session()
        recs = s.execute(
            select(Recommendation)
            .where(Recommendation.stock_id == sid.strip())
            .order_by(Recommendation.date.desc()).limit(30)
        ).scalars().all()
        analyses = s.execute(
            select(AnalysisResult)
            .where(AnalysisResult.stock_id == sid.strip())
            .order_by(AnalysisResult.date.desc()).limit(30)
        ).scalars().all()
        s.close()

        if not recs and not analyses:
            st.info(f"尚無 {sid} 的研究記錄。")
            return

        st.markdown(f"""
        <div class="search-result">
          <div style="font-size:1.2rem; font-weight:800">{sid}</div>
          <div style="color:#888; font-size:0.8rem">共 {len(recs)} 次推薦 · {len(analyses)} 次分析</div>
        </div>
        """, unsafe_allow_html=True)

        if analyses:
            df = pd.DataFrame([{
                "日期": a.date, "綜合": a.total_score,
                "品質": a.quality_score, "時機": a.timing_score,
            } for a in analyses]).sort_values("日期")
            fig = go.Figure()
            for col, color in [("綜合","#764ba2"),("品質","#667eea"),("時機","#33b5e5")]:
                fig.add_trace(go.Scatter(x=df["日期"], y=df[col], name=col,
                    line=dict(color=color, width=2), mode="lines+markers", marker=dict(size=5)))
            fig.update_layout(
                margin=dict(l=0, r=0, t=10, b=0), height=260,
                legend=dict(orientation="h", y=-0.25),
                plot_bgcolor="white", paper_bgcolor="white",
                xaxis=dict(showgrid=False), yaxis=dict(range=[0,100], gridcolor="#f0f0f0"),
            )
            st.plotly_chart(fig, use_container_width=True)

        if recs:
            st.markdown("**推薦紀錄**")
            for r in recs:
                level = r.rec_level or "B"
                color = {"A+":"#00c851","A":"#33b5e5","B":"#ffbb33"}.get(level,"#aaa")
                st.markdown(f"""
                <div class="history-item">
                  <div>
                    <div class="history-date">{r.date}</div>
                    <div style="font-size:0.85rem; color:#333; margin-top:2px">{r.summary or '—'}</div>
                  </div>
                  <span class="rec-badge" style="background:{color};color:{'#333' if level=='B' else 'white'};padding:4px 10px;border-radius:20px;font-size:0.78rem;font-weight:700">{level}</span>
                </div>
                """, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"查詢失敗：{e}")


# ── 歷史記錄 ─────────────────────────────────────────────────

def page_history():
    st.markdown('<div class="section-title">近期推薦紀錄</div>', unsafe_allow_html=True)
    recent = load_recent_recs(days=90)
    logs   = load_exec_logs(30)
    stock_names = load_stock_names()

    if not recent.empty:
        col1, col2 = st.columns([1, 1])
        with col1:
            freq = recent.groupby("stock_id").size().reset_index(name="次數").sort_values("次數", ascending=False).head(10)
            freq["label"] = freq["stock_id"].apply(lambda s: f"{stock_names.get(s, s)}\n{s}")
            fig = px.bar(freq, x="label", y="次數",
                         color="次數", color_continuous_scale=["#e3f2fd","#1565c0"],
                         title="近 90 日推薦次數 Top 10")
            fig.update_layout(margin=dict(l=0,r=0,t=30,b=0), height=280,
                              showlegend=False, plot_bgcolor="white", paper_bgcolor="white",
                              coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            if not logs.empty:
                df_plot = logs.head(14).sort_values("date").copy()
                fig2 = go.Figure()
                fig2.add_trace(go.Bar(x=df_plot["date"], y=df_plot["analyzed"],  name="分析", marker_color="#b3c6ff"))
                fig2.add_trace(go.Bar(x=df_plot["date"], y=df_plot["qualified"], name="篩選", marker_color="#667eea"))
                fig2.add_trace(go.Bar(x=df_plot["date"], y=df_plot["recs"],      name="推薦", marker_color="#764ba2"))
                fig2.update_layout(
                    barmode="group", height=280, margin=dict(l=0,r=0,t=30,b=0),
                    title="執行紀錄（近 14 天）",
                    legend=dict(orientation="h", y=-0.3, font=dict(size=11)),
                    plot_bgcolor="white", paper_bgcolor="white",
                    xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#f0f0f0"),
                )
                st.plotly_chart(fig2, use_container_width=True)

        st.markdown("**推薦明細**")
        for _, row in recent.iterrows():
            level = row.get("rec_level","B") or "B"
            color = {"A+":"#00c851","A":"#33b5e5","B":"#ffbb33"}.get(level,"#aaa")
            sid = row['stock_id']
            name = stock_names.get(sid, "")
            display = f"{name}（{sid}）" if name else sid
            st.markdown(f"""
            <div class="history-item">
              <div>
                <div class="history-date">{row['date']}</div>
                <div class="history-sid">{display}</div>
              </div>
              <span class="rec-badge" style="background:{color};color:{'#333' if level=='B' else 'white'};padding:4px 10px;border-radius:20px;font-size:0.78rem;font-weight:700">{level} · {row.get('confidence',0):.0f}%</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("尚無推薦歷史。執行分析後資料會出現在這裡。")


# ── 持倉追蹤 ─────────────────────────────────────────────────

def _get_neon_url() -> str:
    """每次呼叫都強制從 .env 重讀，避免 Streamlit hot-reload 沿用舊值。"""
    from dotenv import load_dotenv as _lde
    _lde(dotenv_path=Path(__file__).parent.parent / ".env", override=True)
    return os.getenv("NEON_URL") or os.getenv("DATABASE_URL") or ""


@st.cache_data(ttl=120)
def load_positions(status: str = "active") -> list:
    """直連 Neon 讀取 position_monitor，不依賴 get_session()。"""
    import json as _json
    neon_url = _get_neon_url()
    if not neon_url:
        return []  # 呼叫端負責顯示錯誤（st.* 不可在 cache_data 內呼叫）
    if neon_url.startswith("sqlite"):
        # 本機 fallback：用 SQLAlchemy
        try:
            from src.database import get_session, PositionMonitor
            from sqlalchemy import select
            s = get_session()
            rows = s.execute(
                select(PositionMonitor).where(PositionMonitor.status == status)
                .order_by(PositionMonitor.date_entered.desc())
            ).scalars().all()
            result = [{
                "id": r.id, "stock_id": r.stock_id, "name": r.stock_name or r.stock_id,
                "date_entered": str(r.date_entered), "entry_price": r.entry_price,
                "target_price": r.target_price, "stop_loss_price": r.stop_loss_price,
                "target_pct": r.target_pct, "stop_loss_pct": r.stop_loss_pct,
                "position_pct": r.position_pct, "rec_level": r.rec_level,
                "rec_score": r.rec_score, "rationale": r.ai_price_rationale or "",
                "status": r.status, "exit_date": str(r.exit_date) if r.exit_date else None,
                "exit_price": r.exit_price, "exit_reason": r.exit_reason,
                "pnl_pct": r.pnl_pct,
                "mc_result": _json.loads(r.mc_result or "null"),
            } for r in rows]
            s.close()
            return result
        except Exception as e:
            logger.warning(f"load_positions SQLite failed: {e}")
            return []
    try:
        import psycopg2
        conn = psycopg2.connect(neon_url)
        cur  = conn.cursor()
        cur.execute('''
            SELECT id, stock_id, stock_name, date_entered, entry_price,
                   target_price, stop_loss_price, target_pct, stop_loss_pct,
                   position_pct, rec_level, rec_score, confidence, ai_price_rationale,
                   status, exit_date, exit_price, exit_reason, pnl_pct, mc_result
            FROM position_monitor
            WHERE status = %s
            ORDER BY date_entered DESC
        ''', (status,))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close(); conn.close()
        result = []
        for row in rows:
            r = dict(zip(cols, row))
            r["name"]      = r.pop("stock_name") or r["stock_id"]
            r["rationale"] = r.pop("ai_price_rationale") or ""
            r["mc_result"] = _json.loads(r["mc_result"]) if r.get("mc_result") else None
            r["date_entered"] = str(r["date_entered"]) if r.get("date_entered") else None
            r["exit_date"]    = str(r["exit_date"])    if r.get("exit_date")    else None
            result.append(r)
        return result
    except Exception as e:
        logger.warning(f"load_positions failed: {e}")
        return []


def _monte_carlo_chart(pos: dict, prices: list = None):
    """從預存的 mc_result JSON 繪製蒙地卡羅模擬圖。"""
    mc = pos.get("mc_result")
    if not mc:
        st.caption("蒙地卡羅資料尚未計算，待下次每日更新後顯示。")
        return

    import plotly.graph_objects as go
    fig = go.Figure()

    days            = mc["days"]
    sample_paths    = mc["sample_paths"]
    target_price    = mc.get("target_price")    or pos.get("target_price")
    stop_loss_price = mc.get("stop_loss_price") or pos.get("stop_loss_price")
    entry_price     = mc.get("entry_price")     or pos.get("entry_price")

    # 採樣路徑（半透明灰線）
    for path in sample_paths:
        fig.add_trace(go.Scatter(
            x=days, y=path,
            mode="lines", line=dict(color="rgba(150,150,150,0.15)", width=1),
            showlegend=False, hoverinfo="skip",
        ))

    # 目標價 / 停損價 / 進場價水平線
    fig.add_hline(y=target_price,    line=dict(color="#2ecc71", dash="dash", width=2),
                  annotation_text=f"目標 {target_price:.1f}", annotation_position="right")
    fig.add_hline(y=stop_loss_price, line=dict(color="#e74c3c", dash="dash", width=2),
                  annotation_text=f"停損 {stop_loss_price:.1f}", annotation_position="right")
    fig.add_hline(y=entry_price,     line=dict(color="#3498db", width=1.5),
                  annotation_text=f"進場 {entry_price:.1f}", annotation_position="right")

    fig.update_layout(
        height=300, margin=dict(l=10, r=80, t=10, b=30),
        yaxis_title="價格", xaxis_title="交易日",
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("達標機率",  f"{mc['prob_target']:.1f}%")
    col2.metric("停損機率",  f"{mc['prob_stop_loss']:.1f}%")
    col3.metric("期望報酬",  f"{mc['expected_pnl_pct']:+.1f}%")


def page_positions():
    st.markdown('<div class="section-title">📈 模型持倉追蹤（模擬）</div>', unsafe_allow_html=True)
    st.caption("此區為依據模型推薦與歷史資料建立的模擬追蹤紀錄，並不代表使用者實際下單。實際交易請以「我的實際交易紀錄」為準。")

    tab_active, tab_closed = st.tabs(["🟢 持倉中", "📋 歷史紀錄"])

    with tab_active:
        if not (os.getenv("NEON_URL") or os.getenv("DATABASE_URL")):
            st.error("請設定 NEON_URL 環境變數（.env 或 Streamlit secrets）")
            return
        positions = load_positions("active")
        if not positions:
            st.info("目前無持倉。每次推薦時系統會自動建立追蹤記錄。")
        else:
            # ── 整體配置總覽 ──────────────────────────────────────
            total_alloc = sum(p["position_pct"] or 0 for p in positions)
            n_pos       = len(positions)
            # 正規化權重：各持倉佔實際配置的比例（避免 >100% 失真）
            def _w(p):
                return (p["position_pct"] or 0) / total_alloc if total_alloc > 0 else 1 / n_pos

            # 加權目前浮動損益（以各持倉占比為權重）
            weighted_cur = sum(_w(p) * (p["pnl_pct"] or 0) for p in positions)

            # 加權預期報酬：優先用 MC，無 MC 則用目標價距離
            def _exp(p):
                mc = (p["mc_result"] or {}).get("expected_pnl_pct")
                if mc is not None:
                    return mc
                # fallback：用目標價計算潛在報酬（有持倉）
                ep = p.get("entry_price") or 0
                tp = p.get("target_price") or 0
                return ((tp - ep) / ep * 100) if ep > 0 and tp > ep else 0.0
            weighted_exp = sum(_w(p) * _exp(p) for p in positions)

            cash_pct = max(0.0, 100.0 - total_alloc)

            if total_alloc > 100:
                st.warning(f"⚠️ 建議倉位合計 {total_alloc:.0f}%，超過 100%。模型推薦過度分散或資金不足，以下損益數字為正規化後的比例，需人工取捨。")

            st.markdown("#### 📊 目前配置總覽")
            r1c1, r1c2 = st.columns(2)
            r1c1.metric("持倉支數", f"{n_pos} 支",
                        help="目前追蹤中的活躍持倉數")
            r1c2.metric("剩餘現金", f"{cash_pct:.0f}%",
                        delta=f"已配置 {min(total_alloc, 100):.0f}%", delta_color="off",
                        help="100% 代表總資金，已配置為所有活躍持倉建議倉位合計")
            r2c1, r2c2 = st.columns(2)
            r2c1.metric("整體預期報酬", f"{weighted_exp:+.2f}%",
                        help="各持倉目標漲幅（或蒙地卡羅期望值）按持倉比例加權平均")
            r2c2.metric("整體目前損益", f"{weighted_cur:+.2f}%",
                        help="各持倉現價損益按持倉比例加權平均")
            st.divider()

            # 載入現價
            prices_now = load_stock_prices()

            for pos in positions:
                sid   = pos["stock_id"]
                name  = pos["name"]
                curr  = prices_now.get(sid)
                pnl   = ((curr - pos["entry_price"]) / pos["entry_price"] * 100) if curr else None
                level = pos["rec_level"] or "B"
                grade_c = {"A+": "aplus", "A": "a", "B": "b"}.get(level, "b")
                pnl_color = "#2ecc71" if (pnl or 0) >= 0 else "#e74c3c"

                with st.expander(
                    f"{'🟢' if (pnl or 0) >= 0 else '🔴'} {name}（{sid}）  "
                    f"{f'{pnl:+.1f}%' if pnl is not None else '—'}  ｜  {level}級  ｜  建倉 {pos['date_entered']}",
                    expanded=False,
                    key=f"pos_{pos['id']}"
                ):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("進場價", f"{pos['entry_price']:.2f}")
                    c2.metric("目標價", f"{pos['target_price']:.2f}" if pos["target_price"] else "—",
                              delta=f"+{pos['target_pct']:.1f}%" if pos["target_pct"] else None)
                    c3.metric("停損價", f"{pos['stop_loss_price']:.2f}" if pos["stop_loss_price"] else "—",
                              delta=f"{pos['stop_loss_pct']:.1f}%" if pos["stop_loss_pct"] else None,
                              delta_color="inverse")
                    c4.metric("建議倉位", f"{pos['position_pct']:.0f}%" if pos["position_pct"] else "—")

                    if curr:
                        st.metric("現價", f"{curr:.2f}", delta=f"{pnl:+.1f}%")

                    if pos["rationale"]:
                        st.caption(f"📌 {pos['rationale']}")

                    # 蒙地卡羅模擬（從預存 JSON 繪圖）
                    st.markdown("**蒙地卡羅模擬（未來 20 個交易日）**")
                    _monte_carlo_chart(pos)

                    # 手動關倉
                    if curr:
                        col_close, _ = st.columns([1, 3])
                        if col_close.button(f"手動關倉", key=f"close_{sid}_{pos['id']}"):
                            try:
                                from src.database import get_session, PositionMonitor
                                from datetime import date
                                s2 = get_session()
                                p = s2.query(PositionMonitor).get(pos["id"])
                                if p:
                                    p.status      = "closed_manual"
                                    p.exit_date   = date.today()
                                    p.exit_price  = curr
                                    p.exit_reason = "MANUAL"
                                    p.pnl_pct     = round(pnl, 2)
                                    s2.commit()
                                s2.close()
                                st.cache_data.clear()
                                st.success(f"已關倉 {name}（{pnl:+.1f}%）")
                                st.rerun()
                            except Exception as e:
                                st.error(f"關倉失敗：{e}")

    with tab_closed:
        for status in ["closed_profit", "closed_loss", "closed_signal", "closed_manual"]:
            rows = load_positions(status)
            for pos in rows:
                icon  = {"closed_profit": "✅", "closed_loss": "❌",
                         "closed_signal": "⚠️", "closed_manual": "🔷"}.get(status, "—")
                pnl   = pos["pnl_pct"] or 0
                color = "#2ecc71" if pnl >= 0 else "#e74c3c"
                st.markdown(
                    f"{icon} **{pos['name']}**（{pos['stock_id']}）"
                    f"  {pos['date_entered']} → {pos['exit_date'] or '—'}"
                    f"  ｜ 損益 <span style='color:{color};font-weight:700'>{pnl:+.1f}%</span>"
                    f"  ｜ {pos['exit_reason'] or '—'}",
                    unsafe_allow_html=True,
                )
        if not any(load_positions(s) for s in ["closed_profit","closed_loss","closed_signal","closed_manual"]):
            st.info("尚無歷史紀錄。")


# ── 回測 ─────────────────────────────────────────────────────

@st.cache_data(ttl=1800)
def compute_backtest() -> pd.DataFrame:
    """計算所有歷史推薦的 5/20/60 日報酬，及對比 0050、0056 的 Alpha。"""
    try:
        from collections import defaultdict
        from src.database import get_session, Recommendation, DailyPrice
        s = get_session()
        recs = s.query(Recommendation).order_by(Recommendation.date).all()
        all_ids = {r.stock_id for r in recs} | {"0050", "0056"}
        all_prices_q = (s.query(DailyPrice)
                        .filter(DailyPrice.stock_id.in_(all_ids))
                        .order_by(DailyPrice.stock_id, DailyPrice.date).all())
        s.close()

        price_map = defaultdict(list)
        for p in all_prices_q:
            price_map[p.stock_id].append((p.date, p.close))

        def _ret_at(plist, ref_date, n_trading_days):
            # 取 ref_date 當日或之後的收盤序列（交易日）
            after = [(d, c) for d, c in plist if d >= ref_date and c]
            if not after:
                return None, None
            entry = after[0][1]
            if len(after) > n_trading_days:
                exit_c = after[n_trading_days][1]
                return round((exit_c - entry) / entry * 100, 2), entry
            return None, entry

        # 台股單邊交易成本：手續費(買+賣)×0.285% + 證交稅(賣)×0.3%，不含滑價
        ROUND_TRIP_COST = 0.585

        # 20 個交易日冷卻期：同股票上次推薦後未滿 20 個交易日的重複推薦不算新樣本
        last_rec_date: dict = {}
        deduped_recs = []
        for r in sorted(recs, key=lambda x: x.date):
            prev = last_rec_date.get(r.stock_id)
            if prev is None:
                deduped_recs.append(r)
                last_rec_date[r.stock_id] = r.date
            else:
                sp_chk = price_map.get(r.stock_id, [])
                tdays = sum(1 for d, _ in sp_chk if prev < d <= r.date)
                if tdays >= 20:
                    deduped_recs.append(r)
                    last_rec_date[r.stock_id] = r.date

        today_dt = date.today()
        rows = []
        for r in deduped_recs:
            sp = price_map.get(r.stock_id, [])
            if not sp:
                continue
            s20, entry = _ret_at(sp, r.date, 20)
            s60, _     = _ret_at(sp, r.date, 60)

            # 停牌 / 下市處理：推薦超過 35 日但仍無 20 日報酬，不靜默刪除
            data_flag = None
            if s20 is None and entry is not None and (today_dt - r.date).days > 35:
                after_rec = [(d, c) for d, c in sp if d > r.date and c]
                if after_rec:
                    # 有部分交易紀錄但不足 20 日 → 停牌，用最後成交價
                    s20 = round((after_rec[-1][1] - entry) / entry * 100 - ROUND_TRIP_COST, 2)
                    data_flag = "⚠️ 停牌"
                else:
                    # 完全無後續交易 → 下市，視為最大損失（-100% 扣成本）
                    s20 = round(-100.0 - ROUND_TRIP_COST, 2)
                    data_flag = "❌ 下市"

            # 扣除交易成本（買進 + 賣出）
            if s20 is not None and data_flag is None:
                s20 = round(s20 - ROUND_TRIP_COST, 2)
            if s60 is not None:
                s60 = round(s60 - ROUND_TRIP_COST, 2)
            b0050_20, _ = _ret_at(price_map.get("0050", []), r.date, 20)
            b0050_60, _ = _ret_at(price_map.get("0050", []), r.date, 60)
            b0056_20, _ = _ret_at(price_map.get("0056", []), r.date, 20)
            b0056_60, _ = _ret_at(price_map.get("0056", []), r.date, 60)
            # benchmark 同樣扣成本，使比較基準一致
            if b0050_20 is not None: b0050_20 = round(b0050_20 - ROUND_TRIP_COST, 2)
            if b0050_60 is not None: b0050_60 = round(b0050_60 - ROUND_TRIP_COST, 2)
            if b0056_20 is not None: b0056_20 = round(b0056_20 - ROUND_TRIP_COST, 2)
            if b0056_60 is not None: b0056_60 = round(b0056_60 - ROUND_TRIP_COST, 2)

            def _a(s, b): return round(s - b, 2) if s is not None and b is not None else None

            rows.append({
                "date": r.date, "stock_id": r.stock_id,
                "confidence": r.confidence, "entry": entry,
                "ret_20d": s20, "ret_60d": s60,
                "b0050_20": b0050_20, "b0056_20": b0056_20,
                "b0050_60": b0050_60, "b0056_60": b0056_60,
                "a0050_20": _a(s20, b0050_20), "a0056_20": _a(s20, b0056_20),
                "a0050_60": _a(s60, b0050_60), "a0056_60": _a(s60, b0056_60),
                "_all_ids": list(all_ids - {r.stock_id}),
                "data_flag": data_flag,
            })
        return pd.DataFrame(rows)
    except Exception as e:
        logger.exception(f"compute_backtest failed: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def compute_random_baseline(n_sim: int = 1000) -> dict:
    """Monte Carlo：對每筆推薦日期，從當天分析股票池中隨機抽一支，計算第 20 交易日報酬。
    重複 n_sim 次，返回隨機選股平均報酬的分布。"""
    try:
        import random as _rnd
        from collections import defaultdict
        from src.database import get_session, Recommendation, DailyPrice, AnalysisResult as _AR
        s = get_session()
        recs = s.query(Recommendation).order_by(Recommendation.date).all()
        ar_rows = s.query(_AR.date, _AR.stock_id).all()
        # 擴展價格查詢：包含所有曾被分析過的股票，建立真正的分析池基準
        ar_stock_ids = {ar_sid for _, ar_sid in ar_rows}
        all_ids = {r.stock_id for r in recs} | {"0050", "0056"} | ar_stock_ids
        all_prices_q = (s.query(DailyPrice)
                        .filter(DailyPrice.stock_id.in_(all_ids))
                        .order_by(DailyPrice.stock_id, DailyPrice.date).all())
        s.close()
        price_map = defaultdict(list)
        for p in all_prices_q:
            price_map[p.stock_id].append((p.date, p.close))

        ROUND_TRIP_COST = 0.585  # 與 compute_backtest 一致

        def _ret20(plist, ref_date):
            after = [(d, c) for d, c in plist if d >= ref_date and c]
            if len(after) <= 20: return None
            return (after[20][1] - after[0][1]) / after[0][1] * 100

        # 與 compute_backtest 相同的 20 交易日冷卻期，過濾 recs
        _last: dict = {}
        deduped = []
        for r in sorted(recs, key=lambda x: x.date):
            prev = _last.get(r.stock_id)
            if prev is None:
                deduped.append(r); _last[r.stock_id] = r.date
            else:
                tdays = sum(1 for d, _ in price_map.get(r.stock_id, []) if prev < d <= r.date)
                if tdays >= 20:
                    deduped.append(r); _last[r.stock_id] = r.date

        # 預建日期索引，供冷卻期快速查詢
        import bisect as _bs
        dates_idx = {sid: sorted(d for d, _ in plist) for sid, plist in price_map.items()}

        def _tdays(sid, d1, d2):
            dl = dates_idx.get(sid, [])
            return _bs.bisect_right(dl, d2) - _bs.bisect_right(dl, d1)

        # 從 AnalysisResult 取每天實際分析過的股票池（公平隨機基準）
        analyzed_by_date: dict = defaultdict(set)
        for ar_date, ar_sid in ar_rows:
            analyzed_by_date[ar_date].add(ar_sid)

        pool_per_rec = []
        for r in deduped:
            day_pool = analyzed_by_date.get(r.date, set())
            alts = [sid for sid in day_pool if sid != r.stock_id and price_map.get(sid)]
            if not alts:
                alts = [sid for sid in all_ids if sid != r.stock_id and price_map.get(sid)]
            pool_per_rec.append((r.date, alts))

        _rng = _rnd.Random(42)  # 固定 seed，確保每次結果可重現
        sim_means = []
        for _ in range(n_sim):
            sim_rets = []
            last_pick: dict = {}  # 每次模擬獨立冷卻追蹤
            for ref_date, alts in pool_per_rec:
                if not alts: continue
                # 冷卻期過濾：同股票 20 個交易日內不重複抽取
                eligible = [s for s in alts if
                            last_pick.get(s) is None or _tdays(s, last_pick[s], ref_date) >= 20]
                sid = _rng.choice(eligible if eligible else alts)
                last_pick[sid] = ref_date
                ret = _ret20(price_map[sid], ref_date)
                if ret is not None:
                    sim_rets.append(ret - ROUND_TRIP_COST)  # 扣同樣交易成本
            if sim_rets:
                sim_means.append(sum(sim_rets) / len(sim_rets))
        return {"sim_means": sim_means, "n_sim": n_sim}
    except Exception as e:
        logger.exception(f"compute_random_baseline failed: {e}")
        return {}


def _calc_stats(ret: pd.Series, alpha: pd.Series, hold_days: int) -> dict:
    r = ret.dropna(); a = alpha.dropna()
    if len(r) < 5: return {}
    from scipy import stats as _sc
    t, p = _sc.ttest_1samp(a, 0)
    cum = (1 + r / 100).cumprod()
    mdd = ((cum - cum.cummax()) / cum.cummax() * 100).min()
    return {
        "n": len(r), "mean_ret": r.mean(),
        "mean_alpha": a.mean(), "win_alpha": (a > 0).mean() * 100,
        "ir": a.mean() / a.std() if a.std() > 0 else 0,
        "sharpe": r.mean() / r.std() * (252 / hold_days) ** 0.5 if r.std() > 0 else 0,
        "t": t, "p": p, "sig": p < 0.05, "mdd": mdd,
    }


def _calc_beta(ret_s: pd.Series, ret_m: pd.Series):
    df = pd.DataFrame({"s": ret_s, "m": ret_m}).dropna()
    if len(df) < 5: return None
    var_m = df["m"].var()
    return round(df["s"].cov(df["m"]) / var_m, 2) if var_m > 0 else None


def _model_confidence(st_dict: dict) -> tuple:
    """根據樣本數、p 值、Alpha、IR 計算模型信心分數（1–5 星）"""
    if not st_dict:
        return 1, "★☆☆☆☆", "樣本不足，無法評估"
    n, p, alpha, ir = st_dict["n"], st_dict["p"], st_dict["mean_alpha"], st_dict["ir"]
    score = 0
    score += 3 if n >= 80 else 2 if n >= 40 else 1 if n >= 20 else 0   # 樣本數
    score += 3 if p < 0.05 else 2 if p < 0.10 else 1 if p < 0.20 else 0  # p 值
    score += 3 if alpha > 2 else 2 if alpha > 0.5 else 1 if alpha > 0 else 0  # Alpha
    score += 3 if ir > 0.5 else 2 if ir > 0.2 else 1 if ir > 0 else 0    # IR
    stars = max(1, min(5, round(score / 2.5 + 0.5)))
    descs = {1: "效力存疑，請持續累積樣本",
             2: "初步跡象，尚無統計支撐",
             3: "尚可，需跨越更多市場環境",
             4: "良好，具初步超額報酬能力",
             5: "優秀，Alpha 統計顯著"}
    return stars, "★" * stars + "☆" * (5 - stars), descs[stars]


def page_backtest():
    import altair as alt
    from datetime import date as _date
    st.markdown('<div class="section-title">🔬 模型驗證</div>', unsafe_allow_html=True)

    df = compute_backtest()
    if df.empty:
        st.info("尚無足夠歷史資料，請先執行分析並同步。")
        return

    # 停牌 / 下市統計（已用最後成交或 -100% 計入，不靜默刪除）
    n_flagged = df["data_flag"].notna().sum() if "data_flag" in df.columns else 0
    halt_count = (df["data_flag"] == "⚠️ 停牌").sum() if "data_flag" in df.columns else 0
    delist_count = (df["data_flag"] == "❌ 下市").sum() if "data_flag" in df.columns else 0

    sub = df.dropna(subset=["ret_20d", "b0050_20"]).sort_values("date").copy()
    if sub.empty:
        st.info("尚無足夠價格資料（需同步後等待回測窗口完成）。")
        return

    st20 = _calc_stats(sub["ret_20d"], sub["a0050_20"].dropna(), 20)
    st20_56 = _calc_stats(sub["ret_20d"], sub["a0056_20"].dropna(), 20)

    cutoff    = date.today()
    model_mean = sub["ret_20d"].mean()
    bench_mean = sub["b0050_20"].mean()
    alpha_mean = sub["a0050_20"].mean()
    win_bench  = (sub["a0050_20"] > 0).mean() * 100
    beta       = _calc_beta(sub["ret_20d"], sub["b0050_20"])
    p_val      = st20["p"]   if st20 else None
    ir         = st20["ir"]  if st20 else None
    sharpe     = st20["sharpe"] if st20 else None
    mdd        = st20["mdd"] if st20 else None
    n_samp     = st20["n"]   if st20 else len(sub)
    conf_stars, conf_str, conf_desc = _model_confidence(st20)

    if p_val is not None:
        if p_val < 0.05:   verdict, verdict_color = "✅ 有統計顯著的超額報酬（p < 0.05）", "#00c851"
        elif p_val < 0.15: verdict, verdict_color = "⚠️ 初步跡象但尚不顯著（p < 0.15）", "#ffbb33"
        else:              verdict, verdict_color = "❌ 目前沒有足夠證據顯示模型優於大盤", "#ff4444"
    else:
        verdict, verdict_color = "—", "#888"

    # ── 樣本數警告 ────────────────────────────────────────────
    if n_samp < 30:
        st.error(f"⚠️ 樣本數僅 {n_samp} 筆（建議至少 30 筆），統計結論可靠性低，請勿過度解讀 p 值與 Alpha。")
    elif n_samp < 60:
        st.warning(f"⚠️ 樣本數 {n_samp} 筆，建議累積至 60+ 筆後統計結論才較穩定。")

    # ── 模型信心分數 ──────────────────────────────────────────
    conf_color = ["#ff4444","#ff4444","#ffbb33","#ffbb33","#00c851"][conf_stars - 1]
    st.markdown(f"""
<div style="background:#1a1a2e;border:1px solid #333;border-radius:12px;padding:16px 20px;margin-bottom:12px">
  <div style="display:flex;align-items:center;gap:12px">
    <div style="font-size:1.5rem;color:{conf_color}">{conf_str}</div>
    <div>
      <div style="font-size:0.7rem;color:#888">模型信心分數（樣本數 · p 值 · Alpha · IR 綜合）</div>
      <div style="font-size:0.85rem;color:{conf_color};font-weight:600">{conf_desc}</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

    # ── 完整指標卡 ────────────────────────────────────────────
    def _m(label, val, color="#fff"):
        return f'<div style="background:#111;border-radius:8px;padding:10px 12px"><div style="font-size:0.68rem;color:#888">{label}</div><div style="font-size:1.1rem;font-weight:700;color:{color}">{val}</div></div>'

    ac = "#00c851" if alpha_mean >= 0 else "#ff4444"
    st.markdown(f"""
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px">
  {_m("樣本數（冷卻後）", f"{n_samp} 筆")}
  {_m("20日均報酬（淨）", f"{model_mean:+.2f}%", "#667eea")}
  {_m("Alpha vs 0050（淨）", f"{alpha_mean:+.2f}%", ac)}
  {_m("Beta", f"{beta:.2f}" if beta is not None else "—")}
  {_m("Sharpe Ratio", f"{sharpe:.2f}" if sharpe is not None else "—")}
  {_m("IR（資訊比率）", f"{ir:.2f}" if ir is not None else "—")}
  {_m("p 值", f"{p_val:.3f}" if p_val is not None else "—")}
  {_m("勝率 vs 0050", f"{win_bench:.0f}%")}
  {_m("推薦序列 MDD", f"{mdd:.1f}%" if mdd is not None else "—")}
</div>""", unsafe_allow_html=True)

    # ── 結論 ──────────────────────────────────────────────────
    st.markdown(f"""
<div style="background:#1a1a2e;border:1px solid #333;border-radius:8px;padding:12px 16px;margin-bottom:16px">
  <div style="color:{verdict_color};font-size:0.95rem;font-weight:600">{verdict}</div>
  <div style="color:#888;font-size:0.75rem;margin-top:6px">
    ⚠️ 模型、0050、0056、隨機基準報酬均已扣除單次買賣成本 0.585%（手續費＋證交稅），未扣滑價 ·
    模型與隨機基準均套用 20 交易日冷卻期（同股票不重複計算）·
    回測期間偏短，需持續累積跨越完整財報週期的樣本<br>
    {"⚠️ 本回測含 " + str(n_flagged) + " 筆停牌/下市紀錄（停牌用最後成交價、下市用 -100%），不靜默刪除以保留完整損益。 · " if n_flagged > 0 else ""}
    ⚠️ 倖存者偏差：分析池僅含現存且有完整價格資料的股票，歷史上已下市標的無法納入，可能使績效偏高。
  </div>
</div>""", unsafe_allow_html=True)

    # ── Monte Carlo 隨機選股基準 ──────────────────────────────
    st.markdown("#### 🎲 隨機選股基準（Monte Carlo 1000 次模擬）")
    st.caption("在相同日期隨機從當天 AnalysisResult 股票池中選一支（排除實際推薦股，限有價格資料者），重複 1000 次，比較模型是否有識別能力。")

    with st.spinner("計算中…"):
        mc = compute_random_baseline(1000)

    if mc and mc.get("sim_means"):
        sim_means = mc["sim_means"]
        rand_mean = sum(sim_means) / len(sim_means)
        percentile = sum(1 for x in sim_means if x < model_mean) / len(sim_means) * 100

        c1, c2, c3 = st.columns(3)
        c1.metric("模型 20日均報酬（淨）", f"{model_mean:+.2f}%")
        c2.metric("隨機選股均報酬", f"{rand_mean:+.2f}%",
                  f"{'模型領先' if model_mean > rand_mean else '模型落後'} {abs(model_mean-rand_mean):.2f}%",
                  delta_color="normal" if model_mean > rand_mean else "inverse")
        c3.metric("模型位於隨機分布", f"第 {percentile:.0f} 百分位",
                  "✅ 有識別能力" if percentile >= 75 else "⚠️ 尚未顯著優於隨機")

        # 直方圖：隨機分布 + 模型位置
        mc_df = pd.DataFrame({"mean_ret": sim_means, "type": ["隨機"] * len(sim_means)})
        hist = (alt.Chart(mc_df).mark_bar(opacity=0.7, color="#667eea")
                .encode(x=alt.X("mean_ret:Q", bin=alt.Bin(maxbins=40), title="模擬平均報酬 (%)"),
                        y=alt.Y("count()", title="次數"))
                .properties(height=220))
        model_line = alt.Chart(pd.DataFrame({"x": [model_mean]})).mark_rule(
            color="#ff8800", strokeWidth=2.5
        ).encode(x="x:Q")
        model_label = alt.Chart(pd.DataFrame({"x": [model_mean], "y": [len(sim_means)//8],
                                               "text": [f"模型 {model_mean:+.2f}%"]})).mark_text(
            color="#ff8800", fontSize=11, align="left", dx=6
        ).encode(x="x:Q", y="y:Q", text="text:N")
        st.altair_chart(hist + model_line + model_label, use_container_width=True)

    st.markdown("---")

    # ── 策略 vs 0050 vs 0056 累積報酬曲線 ─────────────────────
    st.markdown("#### 推薦序列累積報酬（各筆 20 日報酬連乘）")
    st.caption("⚠️ 此為推薦序列績效，非真實投資組合報酬。同期推薦多檔或持倉重疊時，累積曲線可能高估或低估實際績效。")
    trade_no = list(range(1, len(sub) + 1))
    cum_s   = ((1 + sub["ret_20d"]  / 100).cumprod() * 100 - 100).tolist()
    cum_50  = ((1 + sub["b0050_20"] / 100).cumprod() * 100 - 100).tolist()
    sub56 = sub.dropna(subset=["b0056_20"])
    cum_56  = ((1 + sub56["b0056_20"] / 100).cumprod() * 100 - 100).tolist() if not sub56.empty else []

    curve_data = (
        [{"trade_no": i+1, "cum": v, "type": "策略"}       for i, v in enumerate(cum_s)]
      + [{"trade_no": i+1, "cum": v, "type": "0050"}        for i, v in enumerate(cum_50)]
      + ([{"trade_no": i+1, "cum": v, "type": "0056（高息）"} for i, v in enumerate(cum_56)] if cum_56 else [])
    )
    curve_df = pd.DataFrame(curve_data)
    line = (alt.Chart(curve_df).mark_line()
            .encode(
                x=alt.X("trade_no:Q", title="推薦筆數"),
                y=alt.Y("cum:Q", title="累積報酬 (%)"),
                color=alt.Color("type:N", scale=alt.Scale(
                    domain=["策略", "0050", "0056（高息）"],
                    range=["#667eea", "#aaaaaa", "#ffbb33"])),
                tooltip=["trade_no:Q", "type:N", alt.Tooltip("cum:Q", format=".1f")],
            ).properties(height=260))
    zero = alt.Chart(pd.DataFrame({"y":[0]})).mark_rule(color="#444", strokeDash=[4,4]).encode(y="y:Q")
    st.altair_chart(line + zero, use_container_width=True)

    # ── 各窗口完整統計表 ─────────────────────────────────────
    st.markdown("#### 各基準完整統計（20 日）")
    tbl = []
    for bench_label, ak, bk in [("vs 0050", "a0050_20", "b0050_20"), ("vs 0056", "a0056_20", "b0056_20")]:
        valid = sub.dropna(subset=["ret_20d", bk])
        st_d = _calc_stats(valid["ret_20d"], valid[ak], 20)
        if not st_d: continue
        tbl.append({
            "基準": bench_label, "樣本": st_d["n"],
            "模型均報酬": f"{st_d['mean_ret']:+.2f}%",
            "均 Alpha": f"{st_d['mean_alpha']:+.2f}%",
            "勝率 vs 基準": f"{st_d['win_alpha']:.0f}%",
            "IR": f"{st_d['ir']:.2f}",
            "t 值": f"{st_d['t']:.2f}",
            "p 值": f"{st_d['p']:.3f}",
            "顯著": "✅" if st_d["sig"] else "⚠️",
            "推薦序列 MDD": f"{st_d['mdd']:.1f}%",
        })
    if tbl:
        st.dataframe(pd.DataFrame(tbl), use_container_width=True, hide_index=True)

    # ── 逐筆 Alpha 柱狀圖 ────────────────────────────────────
    st.markdown("#### 逐筆 Alpha vs 0050（20 日）")
    bar_df = sub.copy()
    bar_df["label"] = bar_df["date"].astype(str) + " " + bar_df["stock_id"]
    bar_df["color"] = bar_df["a0050_20"].apply(lambda x: "#00c851" if (x or 0) >= 0 else "#ff4444")
    bar = (alt.Chart(bar_df.dropna(subset=["a0050_20"])).mark_bar()
           .encode(
               x=alt.X("label:N", sort=None,
                        axis=alt.Axis(labelAngle=-60, labelLimit=60, labelFontSize=8)),
               y=alt.Y("a0050_20:Q", title="Alpha (%)"),
               color=alt.Color("color:N", scale=None),
               tooltip=["date:T", "stock_id:N",
                        alt.Tooltip("ret_20d:Q",  format=".2f", title="策略%"),
                        alt.Tooltip("b0050_20:Q", format=".2f", title="0050%"),
                        alt.Tooltip("a0050_20:Q", format=".2f", title="Alpha%")],
           ).properties(height=240))
    zero2 = alt.Chart(pd.DataFrame({"y":[0]})).mark_rule(color="#888", strokeDash=[4,4]).encode(y="y:Q")
    st.altair_chart(bar + zero2, use_container_width=True)

    # ── 明細 ────────────────────────────────────────────────
    with st.expander("📋 推薦明細", expanded=False):
        cols = ["date","stock_id","confidence","entry","ret_20d","b0050_20","a0050_20","b0056_20","a0056_20"]
        if "data_flag" in df.columns:
            cols.append("data_flag")
        show = df[cols].copy()
        col_names = ["日期","股票","信心","進場價","20日%","0050%","Alpha_0050","0056%","Alpha_0056"]
        if "data_flag" in df.columns:
            col_names.append("備注")
        show.columns = col_names
        show = show.sort_values("日期", ascending=False)
        def _c(v):
            if pd.isna(v): return "color:#888"
            return "color:#00c851;font-weight:600" if v > 0 else "color:#ff4444;font-weight:600"
        st.dataframe(show.style.map(_c, subset=["20日%","Alpha_0050","Alpha_0056"]),
                     use_container_width=True, hide_index=True)


# ── 設定 ─────────────────────────────────────────────────────

def page_guide():
    st.markdown('<div class="section-title">📖 評分說明</div>', unsafe_allow_html=True)
    st.caption("本平台以五個維度對每支股票評分（0–100 分），綜合分由各維度加權計算。")

    st.markdown("---")

    # 品質
    st.markdown("### 🔵 品質分（財務體質）")
    st.markdown("""
評估公司的**基本面健康程度**，越高代表財務越穩健。

| 指標 | 說明 |
|---|---|
| ROE（股東權益報酬率） | 越高越好，長期 > 15% 為優 |
| ROA（總資產報酬率） | 衡量資產運用效率 |
| 毛利率 | 反映產品競爭力，越高越佳 |
| 負債比率 | 越低越安全，< 40% 為健康 |
| EPS 趨勢 | 每股盈餘是否持續成長 |
| 自由現金流 | 正數代表實際有在賺錢 |

**分數解讀**：90+ 財務極優 ｜ 70–89 穩健 ｜ 50–69 普通 ｜ < 50 需注意
    """)

    st.markdown("---")

    # 時機
    st.markdown("### 🔵 時機分（技術進場）")
    st.markdown("""
評估**現在是否是好的進場時機**，根據價格與成交量型態判斷。

| 指標 | 說明 |
|---|---|
| 均線排列（MA5/20/60） | 短中長均線多頭排列為正訊號 |
| RSI（相對強弱指標） | 30 以下超賣（可能反彈），70 以上超買（需謹慎） |
| MACD | 黃金交叉（訊號線上穿）為買進訊號 |
| KD 指標 | 低檔黃金交叉為進場參考 |
| 成交量 | 量增價漲確認趨勢，量縮要小心 |

**分數解讀**：90+ 強勢進場 ｜ 70–89 偏多 ｜ 50–69 中性 ｜ < 50 偏空或整理
    """)

    st.markdown("---")

    # 籌碼
    st.markdown("### 🔵 籌碼分（法人動向）")
    st.markdown("""
追蹤**三大法人（外資、投信、自營商）**的買賣超動向。法人資金龐大，其方向往往影響後市。

| 法人 | 特性 |
|---|---|
| 外資 | 資金最大，長線布局為主 |
| 投信（基金） | 月底、季底容易調整，短線影響較大 |
| 自營商 | 偏短線，波動較大，參考為輔 |

**正訊號**：外資 + 投信同步買超、連續多日累積買超
**負訊號**：法人大幅賣超、外資連續出走

**分數解讀**：80+ 法人積極買進 ｜ 60–79 小幅偏多 ｜ 40–59 中性 ｜ < 40 法人賣超
    """)

    st.markdown("---")

    # 風險
    st.markdown("### 🔵 風險分（波動風險）")
    st.markdown("""
評估**持有這支股票的風險程度**，分數越高代表風險越低（越安全）。

| 風險因子 | 說明 |
|---|---|
| 股價波動率 | 短期漲跌幅是否過大 |
| 距均線距離 | 股價離均線太遠，回測機率提高 |
| 市場情緒 | 大盤處於恐慌還是貪婪狀態 |
| 成交量異常 | 爆量可能是主力出貨訊號 |
| 財務槓桿 | 負債高的公司在景氣下行時風險加倍 |

**分數解讀**：85+ 風險極低 ｜ 70–84 風險可控 ｜ 55–69 需留意 ｜ < 55 高風險
    """)

    st.markdown("---")

    # 綜合
    st.markdown("### 🟣 綜合分（加權總分）")
    st.markdown("""
各維度加權後的**最終評分**，反映整體投資吸引力。

| 加權比例 | 說明 |
|---|---|
| 品質 × 40% | 基本面為核心，先確認公司體質 |
| 時機 × 25% | 進場點很重要，好公司也要等好時機 |
| 籌碼 × 20% | 法人方向提供趨勢確認 |
| 情報 × 10% | 新聞、外資報告等市場情報 |
| 風險 × 5%  | 控制下行風險，保護資本 |

| 綜合分 | 等級 | 建議 |
|---|---|---|
| 85 分以上 | A+ 級 | 強烈值得深入研究 |
| 75–84 分 | A 級  | 值得深入研究 |
| 65–74 分 | B 級  | 列入觀察清單 |
| 55–64 分 | C 級  | 條件不足，繼續觀察 |
| 55 分以下 | D 級  | 不建議研究 |
    """)

    st.markdown("---")

    # 信心度
    st.markdown("### ⚪ 分析信心度")
    st.markdown("""
反映**本次分析結果的可靠程度**，受資料完整性影響。

| 扣分原因 | 扣幾分 |
|---|---|
| 無基本面資料（FinMind 未設定） | -20 |
| 歷史價格資料不足（< 14 天） | -15 |
| 無籌碼資料 | -10 |
| 技術面與基本面方向相反 | -10 至 -15 |
| 風險分數偏低（< 65） | -10 至 -20 |

信心度 **80%+** 為高可信度；**65%** 通常代表資料不完整，結果僅供參考。
    """)


def page_settings(selected_date: date):
    st.markdown('<div class="section-title">設定 & 執行</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**查看日期**")
        _min_date = date(2025, 1, 1)
        _clamped  = max(selected_date, _min_date)
        new_date = st.date_input("分析日期", value=_clamped,
                                 min_value=_min_date, max_value=date.today(),
                                 label_visibility="collapsed")
        if new_date != selected_date:
            st.session_state["selected_date"] = new_date
            st.rerun()

    with col2:
        st.markdown("**執行分析**")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🧪 Dry-run", use_container_width=True):
                with st.spinner("執行中..."):
                    _run_analysis(dry_run=True)
        with c2:
            if st.button("▶ 今日分析", use_container_width=True):
                with st.spinner("執行中（約 30 秒）..."):
                    _run_analysis(dry_run=False)

    st.divider()
    st.markdown('<div class="section-title">資料庫狀態</div>', unsafe_allow_html=True)
    try:
        from src.database import get_session, DailyPrice, InstitutionalData, Recommendation
        from sqlalchemy import func
        s = get_session()
        price_cnt = 0
        chip_cnt  = 0
        oldest    = None
        newest    = None
        try:
            price_cnt = s.query(func.count(DailyPrice.id)).scalar() or 0
            chip_cnt  = s.query(func.count(InstitutionalData.id)).scalar() or 0
            oldest    = s.query(func.min(DailyPrice.date)).filter(DailyPrice.date >= '2025-01-01').scalar()
            newest    = s.query(func.max(DailyPrice.date)).scalar()
        except Exception as e:
            logger.debug(f"page_settings price date query failed: {e}")  # 雲端版無本機股價資料
        rec_cnt = s.query(func.count(Recommendation.id)).scalar() or 0
        s.close()
        if price_cnt > 0:
            st.markdown(f"""
            <div class="stat-grid">
              <div class="stat-box">
                <div class="stat-val" style="font-size:1.4rem">{price_cnt:,}</div>
                <div class="stat-lbl">股價紀錄</div>
              </div>
              <div class="stat-box">
                <div class="stat-val" style="font-size:1.4rem">{chip_cnt:,}</div>
                <div class="stat-lbl">法人紀錄</div>
              </div>
              <div class="stat-box">
                <div class="stat-val" style="font-size:1.4rem">{rec_cnt}</div>
                <div class="stat-lbl">推薦紀錄</div>
              </div>
              <div class="stat-box">
                <div class="stat-val" style="font-size:0.85rem; color:#667eea">{oldest or '—'}</div>
                <div class="stat-lbl">研究起始日期</div>
              </div>
            </div>
            """, unsafe_allow_html=True)
            if newest:
                st.caption(f"最新股價：{newest}")
        else:
            st.markdown(f"""
            <div class="stat-grid">
              <div class="stat-box">
                <div class="stat-val" style="font-size:1.4rem">{rec_cnt}</div>
                <div class="stat-lbl">推薦紀錄</div>
              </div>
            </div>
            """, unsafe_allow_html=True)
            st.caption("股價／法人原始資料存於本機，行動版不顯示")
    except Exception as e:
        logger.error(f"page_settings DB query failed: {e}")
        st.caption("資料庫暫時無法連線")


# ── 我的交易 ─────────────────────────────────────────────────

def _render_trade_mc(trade, current_price, n_sim=500, days=20):
    """從當前價格做 Monte Carlo 20 日預測"""
    import numpy as np
    try:
        from sqlalchemy import desc as _d
        sess = get_session()
        prices_db = sess.query(DailyPrice).filter_by(stock_id=trade.stock_id)\
            .order_by(_d(DailyPrice.date)).limit(60).all()
        sess.close()
        if len(prices_db) >= 10:
            closes = [p.close for p in reversed(prices_db)]
            rets = [closes[i]/closes[i-1]-1 for i in range(1, len(closes))]
            mu, sigma = float(np.mean(rets)), float(np.std(rets))
        else:
            mu, sigma = 0.0, 0.015
        np.random.seed(42)
        finals = []
        for _ in range(n_sim):
            p = current_price
            for _ in range(days):
                p *= (1 + np.random.normal(mu, sigma))
            finals.append(p)
        finals = np.array(finals)
        p5, p25, p50, p75, p95 = (np.percentile(finals, q) for q in [5,25,50,75,95])
        prob_t = float((finals >= trade.target_price).mean()*100) if trade.target_price else 0.0
        prob_s = float((finals <= trade.stop_price).mean()*100)   if trade.stop_price  else 0.0
        c1, c2, c3 = st.columns(3)
        c1.metric("20日後中位數", f"{p50:,.1f}", f"{(p50/current_price-1)*100:+.1f}%")
        c2.metric("達目標機率",   f"{prob_t:.0f}%")
        c3.metric("觸停損機率",   f"{prob_s:.0f}%")
        fig = go.Figure(go.Histogram(x=finals, nbinsx=40, marker_color="#764ba2", opacity=0.7))
        fig.add_vline(x=current_price, line_color="#888", line_dash="dash", annotation_text="現價")
        if trade.target_price:
            fig.add_vline(x=trade.target_price, line_color="#00c851", line_width=2, annotation_text="目標")
        if trade.stop_price:
            fig.add_vline(x=trade.stop_price,   line_color="#ff4444", line_width=2, annotation_text="停損")
        fig.update_layout(margin=dict(l=0,r=0,t=20,b=0), height=200, showlegend=False,
                          plot_bgcolor="white", paper_bgcolor="white",
                          xaxis_title="20日後預測價格", yaxis_title="模擬次數")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"5%={p5:,.1f}　25%={p25:,.1f}　中位={p50:,.1f}　75%={p75:,.1f}　95%={p95:,.1f}")
    except Exception as e:
        st.caption(f"MC 計算失敗：{e}")


def page_my_trades():
    st.markdown('<div class="section-title">💼 我的實際交易紀錄</div>', unsafe_allow_html=True)
    stock_prices = load_stock_prices()

    # ── 新增交易 ──────────────────────────────────────────────
    with st.expander("➕ 新增交易"):
        stock_list = load_stock_list()
        stock_labels = [lbl for lbl, _ in stock_list]
        with st.form("add_trade_form", clear_on_submit=True):
            stock_sel = st.selectbox("股票（輸入名稱或代號搜尋）", options=stock_labels,
                                     index=None, placeholder="例：台積電 或 2330")
            c1, c2 = st.columns(2)
            with c1:
                buy_date_in = st.date_input("買入日期", value=date.today())
                notes_in    = st.text_input("備註（選填）")
            with c2:
                buy_price_in = st.number_input("買入均價（元，含手續費，依券商顯示填入）", min_value=0.0, step=0.5, format="%.2f")
                shares_in    = st.number_input("股數（整張=1000股，零股直接填）",
                                               min_value=1, step=1, value=1000)
            c3, c4 = st.columns(2)
            with c3:
                target_in = st.number_input("目標價（0 = 自動 +10%）", min_value=0.0, step=0.5, format="%.2f")
            with c4:
                stop_in   = st.number_input("停損價（0 = 自動 -7%）",  min_value=0.0, step=0.5, format="%.2f")
            if st.form_submit_button("✅ 新增", use_container_width=True):
                sid = dict(stock_list).get(stock_sel, "") if stock_sel else ""
                if not sid or buy_price_in <= 0:
                    st.error("請選擇股票並填寫買入價格")
                else:
                    # 從 selectbox 解析名稱（格式：「名稱（代號）」）
                    sname = stock_sel.split("（")[0].strip() if stock_sel else sid
                    t_price = target_in if target_in > 0 else round(buy_price_in * 1.10, 1)
                    s_price = stop_in   if stop_in   > 0 else round(buy_price_in * 0.93, 1)
                    _s = get_session()
                    _s.add(UserTrade(
                        stock_id=sid.strip(), stock_name=sname,
                        buy_date=buy_date_in, buy_price=buy_price_in,
                        shares=int(shares_in), target_price=t_price, stop_price=s_price,
                        status="holding", notes=notes_in,
                    ))
                    _s.commit(); _s.close()
                    st.success(f"✅ {sname}（{sid.strip()}）已新增！")
                    st.rerun()

    # ── 讀取所有交易 ───────────────────────────────────────────
    _sess = get_session()
    all_trades = _sess.query(UserTrade).order_by(UserTrade.buy_date.desc()).all()
    _sess.close()
    holdings = [t for t in all_trades if t.status == "holding"]
    closed   = [t for t in all_trades if t.status == "closed"]

    # ── 目前持倉 ───────────────────────────────────────────────
    st.markdown(f'<div class="section-title">📌 目前持倉（{len(holdings)} 筆）</div>', unsafe_allow_html=True)
    if not holdings:
        st.info("尚無持倉，點上方「新增交易」加入第一筆。")

    BUY_FEE  = 0.001425   # 買入手續費
    SELL_FEE = 0.004425   # 賣出手續費 + 證交稅

    for trade in holdings:
        cur = stock_prices.get(trade.stock_id)
        cur_date_label = "TWSE"
        if not cur:
            try:
                from sqlalchemy import desc as _dd
                _s3 = get_session()
                _dp = _s3.query(DailyPrice).filter_by(stock_id=trade.stock_id)\
                    .order_by(_dd(DailyPrice.date)).first()
                _s3.close()
                cur = _dp.close if _dp else None
                cur_date_label = str(_dp.date) if _dp else "—"
            except Exception as e:
                logger.debug(f"trade price fallback failed ({trade.stock_id}): {e}")
                cur = None
                cur_date_label = "—"

        days_held    = (date.today() - trade.buy_date).days
        eff_buy      = trade.buy_price                         # 使用者填入的均價（已含買入手續費）
        net_cur      = cur * (1 - SELL_FEE) if cur else None  # 扣賣出手續費+稅的淨收入
        pnl_pct      = (net_cur - eff_buy) / eff_buy * 100    if net_cur else None
        pnl_amount   = (net_cur - eff_buy) * trade.shares      if net_cur else None
        total_cost   = eff_buy * trade.shares

        if cur and trade.stop_price and cur < trade.stop_price:
            signal, sig_color = "🔴 已觸停損，建議出場", "#ff4444"
        elif cur and trade.target_price and cur >= trade.target_price:
            signal, sig_color = "🟢 已達目標，考慮獲利了結", "#00c851"
        elif days_held > 60:
            signal, sig_color = "⚠️ 持有超過 60 日，重新評估", "#ffbb33"
        else:
            signal, sig_color = "🟡 持續觀察", "#888"

        pnl_color = "#00c851" if pnl_pct and pnl_pct > 0 else "#ff4444" if pnl_pct and pnl_pct < 0 else "#aaa"

        st.markdown(f"""
        <div class="rec-card" style="border-left:5px solid {pnl_color}">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
            <div>
              <div style="font-size:1.05rem;font-weight:800">{trade.stock_name}（{trade.stock_id}）</div>
              <div style="font-size:0.75rem;color:#888">買入 {trade.buy_date} @ {trade.buy_price:,.1f}元　{trade.shares}股　持有 {days_held}日</div>
            </div>
            <div style="text-align:right">
              <div style="font-size:1.4rem;font-weight:800;color:{pnl_color}">{f"{pnl_pct:+.2f}%" if pnl_pct is not None else "—"}</div>
              <div style="font-size:0.75rem;color:{pnl_color}">{f"{pnl_amount:+,.0f}元" if pnl_amount is not None else ""}</div>
              <div style="font-size:0.6rem;color:#aaa">含買賣手續費及證交稅</div>
            </div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
            <div style="flex:1;min-width:70px;background:#f5f5f5;border-radius:6px;padding:5px 8px;text-align:center">
              <div style="font-size:0.6rem;color:#888">現價（{cur_date_label}）</div>
              <div style="font-weight:700">{f"{cur:,.1f}" if cur else "—"}</div>
            </div>
            <div style="flex:1;min-width:70px;background:#e8f5e9;border-radius:6px;padding:5px 8px;text-align:center">
              <div style="font-size:0.6rem;color:#2e7d32">目標價</div>
              <div style="font-weight:700;color:#2e7d32">{f"{trade.target_price:,.1f}" if trade.target_price else "—"}</div>
            </div>
            <div style="flex:1;min-width:70px;background:#fce4ec;border-radius:6px;padding:5px 8px;text-align:center">
              <div style="font-size:0.6rem;color:#c62828">停損價</div>
              <div style="font-weight:700;color:#c62828">{f"{trade.stop_price:,.1f}" if trade.stop_price else "—"}</div>
            </div>
            <div style="flex:1;min-width:70px;background:#fff8e1;border-radius:6px;padding:5px 8px;text-align:center">
              <div style="font-size:0.6rem;color:#f57f17">成本總額（含手續費）</div>
              <div style="font-weight:700;color:#f57f17">{total_cost:,.0f}元</div>
            </div>
          </div>
          <div style="font-size:0.85rem;color:{sig_color};font-weight:600">{signal}</div>
          {f'<div style="font-size:0.75rem;color:#aaa;margin-top:4px">備註：{trade.notes}</div>' if trade.notes else ""}
        </div>
        """, unsafe_allow_html=True)

        col_mc, col_exit = st.columns([2, 1])
        with col_mc:
            if cur:
                with st.expander("📊 蒙地卡羅 20 日預測"):
                    _render_trade_mc(trade, cur)
        with col_exit:
            with st.expander("🚪 記錄出場"):
                with st.form(f"close_{trade.id}"):
                    sell_d = st.date_input("出場日", value=date.today(), key=f"sd_{trade.id}")
                    sell_p = st.number_input("出場價", min_value=0.0, step=0.5,
                                             value=float(cur or trade.buy_price), key=f"sp_{trade.id}", format="%.2f")
                    if st.form_submit_button("確認出場"):
                        net_sell = sell_p * (1 - SELL_FEE)   # 扣手續費+證交稅
                        eff_buy_c = trade.buy_price           # 均價已含買入手續費
                        r_pct = (net_sell - eff_buy_c) / eff_buy_c * 100
                        r_pnl = (net_sell - eff_buy_c) * trade.shares
                        _sx = get_session()
                        _tx = _sx.query(UserTrade).filter_by(id=trade.id).first()
                        _tx.status = "closed"; _tx.sell_date = sell_d
                        _tx.sell_price = sell_p; _tx.realized_pct = r_pct; _tx.realized_pnl = r_pnl
                        _sx.commit(); _sx.close()
                        st.success(f"損益 {r_pct:+.1f}%（{r_pnl:+,.0f}元）")
                        st.rerun()

    # ── 歷史績效 ───────────────────────────────────────────────
    if closed:
        st.markdown(f'<div class="section-title">📜 已出場紀錄（{len(closed)} 筆）</div>', unsafe_allow_html=True)
        wins     = [t for t in closed if t.realized_pct and t.realized_pct > 0]
        total_pnl = sum(t.realized_pnl for t in closed if t.realized_pnl)
        avg_pct   = sum(t.realized_pct for t in closed if t.realized_pct) / len(closed)
        win_rate  = len(wins) / len(closed) * 100
        st.markdown(f"""
        <div class="stat-grid">
          <div class="stat-box"><div class="stat-val">{len(closed)}</div><div class="stat-lbl">已出場筆數</div></div>
          <div class="stat-box"><div class="stat-val" style="color:{'#00c851' if win_rate>=50 else '#ff4444'}">{win_rate:.0f}%</div><div class="stat-lbl">勝率</div></div>
          <div class="stat-box"><div class="stat-val" style="color:{'#00c851' if avg_pct>0 else '#ff4444'}">{avg_pct:+.1f}%</div><div class="stat-lbl">平均報酬</div></div>
          <div class="stat-box"><div class="stat-val" style="font-size:1.1rem;color:{'#00c851' if total_pnl>0 else '#ff4444'}">{total_pnl/10000:+.1f}萬</div><div class="stat-lbl">實現損益</div></div>
        </div>
        """, unsafe_allow_html=True)
        rows = []
        for t in sorted(closed, key=lambda x: x.sell_date or date.min, reverse=True):
            hold_days = (t.sell_date - t.buy_date).days if t.sell_date else "—"
            rows.append({
                "股票": f"{t.stock_name}（{t.stock_id}）",
                "買入日": str(t.buy_date), "買入價": f"{t.buy_price:,.1f}",
                "出場日": str(t.sell_date or "—"), "出場價": f"{t.sell_price:,.1f}" if t.sell_price else "—",
                "股數": t.shares, "持有天": hold_days,
                "損益%": f"{t.realized_pct:+.1f}%" if t.realized_pct else "—",
                "實現損益": f"{t.realized_pnl:+,.0f}元" if t.realized_pnl else "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── 觸發分析 ─────────────────────────────────────────────────

def _run_analysis(dry_run: bool):
    import subprocess
    try:
        cmd = [sys.executable, str(Path(__file__).parent.parent / "main.py")]
        if dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        if result.returncode == 0:
            st.success("✅ 分析完成！重新整理頁面查看。")
            st.cache_data.clear()
        else:
            st.error(f"執行失敗：{result.stderr[-300:]}")
    except Exception as e:
        st.error(f"錯誤：{e}")


# ── 主程式 ────────────────────────────────────────────────────

def main():
    if "selected_date" not in st.session_state:
        st.session_state["selected_date"] = date.today()
    sel_date = st.session_state["selected_date"]

    # Sidebar（電腦版顯示，手機版 CSS 隱藏）
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; padding:20px 0 24px 0">
          <div style="font-size:2.5rem">📈</div>
          <div style="font-size:1rem; font-weight:800; color:#1a1a2e; margin-top:6px">台股 AI 研究平台</div>
          <div style="font-size:0.7rem; color:#999; margin-top:3px">v6.8</div>
        </div>
        """, unsafe_allow_html=True)
        st.caption(f"查看日期：{sel_date}")
        if st.button("🔄 重新整理資料", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        try:
            from src.database import get_session, DailyPrice, Recommendation
            from sqlalchemy import func
            s = get_session()
            cnt = s.query(func.count(DailyPrice.id)).scalar()
            newest = s.query(func.max(DailyPrice.date)).scalar()
            # 有效起始：第一筆推薦日期（有推薦才有意義的分析）
            first_rec = s.query(func.min(Recommendation.date)).scalar()
            s.close()
            if cnt > 0:
                st.metric("股價資料", f"{cnt:,} 筆")
                if newest:     st.caption(f"最新：{newest}")
                if first_rec:  st.caption(f"研究起始：{first_rec}")
            else:
                st.caption("股價資料存於本機\n需在家中執行分析")
        except Exception as e:
            logger.debug(f"guide page stock info query failed: {e}")
        st.markdown("---")
        st.markdown("""
        <div style="font-size:0.65rem; color:#aaa; text-align:center; line-height:1.6">
          本工具為 AI 研究輔助<br>所有內容不構成投資建議
        </div>
        """, unsafe_allow_html=True)

    # 手機版 Top Bar
    st.markdown("""
    <div class="top-bar">
      <h1>📈 台股 AI 研究平台</h1>
      <p>v6.8 · 研究輔助工具 · 不構成投資建議</p>
    </div>
    """, unsafe_allow_html=True)

    # Tab 導航（電腦版是橫向底線樣式，手機版是圓角膠囊樣式）
    tabs = st.tabs(["📊今日", "🔍個股", "📋歷史", "📈模型持倉", "🔬模型驗證", "💼我的交易", "📖說明", "⚙️設定"])

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
        page_guide()

    with tabs[7]:
        page_settings(sel_date)

    st.markdown('<div class="disclaimer">本工具為 AI 研究輔助，所有內容不構成投資建議，投資人應自行評估風險</div>',
                unsafe_allow_html=True)


if __name__ == "__main__":
    main()
