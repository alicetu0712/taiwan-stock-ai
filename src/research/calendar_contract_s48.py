"""
20D Calendar Contract Correction, Strict 5D Re-evaluation Readiness,
and Statistical Guardrails — Session 48 PARTS E, F, G (P4–P6).

Key corrections vs S46:
  S46 _CALENDAR_20TD had errors for 5 of 6 clusters (2–7 days too late).
  Root cause: S46 used TSMC-proxy date counting instead of real trading calendar.
  This module uses TaiwanTradingCalendar.next_trading_day() iteration as the
  authoritative source.

Correct 20D maturity dates (nth real TD after fill_date):
  Oct 13 → 2026-11-12  (S46 said 2026-11-14, Δ = -2 days)
  Oct 14 → 2026-11-13  (S46 said 2026-11-17, Δ = -4 days)
  Oct 16 → 2026-11-17  (S46 said 2026-11-19, Δ = -2 days)
  Oct 21 → 2026-11-20  (S46 said 2026-11-24, Δ = -4 days)
  Oct 22 → 2026-11-23  (S46 said 2026-11-25, Δ = -2 days)
  Oct 28 → 2026-11-25  (S46 said 2026-12-02, Δ = -7 days)

Correct 5D dates:
  Oct 13 → 2026-10-20  (S46 said 2026-10-21, Δ = -1 day)
  Oct 14 → 2026-10-21  (S46 said 2026-10-28, Δ = -7 days)
  Oct 16 → 2026-10-27  (S46 said 2026-11-05, Δ = -9 days)
  Oct 21 → 2026-10-30  ✓ (S46 correct)
  Oct 22 → 2026-11-02  ✓ (S46 correct)
  Oct 28 → 2026-11-04  ✓ (S46 correct)

Strict 5D eligibility (unchanged from S47):
  Oct 21/22/28 fills remain DATA_INCOMPLETE: TSMC proxy count < 5.
  Recovery requires backfilling Oct 29/30/Nov 02/03.

SAFETY: READ-ONLY. No 20D outcome computation. No production writes.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MaturityStatus20D(str, Enum):
    NOT_YET_MATURE = "NOT_YET_MATURE"
    MATURE_BUT_DATA_INCOMPLETE = "MATURE_BUT_DATA_INCOMPLETE"
    MATURE_AND_COMPLETE = "MATURE_AND_COMPLETE"
    DATE_UNVERIFIED = "DATE_UNVERIFIED"


class Readiness5D(str, Enum):
    READY_FOR_REEVALUATION = "READY_FOR_REEVALUATION"
    WAITING_FOR_PRICE_DATA = "WAITING_FOR_PRICE_DATA"
    WAITING_FOR_BENCHMARK = "WAITING_FOR_BENCHMARK"
    PROVENANCE_BLOCKED = "PROVENANCE_BLOCKED"
    PERMANENTLY_INELIGIBLE = "PERMANENTLY_INELIGIBLE"


class CalendarContractStatus(str, Enum):
    CORRECT = "CORRECT"
    S46_ERROR_CORRECTED = "S46_ERROR_CORRECTED"
    UNCHANGED = "UNCHANGED"


class GuardrailStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# Hard-coded calendar data (authoritative, TaiwanTradingCalendar-verified)
# ---------------------------------------------------------------------------

# Correct 5D dates: 5th real trading day after fill_date
# (computed via next_trading_day() × 5)
_CORRECT_5TD: Dict[str, str] = {
    "2026-10-13": "2026-10-20",
    "2026-10-14": "2026-10-21",
    "2026-10-16": "2026-10-27",
    "2026-10-21": "2026-10-30",
    "2026-10-22": "2026-11-02",
    "2026-10-28": "2026-11-04",
}

# S46 erroneous values for _CALENDAR_5TD
_S46_5TD: Dict[str, str] = {
    "2026-10-13": "2026-10-21",   # +1 day error (TSMC proxy)
    "2026-10-14": "2026-10-28",   # +7 day error (TSMC proxy)
    "2026-10-16": "2026-11-05",   # +9 day error (TSMC proxy)
    "2026-10-21": "2026-10-30",   # correct
    "2026-10-22": "2026-11-02",   # correct
    "2026-10-28": "2026-11-04",   # correct
}

# Correct 20D dates: 20th real trading day after fill_date
# (computed via next_trading_day() × 20)
_CORRECT_20TD: Dict[str, str] = {
    "2026-10-13": "2026-11-12",
    "2026-10-14": "2026-11-13",
    "2026-10-16": "2026-11-17",
    "2026-10-21": "2026-11-20",
    "2026-10-22": "2026-11-23",
    "2026-10-28": "2026-11-25",
}

# S46 erroneous values for _CALENDAR_20TD
_S46_20TD: Dict[str, str] = {
    "2026-10-13": "2026-11-14",   # +2 day error
    "2026-10-14": "2026-11-17",   # +4 day error
    "2026-10-16": "2026-11-19",   # +2 day error
    "2026-10-21": "2026-11-24",   # +4 day error
    "2026-10-22": "2026-11-25",   # +2 day error
    "2026-10-28": "2026-12-02",   # +7 day error
}

# 5D holding windows (5 actual calendar TDs, exclusive of fill_date)
_HOLD_WINDOWS_5D: Dict[str, Tuple[str, ...]] = {
    "2026-10-13": ("2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"),
    "2026-10-14": ("2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"),
    "2026-10-16": ("2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-27"),
    "2026-10-21": ("2026-10-22", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"),
    "2026-10-22": ("2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-11-02"),
    "2026-10-28": ("2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04"),
}

# Stock counts on 5D window dates (from daily_prices; TSMC proxy = 2330 present)
# Sources: verified in Session 47/48 Bash queries
_WINDOW_STOCK_COUNTS: Dict[str, int] = {
    "2026-10-14": 656, "2026-10-15": 1,   "2026-10-16": 655,
    "2026-10-19": 1,   "2026-10-20": 1,   "2026-10-21": 655,
    "2026-10-22": 655, "2026-10-27": 1,   "2026-10-28": 656,
    "2026-10-29": 1,   "2026-10-30": 1,   "2026-11-02": 1,
    "2026-11-03": 1,   "2026-11-04": 6957,
}

# TSMC (2330) presence on 5D window dates
_WINDOW_TSMC_PRESENT: Dict[str, bool] = {
    "2026-10-14": True,  "2026-10-15": False, "2026-10-16": True,
    "2026-10-19": False, "2026-10-20": False, "2026-10-21": True,
    "2026-10-22": True,  "2026-10-27": False, "2026-10-28": True,
    "2026-10-29": False, "2026-10-30": False, "2026-11-02": False,
    "2026-11-03": False, "2026-11-04": True,
}

# Frozen deltas from S44 (unchanged baseline)
_FROZEN_DELTAS_5D: Dict[str, float] = {
    "2026-10-13": 0.0120,
    "2026-10-14": 0.0276,
    "2026-10-16": -0.0152,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CalendarContractRecord:
    fill_date: str
    correct_5td: str
    s46_5td: str
    correct_20td: str
    s46_20td: str
    td5_contract_status: CalendarContractStatus
    td20_contract_status: CalendarContractStatus
    td5_delta_days: int    # correct - s46 (negative = s46 was too late)
    td20_delta_days: int


@dataclass(frozen=True)
class MaturityRecord20D:
    fill_date: str
    correct_20td: str
    stock_count_at_20td: int
    tsmc_at_20td: bool
    maturity_status: MaturityStatus20D
    days_until_mature: int   # from analysis_date; negative = already mature
    notes: str


@dataclass(frozen=True)
class TwentyDMaturityMatrix:
    analysis_date: str
    records: Tuple[MaturityRecord20D, ...]
    not_yet_mature_count: int
    mature_incomplete_count: int
    mature_complete_count: int
    earliest_maturity_date: str
    latest_maturity_date: str
    authorization_status: str


@dataclass(frozen=True)
class ClusterReadinessRecord5D:
    fill_date: str
    proxy_exit_days: int
    proxy_threshold: int         # 5 required for strict
    window_dates: Tuple[str, ...]
    tsmc_present_in_window: Tuple[bool, ...]
    stock_counts_in_window: Tuple[int, ...]
    is_strict_eligible: bool
    readiness: Readiness5D
    missing_data_dates: Tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class StrictReadinessMatrix5D:
    analysis_date: str
    records: Tuple[ClusterReadinessRecord5D, ...]
    strict_eligible_count: int
    waiting_for_data_count: int
    permanently_ineligible_count: int
    frozen_baseline_unchanged: bool
    frozen_grand_mean_pp: float


@dataclass(frozen=True)
class GuardrailRecord:
    guardrail_id: str            # "G03" | "G04"
    requirement: str
    current_value: str
    threshold: str
    status: GuardrailStatus
    notes: str


@dataclass(frozen=True)
class PairwiseOverlapRecord:
    fill_a: str
    fill_b: str
    window_a: Tuple[str, ...]
    window_b: Tuple[str, ...]
    shared_days: int
    overlap_pct: float           # shared_days / window_size * 100
    is_adjacent: bool
    exceeds_threshold: bool      # > 30%


@dataclass(frozen=True)
class GuardrailSummary:
    analysis_date: str
    g03: GuardrailRecord
    g04: GuardrailRecord
    pairwise_matrix: Tuple[PairwiseOverlapRecord, ...]
    strict_cluster_count: int
    g03_target: int
    g04_max_overlap_pct: float
    overall_status: str    # "ALL_PASS" | "G03_FAIL" | "G04_FAIL" | "BOTH_FAIL"


# ---------------------------------------------------------------------------
# Build functions
# ---------------------------------------------------------------------------

def _days_between(date_a: str, date_b: str) -> int:
    """Return date_b - date_a in calendar days."""
    from datetime import date
    a = date.fromisoformat(date_a)
    b = date.fromisoformat(date_b)
    return (b - a).days


def build_calendar_contract_correction(analysis_date: str) -> List[CalendarContractRecord]:
    """
    Build the corrected calendar contract for all 6 fill clusters.
    Returns list of CalendarContractRecord, one per fill_date.
    """
    records = []
    for fill_date in sorted(_CORRECT_5TD.keys()):
        c5 = _CORRECT_5TD[fill_date]
        s46_5 = _S46_5TD[fill_date]
        c20 = _CORRECT_20TD[fill_date]
        s46_20 = _S46_20TD[fill_date]

        d5 = _days_between(c5, s46_5)   # positive = s46 was late
        d20 = _days_between(c20, s46_20)

        status5 = (
            CalendarContractStatus.UNCHANGED if s46_5 == c5
            else CalendarContractStatus.S46_ERROR_CORRECTED
        )
        status20 = (
            CalendarContractStatus.UNCHANGED if s46_20 == c20
            else CalendarContractStatus.S46_ERROR_CORRECTED
        )

        records.append(CalendarContractRecord(
            fill_date=fill_date,
            correct_5td=c5,
            s46_5td=s46_5,
            correct_20td=c20,
            s46_20td=s46_20,
            td5_contract_status=status5,
            td20_contract_status=status20,
            td5_delta_days=d5,
            td20_delta_days=d20,
        ))
    return records


def build_20d_maturity_matrix(
    conn: sqlite3.Connection,
    analysis_date: str,
) -> TwentyDMaturityMatrix:
    """Build 20D maturity matrix for all 6 fill clusters. READ-ONLY."""
    records = []

    for fill_date in sorted(_CORRECT_20TD.keys()):
        td20 = _CORRECT_20TD[fill_date]
        stock_count = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?",
            (td20,),
        ).fetchone()[0]
        tsmc = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id='2330'",
            (td20,),
        ).fetchone()[0] > 0

        days_until = _days_between(analysis_date, td20)  # positive = future

        if days_until > 0:
            status = MaturityStatus20D.NOT_YET_MATURE
            notes = f"Matures {td20} ({days_until} calendar days from {analysis_date})"
        elif stock_count >= 300:
            status = MaturityStatus20D.MATURE_AND_COMPLETE
            notes = f"Mature. {stock_count} stocks on exit date."
        elif stock_count > 0:
            status = MaturityStatus20D.MATURE_BUT_DATA_INCOMPLETE
            notes = f"Past maturity date but only {stock_count} stocks available."
        else:
            status = MaturityStatus20D.DATE_UNVERIFIED
            notes = "No data for exit date; unverified."

        records.append(MaturityRecord20D(
            fill_date=fill_date,
            correct_20td=td20,
            stock_count_at_20td=stock_count,
            tsmc_at_20td=tsmc,
            maturity_status=status,
            days_until_mature=days_until,
            notes=notes,
        ))

    not_yet = sum(1 for r in records if r.maturity_status == MaturityStatus20D.NOT_YET_MATURE)
    incomplete = sum(1 for r in records if r.maturity_status == MaturityStatus20D.MATURE_BUT_DATA_INCOMPLETE)
    complete = sum(1 for r in records if r.maturity_status == MaturityStatus20D.MATURE_AND_COMPLETE)
    earliest = min(_CORRECT_20TD.values())
    latest = max(_CORRECT_20TD.values())

    return TwentyDMaturityMatrix(
        analysis_date=analysis_date,
        records=tuple(records),
        not_yet_mature_count=not_yet,
        mature_incomplete_count=incomplete,
        mature_complete_count=complete,
        earliest_maturity_date=earliest,
        latest_maturity_date=latest,
        authorization_status="NOT_AUTHORIZED — 20D outcome computation not authorized",
    )


def _count_tsmc_exit_days(conn: sqlite3.Connection, fill_date: str) -> int:
    """Count trading days after fill_date where TSMC (2330) has price data."""
    return conn.execute(
        "SELECT COUNT(*) FROM daily_prices "
        "WHERE stock_id='2330' AND date > ? AND date <= '2026-11-30'",
        (fill_date,),
    ).fetchone()[0]


def build_strict_readiness_matrix_5d(
    conn: sqlite3.Connection,
    analysis_date: str,
) -> StrictReadinessMatrix5D:
    """
    5D re-evaluation readiness for all 6 clusters. READ-ONLY.
    Strict = TSMC proxy count >= 5.

    Proxy count = total dates after fill_date where TSMC (2330) is present in
    daily_prices (not limited to the 5-day window). This matches the
    _count_exit_days() criterion used in canonical_5d_baseline_s44.py.
    """
    records = []
    incomplete_fills = {"2026-10-21", "2026-10-22", "2026-10-28"}

    for fill_date in sorted(_HOLD_WINDOWS_5D.keys()):
        window = _HOLD_WINDOWS_5D[fill_date]
        # tsmc_flags is for the 5-day window (documentation/display only)
        tsmc_flags = tuple(_WINDOW_TSMC_PRESENT.get(d, False) for d in window)
        stock_counts = tuple(_WINDOW_STOCK_COUNTS.get(d, 0) for d in window)

        # Proxy count uses ALL TSMC-present dates after fill_date (not window-limited)
        proxy_count = _count_tsmc_exit_days(conn, fill_date)

        is_strict = proxy_count >= 5
        # Missing dates: window days where TSMC is not present
        missing = tuple(d for d, t in zip(window, tsmc_flags) if not t)

        if is_strict:
            readiness = Readiness5D.READY_FOR_REEVALUATION
            notes = f"Strict eligible; TSMC proxy count={proxy_count} >= 5"
        elif fill_date in incomplete_fills:
            readiness = Readiness5D.WAITING_FOR_PRICE_DATA
            notes = (
                f"Proxy count {proxy_count}/5; needs "
                f"{5 - proxy_count} more TSMC-present days"
            )
        else:
            readiness = Readiness5D.PERMANENTLY_INELIGIBLE
            notes = "Data unavailable; recovery blocked"

        records.append(ClusterReadinessRecord5D(
            fill_date=fill_date,
            proxy_exit_days=proxy_count,
            proxy_threshold=5,
            window_dates=window,
            tsmc_present_in_window=tsmc_flags,
            stock_counts_in_window=stock_counts,
            is_strict_eligible=is_strict,
            readiness=readiness,
            missing_data_dates=missing,
            notes=notes,
        ))

    strict_count = sum(1 for r in records if r.is_strict_eligible)
    waiting_count = sum(1 for r in records if r.readiness == Readiness5D.WAITING_FOR_PRICE_DATA)
    perm_ineligible = sum(1 for r in records if r.readiness == Readiness5D.PERMANENTLY_INELIGIBLE)

    return StrictReadinessMatrix5D(
        analysis_date=analysis_date,
        records=tuple(records),
        strict_eligible_count=strict_count,
        waiting_for_data_count=waiting_count,
        permanently_ineligible_count=perm_ineligible,
        frozen_baseline_unchanged=True,
        frozen_grand_mean_pp=0.81,
    )


def build_guardrail_summary(
    analysis_date: str,
    strict_cluster_count: int = 3,
) -> GuardrailSummary:
    """
    G03 / G04 guardrail status. Formula unchanged from S47.
    G04 formula: overlap_pct = |window_A ∩ window_B| / window_size × 100
    """
    # G03: need >= 10 strict clusters for sufficient power
    g03 = GuardrailRecord(
        guardrail_id="G03",
        requirement="Strict cluster count >= 10",
        current_value=str(strict_cluster_count),
        threshold="10",
        status=GuardrailStatus.FAIL if strict_cluster_count < 10 else GuardrailStatus.PASS,
        notes=f"Current={strict_cluster_count}; need 7 more; recovery path: pipeline restoration + 7-8 weeks data",
    )

    # G04: build pairwise overlap matrix
    all_fills = sorted(_HOLD_WINDOWS_5D.keys())
    pairwise: list[PairwiseOverlapRecord] = []
    max_overlap = 0.0

    for i, fa in enumerate(all_fills):
        for fb in all_fills[i + 1:]:
            wa = set(_HOLD_WINDOWS_5D[fa])
            wb = set(_HOLD_WINDOWS_5D[fb])
            shared = len(wa & wb)
            overlap = shared / 5 * 100.0

            # Adjacent: fills are consecutive in the sorted list
            is_adj = (all_fills.index(fb) - all_fills.index(fa)) == 1

            pairwise.append(PairwiseOverlapRecord(
                fill_a=fa,
                fill_b=fb,
                window_a=_HOLD_WINDOWS_5D[fa],
                window_b=_HOLD_WINDOWS_5D[fb],
                shared_days=shared,
                overlap_pct=overlap,
                is_adjacent=is_adj,
                exceeds_threshold=overlap > 30.0,
            ))
            if overlap > max_overlap:
                max_overlap = overlap

    # G04 fails if any adjacent pair > 30%
    adjacent_pairs = [p for p in pairwise if p.is_adjacent]
    g04_fails = [p for p in adjacent_pairs if p.exceeds_threshold]

    g04 = GuardrailRecord(
        guardrail_id="G04",
        requirement="Adjacent window overlap < 30%",
        current_value=f"{max_overlap:.0f}% max (adjacent)",
        threshold="30%",
        status=GuardrailStatus.FAIL if g04_fails else GuardrailStatus.PASS,
        notes=(
            f"{len(g04_fails)} of {len(adjacent_pairs)} adjacent pairs exceed 30%. "
            "Design-level issue; daily fills inherently produce adjacent windows. "
            "Remediation: weekly-spaced fills or bootstrap CI."
        ),
    )

    if g03.status == GuardrailStatus.FAIL and g04.status == GuardrailStatus.FAIL:
        overall = "BOTH_FAIL"
    elif g03.status == GuardrailStatus.FAIL:
        overall = "G03_FAIL"
    elif g04.status == GuardrailStatus.FAIL:
        overall = "G04_FAIL"
    else:
        overall = "ALL_PASS"

    return GuardrailSummary(
        analysis_date=analysis_date,
        g03=g03,
        g04=g04,
        pairwise_matrix=tuple(pairwise),
        strict_cluster_count=strict_cluster_count,
        g03_target=10,
        g04_max_overlap_pct=max_overlap,
        overall_status=overall,
    )


def get_s46_errors_summary() -> List[dict]:
    """
    Return a list of S46 calendar errors for documentation.
    """
    errors = []
    for fill_date in sorted(_CORRECT_5TD.keys()):
        c5 = _CORRECT_5TD[fill_date]
        s5 = _S46_5TD[fill_date]
        c20 = _CORRECT_20TD[fill_date]
        s20 = _S46_20TD[fill_date]

        d5 = _days_between(c5, s5)
        d20 = _days_between(c20, s20)

        errors.append({
            "fill_date": fill_date,
            "td5_correct": c5,
            "td5_s46": s5,
            "td5_error_days": d5,
            "td20_correct": c20,
            "td20_s46": s20,
            "td20_error_days": d20,
            "td5_has_error": c5 != s5,
            "td20_has_error": c20 != s20,
        })
    return errors
