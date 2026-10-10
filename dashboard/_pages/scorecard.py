"""
pages/scorecard.py — 模型成績單（Recommendation Audit Trail）

顯示每一個有 decision_label 的 ForwardSignal 記錄，以及事後回填的績效結果。
這是模型的「永久記錄」：當時網站說了什麼，之後實際發生了什麼。
"""

import logging

import streamlit as st

logger = logging.getLogger(__name__)

_LABEL_COLOR = {
    "BUY★":              "#1a7f4b",
    "BUY":               "#2ecc71",
    "WAIT FOR PULLBACK": "#f39c12",
    "WAIT":              "#95a5a6",
    "REDUCE":            "#e67e22",
    "SELL/AVOID":        "#e74c3c",
}

_OUTCOME_ICON = {
    "T1_HIT":         "🎯",
    "STOP_TRIGGERED": "🛑",
    "EXPIRED":        "⏱️",
}


def _outcome_color(outcome_note: str | None, alpha: float | None) -> str:
    if outcome_note == "T1_HIT":
        return "#1a7f4b"
    if outcome_note == "STOP_TRIGGERED":
        return "#e74c3c"
    if alpha is not None:
        return "#1a7f4b" if alpha > 0 else "#e74c3c"
    return "#666"


def _fmt(v, suffix="", places=1, plus=False):
    if v is None:
        return "—"
    fmt = f"{'+'if plus else ''}{v:.{places}f}{suffix}"
    return fmt


def _summary_stats(rows: list) -> dict:
    buy_rows = [r for r in rows if r["decision_label"] in ("BUY★", "BUY")]
    matured  = [r for r in buy_rows if r["alpha_20d"] is not None]
    if not matured:
        return {"n_buy": len(buy_rows), "matured": 0, "winrate": None, "avg_alpha": None, "t1_rate": None, "stop_rate": None}

    alphas = [r["alpha_20d"] for r in matured]
    winrate = round(sum(1 for a in alphas if a > 0) / len(alphas) * 100, 1)
    avg_alpha = round(sum(alphas) / len(alphas), 2)
    t1_rate = round(sum(1 for r in matured if r["outcome_note"] == "T1_HIT") / len(matured) * 100, 1)
    stop_rate = round(sum(1 for r in matured if r["outcome_note"] == "STOP_TRIGGERED") / len(matured) * 100, 1)
    return {
        "n_buy":     len(buy_rows),
        "matured":   len(matured),
        "winrate":   winrate,
        "avg_alpha": avg_alpha,
        "t1_rate":   t1_rate,
        "stop_rate": stop_rate,
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

    from dashboard.loaders import load_forward_signals_scorecard

    with st.spinner("讀取成績單資料..."):
        rows = load_forward_signals_scorecard(limit=300)

    if not rows:
        st.info("尚無成績單資料。每日執行後系統會自動凍結 Decision Center 信號。")
        return

    # ── 篩選控制 ──────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns(3)
    all_labels = sorted({r["decision_label"] for r in rows if r["decision_label"]})
    sel_labels = col_f1.multiselect("決策標籤", all_labels, default=["BUY★", "BUY"], key="sc_labels")
    all_setups = sorted({r["setup_type"] for r in rows if r["setup_type"]})
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
    st.markdown("---")
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    sc1.metric("BUY/BUY★ 信號", stats["n_buy"])
    sc2.metric("已成熟（20D）", stats["matured"])
    if stats["winrate"] is not None:
        sc3.metric("勝率（Alpha > 0）", f"{stats['winrate']}%")
        sc4.metric("平均 Alpha 20D", f"{stats['avg_alpha']:+.2f}%")
        sc5.metric("達 T1 率", f"{stats['t1_rate']}%")
    else:
        sc3.metric("勝率", "—")
        sc4.metric("平均 Alpha", "—")
        sc5.metric("達 T1 率", "—")
    st.markdown("---")

    if not filtered:
        st.info("目前篩選條件下無資料。")
        return

    # ── 逐筆展示 ──────────────────────────────────────────────
    for r in filtered:
        label = r["decision_label"] or "WAIT"
        lc = _LABEL_COLOR.get(label, "#666")
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
                        "T1_HIT":         "🎯 達到目標 T1",
                        "STOP_TRIGGERED": "🛑 觸及停損",
                        "EXPIRED":        "⏱️ 時間到期",
                    }.get(r["outcome_note"], r["outcome_note"])
                    st.markdown(f"結果：**{outcome_display}**")
                    if r["stop_triggered_day"]:
                        st.caption(f"停損觸發日：第 {r['stop_triggered_day']} 交易日")
                    if r["t1_hit_day"]:
                        st.caption(f"T1 達成日：第 {r['t1_hit_day']} 交易日")
                    st.markdown(
                        f"20D 報酬：{_fmt(ret_20, '%', plus=True)}  \n"
                        f"20D Alpha：{_fmt(alpha_20, '%', plus=True)}  \n"
                        f"60D 報酬：{_fmt(r['fwd_return_60d'], '%', plus=True)}  \n"
                        f"60D Alpha：{_fmt(r['alpha_60d'], '%', plus=True)}"
                    )
