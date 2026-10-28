"""
outcome_evaluation.py — Forward Outcome Evaluation Protocol v1 (foe_v1)

Pre-registered evaluation protocol: definitions frozen BEFORE outcomes were observed.
All constants, entry definitions, MAE/MFE windows, stop/T1 logic, and benchmark
handling are immutable for foe_v1. Semantics changes require foe_v2.

Protocol constants:
  FORWARD_OUTCOME_PROTOCOL_VERSION = "foe_v1"
  FOE_V1_AWARE_ENTRY_WINDOW_TRADING_DAYS = 3

This module contains PURE FUNCTIONS ONLY — no DB access.
"""

import bisect
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Pre-registration constants ────────────────────────────────────────────────

FORWARD_OUTCOME_PROTOCOL_VERSION = "foe_v1"
FOE_V1_AWARE_ENTRY_WINDOW_TRADING_DAYS = 3  # pre-registered: not 5, not 7, not 10

# Path types
PATH_BASELINE = "BASELINE_NEXT_OPEN"
PATH_AWARE = "OVERNIGHT_AWARE_RECONFIRMED"

# Entry execution statuses
EXEC_EXECUTED = "EXECUTED"
EXEC_EXPIRED_BEFORE_ENTRY = (
    "EXPIRED_BEFORE_ENTRY"  # window elapsed, no ENTRY_RECONFIRMED
)
EXEC_INVALIDATED_BEFORE_ENTRY = (
    "INVALIDATED_BEFORE_ENTRY"  # lifecycle=invalidated during window
)
EXEC_PENDING = "PENDING"  # window not yet elapsed
EXEC_DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
EXEC_NOT_APPLICABLE = "NOT_APPLICABLE"  # signal not BUY or no execution_price

# Target/Stop outcomes
OUTCOME_T1_FIRST = "T1_FIRST"
OUTCOME_STOP_FIRST = "STOP_FIRST"
OUTCOME_SAME_DAY_AMBIGUOUS = "SAME_DAY_AMBIGUOUS"
OUTCOME_NEITHER = "NEITHER"

# Outcome data quality
ODQ_COMPLETE = "COMPLETE"
ODQ_INCOMPLETE_HORIZON = "INCOMPLETE_HORIZON"
ODQ_BENCHMARK_MISSING = "BENCHMARK_MISSING"
ODQ_INVALID_PRICE_PATH = "INVALID_PRICE_PATH"

# Exclusion reasons
EXCL_NO_OVERNIGHT_DATA = "NO_OVERNIGHT_DATA"
EXCL_MISSING_VALID_NEXT_OPEN_ENTRY = "MISSING_VALID_NEXT_OPEN_ENTRY"
EXCL_RETROACTIVE_OVERNIGHT_CONTEXT = "RETROACTIVE_OVERNIGHT_CONTEXT"

# Entry price type labels (for audit trail)
EPT_BASELINE_NEXT_OPEN = "BASELINE_NEXT_OPEN"
EPT_LIVE_ENTRY_RECONFIRMED_QUOTE = "LIVE_ENTRY_RECONFIRMED_QUOTE"
BENCHMARK_PRICE_TYPE_0050_OPEN = "0050_DAILY_OPEN"


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class EntryResult:
    """Outcome of entry-price determination for one evaluation path."""

    entry_status: str
    entry_date: Optional[date] = None
    entry_price: Optional[float] = None
    entry_price_type: Optional[str] = None
    entry_timestamp: Optional[datetime] = None  # Aware path only
    entry_quote_quality: Optional[str] = None  # Aware path only
    mae_mfe_start_date: Optional[date] = None  # entry_date or next_td(entry_date)
    entry_day_excursion_excluded: bool = False  # True for Aware path
    benchmark_entry_date: Optional[date] = None
    benchmark_entry_price: Optional[float] = None
    benchmark_entry_price_type: Optional[str] = None
    benchmark_timing_approximation: bool = False  # True for Aware path
    exclusion_reason: Optional[str] = None


@dataclass
class HorizonBundle:
    """Outcome metrics for a single horizon (20D or 60D)."""

    n_days: int
    return_pct: Optional[float]
    alpha_pct: Optional[float]
    mae_pct: Optional[float]
    mfe_pct: Optional[float]
    target_stop_outcome: Optional[
        str
    ]  # T1_FIRST / STOP_FIRST / SAME_DAY_AMBIGUOUS / NEITHER
    target_hit_date: Optional[date]
    stop_hit_date: Optional[date]
    data_quality: str
    used_close_fallback: bool = False


# ── Baseline entry (Path A) ───────────────────────────────────────────────────


def find_baseline_entry(
    execution_date: Optional[date],
    execution_price: Optional[float],
    execution_price_type: Optional[str],
    open_0050_map: dict,  # {date: float} — 0050 daily open prices
) -> EntryResult:
    """
    foe_v1 §5: Baseline entry uses ForwardSignal.execution_price (NEXT_OPEN only).
    Missing or non-NEXT_OPEN execution_price → INELIGIBLE (not substituted).
    """
    if execution_price_type != "NEXT_OPEN":
        return EntryResult(
            entry_status=EXEC_NOT_APPLICABLE,
            exclusion_reason=EXCL_MISSING_VALID_NEXT_OPEN_ENTRY,
        )
    if execution_price is None or execution_price <= 0:
        return EntryResult(
            entry_status=EXEC_DATA_INSUFFICIENT,
            exclusion_reason=EXCL_MISSING_VALID_NEXT_OPEN_ENTRY,
        )
    if execution_date is None:
        return EntryResult(
            entry_status=EXEC_DATA_INSUFFICIENT,
            exclusion_reason=EXCL_MISSING_VALID_NEXT_OPEN_ENTRY,
        )

    # 0050 benchmark: exact-date open match (§58 — no nearest-date fallback)
    bmark_price = open_0050_map.get(execution_date)
    if bmark_price is None or bmark_price <= 0:
        # Baseline still EXECUTED; benchmark missing is captured in horizon data_quality
        bmark_price = None
        bmark_date = None
    else:
        bmark_date = execution_date

    return EntryResult(
        entry_status=EXEC_EXECUTED,
        entry_date=execution_date,
        entry_price=execution_price,
        entry_price_type=EPT_BASELINE_NEXT_OPEN,
        mae_mfe_start_date=execution_date,  # entry day included (§18)
        entry_day_excursion_excluded=False,
        benchmark_entry_date=bmark_date,
        benchmark_entry_price=bmark_price,
        benchmark_entry_price_type=(
            BENCHMARK_PRICE_TYPE_0050_OPEN if bmark_price else None
        ),
        benchmark_timing_approximation=False,
    )


# ── Aware entry (Path B) ─────────────────────────────────────────────────────


@dataclass
class _LiveEvent:
    """Minimal view of LiveExecutionEvent for entry determination."""

    observed_at: datetime
    current_price: Optional[float]
    quote_quality: Optional[str]
    quote_trade_date: Optional[str]  # "YYYYMMDD" string


def find_aware_entry(
    execution_date: date,
    live_events: list,  # _LiveEvent list — ENTRY_RECONFIRMED transitions only
    invalidation_events: list,  # _LiveEvent list — CANCEL transitions only (formal lifecycle)
    as_of_date: date,
    trading_calendar: list,  # sorted list of TW trading dates
    open_0050_map: dict,  # {date: float}
) -> EntryResult:
    """
    foe_v1 §6-§9: Aware entry uses first valid ENTRY_RECONFIRMED within 3-session window.

    Window: execution_date (Day 1), Day 2, Day 3.

    Temporal-order rules (P0-1 — based on event observed_at, not final Recommendation.lifecycle_status):
      ENTRY_RECONFIRMED before CANCEL (or no CANCEL in window) → EXECUTED
      CANCEL in window before ENTRY_RECONFIRMED (or no reconfirm) → INVALIDATED_BEFORE_ENTRY
      Window not yet elapsed, no events → PENDING
      Window elapsed, no reconfirm, no in-window CANCEL → EXPIRED_BEFORE_ENTRY

    RAPID_DROP does NOT generate a CANCEL event — RAPID_DROP ≠ INVALIDATED.
    Only live_status == CANCEL (stop-loss trigger) counts as formal invalidation.
    """
    window_dates = _window_trading_days(
        execution_date, FOE_V1_AWARE_ENTRY_WINDOW_TRADING_DAYS, trading_calendar
    )
    if not window_dates:
        return EntryResult(
            entry_status=EXEC_DATA_INSUFFICIENT,
            exclusion_reason="WINDOW_CALENDAR_MISSING",
        )

    window_end = window_dates[-1]

    valid_event = _find_first_valid_reconfirmation(live_events, window_dates)
    cancel_event = _find_first_cancel_in_window(invalidation_events, window_dates)

    # Both present: temporal order decides
    if valid_event is not None and cancel_event is not None:
        if valid_event.observed_at <= cancel_event.observed_at:
            # ENTRY_RECONFIRMED came first (or tied) → EXECUTED
            pass  # fall through to EXECUTED block below
        else:
            # CANCEL came before ENTRY_RECONFIRMED → INVALIDATED_BEFORE_ENTRY
            return EntryResult(entry_status=EXEC_INVALIDATED_BEFORE_ENTRY)

    if valid_event is not None:
        event_trade_date = _parse_quote_trade_date(valid_event.quote_trade_date)
        entry_date = (
            event_trade_date
            if event_trade_date
            else _observed_at_to_tw_date(valid_event.observed_at)
        )
        if entry_date is None:
            return EntryResult(entry_status=EXEC_DATA_INSUFFICIENT)

        bmark_price = open_0050_map.get(entry_date)
        if bmark_price is not None and bmark_price <= 0:
            bmark_price = None
        bmark_date = entry_date if bmark_price else None

        next_td = _next_td_in_calendar(entry_date, trading_calendar)

        return EntryResult(
            entry_status=EXEC_EXECUTED,
            entry_date=entry_date,
            entry_price=valid_event.current_price,
            entry_price_type=EPT_LIVE_ENTRY_RECONFIRMED_QUOTE,
            entry_timestamp=valid_event.observed_at,
            entry_quote_quality=valid_event.quote_quality,
            mae_mfe_start_date=next_td,
            entry_day_excursion_excluded=True,
            benchmark_entry_date=bmark_date,
            benchmark_entry_price=bmark_price,
            benchmark_entry_price_type=(
                BENCHMARK_PRICE_TYPE_0050_OPEN if bmark_price else None
            ),
            benchmark_timing_approximation=True,
        )

    # No valid ENTRY_RECONFIRMED
    if cancel_event is not None:
        # CANCEL within window, no prior reconfirm → INVALIDATED_BEFORE_ENTRY
        return EntryResult(entry_status=EXEC_INVALIDATED_BEFORE_ENTRY)

    if as_of_date <= window_end:
        return EntryResult(entry_status=EXEC_PENDING)

    return EntryResult(entry_status=EXEC_EXPIRED_BEFORE_ENTRY)


def _window_trading_days(start: date, n: int, trading_calendar: list) -> list:
    """Return list of n trading days starting from start (inclusive)."""
    idx = bisect.bisect_left(trading_calendar, start)
    if idx >= len(trading_calendar) or trading_calendar[idx] != start:
        # start not a known trading day; find the next one
        if idx >= len(trading_calendar):
            return []
    end_idx = idx + n
    if end_idx > len(trading_calendar):
        end_idx = len(trading_calendar)
    return trading_calendar[idx:end_idx]


def _find_first_cancel_in_window(
    invalidation_events: list, window_dates: list
) -> Optional[_LiveEvent]:
    """
    Return earliest CANCEL event whose trade_date falls within window_dates.
    Formal invalidation only — RAPID_DROP does not produce CANCEL events.
    Falls back to observed_at.date() if quote_trade_date is missing.
    """
    window_set = set(window_dates)
    candidates = []
    for ev in invalidation_events:
        if ev.observed_at is None:
            continue
        trade_date = _parse_quote_trade_date(
            ev.quote_trade_date
        ) or _observed_at_to_tw_date(ev.observed_at)
        if trade_date is None or trade_date not in window_set:
            continue
        candidates.append(ev)
    if not candidates:
        return None
    return min(candidates, key=lambda e: e.observed_at)


def _find_first_valid_reconfirmation(
    events: list, window_dates: list
) -> Optional[_LiveEvent]:
    """
    Return the earliest valid ENTRY_RECONFIRMED event within window_dates.

    Validation (§9):
      - quote_quality == "valid"
      - current_price > 0
      - observed_at exists
      - quote_trade_date falls within window_dates
    """
    window_set = set(window_dates)
    candidates = []
    for ev in events:
        if ev.current_price is None or ev.current_price <= 0:
            continue
        if ev.quote_quality != "valid":
            continue
        if ev.observed_at is None:
            continue
        trade_date = _parse_quote_trade_date(ev.quote_trade_date)
        if trade_date is None or trade_date not in window_set:
            continue
        candidates.append(ev)
    if not candidates:
        return None
    return min(candidates, key=lambda e: e.observed_at)


def _parse_quote_trade_date(s: Optional[str]) -> Optional[date]:
    """Parse "YYYYMMDD" string → date. Returns None on any format error."""
    if not s or len(s) != 8:
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, TypeError):
        return None


def _observed_at_to_tw_date(observed_at: Optional[datetime]) -> Optional[date]:
    """Extract Taiwan date from observed_at (stored as UTC-naive, approximate)."""
    if observed_at is None:
        return None
    return observed_at.date()


def _next_td_in_calendar(d: date, trading_calendar: list) -> Optional[date]:
    """Return the trading day immediately after d in trading_calendar."""
    idx = bisect.bisect_right(trading_calendar, d)
    if idx >= len(trading_calendar):
        return None
    return trading_calendar[idx]


# ── Horizon computation (shared by Baseline and Aware) ───────────────────────


def compute_horizon_bundle(
    entry_price: float,
    entry_date: date,
    mae_mfe_start_date: Optional[date],  # entry_date (Baseline) or next_td (Aware)
    n_days: int,  # 20 or 60
    stop_price: Optional[float],
    target1: Optional[float],
    stock_dates: list,  # sorted trading dates with price data
    close_map: dict,  # {date: float}
    high_map: dict,  # {date: float}
    low_map: dict,  # {date: float}
    benchmark_entry_price: Optional[float],
    benchmark_entry_date: Optional[date],
    benchmark_dates: list,  # sorted 0050 dates
    benchmark_close_map: dict,  # {date: float} — 0050 closes
    round_trip_cost: float,
) -> HorizonBundle:
    """
    foe_v1 §12–§27: Compute return, alpha, MAE/MFE, and stop/T1 for a single horizon.

    Return: nth close / entry_price (from entry_date, not mae_mfe_start_date).
    MAE/MFE: scan from mae_mfe_start_date through exit_date (inclusive).
    Stop/T1: scan from mae_mfe_start_date through exit_date using Daily H/L.

    Invariant (only when both 20D and 60D bundles computed with same start):
      MAE60 <= MAE20,  MFE60 >= MFE20
    """
    empty = HorizonBundle(
        n_days=n_days,
        return_pct=None,
        alpha_pct=None,
        mae_pct=None,
        mfe_pct=None,
        target_stop_outcome=None,
        target_hit_date=None,
        stop_hit_date=None,
        data_quality=ODQ_INVALID_PRICE_PATH,
    )

    # Locate entry_date in stock_dates
    entry_idx = bisect.bisect_left(stock_dates, entry_date)
    if entry_idx >= len(stock_dates) or stock_dates[entry_idx] != entry_date:
        logger.debug("compute_horizon: entry_date %s not in stock_dates", entry_date)
        return empty

    # Locate exit_date (nth trading day AFTER entry_date)
    exit_idx = entry_idx + n_days
    if exit_idx >= len(stock_dates):
        return HorizonBundle(
            n_days=n_days,
            return_pct=None,
            alpha_pct=None,
            mae_pct=None,
            mfe_pct=None,
            target_stop_outcome=None,
            target_hit_date=None,
            stop_hit_date=None,
            data_quality=ODQ_INCOMPLETE_HORIZON,
        )
    exit_date = stock_dates[exit_idx]
    exit_close = close_map.get(exit_date)
    if exit_close is None:
        return HorizonBundle(
            n_days=n_days,
            return_pct=None,
            alpha_pct=None,
            mae_pct=None,
            mfe_pct=None,
            target_stop_outcome=None,
            target_hit_date=None,
            stop_hit_date=None,
            data_quality=ODQ_INCOMPLETE_HORIZON,
        )

    # Stock return
    stock_ret = round((exit_close / entry_price - 1) * 100 - round_trip_cost, 4)

    # Benchmark return (exact-date match only, §58)
    alpha = None
    data_quality = ODQ_COMPLETE
    if benchmark_entry_price is None or benchmark_entry_date is None:
        data_quality = ODQ_BENCHMARK_MISSING
    else:
        bmark_entry_idx = bisect.bisect_left(benchmark_dates, benchmark_entry_date)
        if (
            bmark_entry_idx >= len(benchmark_dates)
            or benchmark_dates[bmark_entry_idx] != benchmark_entry_date
        ):
            data_quality = ODQ_BENCHMARK_MISSING
        else:
            bmark_exit_idx = bmark_entry_idx + n_days
            if bmark_exit_idx >= len(benchmark_dates):
                data_quality = ODQ_BENCHMARK_MISSING
            else:
                bmark_exit_close = benchmark_close_map.get(
                    benchmark_dates[bmark_exit_idx]
                )
                if bmark_exit_close is None:
                    data_quality = ODQ_BENCHMARK_MISSING
                else:
                    # P0-2: benchmark return is raw — round_trip_cost is a stock-side cost only
                    # Alpha = (stock_raw - cost) - benchmark_raw
                    bmark_ret = round(
                        (bmark_exit_close / benchmark_entry_price - 1) * 100, 4
                    )
                    alpha = round(stock_ret - bmark_ret, 4)

    # MAE/MFE scan window: mae_mfe_start_date → exit_date (inclusive)
    mae, mfe, used_close_fallback = _scan_mae_mfe(
        entry_price, mae_mfe_start_date, exit_date, stock_dates, high_map, low_map
    )

    # Stop/T1 scan: same window as MAE/MFE
    stop_outcome, stop_hit_date, target_hit_date, ts_close_fallback = _scan_stop_t1(
        entry_price,
        stop_price,
        target1,
        mae_mfe_start_date,
        exit_date,
        stock_dates,
        high_map,
        low_map,
        close_map,
    )
    if ts_close_fallback:
        used_close_fallback = True

    return HorizonBundle(
        n_days=n_days,
        return_pct=stock_ret,
        alpha_pct=alpha,
        mae_pct=mae,
        mfe_pct=mfe,
        target_stop_outcome=stop_outcome,
        target_hit_date=target_hit_date,
        stop_hit_date=stop_hit_date,
        data_quality=data_quality,
        used_close_fallback=used_close_fallback,
    )


def _scan_mae_mfe(
    entry_price: float,
    scan_start: Optional[date],
    scan_end: date,
    stock_dates: list,
    high_map: dict,
    low_map: dict,
) -> tuple:
    """
    Returns (mae_pct, mfe_pct, used_close_fallback).
    scan_start is None only if Aware path has no next trading day (→ (None, None, False)).
    """
    if scan_start is None:
        return None, None, False

    start_idx = bisect.bisect_left(stock_dates, scan_start)
    end_idx = bisect.bisect_right(stock_dates, scan_end)  # inclusive end

    min_val = None
    max_val = None
    used_close_fallback = False

    for d in stock_dates[start_idx:end_idx]:
        lo = low_map.get(d)
        hi = high_map.get(d)
        if lo is None or hi is None:
            used_close_fallback = True
            continue
        lo_pct = (lo / entry_price - 1) * 100
        hi_pct = (hi / entry_price - 1) * 100
        if min_val is None or lo_pct < min_val:
            min_val = lo_pct
        if max_val is None or hi_pct > max_val:
            max_val = hi_pct

    mae = round(min_val, 4) if min_val is not None else None
    mfe = round(max_val, 4) if max_val is not None else None
    return mae, mfe, used_close_fallback


def _scan_stop_t1(
    entry_price: float,
    stop_price: Optional[float],
    target1: Optional[float],
    scan_start: Optional[date],
    scan_end: date,
    stock_dates: list,
    high_map: dict,
    low_map: dict,
    close_map: dict,
) -> tuple:
    """
    Returns (outcome, stop_hit_date, target_hit_date, used_close_fallback).

    Outcome codes: T1_FIRST / STOP_FIRST / SAME_DAY_AMBIGUOUS / NEITHER.
    SAME_DAY_AMBIGUOUS: both hit on same day, intraday order unknown.
    (§23–§25: ambiguous cases excluded from resolved denominator.)
    """
    if scan_start is None:
        return OUTCOME_NEITHER, None, None, False

    start_idx = bisect.bisect_left(stock_dates, scan_start)
    end_idx = bisect.bisect_right(stock_dates, scan_end)

    stop_day = None
    target_day = None
    used_close_fallback = False

    for d in stock_dates[start_idx:end_idx]:
        lo = low_map.get(d)
        hi = high_map.get(d)
        if lo is None or hi is None:
            used_close_fallback = True
        chk_lo = lo if lo is not None else close_map.get(d)
        chk_hi = hi if hi is not None else close_map.get(d)

        if stop_day is None and stop_price and stop_price > 0 and chk_lo is not None:
            if chk_lo <= stop_price:
                stop_day = d
        if target_day is None and target1 and target1 > 0 and chk_hi is not None:
            if chk_hi >= target1:
                target_day = d

        # Stop scanning once both found
        if stop_day is not None and target_day is not None:
            break

    if stop_day is not None and target_day is not None:
        if target_day < stop_day:
            return OUTCOME_T1_FIRST, stop_day, target_day, used_close_fallback
        elif stop_day < target_day:
            return OUTCOME_STOP_FIRST, stop_day, target_day, used_close_fallback
        else:  # same day — §24 SAME_DAY_AMBIGUOUS
            return OUTCOME_SAME_DAY_AMBIGUOUS, stop_day, target_day, used_close_fallback
    elif target_day is not None:
        return OUTCOME_T1_FIRST, None, target_day, used_close_fallback
    elif stop_day is not None:
        return OUTCOME_STOP_FIRST, stop_day, None, used_close_fallback
    else:
        return OUTCOME_NEITHER, None, None, used_close_fallback


# ── Eligibility helpers ───────────────────────────────────────────────────────


def check_overnight_eligibility(
    execution_date: date,
    overnight_context_id: Optional[int],
    overnight_rule_version: Optional[str],
) -> Optional[str]:
    """
    Returns exclusion_reason string if signal is ineligible for formal overnight cohort,
    None if eligible. (§3 — NO retroactive backfill.)
    """
    if overnight_context_id is None or overnight_rule_version is None:
        return EXCL_NO_OVERNIGHT_DATA
    return None
