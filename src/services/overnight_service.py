"""
overnight_service.py — Fetch, validate, and persist OvernightMarketContext

Public API:
  ensure_overnight_context(execution_date) -> OvernightMarketContext | None
    - If context already exists in DB for (execution_date, OVERNIGHT_RULE_VERSION): return it.
    - Otherwise: fetch → evaluate → persist → return.
    - Any external fetch failure → graceful degradation to UNKNOWN context (still persisted).
    - Never raises; never crashes the caller (Live Monitor / background service).

  get_overnight_context(execution_date) -> OvernightMarketContext | None
    - Read-only DB lookup. Returns None if not yet built.

Caching guarantee:
  Once persisted, the same (execution_date, rule_version) is never fetched again.
  Live Monitor reads DB, never calls external APIs.
"""

import json
import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

UTC = ZoneInfo("UTC")


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

    Returns OvernightMarketContext (with risk_level=UNKNOWN if data unavailable).
    Never raises.
    """
    existing = get_overnight_context(execution_date)
    if existing is not None:
        return existing

    try:
        return _build_and_persist(execution_date)
    except Exception as exc:
        logger.error(f"overnight_service.ensure: unexpected error: {exc}")
        return _persist_unknown(execution_date, reason=str(exc))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_and_persist(execution_date: date):
    """Fetch data, evaluate risk, persist and return OvernightMarketContext."""
    from src.core.us_trading_calendar import tw_exec_to_us_market_date, us_session_close_utc
    from src.collectors.overnight_collector import fetch_overnight_context
    from src.engines.overnight_risk import (
        OVERNIGHT_RULE_VERSION,
        evaluate_overnight_risk,
        risk_reasons_to_json,
        _derive_data_quality,
        DQ_STALE, DQ_UNKNOWN,
    )
    from src.database import OvernightMarketContext, get_session

    us_market_date = tw_exec_to_us_market_date(execution_date)
    if us_market_date is None:
        logger.warning(
            f"overnight_service: cannot determine us_market_date for {execution_date}"
        )
        return _persist_unknown(execution_date, reason="us_calendar_mapping_failed")

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
    vix_change_pct = vix.return_pct  # VIX % change uses same formula

    # Evaluate risk
    risk_result = evaluate_overnight_risk(
        sp500_return=sp.return_pct,
        nasdaq_return=ndq.return_pct,
        sox_return=sox.return_pct,
        vix_close=vix.close,
        vix_change=vix_change_pct,
        data_quality=data_quality,
    )

    # source_timestamp: earliest non-None Yahoo timestamp across all tickers
    source_ts = None
    for r in [sp, ndq, sox, vix]:
        if r.ok and r.us_date is not None:
            # Approximate: us_market_date 16:00 ET as proxy for session close
            break

    # available_at: exact US session close time (DST-correct)
    available_at_utc = us_session_close_utc(us_market_date)
    available_at_naive = available_at_utc.replace(tzinfo=None)  # SQLite stores naive

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
        source_timestamp=None,
        available_at=available_at_naive,
        fetched_at=datetime.now(UTC).replace(tzinfo=None),
        overnight_rule_version=OVERNIGHT_RULE_VERSION,
    )

    s = get_session()
    try:
        s.add(ctx)
        s.commit()
        s.refresh(ctx)
        logger.info(
            f"overnight_context persisted: exec={execution_date} "
            f"us={us_market_date} risk={ctx.risk_level} dq={ctx.data_quality}"
        )
        return ctx
    except Exception as exc:
        s.rollback()
        logger.warning(f"overnight_service: DB persist failed: {exc}")
        return None
    finally:
        s.close()


def _persist_unknown(execution_date: date, reason: str = ""):
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
        fetched_at=datetime.now(UTC).replace(tzinfo=None),
        overnight_rule_version=OVERNIGHT_RULE_VERSION,
    )

    s = get_session()
    try:
        s.add(ctx)
        s.commit()
        s.refresh(ctx)
        logger.info(
            f"overnight_context persisted UNKNOWN: exec={execution_date} reason={reason}"
        )
        return ctx
    except Exception as exc:
        s.rollback()
        logger.warning(f"overnight_service: UNKNOWN persist failed: {exc}")
        return None
    finally:
        s.close()
