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

    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 訊號列表",
        "📊 完整回測（FOS）",
        "🔬 有效性分析",
        "⚠️ 已知限制",
    ])

    with tab1:
        _render_signal_list(research_version)

    with tab2:
        _render_full_backtest(research_version)

    with tab3:
        _render_effectiveness_analysis()

    with tab4:
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
