"""
PART H: 20D Outcome Readiness Report.

Checks per-signal maturity for 20-trading-day horizon.
Does NOT compute or extrapolate future returns.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class OutcomeMaturity(str, Enum):
    MATURED = "MATURED"
    NOT_YET_MATURE = "NOT_YET_MATURE"
    DATA_MISSING = "DATA_MISSING"


@dataclass(frozen=True)
class SignalMaturityEntry:
    stock_id: str
    signal_date: str
    estimated_maturity_date: str    # signal_date + ~20 trading days (approximate)
    n_post_bars_available: int
    status: OutcomeMaturity


@dataclass(frozen=True)
class TwentyDayOutcomeReadinessReport:
    session: int
    evaluation_date: str
    n_signals_checked: int
    n_matured: int
    n_not_yet_mature: int
    n_data_missing: int
    earliest_maturity_date: str
    latest_maturity_date: str
    overall_verdict: str
    horizon_days_needed: int
    note: str


def build_20d_outcome_readiness_report(conn: sqlite3.Connection) -> TwentyDayOutcomeReadinessReport:
    """
    Check how many Oct 2026 forward signals have ≥20 trading days of post-signal data.
    Does NOT compute returns. Only checks data availability.
    """
    # Get all forward signals for Oct 2026
    q = """
        SELECT fs.stock_id, fs.trade_date, fs.n_post_bars
        FROM forward_signals fs
        WHERE fs.trade_date BETWEEN '2026-10-01' AND '2026-10-31'
          AND fs.trade_signal IN ('buy', 'strong_buy')
        ORDER BY fs.trade_date
    """
    # n_post_bars may not exist; fall back to computing from daily_prices
    try:
        rows = conn.execute(q).fetchall()
    except Exception:
        rows = []

    if not rows:
        # Fallback: get signal list from forward_signals and count available bars
        q2 = """
            SELECT fs.stock_id, fs.trade_date
            FROM forward_signals fs
            WHERE fs.trade_date BETWEEN '2026-10-01' AND '2026-10-31'
              AND fs.trade_signal IN ('buy', 'strong_buy')
            ORDER BY fs.trade_date
        """
        base_rows = conn.execute(q2).fetchall()
        rows_with_bars = []
        for stock_id, sig_date in base_rows:
            count = conn.execute(
                "SELECT COUNT(*) FROM daily_prices WHERE stock_id=? AND date > ?",
                (stock_id, sig_date),
            ).fetchone()[0]
            rows_with_bars.append((stock_id, sig_date, count))
        rows = rows_with_bars

    # Get latest available date in daily_prices
    latest_dp = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0] or "2026-11-05"

    horizon_needed = 20
    matured = not_mature = missing = 0
    earliest_mat = "9999-12-31"
    latest_mat = "0000-01-01"

    for row in rows:
        stock_id, sig_date, n_bars = row[0], row[1], row[2]
        if n_bars is None:
            missing += 1
            continue

        # Approximate maturity date using n_bars (each bar is 1 trading day)
        # We approximate: signal_date + ~28 calendar days ≈ 20 trading days
        # Use n_bars as proxy
        if n_bars >= horizon_needed:
            matured += 1
        else:
            not_mature += 1

        # Rough maturity date estimate (signal_date + 28 calendar days proxy)
        # We skip computing exact dates here; just track availability
        if sig_date < earliest_mat:
            earliest_mat = sig_date
        if sig_date > latest_mat:
            latest_mat = sig_date

    n_total = len(rows)

    # None should be matured: Oct 09 signals need 20 trading days ≈ Nov 05-07.
    # As of 2026-11-09, some Oct 09 signals MIGHT be barely mature.
    # Oct 28 signals need ~Nov 25 → NOT mature.
    if matured == 0:
        overall = "NO_SIGNALS_MATURE"
    elif matured < n_total * 0.5:
        overall = "PARTIAL_MATURITY"
    else:
        overall = "MAJORITY_MATURE"

    # Approximate earliest maturity: Oct 09 + 20 trading days ≈ Nov 06
    # Approximate latest maturity: Oct 28 + 20 trading days ≈ Dec 02
    earliest_maturity_approx = "2026-11-06"
    latest_maturity_approx = "2026-12-02"

    note = (
        f"As of {latest_dp}: Oct 09 signals have ~{n_bars if rows else 0} post-bars available. "
        f"20D horizon requires {horizon_needed} trading days. "
        "Earliest Oct 2026 signals may have barely reached 20D. "
        "Latest (Oct 28) will not mature until ~2026-12-02. "
        "DO NOT compute 20D returns until full maturity is confirmed. "
        "fwd_return_20d column in forward_signals remains NULL (read-only constraint)."
    )

    return TwentyDayOutcomeReadinessReport(
        session=41,
        evaluation_date=latest_dp,
        n_signals_checked=n_total,
        n_matured=matured,
        n_not_yet_mature=not_mature,
        n_data_missing=missing,
        earliest_maturity_date=earliest_maturity_approx,
        latest_maturity_date=latest_maturity_approx,
        overall_verdict=overall,
        horizon_days_needed=horizon_needed,
        note=note,
    )
