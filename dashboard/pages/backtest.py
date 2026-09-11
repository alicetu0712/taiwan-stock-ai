"""
pages/backtest.py — 模型驗證頁（回測 + Monte Carlo 隨機基準 + Alpha 分析）

業務邏輯委託 src.services.BacktestService；此模組只負責 Streamlit 快取與 UI。
"""

import logging

import pandas as pd
import streamlit as st

from src.services.backtest_service import (  # noqa: F401
    ROUND_TRIP_COST,
    BacktestService,
    _FACTOR_COLS,
)

logger = logging.getLogger(__name__)


@st.cache_data(ttl=1800)
def compute_backtest() -> pd.DataFrame:
    """計算所有歷史推薦的 5/20/60 日報酬，及對比 0050、0056 的 Alpha。"""
    return BacktestService.compute_backtest_data()


@st.cache_data(ttl=3600)
def compute_random_baseline(n_sim: int = 1000) -> dict:
    """Monte Carlo：對每筆推薦日期隨機抽一支，重複 n_sim 次，返回隨機選股均報酬的分布。"""
    return BacktestService.compute_baseline(n_sim=n_sim)


@st.cache_data(ttl=3600)
def compute_signal_quality() -> dict:
    """模型修正：計算各因子維度 IC（Spearman）與 IC IR，識別 signal quality 瓶頸。"""
    return BacktestService.compute_signal_quality()


@st.cache_data(ttl=1800)
def load_pipeline_funnels(days: int = 30) -> pd.DataFrame:
    """載入近 N 天的 pipeline 漏斗統計。"""
    try:
        from datetime import date, timedelta
        from sqlalchemy.orm import Session
        from src.database import init_db, PipelineFunnel

        engine = init_db()
        since = date.today() - timedelta(days=days)
        with Session(engine) as s:
            rows = (
                s.query(PipelineFunnel)
                .filter(PipelineFunnel.date >= since)
                .order_by(PipelineFunnel.date)
                .all()
            )
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame([{
                "date":             r.date,
                "universe":         r.universe,
                "with_price":       r.with_price,
                "hard_filter_pass": r.hard_filter_pass,
                "scored_55plus":    r.scored_55plus,
                "scored_65plus":    r.scored_65plus,
                "recommended":      r.recommended,
                "fail_top1":        f"{r.fail_top1_reason}({r.fail_top1_count})" if r.fail_top1_reason else "",
                "fail_top2":        f"{r.fail_top2_reason}({r.fail_top2_count})" if r.fail_top2_reason else "",
                "fail_top3":        f"{r.fail_top3_reason}({r.fail_top3_count})" if r.fail_top3_reason else "",
            } for r in rows])
    except Exception as e:
        logger.warning(f"load_pipeline_funnels failed: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=1800)
def load_rec_diversity(days: int = 60) -> dict:
    """計算推薦重複率統計（近 N 天）。"""
    try:
        from datetime import date, timedelta
        from collections import Counter
        from sqlalchemy.orm import Session
        from src.database import init_db, Recommendation

        engine = init_db()
        since = date.today() - timedelta(days=days)
        with Session(engine) as s:
            rows = (
                s.query(Recommendation.date, Recommendation.stock_id,
                        Recommendation.stock_name, Recommendation.total_score)
                .filter(Recommendation.date >= since)
                .all()
            )
        if not rows:
            return {}
        dates = sorted(set(r.date for r in rows))
        cnt = Counter(r.stock_id for r in rows)
        n_days = len(dates)
        n_total = len(rows)
        n_unique = len(cnt)

        top10 = [
            {
                "stock_id": sid,
                "count":    c,
                "pct_days": round(c / n_days * 100, 1),
                "name":     next((r.stock_name for r in rows if r.stock_id == sid), sid),
            }
            for sid, c in cnt.most_common(10)
        ]

        # 逐日 Top-3 重疊率
        daily = {}
        for r in rows:
            daily.setdefault(r.date, []).append(r.stock_id)
        overlap_rates = []
        date_list = sorted(daily.keys())
        for i in range(1, len(date_list)):
            prev = set(daily[date_list[i - 1]])
            curr = set(daily[date_list[i]])
            if prev and curr:
                overlap_rates.append(len(prev & curr) / max(len(prev), len(curr)))

        return {
            "n_days":        n_days,
            "n_total":       n_total,
            "n_unique":      n_unique,
            "unique_rate":   round(n_unique / n_total * 100, 1) if n_total else 0,
            "avg_overlap":   round(sum(overlap_rates) / len(overlap_rates) * 100, 1) if overlap_rates else 0,
            "top10":         top10,
            "since":         since,
        }
    except Exception as e:
        logger.warning(f"load_rec_diversity failed: {e}")
        return {}


def _calc_stats(ret: pd.Series, alpha: pd.Series, hold_days: int) -> dict:
    r = ret.dropna()
    a = alpha.dropna()
    if len(r) < 5:
        return {}
    from scipy import stats as _sc

    t, p = _sc.ttest_1samp(a, 0)
    cum = (1 + r / 100).cumprod()
    mdd = ((cum - cum.cummax()) / cum.cummax() * 100).min()
    return {
        "n": len(r),
        "mean_ret": r.mean(),
        "mean_alpha": a.mean(),
        "win_alpha": (a > 0).mean() * 100,
        "ir": a.mean() / a.std() if a.std() > 0 else 0,
        "sharpe": r.mean() / r.std() * (252 / hold_days) ** 0.5 if r.std() > 0 else 0,
        "t": t,
        "p": p,
        "sig": p < 0.05,
        "mdd": mdd,
    }


def _calc_beta(ret_s: pd.Series, ret_m: pd.Series):
    df = pd.DataFrame({"s": ret_s, "m": ret_m}).dropna()
    if len(df) < 5:
        return None
    var_m = df["m"].var()
    return round(df["s"].cov(df["m"]) / var_m, 2) if var_m > 0 else None


def _model_confidence(st_dict: dict) -> tuple:
    if not st_dict:
        return 1, "★☆☆☆☆", "樣本不足，無法評估"
    n, p, alpha, ir = st_dict["n"], st_dict["p"], st_dict["mean_alpha"], st_dict["ir"]
    score = 0
    score += 3 if n >= 80 else 2 if n >= 40 else 1 if n >= 20 else 0
    score += 3 if p < 0.05 else 2 if p < 0.10 else 1 if p < 0.20 else 0
    score += 3 if alpha > 2 else 2 if alpha > 0.5 else 1 if alpha > 0 else 0
    score += 3 if ir > 0.5 else 2 if ir > 0.2 else 1 if ir > 0 else 0
    stars = max(1, min(5, round(score / 2.5 + 0.5)))
    descs = {
        1: "效力存疑，請持續累積樣本",
        2: "初步跡象，尚無統計支撐",
        3: "尚可，需跨越更多市場環境",
        4: "良好，具初步超額報酬能力",
        5: "優秀，Alpha 統計顯著",
    }
    return stars, "★" * stars + "☆" * (5 - stars), descs[stars]


def page_backtest() -> None:
    import altair as alt

    st.markdown('<div class="section-title">🔬 模型驗證</div>', unsafe_allow_html=True)

    df = compute_backtest()
    if df.empty:
        st.info("尚無足夠歷史資料，請先執行分析並同步。")
        return

    n_flagged = df["data_flag"].notna().sum() if "data_flag" in df.columns else 0
    sub = df.dropna(subset=["ret_20d", "b0050_20"]).sort_values("date").copy()
    if sub.empty:
        st.info("尚無足夠價格資料（需同步後等待回測窗口完成）。")
        return

    st20 = _calc_stats(sub["ret_20d"], sub["a0050_20"].dropna(), 20)
    model_mean = sub["ret_20d"].mean()
    alpha_mean = sub["a0050_20"].mean()
    win_bench = (sub["a0050_20"] > 0).mean() * 100
    beta = _calc_beta(sub["ret_20d"], sub["b0050_20"])
    p_val = st20["p"] if st20 else None
    ir = st20["ir"] if st20 else None
    sharpe = st20["sharpe"] if st20 else None
    mdd = st20["mdd"] if st20 else None
    n_samp = st20["n"] if st20 else len(sub)
    conf_stars, conf_str, conf_desc = _model_confidence(st20)

    if p_val is not None:
        if p_val < 0.05:
            verdict, verdict_color = "✅ 有統計顯著的超額報酬（p < 0.05）", "#00c851"
        elif p_val < 0.15:
            verdict, verdict_color = "⚠️ 初步跡象但尚不顯著（p < 0.15）", "#ffbb33"
        else:
            verdict, verdict_color = "❌ 目前沒有足夠證據顯示模型優於大盤", "#ff4444"
    else:
        verdict, verdict_color = "—", "#888"

    if n_samp < 30:
        st.error(
            f"⚠️ 樣本數僅 {n_samp} 筆（建議至少 30 筆），統計結論可靠性低，請勿過度解讀 p 值與 Alpha。"
        )
    elif n_samp < 60:
        st.warning(f"⚠️ 樣本數 {n_samp} 筆，建議累積至 60+ 筆後統計結論才較穩定。")

    conf_color = ["#ff4444", "#ff4444", "#ffbb33", "#ffbb33", "#00c851"][conf_stars - 1]
    st.markdown(
        f"""
<div style="background:#1a1a2e;border:1px solid #333;border-radius:12px;padding:16px 20px;margin-bottom:12px">
  <div style="display:flex;align-items:center;gap:12px">
    <div style="font-size:1.5rem;color:{conf_color}">{conf_str}</div>
    <div>
      <div style="font-size:0.7rem;color:#888">模型信心分數（樣本數 · p 值 · Alpha · IR 綜合）</div>
      <div style="font-size:0.85rem;color:{conf_color};font-weight:600">{conf_desc}</div>
    </div>
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    def _m(label, val, color="#fff"):
        return f'<div style="background:#111;border-radius:8px;padding:10px 12px"><div style="font-size:0.68rem;color:#888">{label}</div><div style="font-size:1.1rem;font-weight:700;color:{color}">{val}</div></div>'

    ac = "#00c851" if alpha_mean >= 0 else "#ff4444"
    st.markdown(
        f"""
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px">
  {_m("樣本數（冷卻後）", f"{n_samp} 筆")}
  {_m("20日均報酬（淨）", f"{model_mean:+.2f}%", "#667eea")}
  {_m("Alpha vs 0050（淨）", f"{alpha_mean:+.2f}%", ac)}
  {_m("Beta", f"{beta:.2f}" if beta is not None else "—")}
  {_m("Sharpe Ratio", f"{sharpe:.2f}" if sharpe is not None else "—")}
  {_m("IR（資訊比率）", f"{ir:.2f}" if ir is not None else "—")}
  {_m("p 值", f"{p_val:.3f}" if p_val is not None else "—")}
  {_m("勝率 vs 0050", f"{win_bench:.0f}%")}
  {_m("推薦序列 MDD", f"{mdd:.1f}%" if mdd is not None else "—")}
</div>""",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
<div style="background:#1a1a2e;border:1px solid #333;border-radius:8px;padding:12px 16px;margin-bottom:16px">
  <div style="color:{verdict_color};font-size:0.95rem;font-weight:600">{verdict}</div>
  <div style="color:#888;font-size:0.75rem;margin-top:6px">
    ⚠️ 模型、0050、0056、隨機基準報酬均已扣除單次買賣成本 0.585%（手續費＋證交稅），未扣滑價 ·
    模型與隨機基準均套用 20 交易日冷卻期（同股票不重複計算）·
    回測期間偏短，需持續累積跨越完整財報週期的樣本<br>
    {"⚠️ 本回測含 " + str(n_flagged) + " 筆停牌/下市紀錄（停牌用最後成交價、下市用 -100%），不靜默刪除以保留完整損益。 · " if n_flagged > 0 else ""}
    ⚠️ 倖存者偏差：分析池僅含現存且有完整價格資料的股票，歷史上已下市標的無法納入，可能使績效偏高。
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    st.markdown("#### 🎲 隨機選股基準（Monte Carlo 1000 次模擬）")
    st.caption(
        "在相同日期隨機從當天 AnalysisResult 股票池中選一支（排除實際推薦股，限有價格資料者），重複 1000 次，比較模型是否有識別能力。"
    )

    with st.spinner("計算中…"):
        mc = compute_random_baseline(1000)

    if mc and mc.get("sim_means"):
        sim_means = mc["sim_means"]
        rand_mean = sum(sim_means) / len(sim_means)
        percentile = sum(1 for x in sim_means if x < model_mean) / len(sim_means) * 100

        c1, c2, c3 = st.columns(3)
        c1.metric("模型 20日均報酬（淨）", f"{model_mean:+.2f}%")
        c2.metric(
            "隨機選股均報酬",
            f"{rand_mean:+.2f}%",
            f"{'模型領先' if model_mean > rand_mean else '模型落後'} {abs(model_mean - rand_mean):.2f}%",
            delta_color="normal" if model_mean > rand_mean else "inverse",
        )
        c3.metric(
            "模型位於隨機分布",
            f"第 {percentile:.0f} 百分位",
            "✅ 有識別能力" if percentile >= 75 else "⚠️ 尚未顯著優於隨機",
        )

        mc_df = pd.DataFrame({"mean_ret": sim_means, "type": ["隨機"] * len(sim_means)})
        hist = (
            alt.Chart(mc_df)
            .mark_bar(opacity=0.7, color="#667eea")
            .encode(
                x=alt.X(
                    "mean_ret:Q", bin=alt.Bin(maxbins=40), title="模擬平均報酬 (%)"
                ),
                y=alt.Y("count()", title="次數"),
            )
            .properties(height=220)
        )
        model_line = (
            alt.Chart(pd.DataFrame({"x": [model_mean]}))
            .mark_rule(color="#ff8800", strokeWidth=2.5)
            .encode(x="x:Q")
        )
        model_label = (
            alt.Chart(
                pd.DataFrame(
                    {
                        "x": [model_mean],
                        "y": [len(sim_means) // 8],
                        "text": [f"模型 {model_mean:+.2f}%"],
                    }
                )
            )
            .mark_text(color="#ff8800", fontSize=11, align="left", dx=6)
            .encode(x="x:Q", y="y:Q", text="text:N")
        )
        st.altair_chart(hist + model_line + model_label, use_container_width=True)

    st.markdown("---")
    st.markdown("#### 推薦序列累積報酬（各筆 20 日報酬連乘）")
    st.caption(
        "⚠️ 此為推薦序列績效，非真實投資組合報酬。同期推薦多檔或持倉重疊時，累積曲線可能高估或低估實際績效。"
    )
    cum_s = ((1 + sub["ret_20d"] / 100).cumprod() * 100 - 100).tolist()
    cum_50 = ((1 + sub["b0050_20"] / 100).cumprod() * 100 - 100).tolist()
    sub56 = sub.dropna(subset=["b0056_20"])
    cum_56 = (
        ((1 + sub56["b0056_20"] / 100).cumprod() * 100 - 100).tolist()
        if not sub56.empty
        else []
    )

    curve_data = (
        [{"trade_no": i + 1, "cum": v, "type": "策略"} for i, v in enumerate(cum_s)]
        + [{"trade_no": i + 1, "cum": v, "type": "0050"} for i, v in enumerate(cum_50)]
        + (
            [
                {"trade_no": i + 1, "cum": v, "type": "0056（高息）"}
                for i, v in enumerate(cum_56)
            ]
            if cum_56
            else []
        )
    )
    curve_df = pd.DataFrame(curve_data)
    line = (
        alt.Chart(curve_df)
        .mark_line()
        .encode(
            x=alt.X("trade_no:Q", title="推薦筆數"),
            y=alt.Y("cum:Q", title="累積報酬 (%)"),
            color=alt.Color(
                "type:N",
                scale=alt.Scale(
                    domain=["策略", "0050", "0056（高息）"],
                    range=["#667eea", "#aaaaaa", "#ffbb33"],
                ),
            ),
            tooltip=["trade_no:Q", "type:N", alt.Tooltip("cum:Q", format=".1f")],
        )
        .properties(height=260)
    )
    zero = (
        alt.Chart(pd.DataFrame({"y": [0]}))
        .mark_rule(color="#444", strokeDash=[4, 4])
        .encode(y="y:Q")
    )
    st.altair_chart(line + zero, use_container_width=True)

    st.markdown("#### 各基準完整統計（20 日）")
    tbl = []
    for bench_label, ak, bk in [
        ("vs 0050", "a0050_20", "b0050_20"),
        ("vs 0056", "a0056_20", "b0056_20"),
    ]:
        valid = sub.dropna(subset=["ret_20d", bk])
        st_d = _calc_stats(valid["ret_20d"], valid[ak], 20)
        if not st_d:
            continue
        tbl.append(
            {
                "基準": bench_label,
                "樣本": st_d["n"],
                "模型均報酬": f"{st_d['mean_ret']:+.2f}%",
                "均 Alpha": f"{st_d['mean_alpha']:+.2f}%",
                "勝率 vs 基準": f"{st_d['win_alpha']:.0f}%",
                "IR": f"{st_d['ir']:.2f}",
                "t 值": f"{st_d['t']:.2f}",
                "p 值": f"{st_d['p']:.3f}",
                "顯著": "✅" if st_d["sig"] else "⚠️",
                "推薦序列 MDD": f"{st_d['mdd']:.1f}%",
            }
        )
    if tbl:
        st.dataframe(pd.DataFrame(tbl), use_container_width=True, hide_index=True)

    st.markdown("#### 逐筆 Alpha vs 0050（20 日）")
    bar_df = sub.copy()
    bar_df["label"] = bar_df["date"].astype(str) + " " + bar_df["stock_id"]
    bar_df["color"] = bar_df["a0050_20"].apply(
        lambda x: "#00c851" if (x or 0) >= 0 else "#ff4444"
    )
    bar = (
        alt.Chart(bar_df.dropna(subset=["a0050_20"]))
        .mark_bar()
        .encode(
            x=alt.X(
                "label:N",
                sort=None,
                axis=alt.Axis(labelAngle=-60, labelLimit=60, labelFontSize=8),
            ),
            y=alt.Y("a0050_20:Q", title="Alpha (%)"),
            color=alt.Color("color:N", scale=None),
            tooltip=[
                "date:T",
                "stock_id:N",
                alt.Tooltip("ret_20d:Q", format=".2f", title="策略%"),
                alt.Tooltip("b0050_20:Q", format=".2f", title="0050%"),
                alt.Tooltip("a0050_20:Q", format=".2f", title="Alpha%"),
            ],
        )
        .properties(height=240)
    )
    zero2 = (
        alt.Chart(pd.DataFrame({"y": [0]}))
        .mark_rule(color="#888", strokeDash=[4, 4])
        .encode(y="y:Q")
    )
    st.altair_chart(bar + zero2, use_container_width=True)

    # ── Signal Quality（因子 IC 診斷）────────────────────────────
    st.markdown("---")
    st.markdown("#### 🔍 因子 IC 診斷（Signal Quality）")
    st.caption(
        "使用每日全截面 AnalysisResult（非僅推薦股）計算各因子對 20/60 日前向報酬的 Spearman IC。"
        "IC > 0.05 具實務意義；|t| > 1.96 達統計顯著（大樣本）。"
    )

    with st.spinner("計算因子 IC 中…"):
        sq = compute_signal_quality()

    _FACTOR_LABELS = {
        "quality_score": "基本面（品質）",
        "timing_score": "技術面（時機）",
        "behavior_score": "市場行為（籌碼）",
        "intelligence_score": "市場情報",
        "risk_score": "風險分數",
        "total_score": "綜合評分",
    }

    if not sq or not sq.get("factor_ic"):
        st.info("AnalysisResult 資料不足，無法計算因子 IC。請確認已執行分析並同步。")
    else:
        factor_ic = sq["factor_ic"]
        n_obs = sq.get("n_obs", 0)
        st.caption(f"全截面觀測數：{n_obs} 筆（含所有分析日期 × 股票）")

        def _fmt_ic(v):
            return f"{v:+.4f}" if v is not None else "—"

        def _fmt_t(v):
            if v is None:
                return "—"
            badge = " ✅" if abs(v) >= 1.96 else " ⚠️" if abs(v) >= 1.0 else ""
            return f"{v:+.2f}{badge}"

        ic_rows = []
        for f in _FACTOR_COLS:
            s = factor_ic.get(f, {})
            ic_rows.append(
                {
                    "因子": _FACTOR_LABELS.get(f, f),
                    "IC₂₀": _fmt_ic(s.get("ic_20")),
                    "t₂₀": _fmt_t(s.get("t_20")),
                    "IC₆₀": _fmt_ic(s.get("ic_60")),
                    "t₆₀": _fmt_t(s.get("t_60")),
                    "IC IR": f"{s['ic_20_ir']:.2f}" if s.get("ic_20_ir") is not None else "—",
                    "n": s.get("n_20", 0),
                    "_ic20_raw": s.get("ic_20"),
                }
            )
        ic_df = pd.DataFrame(ic_rows)

        def _color_ic_cell(v):
            try:
                val = float(str(v).split()[0])
                if val > 0.05:
                    return "color:#00c851;font-weight:600"
                if val > 0:
                    return "color:#88cc88"
                if val > -0.05:
                    return "color:#ff8800"
                return "color:#ff4444;font-weight:600"
            except Exception:
                return ""

        display_df = ic_df.drop(columns=["_ic20_raw"])
        st.dataframe(
            display_df.style.map(_color_ic_cell, subset=["IC₂₀", "IC₆₀"]),
            use_container_width=True,
            hide_index=True,
        )

        monthly_ic = sq.get("monthly_ic")
        if monthly_ic is not None and not monthly_ic.empty:
            key_factors = ["quality_score", "timing_score", "total_score"]
            mf = monthly_ic[monthly_ic["factor"].isin(key_factors)].copy()
            mf["因子"] = mf["factor"].map(_FACTOR_LABELS)
            st.markdown("##### 逐月 IC 時間序列（20 日，主要因子）")
            ic_line = (
                alt.Chart(mf)
                .mark_line(point=True)
                .encode(
                    x=alt.X("ym:O", title="月份", axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y("ic_20:Q", title="IC（Spearman）"),
                    color=alt.Color("因子:N"),
                    tooltip=[
                        alt.Tooltip("ym:O", title="月份"),
                        alt.Tooltip("因子:N"),
                        alt.Tooltip("ic_20:Q", format=".4f", title="IC"),
                        alt.Tooltip("n:Q", title="樣本數"),
                    ],
                )
                .properties(height=220)
            )
            zero_ic = (
                alt.Chart(pd.DataFrame({"y": [0]}))
                .mark_rule(color="#555", strokeDash=[4, 4])
                .encode(y="y:Q")
            )
            st.altair_chart(ic_line + zero_ic, use_container_width=True)

        st.caption(
            "⚠️ risk_score 越高代表越安全，正 IC 表示高安全分數對應較高報酬（符合預期）。"
            "  IC 穩定跨月為正，才代表該因子具跨 regime 預測力。"
        )

    with st.expander("📋 推薦明細", expanded=False):
        cols = [
            "date",
            "stock_id",
            "confidence",
            "entry",
            "ret_20d",
            "b0050_20",
            "a0050_20",
            "b0056_20",
            "a0056_20",
        ]
        if "data_flag" in df.columns:
            cols.append("data_flag")
        show = df[cols].copy()
        col_names = [
            "日期",
            "股票",
            "信心",
            "進場價",
            "20日%",
            "0050%",
            "Alpha_0050",
            "0056%",
            "Alpha_0056",
        ]
        if "data_flag" in df.columns:
            col_names.append("備注")
        show.columns = col_names
        show = show.sort_values("日期", ascending=False)

        def _c(v):
            if pd.isna(v):
                return "color:#888"
            return (
                "color:#00c851;font-weight:600"
                if v > 0
                else "color:#ff4444;font-weight:600"
            )

        st.dataframe(
            show.style.map(_c, subset=["20日%", "Alpha_0050", "Alpha_0056"]),
            use_container_width=True,
            hide_index=True,
        )

    # ── Pipeline 漏斗 + 推薦重複率診斷 ──────────────────────────
    st.markdown("---")
    st.markdown("#### 🔬 Pipeline 漏斗 & 推薦多樣性診斷")

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown("##### Pipeline 漏斗（近 30 天）")
        funnel_df = load_pipeline_funnels(days=30)
        if funnel_df.empty:
            st.info("尚無漏斗資料，下次執行 main.py 後會自動記錄。")
        else:
            latest = funnel_df.iloc[-1]
            stages = {
                "全市場股價":     int(latest.get("universe", 0)),
                "有歷史資料":     int(latest.get("with_price", 0)),
                "通過 Hard Filter": int(latest.get("hard_filter_pass", 0)),
                "總分 ≥ 55":     int(latest.get("scored_55plus", 0)),
                "總分 ≥ 65":     int(latest.get("scored_65plus", 0)),
                "實際推薦":       int(latest.get("recommended", 0)),
            }
            st.caption(f"最新日期：{latest['date']}")
            stage_df = pd.DataFrame(
                {"階段": list(stages.keys()), "股票數": list(stages.values())}
            )
            try:
                import altair as alt
                chart = (
                    alt.Chart(stage_df)
                    .mark_bar()
                    .encode(
                        x=alt.X("股票數:Q", title="股票數"),
                        y=alt.Y("階段:N", sort=list(stages.keys()), title=""),
                        color=alt.Color(
                            "股票數:Q",
                            scale=alt.Scale(scheme="blues"),
                            legend=None,
                        ),
                        tooltip=["階段:N", "股票數:Q"],
                    )
                    .properties(height=220)
                )
                st.altair_chart(chart, use_container_width=True)
            except Exception:
                st.dataframe(stage_df, use_container_width=True, hide_index=True)

            # 近期漏斗趨勢（≥65 與推薦數）
            if len(funnel_df) > 1:
                trend = funnel_df[["date", "scored_65plus", "recommended"]].copy()
                trend.columns = ["日期", "總分≥65", "實際推薦"]
                st.caption("近期漏斗趨勢（總分≥65 / 實際推薦）")
                st.dataframe(
                    trend.sort_values("日期", ascending=False).head(10),
                    use_container_width=True,
                    hide_index=True,
                )

            # Hard Filter 失敗原因
            if latest.get("fail_top1"):
                st.caption("Hard Filter 主要失敗原因")
                fail_rows = []
                for col in ["fail_top1", "fail_top2", "fail_top3"]:
                    v = latest.get(col, "")
                    if v:
                        fail_rows.append({"原因（次數）": v})
                if fail_rows:
                    st.dataframe(
                        pd.DataFrame(fail_rows),
                        use_container_width=True,
                        hide_index=True,
                    )

    with col_right:
        st.markdown("##### 推薦重複率（近 60 天）")
        div = load_rec_diversity(days=60)
        if not div:
            st.info("尚無推薦記錄。")
        else:
            col_a, col_b = st.columns(2)
            col_a.metric("推薦次數", div["n_total"])
            col_b.metric("不同股票", div["n_unique"])
            col_a.metric("Unique Rate", f"{div['unique_rate']}%",
                         help="不同股票數 / 推薦總次數")
            col_b.metric("日均重疊率", f"{div['avg_overlap']}%",
                         help="相鄰兩日推薦名單的重疊比例（越高 = 越難換）")

            st.caption(f"統計期間：{div['since']} 起，共 {div['n_days']} 個交易日")
            top_df = pd.DataFrame(div["top10"])[["stock_id", "name", "count", "pct_days"]]
            top_df.columns = ["股票代號", "名稱", "推薦次數", "出現天%"]
            st.dataframe(top_df, use_container_width=True, hide_index=True)
