"""
live_execution_service.py — 盤中 Live Decision 狀態轉換落地 DB

寫入策略：State Transition 架構
  - 只在 live_status 與 prev_status 不同時才寫入
  - prev_status=None（首次觀察）視為有效轉換，必定寫入
  - RAPID_DROP 持續 10 秒一次 → 不寫入，避免重複資料

Forward 研究目標（累積 6 個月後可回答）：
  - RAPID_DROP 攔截的 BUY，20D/60D Alpha 如何？
  - 等 ENTRY_RECONFIRMED 再買 vs 直接買 WATCHING_LOW，哪個更好？
  - -2.5% 急跌門檻、+3.0% 轉強門檻是否需要調整？
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def record_if_transition(
    stock_id: str,
    signal_date: date,
    prev_status: Optional[str],
    ld,
    rec: dict,
    quote_trade_date: Optional[str],
    quote_quality: str,
) -> bool:
    """
    Write a LiveExecutionEvent to DB iff the status changed from prev_status.

    Args:
        stock_id:        e.g. "3042"
        signal_date:     date of the original BUY recommendation
        prev_status:     last recorded status for this stock (None = first observation)
        ld:              LiveDecision dataclass from evaluate_entry_status()
        rec:             recommendation dict (price, entry_low, entry_high, stop_price, target1)
        quote_trade_date: YYYYMMDD string from IntradayQuote.trade_date
        quote_quality:   "valid" / "stale" / "unknown" from quote_date_status()

    Returns:
        True if a record was written, False if no transition (skipped).
    """
    from src.engines.live_decision import LIVE_RULE_VERSION
    from src.database import MODEL_VERSION

    new_status = ld.status.value if hasattr(ld.status, "value") else str(ld.status)

    if prev_status is not None and prev_status == new_status:
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
            prev_status=prev_status,
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
            f"LiveExecutionEvent: {stock_id} {prev_status} → {new_status} "
            f"(price={ld.current_price}, low={ld.intraday_low})"
        )
        return True

    except Exception as exc:
        logger.warning(f"LiveExecutionEvent write failed for {stock_id}: {exc}")
        return False
