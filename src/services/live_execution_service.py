"""
live_execution_service.py — 盤中 Live Decision 狀態轉換落地 DB

寫入策略：State Transition 架構，DB 為 Source of Truth
  - record_if_transition() 自己查 DB 取得上一個已記錄狀態
  - 不信任 UI session_state 傳進來的 prev_status（瀏覽器重開會遺失）
  - 只在 DB 最新狀態 ≠ 新狀態時寫入
  - Caller（live_monitor）可用 session_state 做 cache，避免無謂 DB query；
    但 DB 才是最終 gate

Dataset 限制說明（研究時需注意）：
  - 目前事件由 UI 觸發，使用者沒開網站的時段無法記錄（Observed Execution Events）
  - 未來 P1 背景 Collector 完成後，才能成為完整 Forward Execution Dataset

Forward 研究目標（累積 6 個月後可回答）：
  - RAPID_DROP 攔截的 BUY，20D/60D Alpha 如何？
  - 等 ENTRY_RECONFIRMED 再買 vs 直接買 WATCHING_LOW，哪個更好？
  - live_rule_version 比較不同版本門檻的效果
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _query_db_last_status(
    stock_id: str,
    signal_date: date,
    live_rule_version: str,
) -> Optional[str]:
    """
    Query DB for the most recent live_status for this (stock_id, signal_date, rule version).
    Returns None if no record exists.
    """
    try:
        from src.database import get_session, LiveExecutionEvent
        session = get_session()
        last = (
            session.query(LiveExecutionEvent.live_status)
            .filter(
                LiveExecutionEvent.stock_id == stock_id,
                LiveExecutionEvent.signal_date == signal_date,
                LiveExecutionEvent.live_rule_version == live_rule_version,
            )
            .order_by(LiveExecutionEvent.observed_at.desc())
            .first()
        )
        session.close()
        return last[0] if last else None
    except Exception as exc:
        logger.warning(f"DB last-status query failed for {stock_id}: {exc}")
        return None


def record_if_transition(
    stock_id: str,
    signal_date: date,
    ld,
    rec: dict,
    quote_trade_date: Optional[str],
    quote_quality: str,
) -> bool:
    """
    Write a LiveExecutionEvent iff the DB's last known status ≠ current status.

    DB is the source of truth for prev_status — browser session_state is NOT used here.
    Callers should only invoke this function when their local cache already suggests a
    potential transition (or has no cached state), to avoid unnecessary DB queries.

    Args:
        stock_id:        e.g. "3042"
        signal_date:     date of the original BUY recommendation
        ld:              LiveDecision dataclass from evaluate_entry_status()
        rec:             recommendation dict (price, entry_low, entry_high, stop_price, target1)
        quote_trade_date: YYYYMMDD string from IntradayQuote.trade_date
        quote_quality:   "valid" / "stale" / "unknown" from quote_date_status()

    Returns:
        True if a record was written, False if DB confirms no transition (skipped).
    """
    from src.engines.live_decision import LIVE_RULE_VERSION
    from src.database import MODEL_VERSION

    new_status = ld.status.value if hasattr(ld.status, "value") else str(ld.status)

    # DB is source of truth — query regardless of what caller thinks prev_status was
    db_prev_status = _query_db_last_status(stock_id, signal_date, LIVE_RULE_VERSION)

    if db_prev_status == new_status:
        # DB already has this status as the latest — not a transition, skip
        return False

    try:
        from src.database import get_session, LiveExecutionEvent

        evt = LiveExecutionEvent(
            stock_id=stock_id,
            signal_date=signal_date,
            signal_price=rec.get("price"),
            observed_at=datetime.now(timezone.utc).replace(tzinfo=None),
            current_price=ld.current_price,
            intraday_low=ld.intraday_low,
            prev_status=db_prev_status,   # DB truth, not UI session
            live_status=new_status,
            drop_pct=ld.drop_pct,
            bounce_pct=ld.bounce_pct,
            rr_at_observation=ld.rr_current,
            entry_low=rec.get("entry_low"),
            entry_high=rec.get("entry_high"),
            stop_price=rec.get("stop_price"),
            target1=rec.get("target1"),
            quote_trade_date=quote_trade_date,
            quote_quality=quote_quality,
            strategy_version=MODEL_VERSION,
            live_rule_version=LIVE_RULE_VERSION,
        )
        session = get_session()
        session.add(evt)
        session.commit()
        session.close()
        logger.info(
            f"LiveExecutionEvent: {stock_id} {db_prev_status!r} → {new_status!r} "
            f"(price={ld.current_price}, low={ld.intraday_low})"
        )
        return True

    except Exception as exc:
        logger.warning(f"LiveExecutionEvent write failed for {stock_id}: {exc}")
        return False
