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
    Stock,
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
        # Use analysis universe (Stock, is_excluded=False) as denominator.
        # price_distinct spans ALL stocks ever in DailyPrice (TWSE+TPEx+ETFs),
        # which would make fin_coverage falsely low.
        _analysis_universe_size = (
            s.query(func.count(Stock.stock_id))
            .filter(Stock.is_excluded.isnot(True))
            .scalar()
        ) or 0
        fin_coverage = (
            round(fin_stocks / _analysis_universe_size * 100, 1)
            if _analysis_universe_size > 0
            else 0.0
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

        # ── Forward Signal 完整性 ─────────────────────────────
        from src.database import ForwardSignal, RESEARCH_CUTOFF_DATE
        fs_latest = s.query(func.max(ForwardSignal.trade_date)).scalar()
        fs_total  = s.query(func.count(ForwardSignal.id)).scalar() or 0

        # AR 在 cutoff 後有資料的每日筆數（最近 60 天）
        ar_cutoff_rows = (
            s.query(AnalysisResult.date, func.count(AnalysisResult.id).label("ar_cnt"))
            .filter(AnalysisResult.date >= RESEARCH_CUTOFF_DATE)
            .group_by(AnalysisResult.date)
            .order_by(AnalysisResult.date.desc())
            .limit(60)
            .all()
        )
        # cutoff 後已有 forward_signals 的日期集合
        fs_dates_set = {
            d for (d,) in
            s.query(func.distinct(ForwardSignal.trade_date))
            .filter(ForwardSignal.trade_date >= RESEARCH_CUTOFF_DATE)
            .all()
        }
        # 找出 AR 有資料但 FS 缺失的日期
        missing_fs_dates = [
            {"date": d, "ar_cnt": int(cnt)}
            for d, cnt in ar_cutoff_rows
            if d not in fs_dates_set
        ]
        metrics["forward_signal"] = {
            "latest":       fs_latest,
            "total":        fs_total,
            "cutoff":       RESEARCH_CUTOFF_DATE,
            "missing_dates": missing_fs_dates,
        }

        # ── Pipeline 健康度 ─────────────────────────────────
        from src.database import ForwardOutcomeEvaluation
        from datetime import timedelta as _td

        # 有 execution_date 在昨天或更早但 execution_price 仍 NULL → pipeline 曾跳過該天
        yesterday = date.today() - timedelta(days=1)
        fs_unfilled_past = (
            s.query(func.count(ForwardSignal.id))
            .filter(
                ForwardSignal.execution_price_type == "NEXT_OPEN",
                ForwardSignal.execution_price.is_(None),
                ForwardSignal.execution_date <= yesterday,
            )
            .scalar()
        ) or 0

        # compute_signal_outcomes 待處理：trade_date ≤ 30 天前且 outcomes_computed_at IS NULL
        outcomes_pending_cutoff = date.today() - _td(days=30)
        fs_outcomes_pending = (
            s.query(func.count(ForwardSignal.id))
            .filter(
                ForwardSignal.trade_date <= outcomes_pending_cutoff,
                ForwardSignal.outcomes_computed_at.is_(None),
                ForwardSignal.decision_label.isnot(None),
                ForwardSignal.is_valid.isnot(False),
            )
            .scalar()
        ) or 0

        foe_total = s.query(func.count(ForwardOutcomeEvaluation.id)).scalar() or 0
        foe_latest_matured = (
            s.query(func.max(ForwardOutcomeEvaluation.horizon_20d_matured_at)).scalar()
        )
        metrics["pipeline_health"] = {
            "fs_unfilled_past":    fs_unfilled_past,
            "fs_outcomes_pending": fs_outcomes_pending,
            "foe_total":           foe_total,
            "foe_latest_matured":  foe_latest_matured,
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


@st.cache_data(ttl=300)
def _load_coverage_history(n_days: int = 20) -> dict:
    """
    近 n_days 個交易日的市場資料完整度。

    分子：指定日 DailyPrice 中屬於分析宇宙（Stock, is_excluded=False）
          的 DISTINCT stock_id 數量。
    分母：Stock 資料表中 is_excluded != True 的標的總數（固定宇宙）。

    原始資料筆數（raw_count）也一併回傳，供異常診斷：
    若 raw_count >> expected，表示 DailyPrice 包含分析宇宙外的全市場股票。
    覆蓋率計算永遠使用修正後的分子，不得用 min(100%, ratio) 掩蓋問題。
    """
    try:
        from sqlalchemy import func
        s = get_session()
        expected = (
            s.query(func.count(Stock.stock_id))
            .filter(Stock.is_excluded.isnot(True))
            .scalar()
        ) or 0

        # 找近 n_days 個有 DailyPrice 的日期
        recent_dates = (
            s.query(DailyPrice.date)
            .filter(DailyPrice.close.isnot(None))
            .group_by(DailyPrice.date)
            .order_by(DailyPrice.date.desc())
            .limit(n_days)
            .all()
        )
        dates = sorted([r[0] for r in recent_dates])

        rows = []
        for d in dates:
            # Scoped count: only analysis-universe stocks
            cnt = (
                s.query(func.count(func.distinct(DailyPrice.stock_id)))
                .join(Stock, Stock.stock_id == DailyPrice.stock_id)
                .filter(
                    DailyPrice.date == d,
                    DailyPrice.close.isnot(None),
                    Stock.is_excluded.isnot(True),
                )
                .scalar()
            ) or 0
            # Raw total: all rows in DailyPrice for this date (anomaly detection)
            raw_count = (
                s.query(func.count(DailyPrice.stock_id))
                .filter(DailyPrice.date == d, DailyPrice.close.isnot(None))
                .scalar()
            ) or 0
            ratio = cnt / expected if expected > 0 else None
            # Flag if raw count suggests non-universe data (>5% above expected)
            anomaly = raw_count > int(expected * 1.05) if expected > 0 else False
            rows.append({
                "date": d,
                "count": cnt,           # analysis-universe scoped
                "raw_count": raw_count, # all DailyPrice rows
                "expected": expected,
                "ratio": ratio,
                "anomaly": anomaly,
            })
        s.close()
        return {"expected": expected, "rows": rows}
    except Exception as e:
        logger.warning(f"_load_coverage_history: {e}")
        return {"expected": 0, "rows": []}


@st.cache_data(ttl=300)
def _load_coverage_detail(check_date) -> dict:
    """
    指定交易日的缺漏股票分析：分析宇宙中哪些股票缺少收盤價，原因為何。
    """
    try:
        from sqlalchemy import func
        s = get_session()

        universe_stocks = (
            s.query(Stock)
            .filter(Stock.is_excluded.isnot(True))
            .all()
        )
        universe_ids = {st.stock_id for st in universe_stocks}

        priced_ids = {
            r[0]
            for r in s.query(DailyPrice.stock_id)
            .filter(DailyPrice.date == check_date, DailyPrice.close.isnot(None))
            .all()
        }
        priced_universe = universe_ids & priced_ids
        missing_ids = universe_ids - priced_ids

        missing_stocks_map = {st.stock_id: st for st in universe_stocks if st.stock_id in missing_ids}

        delisted, suspended, not_listed, other_missing = [], [], [], []
        for sid, st in missing_stocks_map.items():
            if (st.delisted_date and st.delisted_date <= check_date) or st.security_status == "delisted":
                delisted.append(sid)
            elif st.security_status == "suspended":
                suspended.append(sid)
            elif st.listing_date and st.listing_date > check_date:
                not_listed.append(sid)
            else:
                other_missing.append(sid)

        s.close()
        return {
            "expected": len(universe_ids),
            "actual": len(priced_universe),
            "missing": len(missing_ids),
            "delisted": len(delisted),
            "suspended": len(suspended),
            "not_listed": len(not_listed),
            "other_missing": len(other_missing),
            "other_missing_ids": sorted(other_missing)[:30],
        }
    except Exception as e:
        logger.warning(f"_load_coverage_detail: {e}")
        return {}


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

    # Forward Signals
    fs_m = m.get("forward_signal", {})
    fs_missing = fs_m.get("missing_dates", [])
    fs_detail = f"總計 {fs_m.get('total', 0):,} 筆"
    fs_extra = (
        f"🔴 {len(fs_missing)} 個缺失日期" if fs_missing
        else ("✅ 無缺失" if fs_m.get("total", 0) > 0 else "尚未開始累積")
    )
    _render_source_row(
        "Forward Signals",
        "🔒",
        fs_m.get("latest"),
        fs_detail,
        fs_extra,
    )

    st.markdown("---")

    # ── Pipeline 健康度 ─────────────────────────────────────
    st.markdown("#### 🔧 Pipeline 健康度")
    ph = m.get("pipeline_health", {})
    ph_cols = st.columns(4)
    with ph_cols[0]:
        unfilled = ph.get("fs_unfilled_past", 0)
        c = _RED if unfilled > 0 else _GREEN
        st.markdown(
            f'<div style="text-align:center;padding:10px;border-radius:8px;'
            f'border:2px solid {c}20;background:{c}10">'
            f'<div style="font-size:1.4rem;font-weight:800;color:{c}">{unfilled}</div>'
            f'<div style="font-size:0.72rem;color:#666">未填入執行價<br>'
            f'<small>(過去 NEXT_OPEN 訊號缺 execution_price)</small></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with ph_cols[1]:
        outcomes_pend = ph.get("fs_outcomes_pending", 0)
        c = _YELLOW if outcomes_pend > 0 else _GREEN
        st.markdown(
            f'<div style="text-align:center;padding:10px;border-radius:8px;'
            f'border:2px solid {c}20;background:{c}10">'
            f'<div style="font-size:1.4rem;font-weight:800;color:{c}">{outcomes_pend}</div>'
            f'<div style="font-size:0.72rem;color:#666">績效待計算<br>'
            f'<small>(trade_date ≤ 30d 前但 outcomes_computed_at IS NULL)</small></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with ph_cols[2]:
        foe_total = ph.get("foe_total", 0)
        c = _GREEN if foe_total > 0 else _GRAY
        st.markdown(
            f'<div style="text-align:center;padding:10px;border-radius:8px;'
            f'border:2px solid {c}20;background:{c}10">'
            f'<div style="font-size:1.4rem;font-weight:800;color:{c}">{foe_total:,}</div>'
            f'<div style="font-size:0.72rem;color:#666">foe_v1 已計算結果<br>'
            f'<small>(Forward Outcome Evaluation 總筆數)</small></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with ph_cols[3]:
        last_mat = ph.get("foe_latest_matured")
        if last_mat is None:
            mat_label = "尚無成熟訊號"
            c = _GRAY
        else:
            mat_date = last_mat.date() if hasattr(last_mat, "date") else last_mat
            mat_label = str(mat_date)
            c = _GREEN
        st.markdown(
            f'<div style="text-align:center;padding:10px;border-radius:8px;'
            f'border:2px solid {c}20;background:{c}10">'
            f'<div style="font-size:1.1rem;font-weight:800;color:{c}">{mat_label}</div>'
            f'<div style="font-size:0.72rem;color:#666">最新 foe_v1 成熟日<br>'
            f'<small>(horizon_20d_matured_at)</small></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    if ph.get("fs_unfilled_past", 0) > 0:
        st.warning(
            f"⚠️  {ph['fs_unfilled_past']} 筆 NEXT_OPEN 訊號的 execution_date ≤ 昨日但 execution_price 仍為 NULL。"
            "表示至少有一個交易日的 pipeline 未成功執行 `fill_execution_prices()`。"
            "請手動補跑對應日期：`python scripts/run_daily.py --date YYYY-MM-DD`"
        )
    if ph.get("fs_outcomes_pending", 0) > 0:
        st.info(
            f"ℹ️  {ph['fs_outcomes_pending']} 筆訊號符合成熟條件（trade_date ≤ 30 天前）"
            "但 outcomes_computed_at 仍為 NULL。"
            "這通常表示 compute_signal_outcomes() 在執行時尚未有 DailyPrice 資料。"
            "下次 pipeline 成功執行後應自動回填。"
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

    # Forward Signal 缺失日期（最嚴重，獨立顯示在最前面）
    fs_m = m.get("forward_signal", {})
    fs_missing = fs_m.get("missing_dates", [])
    if fs_missing:
        st.markdown("#### 🔴 Forward Signal 缺失警告")
        st.error(
            f"**偵測到 {len(fs_missing)} 個缺失日期** — "
            "這些天有 `analysis_results` 但 `forward_signals` 未寫入。\n\n"
            "該日的預測記錄**永遠無法補回**（補寫即不再是真正的 append-only OOS）。\n\n"
            "請確認 `main.py` 的 `write_forward_signals()` 是否因例外而靜默失敗。"
        )
        missing_rows = [
            {"日期": str(row["date"]), "analysis_results 筆數": row["ar_cnt"], "forward_signals": "❌ 缺失"}
            for row in fs_missing
        ]
        import pandas as _pd
        st.dataframe(_pd.DataFrame(missing_rows).set_index("日期"), use_container_width=True)
        st.markdown("---")

    if warnings:
        st.markdown("#### ⚠️ 異常警示")
        for w in warnings:
            st.warning(w)
    elif not fs_missing:
        st.success("✅ 所有資料來源狀態正常")

    st.markdown("---")

    # ── 每日市場資料完整度 ────────────────────────────────────────
    st.markdown("#### 📊 每日市場資料完整度（近 20 交易日）")
    st.caption(
        "追蹤各交易日分析股票池（826 檔）中有多少比例具備有效收盤價，"
        "供判斷今日選股結果的可信度。"
    )

    import pandas as _pd

    cov = _load_coverage_history(n_days=20)
    cov_rows = cov.get("rows", [])
    expected_uni = cov.get("expected", 0)

    if not cov_rows:
        st.info("尚無市場資料完整度記錄")
    else:
        # ── 最新交易日摘要 ────────────────────────────────────────
        latest_row = cov_rows[-1]
        latest_date = latest_row["date"]
        detail = _load_coverage_detail(latest_date)

        actual    = detail.get("actual",   latest_row["count"])
        missing   = detail.get("missing",  max(0, expected_uni - actual))
        ratio_now = latest_row.get("ratio") or 0.0

        if ratio_now >= 0.93:
            impact_text, impact_c = "正常，選股可信度高", _GREEN
        elif ratio_now >= 0.85:
            impact_text, impact_c = "輕微缺漏，選股可信度尚可", _YELLOW
        else:
            impact_text, impact_c = "缺漏較多，請確認資料來源", _RED

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("今日應追蹤", f"{expected_uni:,} 檔")
        col2.metric("實際取得", f"{actual:,} 檔")
        col3.metric("缺少資料", f"{missing:,} 檔")
        with col4:
            st.markdown(
                f'<div style="text-align:center;padding:10px;border-radius:8px;'
                f'border:2px solid {impact_c}20;background:{impact_c}10">'
                f'<div style="font-size:0.85rem;font-weight:700;color:{impact_c}">'
                f"{impact_text}</div>"
                f'<div style="font-size:0.7rem;color:#666">對今日選股可信度</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── 缺漏原因分解 ─────────────────────────────────────────
        if missing > 0 and detail:
            n_delisted    = detail.get("delisted", 0)
            n_suspended   = detail.get("suspended", 0)
            n_not_listed  = detail.get("not_listed", 0)
            n_other       = detail.get("other_missing", 0)
            parts = []
            if n_delisted:   parts.append(f"已下市 {n_delisted} 檔")
            if n_suspended:  parts.append(f"停牌 {n_suspended} 檔")
            if n_not_listed: parts.append(f"尚未上市 {n_not_listed} 檔")
            if n_other:      parts.append(f"資料缺漏 {n_other} 檔")
            st.caption(f"**缺少 {missing} 檔原因：** " + "、".join(parts))

            other_ids = detail.get("other_missing_ids", [])
            if other_ids:
                st.warning(
                    f"⚠️ 以下 {len(other_ids)} 檔狀態正常但無今日收盤價（可能 API 未更新）：\n"
                    + "、".join(other_ids)
                )

        # ── 異常警示（DailyPrice 含分析宇宙外資料）──────────────
        anomaly_days = [r for r in cov_rows if r.get("anomaly")]
        if anomaly_days:
            st.error(
                f"⚠️ **資料異常：{len(anomaly_days)} 個交易日的 DailyPrice 原始筆數遠超分析股票池大小。**\n\n"
                "表示 DailyPrice 包含非分析宇宙股票（如全市場股票、ETF、衍生品等）。"
                "以下覆蓋率已修正為股票池內的實際覆蓋，原始資料筆數供診斷用。"
            )

        # ── 近 20 日明細表 ────────────────────────────────────────
        ratios = [r["ratio"] for r in cov_rows if r["ratio"] is not None]
        df_cov = _pd.DataFrame([
            {
                "日期": str(r["date"]),
                "股票池有價格": r["count"],
                "應有檔數": r["expected"],
                "覆蓋率": f"{r['ratio']*100:.1f}%" if r["ratio"] is not None else "—",
                "原始筆數": r.get("raw_count", r["count"]),
                "異常": "⚠️ 含宇宙外資料" if r.get("anomaly") else "",
            }
            for r in reversed(cov_rows)
        ])
        st.dataframe(df_cov.set_index("日期"), use_container_width=True)

        # ── 進階資訊（Gate 設定 + 門檻模擬）────────────────────
        with st.expander("🔧 進階資訊：Forward Gate 設定與門檻模擬"):
            from config import FORWARD_MARKET_COVERAGE
            _min_ratio = FORWARD_MARKET_COVERAGE.get("min_ratio")
            _min_count = FORWARD_MARKET_COVERAGE.get("min_count", 200)

            st.markdown("**目前 Gate 設定**")
            st.caption(
                f"L2a 絕對下限：{_min_count} 檔（分析宇宙中有 ≥ {_min_count} 檔具備收盤價才允許寫入）\n\n"
                f"L2b 比例下限：{'**停用（None）**' if _min_ratio is None else f'**{_min_ratio:.0%}**'}"
            )
            if _min_ratio is None:
                st.info(
                    "**min_ratio=None 實際行為**：只要分析宇宙中有 ≥ 200 檔具備收盤價，"
                    "L2 Gate 就通過，不設比例下限。"
                )

            if ratios:
                st.markdown("**門檻模擬（近 20 交易日）**")
                st.caption("若啟用各門檻，以下天數的 ForwardSignal 寫入會被阻擋（唯讀模擬）：")
                sim_rows = []
                for thr in [0.70, 0.75, 0.80, 0.85, 0.90]:
                    blocked = sum(1 for r in ratios if r < thr)
                    sim_rows.append({
                        "門檻": f"{thr:.0%}",
                        "阻擋天數": blocked,
                        "通過天數": len(ratios) - blocked,
                        "阻擋率": f"{blocked / len(ratios) * 100:.0f}%",
                        "建議": "可考慮" if blocked <= 2 else "謹慎評估" if blocked <= 5 else "過於嚴格",
                    })
                st.dataframe(_pd.DataFrame(sim_rows).set_index("門檻"), use_container_width=True)

            st.markdown("**覆蓋率定義說明**")
            st.caption(
                "分子：指定交易日、分析股票池（Stock.is_excluded=False）內，"
                "具備有效收盤價的 DISTINCT stock_id 數量。\n\n"
                "分母：Stock 資料表中 is_excluded != True 的標的總數（固定宇宙）。\n\n"
                "若「原始筆數」大於「應有檔數」，表示 DailyPrice 包含分析宇宙外的股票，"
                "已修正分子避免覆蓋率超過 100%。"
            )
