"""
pages/overview.py — 今日分析頁（今日推薦 + 市場摘要 + Watch List）
"""

import logging
import re
from datetime import date

import streamlit as st

from dashboard.loaders import (
    load_analysis_results,
    load_candidate_pool_data,
    load_current_regime,
    load_db_recommendations,
    load_evidence_stats,
    load_exec_logs,
    load_latest_completed_date,
    load_market_health,
    load_pipeline_funnel,
    load_report,
    load_stock_names,
    load_stock_prices,
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
        freshness_html = f"""
<div style="font-size:15px;color:#ffb74d;margin-top:12px;padding:9px 14px;
            background:rgba(255,183,77,0.12);border-radius:8px;border-left:3px solid #ff8c00;
            line-height:1.5">
  ⚠️ 此訊號已有 <strong>{days_old}</strong> 天，次日進場窗口可能已過。
</div>"""
    elif latest_date and latest_date > selected_date:
        freshness_html = f"""
<div style="font-size:15px;color:#80cbc4;margin-top:12px;padding:9px 14px;
            background:rgba(128,203,196,0.1);border-radius:8px;border-left:3px solid #4db6ac;
            line-height:1.5">
  🔄 資料庫最新分析：<strong>{latest_date}</strong>（側邊欄可切換日期）
</div>"""

    # — signal processing —
    buy_recs = [r for r in recs if (r.get("trade_signal") or "").lower() in ("buy", "strong_buy")]
    wait_recs = [r for r in recs if (r.get("trade_signal") or "").lower() == "wait"]

    sig_html = ""
    if buy_recs:
        desktop_rows = ""
        mobile_cards = ""

        for r in buy_recs:
            name       = r.get("name") or r.get("sid", "—")
            sid        = r.get("sid", "")
            entry_low  = r.get("entry_low")
            entry_high = r.get("entry_high")
            stop_p     = r.get("stop_price")
            t1         = r.get("target1")
            ma20_gap   = r.get("ma20_gap")
            price      = r.get("price")
            price_date = r.get("price_date")

            chase_badge = ""
            if ma20_gap is not None and abs(ma20_gap) > chase_gap:
                chase_badge = (
                    '<span style="font-size:13px;color:#ff7043;background:rgba(255,112,67,0.2);'
                    'padding:2px 8px;border-radius:10px;margin-left:8px;white-space:nowrap">'
                    "⚡ 高乖離</span>"
                )

            price_note = ""
            if price:
                src = "前收盤" if (price_date and price_date < selected_date) else "收盤"
                price_note = (
                    f'<span style="font-size:13px;opacity:0.55;margin-left:7px;font-weight:400">'
                    f"{src} {price:.1f}</span>"
                )

            if entry_low and entry_high:
                entry_str = f"{entry_low:.1f}–{entry_high:.1f}"
            elif entry_low:
                entry_str = f"≥{entry_low:.1f}"
            else:
                entry_str = "—"
            stop_str = f"{stop_p:.1f}" if stop_p else "—"
            t1_str   = f"{t1:.1f}"    if t1    else "—"

            # desktop row
            desktop_rows += f"""
<tr style="border-bottom:1px solid rgba(255,255,255,0.06)">
  <td style="padding:12px 24px 12px 0;vertical-align:top;white-space:nowrap">
    <div style="font-size:19px;font-weight:700;color:#fff;line-height:1.2">
      {name}{price_note}
    </div>
    <div style="font-size:13px;color:rgba(255,255,255,0.42);margin-top:3px">
      {sid}{chase_badge}
    </div>
  </td>
  <td style="padding:12px 24px 12px 0;vertical-align:top">
    <div style="font-size:21px;font-weight:700;color:#00e5ff;line-height:1.2">{entry_str}</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.38);margin-top:3px">NT$</div>
  </td>
  <td style="padding:12px 24px 12px 0;vertical-align:top">
    <div style="font-size:19px;font-weight:600;color:#ef9a9a;line-height:1.2">{stop_str}</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.38);margin-top:3px">NT$</div>
  </td>
  <td style="padding:12px 0;vertical-align:top">
    <div style="font-size:19px;font-weight:600;color:#a5d6a7;line-height:1.2">{t1_str}</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.38);margin-top:3px">NT$</div>
  </td>
</tr>"""

            # mobile card
            mobile_cards += f"""
<div style="background:rgba(255,255,255,0.07);border-radius:10px;padding:16px;margin-bottom:12px">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
    <div>
      <div style="font-size:19px;font-weight:700;color:#fff;line-height:1.2">{name}</div>
      <div style="font-size:13px;color:rgba(255,255,255,0.45);margin-top:3px">{sid}{price_note}</div>
    </div>
    {f'<div style="margin-top:2px">{chase_badge}</div>' if chase_badge else ''}
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
    <div style="background:rgba(0,229,255,0.1);border:1px solid rgba(0,229,255,0.25);
                border-radius:8px;padding:10px;text-align:center">
      <div style="font-size:12px;color:#80deea;font-weight:600;margin-bottom:5px;letter-spacing:.03em">進場區間</div>
      <div style="font-size:17px;font-weight:700;color:#00e5ff;line-height:1.2">{entry_str}</div>
    </div>
    <div style="background:rgba(239,154,154,0.1);border:1px solid rgba(239,154,154,0.25);
                border-radius:8px;padding:10px;text-align:center">
      <div style="font-size:12px;color:#ef9a9a;font-weight:600;margin-bottom:5px;letter-spacing:.03em">停損</div>
      <div style="font-size:17px;font-weight:600;color:#ef9a9a;line-height:1.2">{stop_str}</div>
    </div>
    <div style="background:rgba(165,214,167,0.1);border:1px solid rgba(165,214,167,0.25);
                border-radius:8px;padding:10px;text-align:center">
      <div style="font-size:12px;color:#a5d6a7;font-weight:600;margin-bottom:5px;letter-spacing:.03em">目標1</div>
      <div style="font-size:17px;font-weight:600;color:#a5d6a7;line-height:1.2">{t1_str}</div>
    </div>
  </div>
</div>"""

        sig_html = f"""
<div style="margin-top:18px">
  <div style="font-size:16px;font-weight:600;color:rgba(255,255,255,0.65);
              margin-bottom:14px;letter-spacing:.02em">
    BUY 訊號 · {len(buy_recs)} 檔
  </div>
  <div class="trd-ref-desktop">
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.15)">
          <th style="text-align:left;padding:0 24px 10px 0;font-size:15px;font-weight:600;
                     color:rgba(255,255,255,0.5)">標的</th>
          <th style="text-align:left;padding:0 24px 10px 0;font-size:15px;font-weight:600;
                     color:rgba(255,255,255,0.5)">進場區間</th>
          <th style="text-align:left;padding:0 24px 10px 0;font-size:15px;font-weight:600;
                     color:rgba(255,255,255,0.5)">停損</th>
          <th style="text-align:left;padding:0 0 10px 0;font-size:15px;font-weight:600;
                     color:rgba(255,255,255,0.5)">目標1</th>
        </tr>
      </thead>
      <tbody>{desktop_rows}</tbody>
    </table>
  </div>
  <div class="trd-ref-mobile">{mobile_cards}</div>
</div>"""

    elif recs:
        wait_names = "、".join(
            r.get("name") or r.get("sid", "") for r in (wait_recs or recs)[:3]
        )
        sig_html = (
            f'<div style="margin-top:16px;font-size:17px;color:rgba(255,255,255,0.6);font-weight:500">'
            f"WAIT — {wait_names}</div>"
        )
    else:
        sig_html = (
            '<div style="margin-top:16px;font-size:17px;color:rgba(255,255,255,0.4)">'
            "今日無推薦標的</div>"
        )

    disclaimer = """
<div style="font-size:15px;color:#78909c;margin-top:16px;
            border-top:1px solid rgba(255,255,255,0.09);padding-top:14px;line-height:1.65">
  ⚠️ 所有報價為前一日收盤，非盤中即時報價。進場前請確認當日市場報價。
</div>"""

    responsive_css = """
<style>
  .trd-ref-desktop { display: block; }
  .trd-ref-mobile  { display: none;  }
  @media (max-width: 640px) {
    .trd-ref-desktop { display: none;  }
    .trd-ref-mobile  { display: block; }
  }
</style>"""

    st.markdown(
        f"""{responsive_css}
<div style="background:linear-gradient(140deg,#0d1b2a 0%,#1b263b 100%);border-radius:14px;
            padding:22px 26px 18px;margin:10px 0 18px;color:white;
            box-shadow:0 4px 16px rgba(0,0,0,0.3)">
  <div style="font-size:23px;font-weight:600;letter-spacing:.01em;margin-bottom:16px;
              line-height:1">今日交易參考</div>
  <div style="display:flex;gap:36px;flex-wrap:wrap">
    <div>
      <div style="font-size:15px;color:rgba(255,255,255,0.5);margin-bottom:5px">訊號分析日</div>
      <div style="font-size:21px;font-weight:700;color:#fff">{selected_date.strftime("%Y/%m/%d")}</div>
    </div>
    <div>
      <div style="font-size:15px;color:rgba(255,255,255,0.5);margin-bottom:5px">適用交易日</div>
      <div style="font-size:21px;font-weight:700;color:#00e5ff">{td_label}</div>
    </div>
  </div>
  {sig_html}
  {freshness_html}
  {disclaimer}
</div>""",
        unsafe_allow_html=True,
    )


def _render_candidate_pool(stock_prices: dict) -> None:
    """進場候選追蹤池 UI（取代原 New Opportunities + Watch List）。"""
    pool_data = load_candidate_pool_data()
    active = pool_data["active"]
    recent_exits = pool_data["recent_exits"]
    stats = pool_data["stats"]
    today_history = pool_data["today_history"]

    if not active and not recent_exits:
        st.info("候選追蹤池目前沒有記錄。系統正式上線後開始累積。")
        return

    # ── 狀態分組 ───────────────────────────────────────────────
    near_entry  = [c for c in active if c.status == "near_entry"]
    watching    = [c for c in active if c.status in ("watching", "overdue")]
    today_new   = [c for c in active if c.first_seen_date == c.last_checked_date]
    today_exited = [c for c in recent_exits if c.exit_date == (
        recent_exits[0].exit_date if recent_exits else None)]

    # ── 區塊標題 ───────────────────────────────────────────────
    if near_entry:
        st.markdown(
            f'<div class="section-title">接近進場條件（{len(near_entry)} 檔）</div>',
            unsafe_allow_html=True,
        )
        for c in near_entry:
            _render_candidate_card(c, today_history, stock_prices, highlight=True)

    if watching:
        st.markdown(
            f'<div class="section-title">觀察中（{len(watching)} 檔）</div>',
            unsafe_allow_html=True,
        )
        for c in watching:
            _render_candidate_card(c, today_history, stock_prices, highlight=False)

    if today_new:
        new_names = "、".join(
            (c.stock_name or c.stock_id) for c in today_new[:5]
        )
        extra = f"等 {len(today_new)} 檔" if len(today_new) > 5 else f"{len(today_new)} 檔"
        st.caption(f"今日新進候選：{new_names}（{extra}）")

    if not active:
        st.info("目前沒有符合追蹤條件的候選股票。")

    # ── 今日退出 ────────────────────────────────────────────────
    if recent_exits:
        latest_exit_date = max(c.exit_date for c in recent_exits if c.exit_date)
        today_exit_list  = [c for c in recent_exits if c.exit_date == latest_exit_date]
        if today_exit_list:
            with st.expander(f"今日退出與退出原因（{len(today_exit_list)} 檔）"):
                for c in today_exit_list:
                    reason_map = {
                        "TRIGGERED_BUY":   "正式 BUY 觸發",
                        "THESIS_FAILED":   "技術型態失效或賣出訊號",
                        "EXPIRED":         f"觀察滿 {c.trading_days_watched} 交易日未觸發 BUY",
                        "NOT_IN_UNIVERSE": "不再出現於分析宇宙",
                    }
                    raw_reason = c.exit_reason or ""
                    reason_key = raw_reason.split(":")[0] if ":" in raw_reason else raw_reason
                    reason_text = reason_map.get(reason_key, raw_reason or "—")
                    icon = "✅" if reason_key == "TRIGGERED_BUY" else "❌"
                    name = c.stock_name or c.stock_id
                    st.markdown(
                        f"{icon} **{name}**（{c.stock_id}）— "
                        f"退出：{reason_text}  ·  "
                        f"觀察 {c.trading_days_watched or 0} 個交易日"
                    )

    # ── 追蹤統計（折疊）──────────────────────────────────────────
    if stats["n_total"] > 0:
        with st.expander("候選追蹤統計"):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("累計入池", stats["n_total"])
            col2.metric("觀察中", stats["n_active"])
            col3.metric("已觸發 BUY", stats["n_buy"])
            col4.metric("已失效／逾期", stats["n_exited"])
            if stats["sufficient_data"]:
                col_a, col_b = st.columns(2)
                col_a.metric(
                    "平均等待交易日",
                    f"{stats['avg_wait_days']:.1f}" if stats["avg_wait_days"] else "—"
                )
                col_b.metric(
                    "BUY 轉換率",
                    f"{stats['conversion_rate']:.1f}%" if stats["conversion_rate"] else "—",
                    help="分母 = 已完成週期（觸發BUY + 失效退出），不含仍在觀察的候選",
                )
            else:
                st.caption("資料累積中（需 ≥ 5 個完成週期才計算轉換率）")
            st.caption(
                "⚠️ 以上為候選池追蹤指標，不等於策略交易績效。"
                "正式績效請見 Evidence Dashboard。"
            )


def _render_candidate_card(cand, today_history: dict, stock_prices: dict,
                           highlight: bool = False) -> None:
    """渲染單一候選卡片。"""
    name = cand.stock_name or cand.stock_id
    sid = cand.stock_id
    price = stock_prices.get(sid)
    price_str = f"NT$ {price:,.1f}" if price else "—"

    days = cand.trading_days_watched or 0
    overdue = cand.status == "overdue"

    # 狀態徽章
    status_badges = {
        "near_entry": ('<span style="background:#e65100;color:#fff;border-radius:4px;'
                       'padding:2px 8px;font-size:0.68rem;font-weight:700">接近進場</span>', "#1a1a2e", "#e65100"),
        "watching":   ('<span style="background:#1565c0;color:#fff;border-radius:4px;'
                       'padding:2px 8px;font-size:0.68rem;font-weight:700">觀察中</span>', "#0d0d1a", "#1565c0"),
        "overdue":    ('<span style="background:#5d4037;color:#fff;border-radius:4px;'
                       'padding:2px 8px;font-size:0.68rem;font-weight:700">觀察逾期</span>', "#0d0d1a", "#5d4037"),
    }
    badge_html, bg_color, border_color = status_badges.get(
        cand.status, ('', "#0d0d1a", "#444")
    )

    # 觀察天數顯示
    overdue_warn = f' <span style="color:#ff7043;font-size:0.7rem">（逾期）</span>' if overdue else ""
    days_str = f"已觀察 {days} 個交易日{overdue_warn}"

    # 今日變化
    history = today_history.get(cand.id)
    change_text = history.change_notes if history else "—"
    change_is_new = change_text == "新進候選追蹤池"
    change_color = "#4caf50" if change_is_new else "#90a4ae"

    # 為什麼值得觀察（entry_reason）
    watch_why = cand.entry_reason or "—"

    # 還差什麼（missing conditions）
    missing = cand.current_missing_conditions or "持續觀察各項技術指標"

    # 退出條件說明
    exit_cond_map = {
        "breakout":     "突破失敗、量縮回落或型態轉為 breakdown",
        "near_breakout": "突破失敗、下跌跌破近期低點或訊號轉賣",
        "pullback_buy": "跌破 MA10/MA20 且無力收復",
        "pullback_hold": "跌破 MA20 收盤",
        "trending":     "趨勢結構破壞（跌破 MA60 或 breakdown 型態）",
    }
    exit_when = exit_cond_map.get(
        cand.entry_setup_type or "none",
        f"達第 20 個交易日仍無 BUY 訊號，或技術型態失效"
    )

    score_str = f"{cand.latest_total_score:.0f}" if cand.latest_total_score else "—"

    st.markdown(
        f"""
<div style="background:{bg_color};border:1px solid {border_color};border-radius:8px;
     padding:12px 16px;margin-bottom:8px">
  <div style="display:flex;justify-content:space-between;align-items:center;
       flex-wrap:wrap;gap:6px;margin-bottom:8px">
    <div>
      {badge_html}
      <span style="font-weight:700;font-size:1rem;color:#f0f6fc;margin-left:8px">{name}</span>
      <span style="color:#aaa;font-size:0.75rem;margin-left:6px">{sid} · {price_str}</span>
    </div>
    <span style="color:#90a4ae;font-size:0.72rem">{days_str}</span>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:0.78rem">
    <div>
      <div style="color:#78909c;font-size:0.65rem;text-transform:uppercase;
           letter-spacing:.04em;margin-bottom:2px">為什麼值得觀察</div>
      <div style="color:#cfd8dc">{watch_why}</div>
    </div>
    <div>
      <div style="color:#78909c;font-size:0.65rem;text-transform:uppercase;
           letter-spacing:.04em;margin-bottom:2px">距離 BUY 還差什麼</div>
      <div style="color:#ffe082">{missing}</div>
    </div>
    <div>
      <div style="color:#78909c;font-size:0.65rem;text-transform:uppercase;
           letter-spacing:.04em;margin-bottom:2px">今日變化</div>
      <div style="color:{change_color}">{change_text}</div>
    </div>
    <div>
      <div style="color:#78909c;font-size:0.65rem;text-transform:uppercase;
           letter-spacing:.04em;margin-bottom:2px">退出條件</div>
      <div style="color:#ef9a9a;font-size:0.72rem">{exit_when}</div>
    </div>
  </div>
  <div style="margin-top:6px;color:#546e7a;font-size:0.68rem">
    綜合 {score_str} 分 · 型態：{cand.latest_setup_type or "—"} ·
    首次入池：{cand.first_seen_date}
  </div>
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

    # ── MA20 乖離率白話 note ──────────────────────────────────────
    from config import ENTRY_QUALITY as _EQ
    _chase_gap = _EQ.get("chase_gap_pct", 5.0)
    _ma_gap = card.ma20_gap
    if _ma_gap > _chase_gap:
        _ma_border = "#ff7043"
        _ma_gap_color = "#e64a19"
        _ma_desc = f"目前股價高於月線 {_ma_gap:.1f}%，已偏離均線較遠，留意追高風險。"
        _chase_html = (
            '<div style="margin-top:6px;font-size:0.76rem;color:#bf360c;'
            'background:rgba(255,112,67,0.08);padding:6px 8px;border-radius:4px;line-height:1.6">'
            '⚠️ <b>什麼是追高？</b> 股票已漲一段，才在相對高位買進，可能剛買就遇到回跌。<br>'
            '好股票不等於好買點。即使模型顯示強買，也需確認進場價格與停損風險。</div>'
        ) if is_buy else ""
    elif _ma_gap > 1.0:
        _ma_border = "#90a4ae"
        _ma_gap_color = "#546e7a"
        _ma_desc = f"目前股價高於月線 {_ma_gap:.1f}%，偏離適中，注意進場節奏。"
        _chase_html = ""
    elif _ma_gap >= -1.0:
        _ma_border = "#b0bec5"
        _ma_gap_color = "#78909c"
        _ma_desc = "股價接近月線，目前價格與近期均價差距不大。"
        _chase_html = ""
    else:
        _ma_border = "#7986cb"
        _ma_gap_color = "#5c6bc0"
        _ma_desc = f"目前股價低於月線 {abs(_ma_gap):.1f}%，短期走勢可能偏弱，需搭配趨勢與支撐判斷。"
        _chase_html = ""

    _ma_note_html = f"""
<div style="border-left:3px solid {_ma_border};background:#f9f9f9;padding:8px 12px;
            margin:8px 0;border-radius:0 6px 6px 0;line-height:1.55">
  <div style="font-size:0.68rem;font-weight:700;color:#78909c;letter-spacing:.04em;margin-bottom:3px">
    📐 MA20 月線乖離率 <span style="color:{_ma_gap_color};font-weight:800">{_ma_gap:+.1f}%</span>
  </div>
  <div style="font-size:0.76rem;color:#546e7a;line-height:1.55">
    MA20 是過去 20 個交易日的平均股價（月線）。{_ma_desc}
  </div>
  {_chase_html}
</div>"""

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

  <!-- MA20 乖離率 & 追高說明 -->
  {_ma_note_html}

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
            # Vol ratio plain-language note
            _vr = card.vol_ratio
            if _vr > 0:
                if _vr >= 1.5:
                    _vol_note = f"成交量為近 20 日均量的 {_vr:.1f} 倍，交易活躍；但量能放大不等於突破確認，仍需配合價格突破壓力位置。"
                elif _vr >= 1.0:
                    _vol_note = f"成交量為近 20 日均量的 {_vr:.1f} 倍，量能接近均量水準，尚無明顯放量。"
                else:
                    _vol_note = f"成交量為近 20 日均量的 {_vr:.1f} 倍（縮量），若要突破確認通常需要放量配合。"
                st.caption(f"📊 量能說明：{_vol_note}")

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
                st.html(f"""
<style>
@media (max-width: 640px) {{
  .ps-grid {{ grid-template-columns: 1fr !important; }}
}}
</style>
<div class="ps-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:8px 0">
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.72rem;color:#888;font-weight:600;margin-bottom:4px">建議張數</div>
    <div style="font-size:1.05rem;font-weight:800;color:#1a1a2e;white-space:normal;word-break:break-word">{ps['lots']} 張{cap_note}</div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.72rem;color:#888;font-weight:600;margin-bottom:4px">部位金額</div>
    <div style="font-size:1.05rem;font-weight:800;color:#1a1a2e;white-space:normal;word-break:break-word">NT${ps['position_ntd']:,}</div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 14px">
    <div style="font-size:0.72rem;color:#888;font-weight:600;margin-bottom:4px">實際風險</div>
    <div style="font-size:1.05rem;font-weight:800;color:#c62828;white-space:normal;word-break:break-word">NT${ps['actual_risk_ntd']:,}</div>
  </div>
</div>""")
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

    # ── 進場候選追蹤池 ────────────────────────────────────────
    _render_candidate_pool(stock_prices)
