"""
Pipeline Reliability Root Cause, Coverage Quality Gate, and
Backfill Dry-run Planner — Session 48 PARTS B, C, D (P1–P3).

Three-tier stock-count pattern in daily_prices (Oct 08 – Nov 09):
  TIER_1_PROXY   (~1 stock, 0050 only): non-fill days after pipeline selective
                  activation. Pipeline fetched only the benchmark token to
                  confirm market status; full data pull was skipped.
  TIER_655_FILL  (~655–656 stocks): fill dates (execution_date in
                  forward_signals). Full v8.0-filtered universe fetched because
                  ForwardSignalService needed execution prices.
  TIER_6957_BACKFILL (~6957 stocks): Nov 04/05 manual backfill — full TWSE
                  + TPEx universe recovered via backfill_daily_prices.py.

Root cause taxonomy (by date):
  PIPELINE_SELECTIVE         — pipeline only ran on fill dates; intermediate
                               trading days never captured (Oct 08/15/19/20/27/29)
  SCHEDULER_NOT_TRIGGERED    — cron was not running; first log entry
                               2026-11-09T08:00:17Z (Oct 30, Nov 02/03)
  QUALITY_GATE_FAIL          — cron ran but daily QG rejected data (Nov 06)
  PROVIDER_NOT_READY         — cron ran but TWSE api_date was stale (Nov 09)
  MANUAL_BACKFILL            — Nov 04/05 recovered manually (no gap)
  MARKET_CLOSED              — holiday/weekend; not a trading day
  NO_GAP                     — full coverage, no issue

Coverage dimensions (15 total):
  1  is_trading_day          6  tsmc_present (2330)    11 source_type
  2  stock_count             7  fill_date_flag          12 pipeline_stage_reached
  3  has_data                8  proxy_date_flag         13 recovery_feasibility
  4  coverage_tier           9  pipeline_root_cause     14 affects_active_cluster
  5  benchmark_present (0050) 10 coverage_status        15 data_verification_status

Backfill Dry-run candidates (11 dates):
  Oct 08/15/19/20/27/29/30, Nov 02/03/06/09.

SAFETY: This module is READ-ONLY research. No production writes.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PipelineTier(str, Enum):
    TIER_1_PROXY = "TIER_1_PROXY"           # 0050 only
    TIER_655_FILL = "TIER_655_FILL"         # fill date, ~655 stocks
    TIER_6957_BACKFILL = "TIER_6957_BACKFILL"  # manual backfill, ~6957
    TIER_PARTIAL_LEGACY = "TIER_PARTIAL_LEGACY"  # pre-Oct-08 partial (~499)
    TIER_ZERO_MISSING = "TIER_ZERO_MISSING"  # 0 rows — completely missing


class PipelineRootCause(str, Enum):
    PIPELINE_SELECTIVE = "PIPELINE_SELECTIVE"
    SCHEDULER_NOT_TRIGGERED = "SCHEDULER_NOT_TRIGGERED"
    QUALITY_GATE_FAIL = "QUALITY_GATE_FAIL"
    PROVIDER_NOT_READY = "PROVIDER_NOT_READY"
    MANUAL_BACKFILL = "MANUAL_BACKFILL"
    MARKET_CLOSED = "MARKET_CLOSED"
    NO_GAP = "NO_GAP"
    UNKNOWN = "UNKNOWN"


class RootCauseConfidence(str, Enum):
    ROOT_CAUSE_CONFIRMED = "ROOT_CAUSE_CONFIRMED"
    ROOT_CAUSE_PARTIAL = "ROOT_CAUSE_PARTIAL"
    ROOT_CAUSE_UNDETERMINED = "ROOT_CAUSE_UNDETERMINED"


class CoverageStatus(str, Enum):
    DATA_COMPLETE = "DATA_COMPLETE"
    DATA_PARTIAL = "DATA_PARTIAL"
    BENCHMARK_ONLY = "BENCHMARK_ONLY"
    DATA_MISSING = "DATA_MISSING"
    NOT_TRADING_DAY = "NOT_TRADING_DAY"
    DATA_UNVERIFIED = "DATA_UNVERIFIED"


class BackfillReadiness(str, Enum):
    INSERT_ONLY_CANDIDATE = "INSERT_ONLY_CANDIDATE"      # has 0050 only; backfill adds ~655 more
    CONFLICT_REQUIRES_REVIEW = "CONFLICT_REQUIRES_REVIEW"  # duplicate risk
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"            # TWSE historical API not confirmed available
    UNIVERSE_UNVERIFIED = "UNIVERSE_UNVERIFIED"          # 0 rows; stock universe unknown
    NOT_REQUIRED = "NOT_REQUIRED"                        # already complete


# ---------------------------------------------------------------------------
# Pipeline Stage constants
# ---------------------------------------------------------------------------

PIPELINE_STAGES = [
    "S01_CALENDAR_CHECK",       # TradingCalendarService: is today a trading day?
    "S02_SCHEDULER_VERIFY",     # Cron / scheduler active?
    "S03_DATA_PROVIDER_FETCH",  # TWSE / TPEx API call
    "S04_QUALITY_GATE",         # QG-1..QG-7 validation
    "S05_TRANSFORM",            # Convert raw → internal format
    "S06_DEDUP_CHECK",          # Check for existing rows (conflict detection)
    "S07_SQLITE_WRITE",         # INSERT to daily_prices
    "S08_SIGNAL_TRIGGER",       # Does today have forward signals to execute?
    "S09_SIGNAL_EXECUTION",     # Record execution_date / execution_price
    "S10_RESEARCH_CACHE",       # Update research cache / analysis_results
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PipelineStageResult:
    stage: str
    reached: bool
    result: str         # "PASS" | "FAIL" | "SKIPPED" | "NOT_APPLICABLE"
    detail: str


@dataclass(frozen=True)
class DailyCoverageRecord:
    """One row in the DailyCoverageMatrix (one trading date)."""
    # Dimension 1
    date_str: str
    # Dimension 2
    is_trading_day: bool
    # Dimension 3
    stock_count: int
    # Dimension 4
    has_data: bool
    # Dimension 5
    coverage_tier: PipelineTier
    # Dimension 6
    benchmark_present: bool   # 0050
    # Dimension 7
    tsmc_present: bool        # 2330
    # Dimension 8
    fill_date_flag: bool
    # Dimension 9
    proxy_date_flag: bool     # 1-stock only day
    # Dimension 10
    pipeline_root_cause: PipelineRootCause
    # Dimension 11
    coverage_status: CoverageStatus
    # Dimension 12
    source_type: str          # "FILL_DATE_PIPELINE" | "MANUAL_BACKFILL" | "PROXY_ONLY" | "NONE"
    # Dimension 13
    pipeline_stage_reached: str   # last PIPELINE_STAGE reached
    # Dimension 14
    recovery_feasibility: str     # "BLOCKED" | "PARTIAL" | "COMPLETE" | "NOT_NEEDED"
    # Dimension 15
    affects_active_cluster: bool  # is a date inside any cluster's 5D window
    # Extra
    root_cause_confidence: RootCauseConfidence
    notes: str


@dataclass(frozen=True)
class DailyCoverageMatrix:
    analysis_date: str
    records: Tuple[DailyCoverageRecord, ...]
    total_trading_days: int
    complete_days: int
    benchmark_only_days: int
    missing_days: int
    root_cause_confirmed: int
    root_cause_partial: int
    root_cause_undetermined: int
    # Pipeline tier counts
    tier_1_proxy_days: int
    tier_655_fill_days: int
    tier_6957_backfill_days: int


@dataclass(frozen=True)
class BackfillDryRunRecord:
    date_str: str
    existing_rows: int
    unique_existing_stocks: int
    has_0050_conflict: bool
    estimated_missing_stocks: int
    candidate_insert_count: int
    is_fill_date: bool
    source_availability: str    # "HISTORICAL_API_AVAILABLE" | "API_UNVERIFIED" | "NOT_APPLICABLE"
    readiness: BackfillReadiness
    conflict_risk: str          # "LOW" | "MEDIUM" | "HIGH"
    notes: str


@dataclass(frozen=True)
class BackfillDryRunPlan:
    analysis_date: str
    candidate_dates: Tuple[str, ...]
    records: Tuple[BackfillDryRunRecord, ...]
    insert_only_count: int
    conflict_count: int
    source_unavailable_count: int
    universe_unverified_count: int


# ---------------------------------------------------------------------------
# Hard-coded pipeline knowledge (read-only research facts)
# ---------------------------------------------------------------------------

# Trading days in Oct 08 – Nov 09 window
_TRADING_DAYS_OCT8_NOV9: frozenset[str] = frozenset([
    "2026-10-08", "2026-10-12", "2026-10-13", "2026-10-14",
    "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20",
    "2026-10-21", "2026-10-22", "2026-10-27", "2026-10-28",
    "2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03",
    "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09",
])

# Non-trading days (holidays and weekends) in this window
_NON_TRADING_DAYS: frozenset[str] = frozenset([
    "2026-10-09", "2026-10-10", "2026-10-11",   # holiday + weekend
    "2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26",  # holiday cluster
    "2026-10-31", "2026-11-01",   # weekend
    "2026-11-07", "2026-11-08",   # weekend
])

# Root cause mapping for each date
_ROOT_CAUSE_MAP: dict[str, PipelineRootCause] = {
    "2026-10-08": PipelineRootCause.PIPELINE_SELECTIVE,
    "2026-10-12": PipelineRootCause.NO_GAP,
    "2026-10-13": PipelineRootCause.NO_GAP,
    "2026-10-14": PipelineRootCause.NO_GAP,
    "2026-10-15": PipelineRootCause.PIPELINE_SELECTIVE,
    "2026-10-16": PipelineRootCause.NO_GAP,
    "2026-10-19": PipelineRootCause.PIPELINE_SELECTIVE,
    "2026-10-20": PipelineRootCause.PIPELINE_SELECTIVE,
    "2026-10-21": PipelineRootCause.NO_GAP,
    "2026-10-22": PipelineRootCause.NO_GAP,
    "2026-10-27": PipelineRootCause.PIPELINE_SELECTIVE,
    "2026-10-28": PipelineRootCause.NO_GAP,
    "2026-10-29": PipelineRootCause.PIPELINE_SELECTIVE,
    "2026-10-30": PipelineRootCause.SCHEDULER_NOT_TRIGGERED,
    "2026-11-02": PipelineRootCause.SCHEDULER_NOT_TRIGGERED,
    "2026-11-03": PipelineRootCause.SCHEDULER_NOT_TRIGGERED,
    "2026-11-04": PipelineRootCause.MANUAL_BACKFILL,
    "2026-11-05": PipelineRootCause.MANUAL_BACKFILL,
    "2026-11-06": PipelineRootCause.QUALITY_GATE_FAIL,
    "2026-11-09": PipelineRootCause.PROVIDER_NOT_READY,
}

# Root cause confidence
_ROOT_CAUSE_CONFIDENCE: dict[str, RootCauseConfidence] = {
    "2026-10-08": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-12": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-13": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-14": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-15": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-16": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-19": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-20": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-21": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-22": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-27": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-28": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-29": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-10-30": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-11-02": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-11-03": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-11-04": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-11-05": RootCauseConfidence.ROOT_CAUSE_CONFIRMED,
    "2026-11-06": RootCauseConfidence.ROOT_CAUSE_PARTIAL,
    "2026-11-09": RootCauseConfidence.ROOT_CAUSE_PARTIAL,
}

# Fill dates (from forward_signals execution_date)
_FILL_DATES: frozenset[str] = frozenset([
    "2026-10-13", "2026-10-14", "2026-10-16",
    "2026-10-21", "2026-10-22", "2026-10-28",
])

# Active cluster 5D windows (trading days inside any cluster's hold period)
_ACTIVE_WINDOW_DATES: frozenset[str] = frozenset([
    # Oct 13 fill window
    "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20",
    # Oct 14 fill window
    "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21",
    # Oct 16 fill window
    "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-27",
    # Oct 21 fill window
    "2026-10-22", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30",
    # Oct 22 fill window
    "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-11-02",
    # Oct 28 fill window
    "2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04",
])

_BACKFILL_CANDIDATES: Tuple[str, ...] = (
    "2026-10-08", "2026-10-15", "2026-10-19", "2026-10-20",
    "2026-10-27", "2026-10-29", "2026-10-30",
    "2026-11-02", "2026-11-03", "2026-11-06", "2026-11-09",
)

# Reference fill-date stock count (universe at v8.0 filter stage)
_REFERENCE_STOCK_COUNT = 655


# ---------------------------------------------------------------------------
# Build functions
# ---------------------------------------------------------------------------

def _classify_tier(stock_count: int) -> PipelineTier:
    if stock_count == 0:
        return PipelineTier.TIER_ZERO_MISSING
    elif stock_count == 1:
        return PipelineTier.TIER_1_PROXY
    elif 400 <= stock_count <= 800:
        return PipelineTier.TIER_655_FILL
    elif stock_count >= 5000:
        return PipelineTier.TIER_6957_BACKFILL
    else:
        return PipelineTier.TIER_PARTIAL_LEGACY


def _last_pipeline_stage(date_str: str, tier: PipelineTier,
                          root_cause: PipelineRootCause) -> str:
    """Return the last pipeline stage that executed for this date."""
    if root_cause == PipelineRootCause.NO_GAP:
        return "S10_RESEARCH_CACHE"
    if root_cause == PipelineRootCause.MANUAL_BACKFILL:
        return "S07_SQLITE_WRITE"
    if root_cause == PipelineRootCause.SCHEDULER_NOT_TRIGGERED:
        return "S01_CALENDAR_CHECK"  # never reached scheduling
    if root_cause == PipelineRootCause.PIPELINE_SELECTIVE:
        # Reached S02 (scheduler ran) and S03 (fetched proxy) and S07 (wrote 0050)
        # but not S08/S09 because no signals executed
        return "S07_SQLITE_WRITE"
    if root_cause == PipelineRootCause.QUALITY_GATE_FAIL:
        return "S04_QUALITY_GATE"
    if root_cause == PipelineRootCause.PROVIDER_NOT_READY:
        return "S03_DATA_PROVIDER_FETCH"
    return "S01_CALENDAR_CHECK"


def _classify_coverage(stock_count: int, is_trading_day: bool,
                        tier: PipelineTier) -> CoverageStatus:
    if not is_trading_day:
        return CoverageStatus.NOT_TRADING_DAY
    if tier == PipelineTier.TIER_ZERO_MISSING:
        return CoverageStatus.DATA_MISSING
    if tier == PipelineTier.TIER_1_PROXY:
        return CoverageStatus.BENCHMARK_ONLY
    if tier in (PipelineTier.TIER_655_FILL, PipelineTier.TIER_6957_BACKFILL):
        return CoverageStatus.DATA_COMPLETE
    return CoverageStatus.DATA_PARTIAL


def build_daily_coverage_matrix(
    conn: sqlite3.Connection,
    analysis_date: str,
) -> DailyCoverageMatrix:
    """
    Build DailyCoverageMatrix for the Oct 08 – Nov 09 research window.
    READ-ONLY. No production writes.
    """
    all_dates_sorted = sorted(_TRADING_DAYS_OCT8_NOV9)
    records: list[DailyCoverageRecord] = []

    for date_str in all_dates_sorted:
        stock_count = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?",
            (date_str,),
        ).fetchone()[0]
        has_benchmark = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id='0050'",
            (date_str,),
        ).fetchone()[0] > 0
        has_tsmc = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id='2330'",
            (date_str,),
        ).fetchone()[0] > 0
        is_fill = date_str in _FILL_DATES
        root_cause = _ROOT_CAUSE_MAP.get(date_str, PipelineRootCause.UNKNOWN)
        confidence = _ROOT_CAUSE_CONFIDENCE.get(
            date_str, RootCauseConfidence.ROOT_CAUSE_UNDETERMINED
        )
        tier = _classify_tier(stock_count)
        coverage = _classify_coverage(stock_count, True, tier)
        last_stage = _last_pipeline_stage(date_str, tier, root_cause)

        if root_cause == PipelineRootCause.NO_GAP:
            source_type = "FILL_DATE_PIPELINE" if is_fill else "MANUAL_BACKFILL"
            recovery = "NOT_NEEDED"
        elif root_cause == PipelineRootCause.MANUAL_BACKFILL:
            source_type = "MANUAL_BACKFILL"
            recovery = "NOT_NEEDED"
        elif tier == PipelineTier.TIER_1_PROXY:
            source_type = "PROXY_ONLY"
            recovery = "BLOCKED"
        elif tier == PipelineTier.TIER_ZERO_MISSING:
            source_type = "NONE"
            recovery = "BLOCKED"
        else:
            source_type = "FILL_DATE_PIPELINE"
            recovery = "NOT_NEEDED"

        notes = _build_notes(date_str, root_cause, tier, is_fill)

        records.append(DailyCoverageRecord(
            date_str=date_str,
            is_trading_day=True,
            stock_count=stock_count,
            has_data=stock_count > 0,
            coverage_tier=tier,
            benchmark_present=has_benchmark,
            tsmc_present=has_tsmc,
            fill_date_flag=is_fill,
            proxy_date_flag=(tier == PipelineTier.TIER_1_PROXY),
            pipeline_root_cause=root_cause,
            coverage_status=coverage,
            source_type=source_type,
            pipeline_stage_reached=last_stage,
            recovery_feasibility=recovery,
            affects_active_cluster=date_str in _ACTIVE_WINDOW_DATES,
            root_cause_confidence=confidence,
            notes=notes,
        ))

    complete_days = sum(1 for r in records if r.coverage_status == CoverageStatus.DATA_COMPLETE)
    benchmark_only = sum(1 for r in records if r.coverage_status == CoverageStatus.BENCHMARK_ONLY)
    missing_days = sum(1 for r in records if r.coverage_status == CoverageStatus.DATA_MISSING)
    tier_1 = sum(1 for r in records if r.coverage_tier == PipelineTier.TIER_1_PROXY)
    tier_655 = sum(1 for r in records if r.coverage_tier == PipelineTier.TIER_655_FILL)
    tier_6957 = sum(1 for r in records if r.coverage_tier == PipelineTier.TIER_6957_BACKFILL)
    rc_confirmed = sum(1 for r in records if r.root_cause_confidence == RootCauseConfidence.ROOT_CAUSE_CONFIRMED)
    rc_partial = sum(1 for r in records if r.root_cause_confidence == RootCauseConfidence.ROOT_CAUSE_PARTIAL)
    rc_undetermined = sum(1 for r in records if r.root_cause_confidence == RootCauseConfidence.ROOT_CAUSE_UNDETERMINED)

    return DailyCoverageMatrix(
        analysis_date=analysis_date,
        records=tuple(records),
        total_trading_days=len(records),
        complete_days=complete_days,
        benchmark_only_days=benchmark_only,
        missing_days=missing_days,
        root_cause_confirmed=rc_confirmed,
        root_cause_partial=rc_partial,
        root_cause_undetermined=rc_undetermined,
        tier_1_proxy_days=tier_1,
        tier_655_fill_days=tier_655,
        tier_6957_backfill_days=tier_6957,
    )


def _build_notes(date_str: str, root_cause: PipelineRootCause,
                 tier: PipelineTier, is_fill: bool) -> str:
    if root_cause == PipelineRootCause.NO_GAP:
        if is_fill:
            return "Fill date: full v8.0-filtered universe fetched for signal execution"
        return "Manual backfill: full TWSE+TPEx universe recovered"
    if root_cause == PipelineRootCause.PIPELINE_SELECTIVE:
        return "Non-fill trading day: pipeline wrote 0050 proxy only; no signals executed"
    if root_cause == PipelineRootCause.SCHEDULER_NOT_TRIGGERED:
        return "Cron not running; first cron entry 2026-11-09T08:00:17Z"
    if root_cause == PipelineRootCause.QUALITY_GATE_FAIL:
        return "Cron ran but QG rejected data; date fully absent from daily_prices"
    if root_cause == PipelineRootCause.PROVIDER_NOT_READY:
        return "Cron ran but TWSE api_date was stale; no data fetched"
    if root_cause == PipelineRootCause.MANUAL_BACKFILL:
        return "Manually backfilled via backfill_daily_prices.py on 2026-11-05"
    return "Unknown root cause"


def build_backfill_dry_run_plan(
    conn: sqlite3.Connection,
    analysis_date: str,
    reference_stock_count: int = _REFERENCE_STOCK_COUNT,
) -> BackfillDryRunPlan:
    """
    Dry-run backfill planning for 11 candidate dates.
    READ-ONLY. No production writes. No external API calls.
    """
    records: list[BackfillDryRunRecord] = []

    for date_str in _BACKFILL_CANDIDATES:
        existing = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=?", (date_str,)
        ).fetchone()[0]
        unique_stocks = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?",
            (date_str,),
        ).fetchone()[0]
        has_0050 = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id='0050'",
            (date_str,),
        ).fetchone()[0] > 0
        is_fill = conn.execute(
            "SELECT COUNT(*) FROM forward_signals WHERE execution_date=?",
            (date_str,),
        ).fetchone()[0] > 0

        # 0050 conflict: existing row for 0050 must be compared
        has_0050_conflict = has_0050  # any insert for 0050 would conflict

        estimated_missing = reference_stock_count - unique_stocks
        candidate_insert = estimated_missing  # 0050 already there, rest to insert

        # Source availability: historical TWSE API can provide data for past dates
        # but authorization for research environment has not been granted.
        if date_str in ("2026-11-06", "2026-11-09"):
            source = "API_UNVERIFIED"
            readiness = BackfillReadiness.UNIVERSE_UNVERIFIED
            conflict_risk = "LOW"
            notes = "0 existing rows; would need full insert; source availability unconfirmed"
        elif has_0050_conflict:
            source = "API_UNVERIFIED"
            readiness = BackfillReadiness.INSERT_ONLY_CANDIDATE
            conflict_risk = "LOW"
            notes = "0050 already present; backfill would INSERT ~655 missing stocks; no UPDATE needed"
        else:
            source = "NOT_APPLICABLE"
            readiness = BackfillReadiness.NOT_REQUIRED
            conflict_risk = "NONE"
            notes = "Already complete"

        records.append(BackfillDryRunRecord(
            date_str=date_str,
            existing_rows=existing,
            unique_existing_stocks=unique_stocks,
            has_0050_conflict=has_0050_conflict,
            estimated_missing_stocks=estimated_missing,
            candidate_insert_count=candidate_insert,
            is_fill_date=is_fill,
            source_availability=source,
            readiness=readiness,
            conflict_risk=conflict_risk,
            notes=notes,
        ))

    insert_only = sum(1 for r in records if r.readiness == BackfillReadiness.INSERT_ONLY_CANDIDATE)
    conflict = sum(1 for r in records if r.readiness == BackfillReadiness.CONFLICT_REQUIRES_REVIEW)
    unavail = sum(1 for r in records if r.readiness == BackfillReadiness.SOURCE_UNAVAILABLE)
    unverified = sum(1 for r in records if r.readiness == BackfillReadiness.UNIVERSE_UNVERIFIED)

    return BackfillDryRunPlan(
        analysis_date=analysis_date,
        candidate_dates=_BACKFILL_CANDIDATES,
        records=tuple(records),
        insert_only_count=insert_only,
        conflict_count=conflict,
        source_unavailable_count=unavail,
        universe_unverified_count=unverified,
    )


def get_pipeline_stage_analysis(date_str: str) -> List[PipelineStageResult]:
    """Return per-stage analysis for a specific date."""
    root_cause = _ROOT_CAUSE_MAP.get(date_str, PipelineRootCause.UNKNOWN)
    results = []

    if root_cause == PipelineRootCause.NO_GAP:
        for stage in PIPELINE_STAGES:
            results.append(PipelineStageResult(
                stage=stage, reached=True, result="PASS",
                detail="Normal execution"
            ))
    elif root_cause == PipelineRootCause.SCHEDULER_NOT_TRIGGERED:
        results.append(PipelineStageResult(
            "S01_CALENDAR_CHECK", True, "PASS", "Calendar: trading day confirmed"
        ))
        for stage in PIPELINE_STAGES[1:]:
            results.append(PipelineStageResult(
                stage, False, "SKIPPED", "Scheduler not running; not reached"
            ))
    elif root_cause == PipelineRootCause.PIPELINE_SELECTIVE:
        # Scheduler ran; fetched 0050 proxy; wrote 0050; no signal stages
        for stage in PIPELINE_STAGES[:7]:
            results.append(PipelineStageResult(stage, True, "PASS",
                "Reached: proxy-only execution"))
        results.append(PipelineStageResult(
            "S08_SIGNAL_TRIGGER", True, "NOT_APPLICABLE",
            "No signals executing today; full data pull skipped"
        ))
        results.append(PipelineStageResult(
            "S09_SIGNAL_EXECUTION", False, "SKIPPED", "No signals"
        ))
        results.append(PipelineStageResult(
            "S10_RESEARCH_CACHE", False, "SKIPPED", "No signals"
        ))
    elif root_cause == PipelineRootCause.QUALITY_GATE_FAIL:
        for stage in PIPELINE_STAGES[:3]:
            results.append(PipelineStageResult(
                stage, True, "PASS", "Reached"
            ))
        results.append(PipelineStageResult(
            "S04_QUALITY_GATE", True, "FAIL", "QG rejected data; not written to DB"
        ))
        for stage in PIPELINE_STAGES[4:]:
            results.append(PipelineStageResult(
                stage, False, "SKIPPED", "Blocked by QG failure"
            ))
    elif root_cause == PipelineRootCause.PROVIDER_NOT_READY:
        results.append(PipelineStageResult(
            "S01_CALENDAR_CHECK", True, "PASS", "Trading day"
        ))
        results.append(PipelineStageResult(
            "S02_SCHEDULER_VERIFY", True, "PASS", "Scheduler running"
        ))
        results.append(PipelineStageResult(
            "S03_DATA_PROVIDER_FETCH", True, "FAIL", "TWSE api_date stale; no fresh data"
        ))
        for stage in PIPELINE_STAGES[3:]:
            results.append(PipelineStageResult(
                stage, False, "SKIPPED", "Blocked by provider failure"
            ))
    elif root_cause == PipelineRootCause.MANUAL_BACKFILL:
        for stage in ["S01_CALENDAR_CHECK", "S06_DEDUP_CHECK", "S07_SQLITE_WRITE"]:
            results.append(PipelineStageResult(
                stage, True, "PASS", "Manual backfill path"
            ))
        for stage in [s for s in PIPELINE_STAGES if s not in
                      ["S01_CALENDAR_CHECK", "S06_DEDUP_CHECK", "S07_SQLITE_WRITE"]]:
            results.append(PipelineStageResult(
                stage, False, "NOT_APPLICABLE", "Manual backfill; normal pipeline not triggered"
            ))
    else:
        for stage in PIPELINE_STAGES:
            results.append(PipelineStageResult(
                stage, False, "SKIPPED", "Unknown root cause"
            ))

    return results
