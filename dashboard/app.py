"""
dashboard/app.py — Responsive Research Dashboard
電腦：寬版多欄  |  手機：窄版單欄（CSS 自動適應）
"""

import sys
import re
import json
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import REPORTS_DIR


# ── 頁面設定 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="台股 AI 研究平台 v6.1",
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
        flex: 1 !important; border-radius: 8px; font-size: 0.72rem !important;
        font-weight: 600 !important; padding: 8px 1px !important; height: 40px !important;
        min-width: 0 !important; overflow: hidden;
    }
    .stTabs [aria-selected="true"] {
        background: white !important; box-shadow: 0 2px 8px rgba(0,0,0,0.12) !important;
        color: #1a1a2e !important; border-bottom: none !important;
    }
    .rec-grid { display: block; }
    .stButton > button { width: 100%; height: 48px; border-radius: 12px; font-weight: 600; }
    [data-testid="metric-container"] {
        background: white; border-radius: 12px; padding: 12px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
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
    except Exception:
        pass
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
    except Exception:
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
    except Exception:
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
    except Exception:
        pass
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
    except Exception:
        pass
    return names


@st.cache_data(ttl=300)
def load_stock_prices() -> dict:
    """從 TWSE 抓即時收盤價，快取 5 分鐘。回傳 {stock_id: close_price}"""
    prices = {}
    try:
        import requests
        r = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            timeout=10, headers={"Accept": "application/json"}
        )
        if r.ok:
            for item in r.json():
                sid = item.get("Code", "").strip()
                close = item.get("ClosingPrice", "")
                try:
                    prices[sid] = float(str(close).replace(",", ""))
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    try:
        import requests
        r = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
            timeout=10, verify=False
        )
        if r.ok:
            for item in r.json():
                sid = str(item.get("SecuritiesCompanyCode", "")).strip()
                close = item.get("Close", "")
                try:
                    prices[sid] = float(str(close).replace(",", ""))
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
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
        s.close()
        result = []
        for r in recs_rows:
            ar = ar_map.get(r.stock_id)
            result.append({
                "name":       stock_name_map.get(r.stock_id, ""),
                "sid":        r.stock_id,
                "price":      None,
                "level":      r.rec_level or "B",
                "scores": {
                    "quality":  ar.quality_score  if ar else 0,
                    "timing":   ar.timing_score   if ar else 0,
                    "behavior": ar.behavior_score if ar else 0,
                    "risk":     ar.risk_score     if ar else 0,
                    "total":    ar.total_score    if ar else 0,
                },
                "confidence": r.confidence or 0,
                "advantages": json.loads(r.advantages)   if r.advantages   else [],
                "risks":      json.loads(r.risks)        if r.risks        else [],
                "watch":      json.loads(r.watch_points) if r.watch_points else [],
                "conclusion": r.ai_conclusion or "",
                "summary":    r.summary or "",
            })
        return result
    except Exception:
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
    except Exception:
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
    chg_color = "#00c851" if "+" in str(idx_chg) else "#ff4444" if "-" in str(idx_chg) else "white"

    today_log = logs[logs["date"] == selected_date] if not logs.empty else pd.DataFrame()
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
      <div class="market-meta">{selected_date} · AI Taiwan Equity Research v6.0</div>
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

    # DB 無推薦時降級到 markdown 解析
    if not recs:
        recs_section = re.search(r'## ③ Research Candidates.*?\n(.*?)(?=## ④|## 免責)', report, re.DOTALL)
        content = recs_section.group(1) if recs_section else ""
        recs = parse_recs_from_report(content)

    # 仍無推薦：用分析結果補卡片（前 8 名）
    if not recs and not results_df.empty:
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

@st.cache_data(ttl=120)
def load_positions(status: str = "active") -> list:
    """直連 Neon 讀取 position_monitor，不依賴 get_session()。"""
    import os, json as _json
    neon_url = os.getenv(
        "DATABASE_URL",
        "postgresql://neondb_owner:npg_JFIrfHWh56Ka@ep-raspy-paper-aozvpvba-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    )
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
        except Exception:
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
    except Exception:
        return []


def _monte_carlo_chart(pos: dict, prices: list = None):
    """從預存的 mc_result JSON 繪製蒙地卡羅模擬圖。"""
    mc = pos.get("mc_result")
    if not mc:
        st.caption("蒙地卡羅資料尚未計算，待下次每日更新後顯示。")
        return

    import plotly.graph_objects as go
    fig = go.Figure()

    days          = mc["days"]
    sample_paths  = mc["sample_paths"]
    target_price  = mc["target_price"]
    stop_loss_price = mc["stop_loss_price"]
    entry_price   = mc["entry_price"]

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
    st.markdown('<div class="section-title">📈 持倉追蹤</div>', unsafe_allow_html=True)

    tab_active, tab_closed = st.tabs(["🟢 持倉中", "📋 歷史紀錄"])

    with tab_active:
        positions = load_positions("active")
        if not positions:
            st.info("目前無持倉。每次推薦時系統會自動建立追蹤記錄。")
        else:
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
                    expanded=False
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
                        if col_close.button(f"手動關倉", key=f"close_{sid}"):
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
| 品質 × 30% | 基本面為核心，先確認公司體質 |
| 時機 × 25% | 進場點很重要，好公司也要等好時機 |
| 籌碼 × 20% | 法人方向提供趨勢確認 |
| 風險 × 25% | 控制下行風險，保護資本 |

| 綜合分 | 建議 |
|---|---|
| 75 分以上 | A 級 — 值得深入研究 |
| 60–74 分 | B 級 — 列入觀察清單 |
| 45–59 分 | C 級 — 條件不足，繼續觀察 |
| 45 分以下 | D 級 — 不建議研究 |
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
        new_date = st.date_input("", value=selected_date, max_value=date.today(),
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
            oldest    = s.query(func.min(DailyPrice.date)).scalar()
            newest    = s.query(func.max(DailyPrice.date)).scalar()
        except Exception:
            pass  # 雲端版無本機股價資料，顯示 0
        rec_cnt = s.query(func.count(Recommendation.id)).scalar() or 0
        s.close()
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
            <div class="stat-lbl">最早股價日期</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
        if newest:
            st.caption(f"最新股價：{newest}")
        elif price_cnt == 0:
            st.caption("股價資料存於本機，雲端版顯示 0 筆為正常")
    except Exception:
        st.caption("資料庫暫時無法連線")


# ── 觸發分析 ─────────────────────────────────────────────────

def _run_analysis(dry_run: bool):
    import subprocess
    try:
        cmd = [sys.executable, str(Path(__file__).parent.parent / "main.py")]
        if dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
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
          <div style="font-size:0.7rem; color:#999; margin-top:3px">v6.0</div>
        </div>
        """, unsafe_allow_html=True)
        st.caption(f"查看日期：{sel_date}")
        if st.button("🔄 重新整理資料", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        try:
            from src.database import get_session, DailyPrice
            from sqlalchemy import func
            s = get_session()
            cnt = s.query(func.count(DailyPrice.id)).scalar()
            newest = s.query(func.max(DailyPrice.date)).scalar()
            s.close()
            if cnt > 0:
                st.metric("股價資料", f"{cnt:,} 筆")
                if newest: st.caption(f"最新：{newest}")
            else:
                st.caption("股價資料存於本機\n需在家中執行分析")
        except Exception:
            pass
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
      <p>v6.0 · 研究輔助工具 · 不構成投資建議</p>
    </div>
    """, unsafe_allow_html=True)

    # Tab 導航（電腦版是橫向底線樣式，手機版是圓角膠囊樣式）
    tabs = st.tabs(["📊今日", "🔍個股", "📋歷史", "📈持倉", "📖說明", "⚙️設定"])

    with tabs[0]:
        page_today(sel_date)

    with tabs[1]:
        page_search()

    with tabs[2]:
        page_history()

    with tabs[3]:
        page_positions()

    with tabs[4]:
        page_guide()

    with tabs[5]:
        page_settings(sel_date)

    st.markdown('<div class="disclaimer">本工具為 AI 研究輔助，所有內容不構成投資建議，投資人應自行評估風險</div>',
                unsafe_allow_html=True)


if __name__ == "__main__":
    main()
