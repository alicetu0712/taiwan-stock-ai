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
    # Core Picks BUY：只計 tier='recommend' 的 BUY 訊號，與 eligible 邏輯一致
    core_recs = [r for r in all_rows if r.tier == "recommend"]
    core_buy_rows = [r for r in buy_rows if r.tier == "recommend"]

    excl_invalid = excl_non_core = excl_lifecycle = not_yet_executable = 0
    if exec_date is not None and exec_date > today:
        # not_yet_executable 只計 Core Picks BUY（eligible 的真實候選數）
        not_yet_executable = len(core_buy_rows)
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
            "sid": r.stock_id,
            "name": r.stock_name or r.stock_id,
            "trade_signal": r.trade_signal,
            "price": price_map.get(r.stock_id),
            "entry_low": r.entry_low,
            "entry_high": r.entry_high,
            "stop_price": r.stop_price,
            "target1": r.target1,
            "setup_type": r.setup_type,
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
        "core_recs_count": len(core_recs),
        "buy_count": len(buy_rows),  # 全 tier BUY（資訊用）
        "core_buy_count": len(core_buy_rows),  # Core Picks BUY（eligible 邏輯基準）
        "excl_invalid": excl_invalid,
        "excl_non_core": excl_non_core,
        "excl_lifecycle": excl_lifecycle,
        "not_yet_executable": not_yet_executable,  # 現為 core_buy_rows 數量
        "eligible_count": len(eligible),
        "eligible_stocks": [(r.get("sid"), r.get("name")) for r in eligible],
        "overnight_ctx": overnight_ctx,
    }

    return eligible, diag


def _render_overnight_diagnostics(ctx) -> None:
    """Render overnight context fields inside the diagnostics expander."""
    from src.engines.overnight_risk import risk_reasons_from_json
    from src.presentation.live_presenter import LivePresenter

    st.markdown(
        f"**🌙 隔夜市場**：{LivePresenter.overnight_risk_badge(ctx.risk_level)}　"
        f"<span style='font-size:0.75rem;color:#888'>"
        f"US {ctx.us_market_date or '—'} · {ctx.data_quality} · {ctx.overnight_rule_version}"
        f"</span>",
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"S&P 500 `{LivePresenter.fmt_pct(ctx.sp500_return_pct)}`　"
            f"Nasdaq `{LivePresenter.fmt_pct(ctx.nasdaq_return_pct)}`　"
            f"SOX `{LivePresenter.fmt_pct(ctx.sox_return_pct)}`"
        )
    with c2:
        vix_str = f"{ctx.vix_close:.1f}" if ctx.vix_close else "—"
        vix_chg = (
            f" ({LivePresenter.fmt_pct(ctx.vix_change_pct)})"
            if ctx.vix_change_pct
            else ""
        )
        st.markdown(
            f"VIX `{vix_str}{vix_chg}`　"
            f"Fetched `{ctx.fetched_at.strftime('%H:%M') if ctx.fetched_at else '—'}`"
        )

    reasons = risk_reasons_from_json(ctx.risk_reasons_json or "[]")
    if reasons:
        st.markdown(
            "　".join(
                f"`{r.code}` {r.message}（{LivePresenter.fmt_pct(r.value)}）"
                for r in reasons
            )
        )


def _render_signal_diagnostics(sel_date: date, signal_date: date, diag: dict) -> None:
    """預設收合的診斷 expander；Core Picks BUY > 0 但 eligible = 0 時自動展開。"""
    core_buy = diag.get("core_buy_count", diag["buy_count"])
    all_buy = diag["buy_count"]
    eligible = diag["eligible_count"]
    # 只有 Core Picks BUY 存在但尚不可執行才顯示 warn
    warn = core_buy > 0 and eligible == 0
    header = (
        "⚠️ 診斷資訊（Core Picks BUY 存在但 Eligible = 0）" if warn else "🔍 診斷資訊"
    )

    with st.expander(header, expanded=warn):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Execution Date**：{sel_date}")
            st.markdown(f"**Signal Date**：{signal_date}")
            # ── 區分全 tier vs Core Picks ──────────────────────────
            total = diag["total_recs"]
            core_cnt = diag.get("core_recs_count", "—")
            st.markdown(
                f"**Recommendations**：{total}　"
                f"<span style='font-size:0.85em;color:#888'>（Core Picks {core_cnt} ／ 其他 tier {total - core_cnt if isinstance(core_cnt, int) else '—'}）</span>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**BUY / BUY★**：Core Picks {core_buy}　"
                f"<span style='font-size:0.85em;color:#888'>（全 tier {all_buy}，含 Watch / Opportunity）</span>",
                unsafe_allow_html=True,
            )
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
                reasons.append(
                    f"{diag['excl_non_core']} 個 Non-Core（tier ≠ recommend）"
                )
            if diag["excl_invalid"]:
                reasons.append(f"{diag['excl_invalid']} 個 Invalid（is_valid=False）")
            if diag["excl_lifecycle"]:
                reasons.append(
                    f"{diag['excl_lifecycle']} 個 Expired（停損或 Superseded）"
                )
            if diag["not_yet_executable"]:
                st.warning(
                    f"⚠️ {signal_date} 有 **{core_buy} 個 Core Picks BUY**，"
                    f"但 execution_date = {diag['exec_date']} > today（尚未可執行）。\n\n"
                    f"另有 {all_buy - core_buy} 個 Watch/Opportunity tier BUY 訊號，"
                    f"不納入正式 Core Picks 監控。"
                )
            elif reasons:
                st.warning(
                    f"⚠️ {signal_date} 有 {core_buy} 個 Core Picks BUY，Eligible = 0。\n\n"
                    f"排除原因：{'、'.join(reasons)}"
                )


def _fetch_forward_signal_ids(signal_date: "date", stock_ids: list) -> dict:
    """
    批次查詢 ForwardSignal.id for (signal_date, stock_id)。
    回傳 {stock_id: fs_id}；查無資料或 is_valid=False 則不含該鍵。
    只做唯讀查詢，不修改任何 ForwardSignal。
    """
    if not stock_ids:
        return {}
    try:
        from src.database import ForwardSignal, get_session

        s = get_session()
        rows = (
            s.query(ForwardSignal.stock_id, ForwardSignal.id)
            .filter(
                ForwardSignal.trade_date == signal_date,
                ForwardSignal.stock_id.in_(stock_ids),
                ForwardSignal.is_valid.is_(True),
            )
            .order_by(ForwardSignal.id.desc())
            .all()
        )
        s.close()
        seen: dict = {}
        for sid, fid in rows:
            if sid not in seen:
                seen[sid] = fid
        return seen
    except Exception as exc:
        logger.debug(f"_fetch_forward_signal_ids: {exc}")
        return {}


def _render_record_buy_form(sid: str, name: str, rec: dict, signal_date, fs_id) -> None:
    """
    「📝 記錄實際買進」表單（在 BUY 卡片 expander 內）。

    使用者填寫實際成交資訊後，透過 trade_service 建立 ACTUAL 持倉。
    不得自動呼叫此函式；只有使用者主動展開 expander 並填表才觸發。
    """
    from datetime import date
    from decimal import Decimal

    import src.services.trade_service as svc
    from src.database import get_session

    signal_source = "AI_SIGNAL" if fs_id else "MANUAL"
    target = rec.get("target1")
    stop = rec.get("stop_price")

    # 原始計畫摘要（唯讀提示）
    plan_parts = []
    if rec.get("entry_low") and rec.get("entry_high"):
        plan_parts.append(f"進場區間 {rec['entry_low']:.1f}–{rec['entry_high']:.1f}")
    if stop:
        plan_parts.append(f"停損 {stop:.1f}")
    if target:
        plan_parts.append(f"目標 {target:.1f}")
    if plan_parts:
        st.caption("原始計畫：" + "　".join(plan_parts))

    if signal_source == "AI_SIGNAL":
        st.caption(f"✅ 已找到正式 ForwardSignal（id={fs_id}），將連結至 AI 訊號")
    else:
        st.caption("ℹ️ 此訊號無對應 ForwardSignal，將以 MANUAL 模式建立持倉")

    form_key = f"record_buy_{sid}_{signal_date}"
    with st.form(key=form_key, clear_on_submit=True):
        c1, c2 = st.columns(2)
        exec_date = c1.date_input(
            "實際成交日期",
            value=date.today(),
            key=f"rb_date_{sid}",
        )
        exec_time = c2.text_input(
            "成交時間（選填，HH:MM）",
            value="",
            key=f"rb_time_{sid}",
        )
        c3, c4 = st.columns(2)
        exec_price = c3.number_input(
            "成交價格",
            min_value=0.01,
            step=0.01,
            format="%.2f",
            key=f"rb_price_{sid}",
        )
        shares = c4.number_input(
            "成交股數",
            min_value=1,
            step=1,
            key=f"rb_shares_{sid}",
        )
        c5, c6 = st.columns(2)
        actual_fee = c5.number_input(
            "手續費（元）",
            min_value=0.0,
            step=1.0,
            format="%.0f",
            key=f"rb_fee_{sid}",
        )
        notes = c6.text_input("備註（選填）", key=f"rb_notes_{sid}")

        submitted = st.form_submit_button("✅ 確認記錄買進", type="primary")
        if submitted:
            if exec_price <= 0:
                st.error("請填寫成交價格（> 0）")
                return
            if shares <= 0:
                st.error("請填寫成交股數（> 0）")
                return
            try:
                exec_datetime = None
                if exec_time.strip():
                    from datetime import datetime

                    exec_datetime = datetime.strptime(
                        f"{exec_date} {exec_time.strip()}", "%Y-%m-%d %H:%M"
                    )
                session = get_session()
                pos = svc.create_position(
                    session,
                    sid,
                    name,
                    signal_source,
                    exec_date,
                    target_price=Decimal(str(target)) if target else None,
                    stop_price=Decimal(str(stop)) if stop else None,
                    forward_signal_id=fs_id,
                    notes=notes,
                )
                svc.add_execution(
                    session,
                    pos.id,
                    "BUY",
                    exec_date,
                    execution_price=Decimal(str(exec_price)),
                    shares=int(shares),
                    actual_fee=Decimal(str(actual_fee)),
                    transaction_tax=Decimal("0"),
                    execution_datetime=exec_datetime,
                    notes=notes,
                )
                session.commit()
                session.close()
                st.success(
                    f"✅ 已記錄：{name}（{sid}）買進 {int(shares)} 股 @ "
                    f"{exec_price:.2f}　持倉 #{pos.id}"
                )
            except svc.TradeSvcError as e:
                st.error(f"記錄失敗（業務規則）：{e}")
            except Exception as e:
                logger.exception(f"record_buy error: {e}")
                st.error(f"記錄失敗（系統錯誤）：{e}")


def _live_cards(
    recs: list,
    market_map: dict,
    signal_date: "date",
    interval: int = 10,
    overnight_ctx=None,
) -> None:
    """
    Live 卡片內容，由外部 fragment 包裝以支援動態刷新頻率。
    狀態轉換（State Transition）透過 live_execution_service 寫入 DB。
    """
    from src.collectors.intraday_collector import (
        best_price,
        fetch_intraday,
        quote_date_status,
    )
    from src.engines.live_decision import evaluate_entry_status, market_session_label
    from src.presentation.live_presenter import LivePresenter
    from src.services.live_execution_service import record_if_transition

    _presenter = LivePresenter()

    session_label = market_session_label()
    is_live = session_label == "盤中"

    stock_ids = [r["sid"] for r in recs]
    quotes = fetch_intraday(stock_ids, market_map=market_map)

    # 批次預取 ForwardSignal IDs（唯讀，不修改任何訊號）
    fs_id_map = _fetch_forward_signal_ids(signal_date, stock_ids)

    # 每個 (stock_id, signal_date) 的最後記錄狀態，跨 fragment 刷新保留
    if "lm_status_map" not in st.session_state:
        st.session_state["lm_status_map"] = {}
    status_map: dict = st.session_state["lm_status_map"]

    signal_date_str = str(signal_date)

    import zoneinfo
    from datetime import datetime

    now_str = datetime.now(zoneinfo.ZoneInfo("Asia/Taipei")).strftime("%H:%M:%S")
    status_color = "#00897b" if is_live else "#78909c"
    refresh_span = (
        f'<span style="font-size:0.72rem;color:#00897b">🔄 每 {interval} 秒自動刷新</span>'
        if is_live
        else ""
    )
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">'
        f'<span style="background:{status_color};color:white;padding:3px 10px;'
        f'border-radius:12px;font-size:0.75rem;font-weight:700">{session_label}</span>'
        f'<span style="font-size:0.72rem;color:#888">最後更新：{now_str}</span>'
        f"{refresh_span}"
        f"</div>",
        unsafe_allow_html=True,
    )

    if not recs:
        st.info("今日無 BUY / BUY★ 推薦，無需監控。")
        return

    cols = st.columns(2)
    for idx, rec in enumerate(recs):
        sid = rec["sid"]
        name = rec.get("name") or sid
        quote = quotes.get(sid)

        cur_price = best_price(quote) if quote else None  # 只取真實成交（z 欄位）
        intraday_low = quote.low if quote else None
        date_status = quote_date_status(quote) if quote else "unknown"
        # fail-closed：只有 date_status=="valid" 才允許輸出正向進場訊號
        date_known = date_status == "valid"

        ld = evaluate_entry_status(
            cur_price, rec, intraday_low=intraday_low, date_known=date_known
        )

        # State Transition → DB
        # session_state 只作 cache 以避免每輪都打 DB query。
        # 只有 cache 顯示「可能有變化（或此 session 首次見到此股）」才呼叫
        # record_if_transition()，由它自己查 DB 做最終確認。
        map_key = (sid, signal_date_str)
        new_st = ld.status.value
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

        sig_price = rec.get("price")
        card = _presenter.present(rec, ld, quote, date_status, overnight_ctx)

        # ── Level 1：精簡卡片（即時狀態 + 計劃）──────────────────────────
        html = f"""
<div style="border:1px solid {card.border_color}33;border-left:4px solid {card.border_color};
            border-radius:10px;padding:14px 16px;background:#fff;margin-bottom:4px">

  <!-- 標題列 -->
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
    <div>
      <div style="font-size:1rem;font-weight:700">{name}</div>
      <div style="font-size:0.72rem;color:#888">{sid}</div>
    </div>
    <div style="text-align:right">
      <div style="font-size:1.1rem;font-weight:900;color:{card.signal_color}">
        {card.signal_label}
        <span style="font-size:0.65rem;color:#aaa;font-weight:400">模型訊號（昨日）</span>
      </div>
    </div>
  </div>

  <!-- 即時價格 -->
  <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:8px">
    <div style="font-size:1.5rem;font-weight:800">{card.price_display}</div>
    {card.delta_html}
  </div>

  <!-- 即時決策狀態 -->
  <div style="margin-bottom:6px">
    {card.status_badge_html}
    <div style="font-size:0.72rem;color:#666;margin-top:4px">{card.reason}</div>
  </div>

  <!-- 隔夜市場（精簡：風險燈號 + 建議標籤） -->
  {card.overnight_l1_html}

  <!-- 交易計劃摘要 -->
  <div style="font-size:0.68rem;color:#888;background:#f8f9fa;
              border-radius:6px;padding:5px 8px;margin-top:6px">
    {card.plan_str}{card.rr_display}
  </div>
</div>"""

        # ── Level 2 & 3 expanders ────────────────────────────────────────
        with cols[idx % 2]:
            st.html(html)

            with st.expander("🔍 盤中細節", expanded=card.l2_expanded):
                if card.buy_note_html:
                    st.html(card.buy_note_html)
                if card.plain_html:
                    st.html(card.plain_html)
                if card.drop_html:
                    st.html(card.drop_html)
                st.html(card.overnight_full_html)

            with st.expander("🧪 原始數值", expanded=False):
                col_a, col_b = st.columns(2)
                with col_a:
                    if sig_price:
                        st.caption(f"訊號參考價：NT$ {sig_price:,.1f}")
                    if ld.intraday_low:
                        st.caption(f"盤中觀察低點：{ld.intraday_low:.1f}")
                with col_b:
                    if date_status != "valid":
                        st.caption(f"報價狀態：{date_status}")
                    if cur_price and sig_price:
                        diff_pct = (cur_price - sig_price) / sig_price * 100
                        st.caption(f"vs 訊號價：{diff_pct:+.1f}%")

            with st.expander("📝 記錄實際買進", expanded=False):
                st.caption(
                    "⚠️ 此處為登記**已完成的成交**，按下確認後才寫入持倉。"
                    "不代表向券商送單，也不影響 AI 訊號與 PAPER 模擬。"
                )
                _render_record_buy_form(
                    sid=sid,
                    name=name,
                    rec=rec,
                    signal_date=signal_date,
                    fs_id=fs_id_map.get(sid),
                )


def page_live_monitor(sel_date: date) -> None:
    st.markdown("### 📡 Live Decision Monitor")
    st.caption("AI 訊號每日收盤後固定。盤中只更新「現在能不能執行」的即時判斷。")

    # sel_date = today 時，盤中實際應監控前一交易日的訊號（execution_date = today）
    signal_date = _effective_signal_date(sel_date)
    buy_recs, diag = _select_live_signals(signal_date)

    if signal_date != sel_date:
        st.caption(f"🗓 監控 {signal_date} 訊號（execution_date = {sel_date}）")

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
        stocks = (
            s.query(Stock)
            .filter(Stock.stock_id.in_([r["sid"] for r in buy_recs]))
            .all()
        )
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
            sig = "BUY ★" if r.get("trade_signal") == "strong_buy" else "BUY"
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
        _live_cards(
            buy_recs,
            market_map,
            signal_date=signal_date,
            interval=refresh_interval,
            overnight_ctx=overnight_ctx,
        )

    _auto_refresh()
