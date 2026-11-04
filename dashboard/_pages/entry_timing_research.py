"""
pages/entry_timing_research.py — V2 Entry Timing Research UI (Shadow Mode)

SHADOW MODE ONLY: This page displays research output.
It does NOT feed into v8.0 BUY/STRONG_BUY decisions or ACTUAL/PAPER trades.
"""

from __future__ import annotations

import logging

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


def _label_badge(label: str) -> str:
    color = _LABEL_COLORS.get(label, "#6b7280")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.75rem;font-weight:600">{label}</span>'
    )


@st.cache_data(ttl=300)
def _load_v2_signals(limit: int = 300) -> list:
    try:
        from sqlalchemy import desc

        from src.database import get_session
        from src.research.models import V2ShadowSignal

        s = get_session()

        # Import ResearchBase tables into the same engine so they can be queried
        # (they may not exist yet — handle gracefully)
        from src.database import get_engine
        from src.research.models import ResearchBase

        engine = get_engine()
        ResearchBase.metadata.create_all(engine, checkfirst=True)

        rows = (
            s.query(V2ShadowSignal)
            .order_by(
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
                "v1_label": r.v1_decision_label or "—",
                "v1_pt_score": r.v1_pt_score,
                "entry_label": r.entry_label or "—",
                "dist_pct": r.dist_to_resistance_pct,
                "ma20_gap": r.ma20_gap_pct,
                "rr_ratio": r.rr_ratio,
                "vol_ratio": r.vol_ratio,
                "reasons": r.reasons_json or "",
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"V2 shadow signals load failed: {e}")
        return []


@st.cache_data(ttl=600)
def _load_comparison() -> dict:
    try:
        from src.research.backtest_comparison import compare_v1_v2

        return compare_v1_v2()
    except Exception as e:
        logger.warning(f"V2 comparison load failed: {e}")
        return {}


def page_entry_timing_research() -> None:
    st.markdown("## V2 進場時機研究（Shadow Mode）")
    st.markdown(
        '<div style="background:#fef3c7;border-left:4px solid #f59e0b;'
        'padding:8px 12px;border-radius:4px;font-size:0.8rem;margin-bottom:16px">'
        "⚠️ Shadow Mode：此頁為研究用途。V2 標籤不影響正式買賣決策、持倉或 ForwardSignal。"
        "</div>",
        unsafe_allow_html=True,
    )

    tab1, tab2 = st.tabs(["📋 V2 訊號列表", "📊 V1 vs V2 比較"])

    with tab1:
        _render_signal_list()

    with tab2:
        _render_comparison()


def _render_signal_list() -> None:
    rows = _load_v2_signals()
    if not rows:
        st.info(
            "尚無 V2 Shadow Signal 資料。請執行 EntryTimingResearchService.run_for_date() 產生資料。"
        )
        return

    # Summary counts by label
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

    # Filter
    all_labels = sorted(set(r["entry_label"] for r in rows))
    sel_labels = st.multiselect("篩選 V2 標籤", all_labels, default=all_labels)
    filtered = [r for r in rows if r["entry_label"] in sel_labels]

    import pandas as pd

    df = pd.DataFrame(filtered)
    if df.empty:
        st.caption("無符合條件的資料")
        return

    # Format display
    df_display = df[
        [
            "trade_date",
            "stock_id",
            "v1_label",
            "entry_label",
            "dist_pct",
            "ma20_gap",
            "rr_ratio",
            "vol_ratio",
        ]
    ].rename(
        columns={
            "trade_date": "日期",
            "stock_id": "股票",
            "v1_label": "V1 標籤",
            "entry_label": "V2 進場標籤",
            "dist_pct": "距壓力%",
            "ma20_gap": "MA20 乖離%",
            "rr_ratio": "R/R",
            "vol_ratio": "量比",
        }
    )

    def _fmt_float(x):
        if x is None:
            return "—"
        try:
            return f"{float(x):.1f}"
        except Exception:
            return "—"

    for col in ["距壓力%", "MA20 乖離%", "R/R", "量比"]:
        df_display[col] = df_display[col].apply(_fmt_float)

    st.dataframe(df_display, use_container_width=True, height=400)
    st.caption(f"共 {len(df_display)} 筆（最多顯示 300 筆）")


def _render_comparison() -> None:
    comp = _load_comparison()
    if not comp or comp.get("v1_count", 0) == 0:
        st.info("尚無足夠比較資料（需要有 fwd_return_20d 的 V2ShadowSignal）。")
        return

    st.markdown("### V1 全量 vs V2 ENTRY_READY 20日報酬比較")
    st.caption("⚠️ 此比較僅供研究：V2 尚未驗證，不代表真實績效提升。")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**V1（全部）**")
        st.metric("樣本數", comp.get("v1_count", "—"))
        st.metric("平均 20d 報酬", f"{comp.get('v1_mean_return_20d', '—')}%")
        st.metric("中位 20d 報酬", f"{comp.get('v1_median_return_20d', '—')}%")
        st.metric("勝率", f"{comp.get('v1_win_rate_20d', '—')}%")
    with c2:
        st.markdown("**V2（ENTRY_READY 子集）**")
        st.metric("樣本數", comp.get("v2_count", "—"))
        st.metric("平均 20d 報酬", f"{comp.get('v2_mean_return_20d', '—')}%")
        st.metric("中位 20d 報酬", f"{comp.get('v2_median_return_20d', '—')}%")
        st.metric("勝率", f"{comp.get('v2_win_rate_20d', '—')}%")

    rows = comp.get("rows", [])
    if rows:
        import pandas as pd

        df = pd.DataFrame(rows)
        df_show = df[
            [
                "trade_date",
                "stock_id",
                "v1_label",
                "v2_label",
                "fwd_return_20d",
                "rr_ratio",
            ]
        ].rename(
            columns={
                "trade_date": "日期",
                "stock_id": "股票",
                "v1_label": "V1",
                "v2_label": "V2",
                "fwd_return_20d": "20d%",
                "rr_ratio": "R/R",
            }
        )
        st.dataframe(df_show, use_container_width=True, height=300)
