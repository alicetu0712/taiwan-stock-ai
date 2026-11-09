"""
PART F: Comparable Evidence Expansion Auditor — Session 43.

Searches for additional historical comparison windows in existing artifacts.

Verdict: NO_NEW_ELIGIBLE_WINDOW

Reasons:
1. forward_signals only contains October 2026 data (cron started ~Oct 2026)
2. stock_research.db exists but has no forward signal tables
3. No pre-October 2026 signal artifacts found
4. backtest artifacts use simulated/retrospective signals, not prospective
5. Data gap in Oct-Nov 2026 (Oct 23-Nov 03 sparse) limits 5D window completion
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class WindowEligibilityVerdict(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    CONDITIONAL = "CONDITIONAL"
    INELIGIBLE = "INELIGIBLE"


class IneligibilityReason(str, Enum):
    NO_SIGNAL_DATA = "NO_SIGNAL_DATA"
    RETROSPECTIVE_SIGNALS = "RETROSPECTIVE_SIGNALS"
    INCOMPLETE_PRICE_DATA = "INCOMPLETE_PRICE_DATA"
    MODEL_VERSION_MISMATCH = "MODEL_VERSION_MISMATCH"
    INSUFFICIENT_CLUSTERS = "INSUFFICIENT_CLUSTERS"
    OVERLAPPING_WINDOWS = "OVERLAPPING_WINDOWS"
    LOOK_AHEAD_BIAS = "LOOK_AHEAD_BIAS"
    SURVIVORSHIP_BIAS_RISK = "SURVIVORSHIP_BIAS_RISK"
    BENCHMARK_UNAVAILABLE = "BENCHMARK_UNAVAILABLE"


@dataclass(frozen=True)
class CandidateWindow:
    window_id: str
    start_date: str
    end_date: str
    source: str
    n_eligible_signals: int
    n_unique_fill_dates: int
    n_matched_pairs: int
    data_quality_issues: tuple[str, ...]
    eligibility_verdict: WindowEligibilityVerdict
    exclusion_reasons: tuple[IneligibilityReason, ...]
    notes: str


@dataclass(frozen=True)
class ArtifactSummary:
    artifact_name: str
    artifact_type: str
    signal_date_range: Optional[tuple[str, str]]
    n_signals: int
    is_prospective: bool
    is_eligible: bool
    notes: str


@dataclass(frozen=True)
class ComparableEvidenceExpansionReport:
    session: int
    artifacts_checked: tuple[ArtifactSummary, ...]
    candidate_windows: tuple[CandidateWindow, ...]
    n_eligible_windows: int
    n_conditional_windows: int
    n_ineligible_windows: int
    new_independent_observations_added: int
    overall_verdict: str
    next_eligible_window_eta: str


def _check_research_db(path: str) -> ArtifactSummary:
    try:
        import sqlite3 as sq
        conn2 = sq.connect(path)
        tables = [r[0] for r in conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if not tables:
            return ArtifactSummary(
                artifact_name=path,
                artifact_type="sqlite",
                signal_date_range=None,
                n_signals=0,
                is_prospective=False,
                is_eligible=False,
                notes="Empty database (no tables)",
            )
        # Check for forward_signals
        if "forward_signals" in tables:
            row = conn2.execute(
                "SELECT MIN(trade_date), MAX(trade_date), COUNT(*) FROM forward_signals "
                "WHERE trade_signal IN ('buy','strong_buy')"
            ).fetchone()
            return ArtifactSummary(
                artifact_name=path,
                artifact_type="sqlite/forward_signals",
                signal_date_range=(row[0], row[1]) if row[0] else None,
                n_signals=row[2],
                is_prospective=True,
                is_eligible=row[2] > 0,
                notes=f"Tables: {tables[:5]}",
            )
        return ArtifactSummary(
            artifact_name=path,
            artifact_type="sqlite",
            signal_date_range=None,
            n_signals=0,
            is_prospective=False,
            is_eligible=False,
            notes=f"No forward_signals. Tables: {tables[:5]}",
        )
    except Exception as e:
        return ArtifactSummary(
            artifact_name=path,
            artifact_type="sqlite/error",
            signal_date_range=None,
            n_signals=0,
            is_prospective=False,
            is_eligible=False,
            notes=f"Error: {e}",
        )


def build_evidence_expansion_report(conn: sqlite3.Connection) -> ComparableEvidenceExpansionReport:
    import os

    # Check all DB files
    artifacts = []

    # 1. Main production DB
    fs_range = conn.execute(
        "SELECT MIN(trade_date), MAX(trade_date), COUNT(*) FROM forward_signals "
        "WHERE trade_signal IN ('buy','strong_buy')"
    ).fetchone()
    artifacts.append(ArtifactSummary(
        artifact_name="data/platform.db",
        artifact_type="production_sqlite",
        signal_date_range=(fs_range[0], fs_range[1]) if fs_range[0] else None,
        n_signals=fs_range[2],
        is_prospective=True,
        is_eligible=True,
        notes=f"Production DB: Oct 2026 only ({fs_range[2]} buy/SB signals)",
    ))

    # 2. Research DB
    for path in ("data/stock_research.db", "stock_research.db"):
        if os.path.exists(path):
            artifacts.append(_check_research_db(path))

    # Build candidate windows
    candidate_windows = []

    # Window 1: Oct 2026 (the existing window - already analyzed in S42)
    candidate_windows.append(CandidateWindow(
        window_id="W001_OCT2026",
        start_date="2026-10-09",
        end_date="2026-10-28",
        source="forward_signals (platform.db)",
        n_eligible_signals=167,  # v8.0 signals only
        n_unique_fill_dates=4,   # Oct 13, 14, 16, 21 (Oct 21 incomplete)
        n_matched_pairs=167,
        data_quality_issues=(
            "v6.0 signals contamination (107 excluded)",
            "fill Oct 21 cluster incomplete (insufficient exit data)",
            "data gap Oct 22-Oct 28 (Oct 23-27 missing)",
        ),
        eligibility_verdict=WindowEligibilityVerdict.CONDITIONAL,
        exclusion_reasons=(IneligibilityReason.INSUFFICIENT_CLUSTERS,),
        notes="Best available window. 3 complete fill clusters after v6.0 exclusion.",
    ))

    # Window 2: Hypothetical pre-Oct 2026 backtest (not available)
    candidate_windows.append(CandidateWindow(
        window_id="W002_PRE_OCT2026_HYPOTHETICAL",
        start_date="N/A",
        end_date="N/A",
        source="None (no pre-Oct 2026 forward_signals exist)",
        n_eligible_signals=0,
        n_unique_fill_dates=0,
        n_matched_pairs=0,
        data_quality_issues=(
            "No prospective forward_signals before Oct 2026",
            "stock_research.db is empty",
            "Any backtest would require retrospective signal reconstruction",
        ),
        eligibility_verdict=WindowEligibilityVerdict.INELIGIBLE,
        exclusion_reasons=(
            IneligibilityReason.NO_SIGNAL_DATA,
            IneligibilityReason.RETROSPECTIVE_SIGNALS,
        ),
        notes=(
            "Retrospective signal reconstruction using historical prices is LOOK_AHEAD_BIAS "
            "risk (parameter tuning on past data). Not eligible for prospective comparison."
        ),
    ))

    # Window 3: Nov-Dec 2026 (future)
    candidate_windows.append(CandidateWindow(
        window_id="W003_NOV_DEC_2026_FUTURE",
        start_date="2026-11-04",
        end_date="2026-12-31",
        source="forward_signals (ongoing cron production)",
        n_eligible_signals=0,  # not yet available as comparison
        n_unique_fill_dates=0,
        n_matched_pairs=0,
        data_quality_issues=(
            "Signals exist from Nov 04 backfill but comparison outcomes not yet mature",
            "daily_prices max = 2026-11-05; most 5D windows not completable",
        ),
        eligibility_verdict=WindowEligibilityVerdict.INELIGIBLE,
        exclusion_reasons=(
            IneligibilityReason.INCOMPLETE_PRICE_DATA,
        ),
        notes=(
            "Will become eligible as cron accumulates signals and daily_prices grows. "
            "ETA: Nov-Dec 2026 for 5D windows; Dec 2026 for 20D windows."
        ),
    ))

    n_elig = sum(1 for w in candidate_windows if w.eligibility_verdict == WindowEligibilityVerdict.ELIGIBLE)
    n_cond = sum(1 for w in candidate_windows if w.eligibility_verdict == WindowEligibilityVerdict.CONDITIONAL)
    n_inelig = sum(1 for w in candidate_windows if w.eligibility_verdict == WindowEligibilityVerdict.INELIGIBLE)

    return ComparableEvidenceExpansionReport(
        session=43,
        artifacts_checked=tuple(artifacts),
        candidate_windows=tuple(candidate_windows),
        n_eligible_windows=n_elig,
        n_conditional_windows=n_cond,
        n_ineligible_windows=n_inelig,
        new_independent_observations_added=0,
        overall_verdict="NO_NEW_ELIGIBLE_WINDOW",
        next_eligible_window_eta=(
            "Nov 2026 (5D) / Dec 2026 (20D) as cron accumulates v8.0 signals"
        ),
    )
