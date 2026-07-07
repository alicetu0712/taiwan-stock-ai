"""
loaders.py — Cached data-loading functions shared across all dashboard pages.
All DB queries are wrapped in @st.cache_data to avoid redundant round trips.
"""
import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from config import REPORTS_DIR

logger = logging.getLogger(__name__)


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
    try:
        from src.database import get_session, Stock
        from sqlalchemy import select
        s = get_session()
        rows = s.execute(select(Stock)).scalars().all()
        s.close()
        names = {r.stock_id: r.name for r in rows if r.name}
    except Exception as e:
        logger.warning(f"load_stock_names DB failed: {e}")
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
        from src.database import get_session, Recommendation, Stock, AnalysisResult, PositionMonitor, DailyPrice
        from sqlalchemy import select
        from sqlalchemy import desc as _desc
        s = get_session()
        recs_rows = s.execute(
            select(Recommendation).where(Recommendation.date == target_date)
            .order_by(Recommendation.confidence.desc())
        ).scalars().all()
        stock_name_map = {r.stock_id: r.name for r in s.execute(select(Stock)).scalars().all() if r.name}
        ar_map = {r.stock_id: r for r in s.execute(
            select(AnalysisResult).where(AnalysisResult.date == target_date)
        ).scalars().all()}
        pm_map = {r.stock_id: r for r in s.execute(select(PositionMonitor)).scalars().all()}
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
        from src.database import get_session, AnalysisResult, Stock
        from sqlalchemy import select
        s = get_session()
        rows = s.execute(
            select(AnalysisResult)
            .where(AnalysisResult.date == target_date)
            .order_by(AnalysisResult.total_score.desc())
        ).scalars().all()
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


# ── 報告解析 ──────────────────────────────────────────────────

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
        if m:
            result[key] = m.group(1)
    return result


def parse_recs_from_report(report: str) -> list:
    results = []
    sections = re.split(r'(?=### \d+\.)', report)
    for sec in sections:
        if not sec.startswith("###"):
            continue
        m_title = re.search(r'### \d+\. (.+?)（(\d{4})）', sec)
        if not m_title:
            continue
        name, sid = m_title.group(1).strip(), m_title.group(2)
        level_m = re.search(r'—— ([A-Z+]+) 級', sec)
        level   = level_m.group(1) if level_m else "B"
        scores  = {}
        for label, key in [("公司品質", "quality"), ("技術時機", "timing"),
                            ("市場行為", "behavior"), ("風險評估", "risk"), ("綜合評分", "total")]:
            sm = re.search(rf'\| {label} \| \*\*(\d+)\*\*/100', sec)
            if sm:
                scores[key] = int(sm.group(1))
        conf_m = re.search(r'\| 分析信心 \| (\d+)%', sec)
        conf   = int(conf_m.group(1)) if conf_m else 0
        adv   = re.findall(r'- ✅ (.+)', sec)
        risks = re.findall(r'• (.+)', sec)
        watch = re.findall(r'- 🔍 (.+)', sec)
        conc_m = re.search(r'\*\*AI 結論\*\*\n\n> (.+)', sec)
        conclusion = conc_m.group(1) if conc_m else ""
        results.append({
            "name": name, "sid": sid, "level": level, "scores": scores,
            "confidence": conf, "advantages": adv, "risks": risks,
            "watch": watch, "conclusion": conclusion,
        })
    return results
