"""
outcome_service.py — compute and persist ForwardOutcomeEvaluation (foe_v1)

Public API:
  compute_foe_outcomes(session, as_of_date) -> int
    Process all pending/immature ForwardSignal records.
    Returns count of rows created or updated.

  get_foe_cohort(overnight_risk_level=None, path_type=None, matured_horizon="20d")
    Read-only cohort query for dashboard/stats.

Row lifecycle:
  1. Row created when ForwardSignal has execution_price (NEXT_OPEN).
  2. Entry status set (Baseline: always EXECUTED if price exists;
     Aware: PENDING / EXECUTED / EXPIRED_BEFORE_ENTRY / INVALIDATED_BEFORE_ENTRY).
  3. 20D bundle computed and locked when horizon matures.
  4. 60D bundle computed and locked when horizon matures.
  5. Immutable bundles are never overwritten (horizon_Nd_matured_at guard).
"""

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from src.services.research_backtest_service import ROUND_TRIP_COST

if TYPE_CHECKING:
    from src.engines.outcome_evaluation import EntryResult

logger = logging.getLogger(__name__)


def compute_foe_outcomes(session, as_of_date: date) -> int:
    """
    Main entry point called from daily pipeline (Step 9d).
    Processes all BUY ForwardSignals with execution_price filled.
    Returns number of rows created or updated.
    """
    from src.database import ForwardSignal

    # Load signals eligible for foe_v1 evaluation
    signals = (
        session.query(ForwardSignal)
        .filter(
            ForwardSignal.execution_price_type == "NEXT_OPEN",
            ForwardSignal.execution_price.isnot(None),
            ForwardSignal.execution_date.isnot(None),
            ForwardSignal.trade_signal.in_(["buy", "strong_buy"]),
        )
        .all()
    )

    if not signals:
        return 0

    # Batch-load all price data needed
    price_data = _load_price_data(session, signals)
    overnight_map = _load_overnight_contexts(session, signals)
    live_event_map = _load_live_events(session, signals)
    cancel_event_map = _load_cancel_events(session, signals)
    trading_calendar = _load_trading_calendar(session)

    rows_affected = 0
    for fs in signals:
        try:
            n = _process_signal(
                session,
                fs,
                as_of_date,
                price_data,
                overnight_map,
                live_event_map,
                cancel_event_map,
                trading_calendar,
            )
            rows_affected += n
        except Exception as exc:
            logger.warning(
                f"outcome_service: error for {fs.stock_id} {fs.trade_date}: {exc}"
            )

    if rows_affected:
        session.commit()
    return rows_affected


def get_foe_cohort(
    overnight_risk_level: Optional[str] = None,
    path_type: Optional[str] = None,
    matured_horizon: str = "20d",
    exclude_no_overnight_data: bool = True,
) -> list:
    """Read-only cohort query for dashboard. Returns list of ForwardOutcomeEvaluation rows."""
    from src.database import ForwardOutcomeEvaluation, get_session
    from src.engines.outcome_evaluation import (
        EXEC_EXECUTED,
        FORWARD_OUTCOME_PROTOCOL_VERSION,
    )

    s = get_session()
    try:
        q = s.query(ForwardOutcomeEvaluation).filter(
            ForwardOutcomeEvaluation.outcome_protocol_version
            == FORWARD_OUTCOME_PROTOCOL_VERSION,
            ForwardOutcomeEvaluation.entry_status == EXEC_EXECUTED,
        )
        if overnight_risk_level:
            q = q.filter(
                ForwardOutcomeEvaluation.overnight_risk_level == overnight_risk_level
            )
        if path_type:
            q = q.filter(ForwardOutcomeEvaluation.path_type == path_type)
        if exclude_no_overnight_data:
            # P1: use IS NULL — NULL != value is NULL in SQL, not TRUE, so != would miss eligible rows
            q = q.filter(ForwardOutcomeEvaluation.exclusion_reason.is_(None))
        if matured_horizon == "20d":
            q = q.filter(ForwardOutcomeEvaluation.horizon_20d_matured_at.isnot(None))
        elif matured_horizon == "60d":
            q = q.filter(ForwardOutcomeEvaluation.horizon_60d_matured_at.isnot(None))
        return q.all()
    finally:
        s.close()


def get_all_foe_rows(include_pending: bool = False) -> list:
    """Return all foe_v1 rows for dashboard sample health display."""
    from src.database import ForwardOutcomeEvaluation, get_session
    from src.engines.outcome_evaluation import FORWARD_OUTCOME_PROTOCOL_VERSION

    s = get_session()
    try:
        q = s.query(ForwardOutcomeEvaluation).filter(
            ForwardOutcomeEvaluation.outcome_protocol_version
            == FORWARD_OUTCOME_PROTOCOL_VERSION,
        )
        if not include_pending:
            # Still show all created rows; dashboard decides what to display
            pass
        return q.all()
    finally:
        s.close()


# ── Internal processing ───────────────────────────────────────────────────────


def _process_signal(
    session,
    fs,
    as_of_date,
    price_data,
    overnight_map,
    live_event_map,
    cancel_event_map,
    trading_calendar,
) -> int:
    from src.engines.outcome_evaluation import (
        EXEC_EXECUTED,
        PATH_AWARE,
        PATH_BASELINE,
        check_overnight_eligibility,
        find_aware_entry,
        find_baseline_entry,
    )

    stock_id = fs.stock_id
    signal_date = fs.trade_date
    exec_date = fs.execution_date
    sig_eval_id = f"{stock_id}_{signal_date}"

    pd = price_data.get(stock_id, {})
    stock_dates = pd.get("dates", [])
    close_map = pd.get("close", {})
    high_map = pd.get("high", {})
    low_map = pd.get("low", {})

    b0050 = price_data.get("0050", {})
    open_0050 = b0050.get("open", {})
    b_dates = b0050.get("dates", [])
    b_close_map = b0050.get("close", {})

    # Overnight context for this execution_date
    omc = overnight_map.get(exec_date)
    overnight_context_id = omc.id if omc else None
    overnight_rule_version = omc.overnight_rule_version if omc else None
    overnight_risk_level = omc.risk_level if omc else None

    excl = check_overnight_eligibility(
        exec_date, overnight_context_id, overnight_rule_version
    )

    live_rule = _get_live_rule_version(live_event_map, stock_id, signal_date)

    rows_affected = 0

    for path_type, entry_fn_result in [
        (
            PATH_BASELINE,
            find_baseline_entry(
                exec_date, fs.execution_price, fs.execution_price_type, open_0050
            ),
        ),
        (
            PATH_AWARE,
            find_aware_entry(
                exec_date,
                _get_live_events(live_event_map, stock_id, signal_date),
                _get_live_events(
                    cancel_event_map, stock_id, signal_date
                ),  # CANCEL events
                as_of_date,
                trading_calendar,
                open_0050,
            ),
        ),
    ]:
        row = _get_or_create_row(
            session,
            fs.id,
            sig_eval_id,
            stock_id,
            signal_date,
            path_type,
            overnight_context_id,
            overnight_rule_version,
            overnight_risk_level,
            live_rule,
            excl,
        )
        changed = _apply_entry(row, entry_fn_result)

        if row.entry_status == EXEC_EXECUTED and entry_fn_result.entry_price:
            changed |= _fill_horizons(
                row,
                entry_fn_result,
                fs,
                stock_dates,
                close_map,
                high_map,
                low_map,
                b_dates,
                b_close_map,
            )

        if changed:
            row.updated_at = datetime.utcnow()
            rows_affected += 1

    return rows_affected


def _get_or_create_row(
    session,
    forward_signal_id,
    sig_eval_id,
    stock_id,
    signal_date,
    path_type,
    overnight_context_id,
    overnight_rule_version,
    overnight_risk_level,
    live_rule,
    exclusion_reason,
):
    from src.database import ForwardOutcomeEvaluation
    from src.engines.outcome_evaluation import FORWARD_OUTCOME_PROTOCOL_VERSION

    row = (
        session.query(ForwardOutcomeEvaluation)
        .filter(
            ForwardOutcomeEvaluation.forward_signal_id == forward_signal_id,
            ForwardOutcomeEvaluation.path_type == path_type,
            ForwardOutcomeEvaluation.outcome_protocol_version
            == FORWARD_OUTCOME_PROTOCOL_VERSION,
        )
        .first()
    )
    if row is None:
        row = ForwardOutcomeEvaluation(
            forward_signal_id=forward_signal_id,
            signal_evaluation_id=sig_eval_id,
            stock_id=stock_id,
            signal_date=signal_date,
            path_type=path_type,
            outcome_protocol_version=FORWARD_OUTCOME_PROTOCOL_VERSION,
            overnight_context_id=overnight_context_id,
            overnight_rule_version=overnight_rule_version,
            overnight_risk_level=overnight_risk_level,
            live_rule_version=live_rule,
            exclusion_reason=exclusion_reason,
            transaction_cost_assumption=ROUND_TRIP_COST,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(row)
        session.flush()  # get id
    return row


def _apply_entry(row, entry: "EntryResult") -> bool:
    """Apply entry result to row. Returns True if anything changed."""
    changed = False
    fields = [
        ("entry_status", entry.entry_status),
        ("entry_date", entry.entry_date),
        ("entry_price", entry.entry_price),
        ("entry_price_type", entry.entry_price_type),
        ("entry_timestamp", entry.entry_timestamp),
        ("entry_quote_quality", entry.entry_quote_quality),
        ("mae_mfe_start_date", entry.mae_mfe_start_date),
        ("entry_day_excursion_excluded", entry.entry_day_excursion_excluded),
        ("benchmark_entry_date", entry.benchmark_entry_date),
        ("benchmark_entry_price", entry.benchmark_entry_price),
        ("benchmark_entry_price_type", entry.benchmark_entry_price_type),
        ("benchmark_timing_approximation", entry.benchmark_timing_approximation),
    ]
    for attr, val in fields:
        if getattr(row, attr) != val:
            setattr(row, attr, val)
            changed = True
    return changed


def _fill_horizons(
    row,
    entry_result,
    fs,
    stock_dates,
    close_map,
    high_map,
    low_map,
    b_dates,
    b_close_map,
) -> bool:
    """Fill 20D and 60D bundles if not yet matured. Honors immutability guards."""
    from src.engines.outcome_evaluation import (
        ODQ_INCOMPLETE_HORIZON,
        compute_horizon_bundle,
    )

    changed = False

    for n_days, matured_attr, bundle_attrs in [
        (20, "horizon_20d_matured_at", _20D_ATTRS),
        (60, "horizon_60d_matured_at", _60D_ATTRS),
    ]:
        if getattr(row, matured_attr) is not None:
            continue  # immutable — do not overwrite

        bundle = compute_horizon_bundle(
            entry_price=entry_result.entry_price,
            entry_date=entry_result.entry_date,
            mae_mfe_start_date=entry_result.mae_mfe_start_date,
            n_days=n_days,
            stop_price=fs.stop_price,
            target1=fs.target1,
            stock_dates=stock_dates,
            close_map=close_map,
            high_map=high_map,
            low_map=low_map,
            benchmark_entry_price=entry_result.benchmark_entry_price,
            benchmark_entry_date=entry_result.benchmark_entry_date,
            benchmark_dates=b_dates,
            benchmark_close_map=b_close_map,
            round_trip_cost=ROUND_TRIP_COST,
        )

        if bundle.data_quality == ODQ_INCOMPLETE_HORIZON:
            continue  # not yet mature; check again next pipeline run

        # Bundle is mature — write and lock
        suffix = "_20d" if n_days == 20 else "_60d"
        _write_bundle(row, bundle, suffix)
        setattr(row, matured_attr, datetime.utcnow())
        changed = True

    return changed


_20D_ATTRS = [
    "return_20d",
    "alpha_20d",
    "mae_20d",
    "mfe_20d",
    "target_stop_outcome_20d",
    "target_hit_date_20d",
    "stop_hit_date_20d",
    "outcome_data_quality_20d",
]
_60D_ATTRS = [
    "return_60d",
    "alpha_60d",
    "mae_60d",
    "mfe_60d",
    "target_stop_outcome_60d",
    "target_hit_date_60d",
    "stop_hit_date_60d",
    "outcome_data_quality_60d",
]


def _write_bundle(row, bundle, suffix: str) -> None:
    setattr(row, f"return{suffix}", bundle.return_pct)
    setattr(row, f"alpha{suffix}", bundle.alpha_pct)
    setattr(row, f"mae{suffix}", bundle.mae_pct)
    setattr(row, f"mfe{suffix}", bundle.mfe_pct)
    setattr(row, f"target_stop_outcome{suffix}", bundle.target_stop_outcome)
    setattr(row, f"target_hit_date{suffix}", bundle.target_hit_date)
    setattr(row, f"stop_hit_date{suffix}", bundle.stop_hit_date)
    setattr(row, f"outcome_data_quality{suffix}", bundle.data_quality)


def _get_live_events(live_event_map: dict, stock_id: str, signal_date) -> list:
    from src.engines.outcome_evaluation import _LiveEvent

    raw = live_event_map.get((stock_id, signal_date), [])
    return [
        _LiveEvent(
            observed_at=e.observed_at,
            current_price=e.current_price,
            quote_quality=e.quote_quality,
            quote_trade_date=e.quote_trade_date,
        )
        for e in raw
    ]


def _get_live_rule_version(
    live_event_map: dict, stock_id: str, signal_date
) -> Optional[str]:
    evs = live_event_map.get((stock_id, signal_date), [])
    for e in evs:
        if e.live_rule_version:
            return e.live_rule_version
    return None


# ── Batch data loaders ────────────────────────────────────────────────────────


def _load_price_data(session, signals: list) -> dict:
    """Returns {stock_id: {dates, close, high, low, open}} for all signal stocks + 0050."""
    from datetime import timedelta

    from src.database import DailyPrice

    all_sids = {fs.stock_id for fs in signals} | {"0050"}
    min_date = min(fs.execution_date for fs in signals if fs.execution_date)
    max_date = min_date + timedelta(days=365)  # 60 trading days ≈ ~90 calendar days

    rows = (
        session.query(
            DailyPrice.stock_id,
            DailyPrice.date,
            DailyPrice.close,
            DailyPrice.high,
            DailyPrice.low,
            DailyPrice.open,
        )
        .filter(
            DailyPrice.stock_id.in_(all_sids),
            DailyPrice.date >= min_date,
            DailyPrice.date <= max_date,
        )
        .order_by(DailyPrice.stock_id, DailyPrice.date)
        .all()
    )

    result: dict = {}
    for sid, d, c, hi, lo, op in rows:
        if sid not in result:
            result[sid] = {"dates": [], "close": {}, "high": {}, "low": {}, "open": {}}
        result[sid]["dates"].append(d)
        if c is not None:
            result[sid]["close"][d] = c
        if hi is not None:
            result[sid]["high"][d] = hi
        if lo is not None:
            result[sid]["low"][d] = lo
        if op is not None:
            result[sid]["open"][d] = op
    return result


def _load_overnight_contexts(session, signals: list) -> dict:
    """Returns {execution_date: OvernightMarketContext} for all signal execution dates."""
    from src.database import OvernightMarketContext
    from src.engines.overnight_risk import OVERNIGHT_RULE_VERSION

    exec_dates = {fs.execution_date for fs in signals if fs.execution_date}
    if not exec_dates:
        return {}
    rows = (
        session.query(OvernightMarketContext)
        .filter(
            OvernightMarketContext.execution_date.in_(exec_dates),
            OvernightMarketContext.overnight_rule_version == OVERNIGHT_RULE_VERSION,
        )
        .all()
    )
    return {r.execution_date: r for r in rows}


def _load_live_events(session, signals: list) -> dict:
    """Returns {(stock_id, signal_date): [LiveExecutionEvent]} for ENTRY_RECONFIRMED events."""
    from src.database import LiveExecutionEvent
    from src.engines.live_decision import LiveStatus

    keys = [(fs.stock_id, fs.trade_date) for fs in signals]
    if not keys:
        return {}
    all_sids = list({k[0] for k in keys})
    all_sdates = list({k[1] for k in keys})

    rows = (
        session.query(LiveExecutionEvent)
        .filter(
            LiveExecutionEvent.stock_id.in_(all_sids),
            LiveExecutionEvent.signal_date.in_(all_sdates),
            LiveExecutionEvent.live_status == LiveStatus.ENTRY_RECONFIRMED.value,
        )
        .all()
    )
    result: dict = {}
    for r in rows:
        key = (r.stock_id, r.signal_date)
        if key not in result:
            result[key] = []
        result[key].append(r)
    return result


def _load_cancel_events(session, signals: list) -> dict:
    """
    Returns {(stock_id, signal_date): [LiveExecutionEvent]} for CANCEL transitions.

    CANCEL (stop-loss trigger) is the only event that constitutes formal lifecycle
    invalidation. RAPID_DROP does NOT generate CANCEL events.
    Used by outcome_service to determine temporal order vs ENTRY_RECONFIRMED (P0-1).
    """
    from src.database import LiveExecutionEvent
    from src.engines.live_decision import LiveStatus

    keys = [(fs.stock_id, fs.trade_date) for fs in signals]
    if not keys:
        return {}
    all_sids = list({k[0] for k in keys})
    all_sdates = list({k[1] for k in keys})

    rows = (
        session.query(LiveExecutionEvent)
        .filter(
            LiveExecutionEvent.stock_id.in_(all_sids),
            LiveExecutionEvent.signal_date.in_(all_sdates),
            LiveExecutionEvent.live_status == LiveStatus.CANCEL.value,
        )
        .all()
    )
    result: dict = {}
    for r in rows:
        key = (r.stock_id, r.signal_date)
        if key not in result:
            result[key] = []
        result[key].append(r)
    return result


def _load_trading_calendar(session) -> list:
    """Return sorted list of all known TW trading dates (from DailyPrice for 0050)."""
    from src.database import DailyPrice

    rows = (
        session.query(DailyPrice.date)
        .filter(DailyPrice.stock_id == "0050")
        .order_by(DailyPrice.date)
        .all()
    )
    return [r.date for r in rows]
