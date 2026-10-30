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


def _credibility_badge(n_dedup: int, p_value, pass_threshold: float = 0.05) -> tuple:
    """Return (emoji, label, color) based on sample size and significance."""
    if n_dedup < 20:
        return "⏳", "樣本不足", "#ff8800"
    if n_dedup < 50:
        if p_value is None or p_value >= pass_threshold:
            return "🟡", "初步", "#ffb300"
        return "🟡", "初步顯著", "#ffb300"
    if p_value is None or p_value >= pass_threshold:
        return "🔵", "樣本足夠，尚不顯著", "#5c6bc0"
    return "🟢", "顯著", "#2e7d32"


def _overall_stats(si: dict | None, key: str = "dedup_20") -> dict:
    """Extract overall 20D/60D stats from sample_independence[key]."""
    empty = {"n": 0, "mean": None, "win_rate": None, "p_value": None,
             "ci_low": None, "ci_high": None, "cohens_d": None,
             "boot_ci_low": None, "boot_ci_high": None}
    if not si or key not in si:
        return {"n": 0, "stats_20d": empty, "stats_60d": empty}
    return si[key]


def page_research_backtest() -> None:
    # ── 頁面標題與目的說明 ─────────────────────────────────────
    st.html("""
<div style="margin-bottom:16px">
  <div style="font-size:1.25rem;font-weight:800;color:#1a1a2e;margin-bottom:8px">
    🧪 研究回測 &amp; 前瞻驗證（Research Backtest &amp; Forward Validation）
  </div>
  <div style="font-size:0.83rem;color:#37474f;line-height:1.75;background:#f0f4ff;
              border-left:4px solid #667eea;padding:11px 15px;border-radius:0 8px 8px 0">
    這個頁面用來回答：<b>系統過去挑出的股票，後來表現如何？是否比 0050 更好？研究結果是否有足夠證據支持？</b><br>
    頁面分為兩個區塊：
    <ul style="margin:6px 0 0 0;padding-left:18px">
      <li><b>歷史研究（Research / In-Sample）</b>：用 2026-10-09 之前的歷史資料，回測候選股票後來的表現，
          用於形成研究假說。</li>
      <li><b>未來驗證（Forward / Out-of-Sample）</b>：2026-10-09 之後每日凍結訊號，
          驗證假說是否在未曾見過的資料上仍然成立。兩組資料絕對不混用。</li>
    </ul>
    <span style="font-size:0.78rem;color:#78909c">
      Alpha = 超額報酬 = 股票報酬 − 0050 同期報酬，正值代表跑贏大盤指數。
    </span>
  </div>
</div>""")

    tab_r, tab_f = st.tabs([
        "🧪 歷史研究（Research / In-Sample）",
        "🔒 未來驗證（Forward / Out-of-Sample）",
    ])

    # ── 🧪 歷史研究（Research / In-Sample）──────────────────────
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

        n_total    = res.get("n_total_candidates", 0)
        n_usable   = res.get("n_usable", 0)
        n_dedup_20 = res.get("n_dedup_20", 0)
        n_dedup_60 = res.get("n_dedup_60", 0)
        raw_df     = res.get("raw_df", pd.DataFrame())
        si         = res.get("sample_independence") or {}

        if raw_df.empty:
            st.info("無可用資料。請確認 cutoff 前有 analysis_results 記錄。")
            return

        date_min = raw_df["date"].min() if not raw_df.empty else None
        date_max = raw_df["date"].max() if not raw_df.empty else None
        n_dates  = raw_df["date"].nunique() if not raw_df.empty else 0

        # ── A. 研究目前進度與可信度 ──────────────────────────
        st.markdown("### A. 研究目前進度與可信度")

        overall = _overall_stats(si, "dedup_20")
        s20     = overall.get("stats_20d", {})
        s60     = overall.get("stats_60d", {})
        p20     = s20.get("p_value")
        p60     = s60.get("p_value")

        _badge20_icon, _badge20_lbl, _badge20_col = _credibility_badge(n_dedup_20, p20)
        _badge60_icon, _badge60_lbl, _badge60_col = _credibility_badge(n_dedup_60, p60)

        # Credibility status cards
        _dedup20_str = f"{n_dedup_20:,}" if isinstance(n_dedup_20, int) else "—"
        _dedup60_str = f"{n_dedup_60:,}" if isinstance(n_dedup_60, int) else "—"
        _date_str = (
            f"{str(date_min)[:10]} ～ {str(date_max)[:10]}"
            if date_min is not None else "—"
        )
        st.html(f"""
<style>
@media (max-width: 640px) {{
  .cred-grid {{ grid-template-columns: 1fr !important; }}
}}
</style>
<div class="cred-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:8px 0 16px">
  <div style="background:#f8f9fa;border-radius:10px;padding:14px 16px;border-left:4px solid #667eea">
    <div style="font-size:0.7rem;font-weight:700;color:#78909c;letter-spacing:.05em;margin-bottom:6px">
      🧪 歷史研究（Research / In-Sample）
    </div>
    <div style="font-size:0.83rem;color:#37474f;line-height:1.7">
      分析日期：<b>{_date_str}</b><br>
      有效樣本（20D 去重）：<b>{_dedup20_str} 筆</b>
      <span style="color:{_badge20_col};font-weight:700">{_badge20_icon} {_badge20_lbl}</span><br>
      有效樣本（60D 去重）：<b>{_dedup60_str} 筆</b>
      <span style="color:{_badge60_col};font-weight:700">{_badge60_icon} {_badge60_lbl}</span>
    </div>
  </div>
  <div style="background:#f8f9fa;border-radius:10px;padding:14px 16px;border-left:4px solid #b0bec5">
    <div style="font-size:0.7rem;font-weight:700;color:#78909c;letter-spacing:.05em;margin-bottom:6px">
      📌 哪些結論目前可以參考？
    </div>
    <div style="font-size:0.83rem;color:#37474f;line-height:1.7">
      {'✅ 20D Alpha 顯著（p &lt; 0.05），可用於形成假說' if (p20 is not None and p20 < 0.05) else '⚠️ 20D Alpha 尚未達統計顯著（p ≥ 0.05）'}<br>
      {'✅ 60D Alpha 顯著（p &lt; 0.05），可用於形成假說' if (p60 is not None and p60 < 0.05) else '⚠️ 60D Alpha 尚未達統計顯著（p ≥ 0.05）'}<br>
      <span style="font-size:0.76rem;color:#90a4ae">
        Research 結論僅用於假說形成，需 Forward 驗證才能確認。
      </span>
    </div>
  </div>
</div>""")

        # 不能成立的結論警告
        _insufficient = n_dedup_20 < 30
        if _insufficient:
            st.warning(
                f"⚠️ **目前去重樣本（{n_dedup_20} 筆）偏少，不能判定策略是否有效。**  \n"
                "候選訊號很多，不代表有同樣多次獨立交易。去重後才是真正可評估策略的樣本。"
            )
        elif p20 is None or p20 >= 0.05:
            st.info(
                "📊 **樣本足夠，但 20D Alpha 尚不顯著（p ≥ 0.05）。**  \n"
                "目前證據不足，不能判定策略有效。這不等於策略無效，只是還需要更多資料。"
            )

        st.divider()

        # ── B. 策略績效摘要 ──────────────────────────────────
        st.markdown("### B. 整體策略績效摘要")
        st.caption(
            f"基於 20D 去重樣本（{_dedup20_str} 筆）整體計算。"
            "Alpha = 超額報酬 = 股票報酬 − 0050 同期報酬。去重確保每檔股票每 20 個交易日最多計入一次。"
        )

        _mean20  = s20.get("mean")
        _wr20    = s20.get("win_rate")
        _p20     = s20.get("p_value")
        _d20     = s20.get("cohens_d")
        _mean60  = s60.get("mean")
        _wr60    = s60.get("win_rate")
        _p60     = s60.get("p_value")

        def _color_alpha(v):
            if v is None: return "#888"
            return "#2e7d32" if v > 0 else "#c62828"

        st.html(f"""
<style>
@media (max-width: 640px) {{
  .perf-grid {{ grid-template-columns: 1fr 1fr !important; }}
}}
</style>
<div class="perf-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:8px 0 4px">
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px;text-align:center">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">20日超額報酬（Alpha）</div>
    <div style="font-size:1.1rem;font-weight:800;color:{_color_alpha(_mean20)};white-space:normal;word-break:break-word">
      {_fmt_pct(_mean20)}
    </div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:3px">均值 · 去重 20D</div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px;text-align:center">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">20日勝率</div>
    <div style="font-size:1.1rem;font-weight:800;color:#1a1a2e">
      {f"{_wr20:.1f}%" if _wr20 is not None else "—"}
    </div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:3px">Alpha &gt; 0 的比例</div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px;text-align:center">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">60日超額報酬（Alpha）</div>
    <div style="font-size:1.1rem;font-weight:800;color:{_color_alpha(_mean60)};white-space:normal;word-break:break-word">
      {_fmt_pct(_mean60)}
    </div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:3px">均值 · 去重 60D</div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px;text-align:center">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">60日勝率</div>
    <div style="font-size:1.1rem;font-weight:800;color:#1a1a2e">
      {f"{_wr60:.1f}%" if _wr60 is not None else "—"}
    </div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:3px">Alpha &gt; 0 的比例</div>
  </div>
</div>""")

        # 績效白話說明
        _p_note = ""
        if _p20 is not None:
            if _p20 < 0.01:
                _p_note = f"p={_p20:.3f}（< 0.01），統計上高度顯著。"
            elif _p20 < 0.05:
                _p_note = f"p={_p20:.3f}（< 0.05），統計上顯著。"
            else:
                _p_note = f"p={_p20:.3f}（≥ 0.05），尚不顯著。"
        _d_note = f"效應量 Cohen's d = {_fmt_d(_d20)}（S≥0.2 小、M≥0.5 中、L≥0.8 大）。" if _d20 else ""
        if _p_note or _d_note:
            st.caption(f"📊 {_p_note} {_d_note}")

        if not _insufficient:
            _alpha_sign = "正" if (_mean20 is not None and _mean20 > 0) else "負"
            if _p20 is not None and _p20 < 0.05:
                st.caption(
                    f"✅ 這代表什麼？去重後 {n_dedup_20} 個獨立樣本中，"
                    f"平均超額報酬為 {_fmt_pct(_mean20)}，統計上顯著（{_p_note}）。"
                    "這是 Research 阶段的假說支持，**仍需 Forward 驗證才算確認**。"
                )
            else:
                st.caption(
                    f"📊 這代表什麼？去重後 {n_dedup_20} 個獨立樣本，"
                    f"平均 20D 超額報酬為 {_fmt_pct(_mean20)}，但{_p_note}"
                    "樣本數或效應量尚不足以得出穩健結論。"
                )

        st.divider()

        # ── C. 研究資料量 ─────────────────────────────────────
        st.markdown("### C. 研究資料量")

        _date_min_str = str(date_min)[:10].replace("-", "/") if date_min is not None else "—"
        _date_max_str = str(date_max)[:10].replace("-", "/") if date_max is not None else "—"

        st.html(f"""
<style>
@media (max-width: 640px) {{
  .data-grid {{ grid-template-columns: 1fr 1fr !important; }}
}}
</style>
<div class="data-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:8px 0">
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">
      歷史候選訊號<br><span style="font-weight:400">(Candidates)</span>
    </div>
    <div style="font-size:1.05rem;font-weight:800;color:#1a1a2e">{n_total:,}</div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:2px">cutoff 前所有出現的股票記錄</div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">
      有後續報酬資料<br><span style="font-weight:400">(Raw N)</span>
    </div>
    <div style="font-size:1.05rem;font-weight:800;color:#1a1a2e">{n_usable:,}</div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:2px">含重疊，不可直接用於統計</div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">
      涵蓋交易日數
    </div>
    <div style="font-size:1.05rem;font-weight:800;color:#1a1a2e">{n_dates}</div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:2px">有候選記錄的不重複日期數</div>
  </div>
</div>
<div class="data-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:8px 0 4px">
  <div style="background:#e8f5e9;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.7rem;color:#388e3c;font-weight:600;margin-bottom:4px">
      20日去重樣本<br><span style="font-weight:400">(20D Dedup N)</span>
    </div>
    <div style="font-size:1.05rem;font-weight:800;color:#1a1a2e">{n_dedup_20:,}</div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:2px">同股 ≥ 20 交易日才計入一次</div>
  </div>
  <div style="background:#e8f5e9;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.7rem;color:#388e3c;font-weight:600;margin-bottom:4px">
      60日去重樣本<br><span style="font-weight:400">(60D Dedup N)</span>
    </div>
    <div style="font-size:1.05rem;font-weight:800;color:#1a1a2e">{n_dedup_60:,}</div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:2px">同股 ≥ 60 交易日才計入一次</div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">起始日期</div>
    <div style="font-size:1.05rem;font-weight:800;color:#1a1a2e;white-space:normal;word-break:break-word">
      {_date_min_str}
    </div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:2px">最早的候選訊號日</div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">結束日期</div>
    <div style="font-size:1.05rem;font-weight:800;color:#1a1a2e;white-space:normal;word-break:break-word">
      {_date_max_str}
    </div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:2px">cutoff 前最後一個候選日</div>
  </div>
</div>""")

        st.caption(
            "💡 這代表什麼？候選訊號很多，不代表有同樣多次獨立交易。"
            "同一檔股票每天都出現等於重複計入，去重後的樣本才是更真實的獨立觀察次數。"
        )

        st.divider()

        # ── D. 進階研究診斷 ──────────────────────────────────
        st.markdown("### D. 進階研究診斷")
        st.caption(
            "以下所有分組統計：20D 欄位基於 **20D 去重樣本（20D Dedup）**，"
            "60D 欄位基於 **60D 去重樣本（60D Dedup）**。各組的 n 為該組在 20D Dedup 樣本中的筆數。"
        )

        # 樣本獨立性診斷
        with st.expander("🔬 樣本獨立性診斷（Sample Independence）", expanded=False):
            st.caption(
                "同一檔股票連續多日出現（例如台積電連續 10 天都在名單上），"
                "未去重時 t-test 會把它們當成獨立樣本，造成 n 虛高、信賴區間虛窄、p 值虛低。"
                "下表對比三種版本的統計差異。"
            )
            if si:
                si_rows = []
                for label, ver in [
                    ("原始（Raw，含重疊）", "raw"),
                    ("20日去重（Dedup 20D）", "dedup_20"),
                    ("60日去重（Dedup 60D）", "dedup_60"),
                ]:
                    v   = si.get(ver, {})
                    s20 = v.get("stats_20d", {})
                    s60 = v.get("stats_60d", {})
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
                        "版本":           label,
                        "n":              v.get("n", 0),
                        "20D均Alpha":     _fmt_pct(s20.get("mean")),
                        "20D p值":        _fmt_p(s20.get("p_value")),
                        "20D t CI":       ci20,
                        "20D Boot CI":    boot20,
                        "20D Cohen'd":    _fmt_d(s20.get("cohens_d")),
                        "60D均Alpha":     _fmt_pct(s60.get("mean")),
                        "60D p值":        _fmt_p(s60.get("p_value")),
                        "60D t CI":       ci60,
                        "60D Boot CI":    boot60,
                        "60D Cohen'd":    _fmt_d(s60.get("cohens_d")),
                    })
                st.dataframe(
                    pd.DataFrame(si_rows).set_index("版本"),
                    use_container_width=True,
                )
                st.caption(
                    "⚠️ 若 p 值在去重後從顯著（如 0.02）變為不顯著（如 0.18），"
                    "表示原始顯著性主要來自重複樣本，**非真實策略優勢**。"
                    "去重後 n 大幅縮水且信賴區間跨越 0 則結論應保守。"
                    "Bootstrap CI（2000次重抽樣）與 t-test CI 大幅分歧時以 Bootstrap 為準。"
                )

        # PT Score 分組
        n_with_pt    = res.get("n_with_pt", 0)
        n_without_pt = res.get("n_without_pt", 0)
        pt_cov       = res.get("pt_coverage_pct", 0.0)
        pt_total     = n_with_pt + n_without_pt

        with st.expander(f"📊 PT 分數分組 (PT Score Buckets) — 主要假說 · Coverage {pt_cov:.1f}%",
                         expanded=pt_cov >= 5.0):
            st.caption(
                "假說：Price Trend Score（PT Score）越高的股票，未來報酬是否越好？  \n"
                "PT ≥ 60 = 技術型態偏強；PT < 60 = 型態偏弱或無明顯方向。"
            )
            if pt_cov < 5.0:
                st.warning(
                    f"⏳ **PT Score 覆蓋率過低（{n_with_pt} / {pt_total}，{pt_cov:.1f}%）**  \n"
                    "歷史資料建立時尚未保存 Price Trend Score，PT 分組目前無法提供有效結論。  \n"
                    "cutoff（2026-10-09）後每日執行可逐步累積真實 PT Score。"
                )
            else:
                st.caption(f"僅含有真實 PT Score 的 {n_with_pt:,} 筆（NULL 不歸入任何 bucket）。")
                _render_stats_table(res.get("by_pt_bucket"), "pt_bucket")

        # Setup Type 分組
        with st.expander("📐 型態分組（Setup Type）", expanded=False):
            st.caption(
                "breakout = 股價突破前 20 日高點；near_breakout = 接近壓力位；"
                "pullback_buy / pullback_hold = 回踩支撐；trending = 趨勢延伸。  \n"
                "假說：哪種型態在去重後的 Alpha 最穩定？"
            )
            _render_stats_table(res.get("by_setup"), "setup_type")

        # MA20 偏離
        with st.expander("📉 MA20 月線乖離分組（MA20 Deviation）", expanded=False):
            st.caption(
                "MA20 gap = (收盤 − MA20) / MA20 × 100%。  \n"
                "正值 = 股價高於月線（可能追高）；負值 = 低於月線（可能弱勢）。  \n"
                "假說：乖離程度是否影響後續 Alpha？"
            )
            _render_stats_table(res.get("by_ma20"), "ma20_bracket")

        # MA60 距離
        with st.expander("📉 MA60 季線距離分組（MA60 Distance）", expanded=False):
            st.caption(
                "MA60 gap = (close − MA60) / MA60 × 100%，僅含有足夠歷史 MA60 資料者。"
            )
            _render_stats_table(res.get("by_ma60"), "ma60_bracket")

        # Market Regime
        with st.expander("🌏 市場環境分組（Market Regime）", expanded=False):
            st.caption(
                "Bull = 0050 在 MA60 上方且 MA60 斜率向上（多頭市場）；"
                "Bear = 0050 在 MA60 下方且斜率向下（空頭市場）；"
                "Neutral = 其他過渡期。  \n"
                "假說：市場環境是否影響策略表現？"
            )
            _render_stats_table(res.get("by_regime"), "regime")

        # Monthly
        with st.expander("📅 月份分組（Month Slice）", expanded=False):
            st.caption(
                "樣本集中在少數月份時，月份結論不可靠。  \n"
                "用途：確認樣本是否均勻分布在不同時期，防止特定市場環境主導結果。"
            )
            _render_stats_table(res.get("by_month"), "ym")

        # Raw data
        with st.expander("📋 原始資料（含所有欄位）", expanded=False):
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

    # ── 🔒 未來驗證（Forward / Out-of-Sample）────────────────────
    with tab_f:
        st.html(f"""
<div style="background:#f8f9fa;border-left:4px solid #546e7a;padding:11px 15px;
            border-radius:0 8px 8px 0;margin-bottom:14px;font-size:0.83rem;color:#37474f;line-height:1.7">
  <b>未來驗證（Forward Validation）</b> 是什麼？<br>
  在 <b>{_CUTOFF_LABEL}</b> 這個固定時間點之後，每天收盤後系統自動把當天挑出的股票「凍結」記錄下來。
  這些記錄就是 Forward Signal。<br>
  等股票出現後 20 天（或 60 天），才可以計算實際報酬，與 0050 比較超額報酬（Alpha）。<br>
  <span style="color:#90a4ae;font-size:0.78rem">Signal 一旦凍結不可修改，保證驗證結果的客觀性。</span>
</div>""")

        fwd_df = _load_forward()

        if fwd_df.empty:
            st.info("🔒 Forward signal 尚未累積，請等待每日 main.py 執行後自動寫入。")
            return

        n_fwd = len(fwd_df)
        n_fwd_dates = fwd_df["trade_date"].nunique() if "trade_date" in fwd_df.columns else 0

        from datetime import date as _date_cls
        _today = _date_cls.today()
        mature_dates = (
            fwd_df["trade_date"]
            .apply(lambda d: (_today - d).days >= 28 if hasattr(d, "day") else False)
            if "trade_date" in fwd_df.columns
            else pd.Series([], dtype=bool)
        )
        n_mature = int(mature_dates.sum())

        _fwd_date_max = str(fwd_df["trade_date"].max())[:10].replace("-", "/") if "trade_date" in fwd_df.columns else "—"
        _fwd_date_min = str(fwd_df["trade_date"].min())[:10].replace("-", "/") if "trade_date" in fwd_df.columns else "—"

        st.html(f"""
<style>
@media (max-width: 640px) {{
  .fwd-grid {{ grid-template-columns: 1fr 1fr !important; }}
}}
</style>
<div class="fwd-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:8px 0 14px">
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">已凍結訊號筆數</div>
    <div style="font-size:1.05rem;font-weight:800;color:#1a1a2e">{n_fwd:,}</div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">涵蓋交易日數</div>
    <div style="font-size:1.05rem;font-weight:800;color:#1a1a2e">{n_fwd_dates}</div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">最新日期</div>
    <div style="font-size:1.05rem;font-weight:800;color:#1a1a2e;white-space:normal;word-break:break-word">
      {_fwd_date_max}
    </div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">已達 20D 成熟期</div>
    <div style="font-size:1.05rem;font-weight:800;color:#{'2e7d32' if n_mature >= 20 else 'ff8800'}">
      {n_mature} 筆
    </div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:2px">需 ≥ 20 筆才開始評估</div>
  </div>
</div>""")

        if n_mature < 20:
            st.warning(
                f"⏳ **累積中** — 目前有 {n_mature} 筆已達 20D 成熟期（需 ≥ 20 筆）。  \n"
                "這代表什麼？Forward Validation 需要足夠的已完成觀察，"
                "才能計算有意義的統計結果。目前尚不能對策略做出驗證結論，請繼續每日執行分析。"
            )
        else:
            st.success(f"✅ 已有 {n_mature} 筆成熟 observation（>= 20D），可開始計算 Forward Alpha。")
            st.caption("Forward 統計計算功能將在此後版本啟用。")

        st.divider()

        with st.expander("📋 已凍結 Forward Signals 明細", expanded=False):
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
