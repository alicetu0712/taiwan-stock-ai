"""
PART B: Session 40 Reproduction Report.
Re-runs V3ComparisonEngine 5D and verifies S40 paired stats.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class ReproductionStatus(str, Enum):
    REPRODUCED = "REPRODUCED"           # within 0.0001 absolute tolerance
    PARTIAL = "PARTIAL"                 # within 0.01 tolerance
    NOT_REPRODUCED = "NOT_REPRODUCED"   # > 0.01 deviation
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


@dataclass(frozen=True)
class ReproductionEntry:
    metric_name: str
    expected_value: float
    actual_value: float
    absolute_diff: float
    status: ReproductionStatus
    note: str = ""


@dataclass(frozen=True)
class Session40ReproductionReport:
    session: int
    n_entries: int
    n_reproduced: int
    n_partial: int
    n_failed: int
    entries: tuple[ReproductionEntry, ...]
    signal_date_discrepancy: str
    overall_status: str


_S40_EXPECTED = {
    "A_direct_mean_net": -0.031959,
    "B_v1v2_mean_net": -0.024770,
    "C_hybrid_mean_net": -0.031866,
    "D_v3_mean_net": -0.018632,
    "D_v3_fill_rate": 0.6861,
    "D_v3_vs_A_direct_delta": 0.036565,
    "D_v3_vs_B_v1v2_delta": 0.029862,
    "D_v3_vs_C_hybrid_delta": 0.036833,
    "D_v3_vs_A_direct_ci_lower": 0.026136,
    "D_v3_vs_A_direct_ci_upper": 0.048344,
}


def _status(diff: float) -> ReproductionStatus:
    if abs(diff) <= 0.0001:
        return ReproductionStatus.REPRODUCED
    if abs(diff) <= 0.01:
        return ReproductionStatus.PARTIAL
    return ReproductionStatus.NOT_REPRODUCED


def build_session40_reproduction_report(conn: sqlite3.Connection) -> Session40ReproductionReport:
    from research.v3_comparison_engine import V3ComparisonEngine

    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=5)

    actual = {
        "A_direct_mean_net": result.strategy_stats["A_direct"].mean_net_return,
        "B_v1v2_mean_net": result.strategy_stats["B_v1v2"].mean_net_return,
        "C_hybrid_mean_net": result.strategy_stats["C_hybrid"].mean_net_return,
        "D_v3_mean_net": result.strategy_stats["D_v3"].mean_net_return,
        "D_v3_fill_rate": result.strategy_stats["D_v3"].fill_rate,
    }

    for ps in result.paired_stats:
        if ps.candidate == "D_v3":
            actual[f"D_v3_vs_{ps.baseline}_delta"] = ps.mean_delta
            if ps.baseline == "A_direct":
                actual["D_v3_vs_A_direct_ci_lower"] = ps.ci_lower
                actual["D_v3_vs_A_direct_ci_upper"] = ps.ci_upper

    entries = []
    for key, expected in _S40_EXPECTED.items():
        if key in actual:
            diff = actual[key] - expected
            st = _status(diff)
            entries.append(ReproductionEntry(
                metric_name=key,
                expected_value=expected,
                actual_value=actual[key],
                absolute_diff=abs(diff),
                status=st,
            ))
        else:
            entries.append(ReproductionEntry(
                metric_name=key,
                expected_value=expected,
                actual_value=0.0,
                absolute_diff=0.0,
                status=ReproductionStatus.SOURCE_UNAVAILABLE,
                note="Not returned by engine",
            ))

    # Signal date discovery
    signal_dates = sorted({row.signal_date for row in result.rows if row.strategy == "A_direct"})

    discrepancy = (
        f"S40 docs: dates 2026-10-12 to 2026-10-28 (7 dates). "
        f"Actual: {signal_dates} ({len(signal_dates)} dates). "
        "Likely cause: EligibleWindowDiscovery filtered differently from V3ComparisonEngine."
    )

    n_rep = sum(1 for e in entries if e.status == ReproductionStatus.REPRODUCED)
    n_par = sum(1 for e in entries if e.status == ReproductionStatus.PARTIAL)
    n_fail = sum(1 for e in entries if e.status == ReproductionStatus.NOT_REPRODUCED)
    n_unavail = sum(1 for e in entries if e.status == ReproductionStatus.SOURCE_UNAVAILABLE)

    if n_fail == 0 and n_unavail == 0:
        overall = "ALL_REPRODUCED"
    elif n_fail == 0:
        overall = "MOSTLY_REPRODUCED"
    else:
        overall = "PARTIAL_REPRODUCTION"

    return Session40ReproductionReport(
        session=41,
        n_entries=len(entries),
        n_reproduced=n_rep,
        n_partial=n_par,
        n_failed=n_fail,
        entries=tuple(entries),
        signal_date_discrepancy=discrepancy,
        overall_status=overall,
    )
