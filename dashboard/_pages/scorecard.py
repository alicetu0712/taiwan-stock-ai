"""
pages/scorecard.py — 模型成績單（Recommendation Audit Trail）

顯示每一個有 decision_label 的 ForwardSignal 記錄，以及事後回填的績效結果。
這是模型的「永久記錄」：當時網站說了什麼，之後實際發生了什麼。
"""

import logging

import streamlit as st

from src.core.decision_codes import buy_codes, to_color, to_display

logger = logging.getLogger(__name__)


@st.cache_data(ttl=300)
def _load_scorecard_rows(limit: int = 300) -> list:
    """直接查 ForwardSignal，不透過 loaders，避免 Streamlit module-cache 問題。"""
    try:
        from src.database import ForwardSignal, get_session
        from sqlalchemy import desc

        s = get_session()
        rows = (
            s.query(ForwardSignal)
            .filter(ForwardSignal.decision_label.isnot(None))
            .filter(ForwardSignal.is_valid.isnot(False))  # exclude invalid records
            .order_by(desc(ForwardSignal.trade_date), ForwardSignal.candidate_rank)
            .limit(limit)
            .all()
        )
        s.close()
        return [
            {
                "trade_date":         str(r.trade_date),
                "stock_id":           r.stock_id,
                "stock_name":         r.stock_name or r.stock_id,
                "setup_type":         r.setup_type,
                "trade_signal":       r.trade_signal,
                "decision_label":     r.decision_label,
                "industry":           r.industry,
                "market_regime":      r.market_regime_at_signal,
                "close_at_signal":    r.close_at_signal,
                "entry_low":          r.entry_low,
                "entry_high":         r.entry_high,
                "stop_price":         r.stop_price,
                "target1":            r.target1,
                "target2":            r.target2,
                "fwd_return_20d":     r.fwd_return_20d,
                "alpha_20d":          r.alpha_20d,
                "fwd_return_60d":     r.fwd_return_60d,
                "alpha_60d":          r.alpha_60d,
                "stop_triggered_day":  r.stop_triggered_day,
                "t1_hit_day":          r.t1_hit_day,
                "outcome_note":        r.outcome_note,
                "outcome_price_quality": getattr(r, "outcome_price_quality", None),
                "pt_score":           r.pt_score,
                "total_score":        r.total_score,
                "confidence":         r.confidence,
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"_load_scorecard_rows: {e}")
        return []

# DB stores stable codes; UI translates via to_display() / to_color()
# Preferred default codes for the decision_label multiselect
_PREFERRED_CODE_DEFAULTS = list(buy_codes())  # ["strong_buy", "buy"]

_OUTCOME_ICON = {
    "T1_HIT":             "🎯",
    "STOP_TRIGGERED":     "🛑",
    "SAME_DAY_AMBIGUOUS": "⚠️",
    "EXPIRED":            "⏱️",
}


def _outcome_color(outcome_note: str | None, alpha: float | None) -> str:
    if outcome_note == "T1_HIT":
        return "#1a7f4b"
    if outcome_note == "STOP_TRIGGERED":
        return "#e74c3c"
    if outcome_note == "SAME_DAY_AMBIGUOUS":
        return "#f39c12"
    if alpha is not None:
        return "#1a7f4b" if alpha > 0 else "#e74c3c"
    return "#666"


def _fmt(v, suffix="", places=1, plus=False):
    if v is None:
        return "—"
    fmt = f"{'+'if plus else ''}{v:.{places}f}{suffix}"
    return fmt


def _dedup_cohort(rows: list, cooldown_calendar_days: int) -> list:
    """Per-stock cooldown dedup: keep first signal per stock in each cooldown window.

    Rows are assumed to contain 'stock_id' and 'trade_date' (ISO string or date).
    Sorted ascending by trade_date; earliest signal in each window is retained.
    """
    from datetime import date as _date
    last_kept: dict = {}
    result = []
    for r in sorted(rows, key=lambda x: x["trade_date"]):
        td = r["trade_date"]
        if isinstance(td, str):
            td = _date.fromisoformat(td)
        last = last_kept.get(r["stock_id"])
        if last is None or (td - last).days >= cooldown_calendar_days:
            result.append(r)
            last_kept[r["stock_id"]] = td
    return result


def _ci95_mean(values: list) -> float | None:
    """95% CI half-width for the mean: 1.96 × std / sqrt(n). Returns None if n < 2."""
    import statistics
    n = len(values)
    if n < 2:
        return None
    return round(1.96 * statistics.stdev(values) / (n ** 0.5), 2)


def _stats_block(matured: list, alpha_key: str) -> dict:
    """Compute a standard stats dict from a list of matured rows."""
    alphas = [r[alpha_key] for r in matured if r[alpha_key] is not None]
    if not alphas:
        return {"n": 0, "winrate": None, "avg_alpha": None, "ci95": None,
                "t1_rate": None, "stop_rate": None, "ambiguous_rate": None}
    n = len(alphas)
    return {
        "n":             n,
        "winrate":       round(sum(1 for a in alphas if a > 0) / n * 100, 1),
        "avg_alpha":     round(sum(alphas) / n, 2),
        "ci95":          _ci95_mean(alphas),
        # outcome rates are only meaningful on 20D outcomes
        "t1_rate":       round(sum(1 for r in matured if r["outcome_note"] == "T1_HIT")              / n * 100, 1),
        "stop_rate":     round(sum(1 for r in matured if r["outcome_note"] == "STOP_TRIGGERED")       / n * 100, 1),
        "ambiguous_rate":round(sum(1 for r in matured if r["outcome_note"] == "SAME_DAY_AMBIGUOUS")   / n * 100, 1),
    }


# 20 trading days ≈ 28 calendar days; 60 trading days ≈ 84 calendar days
_DEDUP_20_DAYS = 28
_DEDUP_60_DAYS = 84


def _summary_stats(rows: list) -> dict:
    """
    Compute dedup-aware stats.

    20D statistics are computed from the 20D-dedup cohort only.
    60D statistics are computed from the 60D-dedup cohort only.
    Raw N is reported for reference but NOT used in any statistic.
    """
    buy_rows = [r for r in rows if r["decision_label"] in buy_codes()]

    dedup_20 = _dedup_cohort(buy_rows, _DEDUP_20_DAYS)
    dedup_60 = _dedup_cohort(buy_rows, _DEDUP_60_DAYS)

    matured_20 = [r for r in dedup_20 if r["alpha_20d"] is not None]
    matured_60 = [r for r in dedup_60 if r["alpha_60d"] is not None]

    return {
        "n_raw":       len(buy_rows),
        "n_dedup_20":  len(dedup_20),
        "n_dedup_60":  len(dedup_60),
        "s20":         _stats_block(matured_20, "alpha_20d"),
        "s60":         _stats_block(matured_60, "alpha_60d"),
    }


def page_scorecard() -> None:
    st.markdown(
        '<div class="section-title">📋 模型成績單</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "永久記錄每個信號當時的決策快照（entry / stop / target / 決策標籤）"
        "以及事後回填的 20 交易日績效結果。僅顯示有進入 Decision Center 的信號。"
    )

    with st.spinner("讀取成績單資料..."):
        rows = _load_scorecard_rows(limit=300)

    if not rows:
        st.info("尚無成績單資料。每日執行後系統會自動凍結 Decision Center 信號。")
        return

    # ── 篩選控制 ──────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns(3)
    all_codes_in_data = sorted({r["decision_label"] for r in rows if r["decision_label"]})
    all_setups = sorted({r["setup_type"] for r in rows if r["setup_type"]})

    # Sanitize stale session_state (handles old display-string values from pre-migration)
    if "sc_labels" in st.session_state:
        st.session_state["sc_labels"] = [
            v for v in st.session_state["sc_labels"] if v in all_codes_in_data
        ]
    if "sc_setups" in st.session_state:
        st.session_state["sc_setups"] = [
            v for v in st.session_state["sc_setups"] if v in all_setups
        ]

    # Default: prefer strong_buy / buy, only if they exist in current data
    default_codes = [x for x in _PREFERRED_CODE_DEFAULTS if x in all_codes_in_data]

    sel_labels = col_f1.multiselect(
        "決策標籤",
        all_codes_in_data,
        default=default_codes,
        format_func=to_display,   # show "BUY ★" but value is "strong_buy"
        key="sc_labels",
    )
    sel_setups = col_f2.multiselect("型態", all_setups, default=all_setups, key="sc_setups")
    outcome_opts = ["全部", "已有結果", "待成熟"]
    sel_outcome = col_f3.selectbox("結果", outcome_opts, key="sc_outcome")

    filtered = rows
    if sel_labels:
        filtered = [r for r in filtered if r["decision_label"] in sel_labels]
    if sel_setups:
        filtered = [r for r in filtered if r["setup_type"] in sel_setups]
    if sel_outcome == "已有結果":
        filtered = [r for r in filtered if r["outcome_note"] is not None]
    elif sel_outcome == "待成熟":
        filtered = [r for r in filtered if r["outcome_note"] is None]

    # ── 摘要統計 ──────────────────────────────────────────────
    stats = _summary_stats(filtered)
    s20, s60 = stats["s20"], stats["s60"]
    st.markdown("---")

    # 樣本計數
    cnt1, cnt2, cnt3, cnt4, cnt5, cnt6 = st.columns(6)
    cnt1.metric(
        "Raw N（BUY+）", stats["n_raw"],
        help="全部 BUY / BUY★ 信號數量（含重疊）。不直接用於統計。",
    )
    cnt2.metric(
        "20D Dedup N", stats["n_dedup_20"],
        help=f"同一股票 {_DEDUP_20_DAYS} 日冷卻去重後的樣本數。20D 統計基於此集合。",
    )
    cnt3.metric(
        "60D Dedup N", stats["n_dedup_60"],
        help=f"同一股票 {_DEDUP_60_DAYS} 日冷卻去重後的樣本數。60D 統計基於此集合。",
    )

    # ── 20D 統計（基於 20D Dedup 樣本）──────────────────────────
    st.markdown("**20D 統計**（基於 20D Dedup 樣本）")
    d1, d2, d3, d4, d5, d6 = st.columns(6)
    d1.metric("20D 已成熟", s20["n"] if s20["n"] else "—")
    if s20["avg_alpha"] is not None:
        ci_str = f"±{s20['ci95']:.2f}%" if s20["ci95"] is not None else ""
        d2.metric("20D Alpha", f"{s20['avg_alpha']:+.2f}%",
                  delta=ci_str or None, delta_color="off",
                  help="20D Dedup 樣本的平均 Alpha；delta 為 95% CI 半寬")
        d3.metric("20D 勝率", f"{s20['winrate']}%",
                  help="Alpha > 0 的比例（20D Dedup 樣本）")
        d4.metric("T1 率", f"{s20['t1_rate']}%")
        d5.metric("停損率", f"{s20['stop_rate']}%")
        d6.metric("⚠️ 同日模糊", f"{s20['ambiguous_rate']}%",
                  help="同一交易日 High≥T1 且 Low≤Stop，日線資料無法判斷先後順序")
    else:
        for col in (d2, d3, d4, d5, d6):
            col.metric("—", "—")

    # ── 60D 統計（基於 60D Dedup 樣本）──────────────────────────
    if s60["n"] > 0:
        st.markdown("**60D 統計**（基於 60D Dedup 樣本）")
        e1, e2, e3, e4, *_ = st.columns(6)
        e1.metric("60D 已成熟", s60["n"])
        ci_str60 = f"±{s60['ci95']:.2f}%" if s60["ci95"] is not None else ""
        e2.metric("60D Alpha", f"{s60['avg_alpha']:+.2f}%",
                  delta=ci_str60 or None, delta_color="off",
                  help="60D Dedup 樣本的平均 Alpha；delta 為 95% CI 半寬")
        e3.metric("60D 勝率", f"{s60['winrate']}%",
                  help="Alpha > 0 的比例（60D Dedup 樣本）")

    st.caption(
        "報酬均為淨報酬，已扣保守假設交易成本 0.585%。Alpha = 股票淨報酬 − 0050 淨報酬。"
        f"Dedup：同一股票 20D/60D 冷卻（約 {_DEDUP_20_DAYS}/{_DEDUP_60_DAYS} 日曆日）去除重疊樣本；"
        "統計直接在 Dedup 樣本上計算，Raw N 僅顯示用。"
    )
    st.caption(
        "⚠️ **研究母體限制** — "
        "統計來自「歷史 Analysis Candidate Pool」（每日通過前置篩選的個股），非台股全市場。 "
        "**Historical Research may contain survivorship bias.** "
        "歷史股票池未完整納入已下市證券，因此結果可能高估實際策略績效。"
    )
    st.markdown("---")

    if not filtered:
        st.info("目前篩選條件下無資料。")
        return

    # ── 逐筆展示 ──────────────────────────────────────────────
    for r in filtered:
        code  = r["decision_label"] or "wait"
        label = to_display(code)
        lc    = to_color(code)
        outcome_icon = _OUTCOME_ICON.get(r["outcome_note"], "⏳" if r["outcome_note"] is None else "")
        alpha_20 = r["alpha_20d"]
        ret_20   = r["fwd_return_20d"]

        header = (
            f"{outcome_icon} **{r['stock_name']}**（{r['stock_id']}）"
            f"  {r['trade_date']}"
            f"  ｜ <span style='background:{lc};color:white;padding:1px 6px;border-radius:4px;font-size:0.8rem'>{label}</span>"
            f"  ｜ {r['setup_type'] or '—'}"
        )
        if alpha_20 is not None:
            ac = "#1a7f4b" if alpha_20 > 0 else "#e74c3c"
            header += f"  ｜ α <span style='color:{ac};font-weight:700'>{alpha_20:+.2f}%</span>"

        with st.expander(header, expanded=False):
            col_a, col_b, col_c = st.columns(3)

            with col_a:
                st.markdown("**進場快照**")
                st.markdown(
                    f"進場收盤：**{_fmt(r['close_at_signal'], ' 元')}**  \n"
                    f"建議進場：{_fmt(r['entry_low'])} ~ {_fmt(r['entry_high'])}  \n"
                    f"停損：**{_fmt(r['stop_price'], ' 元')}**  \n"
                    f"目標 T1：**{_fmt(r['target1'], ' 元')}**  \n"
                    f"目標 T2：{_fmt(r['target2'], ' 元')}"
                )

            with col_b:
                st.markdown("**市場背景**")
                regime = r.get("market_regime") or "—"
                regime_badge = {"bull": "🟢 多頭", "bear": "🔴 空頭", "neutral": "🟡 中性"}.get(regime, regime)
                st.markdown(
                    f"Regime：{regime_badge}  \n"
                    f"產業：{r.get('industry') or '—'}  \n"
                    f"PT Score：{_fmt(r['pt_score'])}  \n"
                    f"信心：{_fmt(r['confidence'], '%')}"
                )

            with col_c:
                st.markdown("**績效結果**")
                if r["outcome_note"] is None:
                    st.markdown("⏳ 尚未成熟（等待 20 交易日後回填）")
                else:
                    outcome_display = {
                        "T1_HIT":             "🎯 盤中觸及目標 T1（High ≥ T1）",
                        "STOP_TRIGGERED":     "🛑 盤中觸及停損（Low ≤ Stop）",
                        "SAME_DAY_AMBIGUOUS": "⚠️ 同日觸及停損與目標（無法判斷順序）",
                        "EXPIRED":            "⏱️ 時間到期（20 交易日內未觸發）",
                    }.get(r["outcome_note"], r["outcome_note"])
                    st.markdown(f"結果：**{outcome_display}**")
                    if r["stop_triggered_day"]:
                        st.caption(f"停損觸發日：第 {r['stop_triggered_day']} 交易日（盤中 Low ≤ Stop Price）")
                    if r["t1_hit_day"]:
                        st.caption(f"T1 達成日：第 {r['t1_hit_day']} 交易日（盤中 High ≥ T1）")
                    _pq = r.get("outcome_price_quality")
                    if _pq == "CLOSE_ONLY":
                        st.caption("⚠️ 價格品質：CLOSE_ONLY — 掃描期間部分交易日缺少盤中 H/L，以收盤價代替判斷停損/目標，結果可信度較低")
                    elif _pq == "OHLC":
                        st.caption("✅ 價格品質：OHLC — 停損/目標判斷全程使用盤中 High/Low")
                    st.markdown(
                        f"20D 淨報酬：{_fmt(ret_20, '%', plus=True)}  \n"
                        f"20D Alpha：{_fmt(alpha_20, '%', plus=True)}  \n"
                        f"60D 淨報酬：{_fmt(r['fwd_return_60d'], '%', plus=True)}  \n"
                        f"60D Alpha：{_fmt(r['alpha_60d'], '%', plus=True)}"
                    )
                    st.caption("淨報酬已扣保守假設交易成本 0.585%（保守固定假設值；實際成本依券商折扣、標的類型而異，不含滑價）。同日 Stop 與 T1 同時觸及時標記為「同日模糊」，不計入 T1 率或停損率。")
