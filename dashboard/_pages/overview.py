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
    load_latest_completed_date,
    load_market_health,
    load_opportunity_recs,
    load_pipeline_funnel,
    load_report,
    load_stock_names,
    load_stock_prices,
    load_watch_recs,
    parse_market_summary,
    parse_recs_from_report,
)

logger = logging.getLogger(__name__)


def _historical_analog_html(ev: dict) -> str:
    """歷史類似情境統計 HTML 片段。"""
    re_ev = ev.get("research", {})
    r_n = re_ev.get("n", 0)
    if r_n < 5:
        return ""
    r20 = re_ev.get("alpha_20d", {})
    r60 = re_ev.get("alpha_60d", {})
    tier_emoji = re_ev.get("tier_emoji", "🔴")
    median_20 = r20.get("median")
    wr_20 = r20.get("winrate")
    p25_20 = r20.get("p25")
    p75_20 = r20.get("p75")
    median_60 = r60.get("median")
    wr_60 = r60.get("winrate")
    if median_20 is None:
        return (
            f'<div style="font-size:0.7rem;color:#888;padding:4px 0">'
            f"📊 歷史相似情境 {r_n} 次 {tier_emoji}，統計數據尚在累積。</div>"
        )
    sign20 = "+" if median_20 >= 0 else ""
    range_str = (
        f"{p25_20:+.1f}% ～ {p75_20:+.1f}%"
        if (p25_20 is not None and p75_20 is not None)
        else "—"
    )
    m60_str = (
        f"60D 中位數 {median_60:+.1f}%　60D 勝率 {wr_60:.0f}%"
        if median_60 is not None
        else ""
    )
    return f"""
<div style="background:#f8f9fa;border:1px dashed #cfd8dc;border-radius:8px;padding:9px 12px;margin:4px 0 10px">
  <div style="font-size:0.62rem;font-weight:700;color:#78909c;letter-spacing:.05em;margin-bottom:5px">
    📊 歷史相似走勢　{tier_emoji} {r_n} 次類似情境
  </div>
  <div style="font-size:0.75rem;color:#333;line-height:1.75">
    20D 中位數 <b>{sign20}{median_20:.1f}%</b>
    25–75% 範圍 <b>{range_str}</b>
    20D 勝率 <b>{wr_20:.0f}%</b>
    {f"<br>{m60_str}" if m60_str else ""}
  </div>
  <div style="font-size:0.62rem;color:#aaa;margin-top:4px">
    以上為相同 Setup × 市場情境的歷史分布，非 AI 預測。實際路徑受多種因素影響。
  </div>
</div>"""


def _render_trading_reference(
    selected_date: date,
    recs: list,
    latest_date: "date | None" = None,
) -> None:
    """今日交易參考：分析日 / 適用交易日 / 進場摘要 / 報價聲明。"""
    from config import ENTRY_QUALITY

    try:
        from src.core.trading_calendar import next_trading_day
        next_td = next_trading_day(selected_date)
    except Exception:
        next_td = None

    today = date.today()
    days_old = (today - selected_date).days
    chase_gap = ENTRY_QUALITY.get("chase_gap_pct", 5.0)

    td_label = next_td.strftime("%Y/%m/%d") if next_td else "—"

    # — freshness note —
    freshness_html = ""
    if days_old > 1:
        freshness_html = (
            f'<div style="font-size:0.7rem;color:#ff8c00;margin-top:6px">'
            f"⚠️ 此訊號已有 {days_old} 天，次日進場窗口可能已過。</div>"
        )
    elif latest_date and latest_date > selected_date:
        freshness_html = (
            f'<div style="font-size:0.7rem;color:#f57f17;margin-top:6px">'
            f"🔄 資料庫最新分析：{latest_date}（側邊欄可切換日期）</div>"
        )

    # — signal rows —
    buy_recs = [r for r in recs if (r.get("trade_signal") or "").lower() in ("buy", "strong_buy")]
    wait_recs = [r for r in recs if (r.get("trade_signal") or "").lower() == "wait"]

    sig_html = ""
    if buy_recs:
        rows_html = ""
        for r in buy_recs:
            name = r.get("name") or r.get("sid", "—")
            entry_low  = r.get("entry_low")
            entry_high = r.get("entry_high")
            stop_p     = r.get("stop_price")
            t1         = r.get("target1")
            ma20_gap   = r.get("ma20_gap")
            price      = r.get("price")
            price_date = r.get("price_date")

            chase_warn = ""
            if ma20_gap is not None and abs(ma20_gap) > chase_gap:
                chase_warn = ' <span style="color:#ff6e40;font-size:0.65rem">⚡高乖離</span>'

            price_str = ""
            if price:
                src = (
                    "前收盤"
                    if (price_date and price_date < selected_date)
                    else "收盤"
                )
                price_str = (
                    f' <span style="opacity:0.55;font-size:0.6rem">{src} {price:.1f}</span>'
                )

            if entry_low and entry_high:
                entry_str = f"{entry_low:.1f}–{entry_high:.1f}"
            elif entry_low:
                entry_str = f"≥{entry_low:.1f}"
            else:
                entry_str = "—"

            stop_str = f"{stop_p:.1f}" if stop_p else "—"
            t1_str   = f"{t1:.1f}"    if t1    else "—"

            rows_html += (
                f"<tr>"
                f'<td style="padding:2px 12px 2px 0;font-weight:700">{name}{price_str}</td>'
                f'<td style="padding:2px 12px 2px 0;color:#00e5ff">{entry_str}</td>'
                f'<td style="padding:2px 12px 2px 0;color:#ff6e6e">{stop_str}</td>'
                f'<td style="padding:2px 0;color:#81c784">{t1_str}</td>'
                f"<td>{chase_warn}</td>"
                f"</tr>"
            )

        sig_html = f"""
<div style="margin-top:10px">
  <div style="font-size:0.6rem;opacity:0.55;margin-bottom:5px">BUY 訊號（{len(buy_recs)} 檔）</div>
  <table style="font-size:0.74rem;color:#fff;border-collapse:collapse;width:100%">
    <tr style="font-size:0.58rem;opacity:0.45">
      <th style="text-align:left;padding:0 12px 4px 0;font-weight:400">標的</th>
      <th style="text-align:left;padding:0 12px 4px 0;font-weight:400">進場區間</th>
      <th style="text-align:left;padding:0 12px 4px 0;font-weight:400">停損</th>
      <th style="text-align:left;padding:0 0 4px 0;font-weight:400">目標1</th>
      <th></th>
    </tr>
    {rows_html}
  </table>
</div>"""
    elif recs:
        wait_names = "、".join(
            r.get("name") or r.get("sid", "") for r in (wait_recs or recs)[:3]
        )
        sig_html = (
            f'<div style="margin-top:8px;font-size:0.78rem;color:#b0bec5">'
            f"WAIT — {wait_names}</div>"
        )
    else:
        sig_html = (
            '<div style="margin-top:8px;font-size:0.78rem;color:#546e7a">'
            "今日無推薦標的</div>"
        )

    disclaimer = (
        '<div style="font-size:0.6rem;color:#546e7a;margin-top:10px;'
        'border-top:1px solid #263040;padding-top:6px">'
        "⚠️ 所有報價為前一日收盤，非盤中即時報價。進場前請確認當日市場報價。"
        "</div>"
    )

    st.markdown(
        f"""
<div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:12px;
            padding:14px 18px;margin:8px 0 14px;color:white">
  <div style="font-size:0.6rem;font-weight:700;opacity:0.45;letter-spacing:.1em;
              text-transform:uppercase;margin-bottom:9px">今日交易參考</div>
  <div style="display:flex;gap:28px">
    <div>
      <div style="font-size:0.58rem;opacity:0.5">訊號分析日</div>
      <div style="font-size:0.9rem;font-weight:700">{selected_date.strftime("%Y/%m/%d")}</div>
    </div>
    <div>
      <div style="font-size:0.58rem;opacity:0.5">適用交易日</div>
      <div style="font-size:0.9rem;font-weight:700;color:#00e5ff">{td_label}</div>
    </div>
  </div>
  {sig_html}
  {freshness_html}
  {disclaimer}
</div>""",
        unsafe_allow_html=True,
    )


def render_rec_card(
    r: dict, current_regime: str = "neutral", portfolio_exposure: dict = None
) -> None:
    from src.engines.decision import decision_label
    from src.engines.decision import position_sizing as _ps
    from src.engines.decision import tomorrow_triggers, trade_thesis
    from src.presentation.decision_presenter import DecisionPresenter

    # ── Engine reads ──────────────────────────────────────────────
    dl = decision_label(r)
    triggers = tomorrow_triggers(r)
    thesis = trade_thesis(r)
    signal = r.get("trade_signal") or "wait"
    is_buy = signal in ("strong_buy", "buy")
    setup = r.get("setup_type") or "none"
    price = r.get("price")
    entry_low = r.get("entry_low")
    entry_high = r.get("entry_high")
    stop_p = r.get("stop_price") or r.get("stop_loss_price")
    t1 = r.get("target1")
    t2 = r.get("target2") or r.get("target_price")
    atr = r.get("atr")
    scores = r.get("scores", {})

    # ── Load evidence ─────────────────────────────────────────────
    _ev: dict = {}
    if setup != "none" and signal != "sell":
        try:
            _ev = load_evidence_stats(setup, current_regime)
        except Exception:
            _ev = {}

    # ── Build card via presenter ──────────────────────────────────
    card = DecisionPresenter().present(r, _ev)

    # ── Consec badge ──────────────────────────────────────────────
    consec_html = (
        f'<span style="font-size:0.63rem;color:#546e7a;background:#eceff1;'
        f'padding:2px 7px;border-radius:10px;margin-left:6px;vertical-align:middle">'
        f"🔄 連續第 {card.consecutive} 日入選</span>"
        if card.consecutive >= 2
        else ""
    )

    # ── Trading plan ──────────────────────────────────────────────
    plan_html = ""
    plan_label = "交易計畫" if is_buy else "確認後，怎麼交易"
    plan_opacity = "1" if is_buy else "0.65"
    if price and stop_p and t1:
        risk_pts = price - stop_p
        if risk_pts > 0:
            rr = round((t1 - price) / risk_pts, 1)
            rr_col = "#00897b" if rr >= 2.0 else "#ffb300" if rr >= 1.5 else "#e53935"
            e_str = (
                f"{entry_low:.1f}–{entry_high:.1f}"
                if (entry_low and entry_high)
                else f"~{price:.1f}"
            )
            t2_str = f" / {t2:.1f}" if t2 else ""
            stop_pct = round((stop_p - price) / price * 100, 1)
            t1_pct = round((t1 - price) / price * 100, 1)
            plan_html = f"""
<div style="opacity:{plan_opacity};background:#f8f9fa;border-radius:8px;padding:10px 12px;margin:10px 0">
  <div style="font-size:0.62rem;font-weight:700;color:#78909c;letter-spacing:.05em;margin-bottom:6px">{plan_label}</div>
  <div style="display:flex;gap:7px;flex-wrap:wrap">
    <div style="flex:1;min-width:60px;background:#fff8e1;border-radius:6px;padding:5px 8px;text-align:center">
      <div style="font-size:0.58rem;color:#f57f17;font-weight:600">進場</div>
      <div style="font-size:0.84rem;font-weight:800;color:#f57f17">{e_str}</div>
    </div>
    <div style="flex:1;min-width:60px;background:#fce4ec;border-radius:6px;padding:5px 8px;text-align:center">
      <div style="font-size:0.58rem;color:#c62828;font-weight:600">停損</div>
      <div style="font-size:0.84rem;font-weight:800;color:#c62828">{stop_p:.1f}</div>
      <div style="font-size:0.58rem;color:#c62828">{stop_pct}%</div>
    </div>
    <div style="flex:1;min-width:60px;background:#e8f5e9;border-radius:6px;padding:5px 8px;text-align:center">
      <div style="font-size:0.58rem;color:#2e7d32;font-weight:600">目標</div>
      <div style="font-size:0.84rem;font-weight:800;color:#2e7d32">{t1:.1f}{t2_str}</div>
      <div style="font-size:0.58rem;color:#2e7d32">+{t1_pct}%</div>
    </div>
    <div style="flex:1;min-width:60px;background:#e3f2fd;border-radius:6px;padding:5px 8px;text-align:center">
      <div style="font-size:0.58rem;color:#1565c0;font-weight:600">R/R</div>
      <div style="font-size:0.84rem;font-weight:800;color:{rr_col}">{rr}x</div>
    </div>
  </div>
</div>"""
    elif entry_low and entry_high and is_buy:
        plan_html = f"""
<div style="background:#fff8e1;border-left:3px solid #f57f17;border-radius:0 6px 6px 0;padding:7px 11px;margin:8px 0">
  <div style="font-size:0.62rem;font-weight:700;color:#e65100;margin-bottom:2px">進場區間</div>
  <div style="font-size:0.95rem;font-weight:800;color:#e65100">NT$ {entry_low:.1f} – {entry_high:.1f}</div>
  <div style="font-size:0.62rem;color:#bf360c;margin-top:2px">停損 / 目標數據待補全</div>
</div>"""

    # ── Invalidation ──────────────────────────────────────────────
    inv_html = ""
    inv_items = (thesis.get("invalidations") or []) if thesis else []
    if inv_items:
        inv_rows = "".join(
            f'<div style="color:#c62828;font-size:0.75rem;padding:1px 0">❌ {inv}</div>'
            for inv in inv_items
        )
        inv_html = f"""
<div style="background:#fff8f8;border-left:3px solid #ef9a9a;padding:8px 12px;margin:10px 0;border-radius:0 6px 6px 0">
  <div style="font-size:0.62rem;font-weight:700;color:#b71c1c;letter-spacing:.05em;margin-bottom:5px">什麼情況代表判斷錯了</div>
  {inv_rows}
  <div style="font-size:0.7rem;color:#888;margin-top:5px;font-style:italic">{card.invalidation_text}</div>
</div>"""

    # ── Evidence 1-liner ──────────────────────────────────────────
    ev_summary_html = (
        f'<div style="font-size:0.72rem;color:#546e7a;margin-top:6px;font-style:italic">'
        f"📊 {card.evidence_summary}</div>"
        if card.evidence_summary
        else ""
    )

    # ── Price source label (Phase 3) ──────────────────────────────
    _price_date = r.get("price_date")
    _price_val  = r.get("price")
    if _price_date and _price_val:
        _price_src_label = (
            f'<span style="font-size:0.6rem;color:#aaa;margin-left:5px">'
            f'{_price_date.strftime("%m/%d")} 收盤</span>'
        )
    else:
        _price_src_label = ""

    # ── Level 1: Main card ────────────────────────────────────────
    st.html(f"""
<div style="border:1px solid #e0e0e0;border-radius:12px;padding:16px 18px;margin-bottom:4px;background:#fff">

  <!-- Header -->
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
    <div>
      <span style="font-size:1.1rem;font-weight:800;color:#1a1a2e">{card.name}</span>
      <span style="font-size:0.78rem;font-weight:400;color:#888;margin-left:6px">{card.sid}</span>
      {consec_html}
      <div style="font-size:1rem;font-weight:700;color:#333;margin-top:2px">{card.price_str}{_price_src_label}</div>
    </div>
    <div style="text-align:right">
      <span style="background:{card.signal_bg};color:{card.signal_col};font-weight:800;font-size:0.95rem;padding:5px 14px;border-radius:20px">{dl["label"]}</span>
    </div>
  </div>

  <!-- 白話解釋 -->
  <div style="background:#f0f4ff;border-left:3px solid #667eea;border-radius:0 8px 8px 0;
              padding:9px 13px;font-size:0.79rem;color:#333;line-height:1.65;margin-bottom:8px">
    <span style="font-weight:700;color:#667eea">💬 為什麼</span><br>
    {card.why_html}
  </div>

  {ev_summary_html}

  <!-- 交易計畫 -->
  {plan_html}

  <!-- 什麼情況代表判斷錯了 -->
  {inv_html}

  <!-- 模型資訊 -->
  <div style="font-size:0.62rem;color:#ccc;margin-top:10px;border-top:1px solid #f5f5f5;padding-top:6px;line-height:1.6">
    {card.setup_label}　分析品質 {card.conf:.0f} / 100　{card.level} 級
  </div>

</div>""")

    # ── Level 2: 為什麼這樣判斷？ ────────────────────────────────
    with st.expander("🔍 為什麼這樣判斷？", expanded=False):
        if card.pro_judgment:
            st.caption(card.pro_judgment)

        # Checklist (WAIT only)
        if card.checklist and not is_buy:
            _rows = "".join(
                f'<div style="display:flex;gap:8px;align-items:center;padding:2px 0">'
                f'<span style="width:20px">{icon}</span>'
                f'<span style="width:50px;font-weight:600;font-size:0.76rem;color:#333">{lbl}</span>'
                f'<span style="font-size:0.76rem;color:#555">{val}</span>'
                f"</div>"
                for icon, lbl, val in card.checklist
            )
            _conclusion_html = (
                f'<div style="margin-top:8px;font-size:0.75rem;color:#37474f;line-height:1.65;'
                f'border-top:1px solid #e0e0e0;padding-top:7px">{card.checklist_conclusion}</div>'
                if card.checklist_conclusion
                else ""
            )
            st.html(f"""
<div style="background:#f8f9fa;border-radius:8px;padding:10px 12px;margin:10px 0">
  <div style="font-size:0.62rem;font-weight:700;color:#78909c;letter-spacing:.05em;margin-bottom:6px">現在還差什麼</div>
  {_rows}
  {_conclusion_html}
</div>""")

        # Triggers (WAIT only)
        if not is_buy and triggers:
            _trig_rows = "".join(
                f'<div style="padding:2px 0;font-size:0.76rem;color:#37474f">{t}</div>'
                for t in triggers
            )
            st.html(f"""
<div style="background:#fafafa;border-left:3px solid #90a4ae;padding:8px 12px;margin:8px 0;border-radius:0 6px 6px 0">
  <div style="font-size:0.62rem;font-weight:700;color:#546e7a;letter-spacing:.05em;margin-bottom:5px">轉為 BUY 的條件</div>
  {_trig_rows}
</div>""")

        # Scenarios
        if card.scenarios:
            _sc_rows = "".join(
                f'<div style="display:flex;gap:8px;align-items:flex-start;padding:5px 0;'
                f'border-bottom:1px solid #f0f0f0">'
                f'<span style="font-size:0.95rem;flex-shrink:0;line-height:1.4">{icon}</span>'
                f'<div><div style="font-weight:700;font-size:0.74rem;color:#333">{lbl}</div>'
                f'<div style="font-size:0.72rem;color:#555;margin-top:1px;line-height:1.5">{desc}</div></div>'
                f"</div>"
                for icon, lbl, desc in card.scenarios
            )
            st.html(f"""
<div style="background:#fafafa;border:1px solid #e8eaf0;border-radius:8px;padding:10px 12px;margin:8px 0 4px">
  <div style="font-size:0.62rem;font-weight:700;color:#78909c;letter-spacing:.05em;margin-bottom:6px">未來可能怎麼走</div>
  {_sc_rows}
</div>""")

        # Evidence panel (Research + Forward)
        if setup != "none" and signal != "sell":
            _re_ev = _ev.get("research", {})
            _fe_ev = _ev.get("forward", {})
            _narrative = _ev.get("narrative", "")
            _r_n = _re_ev.get("n", 0)
            _r_tier_emoji = _re_ev.get("tier_emoji", "🔴")
            _r_tier_label = _re_ev.get("tier_label", "樣本不足")
            _f_total = _fe_ev.get("total_recorded", 0)
            _f_m20 = _fe_ev.get("matured_20d", 0)
            _f_m60 = _fe_ev.get("matured_60d", 0)
            _f_tier_emoji = _fe_ev.get("tier_emoji", "🔴")
            _f_tier_label = _fe_ev.get("tier_label", "尚無 OOS 資料")
            _r_wr = _re_ev.get("alpha_20d", {}).get("winrate")
            _r_detail = (
                f"（{_r_n} 筆，20D 勝率 {_r_wr:.0f}%）"
                if (_r_n >= 10 and _r_wr is not None)
                else f"（{_r_n} 筆）"
            )
            _narrative_html = (
                f'<div style="font-size:0.73rem;color:#555;margin-top:7px;font-style:italic">💬 {_narrative}</div>'
                if _narrative
                else ""
            )
            st.html(
                f'<div style="background:#f8f9fa;border:1px solid #e0e0e0;border-radius:8px;'
                f'padding:10px 14px;margin-bottom:8px">'
                f'<div style="font-size:0.65rem;color:#888;font-weight:700;letter-spacing:.05em;margin-bottom:6px">驗證強度</div>'
                f'<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:0.76rem;color:#333">'
                f"<span>🧪 Research：{_r_tier_emoji} {_r_tier_label} {_r_detail}</span>"
                f"<span>🔒 Forward：{_f_tier_emoji} {_f_tier_label}（20D 成熟 {_f_m20} 筆）</span>"
                f"</div>{_narrative_html}</div>"
            )
            with st.expander("📊 過去類似情境（歷史統計參考）"):
                st.caption(
                    "此為歷史類似情境統計，不是 Out-of-Sample 證據，也不是未來價格預測。"
                )
                _analog_html = _historical_analog_html(_ev)
                if _analog_html:
                    st.html(_analog_html)
                st.divider()
                st.markdown("**🧪 Research In-Sample 統計**")
                if _r_n < 10:
                    st.caption(
                        f"{_r_tier_emoji} 樣本不足（{_r_n} 筆），無法計算可靠統計。"
                    )
                else:
                    r20 = _re_ev.get("alpha_20d", {})
                    r60 = _re_ev.get("alpha_60d", {})
                    c1, c2 = st.columns(2)
                    with c1:
                        st.metric("類似情境", f"{_r_n} 次")
                        if r20.get("mean") is not None:
                            st.metric("20D Alpha 均值", f"{r20['mean']:+.1f}%")
                        if r60.get("mean") is not None:
                            st.metric("60D Alpha 均值", f"{r60['mean']:+.1f}%")
                    with c2:
                        if r20.get("winrate") is not None:
                            st.metric("20D 勝率", f"{r20['winrate']:.0f}%")
                        if r60.get("winrate") is not None:
                            st.metric("60D 勝率", f"{r60['winrate']:.0f}%")
                    st.caption(f"證據強度：{_r_tier_emoji} {_r_tier_label}")
                st.divider()
                st.markdown("**🔒 Forward Validation（真實 OOS）**")
                c3, c4 = st.columns(2)
                with c3:
                    st.metric("已記錄訊號", f"{_f_total} 筆")
                    st.metric("20D 已成熟", f"{_f_m20} 筆")
                    if _f_m20 >= 10:
                        f20 = _fe_ev.get("alpha_20d", {})
                        if f20.get("mean") is not None:
                            st.metric("20D Alpha", f"{f20['mean']:+.1f}%")
                with c4:
                    st.metric("60D 已成熟", f"{_f_m60} 筆")
                    if _f_m20 >= 10:
                        f20 = _fe_ev.get("alpha_20d", {})
                        if f20.get("winrate") is not None:
                            st.metric("20D 勝率", f"{f20['winrate']:.0f}%")
                if _f_m20 < 10:
                    st.caption(
                        f"{_f_tier_emoji} Forward 樣本累積中（{_f_m20} 筆 20D 已成熟）"
                    )
                else:
                    st.caption(f"證據強度：{_f_tier_emoji} {_f_tier_label}")

    # ── Level 2: 部位試算 (BUY only) ──────────────────────────────
    if is_buy and price and stop_p and t1 and price > stop_p:
        with st.expander("💰 部位試算", expanded=False):
            from config import POSITION_SIZING as _PS_CFG

            capital = st.session_state.get("ps_capital", _PS_CFG["capital_ntd"])
            max_risk_pct = st.session_state.get(
                "ps_max_risk_pct", _PS_CFG["max_risk_pct"]
            )
            ps = _ps(
                entry=price,
                stop=stop_p,
                capital=capital,
                max_risk_pct=max_risk_pct,
                max_single_pct=_PS_CFG["max_single_pct"],
                lot_size=_PS_CFG["lot_size"],
            )
            if ps and ps.get("lots", 0) == 0 and ps.get("min_lot_ntd"):
                st.warning(
                    f"1張需 NT${ps['min_lot_ntd']:,}，超出曝險上限，無法試算部位。"
                )
            elif ps and ps.get("lots", 0) > 0:
                cap_note = "（已達曝險上限）" if ps["capped"] else ""
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("建議張數", f"{ps['lots']} 張{cap_note}")
                with c2:
                    st.metric("部位金額", f"NT${ps['position_ntd']:,}")
                with c3:
                    st.metric("實際風險", f"NT${ps['actual_risk_ntd']:,}")
                st.caption(f"風控 {max_risk_pct}% ／ 資金 NT${capital:,.0f}")

            if portfolio_exposure:
                try:
                    from src.services.portfolio_risk_service import (
                        portfolio_context_for_stock,
                    )

                    ctx = portfolio_context_for_stock(
                        r.get("industry"), portfolio_exposure
                    )
                    if ctx.get("message"):
                        if ctx["should_warn"]:
                            st.warning(f"組合角度：{ctx['message']}")
                        else:
                            st.success(f"組合角度：{ctx['message']}")
                except Exception:
                    pass

    # ── Level 3: 專業數據 / Raw Data ──────────────────────────────
    with st.expander("🧪 專業數據 / Raw Data", expanded=False):
        st.caption(card.tech_metrics)

        if card.pt_val >= 70:
            t_lbl, t_col, t_bg = "偏強", "#2e7d32", "#e8f5e9"
        elif card.pt_val >= 50:
            t_lbl, t_col, t_bg = "普通", "#f57f17", "#fff8e1"
        else:
            t_lbl, t_col, t_bg = "偏弱", "#c62828", "#ffebee"

        _n_fin_pos, _n_fin_neg = len(card.fin_adv), len(card.fin_risk)
        if _n_fin_pos == 0 and _n_fin_neg == 0:
            f_lbl, f_col, f_bg = "—", "#888", "#f5f5f5"
        elif _n_fin_pos > _n_fin_neg:
            f_lbl, f_col, f_bg = "改善", "#2e7d32", "#e8f5e9"
        elif _n_fin_neg > _n_fin_pos:
            f_lbl, f_col, f_bg = "惡化", "#c62828", "#ffebee"
        else:
            f_lbl, f_col, f_bg = "穩定", "#1565c0", "#e3f2fd"

        _tech_rows = "".join(
            f'<div style="color:#2e7d32">✓ {a}</div>' for a in card.tech_adv[:3]
        ) + "".join(
            f'<div style="color:#c62828">⚠ {x}</div>' for x in card.tech_risk[:2]
        )
        _fin_rows = "".join(
            f'<div style="color:#2e7d32">✓ {a}</div>' for a in card.fin_adv[:3]
        ) + "".join(
            f'<div style="color:#c62828">⚠ {x}</div>' for x in card.fin_risk[:2]
        )

        st.html(f"""
<div style="margin-bottom:10px">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
    <span style="font-size:0.68rem;font-weight:700;color:#90a4ae;letter-spacing:.06em">技術面</span>
    <span style="background:{t_bg};color:{t_col};font-size:0.63rem;font-weight:700;padding:1px 8px;border-radius:10px">{t_lbl}</span>
  </div>
  <div style="font-size:0.76rem;line-height:1.65;padding-left:4px">{_tech_rows}</div>
  <div style="font-size:0.7rem;color:#666;margin-top:4px;font-style:italic">{card.plain_tech}</div>
</div>
<div style="margin-bottom:12px">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
    <span style="font-size:0.68rem;font-weight:700;color:#90a4ae;letter-spacing:.06em">基本面</span>
    <span style="background:{f_bg};color:{f_col};font-size:0.63rem;font-weight:700;padding:1px 8px;border-radius:10px">{f_lbl}</span>
  </div>
  <div style="font-size:0.76rem;line-height:1.65;padding-left:4px">{_fin_rows}</div>
  <div style="font-size:0.7rem;color:#666;margin-top:4px;font-style:italic">{card.plain_fundamental}</div>
</div>""")

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

        _conclusion = r.get("conclusion", "")
        if _conclusion:
            st.markdown(f"> {_conclusion}")

        _missing_raw = r.get("missing_data_factors") or ""
        _missing_list = (
            [f for f in _missing_raw.split(",") if f] if _missing_raw else []
        )
        _factor_label = {"quality": "基本面", "behavior": "籌碼"}
        if _missing_list:
            _nominal_weights = {"quality": 20, "behavior": 15}
            _missing_pct = sum(_nominal_weights.get(f, 0) for f in _missing_list)
            _completeness = 100 - _missing_pct
            _warn_items = "　".join(
                f"⚠️ {_factor_label.get(f, f)} 資料缺失" for f in _missing_list
            )
            _rw_note = "　".join(
                f"{_factor_label.get(f, f)} {_nominal_weights.get(f, 0)}% → 重分配至技術面"
                for f in _missing_list
            )
            st.html(
                f'<div style="background:#fff8e1;border:1px solid #ffe082;border-radius:7px;'
                f'padding:8px 12px;margin-bottom:8px">'
                f'<span style="font-size:0.68rem;color:#f57f17;font-weight:700">資料完整度 {_completeness}%</span>'
                f'<span style="font-size:0.68rem;color:#e65100;margin-left:10px">{_warn_items}</span>'
                f'<div style="font-size:0.63rem;color:#9e9e9e;margin-top:3px">{_rw_note}；此分數與完整資料的同分標的可信度不同</div>'
                f"</div>"
            )

        if card.dq_str:
            st.caption(card.dq_str)


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
        recs_cnt = (
            _s.execute(
                _text(
                    "SELECT COUNT(*) FROM recommendations WHERE date=:d AND tier='recommend' AND is_valid IS NOT FALSE"
                ),
                {"d": selected_date},
            ).scalar()
            or 0
        )
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

    # Phase 4: data health — auto-redirect to latest available date
    latest_data_date = load_latest_completed_date()

    if not report:
        if latest_data_date and latest_data_date != selected_date:
            st.info(
                f"**尚無 {selected_date} 的分析報告。**  \n"
                f"資料庫最新完成日期：**{latest_data_date}**"
            )
            if st.button(
                f"切換至 {latest_data_date} 的分析結果",
                type="primary",
                key="auto_redirect_btn",
            ):
                st.session_state["selected_date"] = latest_data_date
                st.rerun()
        else:
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

    # Phase 2+3+4: 今日交易參考
    _render_trading_reference(selected_date, recs, latest_data_date)

    # P2: Pipeline funnel
    funnel = load_pipeline_funnel(selected_date)
    if funnel:
        universe = funnel.get("universe", 0)
        with_price = funnel.get("with_price", 0)
        hf_pass = funnel.get("hard_filter_pass", 0)
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
    _h_mstatus = health.get("market_status", "TRADING_DAY")
    _h_last_td = health.get("last_trading_day")

    if _h_level == "closed":
        # ── 休市日專用 banner ───────────────────────────────────
        _is_holiday = _h_mstatus == "HOLIDAY"
        _closed_label = "國定假日" if _is_holiday else "週末"
        _last_td_str = _h_last_td.strftime("%Y/%m/%d") if _h_last_td else "—"
        _note = ""
        if recs:
            _note = (
                f'<div style="font-size:0.74rem;color:#5d4037;margin-top:8px;'
                f'background:#fff3e0;border-radius:6px;padding:5px 10px">'
                f"⚠️ 以下顯示的是 <b>{_last_td_str}</b> 的歷史收盤分析，"
                f"<b>不是 {selected_date} 的新交易訊號</b>。</div>"
            )
        st.markdown(
            f"""
<div style="background:#e8f5e9;border:1.5px solid #a5d6a7;border-radius:10px;padding:12px 16px;margin:8px 0 12px">
  <div style="font-size:1.05rem;font-weight:800;color:#2e7d32;margin-bottom:4px">🟢 今日台股{_closed_label}休市</div>
  <div style="font-size:0.82rem;color:#388e3c">最近有效交易日：<b>{_last_td_str}</b></div>
  {_note}
</div>""",
            unsafe_allow_html=True,
        )

    elif _h_level in ("red", "yellow"):
        # ── 交易日異常 banner ───────────────────────────────────
        _h_regime = health.get("regime", "neutral")
        _h_pass = health.get("pass_rate", 0.0)
        _h_conds = health.get("conditions", [])
        _h_color = "#c62828" if _h_level == "red" else "#f57f17"
        _h_bg = "#ffebee" if _h_level == "red" else "#fff8e1"
        _h_border = "#ef9a9a" if _h_level == "red" else "#ffe082"
        _h_icon = "🔴" if _h_level == "red" else "🟡"
        _h_title = "今日不建議交易" if _h_level == "red" else "今日交易需審慎"
        _cond_html = "".join(
            f'<li style="font-size:0.77rem;margin-bottom:2px">{c}</li>'
            for c in _h_conds
        )
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
        current_regime = load_current_regime()
        try:
            from dashboard.loaders import load_portfolio_exposure as _lpe

            portfolio_exposure = _lpe()
        except Exception:
            portfolio_exposure = {}
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
            sc5 = opp.get("score_change_5d")
            tc5 = opp.get("timing_change_5d")
            bc5 = opp.get("behavior_change_5d")
            sc5_str = f"{sc5:+.1f}" if sc5 is not None else "—"
            tc5_str = f"{tc5:+.1f}" if tc5 is not None else "—"
            bc5_str = f"{bc5:+.1f}" if bc5 is not None else "—"

            def _badge(label, val, val_str, threshold=5):
                bg = "#e65100" if val and val >= threshold else "#37474f"
                arrow = "▲ " if val and val > 0 else ""
                return f'<span style="background:{bg};color:#fff;border-radius:4px;padding:2px 7px;font-size:0.68rem;font-weight:700">{arrow}{label} {val_str}</span>'

            badges = (
                _badge("總5D", sc5, sc5_str, 5)
                + " "
                + _badge("技術5D", tc5, tc5_str, 8)
                + " "
                + _badge("籌碼5D", bc5, bc5_str, 8)
            )
            total = opp.get("total_score", opp["scores"].get("total", 0))
            name = opp.get("name", "") or opp["sid"]
            sid = opp["sid"]
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
        with st.expander(
            f"📋 Watch List（{len(watch_recs_list)} 檔，當日相對最強、待觀察）"
        ):
            for w in watch_recs_list:
                sc5 = w.get("score_change_5d")
                sc5_str = f"（5D {sc5:+.1f}）" if sc5 is not None else ""
                display_name = (
                    f"{w['name']}（{w['sid']}）" if w["name"] != w["sid"] else w["sid"]
                )
                st.markdown(
                    f"**{display_name}** — 綜合 {w['total_score']:.0f} | "
                    f"技術 {w['timing_score']:.0f} | 籌碼 {w['behavior_score']:.0f} | "
                    f"品質 {w['confidence']:.0f}{sc5_str}"
                )
