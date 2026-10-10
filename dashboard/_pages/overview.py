"""
pages/overview.py — 今日分析頁（今日推薦 + 市場摘要 + Watch List）
"""

import logging
import re
from datetime import date

import streamlit as st

from dashboard.loaders import (
    load_analysis_results,
    load_current_regime,
    load_db_recommendations,
    load_evidence_stats,
    load_exec_logs,
    load_market_health,
    load_opportunity_recs,
    load_pipeline_funnel,
    load_portfolio_exposure,
    load_report,
    load_stock_names,
    load_stock_prices,
    load_watch_recs,
    parse_market_summary,
    parse_recs_from_report,
)

logger = logging.getLogger(__name__)


def render_rec_card(r: dict, current_regime: str = "neutral", portfolio_exposure: dict = None) -> None:
    from src.engines.decision import decision_label, entry_quality_label, tomorrow_triggers

    dl         = decision_label(r)
    eq_label   = entry_quality_label(r)
    triggers   = tomorrow_triggers(r)
    price      = r.get("price")
    entry_low  = r.get("entry_low")
    entry_high = r.get("entry_high")
    stop_p     = r.get("stop_price") or r.get("stop_loss_price")
    t1         = r.get("target1")
    t2         = r.get("target2") or r.get("target_price")
    atr        = r.get("atr")
    scores     = r.get("scores", {})
    conf       = r.get("confidence", 0)
    level      = r.get("level", "B")
    name       = r.get("name", "")
    sid        = r.get("sid", "")
    advantages = r.get("advantages", [])
    risks      = r.get("risks", [])
    setup      = r.get("setup_type") or "none"
    ma20_gap   = r.get("ma20_gap") or 0.0

    label_color   = dl["color"]
    label_text    = dl["label"]
    override_note = ""
    if dl.get("is_override"):
        override_note = '<span style="font-size:0.7rem;color:#888;margin-left:8px">（進場品質 override）</span>'

    # ── Consecutive recommendation badge (P4) ──────────────────
    consecutive = r.get("consecutive_days", 1)
    consec_badge = ""
    if consecutive >= 2:
        consec_badge = (
            f'<div style="font-size:0.68rem;color:#546e7a;background:#eceff1;'
            f'padding:2px 8px;border-radius:10px;display:inline-block;margin-top:3px">'
            f'🔄 連續第 {consecutive} 個交易日入選</div>'
        )

    # ── "Why again today?" block (P4) ──────────────────────────
    why_again_html = ""
    if consecutive >= 2:
        pt_now = r.get("price_trend_score") or 0
        ma20   = r.get("ma20_gap") or 0.0
        vol_r  = r.get("vol_ratio") or 0.0
        conditions = []
        if pt_now > 0:
            conditions.append(f"PT {pt_now:.0f}")
        if ma20:
            conditions.append(f"MA20 乖離 {ma20:+.1f}%")
        if vol_r:
            conditions.append(f"量比 {vol_r:.1f}x")
        cond_str = "　".join(conditions) if conditions else "條件持續符合"
        why_again_html = f"""
<div style="background:#f1f8e9;border-left:3px solid #8bc34a;padding:5px 10px;margin:4px 0;border-radius:0 6px 6px 0">
  <div style="font-size:0.63rem;color:#558b2f;font-weight:600;margin-bottom:2px">今日仍入選原因</div>
  <div style="font-size:0.73rem;color:#33691e">{cond_str}</div>
</div>"""

    # ── Trade thesis + invalidation (BUY only) ──────────────────
    from src.engines.decision import trade_thesis, position_sizing as _ps
    thesis      = trade_thesis(r)
    thesis_html = ""
    if r.get("trade_signal") in ("strong_buy", "buy") and thesis.get("assumption"):
        inv_items = "".join(
            f'<li style="color:#c62828">❌ {inv}</li>'
            for inv in thesis["invalidations"]
        )
        thesis_html = f"""
<div style="background:#fff3e0;border-left:3px solid #ff8f00;padding:7px 11px;margin:6px 0;border-radius:0 6px 6px 0">
  <div style="font-size:0.63rem;color:#e65100;font-weight:600;margin-bottom:3px">核心假設</div>
  <div style="font-size:0.76rem;color:#bf360c;margin-bottom:5px">{thesis['assumption']}</div>
  <div style="font-size:0.63rem;color:#e65100;font-weight:600;margin-bottom:3px">交易失效條件</div>
  <ul style="margin:0;padding-left:14px;font-size:0.74rem;line-height:1.65">
    {inv_items}
  </ul>
</div>"""

    # ── R/R ratio and trading plan ─────────────────────────────
    rr_html = ""
    if price and stop_p and t1:
        risk_pts   = price - stop_p
        reward_pts = t1 - price
        if risk_pts > 0:
            rr        = round(reward_pts / risk_pts, 1)
            rr_color  = "#00897b" if rr >= 2.0 else "#ffb300" if rr >= 1.5 else "#e53935"
            entry_str = f"{entry_low:.1f}–{entry_high:.1f}" if (entry_low and entry_high) else f"{price:.1f}"
            t2_str    = f" / {t2:.1f}" if t2 else ""
            stop_pct  = round((stop_p - price) / price * 100, 1)
            t1_pct    = round((t1 - price) / price * 100, 1)
            rr_html = f"""
<div style="background:#f8f9fa;border-radius:8px;padding:10px 12px;margin:8px 0">
  <div style="font-size:0.7rem;color:#666;margin-bottom:6px;font-weight:600">交易計劃</div>
  <div style="display:flex;gap:8px;flex-wrap:wrap">
    <div style="flex:1;min-width:65px;background:#e8f5e9;border-radius:6px;padding:5px 8px;text-align:center">
      <div style="font-size:0.6rem;color:#2e7d32;font-weight:600">目標一</div>
      <div style="font-size:0.88rem;font-weight:800;color:#2e7d32">{t1:.1f}{t2_str}</div>
      <div style="font-size:0.6rem;color:#2e7d32">+{t1_pct}%</div>
    </div>
    <div style="flex:1;min-width:65px;background:#fce4ec;border-radius:6px;padding:5px 8px;text-align:center">
      <div style="font-size:0.6rem;color:#c62828;font-weight:600">停損</div>
      <div style="font-size:0.88rem;font-weight:800;color:#c62828">{stop_p:.1f}</div>
      <div style="font-size:0.6rem;color:#c62828">{stop_pct}%</div>
    </div>
    <div style="flex:1;min-width:65px;background:#fff8e1;border-radius:6px;padding:5px 8px;text-align:center">
      <div style="font-size:0.6rem;color:#f57f17;font-weight:600">進場區間</div>
      <div style="font-size:0.88rem;font-weight:800;color:#f57f17">{entry_str}</div>
    </div>
    <div style="flex:1;min-width:65px;background:#e3f2fd;border-radius:6px;padding:5px 8px;text-align:center">
      <div style="font-size:0.6rem;color:#1565c0;font-weight:600">R/R</div>
      <div style="font-size:0.88rem;font-weight:800;color:{rr_color}">{rr}x</div>
    </div>
  </div>
</div>"""

    # ── Position sizing ─────────────────────────────────────────
    ps_html = ""
    if price and stop_p and t1 and price > stop_p:
        import sys as _sys
        _cfg = _sys.modules.get("config")
        _PS_CFG = getattr(_cfg, "POSITION_SIZING", None) or \
                  {"capital_ntd": 1_000_000, "max_risk_pct": 1.0, "max_single_pct": 20.0, "lot_size": 1000}
        capital      = st.session_state.get("ps_capital",      _PS_CFG["capital_ntd"])
        max_risk_pct = st.session_state.get("ps_max_risk_pct", _PS_CFG["max_risk_pct"])
        ps = _ps(
            entry=price, stop=stop_p, capital=capital,
            max_risk_pct=max_risk_pct,
            max_single_pct=_PS_CFG["max_single_pct"],
            lot_size=_PS_CFG["lot_size"],
        )
        if ps and ps.get("lots", 0) > 0:
            cap_note = '<span style="color:#e65100">（已達曝險上限）</span>' if ps["capped"] else ""
            ps_html = f"""
<div style="background:#f3e5f5;border-radius:8px;padding:8px 12px;margin:4px 0">
  <div style="font-size:0.65rem;color:#6a1b9a;font-weight:600;margin-bottom:5px">部位試算（風控 {max_risk_pct}% / NT${capital:,.0f}）</div>
  <div style="display:flex;gap:6px;flex-wrap:wrap">
    <div style="flex:1;min-width:60px;text-align:center">
      <div style="font-size:0.6rem;color:#7b1fa2">每股風險</div>
      <div style="font-size:0.85rem;font-weight:700;color:#4a148c">${ps['risk_per_share']:.2f}</div>
    </div>
    <div style="flex:1;min-width:60px;text-align:center">
      <div style="font-size:0.6rem;color:#7b1fa2">建議張數</div>
      <div style="font-size:0.85rem;font-weight:700;color:#4a148c">{ps['lots']} 張{cap_note}</div>
    </div>
    <div style="flex:1;min-width:60px;text-align:center">
      <div style="font-size:0.6rem;color:#7b1fa2">部位金額</div>
      <div style="font-size:0.85rem;font-weight:700;color:#4a148c">NT${ps['position_ntd']:,}</div>
    </div>
    <div style="flex:1;min-width:60px;text-align:center">
      <div style="font-size:0.6rem;color:#7b1fa2">實際風險</div>
      <div style="font-size:0.85rem;font-weight:700;color:#c62828">NT${ps['actual_risk_ntd']:,} ({ps['actual_risk_pct']}%)</div>
    </div>
  </div>
  <div style="font-size:0.6rem;color:#9c27b0;margin-top:4px">⚠ 試算值，實際下單請考慮整體帳戶曝險與流動性。</div>
</div>"""

    # ── Portfolio context (only for BUY signals when exposure data available) ──
    portfolio_html = ""
    if portfolio_exposure and r.get("trade_signal") in ("strong_buy", "buy"):
        try:
            from src.services.portfolio_risk_service import portfolio_context_for_stock
            ctx = portfolio_context_for_stock(r.get("industry"), portfolio_exposure)
            if ctx.get("message"):
                warn_bg    = "#fff3cd" if ctx["should_warn"] else "#e8f5e9"
                warn_border = "#ff8f00" if ctx["should_warn"] else "#43a047"
                warn_color  = "#bf360c" if ctx["should_warn"] else "#2e7d32"
                portfolio_html = f"""
<div style="background:{warn_bg};border-left:3px solid {warn_border};padding:5px 10px;margin:4px 0;border-radius:0 6px 6px 0">
  <div style="font-size:0.63rem;color:{warn_color};font-weight:600;margin-bottom:1px">組合角度</div>
  <div style="font-size:0.73rem;color:{warn_color}">{ctx['message']}</div>
</div>"""
        except Exception:
            pass

    # ── Why bullets ────────────────────────────────────────────
    adv_items  = "".join(f"<li style='color:#2e7d32'>✓ {a}</li>" for a in advantages[:3])
    risk_items = "".join(f"<li style='color:#c62828'>⚠ {r2}</li>" for r2 in risks[:2])
    why_html   = ""
    if adv_items or risk_items:
        why_html = f"""
<div style="margin:6px 0">
  <ul style="margin:0;padding-left:16px;font-size:0.78rem;line-height:1.6">
    {adv_items}{risk_items}
  </ul>
</div>"""

    # ── Tomorrow triggers ───────────────────────────────────────
    trig_items = "".join(f"<li>{t}</li>" for t in triggers)
    trig_html  = f"""
<div style="background:#fafafa;border-left:3px solid #90a4ae;padding:6px 10px;margin:6px 0;border-radius:0 6px 6px 0">
  <div style="font-size:0.65rem;color:#546e7a;font-weight:600;margin-bottom:4px">明日觀察觸發條件</div>
  <ul style="margin:0;padding-left:14px;font-size:0.75rem;color:#37474f;line-height:1.6">
    {trig_items}
  </ul>
</div>"""

    # ── Entry quality badge ─────────────────────────────────────
    eq_color = "#e53935" if eq_label in ("追高", "避開") else "#00897b" if eq_label in ("理想進場點", "回檔機會") else "#7e57c2"
    eq_badge  = f'<span style="font-size:0.7rem;background:{eq_color}22;color:{eq_color};padding:2px 7px;border-radius:10px;font-weight:600">{eq_label}</span>'

    # ── Stock header ────────────────────────────────────────────
    price_str = f"　NT$ {price:,.1f}" if price else ""
    name_html = (
        f'<div style="font-size:1.05rem;font-weight:700">{name}</div>'
        f'<div style="font-size:0.75rem;color:#888">{sid} · TWSE{price_str}</div>'
        if name and name != sid
        else f'<div style="font-size:1.05rem;font-weight:700">{sid}</div>'
        f'<div style="font-size:0.75rem;color:#888">TWSE{price_str}</div>'
    )
    ma20_note = f'<span style="font-size:0.65rem;color:#888">MA20 乖離 {ma20_gap:+.1f}%</span>' if ma20_gap else ""

    st.markdown(
        f"""
<div style="border:1px solid #e0e0e0;border-radius:10px;padding:14px 16px;margin-bottom:12px;background:#fff">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
    <div>{name_html}{consec_badge}</div>
    <div style="text-align:right">
      <div style="font-size:1.3rem;font-weight:900;color:{label_color}">{label_text}</div>
      {override_note}
      <div style="margin-top:3px">{eq_badge}</div>
    </div>
  </div>
  <div style="font-size:0.78rem;color:#555;margin-bottom:6px">{dl['reason']}</div>
  {why_again_html}
  {thesis_html}
  {rr_html}
  {ps_html}
  {portfolio_html}
  {why_html}
  {trig_html}
  <div style="font-size:0.7rem;color:#aaa;margin-top:6px">信心度 {conf}% · {level} 級 · {setup} {ma20_note}</div>
</div>""",
        unsafe_allow_html=True,
    )

    with st.expander("📊 原始評分"):
        col1, col2 = st.columns(2)
        with col1:
            st.metric("綜合", f"{scores.get('total', 0):.0f}")
            st.metric("品質", f"{scores.get('quality', 0):.0f}")
            st.metric("時機", f"{scores.get('timing', 0):.0f}")
        with col2:
            st.metric("籌碼", f"{scores.get('behavior', 0):.0f}")
            st.metric("風險", f"{scores.get('risk', 0):.0f}")
            if atr:
                st.metric("ATR", f"{atr:.2f}")
        conclusion = r.get("conclusion", "")
        if conclusion:
            st.markdown(f"> {conclusion}")

    # ── Evidence panel ──────────────────────────────────────────────────────────
    signal = r.get("trade_signal") or "wait"
    if setup != "none" and signal != "sell":
        ev = load_evidence_stats(setup, current_regime)
        re_ev = ev.get("research", {})
        fe_ev = ev.get("forward", {})
        narrative = ev.get("narrative", "")
        r_n          = re_ev.get("n", 0)
        r_tier_emoji = re_ev.get("tier_emoji", "🔴")
        r_tier_label = re_ev.get("tier_label", "樣本不足")
        f_total      = fe_ev.get("total_recorded", 0)
        f_m20        = fe_ev.get("matured_20d", 0)
        f_m60        = fe_ev.get("matured_60d", 0)
        f_tier_emoji = fe_ev.get("tier_emoji", "🔴")
        f_tier_label = fe_ev.get("tier_label", "尚無 OOS 資料")

        with st.expander(f"📊 類似訊號歷史績效（{setup} × {current_regime}）"):
            st.markdown("**🧪 Research（In-Sample）**")
            if r_n < 10:
                st.caption(f"{r_tier_emoji} 樣本不足（{r_n} 筆），無法計算可靠統計。")
            else:
                r20 = re_ev.get("alpha_20d", {})
                r60 = re_ev.get("alpha_60d", {})
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("類似情境", f"{r_n} 次")
                    if r20.get("mean") is not None:
                        st.metric("20D Alpha 均值", f"{r20['mean']:+.1f}%")
                    if r60.get("mean") is not None:
                        st.metric("60D Alpha 均值", f"{r60['mean']:+.1f}%")
                with col2:
                    if r20.get("winrate") is not None:
                        st.metric("20D 勝率", f"{r20['winrate']:.0f}%")
                    if r60.get("winrate") is not None:
                        st.metric("60D 勝率", f"{r60['winrate']:.0f}%")
                st.caption(f"證據強度：{r_tier_emoji} {r_tier_label}")

            st.divider()

            st.markdown("**🔒 Forward Validation（真實 OOS）**")
            col3, col4 = st.columns(2)
            with col3:
                st.metric("已記錄訊號", f"{f_total} 筆")
                st.metric("20D 已成熟", f"{f_m20} 筆")
                if f_m20 >= 10:
                    f20 = fe_ev.get("alpha_20d", {})
                    if f20.get("mean") is not None:
                        st.metric("20D Alpha", f"{f20['mean']:+.1f}%")
            with col4:
                st.metric("60D 已成熟", f"{f_m60} 筆")
                if f_m20 >= 10:
                    f20 = fe_ev.get("alpha_20d", {})
                    if f20.get("winrate") is not None:
                        st.metric("20D 勝率", f"{f20['winrate']:.0f}%")
            if f_m20 < 10:
                st.caption(f"{f_tier_emoji} Forward 樣本累積中（{f_m20} 筆 20D 已成熟）")
            else:
                st.caption(f"證據強度：{f_tier_emoji} {f_tier_label}")

            if narrative:
                st.divider()
                st.markdown(f"**💬 白話解讀**\n\n{narrative}")


def page_today(selected_date: date) -> None:
    report = load_report(selected_date)
    logs = load_exec_logs()
    results_df = load_analysis_results(selected_date)
    mkt = parse_market_summary(report) if report else {}

    idx_val = mkt.get("index", "—")
    idx_chg = mkt.get("change", "—")
    sentiment = mkt.get("sentiment", "—")
    try:
        _chg_val = float(str(idx_chg).replace("%", "").replace("+", ""))
        chg_color = (
            "#00c851" if _chg_val > 0 else "#ff4444" if _chg_val < 0 else "#aaaaaa"
        )
    except Exception as e:
        logger.debug(f"index change color parse failed: {e}")
        chg_color = "#aaaaaa"

    today_log = (
        logs[logs["date"] == selected_date]
        if not logs.empty
        else __import__("pandas").DataFrame()
    )
    if today_log.empty:
        try:
            from src.database import ExecutionLog, get_session

            _s = get_session()
            _el = (
                _s.query(ExecutionLog)
                .filter_by(date=selected_date)
                .order_by(ExecutionLog.id.desc())
                .first()
            )
            _s.close()
            if _el:
                import pandas as pd

                today_log = pd.DataFrame(
                    [
                        {
                            "date": _el.date,
                            "status": _el.status,
                            "analyzed": _el.total_stocks,
                            "qualified": _el.qualified_stocks,
                            "recs": _el.recommended_stocks,
                        }
                    ]
                )
        except Exception as e:
            logger.debug(f"today_log DB fallback failed: {e}")
    analyzed = int(today_log.iloc[0]["analyzed"]) if not today_log.empty else 0
    qualified = int(today_log.iloc[0]["qualified"]) if not today_log.empty else 0
    status = today_log.iloc[0]["status"] if not today_log.empty else "—"

    # 直接從 recommendations 表算，避免 execution_log 記錄值與實際不符
    try:
        from sqlalchemy import text as _text
        from src.database import get_session as _gs
        _s = _gs()
        recs_cnt = _s.execute(
            _text("SELECT COUNT(*) FROM recommendations WHERE date=:d AND tier='recommend'"),
            {"d": selected_date},
        ).scalar() or 0
        _s.close()
    except Exception:
        recs_cnt = int(today_log.iloc[0]["recs"]) if not today_log.empty else 0

    st.markdown(
        f"""
    <div class="market-card">
      <div style="display:flex; justify-content:space-between; align-items:flex-start">
        <div>
          <div style="font-size:0.75rem; opacity:0.7">加權指數</div>
          <div class="index-val">{idx_val}</div>
          <div class="index-chg" style="color:{chg_color}">{idx_chg}</div>
        </div>
        <div style="text-align:right">
          <div style="font-size:0.75rem; opacity:0.7">市場情緒</div>
          <div style="font-size:1.1rem; font-weight:700; margin-top:4px">{
            '🟢 偏多' if sentiment == 'Bullish' else '🔴 偏空' if sentiment == 'Bearish' else '⚪ 中性'
          }</div>
          <div style="font-size:0.75rem; opacity:0.7; margin-top:4px">漲 {mkt.get('up', '—')} / 跌 {mkt.get('down', '—')}</div>
        </div>
      </div>
      <div class="market-meta">{selected_date} · AI Taiwan Equity Research v6.8</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
    <div class="stat-grid">
      <div class="stat-box">
        <div class="stat-val">{analyzed}</div>
        <div class="stat-lbl">分析股票</div>
      </div>
      <div class="stat-box">
        <div class="stat-val">{qualified}</div>
        <div class="stat-lbl">通過篩選</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:#764ba2">{recs_cnt}</div>
        <div class="stat-lbl">Core Picks</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="font-size:1.4rem">{'✅' if status == 'success' else '❌' if status == 'failed' else '—'}</div>
        <div class="stat-lbl">執行狀態</div>
      </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    if not report:
        st.warning(f"尚無 {selected_date} 的分析報告，請先執行分析。")
        return

    stock_names = load_stock_names()
    stock_prices = load_stock_prices()
    recs = load_db_recommendations(selected_date)

    for r in recs:
        if not r.get("name"):
            r["name"] = stock_names.get(r["sid"], "")
    for r in recs:
        if r["price"] is None:
            r["price"] = stock_prices.get(r["sid"])

    # P2: Pipeline funnel
    funnel = load_pipeline_funnel(selected_date)
    if funnel:
        universe  = funnel.get("universe", 0)
        with_price = funnel.get("with_price", 0)
        hf_pass   = funnel.get("hard_filter_pass", 0)
        final_rec = funnel.get("recommended", 0)
        st.markdown(
            f"""
<div style="background:#f8f9fa;border-radius:8px;padding:7px 14px;margin:6px 0 10px;font-size:0.74rem;color:#546e7a">
  <span style="font-weight:600">今日掃描漏斗：</span>
  全市場 <b>{universe:,}</b> 檔
  → 有價格 <b>{with_price:,}</b>
  → 通過初篩 <b>{hf_pass}</b>
  → Core Picks <b>{final_rec}</b>
</div>""",
            unsafe_allow_html=True,
        )

    # No-Trade Today banner
    health = load_market_health(selected_date)
    _h_level = health.get("level", "green")
    if _h_level in ("red", "yellow"):
        _h_regime  = health.get("regime", "neutral")
        _h_pass    = health.get("pass_rate", 0.0)
        _h_conds   = health.get("conditions", [])
        _h_color   = "#c62828" if _h_level == "red" else "#f57f17"
        _h_bg      = "#ffebee" if _h_level == "red" else "#fff8e1"
        _h_border  = "#ef9a9a" if _h_level == "red" else "#ffe082"
        _h_icon    = "🔴" if _h_level == "red" else "🟡"
        _h_title   = "今日不建議交易" if _h_level == "red" else "今日交易需審慎"
        _cond_html = "".join(f'<li style="font-size:0.77rem;margin-bottom:2px">{c}</li>' for c in _h_conds)
        st.markdown(
            f"""
<div style="background:{_h_bg};border:1.5px solid {_h_border};border-radius:10px;padding:12px 16px;margin:8px 0 12px">
  <div style="font-size:1.05rem;font-weight:800;color:{_h_color};margin-bottom:6px">{_h_icon} {_h_title}</div>
  <ul style="margin:0;padding-left:16px;color:{_h_color}">
    {_cond_html}
  </ul>
  <div style="font-size:0.65rem;color:#888;margin-top:6px">通過率 {_h_pass:.1f}% · 市場趨勢 {_h_regime}</div>
</div>""",
            unsafe_allow_html=True,
        )

    # P3: Diversity health warning (monitor only, no scoring change)
    if len(recs) >= 2:
        from collections import Counter
        rec_industries = [r.get("industry", "") for r in recs if r.get("industry")]
        if rec_industries:
            top_ind, top_cnt = Counter(rec_industries).most_common(1)[0]
            if top_cnt == len(recs):
                st.warning(
                    f"⚠️ 多樣性監控：今日 {len(recs)} 支 Core Picks 均屬同一產業（{top_ind}）。"
                    f"市場今日可能高度集中，建議交叉確認是否為整體行情性現象。"
                )

    if not recs:
        recs_section = re.search(
            r"## ③ Research Candidates.*?\n(.*?)(?=## ④|## 免責)", report, re.DOTALL
        )
        content = recs_section.group(1) if recs_section else ""
        recs = parse_recs_from_report(content)
        for r in recs:
            if r.get("price") is None:
                r["price"] = stock_prices.get(r.get("sid", ""))
            p = r.get("price")
            if p and not r.get("target_price"):
                r["target_price"] = round(p * 1.10, 1)
                r["stop_loss_price"] = round(p * 0.93, 1)

    is_fallback = False
    if not recs and not results_df.empty:
        is_fallback = True
        top_df = results_df.head(8)
        for _, row in top_df.iterrows():
            sid = row["stock_id"]
            name = row.get("name") or stock_names.get(sid) or ""
            recs.append(
                {
                    "name": name,
                    "sid": sid,
                    "price": stock_prices.get(sid),
                    "level": row.get("rec_level", "C") or "C",
                    "scores": {
                        "quality": row.get("quality", 0),
                        "timing": row.get("timing", 0),
                        "behavior": row.get("behavior", 0),
                        "risk": row.get("risk", 0),
                        "total": row.get("total", 0),
                    },
                    "confidence": row.get("confidence", 0),
                    "advantages": [],
                    "risks": [],
                    "watch": [],
                    "conclusion": "",
                }
            )

    if recs:
        if is_fallback:
            st.markdown(
                f'<div class="section-title">分析宇宙（{len(recs)} 檔，未達推薦門檻）</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "⚠️ 本日無符合條件的推薦標的（total_score < 65 或 confidence < 70%），以下為分析分數最高的股票，僅供參考。"
            )
        else:
            st.markdown(
                f'<div class="section-title">Core Picks（{len(recs)} 檔）</div>',
                unsafe_allow_html=True,
            )
        current_regime    = load_current_regime()
        portfolio_exposure = load_portfolio_exposure()
        cols_data = [recs[i::2] for i in range(2)]
        col_left, col_right = st.columns(2)
        for rec in cols_data[0]:
            with col_left:
                render_rec_card(rec, current_regime, portfolio_exposure)
        for rec in cols_data[1]:
            with col_right:
                render_rec_card(rec, current_regime, portfolio_exposure)
    else:
        st.info("今日尚無分析資料，請先執行分析。")

    # ── New Opportunities（分數動能強勁但在冷卻期外的新股）──────────
    opp_recs = load_opportunity_recs(selected_date)
    if opp_recs:
        st.markdown(
            f'<div class="section-title">🔥 New Opportunities（{len(opp_recs)} 檔，觀察追蹤中）</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "⚡ 分數動能突出但尚未進入正式 Core Picks。追蹤 4–8 週績效後再決定是否納入正式推薦。"
        )
        for opp in opp_recs:
            if not opp.get("name"):
                opp["name"] = stock_names.get(opp["sid"], "")
            if opp["price"] is None:
                opp["price"] = stock_prices.get(opp["sid"])
            sc5  = opp.get("score_change_5d")
            tc5  = opp.get("timing_change_5d")
            bc5  = opp.get("behavior_change_5d")
            sc5_str = f"{sc5:+.1f}" if sc5 is not None else "—"
            tc5_str = f"{tc5:+.1f}" if tc5 is not None else "—"
            bc5_str = f"{bc5:+.1f}" if bc5 is not None else "—"

            def _badge(label, val, val_str, threshold=5):
                bg = "#e65100" if val and val >= threshold else "#37474f"
                arrow = "▲ " if val and val > 0 else ""
                return f'<span style="background:{bg};color:#fff;border-radius:4px;padding:2px 7px;font-size:0.68rem;font-weight:700">{arrow}{label} {val_str}</span>'

            badges = (
                _badge("總5D", sc5, sc5_str, 5)
                + " " + _badge("技術5D", tc5, tc5_str, 8)
                + " " + _badge("籌碼5D", bc5, bc5_str, 8)
            )
            total = opp.get("total_score", opp["scores"].get("total", 0))
            name  = opp.get("name", "") or opp["sid"]
            sid   = opp["sid"]
            price = opp.get("price")
            price_str = f"NT$ {price:,.1f}" if price else "—"
            adv_tags = "".join(
                f'<span class="tag-good">✓ {a[:18]}</span>'
                for a in opp.get("advantages", [])[:2]
            )
            st.markdown(
                f"""
<div style="background:#1a1a2e;border:1px solid #e65100;border-radius:8px;padding:12px 16px;margin-bottom:8px">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px">
    <div>
      <span style="font-weight:700;font-size:1rem;color:#f0f6fc">{name}</span>
      <span style="color:#aaa;font-size:0.75rem;margin-left:8px">{sid} · {price_str}</span>
    </div>
    <span style="background:#333;color:#ddd;border-radius:4px;padding:2px 7px;font-size:0.7rem">總分 {total:.0f}</span>
  </div>
  <div style="margin-top:8px;display:flex;gap:4px;flex-wrap:wrap">{badges}</div>
  {f'<div style="margin-top:6px">{adv_tags}</div>' if adv_tags else ''}
  {f'<div style="color:#ccc;font-size:0.78rem;margin-top:6px">{opp["summary"]}</div>' if opp.get("summary") else ''}
</div>""",
                unsafe_allow_html=True,
            )

    # Watch List — 由 DecisionEngine.select_watchlist() 產生（percentile + min_score + confidence）
    watch_recs_list = load_watch_recs(selected_date)
    if watch_recs_list:
        with st.expander(f"📋 Watch List（{len(watch_recs_list)} 檔，當日相對最強、待觀察）"):
            for w in watch_recs_list:
                sc5 = w.get("score_change_5d")
                sc5_str = f"（5D {sc5:+.1f}）" if sc5 is not None else ""
                display_name = f"{w['name']}（{w['sid']}）" if w['name'] != w['sid'] else w['sid']
                st.markdown(
                    f"**{display_name}** — 綜合 {w['total_score']:.0f} | "
                    f"技術 {w['timing_score']:.0f} | 籌碼 {w['behavior_score']:.0f} | "
                    f"信心 {w['confidence']:.0f}%{sc5_str}"
                )
