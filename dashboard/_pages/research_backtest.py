"""
dashboard/_pages/research_backtest.py — Research Backtest & Forward Validation

🧪 Research / In-Sample  : analysis_results，date < RESEARCH_CUTOFF_DATE
🔒 Forward / Out-of-Sample: forward_signals，trade_date >= RESEARCH_CUTOFF_DATE

兩個資料集嚴格隔離，不得混用。
Forward 樣本尚未成熟時顯示「累積中」，不產生策略結論。
"""

import streamlit as st
import pandas as pd
import numpy as np


_CUTOFF_LABEL = "2026-10-09"


# ── 統計欄位格式化 ────────────────────────────────────────────

def _fmt_pct(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:+.2f}%"


def _fmt_p(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if v < 0.01:
        return "<0.01 **"
    if v < 0.05:
        return f"{v:.3f} *"
    return f"{v:.3f}"


def _fmt_d(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    tag = " (L)" if abs(v) >= 0.8 else " (M)" if abs(v) >= 0.5 else " (S)" if abs(v) >= 0.2 else ""
    return f"{v:+.2f}{tag}"


def _render_stats_table(df: pd.DataFrame, group_col: str) -> None:
    """顯示分組統計 DataFrame，格式化數值欄位。"""
    if df is None or df.empty:
        st.caption("無資料")
        return

    display = df.copy()

    for col in ["20D均Alpha%", "20D中位Alpha%", "20D CI低", "20D CI高",
                "20D Boot CI低", "20D Boot CI高",
                "60D均Alpha%", "60D中位Alpha%", "60D CI低", "60D CI高",
                "60D Boot CI低", "60D Boot CI高"]:
        if col in display.columns:
            display[col] = display[col].apply(_fmt_pct)

    for col in ["20D Std", "60D Std"]:
        if col in display.columns:
            display[col] = display[col].apply(
                lambda v: f"{v:.2f}" if v is not None and not (isinstance(v, float) and np.isnan(v)) else "—"
            )

    for col in ["20D p值", "60D p值"]:
        if col in display.columns:
            display[col] = display[col].apply(_fmt_p)

    for col in ["20D勝率%", "60D勝率%"]:
        if col in display.columns:
            display[col] = display[col].apply(
                lambda v: f"{v:.1f}%" if v is not None and not (isinstance(v, float) and np.isnan(v)) else "—"
            )

    for col in ["20D Cohen'd", "60D Cohen'd"]:
        if col in display.columns:
            display[col] = display[col].apply(_fmt_d)

    st.dataframe(display.set_index(group_col), use_container_width=True)
    st.caption(
        "p值 < 0.05（*）或 < 0.01（**）表示在 H₀: mean alpha=0 下有統計顯著性。"
        "Cohen's d：S ≥ 0.2，M ≥ 0.5，L ≥ 0.8。"
        "Boot CI = Bootstrap 95% 百分位 CI（2000 次重抽樣），"
        "與 t-test CI 大幅分歧時以 Boot CI 為準（分布有偏、厚尾時常見）。"
        "所有指標需合併判讀，**不能單獨下結論**。"
    )


# ── 主頁面 ────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner="計算 Research Backtest（首次約 30 秒）…")
def _load_research():
    import traceback
    try:
        from src.services.research_backtest_service import ResearchBacktestService
        return ResearchBacktestService().compute()
    except Exception as e:
        return {"_error": traceback.format_exc()}


def _load_forward():
    try:
        import os
        from pathlib import Path
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env", override=True)

        import psycopg
        url = os.getenv("NEON_URL") or os.getenv("DATABASE_URL") or ""
        if url.startswith("postgresql"):
            conn = psycopg.connect(url)
            cur = conn.cursor()
            cur.execute("""
                SELECT trade_date, stock_id, stock_name,
                       pt_score, setup_type, trade_signal,
                       ma20_gap, ma60_gap, ma60_slope, vol_ratio,
                       total_score, rec_level, model_version, locked_at
                FROM forward_signals
                ORDER BY trade_date DESC, stock_id
            """)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return pd.DataFrame(rows, columns=cols)
        else:
            from src.database import ForwardSignal, get_session
            from sqlalchemy import select
            sess = get_session()
            fs = sess.execute(
                select(ForwardSignal).order_by(
                    ForwardSignal.trade_date.desc(), ForwardSignal.stock_id
                )
            ).scalars().all()
            sess.close()
            return pd.DataFrame([{
                "trade_date":    r.trade_date,
                "stock_id":      r.stock_id,
                "stock_name":    r.stock_name,
                "pt_score":      r.pt_score,
                "setup_type":    r.setup_type,
                "trade_signal":  r.trade_signal,
                "ma20_gap":      r.ma20_gap,
                "ma60_gap":      r.ma60_gap,
                "ma60_slope":    r.ma60_slope,
                "vol_ratio":     r.vol_ratio,
                "total_score":   r.total_score,
                "rec_level":     r.rec_level,
                "model_version": r.model_version,
                "locked_at":     r.locked_at,
            } for r in fs])
    except Exception as e:
        return pd.DataFrame()


def page_research_backtest() -> None:
    st.markdown(
        '<div class="section-title">🧪 Research Backtest & Forward Validation</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"**Research cutoff（固定）：{_CUTOFF_LABEL}**　"
        "🧪 In-Sample = cutoff 前　🔒 Out-of-Sample = cutoff 後"
    )
    st.info(
        "**研究架構說明**\n\n"
        "- 🧪 **Research / In-Sample**：以歷史 candidates 回測，用於產生假說（hypothesis generation）\n"
        "- 🔒 **Forward / Out-of-Sample**：cutoff 後每日凍結 signal，用於驗證假說（hypothesis testing）\n"
        "- 兩組資料**絕對不混用**。Research 結論不得直接套用至 Forward，反之亦然。\n"
        "- Forward 樣本未達 20 個 completed observation 前，不產生策略結論。"
    )

    tab_r, tab_f = st.tabs(["🧪 Research / In-Sample", "🔒 Forward / Out-of-Sample"])

    # ── 🧪 Research ──────────────────────────────────────────
    with tab_r:
        res = _load_research()
        if not res:
            st.error("Research Backtest 計算失敗（空結果）。請點側欄「🔄 重新整理資料」再試。")
            return
        if "_error" in res:
            st.error("Research Backtest 計算失敗，詳細錯誤如下：")
            st.code(res["_error"], language="python")
            st.info("請點側欄「🔄 重新整理資料」清除快取後再試。")
            return

        n_total = res.get("n_total_candidates", 0)
        n_usable = res.get("n_usable", 0)
        raw_df = res.get("raw_df", pd.DataFrame())

        # 摘要指標
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Candidates（cutoff 前）", f"{n_total:,}")
        c2.metric("有 20D Return", f"{n_usable:,}")
        if not raw_df.empty:
            n_dates = raw_df["date"].nunique()
            date_min = raw_df["date"].min()
            date_max = raw_df["date"].max()
            c3.metric("日期數", f"{n_dates}")
            c4.metric("日期範圍", f"{date_min} ~ {date_max}")

        if raw_df.empty:
            st.info("無可用資料。")
            return

        st.divider()

        # ── 樣本獨立性診斷 ────────────────────────────────────
        si = res.get("sample_independence")
        if si:
            st.markdown("#### 樣本獨立性診斷")
            st.caption(
                "每日相同股票的信號前向報酬高度重疊（例如台積電連續 10 天都出現），"
                "t-test 會把它們當成獨立樣本，造成 n 虛高、CI 虛窄、p-value 虛美。"
                "以下對比原始樣本與「去重後」（同股 ≥ N 個交易日才取一次）的整體統計差異。"
            )

            si_rows = []
            for label, ver in [
                ("Raw（全部）", "raw"),
                ("Dedup 20D（同股 ≥ 20 交易日一次）", "dedup_20"),
                ("Dedup 60D（同股 ≥ 60 交易日一次）", "dedup_60"),
            ]:
                v   = si[ver]
                s20 = v["stats_20d"]
                s60 = v["stats_60d"]
                ci20 = (
                    f"[{s20['ci_low']:+.2f}%, {s20['ci_high']:+.2f}%]"
                    if s20.get("ci_low") is not None else "—"
                )
                ci60 = (
                    f"[{s60['ci_low']:+.2f}%, {s60['ci_high']:+.2f}%]"
                    if s60.get("ci_low") is not None else "—"
                )
                boot20 = (
                    f"[{s20['boot_ci_low']:+.2f}%, {s20['boot_ci_high']:+.2f}%]"
                    if s20.get("boot_ci_low") is not None else "—"
                )
                boot60 = (
                    f"[{s60['boot_ci_low']:+.2f}%, {s60['boot_ci_high']:+.2f}%]"
                    if s60.get("boot_ci_low") is not None else "—"
                )
                si_rows.append({
                    "版本":          label,
                    "n":             v["n"],
                    "20D均Alpha":    _fmt_pct(s20.get("mean")),
                    "20D p值":       _fmt_p(s20.get("p_value")),
                    "20D t CI":      ci20,
                    "20D Boot CI":   boot20,
                    "20D Cohen'd":   _fmt_d(s20.get("cohens_d")),
                    "60D均Alpha":    _fmt_pct(s60.get("mean")),
                    "60D p值":       _fmt_p(s60.get("p_value")),
                    "60D t CI":      ci60,
                    "60D Boot CI":   boot60,
                    "60D Cohen'd":   _fmt_d(s60.get("cohens_d")),
                })

            st.dataframe(
                pd.DataFrame(si_rows).set_index("版本"),
                use_container_width=True,
            )
            st.caption(
                "⚠️ 若 p 值在去重後從顯著變為不顯著（例如 0.02 → 0.18），"
                "表示原始顯著性很可能主要來自重複樣本，**非真實策略優勢**。"
                "去重後 n 大幅縮水且 CI 跨越 0 則結論應保守。"
            )

        st.divider()

        # PT Score Coverage
        n_with_pt    = res.get("n_with_pt", 0)
        n_without_pt = res.get("n_without_pt", 0)
        pt_cov       = res.get("pt_coverage_pct", 0.0)
        pt_total     = n_with_pt + n_without_pt

        st.markdown("#### PT Score 分組 — 主要假說")
        st.info(
            "**資料完整性說明**\n\n"
            "歷史 `analysis_results` 建立時尚未保存 Price Trend Score，"
            "因此部分歷史資料無法進行可靠的 PT bucket 分析。"
            "本分析**僅使用實際保存的 Price Trend Score**，不使用估算或回填值。"
            "NULL 值不會被歸入任何 bucket（包含 `<40`）。"
        )

        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("Research 樣本總數", f"{pt_total:,}")
        pc2.metric("有 PT Score", f"{n_with_pt:,}")
        pc3.metric("無 PT Score（NULL）", f"{n_without_pt:,}")
        pc4.metric("PT Coverage", f"{pt_cov:.1f}%")

        if pt_cov < 5.0:
            st.warning(
                f"⏳ **PT Score Coverage 過低（{n_with_pt} / {pt_total}，{pt_cov:.1f}%）**\n\n"
                "目前歷史資料中 Price Trend Score 尚未累積足夠，PT bucket 分析暫時無法提供有效結論。\n"
                "cutoff（2026-10-09）後每日執行 main.py 可逐步累積真實 PT Score。"
            )
        else:
            st.caption(
                f"假說：PT ≥ 60 的股票，未來 20D/60D Alpha 是否顯著優於 PT < 60？"
                f"（僅含有真實 PT Score 的 {n_with_pt:,} 筆）"
            )
            _render_stats_table(res.get("by_pt_bucket"), "pt_bucket")

        st.divider()

        # Setup Type
        st.markdown("#### Setup Type 分組")
        _render_stats_table(res.get("by_setup"), "setup_type")

        st.divider()

        # MA20 Deviation
        st.markdown("#### MA20 偏離度分組")
        _render_stats_table(res.get("by_ma20"), "ma20_bracket")

        st.divider()

        # MA60 Distance
        st.markdown("#### MA60 距離分組")
        st.caption("MA60 gap = (close − MA60) / MA60 × 100%，僅含有足夠歷史 MA60 資料者")
        _render_stats_table(res.get("by_ma60"), "ma60_bracket")

        st.divider()

        # Market Regime
        st.markdown("#### 市場 Regime 分組")
        st.caption(
            "Bull = 0050 > MA60 且 MA60 slope 向上；"
            "Bear = 0050 < MA60 且 MA60 slope 向下；"
            "Neutral = 其他（slope flat 或位置與趨勢方向不一致的過渡期）"
        )
        _render_stats_table(res.get("by_regime"), "regime")

        st.divider()

        # Monthly
        st.markdown("#### 月份分組（市場環境切片）")
        st.caption("樣本集中在少數月份時，月份結論不可靠。")
        _render_stats_table(res.get("by_month"), "ym")

        st.divider()

        # Raw data expander
        with st.expander("📋 展開原始資料（含所有欄位）"):
            show_cols = [
                "date", "stock_id", "pt_score", "setup_type", "trade_signal",
                "ma20_gap", "ma60_gap", "vol_ratio", "total_score",
                "ret_20d", "ret_60d", "alpha_20d", "alpha_60d",
                "regime", "ym",
            ]
            st.dataframe(
                raw_df[[c for c in show_cols if c in raw_df.columns]],
                use_container_width=True,
            )

    # ── 🔒 Forward ────────────────────────────────────────────
    with tab_f:
        st.markdown(f"**Out-of-Sample 邊界（固定）：{_CUTOFF_LABEL}**")
        st.caption(
            "此頁資料來自 `forward_signals` 表，每日 main.py 結束後自動凍結。"
            "signal 一旦寫入即不可修改，演算法改版也不回頭重算。"
        )

        fwd_df = _load_forward()

        if fwd_df.empty:
            st.info("🔒 Forward signal 尚未累積，請等待每日 main.py 執行後自動寫入。")
            return

        n_fwd = len(fwd_df)
        n_fwd_dates = fwd_df["trade_date"].nunique() if "trade_date" in fwd_df.columns else 0

        fa, fb, fc = st.columns(3)
        fa.metric("Forward Signal 總筆數", f"{n_fwd:,}")
        fb.metric("交易日數", f"{n_fwd_dates}")
        fc.metric("最新日期", str(fwd_df["trade_date"].max()) if "trade_date" in fwd_df.columns else "—")

        # 判斷是否有足夠成熟的 observation（20 個交易日後才能計算 20D return）
        from datetime import date, timedelta
        today = date.today()
        mature_dates = (
            fwd_df["trade_date"]
            .apply(lambda d: (today - d).days >= 28 if hasattr(d, "day") else False)
            if "trade_date" in fwd_df.columns
            else pd.Series([], dtype=bool)
        )
        n_mature = int(mature_dates.sum())

        if n_mature < 20:
            st.warning(
                f"⏳ **累積中** — 目前有 {n_mature} 筆已達 20D 成熟期（需 ≥ 20 筆才開始評估）。\n\n"
                "Forward Validation 需要足夠的完整 observation 才能產生有意義的統計結論，"
                "請繼續執行每日 main.py 自動累積。"
            )
        else:
            st.success(f"✅ 已有 {n_mature} 筆成熟 observation，可開始計算 Forward Alpha。")
            st.caption("Forward 統計計算功能將在此後版本啟用。")

        st.divider()

        # 顯示目前已凍結的 signals
        st.markdown("#### 已凍結 Forward Signals")
        show_fwd_cols = [
            "trade_date", "stock_id", "stock_name",
            "candidate_rank", "rec_level", "confidence",
            "close_at_signal", "market_regime_at_signal",
            "pt_score", "setup_type", "trade_signal",
            "ma20_gap", "ma60_gap", "vol_ratio",
            "total_score", "industry", "model_version",
        ]
        st.dataframe(
            fwd_df[[c for c in show_fwd_cols if c in fwd_df.columns]],
            use_container_width=True,
        )
