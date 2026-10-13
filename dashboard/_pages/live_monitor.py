"""
pages/live_monitor.py — 📡 Live Decision Monitor

每 10 秒自動更新盤中即時股價，判斷 AI 訊號的進場條件是否仍成立。

設計原則：
  - AI 原始訊號（BUY ★）固定不變，來自每日收盤後分析
  - 盤中只判斷「現在能不能執行這個 BUY 計畫」
  - 不寫入任何 DB，純展示層
"""

import logging
from datetime import date

import streamlit as st

logger = logging.getLogger(__name__)

# 盤中監控的股票清單來源：今日 BUY/BUY★ 推薦 + 使用者自選
_DEFAULT_WATCHLIST = ["6505", "2330", "2317", "2308", "2412"]


def _load_today_buy_recs(sel_date: date) -> list:
    """讀取今日 BUY/BUY★ 推薦（已含 entry/stop/target）。"""
    from dashboard.loaders import load_db_recommendations
    recs = load_db_recommendations(sel_date)
    return [r for r in recs if r.get("trade_signal") in ("strong_buy", "buy")]


def _render_status_badge(ld) -> str:
    return (
        f'<span style="background:{ld.bg};color:{ld.color};'
        f'font-weight:700;padding:3px 10px;border-radius:12px;font-size:0.8rem">'
        f'{ld.icon} {ld.label}</span>'
    )


def _render_price_delta(current: float, reference: float, label: str) -> str:
    diff = current - reference
    pct  = diff / reference * 100
    color = "#00897b" if diff >= 0 else "#e53935"
    sign  = "+" if diff >= 0 else ""
    return (
        f'<span style="font-size:0.68rem;color:{color}">'
        f'{label} {sign}{pct:.1f}%</span>'
    )


def _live_cards(recs: list, market_map: dict, interval: int = 10) -> None:
    """
    Live 卡片內容，由外部 fragment 包裝以支援動態刷新頻率。
    """
    from src.collectors.intraday_collector import fetch_intraday, best_price
    from src.engines.live_decision import evaluate_entry_status, market_session_label

    session_label = market_session_label()
    is_live = session_label == "盤中"

    # 抓即時報價
    stock_ids = [r["sid"] for r in recs]
    quotes = fetch_intraday(stock_ids, market_map=market_map)

    # 頂部狀態列
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
        cur_price = best_price(quote) if quote else None
        ld     = evaluate_entry_status(cur_price, rec)

        signal_label = "BUY ★" if rec.get("trade_signal") == "strong_buy" else "BUY"
        signal_color = "#1a7f4b" if rec.get("trade_signal") == "strong_buy" else "#2ecc71"
        sig_price    = rec.get("price")
        entry_low    = rec.get("entry_low")
        entry_high   = rec.get("entry_high")
        stop_p       = rec.get("stop_price")
        t1           = rec.get("target1")

        # 即時價格顯示
        price_display = f"NT$ {cur_price:,.1f}" if cur_price else "—"
        if quote and quote.update_time:
            price_display += f'<span style="font-size:0.62rem;color:#aaa"> ({quote.update_time})</span>'

        # 距訊號價漲跌
        delta_html = ""
        if cur_price and sig_price:
            delta_html = _render_price_delta(cur_price, sig_price, "vs 訊號")

        # 交易計劃一行摘要
        plan_parts = []
        if entry_low and entry_high:
            plan_parts.append(f"進場 {entry_low:.1f}–{entry_high:.1f}")
        if stop_p:
            plan_parts.append(f"停損 {stop_p:.1f}")
        if t1:
            plan_parts.append(f"T1 {t1:.1f}")
        plan_str = "　".join(plan_parts) if plan_parts else "交易計劃待補"

        rr_html = ""
        if cur_price and stop_p and t1 and cur_price > stop_p:
            rr = (t1 - cur_price) / (cur_price - stop_p)
            rr_color = "#00897b" if rr >= 2.0 else "#f57f17" if rr >= 1.5 else "#e53935"
            rr_html = f'<span style="color:{rr_color};font-weight:700"> R/R {rr:.1f}x</span>'

        status_badge = _render_status_badge(ld)

        html = f"""
<div style="border:1px solid #e0e0e0;border-radius:10px;padding:14px 16px;
            background:#fff;margin-bottom:4px">
  <!-- 標題列 -->
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
    <div>
      <div style="font-size:1rem;font-weight:700">{name}</div>
      <div style="font-size:0.72rem;color:#888">{sid}</div>
    </div>
    <div style="text-align:right">
      <div style="font-size:1.1rem;font-weight:900;color:{signal_color}">
        {signal_label} <span style="font-size:0.68rem;color:#aaa;font-weight:400">AI 原始訊號（固定）</span>
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

  <!-- 即時決策 -->
  <div style="margin-bottom:8px">
    {status_badge}
    <div style="font-size:0.72rem;color:#666;margin-top:4px">{ld.reason}</div>
  </div>

  <!-- 交易計劃摘要 -->
  <div style="font-size:0.68rem;color:#888;background:#f8f9fa;
              border-radius:6px;padding:5px 8px">
    {plan_str}{rr_html}
  </div>
</div>"""

        with cols[idx % 2]:
            st.html(html)


def page_live_monitor(sel_date: date) -> None:
    st.markdown("### 📡 Live Decision Monitor")
    st.caption("AI 訊號每日收盤後固定。盤中只更新「現在能不能執行」的即時判斷。")

    # 讀取今日 BUY 推薦
    buy_recs = _load_today_buy_recs(sel_date)

    if not buy_recs:
        st.info(f"📭 {sel_date} 無 BUY / BUY★ 推薦，無需監控。")
        st.caption("收盤後 pipeline 執行完成後會出現推薦。")
        return

    # 組 market_map（供 intraday_collector 判斷 tse/otc 前綴）
    try:
        from src.database import Stock, get_session
        s = get_session()
        stocks = s.query(Stock).filter(
            Stock.stock_id.in_([r["sid"] for r in buy_recs])
        ).all()
        s.close()
        market_map = {st.stock_id: st.market for st in stocks}
    except Exception:
        market_map = {}

    # 設定面板（selectbox 放在 expander 外確保值隨時可讀）
    col_cfg1, col_cfg2, col_cfg3 = st.columns([2, 2, 4])
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
            sig = "BUY ★" if r.get("trade_signal") == "strong_buy" else "BUY"
            setup = r.get("setup_type") or "—"
            st.markdown(
                f"**{r.get('name', r['sid'])}** ({r['sid']}) — "
                f"`{sig}` · {setup} · 訊號價 NT$ {r.get('price', '—')}"
            )

    st.markdown("---")

    # Live 卡片：動態 fragment，interval 由 selectbox 控制
    # 每次 page_live_monitor 重新執行（selectbox 改變時），fragment 以新 interval 重建
    @st.fragment(run_every=f"{refresh_interval}s")
    def _auto_refresh():
        _live_cards(buy_recs, market_map, interval=refresh_interval)

    _auto_refresh()
