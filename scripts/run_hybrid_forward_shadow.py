"""
scripts/run_hybrid_forward_shadow.py — Hybrid V1 Prospective Forward Shadow (v2)

RESEARCH ONLY — NOT A PRODUCTION SYSTEM.
Writes to research SQLite only (data/platform.db — research tables).
Does NOT touch production Neon PostgreSQL or any live positions.

Design guarantees:
  1. Append-only decisions: hybrid_forward_decision is NEVER updated after insert.
  2. Conflict detection: same (stock, date, rule_version) with different decision
     → recorded as CONFLICT, never silently overwritten.
  3. Outcome separation: hybrid_forward_outcome is a separate table; decisions
     remain immutable when outcomes are added.
  4. Capture classification: each record is tagged PROSPECTIVE / LATE_CAPTURE /
     RETROSPECTIVE_RECONSTRUCTION / INVALID_DATA.
  5. Run log: every execution is recorded in hybrid_forward_run_log.
  6. Trading-day maturity: 5D/10D/20D outcomes use Taiwan trading days (0050 proxy),
     not calendar days.
  7. Stale data guard: refuses to run if DailyPrice is not fresh for trade_date.

SAFETY LIMITS:
  - Signals before RULE_FREEZE_DATE (2026-11-05) are classified RETROSPECTIVE_RECONSTRUCTION.
  - Only the production Neon DB holds ForwardSignals; this script reads DailyPrice only.
  - No production migrations, no ForwardSignal writes, no MODEL_VERSION changes.

Usage:
  python scripts/run_hybrid_forward_shadow.py               # today
  python scripts/run_hybrid_forward_shadow.py --date 2026-11-06
  python scripts/run_hybrid_forward_shadow.py --date 2026-11-06 --force-stale
  python scripts/run_hybrid_forward_shadow.py --backfill-outcomes-only
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.research.effectiveness_analyzer import STOP_BUFFER, classify_ma_slope, compute_ma_slope
from src.research.execution_simulator import FEES_PCT
from src.research.hybrid_entry_strategy import HybridDecisionService, RULE_VERSION
from src.research.full_market_freshness_gate import FreshnessStatus, check_market_freshness
from src.research.ohlc_continuity_gate import GateResult, OHLCContinuityGate
from src.research.hybrid_forward_db import (
    CALCULATION_VERSION,
    RESEARCH_VERSION,
    ConflictError,
    HybridForwardDecision,
    HybridForwardOutcome,
    HybridForwardRunLog,
    OutcomeStatus,
    RunStatus,
    classify_capture,
    compute_decision_hash,
    compute_input_data_hash,
    ensure_schema,
    get_operational_summary,
    get_pending_outcome_decisions,
    insert_decision,
    insert_outcome,
    new_run_id,
    upsert_run_log,
)
from src.research.hybrid_trading_calendar import TradingCalendar

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")

MIN_HIST_BARS = 70
STALE_DATA_TOLERANCE_DAYS = 7   # allow DailyPrice up to 7 calendar days old before blocking
OUTCOME_MATURITY_BUFFER_DAYS = 2  # extra calendar days after theoretical maturity before computing
HOLD_PERIODS = {"5d": 5, "10d": 10, "20d": 20}

# ── Data freshness check ──────────────────────────────────────────────────────

def _get_dailyprice_last_date(conn: sqlite3.Connection) -> Optional[date]:
    row = conn.execute(
        "SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'"
    ).fetchone()
    return date.fromisoformat(row[0]) if row and row[0] else None


def _is_data_fresh(last_date: Optional[date], trade_date: date, tolerance_days: int) -> bool:
    if last_date is None:
        return False
    return (trade_date - last_date).days <= tolerance_days


# ── Market regime ─────────────────────────────────────────────────────────────

def _regime_on_date(conn: sqlite3.Connection, d: date) -> str:
    rows = conn.execute(
        "SELECT close FROM daily_prices "
        "WHERE stock_id='0050' AND date <= ? ORDER BY date DESC LIMIT 30",
        (str(d),),
    ).fetchall()
    if len(rows) < 20:
        return "unknown"
    closes = [float(r[0]) for r in reversed(rows)]
    ma20 = sum(closes[-20:]) / 20
    close_now = closes[-1]
    if len(closes) >= 30:
        ma20_prev = sum(closes[-30:-10]) / 20
        slope_pct = (ma20 - ma20_prev) / ma20_prev * 100 if ma20_prev > 0 else 0.0
    else:
        slope_pct = 0.0
    if close_now > ma20 and slope_pct > 0.3:
        return "bull"
    if close_now < ma20 and slope_pct < -0.3:
        return "bear"
    return "neutral"


# ── Signal generation ─────────────────────────────────────────────────────────

def _get_signal(conn: sqlite3.Connection, stock_id: str, trade_date: date) -> Optional[dict]:
    """Generate one simplified EntryTimingAnalyzer signal for stock_id on trade_date."""
    rows = conn.execute(
        "SELECT close FROM daily_prices "
        "WHERE stock_id=? AND date <= ? ORDER BY date DESC LIMIT 100",
        (stock_id, str(trade_date)),
    ).fetchall()
    if len(rows) < MIN_HIST_BARS:
        return None

    closes = [float(r[0]) for r in reversed(rows)]
    ma20 = round(sum(closes[-20:]) / 20, 4)
    close_now = closes[-1]
    ma20_gap_pct = round((close_now - ma20) / ma20 * 100, 4) if ma20 > 0 else 0.0

    if abs(ma20_gap_pct) > 5:
        return None

    stop_price = round(ma20 * (1.0 - STOP_BUFFER), 4)
    if stop_price <= 0:
        return None

    entry_label = "WAIT_FOR_PULLBACK" if 0 <= ma20_gap_pct <= 3 else "ENTRY_READY"
    ma20_slope_pct = compute_ma_slope(closes)
    ma20_trend = classify_ma_slope(ma20_slope_pct)
    market_regime = _regime_on_date(conn, trade_date)

    return {
        "stock_id": stock_id,
        "trade_date": trade_date,
        "entry_label": entry_label,
        "market_regime": market_regime,
        "ma20_trend": ma20_trend,
        "ma20_slope_pct": ma20_slope_pct,
        "ma20_gap_pct": ma20_gap_pct,
    }


# ── Stock universe ────────────────────────────────────────────────────────────

def _get_stocks_on_date(conn: sqlite3.Connection, trade_date: date) -> List[str]:
    rows = conn.execute(
        "SELECT DISTINCT stock_id FROM daily_prices "
        "WHERE stock_id != '0050' AND date = ? LIMIT 200",
        (str(trade_date),),
    ).fetchall()
    return [r[0] for r in rows]


# ── Outcome computation ───────────────────────────────────────────────────────

def _compute_net_return_close(
    conn: sqlite3.Connection,
    stock_id: str,
    entry_date: date,
    n_trading_days: int,
    cal: TradingCalendar,
) -> Tuple[Optional[float], Optional[date], int]:
    """
    Compute approximate net return using daily close prices.

    Returns (net_return_pct, exit_date, actual_trading_days).
    Uses close[D+n_trading_days] / close[D+1] − FEES_PCT.
    """
    exit_date = cal.add_trading_days(entry_date, n_trading_days)
    if exit_date is None:
        return None, None, 0

    rows = conn.execute(
        "SELECT date, close FROM daily_prices "
        "WHERE stock_id=? AND date BETWEEN ? AND ? ORDER BY date",
        (stock_id, str(entry_date), str(exit_date)),
    ).fetchall()

    if len(rows) < 2:
        return None, None, 0

    entry_close = float(rows[0][1])
    exit_close = float(rows[-1][1])
    if entry_close <= 0:
        return None, exit_date, 0

    actual_days = cal.count_trading_days(entry_date, date.fromisoformat(rows[-1][0]))
    gross = (exit_close - entry_close) / entry_close * 100.0
    return round(gross - FEES_PCT, 4), exit_date, actual_days


def _compute_outcomes_for_decision(
    conn: sqlite3.Connection,
    decision: dict,          # from get_pending_outcome_decisions
    cal: TradingCalendar,
    input_data_as_of: date,
) -> List[HybridForwardOutcome]:
    """
    Compute V1/V2/Hybrid outcomes for all three horizons for one decision.

    For this simplified implementation:
    - V1 return = close return (approximation; both V1 and Hybrid DIRECT use same entry)
    - V2 return = same close return (Hybrid V2 FOS: SA-7 for no-fill = 0%)
    - Hybrid return = V2 return if WAIT_PULLBACK else V1 return

    A production version would use EntryTimingExecutionSimulator for precise fills.
    """
    stock_id = decision["stock_id"]
    trade_date = date.fromisoformat(decision["trade_date"])
    decision_id = decision["id"]
    hybrid_action = decision["hybrid_action"]

    # Entry is next trading day after trade_date
    entry_date = cal.next_trading_day(trade_date)
    if entry_date is None:
        return []

    outcomes = []
    for horizon, n_days in HOLD_PERIODS.items():
        # Maturity check: trade_date must be old enough
        exit_date_expected = cal.add_trading_days(entry_date, n_days)
        if exit_date_expected is None or exit_date_expected > input_data_as_of:
            # Not yet matured — data not available
            continue

        v1_ret, exit_date, actual_days = _compute_net_return_close(
            conn, stock_id, entry_date, n_days, cal
        )
        if exit_date is None:
            continue

        # V2 FOS: simplified — use same close return as V1 (full sim would use EntryTimingExecutionSimulator)
        v2_ret = v1_ret

        # Hybrid: if WAIT_PULLBACK → use v2_ret; if DIRECT_NEXT_OPEN → use v1_ret
        hybrid_ret = v2_ret if hybrid_action == "WAIT_PULLBACK" else v1_ret

        hyb_v1_delta = round(hybrid_ret - v1_ret, 4) if hybrid_ret is not None and v1_ret is not None else None
        hyb_v2_delta = round(hybrid_ret - v2_ret, 4) if hybrid_ret is not None and v2_ret is not None else None

        outcomes.append(HybridForwardOutcome(
            decision_id=decision_id,
            stock_id=stock_id,
            trade_date=trade_date,
            rule_version=decision["rule_version"],
            horizon=horizon,
            maturity_date=exit_date,
            maturity_trading_days=actual_days,
            v1_net_return=v1_ret,
            v2_net_return=v2_ret,
            hybrid_net_return=hybrid_ret,
            hybrid_vs_v1_delta=hyb_v1_delta,
            hybrid_vs_v2_delta=hyb_v2_delta,
            data_source_version=str(input_data_as_of),
            calculation_version=CALCULATION_VERSION,
            outcome_status=OutcomeStatus.MATURED,
            calculated_at=datetime.now(timezone.utc),
        ))

    return outcomes


# ── Main daily runner ─────────────────────────────────────────────────────────

def run_shadow(
    trade_date: Optional[date] = None,
    force_stale: bool = False,
    backfill_outcomes_only: bool = False,
) -> Dict:
    """
    Main entry point for the daily Hybrid forward shadow run.

    Returns a summary dict with counts and status.
    """
    today = trade_date or date.today()
    run_id = new_run_id()
    started_at = datetime.now(timezone.utc)

    if not os.path.exists(DB_PATH):
        return {"error": "db_not_found", "db_path": DB_PATH}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    # Start run log immediately (so it exists even on early exit)
    log = HybridForwardRunLog(
        run_id=run_id,
        trade_date=today,
        started_at=started_at,
        finished_at=None,
        input_data_date=None,
        inserted_count=0,
        skipped_count=0,
        conflict_count=0,
        error_count=0,
        outcome_filled_count=0,
        status=RunStatus.FAILED,
        error_summary=None,
    )
    upsert_run_log(conn, log)

    cal = TradingCalendar.from_db(conn)
    last_data_date = _get_dailyprice_last_date(conn)
    log.input_data_date = last_data_date

    # ── Non-trading day check ─────────────────────────────────────────────────
    if not cal.is_trading_day(today) and not force_stale:
        log.status = RunStatus.SKIPPED_NON_TRADING_DAY
        log.finished_at = datetime.now(timezone.utc)
        upsert_run_log(conn, log)
        conn.close()
        print(f"[hybrid_shadow] {today} is not a trading day — skipped")
        return {"status": RunStatus.SKIPPED_NON_TRADING_DAY, "trade_date": str(today)}

    # ── Stale data guard ──────────────────────────────────────────────────────
    if not backfill_outcomes_only and not force_stale:
        if not _is_data_fresh(last_data_date, today, STALE_DATA_TOLERANCE_DAYS):
            msg = f"DailyPrice last_date={last_data_date}, trade_date={today}, tolerance={STALE_DATA_TOLERANCE_DAYS}D exceeded"
            log.status = RunStatus.BLOCKED_STALE_DATA
            log.error_summary = msg
            log.finished_at = datetime.now(timezone.utc)
            upsert_run_log(conn, log)
            conn.close()
            print(f"[hybrid_shadow] BLOCKED_STALE_DATA: {msg}")
            return {"status": RunStatus.BLOCKED_STALE_DATA, "trade_date": str(today), "detail": msg}

    if not backfill_outcomes_only:
        # ── OHLC Continuity Gate ──────────────────────────────────────────────
        if not force_stale:
            _gate = OHLCContinuityGate()
            _market_report = _gate.check_market(conn, today)
            if _market_report.gate_result == GateResult.BLOCKED_MISSING_OHLC:
                _n_missing = _market_report.missing_sessions
                _last_missing = str(_market_report.missing_dates[-1]) if _market_report.missing_dates else "?"
                msg = (
                    f"OHLC continuity gate blocked: {_n_missing} missing expected trading days "
                    f"in {_market_report.continuity_window}-day window. "
                    f"Most recent missing: {_last_missing}. "
                    f"PROSPECTIVE decisions cannot be generated with incomplete MA20/MA60 data."
                )
                log.status = RunStatus.BLOCKED_MISSING_OHLC
                log.error_summary = msg
                log.finished_at = datetime.now(timezone.utc)
                upsert_run_log(conn, log)
                conn.close()
                print(f"[hybrid_shadow] BLOCKED_MISSING_OHLC: {msg}")
                return {
                    "status": RunStatus.BLOCKED_MISSING_OHLC,
                    "trade_date": str(today),
                    "detail": msg,
                    "missing_sessions": [str(d) for d in _market_report.missing_dates],
                    "continuity_window": _market_report.continuity_window,
                }

        # ── Full-Market Freshness Gate ────────────────────────────────────────
        # Blocks PROSPECTIVE decisions when 0050 updated but full stock universe missing.
        # Allows force_stale to bypass (for historical backfill of RETROSPECTIVE records).
        if not force_stale:
            _freshness = check_market_freshness(conn, today, is_trading_day=True)
            if _freshness.is_blocked:
                msg = _freshness.detail
                if _freshness.status in (
                    FreshnessStatus.PARTIAL_MARKET_UPDATE,
                    FreshnessStatus.BENCHMARK_ONLY_UPDATED,
                ):
                    _run_status = RunStatus.BLOCKED_PARTIAL_MARKET
                else:
                    _run_status = RunStatus.BLOCKED_STALE_DATA
                log.status = _run_status
                log.error_summary = f"{_freshness.status.value}: {msg}"
                log.finished_at = datetime.now(timezone.utc)
                upsert_run_log(conn, log)
                conn.close()
                print(
                    f"[hybrid_shadow] {_run_status}: {_freshness.human_readable()} | {msg}"
                )
                return {
                    "status": _run_status,
                    "trade_date": str(today),
                    "freshness_status": _freshness.status.value,
                    "detail": msg,
                }

        # ── Decide: PROSPECTIVE or RETROSPECTIVE? ─────────────────────────────
        # Count trading days since trade_date
        trading_days_since: int
        if last_data_date and cal.is_trading_day(last_data_date):
            trading_days_since = max(0, cal.count_trading_days(today, last_data_date) - 1)
        else:
            trading_days_since = 999  # no data → late capture

        # ── Stock universe ────────────────────────────────────────────────────
        stocks = _get_stocks_on_date(conn, today)
        if not stocks and not force_stale:
            # Try last known data date
            if last_data_date:
                stocks = _get_stocks_on_date(conn, last_data_date)
                if stocks:
                    print(f"[hybrid_shadow] No stocks on {today}, using last_data_date={last_data_date}")
        if not stocks:
            msg = f"No stocks with DailyPrice data on {today}"
            log.status = RunStatus.BLOCKED_MISSING_SIGNALS
            log.error_summary = msg
            log.finished_at = datetime.now(timezone.utc)
            upsert_run_log(conn, log)
            conn.close()
            print(f"[hybrid_shadow] BLOCKED_MISSING_SIGNALS: {msg}")
            return {"status": RunStatus.BLOCKED_MISSING_SIGNALS, "trade_date": str(today), "detail": msg}

        svc = HybridDecisionService()
        effective_data_date = last_data_date or today
        inserted = 0
        skipped = 0
        conflicts = 0
        errors = 0

        for stock_id in stocks:
            sig = _get_signal(conn, stock_id, today)
            if sig is None:
                sig = _get_signal(conn, stock_id, effective_data_date) if effective_data_date != today else None
            if sig is None:
                skipped += 1
                continue

            try:
                decision_obj = svc.decide(
                    stock_id=sig["stock_id"],
                    signal_date=sig["trade_date"] if isinstance(sig["trade_date"], date) else date.fromisoformat(sig["trade_date"]),
                    v2_entry_label=sig["entry_label"],
                    market_regime=sig["market_regime"],
                    ma20_trend=sig["ma20_trend"],
                    ma20_slope_pct=sig["ma20_slope_pct"],
                    ma20_gap_pct=sig["ma20_gap_pct"],
                )

                input_hash = compute_input_data_hash(
                    stock_id=sig["stock_id"],
                    trade_date=today,
                    market_regime=sig["market_regime"],
                    ma20_slope_pct=sig["ma20_slope_pct"],
                    ma20_trend=sig["ma20_trend"],
                    ma20_gap_pct=sig["ma20_gap_pct"],
                    v2_entry_label=sig["entry_label"],
                    input_data_as_of=effective_data_date,
                )
                decision_hash = compute_decision_hash(
                    hybrid_action=decision_obj.hybrid_action.value,
                    rule_reason=decision_obj.rule_reason,
                    rule_priority=decision_obj.rule_priority,
                    rule_version=decision_obj.rule_version,
                )

                # Determine capture classification
                classification = classify_capture(
                    trade_date=today,
                    captured_at=started_at,
                    input_data_as_of=effective_data_date,
                    trading_days_since_trade=trading_days_since,
                )

                record = HybridForwardDecision(
                    stock_id=sig["stock_id"],
                    trade_date=today,
                    rule_version=RULE_VERSION,
                    research_version=RESEARCH_VERSION,
                    v2_entry_label=sig["entry_label"],
                    hybrid_action=decision_obj.hybrid_action.value,
                    rule_reason=decision_obj.rule_reason,
                    rule_priority=decision_obj.rule_priority,
                    market_regime=sig["market_regime"],
                    ma20_slope_pct=sig["ma20_slope_pct"],
                    ma20_trend=sig["ma20_trend"],
                    ma20_gap_pct=sig["ma20_gap_pct"],
                    feature_cutoff_date=today,
                    input_data_as_of=effective_data_date,
                    input_data_hash=input_hash,
                    decision_hash=decision_hash,
                    capture_classification=classification,
                    captured_at=started_at,
                    run_id=run_id,
                )

                result_id = insert_decision(conn, record)
                if result_id is None:
                    skipped += 1  # idempotent skip
                else:
                    inserted += 1

            except ConflictError as e:
                conflicts += 1
                print(f"[hybrid_shadow] CONFLICT {stock_id}/{today}: {e}")
            except Exception as e:
                errors += 1
                print(f"[hybrid_shadow] ERROR {stock_id}/{today}: {e}")

        conn.commit()
        log.inserted_count = inserted
        log.skipped_count = skipped
        log.conflict_count = conflicts
        log.error_count = errors

        if conflicts > 0:
            log.status = RunStatus.CONFLICT
            log.error_summary = f"{conflicts} decision conflict(s) detected"
        elif errors > 0:
            log.status = RunStatus.PARTIAL
            log.error_summary = f"{errors} error(s)"
        elif inserted == 0 and skipped == len(stocks):
            log.status = RunStatus.SUCCESS
        else:
            log.status = RunStatus.SUCCESS

    # ── Outcome backfill ──────────────────────────────────────────────────────
    outcome_filled = 0
    if last_data_date:
        for horizon, n_days in HOLD_PERIODS.items():
            # Maturity cutoff: trade_date + n_days trading days ago (with buffer)
            cutoff = cal.add_trading_days(today, -(n_days + OUTCOME_MATURITY_BUFFER_DAYS))
            if cutoff is None:
                continue
            pending = get_pending_outcome_decisions(conn, cutoff, horizon, CALCULATION_VERSION)
            for decision in pending:
                try:
                    outcomes = _compute_outcomes_for_decision(conn, decision, cal, last_data_date)
                    for o in outcomes:
                        if o.horizon == horizon:
                            result_id = insert_outcome(conn, o)
                            if result_id is not None:
                                outcome_filled += 1
                except ConflictError as e:
                    log.conflict_count += 1
                    print(f"[hybrid_shadow] OUTCOME CONFLICT {decision.get('stock_id')}: {e}")
                except Exception as e:
                    log.error_count += 1
                    print(f"[hybrid_shadow] OUTCOME ERROR {decision.get('stock_id')}: {e}")

        conn.commit()

    log.outcome_filled_count = outcome_filled
    log.finished_at = datetime.now(timezone.utc)
    if not backfill_outcomes_only and log.status == RunStatus.FAILED:
        log.status = RunStatus.SUCCESS
    elif backfill_outcomes_only:
        log.status = RunStatus.SUCCESS

    upsert_run_log(conn, log)
    summary = get_operational_summary(conn)
    conn.close()

    result = {
        "run_id": run_id,
        "trade_date": str(today),
        "status": log.status,
        "inserted": log.inserted_count,
        "skipped": log.skipped_count,
        "conflicts": log.conflict_count,
        "errors": log.error_count,
        "outcomes_filled": outcome_filled,
        "data_as_of": str(last_data_date) if last_data_date else None,
        "operational_summary": summary,
    }
    print(
        f"[hybrid_shadow] {today} run_id={run_id} status={log.status} "
        f"inserted={log.inserted_count} outcomes_filled={outcome_filled}"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid V1 Forward Shadow Runner")
    parser.add_argument("--date", help="Trade date (YYYY-MM-DD), default today")
    parser.add_argument("--force-stale", action="store_true",
                        help="Run even if DailyPrice is stale (testing only)")
    parser.add_argument("--backfill-outcomes-only", action="store_true",
                        help="Only compute matured outcomes; skip new decisions")
    args = parser.parse_args()

    trade_date = date.fromisoformat(args.date) if args.date else None
    result = run_shadow(
        trade_date=trade_date,
        force_stale=args.force_stale,
        backfill_outcomes_only=args.backfill_outcomes_only,
    )
    import json
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
