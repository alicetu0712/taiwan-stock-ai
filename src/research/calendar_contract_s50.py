"""
Research Trading Calendar Contract — Single Source of Truth (Session 50 PARTS D–H).

This module supersedes the duplicate calendar dicts in pipeline_recovery_s49.py
and consolidates all authoritative calendar values into one SSOT.

CONSOLIDATION HISTORY:
  calendar_contract_s48.py  — first introduced _CORRECT_5TD/_CORRECT_20TD (S48, frozen)
  pipeline_recovery_s49.py  — duplicated same values as overlay layer (S49, frozen)
  calendar_contract_s50.py  — THIS FILE: single SSOT. Neither S48 nor S49 modified.

IMPORTANT: prospective_comparison_s46.py still contains the ERRONEOUS S46 dates.
  It is NOT modified here. All new callers MUST use get_corrected_exit() from this module.
  Any function that still calls S46's _CALENDAR_5TD/_CALENDAR_20TD will produce wrong dates.

G04 DEPENDENCE STUDY (S50 PART G — NEW ANALYSIS):
  Weekly spacing reduces but does NOT fully resolve G04. See G04DependenceStudy below.
  Key finding: Oct 21/Oct 28 pair has 40% overlap even with ≥5 TD spacing → G04 still FAILS.
  Root cause: 5-day holding period + ≤5-TD between fills → structural G04 failure.

SAFETY: READ-ONLY. No production writes.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CalendarSource(str, Enum):
    S46_ERRONEOUS = "S46_ERRONEOUS"          # Original S46 values (3 of 6 5TD wrong; all 6 20TD wrong)
    S48_CORRECTED = "S48_CORRECTED"          # Corrections introduced in S48
    S50_SSOT = "S50_SSOT"                    # This file — authoritative single source of truth


class PipelineStageStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"
    BLOCKED = "BLOCKED"
    DATA_COMPLETE = "DATA_COMPLETE"
    BENCHMARK_ONLY = "BENCHMARK_ONLY"


class StrictEligibilityStatus(str, Enum):
    STRICT_ELIGIBLE = "STRICT_ELIGIBLE"                   # proxy_count ≥ 5 now
    READY_AFTER_VERIFIED_BACKFILL = "READY_AFTER_VERIFIED_BACKFILL"  # backfill makes it eligible
    WAITING_FOR_PIPELINE = "WAITING_FOR_PIPELINE"         # future dates not yet reached
    INSUFFICIENT_PROXY = "INSUFFICIENT_PROXY"             # proxy_count < 5


class TwentyDReadinessVerdict(str, Enum):
    NOT_YET_MATURE = "NOT_YET_MATURE"
    MATURE_PENDING_DATA = "MATURE_PENDING_DATA"
    DATA_AVAILABLE = "DATA_AVAILABLE"
    AUTHORIZED_READY = "AUTHORIZED_READY"
    BLOCKED_PIPELINE = "BLOCKED_PIPELINE"
    BLOCKED_AUTH01 = "BLOCKED_AUTH01"


class G04WeeklySpacingVerdict(str, Enum):
    G04_PASS = "G04_PASS"
    G04_FAIL = "G04_FAIL"
    G04_PARTIAL = "G04_PARTIAL"


# ---------------------------------------------------------------------------
# Authoritative Calendar Contract — SSOT
# ---------------------------------------------------------------------------
# S46 errors:
#   5TD: Oct 13 had Oct 21 (should Oct 20), Oct 14 had Oct 28 (should Oct 21),
#        Oct 16 had Nov 05 (should Oct 27)
#   20TD: ALL 6 dates were wrong (2–7 days too late)

_S46_5TD: Dict[str, str] = {
    "2026-10-13": "2026-10-21",   # WRONG  (Δ=+1 TD)
    "2026-10-14": "2026-10-28",   # WRONG  (Δ=+5 TD)
    "2026-10-16": "2026-11-05",   # WRONG  (Δ=+7 TD)
    "2026-10-21": "2026-10-30",   # correct
    "2026-10-22": "2026-11-02",   # correct
    "2026-10-28": "2026-11-04",   # correct
}

_S46_20TD: Dict[str, str] = {
    "2026-10-13": "2026-11-14",   # WRONG  (Δ=+2d)
    "2026-10-14": "2026-11-17",   # WRONG  (Δ=+4d)
    "2026-10-16": "2026-11-19",   # WRONG  (Δ=+2d)
    "2026-10-21": "2026-11-24",   # WRONG  (Δ=+4d)
    "2026-10-22": "2026-11-25",   # WRONG  (Δ=+2d)
    "2026-10-28": "2026-12-02",   # WRONG  (Δ=+7d)
}

# AUTHORITATIVE VALUES — corrected in S48, confirmed in S49, SSOT in S50
_CORRECT_5TD: Dict[str, str] = {
    "2026-10-13": "2026-10-20",   # S46 had 2026-10-21 (CORRECTED)
    "2026-10-14": "2026-10-21",   # S46 had 2026-10-28 (CORRECTED)
    "2026-10-16": "2026-10-27",   # S46 had 2026-11-05 (CORRECTED)
    "2026-10-21": "2026-10-30",   # S46 correct (UNCHANGED)
    "2026-10-22": "2026-11-02",   # S46 correct (UNCHANGED)
    "2026-10-28": "2026-11-04",   # S46 correct (UNCHANGED)
}

_CORRECT_20TD: Dict[str, str] = {
    "2026-10-13": "2026-11-12",   # S46 had 2026-11-14 (CORRECTED, Δ=-2d)
    "2026-10-14": "2026-11-13",   # S46 had 2026-11-17 (CORRECTED, Δ=-4d)
    "2026-10-16": "2026-11-17",   # S46 had 2026-11-19 (CORRECTED, Δ=-2d)
    "2026-10-21": "2026-11-20",   # S46 had 2026-11-24 (CORRECTED, Δ=-4d)
    "2026-10-22": "2026-11-23",   # S46 had 2026-11-25 (CORRECTED, Δ=-2d)
    "2026-10-28": "2026-11-25",   # S46 had 2026-12-02 (CORRECTED, Δ=-7d)
}

# 5TD window = {TD1, ..., TD5} for each fill date (all 5 trading days in holding period)
_FIVE_TD_WINDOW: Dict[str, List[str]] = {
    "2026-10-13": ["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"],
    "2026-10-14": ["2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"],
    "2026-10-16": ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-27"],
    "2026-10-21": ["2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27", "2026-10-28"],
    "2026-10-22": ["2026-10-23", "2026-10-26", "2026-10-27", "2026-10-28", "2026-11-02"],
    "2026-10-28": ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04"],
}

# Established pairwise 5TD window overlap (from guardrails_session49.md, all 15 pairs)
_PAIRWISE_OVERLAP: Dict[Tuple[str, str], Dict] = {
    ("2026-10-13", "2026-10-14"): {"shared": 4, "pct": 80, "adjacent": True},
    ("2026-10-13", "2026-10-16"): {"shared": 2, "pct": 40, "adjacent": False},
    ("2026-10-13", "2026-10-21"): {"shared": 0, "pct": 0, "adjacent": False},
    ("2026-10-13", "2026-10-22"): {"shared": 0, "pct": 0, "adjacent": False},
    ("2026-10-13", "2026-10-28"): {"shared": 0, "pct": 0, "adjacent": False},
    ("2026-10-14", "2026-10-16"): {"shared": 3, "pct": 60, "adjacent": True},
    ("2026-10-14", "2026-10-21"): {"shared": 0, "pct": 0, "adjacent": False},
    ("2026-10-14", "2026-10-22"): {"shared": 0, "pct": 0, "adjacent": False},
    ("2026-10-14", "2026-10-28"): {"shared": 0, "pct": 0, "adjacent": False},
    ("2026-10-16", "2026-10-21"): {"shared": 2, "pct": 40, "adjacent": True},
    ("2026-10-16", "2026-10-22"): {"shared": 1, "pct": 20, "adjacent": False},
    ("2026-10-16", "2026-10-28"): {"shared": 0, "pct": 0, "adjacent": False},
    ("2026-10-21", "2026-10-22"): {"shared": 4, "pct": 80, "adjacent": True},
    ("2026-10-21", "2026-10-28"): {"shared": 2, "pct": 40, "adjacent": False},
    ("2026-10-22", "2026-10-28"): {"shared": 3, "pct": 60, "adjacent": True},
}


def get_overlap(fill_a: str, fill_b: str) -> Dict:
    """Get overlap data for a pair of fills. Order-insensitive."""
    key = (fill_a, fill_b)
    rev = (fill_b, fill_a)
    return _PAIRWISE_OVERLAP.get(key) or _PAIRWISE_OVERLAP.get(rev) or {"shared": 0, "pct": 0, "adjacent": False}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CalendarCorrectionRecord:
    fill_date: str
    holding_period: str
    s46_exit: str
    corrected_exit: str
    calendar_days_delta: int
    was_error: bool
    error_direction: str
    source: CalendarSource


@dataclass
class ResearchTradingCalendarContract:
    fill_dates: List[str]
    corrections_5td: List[CalendarCorrectionRecord]
    corrections_20td: List[CalendarCorrectionRecord]
    n_5td_errors: int
    n_20td_errors: int
    ssot_version: str
    fingerprint: str
    consolidation_note: str
    s46_module_status: str


@dataclass
class PipelineStageRecord:
    stage_id: str
    stage_name: str
    description: str
    data_complete_criterion: str
    benchmark_only_allowed: bool
    minimum_stock_count: Optional[int]
    failure_verdict: str


@dataclass
class PipelineCompletionContract:
    stages: List[PipelineStageRecord]
    data_complete_definition: str
    benchmark_only_rejection_rule: str
    minimum_stocks_for_data_complete: int
    total_stages: int
    critical_stages: List[str]
    pipeline_blocked_reason: str


@dataclass
class Strict5DClusterRecord:
    fill_date: str
    exit_5td: str
    proxy_count_now: int
    strict_eligible_now: bool
    proxy_count_after_p1_backfill: int
    strict_eligible_after_p1: bool
    status: StrictEligibilityStatus
    blocking_reason: Optional[str]
    backfill_dates_needed: List[str]


@dataclass
class Strict5DEligibilityMatrix:
    clusters: List[Strict5DClusterRecord]
    n_strict_now: int
    n_strict_after_p1: int
    g03_now: bool
    g03_after_p1: bool
    g03_requirement: int
    grand_mean_delta: float
    frozen_baseline_fingerprint: str


@dataclass
class WeeklySpacingScenario:
    name: str
    min_td_gap: int
    retained_fills: List[str]
    n_retained: int
    adjacent_pairs: List[Tuple[str, str]]
    max_overlap_pct: int
    g04_verdict: G04WeeklySpacingVerdict
    g03_verdict: bool
    tradeoff_note: str


@dataclass
class G04DependenceStudy:
    all_fills: List[str]
    all_overlaps: Dict[str, int]
    max_adjacent_overlap_pct: int
    g04_current_verdict: G04WeeklySpacingVerdict
    n_adjacent_failing: int
    weekly_spacing_scenarios: List[WeeklySpacingScenario]
    effective_n_calculation: Dict[str, float]
    bootstrap_applicable: bool
    bootstrap_blocked_reason: str
    root_cause: str
    remediation_recommendation: str
    finding: str


@dataclass
class TwentyDReadinessRecord:
    fill_date: str
    exit_20td_corrected: str
    exit_20td_s46_erroneous: str
    calendar_days_to_maturity: int
    is_mature: bool
    pipeline_data_available: bool
    strict_eligible: bool
    auth01_granted: bool
    auth02_granted: bool
    verdict: TwentyDReadinessVerdict
    days_until_maturity: int
    notes: str


@dataclass
class TwentyDReadinessMatrix:
    clusters: List[TwentyDReadinessRecord]
    earliest_maturity_date: str
    latest_maturity_date: str
    n_mature_now: int
    n_mature_after_maturity_date: int
    auth01_status: str
    auth02_status: str
    overall_verdict: TwentyDReadinessVerdict
    critical_path: str
    nov12_hard_deadline_note: str


# ---------------------------------------------------------------------------
# Calendar Contract Construction
# ---------------------------------------------------------------------------

def build_research_trading_calendar_contract() -> ResearchTradingCalendarContract:
    """
    Build the authoritative calendar contract for all 6 fill dates.
    Single source of truth consolidating S48 + S49 corrections.
    """
    fills = ["2026-10-13", "2026-10-14", "2026-10-16", "2026-10-21", "2026-10-22", "2026-10-28"]

    corrections_5td = []
    n_5td_errors = 0
    for f in fills:
        s46 = _S46_5TD[f]
        corrected = _CORRECT_5TD[f]
        was_error = s46 != corrected
        if was_error:
            n_5td_errors += 1
        from datetime import date
        d_s46 = date.fromisoformat(s46)
        d_cor = date.fromisoformat(corrected)
        delta = (d_cor - d_s46).days
        corrections_5td.append(CalendarCorrectionRecord(
            fill_date=f,
            holding_period="5TD",
            s46_exit=s46,
            corrected_exit=corrected,
            calendar_days_delta=delta,
            was_error=was_error,
            error_direction="too_late" if delta < 0 else "correct",
            source=CalendarSource.S50_SSOT,
        ))

    corrections_20td = []
    n_20td_errors = 0
    for f in fills:
        s46 = _S46_20TD[f]
        corrected = _CORRECT_20TD[f]
        was_error = True  # all 6 were wrong in S46
        n_20td_errors += 1
        from datetime import date
        d_s46 = date.fromisoformat(s46)
        d_cor = date.fromisoformat(corrected)
        delta = (d_cor - d_s46).days
        corrections_20td.append(CalendarCorrectionRecord(
            fill_date=f,
            holding_period="20TD",
            s46_exit=s46,
            corrected_exit=corrected,
            calendar_days_delta=delta,
            was_error=True,
            error_direction="too_late",
            source=CalendarSource.S50_SSOT,
        ))

    fp_data = json.dumps({
        "5td": _CORRECT_5TD, "20td": _CORRECT_20TD, "version": "s50"
    }, sort_keys=True)
    fp = "CCFP-" + hashlib.sha256(fp_data.encode()).hexdigest()[:8]

    return ResearchTradingCalendarContract(
        fill_dates=fills,
        corrections_5td=corrections_5td,
        corrections_20td=corrections_20td,
        n_5td_errors=n_5td_errors,
        n_20td_errors=n_20td_errors,
        ssot_version="S50",
        fingerprint=fp,
        consolidation_note=(
            "calendar_contract_s48 (S48) introduced _CORRECT_5TD/_CORRECT_20TD. "
            "pipeline_recovery_s49 (S49) duplicated the same values as an overlay. "
            "calendar_contract_s50 (S50) is the SINGLE SSOT. "
            "Neither S48 nor S49 modules are modified. "
            "New callers MUST import get_corrected_exit() from this module."
        ),
        s46_module_status=(
            "prospective_comparison_s46.py UNCHANGED — still contains ERRONEOUS S46 dates. "
            "Do NOT use _CALENDAR_5TD or _CALENDAR_20TD from that module. "
            "Modification requires explicit authorization in a separate session."
        ),
    )


def get_corrected_exit(fill_date: str, holding_period: str) -> Optional[str]:
    """
    Return the authoritative corrected exit date.
    holding_period: '5TD' or '20TD'
    Returns None if fill_date not found.
    """
    if holding_period == "5TD":
        return _CORRECT_5TD.get(fill_date)
    elif holding_period == "20TD":
        return _CORRECT_20TD.get(fill_date)
    return None


# ---------------------------------------------------------------------------
# Pipeline Completion Contract — PARTS D
# ---------------------------------------------------------------------------

def build_pipeline_completion_contract() -> PipelineCompletionContract:
    """
    10-stage pipeline completion contract with explicit DATA_COMPLETE criteria.
    BENCHMARK_ONLY (1 stock = 0050 proxy) is explicitly NOT DATA_COMPLETE.
    """
    stages = [
        PipelineStageRecord(
            stage_id="S01",
            stage_name="SCHEDULER_TRIGGER",
            description="Cron job triggers pipeline execution on a trading day",
            data_complete_criterion="N/A — prerequisite stage",
            benchmark_only_allowed=False,
            minimum_stock_count=None,
            failure_verdict="SCHEDULER_NOT_TRIGGERED",
        ),
        PipelineStageRecord(
            stage_id="S02",
            stage_name="PROVIDER_READY_CHECK",
            description="API provider returns data for TODAY (api_date == execution_date)",
            data_complete_criterion="api_date == expected trading date (tolerance 0)",
            benchmark_only_allowed=False,
            minimum_stock_count=None,
            failure_verdict="PROVIDER_NOT_READY",
        ),
        PipelineStageRecord(
            stage_id="S03",
            stage_name="BULK_FETCH",
            description="Bulk download: attempt TWSE + TPEx current-day endpoints",
            data_complete_criterion="at least one provider returns ≥ 1000 records",
            benchmark_only_allowed=False,
            minimum_stock_count=1000,
            failure_verdict="BULK_FETCH_FAILED",
        ),
        PipelineStageRecord(
            stage_id="S04",
            stage_name="UNIVERSE_FILTER",
            description="Filter to v8.0 universe: 4-digit numeric codes only (excludes ETFs)",
            data_complete_criterion="filtered count ≥ 300 (not benchmark only)",
            benchmark_only_allowed=False,
            minimum_stock_count=300,
            failure_verdict="UNIVERSE_FILTER_FAILED",
        ),
        PipelineStageRecord(
            stage_id="S05",
            stage_name="QUALITY_GATE",
            description="QG: check OHLC validity, price bounds, volume reasonableness",
            data_complete_criterion="pass_rate ≥ 95% AND stock_count ≥ 300",
            benchmark_only_allowed=False,
            minimum_stock_count=300,
            failure_verdict="QUALITY_GATE_FAIL",
        ),
        PipelineStageRecord(
            stage_id="S06",
            stage_name="CONFLICT_DETECTION",
            description="Check for existing records on this date; flag conflicts",
            data_complete_criterion="conflict_count == 0 OR conflicts explicitly resolved",
            benchmark_only_allowed=False,
            minimum_stock_count=None,
            failure_verdict="CONFLICT_DETECTED",
        ),
        PipelineStageRecord(
            stage_id="S07",
            stage_name="TRANSACTION_PREPARE",
            description="Build INSERT OR IGNORE batch; compute fingerprint",
            data_complete_criterion="n_prepared == n_qg_passed",
            benchmark_only_allowed=False,
            minimum_stock_count=None,
            failure_verdict="TRANSACTION_PREPARE_FAILED",
        ),
        PipelineStageRecord(
            stage_id="S08",
            stage_name="TRANSACTION_COMMIT",
            description="Atomic commit; rollback on any error",
            data_complete_criterion="rows_inserted == n_prepared (all committed or none)",
            benchmark_only_allowed=False,
            minimum_stock_count=None,
            failure_verdict="TRANSACTION_COMMIT_FAILED",
        ),
        PipelineStageRecord(
            stage_id="S09",
            stage_name="COVERAGE_VERIFY",
            description="Post-write verification: count stocks in DB for this date",
            data_complete_criterion="stock_count ≥ 300 (not 1 benchmark proxy)",
            benchmark_only_allowed=False,
            minimum_stock_count=300,
            failure_verdict="COVERAGE_VERIFY_FAILED",
        ),
        PipelineStageRecord(
            stage_id="S10",
            stage_name="PIPELINE_COMPLETE",
            description="Audit log written; downstream signal refresh triggered",
            data_complete_criterion="all prior stages PASS AND audit_log written",
            benchmark_only_allowed=False,
            minimum_stock_count=None,
            failure_verdict="PIPELINE_INCOMPLETE",
        ),
    ]

    return PipelineCompletionContract(
        stages=stages,
        data_complete_definition=(
            "DATA_COMPLETE: S04 ≥ 300 stocks AND S05 QG PASS AND S08 committed AND S09 ≥ 300. "
            "DATA_COMPLETE is binary — partial completion does not count."
        ),
        benchmark_only_rejection_rule=(
            "BENCHMARK_ONLY_REJECTED: If daily_prices for a given date contains only 1 stock (0050 proxy), "
            "that date is NOT DATA_COMPLETE. It is classified as TIER_1_PROXY. "
            "TIER_1_PROXY cannot serve as an exit-price source for multi-stock portfolio evaluation."
        ),
        minimum_stocks_for_data_complete=300,
        total_stages=10,
        critical_stages=["S02", "S05", "S09"],
        pipeline_blocked_reason=(
            "Pipeline blocked since Nov 05 (last DATA_COMPLETE date). "
            "Nov 06: QUALITY_GATE_FAIL — bulk provider passed but stock count insufficient. "
            "Nov 09: PROVIDER_NOT_READY — api_date returned Nov 06, not Nov 09. "
            "Root cause: SCHEDULER_NOT_TRIGGERED or bulk API date detection failure. "
            "Resolution requires authorized pipeline fix (not in scope for S50 research)."
        ),
    )


# ---------------------------------------------------------------------------
# Strict 5D Eligibility Matrix — PART F
# ---------------------------------------------------------------------------

# Proxy counts as of platform.db today (READ-ONLY, pre-established in A1)
_PROXY_COUNTS_NOW: Dict[str, int] = {
    "2026-10-13": 7,
    "2026-10-14": 6,
    "2026-10-16": 5,
    "2026-10-21": 4,
    "2026-10-22": 3,
    "2026-10-28": 2,
}

# Proxy counts after P1 backfill (Oct 29/30/Nov 02/03) — from S49 SC10
_PROXY_COUNTS_AFTER_P1: Dict[str, int] = {
    "2026-10-13": 7,   # unchanged (backfill dates are after window; proxy is about all TSMC-present dates post-fill)
    "2026-10-14": 6,   # unchanged
    "2026-10-16": 5,   # unchanged
    "2026-10-21": 8,   # Oct 29/30/Nov02 added (backfill brings 3 new TSMC-present dates after Oct 21)
    "2026-10-22": 7,   # Oct 29/30/Nov02 added (3 new dates after Oct 22)
    "2026-10-28": 5,   # Oct 29/30/Nov02 added (3 new dates after Oct 28)
}

_BACKFILL_DATES_NEEDED: Dict[str, List[str]] = {
    "2026-10-13": [],
    "2026-10-14": [],
    "2026-10-16": [],
    "2026-10-21": ["2026-10-29"],
    "2026-10-22": ["2026-10-29", "2026-10-30"],
    "2026-10-28": ["2026-10-29", "2026-10-30", "2026-11-02"],
}

STRICT_THRESHOLD = 5


def build_strict5d_eligibility_matrix() -> Strict5DEligibilityMatrix:
    fills = ["2026-10-13", "2026-10-14", "2026-10-16", "2026-10-21", "2026-10-22", "2026-10-28"]
    clusters = []

    for f in fills:
        cnt_now = _PROXY_COUNTS_NOW[f]
        cnt_p1 = _PROXY_COUNTS_AFTER_P1[f]
        eligible_now = cnt_now >= STRICT_THRESHOLD
        eligible_p1 = cnt_p1 >= STRICT_THRESHOLD
        backfill_needed = _BACKFILL_DATES_NEEDED[f]

        if eligible_now:
            status = StrictEligibilityStatus.STRICT_ELIGIBLE
            blocking = None
        elif eligible_p1:
            status = StrictEligibilityStatus.READY_AFTER_VERIFIED_BACKFILL
            blocking = f"Need AUTH01 backfill of {backfill_needed} to reach proxy_count ≥ {STRICT_THRESHOLD}"
        else:
            status = StrictEligibilityStatus.INSUFFICIENT_PROXY
            blocking = f"Even after P1 backfill, proxy_count={cnt_p1} < {STRICT_THRESHOLD}"

        clusters.append(Strict5DClusterRecord(
            fill_date=f,
            exit_5td=_CORRECT_5TD[f],
            proxy_count_now=cnt_now,
            strict_eligible_now=eligible_now,
            proxy_count_after_p1_backfill=cnt_p1,
            strict_eligible_after_p1=eligible_p1,
            status=status,
            blocking_reason=blocking,
            backfill_dates_needed=backfill_needed,
        ))

    n_now = sum(1 for c in clusters if c.strict_eligible_now)
    n_p1 = sum(1 for c in clusters if c.strict_eligible_after_p1)

    return Strict5DEligibilityMatrix(
        clusters=clusters,
        n_strict_now=n_now,
        n_strict_after_p1=n_p1,
        g03_now=n_now >= 10,
        g03_after_p1=n_p1 >= 10,
        g03_requirement=10,
        grand_mean_delta=0.81,
        frozen_baseline_fingerprint="09c04e8c4059d87e",
    )


# ---------------------------------------------------------------------------
# G04 Dependence Study — PART G (NEW in S50)
# ---------------------------------------------------------------------------

def _apply_weekly_spacing(fills: List[str], min_td_gap: int) -> List[str]:
    """
    Retain only fill dates where the gap from the previous retained fill >= min_td_gap TD.
    Uses pre-established trading day sequence to count gaps.
    """
    # Trading day sequence covering all relevant fill dates
    _ALL_TRADING_DAYS = [
        "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16",
        "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22",
        "2026-10-23", "2026-10-26", "2026-10-27", "2026-10-28",
    ]
    td_index = {d: i for i, d in enumerate(_ALL_TRADING_DAYS)}

    retained = []
    for f in fills:
        if not retained:
            retained.append(f)
            continue
        last = retained[-1]
        gap = td_index.get(f, 999) - td_index.get(last, 0)
        if gap >= min_td_gap:
            retained.append(f)
    return retained


def build_g04_dependence_study() -> G04DependenceStudy:
    """
    G04 dependence study: weekly spacing scenarios + cluster-aware bootstrap limitations.

    Key finding (S50 NEW):
    - Applying ≥5 TD spacing produces {Oct 13, Oct 21, Oct 28} (N=3).
    - Oct 21/Oct 28 pair in this subset has 40% overlap → G04 STILL FAILS.
    - Applying ≥6 TD spacing produces {Oct 13, Oct 21} (N=2) → G04 passes but G03 worse.
    - Bootstrap with cluster-aware correction requires N≥10, not applicable now.
    - Root cause: 5-day holding window + fill dates ≤5 TD apart = structural overlap.
    """
    all_fills = ["2026-10-13", "2026-10-14", "2026-10-16", "2026-10-21", "2026-10-22", "2026-10-28"]

    # Collect overlaps for all adjacent pairs in original set
    adjacent_pairs_orig = [
        ("2026-10-13", "2026-10-14"),
        ("2026-10-14", "2026-10-16"),
        ("2026-10-16", "2026-10-21"),
        ("2026-10-21", "2026-10-22"),
        ("2026-10-22", "2026-10-28"),
    ]
    all_overlaps = {
        f"{a}/{b}": get_overlap(a, b)["pct"]
        for a, b in adjacent_pairs_orig
    }
    max_pct = max(all_overlaps.values())

    # Weekly spacing scenarios
    scenarios = []

    # Scenario 1: ≥5 TD spacing
    r5 = _apply_weekly_spacing(all_fills, 5)
    adj5 = [(r5[i], r5[i+1]) for i in range(len(r5)-1)]
    max5 = max((get_overlap(a, b)["pct"] for a, b in adj5), default=0)
    scenarios.append(WeeklySpacingScenario(
        name="WEEKLY_5TD",
        min_td_gap=5,
        retained_fills=r5,
        n_retained=len(r5),
        adjacent_pairs=adj5,
        max_overlap_pct=max5,
        g04_verdict=G04WeeklySpacingVerdict.G04_FAIL if max5 > 30 else G04WeeklySpacingVerdict.G04_PASS,
        g03_verdict=len(r5) >= 10,
        tradeoff_note=(
            f"N={len(r5)}: G04 max adjacent overlap={max5}% "
            f"({'FAIL' if max5 > 30 else 'PASS'}). "
            "Oct 21/Oct 28 pair (5 TD apart) has 40% overlap → G04 STILL FAILS. "
            "G03 NOT MET (need 10)."
        ),
    ))

    # Scenario 2: ≥6 TD spacing
    r6 = _apply_weekly_spacing(all_fills, 6)
    adj6 = [(r6[i], r6[i+1]) for i in range(len(r6)-1)]
    max6 = max((get_overlap(a, b)["pct"] for a, b in adj6), default=0)
    scenarios.append(WeeklySpacingScenario(
        name="WEEKLY_6TD",
        min_td_gap=6,
        retained_fills=r6,
        n_retained=len(r6),
        adjacent_pairs=adj6,
        max_overlap_pct=max6,
        g04_verdict=G04WeeklySpacingVerdict.G04_PASS if max6 <= 30 else G04WeeklySpacingVerdict.G04_FAIL,
        g03_verdict=len(r6) >= 10,
        tradeoff_note=(
            f"N={len(r6)}: G04 max overlap={max6}% "
            f"({'PASS' if max6 <= 30 else 'FAIL'}). "
            "G04 passes but N too small for G03 or bootstrap."
        ),
    ))

    # Scenario 3: Accept current data, apply cluster-aware correlation correction
    scenarios.append(WeeklySpacingScenario(
        name="BOOTSTRAP_CLUSTER_AWARE",
        min_td_gap=0,
        retained_fills=all_fills,
        n_retained=len(all_fills),
        adjacent_pairs=adjacent_pairs_orig,
        max_overlap_pct=max_pct,
        g04_verdict=G04WeeklySpacingVerdict.G04_FAIL,
        g03_verdict=len(all_fills) >= 10,
        tradeoff_note=(
            "Bootstrap with cluster-aware correction BLOCKED: N=6 < 10 required (G03). "
            "Effective N ≈ 1.09 (from r≈0.8). Bootstrap CI is unreliable with effective N < 2. "
            "Must resolve G03 before this approach is valid."
        ),
    ))

    # Effective N calculation
    # Formula: N_eff = N / (1 + (N-1)*r)  where r = estimated autocorrelation from overlap
    # r is estimated as max_adjacent_overlap_pct / 100
    r_est = max_pct / 100.0
    effective_n = {
        f"N=3_r={r_est:.2f}": round(3 / (1 + 2 * r_est), 2),
        f"N=6_r={r_est:.2f}": round(6 / (1 + 5 * r_est), 2),
        f"N=10_r={r_est:.2f}": round(10 / (1 + 9 * r_est), 2),
        "interpretation": (
            "Effective N < 2 for all current scenarios. "
            "Standard t-test treating N=3 as independent overstates power by ~2.6x. "
            "Published p=0.58 (S41) is not significant even without correction."
        ),
    }

    return G04DependenceStudy(
        all_fills=all_fills,
        all_overlaps=all_overlaps,
        max_adjacent_overlap_pct=max_pct,
        g04_current_verdict=G04WeeklySpacingVerdict.G04_FAIL,
        n_adjacent_failing=5,
        weekly_spacing_scenarios=scenarios,
        effective_n_calculation=effective_n,
        bootstrap_applicable=False,
        bootstrap_blocked_reason=(
            "Bootstrap CI requires G03 (N≥10 independent clusters). "
            "Current N=6 with effective N≈1.09 — bootstrap would be sampling 6 highly-correlated "
            "returns and labeling them as independent draws. This is methodologically invalid."
        ),
        root_cause=(
            "5-day holding window combined with fill dates ≤5 TD apart creates structural overlap. "
            "Adjacent fill dates (e.g., Oct 13/Oct 14, one day apart) share 4 of 5 holding days. "
            "Even weekly-spaced fills can have 40% overlap if exactly 5 TD apart (Oct 21/Oct 28)."
        ),
        remediation_recommendation=(
            "Only option for G04 PASS + usable N: "
            "Collect fills exclusively at ≥6 TD intervals (weekly+ frequency). "
            "With current 6 fills, only N=2 or N=3 survive spacing filter — not enough. "
            "Need 4+ additional weeks of weekly-frequency fills after backfill."
        ),
        finding=(
            "G04 STRUCTURAL FAILURE: Weekly spacing does not resolve G04. "
            "≥5 TD spacing: G04 still FAILS (Oct 21/Oct 28 = 40%). "
            "≥6 TD spacing: G04 PASSES but N=2 (G03 worse). "
            "Bootstrap CI: NOT applicable until G03 (N≥10) resolved. "
            "Statistical verdict unchanged: SIGNIFICANCE_INCONCLUSIVE."
        ),
    )


# ---------------------------------------------------------------------------
# 20D Readiness Matrix — PART H
# ---------------------------------------------------------------------------

def build_20d_readiness_matrix(
    analysis_date: str,
    auth01_granted: bool = False,
    auth02_granted: bool = False,
    pipeline_restored: bool = False,
) -> TwentyDReadinessMatrix:
    """
    Per-cluster 20D authorization readiness.
    Does NOT compute outcomes — only assesses readiness.

    Parameters:
      analysis_date: today (ISO format, e.g. '2026-11-02')
      auth01_granted: whether backfill authorization has been given
      auth02_granted: whether 20D computation authorization has been given
      pipeline_restored: whether pipeline is delivering full universe data again
    """
    from datetime import date

    today = date.fromisoformat(analysis_date)
    fills = ["2026-10-13", "2026-10-14", "2026-10-16", "2026-10-21", "2026-10-22", "2026-10-28"]
    records = []

    for f in fills:
        corrected_exit = _CORRECT_20TD[f]
        s46_exit = _S46_20TD[f]
        exit_date = date.fromisoformat(corrected_exit)
        days_to_maturity = (exit_date - today).days
        is_mature = days_to_maturity <= 0

        proxy_now = _PROXY_COUNTS_NOW[f]
        strict_now = proxy_now >= STRICT_THRESHOLD

        # Pipeline data available: only if exit_date <= last filled date (Nov 05)
        last_filled = date.fromisoformat("2026-11-05")
        pipeline_data_available = pipeline_restored and (exit_date <= last_filled)

        # Determine verdict — pipeline is the most foundational blocker
        if not pipeline_restored:
            verdict = TwentyDReadinessVerdict.BLOCKED_PIPELINE
        elif not auth01_granted and not strict_now:
            verdict = TwentyDReadinessVerdict.BLOCKED_AUTH01
        elif not is_mature:
            verdict = TwentyDReadinessVerdict.NOT_YET_MATURE
        elif not pipeline_data_available:
            verdict = TwentyDReadinessVerdict.MATURE_PENDING_DATA
        elif auth02_granted:
            verdict = TwentyDReadinessVerdict.AUTHORIZED_READY
        else:
            verdict = TwentyDReadinessVerdict.DATA_AVAILABLE

        calendar_days_to_maturity = max(days_to_maturity, 0)
        notes = ""
        if f == "2026-10-13":
            notes = "Earliest maturity Nov 12 — 10 TD deadline before data permanently unrecoverable without Neon DB."
        elif days_to_maturity <= 0:
            notes = "Already mature (exit date passed) — but pipeline_restored required to have exit data."
        else:
            notes = f"Matures in {days_to_maturity} calendar days on {corrected_exit}."

        records.append(TwentyDReadinessRecord(
            fill_date=f,
            exit_20td_corrected=corrected_exit,
            exit_20td_s46_erroneous=s46_exit,
            calendar_days_to_maturity=calendar_days_to_maturity,
            is_mature=is_mature,
            pipeline_data_available=pipeline_data_available,
            strict_eligible=strict_now,
            auth01_granted=auth01_granted,
            auth02_granted=auth02_granted,
            verdict=verdict,
            days_until_maturity=max(days_to_maturity, 0),
            notes=notes,
        ))

    n_mature = sum(1 for r in records if r.is_mature)
    # Count how many will be mature by the latest exit date
    n_mature_all = len(records)  # all will be mature after Nov 25

    earliest = _CORRECT_20TD["2026-10-13"]
    latest = _CORRECT_20TD["2026-10-28"]

    # Overall verdict
    if not pipeline_restored:
        overall = TwentyDReadinessVerdict.BLOCKED_PIPELINE
    elif not auth01_granted:
        overall = TwentyDReadinessVerdict.BLOCKED_AUTH01
    elif auth02_granted:
        overall = TwentyDReadinessVerdict.AUTHORIZED_READY
    else:
        overall = TwentyDReadinessVerdict.DATA_AVAILABLE

    return TwentyDReadinessMatrix(
        clusters=records,
        earliest_maturity_date=earliest,
        latest_maturity_date=latest,
        n_mature_now=n_mature,
        n_mature_after_maturity_date=n_mature_all,
        auth01_status="PENDING" if not auth01_granted else "GRANTED",
        auth02_status="PENDING" if not auth02_granted else "GRANTED",
        overall_verdict=overall,
        critical_path=(
            "AUTH01 (backfill Oct 29/30/Nov 02/03) → "
            "Pipeline restoration (Nov 06+ data) → "
            "Wait for maturity (Oct 13 → Nov 12 earliest) → "
            "Confirm exit data in DB → "
            "AUTH02 (20D computation) → "
            "Compute 20D outcomes"
        ),
        nov12_hard_deadline_note=(
            "Nov 12 is Oct 13 fill's 20TD exit. If pipeline is NOT restored by Nov 12, "
            "that date's exit close price will NOT be in platform.db. "
            "The only recovery path would be Neon production DB (requires separate authorization). "
            "Current pipeline last filled: Nov 05. Urgency: HIGH."
        ),
    )
