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


def _select_live_signals(signal_date: date) -> "tuple[list, dict]":
    """
    Single pipeline：回傳 (eligible_recs, diagnostics)。

    直接查 Recommendation + DailyPrice（不經過 @st.cache_data 的 load_db_recommendations），
    確保 count pass 與 eligible list 使用完全相同的 filter 邏輯與 source of truth。

    diagnostics keys：
      signal_date, exec_date, total_recs, buy_count,
      excl_invalid, excl_non_core, excl_lifecycle, not_yet_executable,
      eligible_count, eligible_stocks [(sid, name)]
    """
    from src.core.trading_calendar import next_trading_day
    from src.database import Recommendation, get_session

    today = date.today()
    exec_date = next_trading_day(signal_date)

    # ── single DB pass：count + select（不經過 load_db_recommendations 的 cache）────
    s = get_session()
    all_rows = (
        s.query(
            Recommendation.stock_id,
            Recommendation.stock_name,
            Recommendation.trade_signal,
            Recommendation.tier,
            Recommendation.is_valid,
            Recommendation.lifecycle_status,
            Recommendation.entry_low,
            Recommendation.entry_high,
            Recommendation.stop_price,
            Recommendation.target1,
            Recommendation.setup_type,
        )
        .filter(Recommendation.date == signal_date)
        .all()
    )

    # 訊號價：signal_date 的收盤價（DailyPrice）
    buy_sids = [r.stock_id for r in all_rows if r.trade_signal in ("buy", "strong_buy")]
    price_map: dict = {}
    if buy_sids:
        from src.database import DailyPrice
        price_rows = (
            s.query(DailyPrice.stock_id, DailyPrice.close)
            .filter(DailyPrice.date == signal_date, DailyPrice.stock_id.in_(buy_sids))
            .all()
        )
        price_map = {r.stock_id: r.close for r in price_rows}
    s.close()

    total_recs = len(all_rows)
    buy_rows = [r for r in all_rows if r.trade_signal in ("buy", "strong_buy")]

    excl_invalid = excl_non_core = excl_lifecycle = not_yet_executable = 0
    if exec_date is not None and exec_date > today:
        not_yet_executable = len(buy_rows)
    else:
        for r in buy_rows:
            if r.is_valid is False:
                excl_invalid += 1
            elif r.tier != "recommend":
                excl_non_core += 1
            elif r.lifecycle_status in ("invalidated", "superseded"):
                excl_lifecycle += 1

    # ── eligible list（相同 filter 邏輯，直接從 all_rows 建構）────────────
    eligible = [
        {
            "sid":          r.stock_id,
            "name":         r.stock_name or r.stock_id,
            "trade_signal": r.trade_signal,
            "price":        price_map.get(r.stock_id),
            "entry_low":    r.entry_low,
            "entry_high":   r.entry_high,
            "stop_price":   r.stop_price,
            "target1":      r.target1,
            "setup_type":   r.setup_type,
        }
        for r in buy_rows
        if r.tier == "recommend"
        and r.is_valid is not False
        and r.lifecycle_status not in ("invalidated", "superseded")
        and (exec_date is None or exec_date <= today)
    ]

    # overnight context for exec_date（read-only from DB，不呼叫外部 API）
    overnight_ctx = None
    if exec_date is not None:
        try:
            from src.services.overnight_service import get_overnight_context
            overnight_ctx = get_overnight_context(exec_date)
        except Exception:
            pass

    diag: dict = {
        "signal_date": signal_date,
        "exec_date": exec_date,
        "total_recs": total_recs,
        "buy_count": len(buy_rows),
        "excl_invalid": excl_invalid,
        "excl_non_core": excl_non_core,
        "excl_lifecycle": excl_lifecycle,
        "not_yet_executable": not_yet_executable,
        "eligible_count": len(eligible),
        "eligible_stocks": [(r.get("sid"), r.get("name")) for r in eligible],
        "overnight_ctx": overnight_ctx,
    }

    return eligible, diag


def _overnight_risk_badge(risk_level: str) -> str:
    """Return colored HTML badge for overnight risk level."""
    _META = {
        "GREEN":   ("🟢", "#00897b", "#e0f2f1"),
        "YELLOW":  ("🟡", "#f57f17", "#fff8e1"),
        "RED":     ("🔴", "#c62828", "#ffebee"),
        "UNKNOWN": ("⚪", "#78909c", "#eceff1"),
    }
    icon, color, bg = _META.get(risk_level, _META["UNKNOWN"])
    label_map = {"GREEN": "穩定", "YELLOW": "偏弱", "RED": "高風險", "UNKNOWN": "資料不足"}
    label = label_map.get(risk_level, risk_level)
    return (
        f'<span style="background:{bg};color:{color};'
        f'font-weight:700;padding:2px 9px;border-radius:10px;font-size:0.78rem">'
        f'{icon} {label}</span>'
    )


def _fmt_pct(v) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def _render_overnight_diagnostics(ctx) -> None:
    """Render overnight context fields inside the diagnostics expander."""
    from src.engines.overnight_risk import risk_reasons_from_json
    st.markdown(
        f"**🌙 隔夜市場**：{_overnight_risk_badge(ctx.risk_level)}　"
        f"<span style='font-size:0.75rem;color:#888'>"
        f"US {ctx.us_market_date or '—'} · {ctx.data_quality} · {ctx.overnight_rule_version}"
        f"</span>",
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"S&P 500 `{_fmt_pct(ctx.sp500_return_pct)}`　"
            f"Nasdaq `{_fmt_pct(ctx.nasdaq_return_pct)}`　"
            f"SOX `{_fmt_pct(ctx.sox_return_pct)}`"
        )
    with c2:
        vix_str = f"{ctx.vix_close:.1f}" if ctx.vix_close else "—"
        vix_chg = f" ({_fmt_pct(ctx.vix_change_pct)})" if ctx.vix_change_pct else ""
        st.markdown(f"VIX `{vix_str}{vix_chg}`　Fetched `{ctx.fetched_at.strftime('%H:%M') if ctx.fetched_at else '—'}`")

    reasons = risk_reasons_from_json(ctx.risk_reasons_json or "[]")
    if reasons:
        st.markdown("　".join(f"`{r.code}` {r.message}（{_fmt_pct(r.value)}）" for r in reasons))


def _render_overnight_card(ctx, trade_signal: str, live_status) -> str:
    """
    Return HTML for the overnight market section inside a Live card.
    Calls ExecutionGuidanceEngine to get the final guidance.

    Returns empty string if ctx is None (no overnight data yet).
    """
    if ctx is None:
        return (
            '<div style="margin:6px 0;padding:6px 10px;background:#f5f5f5;'
            'border-radius:6px;font-size:0.72rem;color:#9e9e9e">'
            '🌙 隔夜市場資料尚未取得（盤前自動建立）</div>'
        )

    from src.engines.overnight_risk import risk_reasons_from_json, RISK_UNKNOWN
    from src.engines.execution_guidance import evaluate_execution_guidance, guidance_meta

    risk_level = ctx.risk_level or RISK_UNKNOWN
    _RISK_META = {
        "GREEN":   ("🟢", "#00897b", "#e0f2f1", "穩定"),
        "YELLOW":  ("🟡", "#f57f17", "#fff8e1", "偏弱"),
        "RED":     ("🔴", "#c62828", "#ffebee", "高風險"),
        "UNKNOWN": ("⚪", "#78909c", "#eceff1", "資料不足"),
    }
    icon, color, bg, label = _RISK_META.get(risk_level, _RISK_META["UNKNOWN"])

    # Index returns row
    rows_parts = []
    if ctx.nasdaq_return_pct is not None:
        rows_parts.append(f"Nasdaq {_fmt_pct(ctx.nasdaq_return_pct)}")
    if ctx.sox_return_pct is not None:
        rows_parts.append(f"SOX {_fmt_pct(ctx.sox_return_pct)}")
    if ctx.sp500_return_pct is not None:
        rows_parts.append(f"S&P {_fmt_pct(ctx.sp500_return_pct)}")
    if ctx.vix_close is not None:
        rows_parts.append(f"VIX {ctx.vix_close:.1f}")
    index_row = "　".join(rows_parts) if rows_parts else "—"

    # Execution guidance
    guidance_result = evaluate_execution_guidance(
        trade_signal=trade_signal,
        live_status=live_status,
        overnight_risk=risk_level,
    )
    gmeta = guidance_meta(guidance_result.guidance)

    guidance_html = (
        f'<div style="margin-top:5px;font-size:0.72rem">'
        f'<span style="background:{gmeta["bg"]};color:{gmeta["color"]};'
        f'font-weight:700;padding:2px 8px;border-radius:8px">'
        f'{gmeta["icon"]} {gmeta["label"]}</span>'
        f'<span style="color:#666;margin-left:8px">{guidance_result.plain_text}</span>'
        f'</div>'
    )
    if guidance_result.caution and guidance_result.caution_text:
        guidance_html += (
            f'<div style="font-size:0.68rem;color:#e65100;margin-top:3px">'
            f'{guidance_result.caution_text}</div>'
        )

    return (
        f'<div style="margin:8px 0;padding:8px 10px;background:{bg};'
        f'border-left:3px solid {color};border-radius:0 6px 6px 0">'
        f'<div style="font-size:0.67rem;color:#999;margin-bottom:2px">🌙 隔夜市場風險</div>'
        f'<div style="font-size:0.85rem;font-weight:700;color:{color}">'
        f'{icon} {label}</div>'
        f'<div style="font-size:0.72rem;color:#555;margin-top:3px">{index_row}</div>'
        f'{guidance_html}'
        f'</div>'
    )


def _render_signal_diagnostics(sel_date: date, signal_date: date, diag: dict) -> None:
    """預設收合的診斷 expander；BUY > 0 但 eligible = 0 時自動展開並顯示 warning。"""
    buy_count = diag["buy_count"]
    eligible  = diag["eligible_count"]
    warn      = buy_count > 0 and eligible == 0
    header    = "⚠️ 診斷資訊（BUY 存在但 Eligible = 0）" if warn else "🔍 診斷資訊"

    with st.expander(header, expanded=warn):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Execution Date**：{sel_date}")
            st.markdown(f"**Signal Date**：{signal_date}")
            st.markdown(f"**Recommendations**：{diag['total_recs']}")
            st.markdown(f"**BUY / BUY★**：{buy_count}")
            st.markdown(f"**Eligible Live Signals**：{eligible}")
        with c2:
            if diag["eligible_stocks"]:
                names = "、".join(
                    f"{name}（{sid}）" if name else sid
                    for sid, name in diag["eligible_stocks"]
                )
                st.markdown(f"**監控**：{names}")
            else:
                st.markdown("**監控**：無")
            excl_parts = [
                f"Invalid {diag['excl_invalid']}",
                f"Non-Core {diag['excl_non_core']}",
                f"Expired {diag['excl_lifecycle']}",
                f"Not Yet Executable {diag['not_yet_executable']}",
            ]
            st.markdown(f"**排除**：{'｜'.join(excl_parts)}")

        # Overnight context section
        ctx = diag.get("overnight_ctx")
        if ctx is not None:
            st.markdown("---")
            _render_overnight_diagnostics(ctx)
        else:
            st.markdown("---")
            st.markdown("**🌙 隔夜市場**：⚪ 尚未建立（盤前由 Collector 自動取得）")

        if diag["total_recs"] == 0:
            st.error(f"⛔ {signal_date} 無任何 Recommendation（pipeline 可能未執行）。")
        elif warn:
            reasons = []
            if diag["excl_non_core"]:
                reasons.append(f"{diag['excl_non_core']} 個 Non-Core（tier ≠ recommend）")
            if diag["excl_invalid"]:
                reasons.append(f"{diag['excl_invalid']} 個 Invalid（is_valid=False）")
            if diag["excl_lifecycle"]:
                reasons.append(f"{diag['excl_lifecycle']} 個 Expired（停損或 Superseded）")
            if diag["not_yet_executable"]:
                st.warning(
                    f"⚠️ {signal_date} 有 {buy_count} 個 BUY，但 execution_date "
                    f"= {diag['exec_date']} > today（尚未可執行）。"
                )
            elif reasons:
                st.warning(
                    f"⚠️ {signal_date} 有 {buy_count} 個 BUY，Eligible = 0。\n\n"
                    f"排除原因：{'、'.join(reasons)}"
                )


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


def _live_cards(recs: list, market_map: dict, signal_date: "date", interval: int = 10,
                overnight_ctx=None) -> None:
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

        # 隔夜市場風險 + 執行建議
        overnight_html = _render_overnight_card(overnight_ctx, rec.get("trade_signal", ""), ld.status)

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

  <!-- 隔夜市場風險 + 執行建議 -->
  {overnight_html}

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
    signal_date      = _effective_signal_date(sel_date)
    buy_recs, diag   = _select_live_signals(signal_date)

    if signal_date != sel_date:
        st.caption(
            f"🗓 監控 {signal_date} 訊號（execution_date = {sel_date}）"
        )

    _render_signal_diagnostics(sel_date, signal_date, diag)

    if not buy_recs:
        if diag["total_recs"] == 0:
            st.info(f"📭 {signal_date} 無 Recommendation 資料（pipeline 可能未執行）。")
        else:
            st.info(f"📭 {signal_date} 無可監控的 BUY 訊號。")
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
    overnight_ctx = diag.get("overnight_ctx")

    @st.fragment(run_every=f"{refresh_interval}s")
    def _auto_refresh():
        _live_cards(buy_recs, market_map, signal_date=signal_date,
                    interval=refresh_interval, overnight_ctx=overnight_ctx)

    _auto_refresh()
