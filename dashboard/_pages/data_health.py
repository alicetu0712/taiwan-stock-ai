"""
data_health.py — 資料品質監控頁面

顯示各資料來源的新鮮度、覆蓋率與狀態，
讓使用者快速掌握「哪個資料抓不到」。
"""

import logging
from datetime import date, timedelta

import streamlit as st

from dashboard.db import (
    AnalysisResult,
    DailyPrice,
    Recommendation,
    get_session,
)

logger = logging.getLogger(__name__)

# ── 狀態色碼 ─────────────────────────────────────────────────
_GREEN = "#2ecc71"
_YELLOW = "#f39c12"
_RED = "#e74c3c"
_GRAY = "#95a5a6"


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;'
        f"padding:2px 10px;border-radius:12px;font-size:0.78rem;"
        f'font-weight:600">{text}</span>'
    )


def _staleness(latest_date) -> tuple:
    """回傳 (days_old, color, label)。"""
    if latest_date is None:
        return None, _GRAY, "無資料"
    today = date.today()
    delta = (today - latest_date).days
    if delta == 0:
        return delta, _GREEN, "今日"
    elif delta <= 3:
        return delta, _GREEN, f"{delta} 天前"
    elif delta <= 7:
        return delta, _YELLOW, f"{delta} 天前"
    else:
        return delta, _RED, f"{delta} 天前 ⚠️"


@st.cache_data(ttl=300)
def _load_health_metrics() -> dict:
    """從 DB 蒐集各資料來源的健康指標，TTL=5 分鐘。"""
    metrics = {}
    try:
        from sqlalchemy import func

        from src.database import (
            ExecutionLog,
            FinancialQuarter,
            InstitutionalData,
            MonthlyRevenue,
        )

        s = get_session()

        # ── 股價 ──────────────────────────────────────────────
        price_total = s.query(func.count(DailyPrice.id)).scalar() or 0
        price_latest = s.query(func.max(DailyPrice.date)).scalar()
        price_today_cnt = (
            s.query(func.count(DailyPrice.id))
            .filter(DailyPrice.date == price_latest)
            .scalar()
            or 0
            if price_latest
            else 0
        )
        price_distinct = (
            s.query(func.count(func.distinct(DailyPrice.stock_id))).scalar() or 0
        )
        metrics["price"] = {
            "total": price_total,
            "latest": price_latest,
            "latest_cnt": price_today_cnt,
            "distinct_stocks": price_distinct,
        }

        # ── 三大法人 ──────────────────────────────────────────
        chip_latest = s.query(func.max(InstitutionalData.date)).scalar()
        chip_latest_cnt = (
            s.query(func.count(InstitutionalData.id))
            .filter(InstitutionalData.date == chip_latest)
            .scalar()
            or 0
            if chip_latest
            else 0
        )
        metrics["chip"] = {
            "latest": chip_latest,
            "latest_cnt": chip_latest_cnt,
        }

        # ── 財務資料（季報）──────────────────────────────────
        fin_stocks = (
            s.query(func.count(func.distinct(FinancialQuarter.stock_id))).scalar() or 0
        )
        fin_latest_year = s.query(func.max(FinancialQuarter.year)).scalar()
        fin_latest_q = (
            s.query(func.max(FinancialQuarter.quarter))
            .filter(FinancialQuarter.year == fin_latest_year)
            .scalar()
            if fin_latest_year
            else None
        )
        fin_coverage = (
            round(fin_stocks / price_distinct * 100, 1) if price_distinct > 0 else 0.0
        )
        metrics["financial"] = {
            "stocks": fin_stocks,
            "latest_year": fin_latest_year,
            "latest_q": fin_latest_q,
            "coverage_pct": fin_coverage,
        }

        # ── 月營收 ────────────────────────────────────────────
        rev_stocks = (
            s.query(func.count(func.distinct(MonthlyRevenue.stock_id))).scalar() or 0
        )
        rev_latest_year = s.query(func.max(MonthlyRevenue.year)).scalar()
        rev_latest_month = (
            s.query(func.max(MonthlyRevenue.month))
            .filter(MonthlyRevenue.year == rev_latest_year)
            .scalar()
            if rev_latest_year
            else None
        )
        metrics["revenue"] = {
            "stocks": rev_stocks,
            "latest_year": rev_latest_year,
            "latest_month": rev_latest_month,
        }

        # ── 研究推薦 ──────────────────────────────────────────
        rec_latest = s.query(func.max(Recommendation.date)).scalar()
        rec_30d = (
            s.query(func.count(Recommendation.id))
            .filter(Recommendation.date >= date.today() - timedelta(days=30))
            .scalar()
            or 0
        )
        metrics["recommendation"] = {
            "latest": rec_latest,
            "last_30d": rec_30d,
        }

        # ── 分析結果 ──────────────────────────────────────────
        ar_latest = s.query(func.max(AnalysisResult.date)).scalar()
        ar_7d = (
            s.query(func.count(AnalysisResult.id))
            .filter(AnalysisResult.date >= date.today() - timedelta(days=7))
            .scalar()
            or 0
        )
        metrics["analysis"] = {
            "latest": ar_latest,
            "last_7d": ar_7d,
        }

        # ── 最近執行記錄（最新 5 筆）────────────────────────
        exec_logs = (
            s.query(ExecutionLog).order_by(ExecutionLog.date.desc()).limit(5).all()
        )
        metrics["exec_logs"] = [
            {
                "date": r.date,
                "status": r.status,
                "total": r.total_stocks,
                "qualified": r.qualified_stocks,
                "recommended": r.recommended_stocks,
                "errors": r.errors,
            }
            for r in exec_logs
        ]

        s.close()

    except Exception as e:
        logger.warning(f"data health metrics load failed: {e}")

    return metrics


def _render_source_row(
    label: str,
    icon: str,
    latest_date,
    detail: str,
    extra: str = "",
) -> None:
    """渲染一行資料來源狀態。"""
    days_old, color, freshness_label = _staleness(latest_date)
    cols = st.columns([2, 2, 2, 3])
    with cols[0]:
        st.markdown(f"**{icon} {label}**")
    with cols[1]:
        if latest_date:
            st.caption(str(latest_date))
        else:
            st.caption("—")
    with cols[2]:
        st.markdown(_badge(freshness_label, color), unsafe_allow_html=True)
    with cols[3]:
        st.caption(detail + (f"  {extra}" if extra else ""))


def page_data_health() -> None:
    st.subheader("🩺 資料品質監控")
    st.caption("各資料來源的新鮮度與覆蓋率。每 5 分鐘自動更新。")

    if st.button("🔄 立即刷新", key="health_refresh"):
        st.cache_data.clear()
        st.rerun()

    m = _load_health_metrics()
    if not m:
        st.error("無法連線資料庫，請確認環境設定。")
        return

    st.markdown("---")

    # ── 總覽卡片 ─────────────────────────────────────────────
    price_m = m.get("price", {})
    fin_m = m.get("financial", {})
    chip_m = m.get("chip", {})
    rec_m = m.get("recommendation", {})

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        price_total = price_m.get("total", 0)
        _, color, _ = _staleness(price_m.get("latest"))
        st.markdown(
            f'<div style="text-align:center;padding:12px;border-radius:8px;'
            f'border:2px solid {color}20;background:{color}10">'
            f'<div style="font-size:1.6rem;font-weight:800;color:{color}">'
            f"{price_total:,}</div>"
            f'<div style="font-size:0.75rem;color:#666">💹 股價資料（總筆）</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
    with c2:
        chip_cnt = chip_m.get("latest_cnt", 0)
        _, color, _ = _staleness(chip_m.get("latest"))
        st.markdown(
            f'<div style="text-align:center;padding:12px;border-radius:8px;'
            f'border:2px solid {color}20;background:{color}10">'
            f'<div style="font-size:1.6rem;font-weight:800;color:{color}">'
            f"{chip_cnt:,}</div>"
            f'<div style="font-size:0.75rem;color:#666">📊 法人（最新交易日）</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
    with c3:
        fin_pct = fin_m.get("coverage_pct", 0.0)
        fin_color = _GREEN if fin_pct >= 80 else _YELLOW if fin_pct >= 50 else _RED
        st.markdown(
            f'<div style="text-align:center;padding:12px;border-radius:8px;'
            f'border:2px solid {fin_color}20;background:{fin_color}10">'
            f'<div style="font-size:1.6rem;font-weight:800;color:{fin_color}">'
            f"{fin_pct:.0f}%</div>"
            f'<div style="font-size:0.75rem;color:#666">📈 財務覆蓋率</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
    with c4:
        rec_30d = rec_m.get("last_30d", 0)
        rec_color = _GREEN if rec_30d > 0 else _RED
        st.markdown(
            f'<div style="text-align:center;padding:12px;border-radius:8px;'
            f'border:2px solid {rec_color}20;background:{rec_color}10">'
            f'<div style="font-size:1.6rem;font-weight:800;color:{rec_color}">'
            f"{rec_30d}</div>"
            f'<div style="font-size:0.75rem;color:#666">📋 近 30 天推薦</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── 逐來源狀態表 ─────────────────────────────────────────
    st.markdown("#### 各資料來源狀態")

    header_cols = st.columns([2, 2, 2, 3])
    for col, label in zip(header_cols, ["來源", "最新日期", "新鮮度", "詳情"]):
        col.markdown(f"<small><b>{label}</b></small>", unsafe_allow_html=True)
    st.markdown('<hr style="margin:4px 0 8px 0">', unsafe_allow_html=True)

    # 股價
    _render_source_row(
        "股價",
        "💹",
        price_m.get("latest"),
        f"{price_m.get('latest_cnt', 0):,} 檔 (今日) ／ 總計 {price_m.get('total', 0):,} 筆",
    )

    # 三大法人
    _render_source_row(
        "三大法人",
        "📊",
        chip_m.get("latest"),
        f"{chip_m.get('latest_cnt', 0):,} 檔 (最新交易日)",
    )

    # 財務季報
    fin_latest_str = (
        f"{fin_m.get('latest_year')}Q{fin_m.get('latest_q')}"
        if fin_m.get("latest_year")
        else "—"
    )
    _render_source_row(
        "財務季報",
        "📈",
        None,  # 財務資料無具體日期，用文字
        f"{fin_m.get('stocks', 0):,} 檔有資料 (覆蓋 {fin_m.get('coverage_pct', 0):.1f}%)",
        f"最新：{fin_latest_str}",
    )

    # 月營收
    rev_m = m.get("revenue", {})
    rev_str = (
        f"{rev_m.get('latest_year')}/{rev_m.get('latest_month'):02d}"
        if rev_m.get("latest_year")
        else "—"
    )
    _render_source_row(
        "月營收",
        "📉",
        None,
        f"{rev_m.get('stocks', 0):,} 檔有資料",
        f"最新：{rev_str}",
    )

    # 研究推薦
    _render_source_row(
        "研究推薦",
        "📋",
        rec_m.get("latest"),
        f"近 30 天 {rec_m.get('last_30d', 0)} 筆",
    )

    # 分析結果
    ar_m = m.get("analysis", {})
    _render_source_row(
        "分析結果",
        "🔬",
        ar_m.get("latest"),
        f"近 7 天 {ar_m.get('last_7d', 0)} 筆",
    )

    st.markdown("---")

    # ── 最近執行記錄 ─────────────────────────────────────────
    st.markdown("#### 最近執行記錄")
    exec_logs = m.get("exec_logs", [])
    if not exec_logs:
        st.caption("尚無執行記錄")
    else:
        for log in exec_logs:
            status = log.get("status", "unknown")
            s_color = (
                _GREEN
                if status == "success"
                else _YELLOW if status == "partial" else _RED
            )
            badge = _badge(status, s_color)
            total = log.get("total") or 0
            qual = log.get("qualified") or 0
            rec = log.get("recommended") or 0
            err = log.get("errors") or ""
            detail = f"分析 {total} → 合格 {qual} → 推薦 {rec}"
            st.markdown(
                f"`{log.get('date')}` &nbsp; {badge} &nbsp; "
                f"<small>{detail}</small>"
                + (
                    f"  <small style='color:{_RED}'>⚠ {err[:60]}</small>" if err else ""
                ),
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── 異常警示 ─────────────────────────────────────────────
    warnings = []
    price_latest = price_m.get("latest")
    if price_latest and (date.today() - price_latest).days > 3:
        warnings.append(f"⚠️  股價資料已 {(date.today() - price_latest).days} 天未更新")
    chip_latest = chip_m.get("latest")
    if chip_latest and (date.today() - chip_latest).days > 3:
        warnings.append(f"⚠️  法人資料已 {(date.today() - chip_latest).days} 天未更新")
    if fin_m.get("coverage_pct", 100) < 50:
        warnings.append(
            f"⚠️  財務資料覆蓋率僅 {fin_m.get('coverage_pct', 0):.0f}%，考慮執行 import_financials"
        )
    if rec_m.get("last_30d", 0) == 0:
        warnings.append("⚠️  近 30 天無任何推薦記錄，請確認分析流程是否正常運行")

    if warnings:
        st.markdown("#### ⚠️ 異常警示")
        for w in warnings:
            st.warning(w)
    else:
        st.success("✅ 所有資料來源狀態正常")
