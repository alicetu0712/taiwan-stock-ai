"""
overnight_service.py — Fetch, validate, and persist OvernightMarketContext

Public API:
  ensure_overnight_context(execution_date) -> OvernightMarketContext | None
    - If context already exists in DB for (execution_date, OVERNIGHT_RULE_VERSION): return it.
    - Exception: UNKNOWN (fetch_error) before freeze time → retry up to MAX_RETRY_COUNT times.
    - Otherwise: fetch → evaluate → persist → return.
    - Any external fetch failure → graceful degradation to UNKNOWN context (still persisted).
    - Never raises; never crashes the caller (Live Monitor / background service).

  get_overnight_context(execution_date) -> OvernightMarketContext | None
    - Read-only DB lookup. Returns None if not yet built.

Freeze / retry policy:
  COMPLETE / PARTIAL / STALE  → permanently frozen once persisted (valid data quality)
  UNKNOWN (fetch_error)        → retried up to MAX_RETRY_COUNT times before FREEZE_HOUR_TW:FREEZE_MINUTE_TW
  After freeze time            → UNKNOWN is permanent for that execution_date

  This prevents a transient 07:00 Yahoo timeout from making the entire trading day UNKNOWN.
  retry_count in DB provides auditability of how many attempts were made.
"""

import json
import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

UTC = ZoneInfo("UTC")
TW  = ZoneInfo("Asia/Taipei")

# UNKNOWN retry policy
_FREEZE_HOUR_TW   = 8    # 08:30 TW: after this, UNKNOWN is permanent for the day
_FREEZE_MINUTE_TW = 30
MAX_RETRY_COUNT   = 3    # max retry attempts for transient UNKNOWN (fetch_error)


def get_overnight_context(execution_date: date):
    """Read-only: return OvernightMarketContext from DB, or None."""
    from src.database import OvernightMarketContext, get_session
    from src.engines.overnight_risk import OVERNIGHT_RULE_VERSION

    s = get_session()
    try:
        return (
            s.query(OvernightMarketContext)
            .filter(
                OvernightMarketContext.execution_date == execution_date,
                OvernightMarketContext.overnight_rule_version == OVERNIGHT_RULE_VERSION,
            )
            .first()
        )
    except Exception as exc:
        logger.warning(f"overnight_service.get: {exc}")
        return None
    finally:
        s.close()


def ensure_overnight_context(execution_date: date):
    """
    Idempotent: return existing context or fetch → validate → persist → return.

    UNKNOWN contexts from transient fetch failures are retried before the freeze
    time (08:30 TW). COMPLETE/PARTIAL/STALE are permanently frozen.

    Returns OvernightMarketContext (with risk_level=UNKNOWN if data unavailable).
    Never raises.
    """
    existing = get_overnight_context(execution_date)

    if existing is not None:
        if not _should_retry_unknown(existing):
            return existing
        # Retry: remove the stale UNKNOWN record and re-fetch
        prior_retry_count = existing.retry_count
        logger.info(
            f"overnight_service: retrying UNKNOWN context for {execution_date} "
            f"(attempt #{prior_retry_count + 1})"
        )
        _delete_context(existing)
        retry_count = prior_retry_count + 1
    else:
        retry_count = 0

    try:
        return _build_and_persist(execution_date, retry_count=retry_count)
    except Exception as exc:
        logger.error(f"overnight_service.ensure: unexpected error: {exc}")
        return _persist_unknown(execution_date, reason=str(exc), retry_count=retry_count)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _should_retry_unknown(ctx) -> bool:
    """
    Return True if an UNKNOWN context should be retried.

    Conditions:
    - data_quality == UNKNOWN (not COMPLETE/PARTIAL/STALE — those are valid and frozen)
    - retry_count < MAX_RETRY_COUNT
    - current TW time < freeze time (08:30)
    """
    from src.engines.overnight_risk import DQ_UNKNOWN
    if ctx.data_quality != DQ_UNKNOWN:
        return False
    if ctx.retry_count >= MAX_RETRY_COUNT:
        return False
    now_tw = datetime.now(TW)
    freeze = now_tw.replace(
        hour=_FREEZE_HOUR_TW, minute=_FREEZE_MINUTE_TW,
        second=0, microsecond=0,
    )
    return now_tw < freeze


def _delete_context(ctx) -> None:
    """Delete an OvernightMarketContext row from DB (used before retry)."""
    from src.database import OvernightMarketContext, get_session
    s = get_session()
    try:
        row = s.query(OvernightMarketContext).filter(OvernightMarketContext.id == ctx.id).first()
        if row:
            s.delete(row)
            s.commit()
            logger.debug(f"overnight_service: deleted UNKNOWN ctx id={ctx.id} for retry")
    except Exception as exc:
        logger.warning(f"overnight_service: delete context failed: {exc}")
        s.rollback()
    finally:
        s.close()


def _build_and_persist(execution_date: date, retry_count: int = 0):
    """Fetch data, evaluate risk, persist and return OvernightMarketContext."""
    from src.core.us_trading_calendar import tw_exec_to_us_market_date, us_session_close_utc
    from src.collectors.overnight_collector import fetch_overnight_context
    from src.engines.overnight_risk import (
        OVERNIGHT_RULE_VERSION,
        evaluate_overnight_risk,
        risk_reasons_to_json,
        _derive_data_quality,
    )
    from src.database import OvernightMarketContext, get_session

    us_market_date = tw_exec_to_us_market_date(execution_date)
    if us_market_date is None:
        logger.warning(
            f"overnight_service: cannot determine us_market_date for {execution_date}"
        )
        return _persist_unknown(
            execution_date, reason="us_calendar_mapping_failed", retry_count=retry_count
        )

    # Fetch from Yahoo
    fetch_result = fetch_overnight_context(us_market_date)

    sp  = fetch_result.sp500
    ndq = fetch_result.nasdaq
    sox = fetch_result.sox
    vix = fetch_result.vix

    # Data quality: stale if any indicator has reason="stale"
    any_stale = any(r.reason == "stale" for r in [sp, ndq, sox, vix])
    data_quality = _derive_data_quality(
        sp500_ok=sp.ok, nasdaq_ok=ndq.ok, sox_ok=sox.ok, vix_ok=vix.ok,
        any_stale=any_stale,
    )

    # VIX change_pct = None when prev_close unavailable
    vix_change_pct = vix.return_pct

    # Evaluate risk
    risk_result = evaluate_overnight_risk(
        sp500_return=sp.return_pct,
        nasdaq_return=ndq.return_pct,
        sox_return=sox.return_pct,
        vix_close=vix.close,
        vix_change=vix_change_pct,
        data_quality=data_quality,
    )

    # Canonical source_timestamp: earliest ok result's Yahoo row timestamp.
    # Each ticker independently validates exact-session match; the first ok
    # timestamp is representative of when the US session data became available.
    source_ts_naive = None
    for r in [sp, ndq, sox, vix]:
        if r.ok and r.source_timestamp is not None:
            source_ts_naive = r.source_timestamp.replace(tzinfo=None)  # UTC-naive for SQLite
            break

    # available_at: exact US session close time (DST-correct, stored as UTC-naive)
    available_at_utc = us_session_close_utc(us_market_date)
    available_at_naive = available_at_utc.replace(tzinfo=None)

    ctx = OvernightMarketContext(
        execution_date=execution_date,
        us_market_date=us_market_date,
        sp500_return_pct=sp.return_pct,
        nasdaq_return_pct=ndq.return_pct,
        sox_return_pct=sox.return_pct,
        vix_close=vix.close,
        vix_change_pct=vix_change_pct,
        taiex_futures_overnight_return_pct=None,  # Phase 1: not available
        risk_level=risk_result.risk_level,
        risk_score=None,
        risk_reasons_json=risk_reasons_to_json(risk_result.reasons),
        data_quality=data_quality,
        source_name="yahoo_finance_v8",
        source_timestamp=source_ts_naive,
        available_at=available_at_naive,
        fetched_at=datetime.now(UTC).replace(tzinfo=None),
        overnight_rule_version=OVERNIGHT_RULE_VERSION,
        retry_count=retry_count,
    )

    s = get_session()
    try:
        s.add(ctx)
        s.commit()
        s.refresh(ctx)
        logger.info(
            f"overnight_context persisted: exec={execution_date} "
            f"us={us_market_date} risk={ctx.risk_level} dq={ctx.data_quality} "
            f"source_ts={source_ts_naive} retry={retry_count}"
        )
        return ctx
    except Exception as exc:
        s.rollback()
        logger.warning(f"overnight_service: DB persist failed: {exc}")
        return None
    finally:
        s.close()


def link_overnight_to_forward_signals(execution_date: date, ctx) -> int:
    """
    Back-fill overnight_context_id / overnight_rule_version on forward_signals
    where execution_date matches and overnight_rule_version is still NULL.

    Called by run_overnight.py after ensure_overnight_context() succeeds.
    Non-destructive: only touches rows that have not been linked yet.
    Returns count of rows updated.
    """
    from src.database import ForwardSignal, get_session

    if ctx is None:
        logger.warning("link_overnight_to_forward_signals: ctx is None, skipping")
        return 0

    s = get_session()
    try:
        rows = (
            s.query(ForwardSignal)
            .filter(
                ForwardSignal.execution_date == execution_date,
                ForwardSignal.overnight_rule_version == None,  # noqa: E711
            )
            .all()
        )
        count = 0
        for row in rows:
            row.overnight_rule_version = ctx.overnight_rule_version
            row.overnight_context_id   = ctx.id
            count += 1
        if count:
            s.commit()
            logger.info(
                f"link_overnight: {count} forward_signal(s) linked "
                f"execution_date={execution_date} ctx_id={ctx.id} "
                f"rule={ctx.overnight_rule_version}"
            )
        else:
            logger.info(
                f"link_overnight: 0 unlinked signals for execution_date={execution_date} "
                f"(already linked or none exist)"
            )
        return count
    except Exception as exc:
        s.rollback()
        logger.warning(f"link_overnight_to_forward_signals: {exc}")
        return 0
    finally:
        s.close()


def _persist_unknown(execution_date: date, reason: str = "", retry_count: int = 0):
    """Persist an UNKNOWN context when data is completely unavailable."""
    from src.engines.overnight_risk import OVERNIGHT_RULE_VERSION, RISK_UNKNOWN, DQ_UNKNOWN
    from src.database import OvernightMarketContext, get_session

    ctx = OvernightMarketContext(
        execution_date=execution_date,
        us_market_date=None,
        risk_level=RISK_UNKNOWN,
        data_quality=DQ_UNKNOWN,
        risk_reasons_json=json.dumps([]),
        source_name="yahoo_finance_v8",
        source_timestamp=None,
        fetched_at=datetime.now(UTC).replace(tzinfo=None),
        overnight_rule_version=OVERNIGHT_RULE_VERSION,
        retry_count=retry_count,
    )

    s = get_session()
    try:
        s.add(ctx)
        s.commit()
        s.refresh(ctx)
        logger.info(
            f"overnight_context persisted UNKNOWN: exec={execution_date} "
            f"reason={reason} retry={retry_count}"
        )
        return ctx
    except Exception as exc:
        s.rollback()
        logger.warning(f"overnight_service: UNKNOWN persist failed: {exc}")
        return None
    finally:
        s.close()
