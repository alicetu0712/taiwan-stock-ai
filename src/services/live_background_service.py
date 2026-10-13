"""
live_background_service.py — 盤中背景 Live Execution Collector

單次執行入口：run_once()
  - 取得今日 Active BUY Signals（非「今日推薦」）：
      signal_date 在過去 SIGNAL_ACTIVE_DAYS 個交易日內，
      且 execution_date（= next_trading_day(signal_date)）≤ today
  - 批次取得即時報價
  - evaluate_entry_status() 計算各股目前狀態
  - record_if_transition() 寫入狀態轉換事件（DB 去重，安全重複呼叫）

時間架構說明：
  signal_date   = 模型產生 BUY 的日期（收盤後）
  execution_date = next_trading_day(signal_date)，第一個可進場日

  ✗ 錯誤做法：查 Recommendation.date == today
    → 10/14 盤中查不到 10/13 的 BUY Signal（管線在 10/14 收盤後才跑）

  ✓ 正確做法：查「execution_date ≤ today」的所有 Active Signals
    → 10/14 找到 10/13 的 BUY，signal_date=10/13 正確記入 LiveExecutionEvent

與 live_monitor.py 的關係：
  - 兩者都呼叫相同的 record_if_transition()，DB 去重確保不重複
  - 此 service 完全不依賴 Streamlit / 瀏覽器
  - live_monitor 最終可簡化為只讀 DB 顯示，但目前兩者並行沒有問題

呼叫方式：
  - crontab / launchd 每 N 分鐘：python3 scripts/run_live_collector.py
  - 背景 loop：python3 scripts/run_live_collector.py --loop
  - 程式內部呼叫：from src.services.live_background_service import run_once
"""

import logging
import zoneinfo
from datetime import date, datetime, time
from typing import Optional

logger = logging.getLogger(__name__)

_TZ = zoneinfo.ZoneInfo("Asia/Taipei")

# 盤中收集時間窗口（含收盤後緩衝，盤後仍可跑一次記錄收盤狀態）
_MARKET_OPEN  = time(9, 0)
_MARKET_CLOSE = time(13, 45)   # 13:30 收盤 + 15 分鐘緩衝

# 訊號有效監控天數：往回找幾個 signal_date
# 設 3 = 本週三開盤時，同時監控週二、週一、上週五的 BUY Signal（若未失效）
SIGNAL_ACTIVE_DAYS = 3


def _is_market_window() -> bool:
    """回傳現在是否在盤中收集時間窗口內（台灣時間 09:00–13:45）。"""
    now_t = datetime.now(_TZ).time()
    return _MARKET_OPEN <= now_t <= _MARKET_CLOSE


def _active_signal_dates(today: date) -> list[date]:
    """
    回傳今天仍可執行的 signal_dates（最多 SIGNAL_ACTIVE_DAYS 個）。

    邏輯：往回走交易日，收集「next_trading_day(signal_date) ≤ today」的 signal_date。

    範例（today = 10/14, SIGNAL_ACTIVE_DAYS = 3）：
      signal 10/13 → exec 10/14 ≤ 10/14 ✓
      signal 10/12 → exec 10/13 ≤ 10/14 ✓
      signal 10/09 → exec 10/12 ≤ 10/14 ✓  ← 3 個，停止
    """
    from src.core.trading_calendar import prev_trading_day, next_trading_day

    result: list[date] = []
    d = today
    while len(result) < SIGNAL_ACTIVE_DAYS:
        prev = prev_trading_day(d)
        if prev is None:
            break
        exec_d = next_trading_day(prev)
        if exec_d is not None and exec_d <= today:
            result.append(prev)
        d = prev
    return result


def _get_active_buy_signals(today: date) -> list[dict]:
    """
    取得今日 Active BUY Signals。

    每個 rec dict 包含 signal_date 欄位（= Recommendation.date），
    用於正確記錄 LiveExecutionEvent.signal_date。
    """
    signal_dates = _active_signal_dates(today)
    if not signal_dates:
        return []

    from src.database import get_session, Recommendation, DailyPrice

    session = get_session()
    try:
        rows = (
            session.query(Recommendation)
            .filter(
                Recommendation.date.in_(signal_dates),
                Recommendation.trade_signal.in_(["buy", "strong_buy"]),
                Recommendation.is_valid.isnot(False),
                Recommendation.tier == "recommend",
            )
            .all()
        )
        if not rows:
            return []

        # 訊號價 = signal_date 的收盤價（DailyPrice）
        all_dates = list({r.date for r in rows})
        all_sids  = list({r.stock_id for r in rows})
        price_rows = (
            session.query(DailyPrice.stock_id, DailyPrice.date, DailyPrice.close)
            .filter(
                DailyPrice.date.in_(all_dates),
                DailyPrice.stock_id.in_(all_sids),
            )
            .all()
        )
        price_map = {(r.stock_id, r.date): r.close for r in price_rows}

        result = []
        for r in rows:
            result.append({
                "sid":           r.stock_id,
                "name":          r.stock_name or r.stock_id,
                "trade_signal":  r.trade_signal,
                "price":         price_map.get((r.stock_id, r.date)),
                "entry_low":     r.entry_low,
                "entry_high":    r.entry_high,
                "stop_price":    r.stop_price,
                "target1":       r.target1,
                "signal_date":   r.date,       # ← 關鍵：訊號產生日，非 execution_date
            })
        return result

    finally:
        session.close()


def _get_market_map(stock_ids: list[str]) -> dict[str, str]:
    """取得各股掛牌市場（TWSE / TPEx），用於 fetch_intraday。"""
    from src.database import get_session, Stock

    session = get_session()
    try:
        rows = (
            session.query(Stock.stock_id, Stock.market)
            .filter(Stock.stock_id.in_(stock_ids))
            .all()
        )
        return {r.stock_id: r.market for r in rows}
    finally:
        session.close()


def run_once(force: bool = False) -> dict:
    """
    單次收集執行：取 Active Signals → 取報價 → 評估狀態 → 寫入 DB。

    Args:
        force: 忽略市場時間窗口限制（測試 / 補跑用）

    Returns:
        summary dict:
          skipped:        True if run was skipped (market closed / outside hours)
          reason:         skip reason string
          candidates:     number of active BUY signals processed
          events_written: number of new state transitions written to DB
          errors:         number of per-stock errors
          signal_dates:   list of signal_dates that were active today
    """
    from src.core.trading_calendar import market_status, MarketStatus

    today = datetime.now(_TZ).date()

    # 交易日確認
    mstatus = market_status(today)
    if mstatus in (MarketStatus.WEEKEND, MarketStatus.HOLIDAY):
        return {"skipped": True, "reason": f"market_closed:{mstatus.value}"}

    # 時間窗口確認
    if not force and not _is_market_window():
        return {"skipped": True, "reason": "outside_market_hours"}

    # 取 Active BUY Signals（execution_date ≤ today，往回 SIGNAL_ACTIVE_DAYS 天）
    recs = _get_active_buy_signals(today)
    if not recs:
        return {
            "skipped": False, "candidates": 0,
            "events_written": 0, "errors": 0, "signal_dates": [],
        }

    stock_ids  = [r["sid"] for r in recs]
    market_map = _get_market_map(stock_ids)

    # 批次取即時報價
    from src.collectors.intraday_collector import fetch_intraday, best_price, quote_date_status
    quotes = fetch_intraday(stock_ids, market_map=market_map)

    # 評估 + 記錄
    from src.engines.live_decision import evaluate_entry_status
    from src.services.live_execution_service import record_if_transition

    events_written = 0
    errors = 0

    for rec in recs:
        sid         = rec["sid"]
        signal_date = rec["signal_date"]   # ← signal_date，不是 today
        try:
            quote       = quotes.get(sid)
            cur_price   = best_price(quote) if quote else None
            iday_low    = quote.low if quote else None
            date_status = quote_date_status(quote) if quote else "unknown"
            date_known  = (date_status == "valid")

            ld = evaluate_entry_status(
                cur_price, rec,
                intraday_low=iday_low,
                date_known=date_known,
            )

            written = record_if_transition(
                stock_id=sid,
                signal_date=signal_date,   # ← 正確的訊號日期
                ld=ld,
                rec=rec,
                quote_trade_date=quote.trade_date if quote else None,
                quote_quality=date_status,
            )
            if written:
                events_written += 1

        except Exception as exc:
            logger.warning(f"live_background_service: error processing {sid}: {exc}")
            errors += 1

    signal_dates_used = sorted({r["signal_date"] for r in recs})
    return {
        "skipped":        False,
        "candidates":     len(recs),
        "events_written": events_written,
        "errors":         errors,
        "signal_dates":   signal_dates_used,
    }
