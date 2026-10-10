"""
loaders.py — Cached data-loading functions shared across all dashboard pages.
All DB queries are wrapped in @st.cache_data to avoid redundant round trips.
"""

import json
import logging
import re
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config import REPORTS_DIR

logger = logging.getLogger(__name__)


@st.cache_data(ttl=1800)
def load_report(report_date: date) -> str:
    try:
        from src.database import DailyReport, get_session

        s = get_session()
        r = s.query(DailyReport).filter_by(date=report_date).first()
        s.close()
        if r and r.content_md:
            return r.content_md
    except Exception as e:
        logger.warning(f"load_report({report_date}) DB failed: {e}")
    path = REPORTS_DIR / "daily" / f"{report_date.isoformat()}_report.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


@st.cache_data(ttl=1800)
def load_exec_logs(limit: int = 90) -> pd.DataFrame:
    try:
        from sqlalchemy import func, select

        from src.database import ExecutionLog, get_session

        s = get_session()
        subq = (
            select(func.max(ExecutionLog.id).label("max_id"))
            .group_by(ExecutionLog.date)
            .subquery()
        )
        rows = (
            s.execute(
                select(ExecutionLog)
                .where(ExecutionLog.id.in_(select(subq.c.max_id)))
                .order_by(ExecutionLog.date.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        s.close()
        return pd.DataFrame(
            [
                {
                    "date": r.date,
                    "status": r.status,
                    "analyzed": r.total_stocks,
                    "qualified": r.qualified_stocks,
                    "recs": r.recommended_stocks,
                }
                for r in rows
            ]
        )
    except Exception as e:
        logger.warning(f"load_exec_logs failed: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=1800)
def load_recent_recs(days: int = 60) -> pd.DataFrame:
    try:
        from sqlalchemy import select

        from src.database import Recommendation, get_session

        s = get_session()
        since = date.today() - timedelta(days=days)
        rows = (
            s.execute(
                select(Recommendation)
                .where(Recommendation.date >= since)
                .order_by(Recommendation.date.desc())
            )
            .scalars()
            .all()
        )
        s.close()
        return pd.DataFrame(
            [
                {
                    "date": r.date,
                    "stock_id": r.stock_id,
                    "rec_level": r.rec_level,
                    "confidence": r.confidence,
                    "summary": r.summary,
                    "advantages": json.loads(r.advantages) if r.advantages else [],
                    "risks": json.loads(r.risks) if r.risks else [],
                    "watch_points": (
                        json.loads(r.watch_points) if r.watch_points else []
                    ),
                    "ai_conclusion": r.ai_conclusion or "",
                }
                for r in rows
            ]
        )
    except Exception as e:
        logger.warning(f"load_recent_recs failed: {e}")
        return pd.DataFrame()


def _is_etf_or_excluded(sid: str, name: str) -> bool:
    """判斷是否為 ETF/權證/非個股標的，需從清單中排除。"""
    from config import EXCLUDE_KEYWORDS, EXCLUDE_PATTERNS
    import re
    # 代碼以 0 開頭 → ETF（0050, 0056 等）
    if sid.startswith("0"):
        return True
    # 代碼含英文字母 → 權證/DR 等
    if re.search(r"[A-Za-z]", sid):
        return True
    # 名稱含排除關鍵字
    name_upper = name.upper()
    if any(kw.upper() in name_upper for kw in EXCLUDE_KEYWORDS):
        return True
    # 代碼 pattern 比對
    for pat in EXCLUDE_PATTERNS:
        if re.match(pat, sid):
            return True
    return False


@st.cache_data(ttl=86400)
def load_stock_names() -> dict:
    """股票代號→名稱對照表：優先讀本地 DB，再從 TWSE API 補缺（排除 ETF/非個股）"""
    names = {}
    try:
        from sqlalchemy import select

        from src.database import Stock, get_session

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
            timeout=8,
            headers={"Accept": "application/json"},
        )
        if r.ok:
            for item in r.json():
                sid = item.get("Code", "").strip()
                name = item.get("Name", "").strip()
                # 已在 DB 中的優先保留 DB 名稱，且排除非個股標的
                if sid and name and sid not in names and not _is_etf_or_excluded(sid, name):
                    names[sid] = name
    except Exception as e:
        logger.warning(f"load_stock_names TWSE API failed: {e}")
    # 移除 DB 中本身就是 ETF/非個股的條目
    return {sid: name for sid, name in names.items() if not _is_etf_or_excluded(sid, name)}


@st.cache_data(ttl=86400)
def load_stock_list() -> list:
    """回傳 [(顯示文字, stock_id), ...] 供 selectbox 搜尋用（已排除 ETF/非個股）。"""
    names = load_stock_names()
    return sorted(
        [(f"{name}（{sid}）", sid) for sid, name in names.items()], key=lambda x: x[1]
    )


@st.cache_data(ttl=300)
def load_stock_prices() -> dict:
    """讀取 DB 最新一日收盤價。回傳 {stock_id: close_price}"""
    prices = {}
    try:
        from sqlalchemy import func

        from src.database import DailyPrice, get_session

        s = get_session()
        latest_date = s.query(func.max(DailyPrice.date)).scalar()
        if latest_date:
            rows = (
                s.query(DailyPrice.stock_id, DailyPrice.close)
                .filter_by(date=latest_date)
                .all()
            )
            prices = {sid: close for sid, close in rows if close}
        s.close()
    except Exception as e:
        logger.warning(f"load_stock_prices failed: {e}")
    return prices


@st.cache_data(ttl=1800)
def load_db_recommendations(target_date: date) -> list:
    """從 DB recommendations 表讀取當日推薦，組成 render_rec_card 所需格式。"""
    try:
        from sqlalchemy import desc as _desc
        from sqlalchemy import select

        from src.database import (
            AnalysisResult,
            DailyPrice,
            PositionMonitor,
            Recommendation,
            Stock,
            get_session,
        )

        s = get_session()
        recs_rows = (
            s.execute(
                select(Recommendation)
                .where(
                    Recommendation.date == target_date,
                    Recommendation.tier == "recommend",
                )
                .order_by(Recommendation.confidence.desc())
            )
            .scalars()
            .all()
        )
        stock_rows = s.execute(select(Stock)).scalars().all()
        stock_name_map = {r.stock_id: r.name for r in stock_rows if r.name}
        industry_map   = {
            r.stock_id: r.industry
            for r in stock_rows
            if getattr(r, "industry", None)
        }
        ar_map = {
            r.stock_id: r
            for r in s.execute(
                select(AnalysisResult).where(AnalysisResult.date == target_date)
            )
            .scalars()
            .all()
        }
        pm_map = {
            r.stock_id: r for r in s.execute(select(PositionMonitor)).scalars().all()
        }
        rec_ids = [r.stock_id for r in recs_rows]
        db_price_map = {}
        for sid in rec_ids:
            dp = s.execute(
                select(DailyPrice)
                .where(DailyPrice.stock_id == sid)
                .order_by(_desc(DailyPrice.date))
                .limit(1)
            ).scalar_one_or_none()
            if dp:
                db_price_map[sid] = dp.close
        s.close()

        # Consecutive Core Picks days per stock
        consecutive_map: dict = {}
        try:
            from collections import defaultdict
            s2 = get_session()
            if rec_ids:
                past_rows = (
                    s2.execute(
                        select(Recommendation.stock_id, Recommendation.date)
                        .where(
                            Recommendation.stock_id.in_(rec_ids),
                            Recommendation.tier == "recommend",
                            Recommendation.date <= target_date,
                        )
                        .order_by(Recommendation.stock_id, Recommendation.date.desc())
                    )
                    .all()
                )
                s2.close()
                hist: dict = defaultdict(list)
                for sid, d in past_rows:
                    hist[sid].append(d)
                for sid, dates in hist.items():
                    dates_sorted = sorted(dates, reverse=True)
                    cnt = 1
                    for i in range(1, len(dates_sorted)):
                        if (dates_sorted[i - 1] - dates_sorted[i]).days <= 5:
                            cnt += 1
                        else:
                            break
                    consecutive_map[sid] = cnt
        except Exception as _e:
            logger.warning(f"consecutive_map: {_e}")

        result = []
        for r in recs_rows:
            ar = ar_map.get(r.stock_id)
            pm = pm_map.get(r.stock_id)
            result.append(
                {
                    "name": getattr(r, "stock_name", None) or stock_name_map.get(r.stock_id, ""),
                    "sid": r.stock_id,
                    "price": db_price_map.get(r.stock_id),
                    "level": r.rec_level or "B",
                    "scores": {
                        "quality": ar.quality_score if ar else 0,
                        "timing": ar.timing_score if ar else 0,
                        "behavior": ar.behavior_score if ar else 0,
                        "risk": ar.risk_score if ar else 0,
                        "total": ar.total_score if ar else 0,
                    },
                    "confidence": r.confidence or 0,
                    "advantages": json.loads(r.advantages) if r.advantages else [],
                    "risks": json.loads(r.risks) if r.risks else [],
                    "watch": json.loads(r.watch_points) if r.watch_points else [],
                    "conclusion": r.ai_conclusion or "",
                    "summary": r.summary or "",
                    "target_price": pm.target_price if pm else None,
                    "stop_loss_price": pm.stop_loss_price if pm else None,
                    "position_pct": pm.position_pct if pm else None,
                    # V2 Decision Center fields
                    "trade_signal":      getattr(r, "trade_signal", None) or "wait",
                    "setup_type":        getattr(r, "setup_type", None) or "none",
                    "ma20_gap":          getattr(r, "ma20_gap", None),
                    "price_trend_score": getattr(r, "price_trend_score", None),
                    "entry_low":         getattr(r, "entry_low", None),
                    "entry_high":        getattr(r, "entry_high", None),
                    "stop_price":        getattr(r, "stop_price", None),
                    "target1":           getattr(r, "target1", None),
                    "target2":           getattr(r, "target2", None),
                    "atr":               getattr(r, "atr", None),
                    "vol_ratio":         getattr(r, "vol_ratio", None),
                    # P3/P4 fields
                    "industry":          industry_map.get(r.stock_id, ""),
                    "consecutive_days":  consecutive_map.get(r.stock_id, 1),
                }
            )
        return result
    except Exception as e:
        logger.warning(f"load_db_recommendations failed: {e}")
        return []


@st.cache_data(ttl=1800)
def load_opportunity_recs(target_date: date) -> list:
    """從 DB 讀取當日 tier='opportunity' 的推薦（New Opportunities），供 overview 頁獨立顯示。"""
    try:
        from sqlalchemy import select

        from src.database import AnalysisResult, DailyPrice, Recommendation, Stock, get_session
        from sqlalchemy import desc as _desc

        s = get_session()
        rows = (
            s.execute(
                select(Recommendation)
                .where(
                    Recommendation.date == target_date,
                    Recommendation.tier == "opportunity",
                )
                .order_by(Recommendation.total_score.desc())
            )
            .scalars()
            .all()
        )
        stock_name_map = {
            r.stock_id: r.name
            for r in s.execute(select(Stock)).scalars().all()
            if r.name
        }
        ar_map = {
            r.stock_id: r
            for r in s.execute(
                select(AnalysisResult).where(AnalysisResult.date == target_date)
            ).scalars().all()
        }
        db_price_map = {}
        for r in rows:
            dp = s.execute(
                select(DailyPrice)
                .where(DailyPrice.stock_id == r.stock_id)
                .order_by(_desc(DailyPrice.date))
                .limit(1)
            ).scalar_one_or_none()
            if dp:
                db_price_map[r.stock_id] = dp.close
        s.close()
        result = []
        for r in rows:
            ar = ar_map.get(r.stock_id)
            result.append({
                "name": r.stock_name or stock_name_map.get(r.stock_id, ""),
                "sid": r.stock_id,
                "price": db_price_map.get(r.stock_id),
                "level": r.rec_level or "B",
                "total_score": r.total_score or 0,
                "score_change_5d": r.score_change_5d,
                "score_change_10d": r.score_change_10d,
                "scores": {
                    "quality": ar.quality_score if ar else 0,
                    "timing": ar.timing_score if ar else 0,
                    "behavior": ar.behavior_score if ar else 0,
                    "risk": ar.risk_score if ar else 0,
                    "total": r.total_score or (ar.total_score if ar else 0),
                },
                "confidence": r.confidence or 0,
                "timing_change_5d": r.timing_change_5d,
                "behavior_change_5d": r.behavior_change_5d,
                "advantages": json.loads(r.advantages) if r.advantages else [],
                "risks": json.loads(r.risks) if r.risks else [],
                "watch": json.loads(r.watch_points) if r.watch_points else [],
                "summary": r.summary or "",
            })
        return result
    except Exception as e:
        logger.warning(f"load_opportunity_recs failed: {e}")
        return []


@st.cache_data(ttl=1800)
def load_watch_recs(target_date: date) -> list:
    """從 DB 讀取當日 tier='watch' 的觀察名單（由 DecisionEngine.select_watchlist 產生）。"""
    try:
        from sqlalchemy import select
        from src.database import AnalysisResult, Recommendation, Stock, get_session

        s = get_session()
        rows = (
            s.execute(
                select(Recommendation)
                .where(
                    Recommendation.date == target_date,
                    Recommendation.tier == "watch",
                )
                .order_by(Recommendation.total_score.desc())
            )
            .scalars()
            .all()
        )
        stock_name_map = {
            r.stock_id: r.name
            for r in s.execute(select(Stock)).scalars().all()
            if r.name
        }
        ar_map = {
            r.stock_id: r
            for r in s.execute(
                select(AnalysisResult).where(AnalysisResult.date == target_date)
            ).scalars().all()
        }
        s.close()
        result = []
        for r in rows:
            ar = ar_map.get(r.stock_id)
            result.append({
                "name": r.stock_name or stock_name_map.get(r.stock_id, r.stock_id),
                "sid": r.stock_id,
                "total_score": r.total_score or 0,
                "timing_score": r.timing_score or 0,
                "behavior_score": r.behavior_score or 0,
                "confidence": r.confidence or 0,
                "score_change_5d": r.score_change_5d,
                "quality": ar.quality_score if ar else 0,
                "risk": ar.risk_score if ar else 0,
            })
        return result
    except Exception as e:
        logger.warning(f"load_watch_recs failed: {e}")
        return []


@st.cache_data(ttl=1800)
def load_analysis_results(target_date: date) -> pd.DataFrame:
    try:
        from sqlalchemy import select

        from src.database import AnalysisResult, Stock, get_session

        s = get_session()
        rows = (
            s.execute(
                select(AnalysisResult)
                .where(AnalysisResult.date == target_date)
                .order_by(AnalysisResult.total_score.desc())
            )
            .scalars()
            .all()
        )
        stock_name_map = {
            r.stock_id: r.name
            for r in s.execute(select(Stock)).scalars().all()
            if r.name
        }
        s.close()
        return pd.DataFrame(
            [
                {
                    "stock_id": r.stock_id,
                    "name": stock_name_map.get(r.stock_id, r.stock_id),
                    "grade": r.quality_grade,
                    "quality": r.quality_score,
                    "timing": r.timing_score,
                    "behavior": r.behavior_score,
                    "risk": r.risk_score,
                    "total": r.total_score,
                    "confidence": r.confidence,
                    "rec_level": r.rec_level,
                }
                for r in rows
            ]
        )
    except Exception as e:
        logger.warning(f"load_analysis_results failed: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=1800)
def load_stock_history(stock_id: str) -> dict:
    """個股歷史推薦 + 分析結果（最新 30 筆），TTL=30 分鐘。"""
    try:
        from sqlalchemy import select

        from src.database import AnalysisResult, Recommendation, get_session

        s = get_session()
        sid = stock_id.strip()
        recs = (
            s.execute(
                select(Recommendation)
                .where(Recommendation.stock_id == sid)
                .order_by(Recommendation.date.desc())
                .limit(30)
            )
            .scalars()
            .all()
        )
        analyses = (
            s.execute(
                select(AnalysisResult)
                .where(AnalysisResult.stock_id == sid)
                .order_by(AnalysisResult.date.desc())
                .limit(30)
            )
            .scalars()
            .all()
        )
        s.close()
        return {"recs": recs, "analyses": analyses}
    except Exception as e:
        logger.warning(f"load_stock_history({stock_id}) failed: {e}")
        return {"recs": [], "analyses": []}


@st.cache_data(ttl=1800)
def load_db_stats() -> dict:
    """DB 統計數字（股價/法人/推薦筆數 + 日期範圍），TTL=30 分鐘。"""
    try:
        from sqlalchemy import func

        from src.database import (
            DailyPrice,
            InstitutionalData,
            Recommendation,
            get_session,
        )

        s = get_session()
        price_cnt = s.query(func.count(DailyPrice.id)).scalar() or 0
        chip_cnt = s.query(func.count(InstitutionalData.id)).scalar() or 0
        oldest = (
            s.query(func.min(DailyPrice.date))
            .filter(DailyPrice.date >= "2025-01-01")
            .scalar()
        )
        newest = s.query(func.max(DailyPrice.date)).scalar()
        rec_cnt = s.query(func.count(Recommendation.id)).scalar() or 0
        s.close()
        return {
            "price_cnt": price_cnt,
            "chip_cnt": chip_cnt,
            "rec_cnt": rec_cnt,
            "oldest": oldest,
            "newest": newest,
        }
    except Exception as e:
        logger.warning(f"load_db_stats failed: {e}")
        return {}


# ── 報告解析 ──────────────────────────────────────────────────


def parse_market_summary(report: str) -> dict:
    result = {}
    for pattern, key in [
        (r"\| 加權指數 \| ([\d,.]+)", "index"),
        (r"\| 漲跌幅 \| ([+-]?[\d.]+%)", "change"),
        (r"\| 市場情緒 \| .* (Bullish|Neutral|Bearish)", "sentiment"),
        (r"\| 上漲家數 \| (\d+)", "up"),
        (r"\| 下跌家數 \| (\d+)", "down"),
    ]:
        m = re.search(pattern, report)
        if m:
            result[key] = m.group(1)
    return result


def parse_recs_from_report(report: str) -> list:
    results = []
    sections = re.split(r"(?=### \d+\.)", report)
    for sec in sections:
        if not sec.startswith("###"):
            continue
        m_title = re.search(r"### \d+\. (.+?)（(\d{4})）", sec)
        if not m_title:
            continue
        name, sid = m_title.group(1).strip(), m_title.group(2)
        level_m = re.search(r"—— ([A-Z+]+) 級", sec)
        level = level_m.group(1) if level_m else "B"
        scores = {}
        for label, key in [
            ("公司品質", "quality"),
            ("技術時機", "timing"),
            ("市場行為", "behavior"),
            ("風險評估", "risk"),
            ("綜合評分", "total"),
        ]:
            sm = re.search(rf"\| {label} \| \*\*(\d+)\*\*/100", sec)
            if sm:
                scores[key] = int(sm.group(1))
        conf_m = re.search(r"\| 分析信心 \| (\d+)%", sec)
        conf = int(conf_m.group(1)) if conf_m else 0
        adv = re.findall(r"- ✅ (.+)", sec)
        risks = re.findall(r"• (.+)", sec)
        watch = re.findall(r"- 🔍 (.+)", sec)
        conc_m = re.search(r"\*\*AI 結論\*\*\n\n> (.+)", sec)
        conclusion = conc_m.group(1) if conc_m else ""
        results.append(
            {
                "name": name,
                "sid": sid,
                "level": level,
                "scores": scores,
                "confidence": conf,
                "advantages": adv,
                "risks": risks,
                "watch": watch,
                "conclusion": conclusion,
            }
        )
    return results


@st.cache_data(ttl=600)
def load_price_chart_data(stock_id: str, days: int = 120) -> pd.DataFrame:
    """個股最近 N 日 OHLCV，供 K 線圖使用。TTL=10 分鐘。"""
    try:
        from sqlalchemy import select

        from src.database import DailyPrice, get_session

        s = get_session()
        rows = (
            s.execute(
                select(DailyPrice)
                .where(DailyPrice.stock_id == stock_id.strip())
                .order_by(DailyPrice.date.desc())
                .limit(days)
            )
            .scalars()
            .all()
        )
        s.close()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(
            [
                {
                    "date":       r.date,
                    "open":       r.open,
                    "high":       r.high,
                    "low":        r.low,
                    "close":      r.close,
                    "volume":     r.volume,
                    "change_pct": r.change_pct,
                }
                for r in rows
            ]
        )
        df = df.sort_values("date").reset_index(drop=True)
        # 不轉 datetime：macOS ARM64 + pandas3 + numpy2 + Python3.13 會在 datetime array 操作時 SIGBUS crash
        df["date"] = df["date"].astype(str)
        return df
    except Exception as e:
        logger.warning(f"load_price_chart_data({stock_id}) failed: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=600)
def load_latest_pt_analysis(stock_id: str) -> dict:
    """讀取個股最新一筆 AnalysisResult（V2 欄位），供看盤頁顯示。TTL=10 分鐘。"""
    try:
        from sqlalchemy import select

        from src.database import AnalysisResult, get_session

        s = get_session()
        row = (
            s.execute(
                select(AnalysisResult)
                .where(AnalysisResult.stock_id == stock_id.strip())
                .order_by(AnalysisResult.date.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        s.close()
        if not row:
            return {}
        return {
            "date":              row.date,
            "price_trend_score": row.price_trend_score,
            "timing_score":      row.timing_score,
            "quality_score":     row.quality_score,
            "behavior_score":    row.behavior_score,
            "total_score":       row.total_score,
            "setup_type":        getattr(row, "setup_type", None),
            "ma20_gap":          getattr(row, "ma20_gap", None),
            "volume_ratio":      getattr(row, "volume_ratio", None),
            "trade_signal":      getattr(row, "trade_signal", None),
            "rec_level":         row.rec_level,
        }
    except Exception as e:
        logger.warning(f"load_latest_pt_analysis({stock_id}) failed: {e}")
        return {}


@st.cache_data(ttl=600)
def load_watchable_stocks(sel_date: date) -> list[dict]:
    """回傳看盤用股票清單：今日推薦優先，fallback 到 analysis_results top-20。TTL=10 分鐘。"""
    try:
        from sqlalchemy import text

        from src.database import get_session

        s = get_session()

        # 直接用原始 SQL 只取需要的欄位，避免 ORM 讀取不存在的新欄位
        rows = s.execute(
            text("""
                SELECT r.stock_id, COALESCE(r.stock_name, st.name, r.stock_id) AS name,
                       COALESCE(r.tier, 'recommend') AS tier
                FROM recommendations r
                LEFT JOIN stocks st ON st.stock_id = r.stock_id
                WHERE r.date = :d
                ORDER BY r.tier, r.id DESC
            """),
            {"d": sel_date},
        ).fetchall()

        if not rows:
            # fallback：從 analysis_results 取今日 total_score 最高的 20 支
            rows = s.execute(
                text("""
                    SELECT ar.stock_id,
                           COALESCE(st.name, ar.stock_id) AS name,
                           'analysis' AS tier
                    FROM analysis_results ar
                    LEFT JOIN stocks st ON st.stock_id = ar.stock_id
                    WHERE ar.date = :d
                    ORDER BY ar.total_score DESC
                    LIMIT 20
                """),
                {"d": sel_date},
            ).fetchall()

        s.close()
        seen = set()
        result = []
        for r in rows:
            sid = r[0]
            if sid not in seen:
                seen.add(sid)
                result.append({"sid": sid, "name": r[1] or "", "tier": r[2] or "recommend"})
        return result
    except Exception as e:
        logger.warning(f"load_watchable_stocks failed: {e}")
        return []


@st.cache_data(ttl=3600)
def load_current_regime() -> str:
    """Compute current market regime from 0050 (cached 1h)."""
    try:
        from src.services.evidence_service import get_current_regime
        return get_current_regime()
    except Exception as e:
        logger.warning(f"load_current_regime: {e}")
        return "neutral"


@st.cache_data(ttl=3600)
def load_evidence_stats(setup_type: str, market_regime: str) -> dict:
    """
    Load similar-signal evidence stats for Decision Center (cached 1h per combination).
    Returns {"research": {...}, "forward": {...}, "narrative": str}.
    """
    try:
        from src.services.evidence_service import (
            evidence_narrative,
            forward_evidence,
            research_evidence,
        )
        re_ev = research_evidence(setup_type, market_regime)
        fe_ev = forward_evidence(setup_type, market_regime)
        narrative = evidence_narrative(re_ev, fe_ev)
        return {"research": re_ev, "forward": fe_ev, "narrative": narrative}
    except Exception as e:
        logger.warning(f"load_evidence_stats({setup_type}, {market_regime}): {e}")
        return {"research": {"n": 0}, "forward": {"total_recorded": 0}, "narrative": ""}


@st.cache_data(ttl=300)
def load_pipeline_funnel(target_date: date) -> dict:
    """Load today's pipeline funnel stats from PipelineFunnel table (cached 5 min)."""
    try:
        from sqlalchemy import select
        from src.database import PipelineFunnel, get_session
        s = get_session()
        row = s.execute(
            select(PipelineFunnel).where(PipelineFunnel.date == target_date)
        ).scalar_one_or_none()
        s.close()
        if not row:
            return {}
        return {
            "universe":         row.universe or 0,
            "with_price":       row.with_price or 0,
            "hard_filter_pass": row.hard_filter_pass or 0,
            "recommended":      row.recommended or 0,
        }
    except Exception as e:
        logger.warning(f"load_pipeline_funnel: {e}")
        return {}


@st.cache_data(ttl=300)
def load_market_health(target_date) -> dict:
    """
    Assess today's trading environment for the No-Trade-Today banner.
    Combines: 0050 regime + pipeline pass rate + Core Picks count.
    level: "green" (normal) / "yellow" (caution) / "red" (avoid new positions)
    """
    try:
        from src.services.evidence_service import get_current_regime
        from src.database import PipelineFunnel, Recommendation, get_session
        from sqlalchemy import select, func as _func
        s = get_session()
        funnel_row = s.execute(
            select(PipelineFunnel).where(PipelineFunnel.date == target_date)
        ).scalar_one_or_none()
        recs_count = s.execute(
            select(_func.count()).select_from(Recommendation).where(
                Recommendation.date == target_date,
                Recommendation.tier == "recommend",
            )
        ).scalar() or 0
        s.close()

        regime    = get_current_regime()
        universe  = funnel_row.universe if funnel_row else 0
        hf_pass   = funnel_row.hard_filter_pass if funnel_row else 0
        pass_rate = round((hf_pass / universe * 100), 1) if universe > 0 else 0.0

        conditions = []
        level = "green"

        if regime == "bear":
            conditions.append("0050 跌破 MA60 且 MA60 轉弱（確認空頭 Regime）")
            level = "red"

        if 0 < universe < 200:
            conditions.append(f"今日有效股價資料僅 {universe} 檔（可能資料蒐集異常）")
            level = "red"

        if universe >= 200 and pass_rate < 3.0 and level == "green":
            conditions.append(f"通過趨勢條件比例偏低（{pass_rate}%），市場整體動能弱")
            level = "yellow"

        if recs_count == 0 and level == "green":
            conditions.append("今日無股票通過完整篩選條件（V2 + DQ Gate）")
            level = "yellow"

        return {
            "level": level,
            "regime": regime,
            "universe": universe,
            "pass_rate": pass_rate,
            "recs_count": recs_count,
            "conditions": conditions,
        }
    except Exception as e:
        logger.warning(f"load_market_health: {e}")
        return {"level": "unknown", "conditions": [], "regime": "neutral",
                "universe": 0, "pass_rate": 0, "recs_count": 0}
