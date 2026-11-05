"""
pages/entry_timing_research.py — V2 Entry Timing Research UI (Shadow Mode)

RESEARCH ONLY — NOT A LIVE TRADING SYSTEM.
This page does NOT feed into v8.0 BUY/STRONG_BUY decisions or ACTUAL/PAPER trades.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import streamlit as st

logger = logging.getLogger(__name__)

_LABEL_COLORS = {
    "ENTRY_READY": "#16a34a",
    "WAIT_FOR_PULLBACK": "#ca8a04",
    "WAIT_FOR_BREAKOUT": "#2563eb",
    "TOO_EXTENDED": "#dc2626",
    "RISK_REWARD_UNFAVORABLE": "#9333ea",
    "NO_VALID_SETUP": "#6b7280",
    "INSUFFICIENT_DATA": "#9ca3af",
}

_RESEARCH_VERSIONS = ["v2_research_v2", "v2_research_v1"]

_KNOWN_LIMITATIONS = [
    "比較 B/C 的 V1 baseline 採 OHLC 模擬（同 stop/target），與 V2 使用相同條件。比較 A 仍用 fwd_return_20d 供參考（訊號選擇角度）。",
    "SA: open prices are approximated by daily close (DailyPrice 無獨立 open 欄位)。",
    "SA-7: V2 no-fill signals are assigned 0% return in Comparison C (Full Opportunity Set)；這會壓低 V2 FOS mean。",
    "SA-3: 同日 stop+target 兩者均觸發時，採 stop-first 保守假設。",
    "SA-4: 跳空缺口以開盤出場（gap slippage 未額外建模）。",
    "台灣交易費 0.585% round-trip（已含入 net_return_pct）。",
    "Bootstrap CI 僅在 n ≥ 10 樣本時計算，seed=42，1000 iterations。",
    "此頁結果僅供研究比較，不代表未來真實績效。",
]


def _label_badge(label: str) -> str:
    color = _LABEL_COLORS.get(label, "#6b7280")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.75rem;font-weight:600">{label}</span>'
    )


def _research_badge(version: str, is_legacy: bool) -> str:
    if is_legacy or version == "v2_research_v1":
        return (
            '<span style="background:#fef3c7;color:#92400e;padding:2px 6px;'
            'border-radius:4px;font-size:0.7rem;font-weight:600">legacy v1</span>'
        )
    return (
        '<span style="background:#dcfce7;color:#14532d;padding:2px 6px;'
        'border-radius:4px;font-size:0.7rem;font-weight:600">v2</span>'
    )


@st.cache_data(ttl=300)
def _load_v2_signals(research_version: str, limit: int = 300) -> list:
    try:
        from sqlalchemy import desc

        from src.database import get_session
        from src.research.models import V2ShadowSignal

        s = get_session()
        query = s.query(V2ShadowSignal).filter(
            V2ShadowSignal.research_version == research_version
        )
        rows = (
            query.order_by(
                desc(V2ShadowSignal.trade_date),
                V2ShadowSignal.stock_id,
            )
            .limit(limit)
            .all()
        )
        s.close()
        return [
            {
                "trade_date": str(r.trade_date),
                "stock_id": r.stock_id,
                "research_version": r.research_version,
                "is_legacy": bool(r.is_legacy),
                "v1_label": r.v1_decision_label or "—",
                "entry_label": r.entry_label or "—",
                "entry_price": r.entry_price,
                "stop_price": r.stop_price,
                "target_price": r.target_price,
                "rr_ratio": r.rr_ratio,
                "vol_ratio": r.vol_ratio,
                "dist_pct": r.dist_to_resistance_pct,
                "ma20_gap": r.ma20_gap_pct,
                "reasons": r.reasons_json or "",
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"V2 shadow signals load failed: {e}")
        return []


@st.cache_data(ttl=600)
def _load_full_backtest(
    from_date_str: str,
    to_date_str: str,
    research_version: str,
    expiry_days: int,
) -> dict:
    try:
        from src.database import get_session
        from src.research.backtest_full import run_full_backtest

        from_date = date.fromisoformat(from_date_str)
        to_date = date.fromisoformat(to_date_str)

        sess = get_session()
        result = run_full_backtest(
            research_session=sess,
            prod_session=sess,
            from_date=from_date,
            to_date=to_date,
            research_version=research_version,
            expiry_days=expiry_days,
        )
        sess.close()
        return result
    except Exception as e:
        logger.warning(f"Full backtest failed: {e}")
        return {"error": str(e)}


def _fmt_pct(val, decimals: int = 2) -> str:
    if val is None:
        return "—"
    try:
        return f"{float(val) * 100:.{decimals}f}%"
    except Exception:
        return "—"


def _fmt_float(val, decimals: int = 1) -> str:
    if val is None:
        return "—"
    try:
        return f"{float(val):.{decimals}f}"
    except Exception:
        return "—"


def _render_stats_col(label: str, stats: dict) -> None:
    n = stats.get("count", 0)
    mean = stats.get("mean")
    median = stats.get("median")
    win_rate = stats.get("win_rate")
    ci = stats.get("ci_95")

    st.markdown(f"**{label}**")
    st.metric("樣本數 N", n)
    st.metric("平均淨報酬", _fmt_pct(mean) if mean is not None else "—")
    st.metric("中位淨報酬", _fmt_pct(median) if median is not None else "—")
    if win_rate is not None:
        st.metric("勝率", f"{win_rate:.1f}%")
    if ci:
        lo = ci.get("lo", 0)
        hi = ci.get("hi", 0)
        st.caption(f"95% CI [{_fmt_pct(lo)}, {_fmt_pct(hi)}]")
    elif n > 0 and n < 10:
        st.caption("CI: 需 n ≥ 10")


def page_entry_timing_research() -> None:
    st.markdown("## V2 進場時機研究（Shadow Mode）")

    # Prominent research-only banner
    st.markdown(
        '<div style="background:#fef2f2;border:2px solid #dc2626;'
        'border-radius:6px;padding:10px 14px;margin-bottom:12px">'
        '<span style="color:#dc2626;font-weight:700;font-size:0.85rem">'
        "🔬 RESEARCH ONLY — NOT A LIVE BUY SIGNAL</span><br>"
        '<span style="color:#7f1d1d;font-size:0.78rem">'
        "此頁為 V2 Entry Timing 研究輸出。V2 標籤不影響正式買賣決策、"
        "持倉、ForwardSignal 或 MODEL_VERSION v8.0 任何元件。"
        "</span></div>",
        unsafe_allow_html=True,
    )

    # Research version selector (global, affects all tabs)
    col_v, col_info = st.columns([2, 5])
    with col_v:
        research_version = st.selectbox(
            "研究版本",
            _RESEARCH_VERSIONS,
            index=0,
            key="et_research_version",
        )
    with col_info:
        if research_version == "v2_research_v1":
            st.info(
                "v2_research_v1：舊版資料（pre-DESC fix），is_legacy=True。"
                "僅供歷史對照。"
            )
        else:
            st.success("v2_research_v2：最新版本（post-DESC fix），is_legacy=False。")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 訊號列表",
        "📊 完整回測（FOS）",
        "🔬 有效性分析",
        "🔀 Hybrid 策略",
        "⚠️ 已知限制",
    ])

    with tab1:
        _render_signal_list(research_version)

    with tab2:
        _render_full_backtest(research_version)

    with tab3:
        _render_effectiveness_analysis()

    with tab4:
        _render_hybrid_analysis()

    with tab5:
        _render_known_limitations()


def _render_signal_list(research_version: str) -> None:
    rows = _load_v2_signals(research_version)
    if not rows:
        st.info(
            f"尚無 {research_version} Shadow Signal。"
            "請執行 EntryTimingResearchService.run_for_date() 或 "
            "ShadowRecalculationService.recalculate() 產生資料。"
        )
        return

    # Freshness
    dates = [r["trade_date"] for r in rows]
    st.caption(
        f"資料範圍：{min(dates)} ～ {max(dates)}  ·  "
        f"共 {len(rows)} 筆（最多顯示 300 筆）"
    )

    # Label distribution
    from collections import Counter

    label_counts = Counter(r["entry_label"] for r in rows)
    cols = st.columns(min(len(label_counts), 4))
    for i, (label, cnt) in enumerate(sorted(label_counts.items(), key=lambda x: -x[1])):
        if i >= 4:
            break
        color = _LABEL_COLORS.get(label, "#6b7280")
        with cols[i % 4]:
            st.markdown(
                f'<div style="background:{color}20;border:1px solid {color}40;'
                f'border-radius:6px;padding:8px;text-align:center">'
                f'<div style="font-size:1.4rem;font-weight:700;color:{color}">{cnt}</div>'
                f'<div style="font-size:0.65rem;color:#666">{label}</div></div>',
                unsafe_allow_html=True,
            )
    st.markdown("---")

    # Filters
    all_labels = sorted(set(r["entry_label"] for r in rows))
    sel_labels = st.multiselect("篩選 V2 標籤", all_labels, default=all_labels, key="et_label_filter")
    filtered = [r for r in rows if r["entry_label"] in sel_labels]

    import pandas as pd

    df = pd.DataFrame(filtered)
    if df.empty:
        st.caption("無符合條件的資料")
        return

    df_display = df[[
        "trade_date", "stock_id", "v1_label", "entry_label",
        "entry_price", "stop_price", "target_price",
        "rr_ratio", "vol_ratio",
    ]].rename(columns={
        "trade_date": "日期",
        "stock_id": "股票",
        "v1_label": "V1 標籤",
        "entry_label": "V2 進場標籤",
        "entry_price": "進場價",
        "stop_price": "停損價",
        "target_price": "目標價",
        "rr_ratio": "R/R",
        "vol_ratio": "量比",
    })

    for col in ["進場價", "停損價", "目標價", "R/R", "量比"]:
        df_display[col] = df_display[col].apply(_fmt_float)

    st.dataframe(df_display, use_container_width=True, height=400)


def _render_full_backtest(research_version: str) -> None:
    st.markdown("### V1 vs V2 三路比較（Full Opportunity Set）")
    st.caption(
        "Comparison C (FOS) 為主要指標：同一 V1 訊號池，V2 有成交用模擬報酬，"
        "未成交用 0%（SA-7）。"
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        today = date.today()
        from_date = st.date_input(
            "起始日",
            value=today - timedelta(days=180),
            key="et_from_date",
        )
    with col2:
        to_date = st.date_input(
            "結束日",
            value=today,
            key="et_to_date",
        )
    with col3:
        expiry_days = st.number_input(
            "等待上限（交易日）",
            min_value=1,
            max_value=30,
            value=10,
            step=1,
            key="et_expiry",
        )

    if st.button("執行回測", type="primary", key="et_run_backtest"):
        st.cache_data.clear()

    result = _load_full_backtest(
        from_date_str=str(from_date),
        to_date_str=str(to_date),
        research_version=research_version,
        expiry_days=int(expiry_days),
    )

    if "error" in result:
        st.error(f"回測失敗：{result['error']}")
        return

    if result.get("v1_eligible_count", 0) == 0:
        notes = result.get("notes", [])
        st.info(notes[1] if len(notes) > 1 else "此區間無符合條件的訊號。")
        return

    # Header metrics
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("V1 訊號數 (OHLC 模擬)", result["v1_eligible_count"])
    with m2:
        st.metric("V2 可嘗試進場", result["v2_fillable_count"])
    with m3:
        fill_rate = result.get("fill_rate_pct")
        st.metric("成交率（Fill Rate）", f"{fill_rate:.1f}%" if fill_rate is not None else "—")
    with m4:
        avg_wait = result.get("avg_waiting_days")
        st.metric("平均等待天數", f"{avg_wait:.1f}d" if avg_wait is not None else "—")
    with m5:
        perf_delta = result.get("performance_delta")
        if perf_delta is not None:
            delta_color = "normal" if perf_delta >= 0 else "inverse"
            st.metric(
                "策略績效差（V2-V1）",
                _fmt_pct(perf_delta),
                delta=_fmt_pct(perf_delta),
                delta_color=delta_color,
                help="mean(V2_ret - V1_ret) per paired signal",
            )
        else:
            st.metric("策略績效差", "—")

    st.markdown("---")

    # Three-way comparison
    comp_a, comp_b, comp_c = st.columns(3)
    with comp_a:
        st.markdown(
            '<div style="background:#eff6ff;border-left:3px solid #2563eb;'
            'padding:8px;border-radius:4px;margin-bottom:8px">'
            '<span style="font-size:0.7rem;color:#1e40af;font-weight:600">'
            "比較 A：訊號選擇（fwd_return_20d）"
            "</span></div>",
            unsafe_allow_html=True,
        )
        st.caption("ENTRY_READY 子集 vs V1 全量（同用 fwd_return_20d；參考用）")
        c1a, c1b = st.columns(2)
        with c1a:
            _render_stats_col("V1 (fwd)", result.get("v1_fwd_stats", {}))
        with c1b:
            _render_stats_col("V2 ENTRY_READY", result.get("v2_selection_stats", {}))

    with comp_b:
        st.markdown(
            '<div style="background:#fefce8;border-left:3px solid #ca8a04;'
            'padding:8px;border-radius:4px;margin-bottom:8px">'
            '<span style="font-size:0.7rem;color:#713f12;font-weight:600">'
            "比較 B：已成交（⚠️ 選擇偏差）"
            "</span></div>",
            unsafe_allow_html=True,
        )
        st.caption("僅已模擬成交的 V2 — 存在選擇偏差，勿單獨解讀")
        c2a, c2b = st.columns(2)
        with c2a:
            _render_stats_col("V1 (OHLC)", result.get("v1_fos_stats", {}))
        with c2b:
            _render_stats_col("V2 Filled", result.get("v2_filled_stats", {}))

    with comp_c:
        st.markdown(
            '<div style="background:#f0fdf4;border-left:3px solid #16a34a;'
            'padding:8px;border-radius:4px;margin-bottom:8px">'
            '<span style="font-size:0.7rem;color:#14532d;font-weight:600">'
            "比較 C：Full Opportunity Set（主要指標）"
            "</span></div>",
            unsafe_allow_html=True,
        )
        st.caption("V2 filled 用 OHLC 模擬報酬 + 未成交用 0%（SA-7）")
        c3a, c3b = st.columns(2)
        with c3a:
            _render_stats_col("V1 (OHLC)", result.get("v1_fos_stats", {}))
        with c3b:
            _render_stats_col("V2 FOS", result.get("v2_fos_stats", {}))

    st.markdown("---")

    # Performance Delta & Missed Opportunity section
    st.markdown("#### 策略績效差（Performance Delta）與錯失機會（Missed Opportunity）")
    da_col, mo_col = st.columns([1, 2])

    with da_col:
        st.markdown(
            '<div style="background:#faf5ff;border-left:3px solid #9333ea;'
            'padding:8px;border-radius:4px;margin-bottom:8px">'
            '<span style="font-size:0.7rem;color:#6b21a8;font-weight:600">'
            "策略績效差（Paired）"
            "</span></div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "mean(V2_ret − V1_ret) per paired signal — "
            "正值 → V2 相對 V1 多賺；負值 → V2 相對 V1 少賺。"
        )
        perf_delta = result.get("performance_delta")
        if perf_delta is not None:
            arrow = "↑" if perf_delta >= 0 else "↓"
            color = "#16a34a" if perf_delta >= 0 else "#dc2626"
            st.markdown(
                f'<div style="font-size:1.6rem;font-weight:700;color:{color}">'
                f"{arrow} {_fmt_pct(perf_delta)}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("無資料（需配對訊號）")

        indep = result.get("independent_delta")
        if indep is not None:
            st.caption(f"獨立樣本 delta（V2_FOS - V1_FOS）：{_fmt_pct(indep)}")

        # Paired delta CI
        pds = result.get("paired_delta_stats", {})
        if pds.get("ci_95"):
            ci = pds["ci_95"]
            st.caption(
                f"Paired delta 95% CI [{_fmt_pct(ci.get('lo'))}, {_fmt_pct(ci.get('hi'))}]"
                f"  (n={pds.get('count', '?')})"
            )

    with mo_col:
        st.markdown(
            '<div style="background:#fff7ed;border-left:3px solid #ea580c;'
            'padding:8px;border-radius:4px;margin-bottom:8px">'
            '<span style="font-size:0.7rem;color:#9a3412;font-weight:600">'
            "錯失機會（Missed Opportunity）— V2 未成交訊號"
            "</span></div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "V2 未成交訊號的 V1 OHLC 模擬報酬：正值代表真正錯失上漲；"
            "負值代表因等待反而避開下跌。"
        )
        mo = result.get("missed_opportunity", {})
        n_no_fill = mo.get("n_no_fill", 0)

        if n_no_fill == 0:
            st.info("此區間無 V2 未成交訊號。")
        else:
            m1c, m2c, m3c = st.columns(3)
            with m1c:
                st.metric(
                    "V2 未成交（n）",
                    n_no_fill,
                )
                signed = mo.get("signed_missed_return")
                st.metric(
                    "綜合錯失報酬",
                    _fmt_pct(signed) if signed is not None else "—",
                    help="mean V1 return for no-fill signals (+/-)",
                )
            with m2c:
                n_pos = mo.get("n_positive_missed", 0)
                pos_up = mo.get("positive_missed_upside")
                st.metric(
                    f"錯失上漲 (n={n_pos})",
                    _fmt_pct(pos_up) if pos_up is not None else "—",
                    help="mean V1 return where V1 > 0 (true missed upside)",
                )
            with m3c:
                n_neg = mo.get("n_avoided_negative", 0)
                avoided = mo.get("avoided_loss")
                st.metric(
                    f"避開下跌 (n={n_neg})",
                    _fmt_pct(avoided) if avoided is not None else "—",
                    help="mean V1 return where V1 < 0 (loss avoided by waiting)",
                )

    # Data quality notes
    missing_ohlcv = result.get("missing_ohlcv_count", 0)
    if missing_ohlcv:
        st.warning(f"資料缺失：{missing_ohlcv} 筆缺 OHLCV（已略過）")
    dedup_removed = result.get("dedup_removed", 0)
    if dedup_removed:
        st.caption(f"28 日 Dedup 移除重複訊號：{dedup_removed} 筆")

    # Notes
    with st.expander("回測假設 (SA)"):
        for note in result.get("notes", []):
            st.caption(f"• {note}")


def _load_effectiveness_json() -> dict:
    import json
    import os
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data", "effectiveness_analysis.json",
    )
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _verdict_color(verdict: str) -> str:
    return {
        "VALIDATED": "#16a34a",
        "CONDITIONAL": "#ca8a04",
        "NOT SUPPORTED": "#dc2626",
        "INSUFFICIENT DATA": "#6b7280",
    }.get(verdict, "#6b7280")


def _render_group_table(groups: dict) -> None:
    """Render a group-performance dict as a colour-coded table."""
    import pandas as pd
    rows = []
    for label, s in groups.items():
        n = s.get("n", 0)
        delta = s.get("paired_delta_mean")
        ci = s.get("paired_delta_ci95")
        rows.append({
            "分組": label,
            "N": n,
            "V1 均值": _fmt_pct(s.get("v1_mean")),
            "V2 FOS 均值": _fmt_pct(s.get("v2_mean")),
            "配對 Delta": _fmt_pct(delta),
            "95% CI": (
                f"[{_fmt_pct(ci['lo'])}, {_fmt_pct(ci['hi'])}]" if ci else "—"
            ),
            "成交率": f"{s.get('fill_rate_pct'):.1f}%" if s.get("fill_rate_pct") else "—",
            "樣本": "⚠️ 不足" if s.get("insufficient_sample") else "OK",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_effectiveness_analysis() -> None:
    st.markdown("### V2 有效性分析（Effectiveness Analysis）")
    st.caption(
        "RESEARCH ONLY — 此分析基於 EntryTimingAnalyzer 生成的研究訊號，"
        "非正式 ForwardSignal pipeline。"
    )

    data = _load_effectiveness_json()
    if not data:
        st.info(
            "尚無有效性分析資料。請執行：\n\n"
            "```bash\npython3 scripts/run_effectiveness_analysis.py\n```"
        )
        return

    generated = data.get("generated_at", "未知")
    cfg = data.get("config", {})
    st.caption(
        f"分析生成日期：{generated}  ·  "
        f"研究期間：{cfg.get('signal_start')} to {cfg.get('signal_end')}  ·  "
        f"股票：{cfg.get('sample_stocks')}  ·  去重視窗：{cfg.get('dedup_window')}d"
    )

    summary = data.get("summary", {})
    verdict = summary.get("verdict", "—")
    verdict_color = _verdict_color(verdict)

    # Overall verdict banner
    st.markdown(
        f'<div style="background:{verdict_color}20;border:2px solid {verdict_color};'
        f'border-radius:6px;padding:10px 16px;margin-bottom:12px">'
        f'<span style="font-weight:700;font-size:0.9rem;color:{verdict_color}">'
        f"最終評級：{verdict}</span><br>"
        f'<span style="color:#374151;font-size:0.78rem">'
        "RESEARCH ONLY — 此評級不代表正式買賣建議"
        "</span></div>",
        unsafe_allow_html=True,
    )

    # Header metrics
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("有效配對訊號", summary.get("overall_n", "—"))
    with m2:
        fill = summary.get("overall_fill_rate")
        st.metric("整體成交率", f"{fill:.1f}%" if fill else "—")
    with m3:
        delta = summary.get("overall_paired_delta")
        color = "normal" if (delta or 0) >= 0 else "inverse"
        st.metric("整體 Paired Delta（V2-V1）", _fmt_pct(delta), delta=_fmt_pct(delta), delta_color=color,
                  help="V2 FOS 相較 V1 OHLC 平均每訊號多賺/少賺")
    with m4:
        oos = summary.get("oos_paired_delta")
        oos_color = "normal" if (oos or 0) >= 0 else "inverse"
        st.metric("OOS Delta", _fmt_pct(oos), delta=_fmt_pct(oos), delta_color=oos_color,
                  help="樣本外 (OOS) 2026-07 to 2026-09 的 Paired Delta")
    with m5:
        st.metric("OOS 通過", summary.get("oos_pass_fail", "—"),
                  help="PASS = delta ≥ -1pp；FAIL = delta < -1pp")

    st.markdown("---")

    # Tabs for each analysis section
    ea_tabs = st.tabs([
        "📋 資料稽核", "🔍 MA20 稽核", "📊 分組分析",
        "⏱ Walk-forward", "🔧 敏感度"
    ])

    # ── Tab 1: Data Integrity Audit ───────────────────────────────────────────
    with ea_tabs[0]:
        st.markdown("#### 資料完整性稽核")
        st.caption(
            "**去重規則（28-day dedup）**：同一股票在 28 曆日內重複出現的訊號，"
            "保留最早一筆，餘者排除。主要結論採用「去重後＋已成熟＋有效配對」資料集。"
        )
        audit = data.get("data_integrity_audit", {})
        a1, a2, a3, a4 = st.columns(4)
        with a1:
            st.metric("原始訊號（Raw）", audit.get("raw_count", "—"))
        with a2:
            st.metric("去重後（Dedup）", audit.get("dedup_count", "—"))
        with a3:
            st.metric("已成熟", audit.get("matured_count", "—"))
        with a4:
            st.metric("有效配對（主要分析）", audit.get("valid_paired_count", "—"))

        col_l, col_r = st.columns(2)
        with col_l:
            st.caption(f"獨立股票數：{audit.get('unique_stocks')} | "
                       f"獨立交易日：{audit.get('unique_dates')}")
            st.caption(f"去重移除：{audit.get('dedup_removed')} | "
                       f"未成熟（無足夠後續資料）：{audit.get('missing_maturity_count')}")
            if audit.get("concentration_warning"):
                st.warning("⚠️ 集中度警告：單一股票超過 15% 的去重成熟訊號")
            else:
                st.success("✅ 無集中度警告（單一股票 ≤ 15%）")

        with col_r:
            label_dist = audit.get("entry_label_dist", {})
            if label_dist:
                import pandas as pd
                df_dist = pd.DataFrame(
                    [{"進場標籤": k, "數量": v} for k, v in label_dist.items()]
                )
                st.dataframe(df_dist, use_container_width=True, hide_index=True)

        monthly = audit.get("monthly_dist", {})
        if monthly:
            import pandas as pd
            df_monthly = pd.DataFrame([{"月份": k, "訊號數": v} for k, v in monthly.items()])
            st.markdown("**月份分布（去重成熟）**")
            st.bar_chart(df_monthly.set_index("月份"))

        regime_dist = audit.get("regime_dist", {})
        if regime_dist:
            st.caption(
                "市場狀態分布：" + "  |  ".join(f"{k}: {v}" for k, v in regime_dist.items())
            )

    # ── Tab 2: MA20 Audit ─────────────────────────────────────────────────────
    with ea_tabs[1]:
        st.markdown("#### MA20 / Planned Entry 稽核")
        st.caption(
            "**SA-1 fix 驗證**：WAIT_FOR_PULLBACK 的 planned_entry = stop/(1-0.03) = MA20 估計值。"
            "此稽核確認 stop-derived MA20 與 EntryTimingAnalyzer 實際計算的 MA20 誤差。"
        )
        ma = data.get("ma20_audit", {})
        assessment = ma.get("assessment", "—")
        ma_color = "#16a34a" if assessment == "ACCURATE" else "#ca8a04" if assessment == "MINOR_DEVIATION" else "#dc2626"
        st.markdown(
            f'<span style="background:{ma_color}20;border:1px solid {ma_color};'
            f'padding:4px 12px;border-radius:4px;font-weight:600;color:{ma_color}">'
            f"評估：{assessment}</span>",
            unsafe_allow_html=True,
        )
        ma1, ma2, ma3, ma4 = st.columns(4)
        with ma1:
            st.metric("稽核訊號數", ma.get("n_audited", "—"))
        with ma2:
            st.metric("1% 以內比例", f"{ma.get('pct_within_1pct')}%" if ma.get("pct_within_1pct") is not None else "—")
        with ma3:
            st.metric("平均絕對誤差", _fmt_float(ma.get("ma20_vs_derived_mean_abs_diff"), 4))
        with ma4:
            st.metric("WAIT_PULLBACK 筆數", ma.get("wait_pullback_n", "—"))

        wp_diff = ma.get("wait_pullback_entry_vs_ma20_mean_diff_pct")
        if wp_diff is not None:
            st.caption(
                f"WAIT_FOR_PULLBACK：planned_entry vs 實際 MA20 均差 = {wp_diff:.4f}%"
                "（接近 0 表示 SA-1 公式正確）"
            )
        for note in ma.get("notes", []):
            st.caption(f"• {note}")

    # ── Tab 3: Group Analysis ─────────────────────────────────────────────────
    with ea_tabs[2]:
        st.markdown("#### 分組績效分析（Part B）")
        st.warning(data.get("group_analysis", {}).get("multiple_testing_note", ""))
        st.caption(
            "⚠️ 分組後最好的結果不代表有效策略。"
            "樣本數不足的分組（標記為「⚠️ 不足」）僅供假設生成，不可用於決策。"
        )

        ga = data.get("group_analysis", {})
        g_tabs = st.tabs([
            "進場類型", "MA20 趨勢", "MA60 趨勢", "MA20 Gap", "市場狀態", "整體"
        ])

        with g_tabs[0]:
            st.caption(
                "**進場類型（Entry Setup）**：ENTRY_READY = V2 與 V1 相同立即進場；"
                "WAIT_FOR_PULLBACK/BREAKOUT = 等待觸發條件。"
                "ENTRY_READY 的 delta 應接近 0（相同進場條件）。"
            )
            _render_group_table(ga.get("by_entry_label", {}))

        with g_tabs[1]:
            st.caption(
                "**MA20 趨勢**：rising/flat/falling 依訊號當天前 10 個交易日的 MA20 斜率判定。"
                "rising > +0.3% / falling < -0.3% / 其餘 flat。"
            )
            _render_group_table(ga.get("by_ma20_trend", {}))

        with g_tabs[2]:
            st.caption(
                "**MA60 趨勢**：需 ≥70 bars 歷史才能計算。unknown = 歷史不足。"
            )
            _render_group_table(ga.get("by_ma60_trend", {}))

        with g_tabs[3]:
            st.caption(
                "**MA20 Gap（% 距離）**：訊號當天收盤距 MA20 的百分比。"
                "<0% = 收盤低於 MA20；>5% = 偏離過大。"
            )
            _render_group_table(ga.get("by_ma20_gap_bucket", {}))

        with g_tabs[4]:
            st.caption(
                "**市場狀態（Market Regime）**：依 0050 MA20 斜率判定。"
                "bull = 0050 > MA20 且 MA20 rising；"
                "bear = 0050 < MA20 且 MA20 falling；neutral = 其餘。"
            )
            _render_group_table(ga.get("by_market_regime", {}))

        with g_tabs[5]:
            overall = ga.get("overall", {})
            if overall:
                _render_group_table({"整體": overall})

    # ── Tab 4: Walk-forward ───────────────────────────────────────────────────
    with ea_tabs[3]:
        st.markdown("#### Walk-forward 時序驗證（Part C）")
        st.caption(
            "**Out-of-Sample（OOS）**：用沒有參與策略設計的歷史期間確認策略是否仍有效。"
            "此處 OOS 為 2026-07-01 to 2026-09-15（最後 2.5 個月）。"
            "W1–W9 為開發期間內的時序切分（无 parameter fitting，僅供時間一致性驗證）。"
        )
        wf = data.get("walk_forward", [])
        if wf:
            import pandas as pd
            rows = []
            for w in wf:
                pf = w.get("pass_fail", "—")
                is_oos = w.get("is_oos", False)
                rows.append({
                    "視窗": ("🔵 OOS: " if is_oos else "") + w.get("name", "—"),
                    "測試期間": f"{w.get('test_start')} ～ {w.get('test_end')}",
                    "N": w.get("n", 0),
                    "Paired Delta": _fmt_pct(w.get("paired_delta_mean")),
                    "95% CI": (
                        f"[{_fmt_pct(w.get('paired_delta_ci95', {}).get('lo'))}, "
                        f"{_fmt_pct(w.get('paired_delta_ci95', {}).get('hi'))}]"
                        if w.get("paired_delta_ci95") else "—"
                    ),
                    "成交率": f"{w.get('fill_rate_pct'):.1f}%" if w.get("fill_rate_pct") else "—",
                    "主要 Regime": w.get("dominant_regime", "—"),
                    "通過/失敗": pf,
                })
            df_wf = pd.DataFrame(rows)
            st.dataframe(df_wf, use_container_width=True, hide_index=True)

            pass_count = sum(1 for w in wf if w.get("pass_fail") == "PASS")
            total_count = sum(1 for w in wf if w.get("pass_fail") in ("PASS", "FAIL"))
            st.caption(
                f"通過率：{pass_count}/{total_count} 個視窗 PASS  "
                f"（INSUFFICIENT_DATA 視窗不計）"
            )

    # ── Tab 5: Sensitivity ────────────────────────────────────────────────────
    with ea_tabs[4]:
        st.markdown("#### 敏感度分析（Sensitivity Matrix，Part D）")
        st.caption(
            "**Robustness（穩健性）**：交易條件稍微改變（等待天數、費率等），"
            "策略結果是否仍維持類似表現。"
            "FRAGILE = 與 base 偏差 > 0.5pp；ROBUST = 所有變體均穩定。"
        )
        sens = data.get("sensitivity_matrix", [])
        if sens:
            import pandas as pd
            overall_row = next((r for r in sens if r["variant"] == "_overall"), None)
            if overall_row:
                robustness = overall_row.get("note", "—")
                rob_color = "#16a34a" if "ROBUST" in robustness else "#dc2626"
                st.markdown(
                    f'<span style="background:{rob_color}20;border:1px solid {rob_color};'
                    f'padding:4px 12px;border-radius:4px;font-weight:600;color:{rob_color}">'
                    f"{robustness}</span>",
                    unsafe_allow_html=True,
                )

            rows = []
            for v in sens:
                if v["variant"] == "_overall":
                    continue
                is_fragile = v.get("is_fragile", False)
                rows.append({
                    "變體": v["variant"],
                    "說明": v.get("description", ""),
                    "N": v.get("n", "—"),
                    "Paired Delta": _fmt_pct(v.get("paired_delta_mean")),
                    "V1 均值": _fmt_pct(v.get("v1_mean")),
                    "V2 均值": _fmt_pct(v.get("v2_mean")),
                    "成交率": f"{v.get('fill_rate_pct'):.1f}%" if v.get("fill_rate_pct") else "—",
                    "穩健性": "🔴 FRAGILE" if is_fragile else "✅ OK",
                })
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("⚠️ 不得選擇表現最佳的參數版本作為正式設定。")


@st.cache_data(ttl=600)
def _load_hybrid_json() -> dict:
    import json
    import os
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data", "hybrid_backtest.json",
    )
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _render_hybrid_analysis() -> None:
    st.markdown("### 🔀 Hybrid Entry Strategy V1 — 三策略比較")

    # In-sample warning banner
    st.markdown(
        '<div style="background:#fff7ed;border:2px solid #f97316;'
        'border-radius:6px;padding:10px 14px;margin-bottom:16px">'
        '<span style="color:#c2410c;font-weight:700">⚠️ RETROSPECTIVE / IN-SAMPLE</span><br>'
        'Hybrid V1 規則由同一組 2024-10 至 2026-09 研究資料推導出。'
        '所有回顧性結果均屬<strong>樣本內 (IN-SAMPLE)</strong>，無法視為獨立驗證。<br>'
        '真正的 OOS 驗證 = 2026-11-05 規則凍結後的前瞻影子 (Forward Shadow)。'
        '</div>',
        unsafe_allow_html=True,
    )

    data = _load_hybrid_json()

    if not data:
        st.info(
            "尚無 Hybrid 分析結果。請執行：\n\n"
            "`python scripts/run_hybrid_backtest.py`\n\n"
            "結果將存入 data/hybrid_backtest.json。"
        )
        _render_hybrid_rule_reference()
        return

    # Meta
    meta = data.get("meta", {})
    if meta:
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("規則版本", meta.get("rule_version", "—"))
        col_b.metric("規則凍結時間", meta.get("rule_frozen_at", "—")[:10])
        col_c.metric("有效訊號數", f"{meta.get('n_valid_signals', '—'):,}" if isinstance(meta.get('n_valid_signals'), int) else "—")
        st.caption(f"分析期間：{meta.get('signal_period', '—')} | 凍結 commit：{meta.get('rule_frozen_commit', '—')}")

    htabs = st.tabs(["📊 三策略比較", "🎯 動作分佈", "🔍 子群分析", "🔮 前瞻影子", "📋 規則說明"])

    # ── Tab: Three-strategy comparison ────────────────────────────────────────
    with htabs[0]:
        import pandas as pd
        comp = data.get("comparison", {})
        strategies = comp.get("strategies", {})
        if strategies:
            rows = []
            for key, s in strategies.items():
                rows.append({
                    "策略": {"v1": "V1 (立即進場)", "v2_fos": "V2 FOS (等待進場)", "hybrid": "Hybrid V1 (條件選擇)"}.get(key, key),
                    "訊號數": s.get("n", "—"),
                    "平均淨報酬": f"{s.get('mean_net_ret', 0):+.3f}%" if s.get('mean_net_ret') is not None else "—",
                    "勝率": f"{s.get('win_rate', 0):.1f}%" if s.get('win_rate') is not None else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        deltas = comp.get("paired_deltas", {})
        if deltas:
            st.markdown("#### 配對差值分析")
            delta_rows = []
            pair_labels = {
                "v2_vs_v1": "V2 vs V1",
                "hybrid_vs_v1": "Hybrid vs V1 ⭐",
                "hybrid_vs_v2": "Hybrid vs V2",
            }
            for pair_key, pair_label in pair_labels.items():
                s = deltas.get(pair_key, {})
                ci = s.get("ci_95") or {}
                verdict = s.get("ci_verdict", "—")
                verdict_icon = {"POSITIVE_CI": "✅", "NEGATIVE_CI": "🔴", "CI_SPANS_ZERO": "⚪"}.get(verdict, "—")
                delta_rows.append({
                    "比較": pair_label,
                    "平均差值": f"{s.get('mean', 0):+.3f}%" if s.get('mean') is not None else "—",
                    "95% CI 下界": f"{ci.get('lo', '—'):.3f}%" if isinstance(ci.get('lo'), float) else "—",
                    "95% CI 上界": f"{ci.get('hi', '—'):.3f}%" if isinstance(ci.get('hi'), float) else "—",
                    "結論": f"{verdict_icon} {verdict}",
                })
            st.dataframe(pd.DataFrame(delta_rows), use_container_width=True, hide_index=True)

        switch = data.get("switch_summary", {})
        if switch:
            st.markdown("#### Hybrid 動作切換摘要（WAIT_FOR_PULLBACK 訊號）")
            col1, col2, col3 = st.columns(3)
            col1.metric("WAIT_FOR_PULLBACK 總數", switch.get("total_wait_for_pullback", "—"))
            col2.metric("保持等待 (Bear/Flat → 維持V2)", switch.get("kept_waiting", "—"))
            col3.metric("切換直接進場 (Bull/Rising → 改用V1)", switch.get("switched_to_direct", "—"))

        st.caption(
            "⚠️ 所有數字均為回顧性 (IN-SAMPLE)。Hybrid 規則由同一資料推導，無法視為 OOS。"
        )

    # ── Tab: Action distribution ───────────────────────────────────────────────
    with htabs[1]:
        import pandas as pd
        dist = data.get("action_distribution", {})
        if not dist:
            st.info("無動作分佈資料。")
        else:
            st.markdown(f"**訊號總數：{dist.get('total', 0):,}**")
            ac = dist.get("action_counts", {})
            if ac:
                st.markdown("#### 整體動作分佈")
                rows = [{"動作": k, "數量": v, "佔比": f"{v / dist['total'] * 100:.1f}%"}
                        for k, v in sorted(ac.items(), key=lambda x: -x[1])]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            by_label = dist.get("by_entry_label", {})
            if by_label:
                st.markdown("#### 依 Entry Label 分佈")
                rows = []
                for lbl, actions in sorted(by_label.items()):
                    total_lbl = sum(actions.values())
                    for action, cnt in sorted(actions.items()):
                        rows.append({"Entry Label": lbl, "Hybrid 動作": action,
                                     "數量": cnt, "佔比": f"{cnt/total_lbl*100:.1f}%"})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            by_regime = dist.get("by_market_regime", {})
            if by_regime:
                st.markdown("#### 依市場狀態分佈")
                rows = []
                for regime, actions in sorted(by_regime.items()):
                    total_r = sum(actions.values())
                    for action, cnt in sorted(actions.items()):
                        rows.append({"市場狀態": regime, "Hybrid 動作": action,
                                     "數量": cnt, "佔比": f"{cnt/total_r*100:.1f}%"})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Tab: Subgroup analysis ─────────────────────────────────────────────────
    with htabs[2]:
        import pandas as pd
        sub = data.get("subgroup_analysis", {})
        if not sub:
            st.info("無子群分析資料。")
        else:
            def _render_sub_table(title: str, groups: dict) -> None:
                st.markdown(f"#### {title}")
                rows = []
                for key, s in sorted(groups.items()):
                    ci = s.get("ci_95") or {}
                    verdict = s.get("ci_verdict", "—")
                    verdict_icon = {"POSITIVE_CI": "✅", "NEGATIVE_CI": "🔴", "CI_SPANS_ZERO": "⚪", "INSUFFICIENT_SAMPLE": "⚫"}.get(verdict, "—")
                    rows.append({
                        "群組": key,
                        "N": s.get("n", "—"),
                        "Hybrid vs V1 均值": f"{s.get('mean_delta', 0):+.3f}%" if s.get('mean_delta') is not None else "—",
                        "95% CI": f"[{ci.get('lo','—')}, {ci.get('hi','—')}]" if ci else "—",
                        "結論": f"{verdict_icon} {verdict}",
                    })
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            _render_sub_table("依 Hybrid 動作", sub.get("by_hybrid_action", {}))
            _render_sub_table("依市場狀態", sub.get("by_market_regime", {}))
            _render_sub_table("依 MA20 趨勢", sub.get("by_ma20_trend", {}))
            _render_sub_table("依 Entry Label", sub.get("by_entry_label", {}))

        st.caption("⚠️ 所有子群分析均為 IN-SAMPLE。需 Bonferroni 校正（~20 次比較 → α=0.0025）。")

    # ── Tab: Forward shadow ────────────────────────────────────────────────────
    with htabs[3]:
        _render_hybrid_forward_shadow_status()

    # ── Tab: Rule reference ────────────────────────────────────────────────────
    with htabs[4]:
        _render_hybrid_rule_reference()


def _render_dailyprice_freshness_panel(db_path: str) -> None:
    """H2. DailyPrice data freshness — last date, gap, missing days, cron status."""
    import os as _os
    import sqlite3 as _sqlite3
    from datetime import date as _date

    st.markdown("#### H2. DailyPrice 資料新鮮度")
    if not _os.path.exists(db_path):
        st.error("SQLite not found")
        return

    try:
        conn = _sqlite3.connect(db_path)
        last_row = conn.execute(
            "SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'"
        ).fetchone()
        total_rows = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        stocks_today = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=(SELECT MAX(date) FROM daily_prices)"
        ).fetchone()[0]
        conn.close()
    except Exception as e:
        st.error(f"DB read error: {e}")
        return

    last_date_str = last_row[0] if last_row else None
    today = _date.today()

    if last_date_str:
        last_date = _date.fromisoformat(last_date_str)
        gap_days = (today - last_date).days
        stale = gap_days > 7
    else:
        last_date = None
        gap_days = None
        stale = True

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("最新日期 (0050)", str(last_date) if last_date else "無資料")
    with col2:
        gap_label = f"{gap_days}天" if gap_days is not None else "—"
        st.metric("距今天數", gap_label, delta=None)
    with col3:
        st.metric("最新日股票數", f"{stocks_today:,}")
    with col4:
        st.metric("DB 總行數", f"{total_rows:,}")

    if stale:
        st.warning(
            f"DailyPrice 已過期 {gap_days} 天（閾值 7 天）。"
            "Shadow runner 將被 BLOCKED_STALE_DATA 阻擋。\n\n"
            "修復：`python3 scripts/backfill_daily_prices.py --execute`"
        )
    elif gap_days is not None and gap_days > 2:
        st.info(
            f"DailyPrice 距今 {gap_days} 天。Shadow runner 仍可運行（< 7 天閾值）。"
        )
    else:
        st.success(f"DailyPrice 新鮮（{gap_days} 天前）")

    st.caption(
        "Cron 自動化狀態見 G0 面板。手動補資料：`python3 scripts/backfill_daily_prices.py --execute`"
    )


def _render_storage_health_panel(db_path: str) -> None:
    """
    H. Storage health panel — shows backend status without exposing credentials.
    Status: HEALTHY / DEGRADED / BLOCKED / UNKNOWN.
    Never exposes DB URL, password, token, or full file path.
    """
    import os

    from src.research.storage_adapter import SQLiteResearchStorage, StorageHealthStatus

    st.markdown("#### H. 儲存系統健康")

    # Backend info (non-sensitive)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("儲存後端", "SQLite (Option A)")
    col2.metric("環境", "research_local")
    col3.metric("是否為正式資料庫", "否")
    col4.metric("DB 檔案", "platform.db")

    if not os.path.exists(db_path):
        st.error("🔴 BLOCKED — data/platform.db 不存在")
        st.info("執行 `python scripts/run_hybrid_forward_shadow.py` 建立研究資料庫。")
        return

    try:
        file_size_kb = round(os.path.getsize(db_path) / 1024, 1)
    except OSError:
        file_size_kb = None

    with SQLiteResearchStorage(db_path) as store:
        health = store.health_check()

    status = health.get("status", StorageHealthStatus.UNKNOWN)
    tables_present = health.get("tables_present", [])
    tables_missing = health.get("tables_missing", [])

    status_display = {
        StorageHealthStatus.HEALTHY:  "✅ HEALTHY",
        StorageHealthStatus.DEGRADED: "⚠️ DEGRADED",
        StorageHealthStatus.BLOCKED:  "🔴 BLOCKED",
        StorageHealthStatus.UNKNOWN:  "❓ UNKNOWN",
    }.get(status, f"❓ {status}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("連線狀態", status_display)
    col2.metric("研究表 (3/3)", f"{len(tables_present)}/3")
    col3.metric("DB 大小", f"{file_size_kb} KB" if file_size_kb else "未知")
    col4.metric("持久化方案", "GitHub Actions Option A")

    if tables_missing:
        st.warning(
            f"⚠️ 以下研究表尚未建立：{', '.join(tables_missing)}。"
            "執行 `python scripts/run_hybrid_forward_shadow.py` 建立。"
        )

    if status == StorageHealthStatus.HEALTHY and not tables_missing:
        st.success("✅ 儲存系統正常 — 三個研究表均已存在，連線可用。")

    st.caption(
        "儲存路徑已遮蔽。資料庫不含正式交易資料，不連結正式 Neon PostgreSQL。"
    )


def _render_ohlc_continuity_panel(db_path: str) -> None:
    """H3. OHLC Continuity Gate — 30-day window status for Hybrid signal generation."""
    import os as _os
    import sqlite3 as _sqlite3
    from datetime import date as _date

    st.markdown("#### H3. OHLC 連續性閘門")
    if not _os.path.exists(db_path):
        st.error("SQLite not found")
        return

    try:
        from src.research.ohlc_continuity_gate import GateResult, OHLCContinuityGate
        conn = _sqlite3.connect(db_path)
        gate = OHLCContinuityGate()
        trade_date = _date.today()
        report = gate.check_market(conn, trade_date)
        conn.close()
    except Exception as e:
        st.error(f"Gate check error: {e}")
        return

    result = report.gate_result
    gate_color = {
        GateResult.PASS: "✅",
        GateResult.UNKNOWN_CALENDAR: "🟡",
        GateResult.BLOCKED_MISSING_OHLC: "🔴",
        GateResult.BLOCKED_STALE_DATA: "🔴",
        GateResult.BLOCKED_INSUFFICIENT_HISTORY: "🔴",
        GateResult.NOT_APPLICABLE: "⚪",
    }.get(result, "❓")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("閘門狀態", f"{gate_color} {result.value}")
    col2.metric("檢查窗口（天）", report.continuity_window)
    col3.metric("資料齊全", report.present_sessions)
    col4.metric("資料缺失", report.missing_sessions)

    if result == GateResult.PASS:
        st.success(
            f"OHLC 連續性 PASS — 最近 {report.continuity_window} 個交易日資料完整，"
            "MA20 / MA20_SLOPE / REGIME 計算可信。"
        )
    elif result == GateResult.UNKNOWN_CALENDAR:
        st.info(
            f"OHLC 閘門：UNKNOWN_CALENDAR — {report.unknown_sessions} 個日曆矛盾日期"
            "（日曆標記休市但 DB 有資料，如 2026-10-09）。不阻擋信號產生。"
        )
    elif result == GateResult.BLOCKED_MISSING_OHLC:
        st.warning(
            f"🔴 BLOCKED_MISSING_OHLC — {report.missing_sessions} 個預期交易日缺乏 0050 資料。"
            " Hybrid 信號產生已暫停。\n\n"
            f"缺失日期：{', '.join(str(d) for d in report.missing_dates[:10])}"
            + (" ..." if len(report.missing_dates) > 10 else "")
        )
    elif result == GateResult.BLOCKED_STALE_DATA:
        st.error(
            "🔴 BLOCKED_STALE_DATA — 最後 0050 資料日距今超過 7 天。"
            "請執行 `python scripts/backfill_daily_prices.py --execute`。"
        )
    elif result == GateResult.NOT_APPLICABLE:
        st.info(f"今天（{trade_date}）非交易日，閘門不適用。")

    # Feature audit table
    if report.feature_audits:
        import pandas as pd
        audit_rows = [
            {
                "特徵": fa.feature_name,
                "需要 Bars": fa.required_lookback_bars,
                "可用 Bars": fa.available_bars,
                "缺失工作日": fa.missing_expected_sessions,
                "閘門": fa.gate_result.value,
            }
            for fa in report.feature_audits
        ]
        st.dataframe(pd.DataFrame(audit_rows), use_container_width=True, hide_index=True)

    st.caption(
        f"檢查基準：{trade_date} | 市場代理：0050 | 窗口：{report.continuity_window} 交易日 | "
        "阻擋條件：任一預期交易日缺 0050 資料"
    )


def _render_hybrid_forward_shadow_status() -> None:
    """Display forward shadow operational health from hybrid_forward_decision/outcome tables."""
    import sqlite3
    import os
    import pandas as pd

    st.markdown("### 🔮 Hybrid 前瞻影子（True OOS）")
    st.markdown(
        "**規則凍結日：2026-11-05**  \n"
        "只有 `capture_classification = PROSPECTIVE`（signal_date ≥ 2026-11-05 "
        "且在規定時間內捕捉）的記錄才是真正的前瞻 OOS 驗證。"
    )

    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data", "platform.db",
    )

    # ── H. Storage health panel ───────────────────────────────────────────────
    _render_storage_health_panel(db_path)

    # ── H2. DailyPrice freshness ──────────────────────────────────────────────
    _render_dailyprice_freshness_panel(db_path)

    # ── H3. OHLC Continuity Gate ──────────────────────────────────────────────
    _render_ohlc_continuity_panel(db_path)
    st.divider()

    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        # Check new schema tables
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        has_new_schema = "hybrid_forward_decision" in tables
        has_old_schema = "hybrid_forward_shadow" in tables

        if not has_new_schema and not has_old_schema:
            st.info(
                "forward shadow 表尚未建立。\n\n"
                "執行：`python scripts/run_hybrid_forward_shadow.py`\n\n"
                "每日市場收盤後定期執行以累積真實 OOS 記錄。"
            )
            conn.close()
            return

        if not has_new_schema and has_old_schema:
            st.warning(
                "⚠️ 偵測到舊版 `hybrid_forward_shadow` 表（V1 schema）。"
                "請執行 `run_hybrid_forward_shadow.py` 一次以建立新版 V2 schema。"
            )
            conn.close()
            return

        # ── G0. Automation / Cron Panel ───────────────────────────────────────
        import json as _json
        import subprocess
        from pathlib import Path as _Path

        _state_file = _Path(db_path).parent / ".cron_state.json"
        _cron_state: dict = {}
        if _state_file.exists():
            try:
                _cron_state = _json.loads(_state_file.read_text())
            except Exception:
                pass

        _cron_installed = False
        try:
            _cron_result = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True, timeout=5
            )
            _cron_installed = "hybrid_shadow_cron" in _cron_result.stdout
        except Exception:
            pass

        _backup_dir = _Path(db_path).parent / "backups"
        _backup_count = len(list(_backup_dir.glob("*.db.bak"))) if _backup_dir.exists() else 0

        st.markdown("#### G0. 自動化排程（Cron）")
        _run_at = _cron_state.get("run_at", "")
        _run_at_display = _run_at[:16] if len(_run_at) >= 16 else (_run_at or "—")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Cron 已安裝", "✅ 是" if _cron_installed else "⏳ 未安裝")
        col2.metric("最後執行時間", _run_at_display)
        col3.metric("最後執行狀態", _cron_state.get("status", "—"))
        col4.metric("備份檔案數", _backup_count)

        if not _cron_installed:
            st.info(
                "Local cron 尚未安裝。每日 Taiwan 16:00 自動執行需手動設定。  \n"
                "安裝指令見 `docs/hybrid_go_live_readiness.md`。"
            )
        elif _cron_state:
            _last_status = _cron_state.get("status", "")
            _last_data = _cron_state.get("last_data_date", "—")
            _execute_flag = _cron_state.get("execute", False)
            if not _execute_flag:
                st.warning(
                    "⚠️ 最後執行為 dry-run（無 `--execute` 旗標）。"
                    "請確認 crontab 包含 `--execute`。"
                )
            elif _last_status == "SUCCESS":
                st.success(f"✅ 最後執行成功。資料日期：{_last_data}")
            elif _last_status in (
                "BLOCKED_STALE_DATA",
                "SKIPPED_NON_TRADING_DAY",
                "BLOCKED_LOCK",
            ):
                st.info(f"ℹ️ 最後執行：{_last_status}（非異常狀態）。資料日期：{_last_data}")
            else:
                st.warning(
                    f"⚠️ 最後執行狀態：{_last_status}。"
                    "請檢查 `logs/hybrid_cron.log`。"
                )

        # ── G1. Operational Health ─────────────────────────────────────────────
        from src.research.hybrid_forward_db import (
            get_operational_summary, get_matured_performance
        )
        summary = get_operational_summary(conn)

        st.markdown("#### G1. 系統健康")
        latest = summary.get("latest_run")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("最新執行日", latest["trade_date"] if latest else "—")
        status_val = latest["status"] if latest else "—"
        status_color = "✅" if status_val == "SUCCESS" else ("⚠️" if status_val in ("PARTIAL", "CONFLICT") else "🔴")
        col2.metric("執行狀態", f"{status_color} {status_val}")
        col3.metric("連續失敗次數", summary.get("consecutive_failures", 0))
        col4.metric("衝突計數", latest["conflict_count"] if latest else 0)

        # Data freshness from run log
        if latest and latest.get("input_data_date"):
            last_data = latest["input_data_date"]
            st.caption(f"資料日期：{last_data} | 規則版本：hybrid_v1 | 規則凍結 commit：6602c3b")

        # ── G2. Forward Cohort ────────────────────────────────────────────────
        st.markdown("#### G2. 前瞻記錄池")
        cls_counts = summary.get("decisions_by_classification", {})
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("PROSPECTIVE（真正 OOS）", summary.get("prospective_decisions", 0))
        col2.metric("LATE_CAPTURE", cls_counts.get("LATE_CAPTURE", 0))
        col3.metric("RETROSPECTIVE", cls_counts.get("RETROSPECTIVE_RECONSTRUCTION", 0))
        col4.metric("INVALID_DATA", cls_counts.get("INVALID_DATA", 0))

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("成熟 5D", summary.get("matured_5d", 0))
        col2.metric("成熟 10D", summary.get("matured_10d", 0))
        col3.metric("成熟 20D", summary.get("matured_20d", 0))
        pending = summary.get("prospective_decisions", 0) - summary.get("matured_20d", 0)
        col4.metric("待成熟", max(0, pending))

        if summary.get("prospective_decisions", 0) > 0:
            col1b, col2b, _, _ = st.columns(4)
            col1b.metric("唯一個股", summary.get("prospective_stocks", 0))
            col2b.metric("唯一交易日", summary.get("prospective_trade_dates", 0))

        # ── G3. Forward Performance ────────────────────────────────────────────
        st.markdown("#### G3. 前瞻績效（僅 PROSPECTIVE 成熟記錄）")

        matured_20d = summary.get("matured_20d", 0)
        if matured_20d == 0:
            st.markdown(
                '<div style="background:#f0f9ff;border:1px solid #0284c7;'
                'border-radius:4px;padding:10px 14px;margin:8px 0">'
                '📊 <strong>尚無足夠前瞻樣本，等待未來交易日資料成熟。</strong><br>'
                '需要至少 50 個成熟 PROSPECTIVE 記錄才能顯示有統計意義的績效。<br>'
                '每日執行 <code>run_hybrid_forward_shadow.py</code> 累積記錄。'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            perf_rows = []
            for h in ("5d", "10d", "20d"):
                perf = get_matured_performance(conn, h)
                if perf:
                    n = perf["n_matured"]
                    hyb_v1 = perf.get("hybrid_vs_v1_mean_delta")
                    perf_rows.append({
                        "持有期": h.upper(),
                        "N（成熟）": n,
                        "V1 均值": f"{perf.get('v1_mean_ret', 0):+.3f}%" if perf.get("v1_mean_ret") else "—",
                        "V2 均值": f"{perf.get('v2_mean_ret', 0):+.3f}%" if perf.get("v2_mean_ret") else "—",
                        "Hybrid 均值": f"{perf.get('hybrid_mean_ret', 0):+.3f}%" if perf.get("hybrid_mean_ret") else "—",
                        "Hybrid vs V1 Δ": f"{hyb_v1:+.3f}%" if hyb_v1 is not None else "—",
                        "統計意義": "樣本不足（<200）" if n < 200 else "需 CI 計算",
                    })
            if perf_rows:
                st.dataframe(pd.DataFrame(perf_rows), use_container_width=True, hide_index=True)
                if matured_20d < 200:
                    st.warning(
                        f"⚠️ 目前 OOS 20D 成熟樣本 ({matured_20d}) 不足 200，結果無統計意義。"
                        "需累積至少 200 個成熟 PROSPECTIVE 記錄（約 2027-06）。"
                    )

        # ── Recent run log ─────────────────────────────────────────────────────
        st.markdown("#### 最近執行記錄")
        runs = conn.execute(
            "SELECT trade_date, status, started_at, inserted_count, "
            "skipped_count, conflict_count, error_count, outcome_filled_count, error_summary "
            "FROM hybrid_forward_run_log ORDER BY started_at DESC LIMIT 10"
        ).fetchall()
        if runs:
            run_rows = []
            for r in runs:
                run_rows.append({
                    "日期": r[0],
                    "狀態": r[1],
                    "新增": r[3],
                    "略過": r[4],
                    "衝突": r[5],
                    "錯誤": r[6],
                    "結果回填": r[7],
                    "說明": r[8] or "",
                })
            st.dataframe(pd.DataFrame(run_rows), use_container_width=True, hide_index=True)
        else:
            st.info("尚無執行記錄。")

        # ── G4. Plain language explanations ───────────────────────────────────
        with st.expander("📖 名詞白話解釋"):
            st.markdown(
                "**PROSPECTIVE（前瞻）：** 在訊號發出當天就已保存的決策，不是事後重建。"
                "只有這類記錄才能作為策略驗證的依據。  \n\n"
                "**成熟（Matured）：** 決策已經經過指定交易日數（5/10/20D），可以計算結果。  \n\n"
                "**Paired Delta：** 同一批訊號使用不同策略，平均績效差多少。  \n\n"
                "**Conflict：** 同一訊號重跑時產生不同結果，需要檢查資料或規則。  \n\n"
                "**LATE_CAPTURE：** 訊號日期合規，但記錄是在事後才補存入的，可信度低於 PROSPECTIVE。  \n\n"
                "**RETROSPECTIVE_RECONSTRUCTION：** 規則凍結前的歷史訊號，不能視為 OOS 驗證。"
            )

    finally:
        conn.close()


def _render_hybrid_rule_reference() -> None:
    st.markdown("### 📋 Hybrid V1 規則說明")
    st.markdown(
        """
| 優先級 | 條件 | Hybrid 動作 | 說明 |
|--------|------|-------------|------|
| P1（最高） | Bear 市場 + WAIT_FOR_PULLBACK | WAIT_PULLBACK | 熊市中繼續等待，避免買入下跌途中 |
| P2 | Flat MA20 + WAIT_FOR_PULLBACK | WAIT_PULLBACK | 趨勢不明確時，回調進場更謹慎 |
| P3 | Bull 市場 + Rising MA20 | DIRECT_NEXT_OPEN | 動能明確，直接進場捕捉上漲 |
| P4（預設） | 其他所有情況 | DIRECT_NEXT_OPEN | 不符合 P1–P3 → 採 V1 立即進場 |
        """
    )
    st.markdown("#### 規則凍結資訊")
    st.code(
        "rule_version:   hybrid_v1\n"
        "frozen_at:      2026-11-05T00:00:00\n"
        "frozen_commit:  6602c3b\n"
    )
    st.markdown(
        "**市場狀態（Market Regime）定義：**\n\n"
        "- bull: 0050 收盤 > MA20 且 MA20 10-bar 斜率 > 0.3%\n"
        "- bear: 0050 收盤 < MA20 且 MA20 10-bar 斜率 < -0.3%\n"
        "- neutral: 其他\n\n"
        "**MA20 趨勢定義：**\n\n"
        "- rising: 10-bar MA20 斜率 > 0.3%\n"
        "- falling: 10-bar MA20 斜率 < -0.3%\n"
        "- flat: 介於兩者之間\n\n"
        "**重要：** WAIT_FOR_BREAKOUT 訊號一律直接進場（P4 預設）。"
        "規則僅對 WAIT_FOR_PULLBACK 訊號有效。"
    )
    st.caption(
        "來源：docs/hybrid_entry_v1_preregistration.md | "
        "研究基礎：docs/entry_timing_v2_effectiveness_analysis.md"
    )


def _render_known_limitations() -> None:
    st.markdown("### 已知限制與研究假設")
    st.markdown(
        '<div style="background:#fef2f2;border:2px solid #dc2626;'
        'border-radius:6px;padding:10px 14px;margin-bottom:16px">'
        '<span style="color:#dc2626;font-weight:700">RESEARCH ONLY — NOT A LIVE BUY SIGNAL</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    for i, lim in enumerate(_KNOWN_LIMITATIONS, 1):
        st.markdown(f"**{i}.** {lim}")

    st.markdown("---")
    st.markdown("#### 安全邊界（禁止觸碰）")
    st.markdown(
        "- MODEL_VERSION v8.0  \n"
        "- BUY / STRONG BUY 閾值  \n"
        "- foe_v1 計算邏輯  \n"
        "- 凍結的 ForwardSignal  \n"
        "- ACTUAL Trade Service 帳務  \n"
        "- PAPER Position Monitor  \n"
        "- Phase 1B Production Migration Workflow"
    )
    st.caption(
        "所有研究 Migration 與 Recalculation 僅能在隔離 PostgreSQL 或經批准的研究副本進行。"
    )
