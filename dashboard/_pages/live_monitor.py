"""
pages/live_monitor.py — 📡 Live Decision Monitor

每 N 秒自動更新盤中即時股價，判斷 AI 訊號的進場條件是否仍成立。

設計原則：
  - AI 原始訊號（BUY ★）固定不變，來自每日收盤後分析
  - BUY ≠ Good Entry：模型看好 Setup，不等於現在進場 R/R 合理
  - 盤中只判斷「現在能不能執行這個 BUY 計畫」
  - State Transition 寫入 DB：狀態改變時透過 live_execution_service 落地，
    供日後 Forward 研究（門檻最佳化、RAPID_DROP 效果驗證等）
"""

import logging
from datetime import date

import streamlit as st

logger = logging.getLogger(__name__)


def _effective_signal_date(sel_date: date) -> date:
    """
    Live Monitor 的 signal_date 解析：
      - 盤中（sel_date == today, 且今天是交易日）→ 監控前一交易日的訊號
        （signal_date = prev_trading_day(today)，execution_date = today）
      - 其他（歷史查詢 / 非交易日）→ 直接用 sel_date

    設計緣由：模型在收盤後產生訊號（signal_date = 10/13），
    實際可執行是下一交易日（execution_date = 10/14）。
    如果 UI 直接用 today(10/14) 查推薦，會找不到任何資料。
    """
    from src.core.trading_calendar import is_trading_day, prev_trading_day

    today = date.today()
    if sel_date == today and is_trading_day(today):
        prev = prev_trading_day(today)
        return prev if prev is not None else sel_date
    return sel_date


def _load_today_buy_recs(signal_date: date) -> list:
    """讀取指定 signal_date 的 BUY/BUY★ 推薦（已含 entry/stop/target）。"""
    from dashboard.loaders import load_db_recommendations
    recs = load_db_recommendations(signal_date)
    return [r for r in recs if r.get("trade_signal") in ("strong_buy", "buy")]


def _render_status_badge(ld) -> str:
    return (
        f'<span style="background:{ld.bg};color:{ld.color};'
        f'font-weight:700;padding:3px 10px;border-radius:12px;font-size:0.8rem">'
        f'{ld.icon} {ld.label}</span>'
    )


def _render_price_delta(current: float, reference: float, label: str) -> str:
    diff  = current - reference
    pct   = diff / reference * 100
    color = "#00897b" if diff >= 0 else "#e53935"
    sign  = "+" if diff >= 0 else ""
    return (
        f'<span style="font-size:0.68rem;color:{color}">'
        f'{label} {sign}{pct:.1f}%</span>'
    )


def _drop_scenario_html(ld, sig_price: float) -> str:
    """急跌情境：價格走勢敘述 + 三階段指示 + 盤中觀察低點說明。"""
    from src.engines.live_decision import LiveStatus
    drop_statuses = (LiveStatus.RAPID_DROP, LiveStatus.WATCHING_LOW, LiveStatus.ENTRY_RECONFIRMED)
    if ld.status not in drop_statuses:
        return ""

    cur  = ld.current_price
    ilow = ld.intraday_low

    # 價格走勢敘述
    if ilow and cur and ilow < sig_price:
        cur_color = "#558b2f" if ld.status == LiveStatus.ENTRY_RECONFIRMED else "#1565c0"
        narrative = (
            f'<span style="color:#333">{sig_price:.1f}</span>'
            f' <span style="color:#e53935">↘ {ilow:.1f} 最低</span>'
            f' <span style="color:{cur_color}">↗ {cur:.1f} 現價</span>'
        )
    elif cur:
        narrative = (
            f'<span style="color:#333">{sig_price:.1f}</span>'
            f' <span style="color:#e53935">↘ {cur:.1f}</span>'
        )
    else:
        narrative = f'<span style="color:#333">{sig_price:.1f}</span>'

    # 三階段指示：stage 1=RAPID_DROP, 2=WATCHING_LOW, 3=ENTRY_RECONFIRMED
    stage = {
        LiveStatus.RAPID_DROP:        1,
        LiveStatus.WATCHING_LOW:      2,
        LiveStatus.ENTRY_RECONFIRMED: 3,
    }[ld.status]

    stage_colors = {1: "#f57f17", 2: "#1565c0", 3: "#558b2f"}
    stage_labels = ["急跌暫緩", "觀察低點", "轉強確認"]

    def _stage_span(i: int) -> str:
        is_done    = i < stage
        is_current = i == stage
        if is_current:
            clr = stage_colors[i]
            return f'<span style="color:{clr};font-weight:700">● {stage_labels[i-1]}</span>'
        if is_done:
            return f'<span style="color:#aaa">✓ {stage_labels[i-1]}</span>'
        return f'<span style="color:#ddd">○ {stage_labels[i-1]}</span>'

    stages_html = " <span style='color:#bbb'>→</span> ".join(_stage_span(i) for i in [1, 2, 3])

    # 盤中觀察低點 vs 模型停損
    ilow_row = ""
    if ilow:
        stop_note = (
            f'<span style="color:#aaa;font-size:0.65rem"> '
            f'（盤中觀察點，非模型停損 {ld.stop_price:.1f}）</span>'
            if ld.stop_price else ""
        )
        ilow_row = (
            f'<div style="font-size:0.72rem;color:#555;margin-top:5px">'
            f'今日盤中觀察低點：<strong style="color:#1565c0">{ilow:.1f}</strong>'
            f'{stop_note}</div>'
        )

    border_color = stage_colors.get(stage, "#f57f17")
    return f"""
<div style="margin:8px 0;padding:8px 10px;background:#f8f9fa;border-left:3px solid {border_color};border-radius:0 6px 6px 0">
  <div style="font-size:0.67rem;color:#999;margin-bottom:3px">今日價格走勢</div>
  <div style="font-size:0.82rem;font-weight:600">{narrative}</div>
  <div style="font-size:0.68rem;margin-top:5px">{stages_html}</div>
  {ilow_row}
</div>"""


def _plain_text_html(plain_text: str) -> str:
    if not plain_text:
        return ""
    return (
        f'<div style="background:#fffde7;border-radius:6px;padding:8px 10px;'
        f'margin:6px 0;font-size:0.72rem;color:#555;line-height:1.55">'
        f'💬 {plain_text}</div>'
    )


def _rr_html(ld) -> str:
    """R/R 以現價計算，含顏色與標注。"""
    rr = ld.rr_current
    if rr is None or rr <= 0:
        return ""
    if rr >= 2.0:
        color = "#00897b"
    elif rr >= 1.0:
        color = "#f57f17"
    else:
        color = "#e53935"

    from src.engines.live_decision import LiveStatus
    price_note = (
        f'<span style="color:#aaa;font-size:0.65rem">（以 {ld.current_price:.1f} 計）</span>'
        if ld.status in (LiveStatus.RAPID_DROP, LiveStatus.WATCHING_LOW) and ld.current_price
        else ""
    )
    return f'<span style="color:{color};font-weight:700"> R/R {rr:.1f}x</span>{price_note}'


def _live_cards(recs: list, market_map: dict, signal_date: "date", interval: int = 10) -> None:
    """
    Live 卡片內容，由外部 fragment 包裝以支援動態刷新頻率。
    狀態轉換（State Transition）透過 live_execution_service 寫入 DB。
    """
    from src.collectors.intraday_collector import fetch_intraday, best_price, quote_date_status
    from src.engines.live_decision import LiveStatus, evaluate_entry_status, market_session_label
    from src.services.live_execution_service import record_if_transition

    session_label = market_session_label()
    is_live = session_label == "盤中"

    stock_ids = [r["sid"] for r in recs]
    quotes    = fetch_intraday(stock_ids, market_map=market_map)

    # 每個 (stock_id, signal_date) 的最後記錄狀態，跨 fragment 刷新保留
    if "lm_status_map" not in st.session_state:
        st.session_state["lm_status_map"] = {}
    status_map: dict = st.session_state["lm_status_map"]

    signal_date_str = str(signal_date)

    from datetime import datetime
    import zoneinfo
    now_str = datetime.now(zoneinfo.ZoneInfo("Asia/Taipei")).strftime("%H:%M:%S")
    status_color = "#00897b" if is_live else "#78909c"
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">'
        f'<span style="background:{status_color};color:white;padding:3px 10px;'
        f'border-radius:12px;font-size:0.75rem;font-weight:700">{session_label}</span>'
        f'<span style="font-size:0.72rem;color:#888">最後更新：{now_str}</span>'
        f'{"<span style=\'font-size:0.72rem;color:#00897b\'>🔄 每 " + str(interval) + " 秒自動刷新</span>" if is_live else ""}'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not recs:
        st.info("今日無 BUY / BUY★ 推薦，無需監控。")
        return

    cols = st.columns(2)
    for idx, rec in enumerate(recs):
        sid    = rec["sid"]
        name   = rec.get("name") or sid
        quote  = quotes.get(sid)

        cur_price    = best_price(quote) if quote else None   # 只取真實成交（z 欄位）
        intraday_low = quote.low if quote else None
        date_status  = quote_date_status(quote) if quote else "unknown"
        # fail-closed：只有 date_status=="valid" 才允許輸出正向進場訊號
        date_known   = (date_status == "valid")

        ld = evaluate_entry_status(cur_price, rec, intraday_low=intraday_low, date_known=date_known)

        # State Transition → DB
        # session_state 只作 cache 以避免每輪都打 DB query。
        # 只有 cache 顯示「可能有變化（或此 session 首次見到此股）」才呼叫
        # record_if_transition()，由它自己查 DB 做最終確認。
        map_key = (sid, signal_date_str)
        new_st  = ld.status.value
        if status_map.get(map_key) != new_st:
            record_if_transition(
                stock_id=sid,
                signal_date=signal_date,
                ld=ld,
                rec=rec,
                quote_trade_date=quote.trade_date if quote else None,
                quote_quality=date_status,
            )
            status_map[map_key] = new_st

        signal_label = "BUY ★" if rec.get("trade_signal") == "strong_buy" else "BUY"
        signal_color = "#1a7f4b" if rec.get("trade_signal") == "strong_buy" else "#2ecc71"
        sig_price    = rec.get("price")
        entry_low    = rec.get("entry_low")
        entry_high   = rec.get("entry_high")
        stop_p       = rec.get("stop_price")
        t1           = rec.get("target1")

        # 即時價格顯示（只用真實成交）
        if date_status == "stale":
            price_display = f'<span style="color:#e53935">⚠ 舊交易日資料</span>'
            if quote and quote.trade_date:
                price_display += f'<span style="font-size:0.62rem;color:#e53935"> ({quote.trade_date[:4]}/{quote.trade_date[4:6]}/{quote.trade_date[6:]})</span>'
        elif date_status == "unknown" and not cur_price:
            price_display = '<span style="color:#78909c">⚪ 日期未確認</span>'
        elif cur_price:
            price_display = f"NT$ {cur_price:,.1f}"
            if quote and quote.update_time:
                price_display += f'<span style="font-size:0.62rem;color:#aaa"> ({quote.update_time})</span>'
        else:
            price_display = '<span style="color:#f57f17">無即時成交</span>'
            if quote and quote.update_time:
                price_display += f'<span style="font-size:0.62rem;color:#aaa"> ({quote.update_time})</span>'

        # 距訊號價漲跌（訊號參考價 = 昨日模型發出 BUY 時的收盤價）
        delta_html = ""
        if cur_price and sig_price:
            delta_html = _render_price_delta(cur_price, sig_price, "vs 昨日訊號價")

        # 交易計劃摘要
        plan_parts = []
        if entry_low and entry_high:
            plan_parts.append(f"進場 {entry_low:.1f}–{entry_high:.1f}")
        if stop_p:
            plan_parts.append(f"停損 {stop_p:.1f}")
        if t1:
            plan_parts.append(f"T1 {t1:.1f}")
        plan_str = "　".join(plan_parts) if plan_parts else "交易計劃待補"

        # 狀態 badge
        status_badge = _render_status_badge(ld)

        # 急跌情境區塊
        drop_html = _drop_scenario_html(ld, sig_price) if sig_price else ""

        # 白話解釋
        plain_html = _plain_text_html(ld.plain_text)

        # R/R（以現價計算）
        rr_display = _rr_html(ld)

        # BUY ≠ Good Entry 提醒（急跌情境下 R/R 不佳時）
        drop_statuses = (LiveStatus.RAPID_DROP, LiveStatus.WATCHING_LOW, LiveStatus.ENTRY_RECONFIRMED)
        buy_note_html = ""
        if ld.status in drop_statuses:
            if ld.status == LiveStatus.ENTRY_RECONFIRMED:
                buy_note_html = (
                    '<div style="font-size:0.67rem;color:#558b2f;margin-top:3px">'
                    '轉強觀察訊號 — 進場條件改善，但非正式 BUY 確認；仍需自行評估量價結構</div>'
                )
            elif ld.rr_current is not None and ld.rr_current < 1.5:
                buy_note_html = (
                    f'<div style="font-size:0.67rem;color:#e65100;margin-top:3px">'
                    f'BUY = 模型看好此 Setup ≠ 現價 R/R {ld.rr_current:.1f}x 就是好時機</div>'
                )
            else:
                buy_note_html = (
                    '<div style="font-size:0.67rem;color:#888;margin-top:3px">'
                    'BUY = 模型看好此 Setup，非現在即可進場的指令</div>'
                )

        # 卡片邊框顏色隨狀態改變
        border_color = ld.color

        html = f"""
<div style="border:1px solid {border_color}33;border-left:4px solid {border_color};
            border-radius:10px;padding:14px 16px;background:#fff;margin-bottom:4px">

  <!-- 標題列 -->
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
    <div>
      <div style="font-size:1rem;font-weight:700">{name}</div>
      <div style="font-size:0.72rem;color:#888">{sid}</div>
    </div>
    <div style="text-align:right">
      <div style="font-size:1.1rem;font-weight:900;color:{signal_color}">
        {signal_label}
        <span style="font-size:0.65rem;color:#aaa;font-weight:400">模型訊號（昨日）</span>
      </div>
      <div style="font-size:0.68rem;color:#888;margin-top:2px">
        訊號參考價 NT$ {sig_price:,.1f}
      </div>
    </div>
  </div>

  <!-- 即時價格 -->
  <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:8px">
    <div style="font-size:1.5rem;font-weight:800">{price_display}</div>
    {delta_html}
  </div>

  <!-- 即時決策狀態 -->
  <div style="margin-bottom:6px">
    {status_badge}
    <div style="font-size:0.72rem;color:#666;margin-top:4px">{ld.reason}</div>
    {buy_note_html}
  </div>

  <!-- 急跌情境：走勢敘述 + 階段指示 -->
  {drop_html}

  <!-- 白話解釋 -->
  {plain_html}

  <!-- 交易計劃摘要 -->
  <div style="font-size:0.68rem;color:#888;background:#f8f9fa;
              border-radius:6px;padding:5px 8px;margin-top:4px">
    {plan_str}{rr_display}
  </div>
</div>"""

        with cols[idx % 2]:
            st.html(html)


def page_live_monitor(sel_date: date) -> None:
    st.markdown("### 📡 Live Decision Monitor")
    st.caption("AI 訊號每日收盤後固定。盤中只更新「現在能不能執行」的即時判斷。")

    # sel_date = today 時，盤中實際應監控前一交易日的訊號（execution_date = today）
    signal_date = _effective_signal_date(sel_date)
    buy_recs    = _load_today_buy_recs(signal_date)

    if signal_date != sel_date:
        st.caption(
            f"🗓 監控 {signal_date} 訊號（execution_date = {sel_date}）"
        )

    if not buy_recs:
        st.info(f"📭 {signal_date} 無 BUY / BUY★ 推薦，無需監控。")
        st.caption("收盤後 pipeline 執行完成後會出現推薦。")
        return

    try:
        from src.database import Stock, get_session
        s = get_session()
        stocks = s.query(Stock).filter(
            Stock.stock_id.in_([r["sid"] for r in buy_recs])
        ).all()
        s.close()
        market_map = {stk.stock_id: stk.market for stk in stocks}
    except Exception:
        market_map = {}

    # selectbox 必須在 fragment 外，才能讀到最新值
    col_cfg1, col_cfg2, _ = st.columns([2, 2, 4])
    with col_cfg1:
        refresh_interval = st.selectbox(
            "自動刷新頻率",
            options=[5, 10, 30, 60],
            index=1,
            format_func=lambda x: f"每 {x} 秒",
            key="lm_refresh",
        )
    with col_cfg2:
        st.metric("監控標的數", len(buy_recs))

    with st.expander("📋 今日 BUY 推薦", expanded=False):
        for r in buy_recs:
            sig   = "BUY ★" if r.get("trade_signal") == "strong_buy" else "BUY"
            setup = r.get("setup_type") or "—"
            st.markdown(
                f"**{r.get('name', r['sid'])}** ({r['sid']}) — "
                f"`{sig}` · {setup} · 訊號價 NT$ {r.get('price', '—')}"
            )

    st.markdown("---")

    # 動態 fragment：每次 page_live_monitor 重新執行時（selectbox 改變），以新 interval 重建
    @st.fragment(run_every=f"{refresh_interval}s")
    def _auto_refresh():
        _live_cards(buy_recs, market_map, signal_date=signal_date, interval=refresh_interval)

    _auto_refresh()
