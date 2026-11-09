"""
PART H: 20D Research Readiness Auditor — Session 43.

Assesses per-signal maturity for a 20-trading-day return window.

20D window requires:
  - fill_date + 20 stock-specific trading days available in daily_prices
  - daily_prices max date = 2026-11-05
  - For fill Oct 13: 20 TDs after Oct 13 → needs ~Nov 25-26 (not available)
  - For fill Oct 14: same problem
  - For fill Oct 16: needs ~Nov 25
  - For fill Oct 21: needs ~Nov 25

Conclusion: NO signals have complete 20D windows as of Nov 2026.
ETA: earliest complete 20D window = fill Oct 13 → ~Nov 26 (trading days)
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class MaturityStatus(str, Enum):
    MATURE = "MATURE"
    PARTIAL = "PARTIAL"
    IMMATURE = "IMMATURE"
    NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class SignalMaturityRecord:
    fill_date: str
    n_signals: int
    n_exit_days_available: int
    required_exit_days: int
    pct_complete: float
    maturity_status: MaturityStatus
    # Stock-specific detail for representative stock (2330 TSMC)
    tsmc_exit_days: int
    tsmc_exit_date_if_complete: str | None
    # ETA for completion
    eta_date: str | None
    notes: str


@dataclass(frozen=True)
class TwentyDayReadinessReport:
    session: int
    evaluation_date: str
    daily_prices_max_date: str
    # Per fill-date maturity
    maturity_records: tuple[SignalMaturityRecord, ...]
    n_mature_fill_dates: int
    n_partial_fill_dates: int
    n_immature_fill_dates: int
    # Overall readiness
    pct_eligible_for_20d: float
    earliest_complete_20d_eta: str | None
    # Blocking issues
    blocking_issues: tuple[str, ...]
    overall_verdict: str


def build_20d_readiness_report(conn: sqlite3.Connection) -> TwentyDayReadinessReport:
    today = "2026-11-09"

    # Get daily_prices max date
    max_date_row = conn.execute(
        "SELECT MAX(date) FROM daily_prices WHERE stock_id='2330'"
    ).fetchone()
    max_date = max_date_row[0] if max_date_row else "UNKNOWN"

    # v8.0 fill dates to check
    fill_dates = ["2026-10-13", "2026-10-14", "2026-10-16", "2026-10-21"]

    maturity_records = []

    for fd in fill_dates:
        # Count how many trading days available after fill_date for TSMC
        tsmc_rows = conn.execute(
            "SELECT date FROM daily_prices WHERE stock_id='2330' AND date > ? ORDER BY date",
            (fd,)
        ).fetchall()
        tsmc_exit_days = len(tsmc_rows)

        # 20D exit would be the 20th row
        tsmc_20d_exit = tsmc_rows[19][0] if len(tsmc_rows) >= 20 else None

        required = 20
        pct = min(1.0, tsmc_exit_days / required)

        if tsmc_exit_days >= required:
            status = MaturityStatus.MATURE
        elif tsmc_exit_days >= 10:
            status = MaturityStatus.PARTIAL
        elif tsmc_exit_days > 0:
            status = MaturityStatus.IMMATURE
        else:
            status = MaturityStatus.NO_DATA

        # Count signals in this fill-date cluster
        # fill Oct 13 = signal Oct 12; fill Oct 14 = signal Oct 13; etc.
        fill_map = {
            "2026-10-13": "2026-10-12",
            "2026-10-14": "2026-10-13",
            "2026-10-16": "2026-10-14",
            "2026-10-21": "2026-10-16",
        }
        sig_date = fill_map.get(fd, fd)
        n_sigs = conn.execute(
            "SELECT COUNT(*) FROM forward_signals WHERE trade_date=? AND trade_signal IN ('buy','strong_buy') AND model_version='v8.0'",
            (sig_date,)
        ).fetchone()[0]

        # ETA: estimate when 20D will be available
        # Trading days in Taiwan roughly 20/month → ~1 month per 20 TDs after fill_date
        # fill Oct 13 → ~20 TDs → ~Nov 25 (Oct has ~8 TDs left after 13, Nov has ~12 by mid-Nov)
        eta_map = {
            "2026-10-13": "~2026-11-25",
            "2026-10-14": "~2026-11-26",
            "2026-10-16": "~2026-11-28",
            "2026-10-21": "~2026-12-04",
        }
        eta = eta_map.get(fd) if status != MaturityStatus.MATURE else None

        # Count available exit days per fill date for all stocks
        # Approximate: use TSMC count as representative
        maturity_records.append(SignalMaturityRecord(
            fill_date=fd,
            n_signals=n_sigs,
            n_exit_days_available=tsmc_exit_days,
            required_exit_days=required,
            pct_complete=pct,
            maturity_status=status,
            tsmc_exit_days=tsmc_exit_days,
            tsmc_exit_date_if_complete=tsmc_20d_exit,
            eta_date=eta,
            notes=(
                f"TSMC: {tsmc_exit_days}/20 exit days available. "
                f"Max daily_prices date: {max_date}."
            ),
        ))

    n_mature = sum(1 for r in maturity_records if r.maturity_status == MaturityStatus.MATURE)
    n_partial = sum(1 for r in maturity_records if r.maturity_status == MaturityStatus.PARTIAL)
    n_immature = sum(1 for r in maturity_records if r.maturity_status == MaturityStatus.IMMATURE)

    total = len(maturity_records)
    pct_eligible = n_mature / total if total > 0 else 0.0

    earliest_eta = None
    for r in sorted(maturity_records, key=lambda x: x.fill_date):
        if r.eta_date and r.maturity_status != MaturityStatus.MATURE:
            earliest_eta = r.eta_date
            break

    blocking_issues = []
    if n_mature == 0:
        blocking_issues.append(
            f"daily_prices max date ({max_date}) is insufficient for any 20D window; "
            f"earliest fill date is {fill_dates[0]}, needs 20 TDs (est. {earliest_eta})"
        )
    if n_partial > 0:
        partial_records = [r for r in maturity_records if r.maturity_status == MaturityStatus.PARTIAL]
        for pr in partial_records:
            blocking_issues.append(
                f"fill {pr.fill_date}: {pr.tsmc_exit_days}/20 trading days available"
            )

    if n_mature == total:
        verdict = "READY_FOR_20D"
    elif n_mature > 0:
        verdict = "PARTIALLY_READY_FOR_20D"
    else:
        verdict = "NOT_READY_FOR_20D"

    return TwentyDayReadinessReport(
        session=43,
        evaluation_date=today,
        daily_prices_max_date=max_date or "UNKNOWN",
        maturity_records=tuple(maturity_records),
        n_mature_fill_dates=n_mature,
        n_partial_fill_dates=n_partial,
        n_immature_fill_dates=n_immature,
        pct_eligible_for_20d=pct_eligible,
        earliest_complete_20d_eta=earliest_eta,
        blocking_issues=tuple(blocking_issues),
        overall_verdict=verdict,
    )
