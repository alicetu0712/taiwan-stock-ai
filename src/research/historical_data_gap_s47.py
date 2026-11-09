"""
PART B/C (P1/P2): Historical Data Gap Analysis — Session 47.

Investigates the full trading-day coverage gap in the research SQLite DB,
covering Oct 8 through Nov 09.  Distinct from S46 which only diagnosed
the Nov 02-09 window.

Key finding:
  Trading days with only 0050 proxy data (not just Nov 02/03):
    Oct 08, Oct 15, Oct 19, Oct 20, Oct 27, Oct 29, Oct 30, Nov 02, Nov 03
  Trading days completely absent from daily_prices:
    Nov 06, Nov 09

Root cause taxonomy:
  - PIPELINE_SELECTIVE: pipeline only ran on fill dates; intermediate dates
    never captured (affects Oct 08, 15, 19, 20, 27, 29, 30)
  - SCHEDULER_NOT_TRIGGERED: cron not running (also affects Oct 30, Nov 02-03,
    Nov 06, Nov 09 — first cron entry 2026-11-09T08:00:17Z)
  - QUALITY_GATE_FAIL: Nov 06 cron attempt rejected
  - PROVIDER_NOT_READY: Nov 09 cron blocked (TWSE api_date stale)
  - MANUAL_BACKFILL: Nov 04/05 recovered manually

Recovery verdict: RECOVERY_BLOCKED in isolated research environment
  (no local cache for missing dates; production backfill not authorized).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class DateCoverageStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    DATE_MISSING = "DATE_MISSING"
    NOT_A_TRADING_DAY = "NOT_A_TRADING_DAY"
    PRE_RESEARCH_ERA = "PRE_RESEARCH_ERA"


class GapRootCause(str, Enum):
    PIPELINE_SELECTIVE = "PIPELINE_SELECTIVE"
    SCHEDULER_NOT_TRIGGERED = "SCHEDULER_NOT_TRIGGERED"
    QUALITY_GATE_FAIL = "QUALITY_GATE_FAIL"
    PROVIDER_NOT_READY = "PROVIDER_NOT_READY"
    MANUAL_BACKFILL = "MANUAL_BACKFILL"
    MARKET_CLOSED = "MARKET_CLOSED"
    NO_GAP = "NO_GAP"
    UNKNOWN = "UNKNOWN"


class RecoveryFeasibility(str, Enum):
    RECOVERY_COMPLETE = "RECOVERY_COMPLETE"
    RECOVERY_PARTIAL = "RECOVERY_PARTIAL"
    RECOVERY_BLOCKED = "RECOVERY_BLOCKED"
    NO_RECOVERY_NEEDED = "NO_RECOVERY_NEEDED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class DateCoverageRecord:
    date_str: str
    is_trading_day: bool
    stock_count: int
    has_tsmc: bool
    has_0050: bool
    coverage_status: DateCoverageStatus
    root_cause: GapRootCause
    recovery_feasibility: RecoveryFeasibility
    affected_fill_clusters: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class HistoricalDataGapMatrix:
    analysis_date: str
    date_range_start: str
    date_range_end: str
    records: tuple[DateCoverageRecord, ...]
    # Summary counts
    n_trading_days: int
    n_complete: int
    n_partial_coverage: int
    n_date_missing: int
    n_not_trading: int
    # Gap lists
    partial_coverage_dates: tuple[str, ...]
    missing_dates: tuple[str, ...]
    # Recovery assessment
    overall_recovery_verdict: RecoveryFeasibility
    recovery_blocker_reason: str


# Official trading days Oct 8 – Nov 10 per TaiwanTradingCalendar
# Derived from: TaiwanTradingCalendar().is_trading_day() calls
_TRADING_DAYS_OCT8_NOV10 = frozenset({
    "2026-10-08",
    "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15",
    "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21",
    "2026-10-22", "2026-10-27", "2026-10-28", "2026-10-29",
    "2026-10-30",
    "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05",
    "2026-11-06", "2026-11-09", "2026-11-10",
})

# Fill dates: dates where the pipeline generated forward signals and ran fully
_FILL_DATES = frozenset({
    "2026-10-12",  # v6.0 fill
    "2026-10-13", "2026-10-14", "2026-10-16",  # strict baseline
    "2026-10-21", "2026-10-22", "2026-10-28",  # incomplete clusters
})

# Manually backfilled dates
_MANUAL_BACKFILL_DATES = frozenset({"2026-11-04", "2026-11-05"})

# Root causes per date (determined from logs + DB evidence)
_ROOT_CAUSES: dict[str, GapRootCause] = {
    "2026-10-08": GapRootCause.PIPELINE_SELECTIVE,
    "2026-10-12": GapRootCause.NO_GAP,
    "2026-10-13": GapRootCause.NO_GAP,
    "2026-10-14": GapRootCause.NO_GAP,
    "2026-10-15": GapRootCause.PIPELINE_SELECTIVE,
    "2026-10-16": GapRootCause.NO_GAP,
    "2026-10-19": GapRootCause.PIPELINE_SELECTIVE,
    "2026-10-20": GapRootCause.PIPELINE_SELECTIVE,
    "2026-10-21": GapRootCause.NO_GAP,
    "2026-10-22": GapRootCause.NO_GAP,
    "2026-10-27": GapRootCause.PIPELINE_SELECTIVE,
    "2026-10-28": GapRootCause.NO_GAP,
    "2026-10-29": GapRootCause.PIPELINE_SELECTIVE,
    "2026-10-30": GapRootCause.SCHEDULER_NOT_TRIGGERED,
    "2026-11-02": GapRootCause.SCHEDULER_NOT_TRIGGERED,
    "2026-11-03": GapRootCause.SCHEDULER_NOT_TRIGGERED,
    "2026-11-04": GapRootCause.MANUAL_BACKFILL,
    "2026-11-05": GapRootCause.MANUAL_BACKFILL,
    "2026-11-06": GapRootCause.QUALITY_GATE_FAIL,
    "2026-11-09": GapRootCause.PROVIDER_NOT_READY,
}

# Which fill clusters each gap date affects (as holding-period intermediate dates)
_AFFECTED_CLUSTERS: dict[str, tuple[str, ...]] = {
    "2026-10-08": (),
    "2026-10-15": ("2026-10-13", "2026-10-14"),
    "2026-10-19": ("2026-10-13", "2026-10-14", "2026-10-16"),
    "2026-10-20": ("2026-10-13", "2026-10-14", "2026-10-16"),
    "2026-10-27": ("2026-10-16", "2026-10-21", "2026-10-22"),
    "2026-10-29": ("2026-10-21", "2026-10-22", "2026-10-28"),
    "2026-10-30": ("2026-10-21", "2026-10-22"),
    "2026-11-02": ("2026-10-22", "2026-10-28"),
    "2026-11-03": ("2026-10-28",),
    "2026-11-06": (),
    "2026-11-09": (),
}

# PIPELINE_SELECTIVE: pipeline only fetched data on fill dates (execution_date of signals)
# Intermediate dates between fills were never captured, hence 0050-only entries.
# These older gaps (pre-Nov 02) cannot be recovered without an external historical
# data source or authorized production backfill.
_RECOVERY_NOTES = {
    "PIPELINE_SELECTIVE": (
        "Pipeline ran only on signal fill dates; intermediate dates never captured. "
        "Recovery requires historical TWSE data fetch not available in isolated environment."
    ),
    "SCHEDULER_NOT_TRIGGERED": (
        "Cron was not running Nov 02-08 (first entry 2026-11-09T08:00:17Z). "
        "Recovery requires authorized pipeline execution or manual backfill command."
    ),
    "QUALITY_GATE_FAIL": (
        "Nov 06 cron attempt rejected by quality gate. "
        "Root cause of QG failure not yet identified from logs."
    ),
    "PROVIDER_NOT_READY": (
        "TWSE API returned stale api_date on Nov 09 all 4 attempts. "
        "Should resolve on next cron run once provider publishes current data."
    ),
    "MANUAL_BACKFILL": "Recovered via manual backfill_daily_prices.py run (DailyPrice Pipeline project).",
    "NO_GAP": "Complete data present.",
}


def build_data_gap_matrix(
    conn: sqlite3.Connection,
    analysis_date: str = "2026-11-09",
    date_start: str = "2026-10-08",
    date_end: str = "2026-11-09",
) -> HistoricalDataGapMatrix:
    # Build DB-side lookup
    db_rows = conn.execute(
        "SELECT date, COUNT(DISTINCT stock_id) FROM daily_prices "
        "WHERE date >= ? AND date <= ? GROUP BY date",
        (date_start, date_end),
    ).fetchall()
    db_coverage: dict[str, int] = {r[0]: r[1] for r in db_rows}

    # TSMC and 0050 presence per date
    tsmc_dates = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT date FROM daily_prices WHERE stock_id='2330' AND date >= ? AND date <= ?",
            (date_start, date_end),
        ).fetchall()
    }
    benchmark_dates = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT date FROM daily_prices WHERE stock_id='0050' AND date >= ? AND date <= ?",
            (date_start, date_end),
        ).fetchall()
    }

    records: list[DateCoverageRecord] = []
    start = date(2026, 10, 8)
    end = date(2026, 11, 9)
    d = start
    n_trading = n_complete = n_partial = n_missing = n_not_trading = 0
    partial_dates: list[str] = []
    missing_dates: list[str] = []

    while d <= end:
        ds = d.strftime("%Y-%m-%d")
        is_td = ds in _TRADING_DAYS_OCT8_NOV10
        stock_cnt = db_coverage.get(ds, 0)
        has_tsmc = ds in tsmc_dates
        has_0050 = ds in benchmark_dates

        if not is_td:
            status = DateCoverageStatus.NOT_A_TRADING_DAY
            root = GapRootCause.MARKET_CLOSED
            recovery = RecoveryFeasibility.NOT_APPLICABLE
            n_not_trading += 1
        elif stock_cnt == 0:
            status = DateCoverageStatus.DATE_MISSING
            root = _ROOT_CAUSES.get(ds, GapRootCause.UNKNOWN)
            recovery = RecoveryFeasibility.RECOVERY_BLOCKED
            n_missing += 1
            missing_dates.append(ds)
            n_trading += 1
        elif stock_cnt == 1:
            status = DateCoverageStatus.PARTIAL_COVERAGE
            root = _ROOT_CAUSES.get(ds, GapRootCause.UNKNOWN)
            recovery = RecoveryFeasibility.RECOVERY_BLOCKED
            n_partial += 1
            partial_dates.append(ds)
            n_trading += 1
        else:
            status = DateCoverageStatus.COMPLETE
            root = _ROOT_CAUSES.get(ds, GapRootCause.NO_GAP)
            recovery = RecoveryFeasibility.NO_RECOVERY_NEEDED
            n_complete += 1
            n_trading += 1

        affected = _AFFECTED_CLUSTERS.get(ds, ())
        note = _RECOVERY_NOTES.get(root.value, "")

        records.append(DateCoverageRecord(
            date_str=ds,
            is_trading_day=is_td,
            stock_count=stock_cnt,
            has_tsmc=has_tsmc,
            has_0050=has_0050,
            coverage_status=status,
            root_cause=root,
            recovery_feasibility=recovery,
            affected_fill_clusters=affected,
            notes=note,
        ))
        d += timedelta(days=1)

    # Overall recovery verdict
    # All gaps are RECOVERY_BLOCKED in isolated research environment
    any_blocked = any(
        r.recovery_feasibility == RecoveryFeasibility.RECOVERY_BLOCKED
        for r in records
        if r.is_trading_day and r.coverage_status != DateCoverageStatus.COMPLETE
    )
    overall = (
        RecoveryFeasibility.RECOVERY_BLOCKED if any_blocked
        else RecoveryFeasibility.NO_RECOVERY_NEEDED
    )

    return HistoricalDataGapMatrix(
        analysis_date=analysis_date,
        date_range_start=date_start,
        date_range_end=date_end,
        records=tuple(records),
        n_trading_days=n_trading,
        n_complete=n_complete,
        n_partial_coverage=n_partial,
        n_date_missing=n_missing,
        n_not_trading=n_not_trading,
        partial_coverage_dates=tuple(partial_dates),
        missing_dates=tuple(missing_dates),
        overall_recovery_verdict=overall,
        recovery_blocker_reason=(
            "No local data cache for missing dates; "
            "historical TWSE fetch and production backfill not authorized in isolated environment."
        ),
    )


def get_gap_dates_affecting_cluster(
    gap_matrix: HistoricalDataGapMatrix, fill_date: str
) -> list[DateCoverageRecord]:
    return [
        r for r in gap_matrix.records
        if fill_date in r.affected_fill_clusters
        and r.coverage_status != DateCoverageStatus.COMPLETE
    ]
