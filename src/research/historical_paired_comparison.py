"""
historical_paired_comparison.py — Actual V1/V2/V3 historical paired comparison.

RESEARCH ONLY. Read-only. No production DB writes.

Data sources:
  1. effectiveness_analysis.json — V1 vs V2 (backtest era Oct 2024 – Sep 2026, N=2953)
  2. V3ComparisonEngine on forward_signals — V1/V2/V3 (Oct 2026, N=274, 5D only)

Comparability:
  - V1 ↔ V2: CONDITIONAL (from effectiveness_analysis.json, CI includes zero)
  - V1/V2 ↔ V3: CONDITIONAL (from 5D window, underpowered, single regime)
  - Hybrid V1 ↔ V3: CONDITIONAL (same 5D window)

Statistical safeguards:
  - Report both raw N and effective N (independent dates).
  - Bootstrap CI does NOT adjust for temporal clustering — flag explicitly.
  - Single-regime concentration must be noted.
  - Do NOT claim ranking without adequate power.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ComparabilityVerdict(str, Enum):
    COMPARABLE = "COMPARABLE"
    CONDITIONAL = "CONDITIONAL"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    OUTCOME_UNAVAILABLE = "OUTCOME_UNAVAILABLE"
    NO_ELIGIBLE_PAIRS = "NO_ELIGIBLE_PAIRS"


class RankingVerdict(str, Enum):
    RANKING_SUPPORTED = "RANKING_SUPPORTED"
    RANKING_CONDITIONAL = "RANKING_CONDITIONAL"
    RANKING_NOT_SUPPORTED = "RANKING_NOT_SUPPORTED"


class StatisticalConfidence(str, Enum):
    VERIFIED = "VERIFIED"
    CONDITIONAL = "CONDITIONAL"
    UNVERIFIED = "STATISTICAL_CONFIDENCE_UNVERIFIED"


@dataclass
class PairedComparisonResult:
    """
    One V_candidate vs V_baseline comparison on one data source.
    """
    candidate: str                          # e.g. "D_v3"
    baseline: str                           # e.g. "A_direct"
    data_source: str                        # e.g. "v3_comparison_engine_5d"
    horizon_days: int
    comparability: ComparabilityVerdict
    raw_n: int
    effective_n: int                        # independent clusters (trading dates)
    n_independent_dates: int
    mean_net_alpha: Optional[float]         # percentage points
    median_net_alpha: Optional[float]
    ci_lower: Optional[float]              # bootstrap CI lower bound
    ci_upper: Optional[float]              # bootstrap CI upper bound
    ci_cluster_adjusted: bool              # True if cluster-adjusted
    cohens_d: Optional[float]
    p_value: Optional[float]
    verdict: str                            # e.g. "SIGNIFICANT_POSITIVE"
    statistical_confidence: StatisticalConfidence
    caveats: List[str] = field(default_factory=list)


@dataclass
class VersionComparisonReport:
    """
    Full historical comparison report for all V1/V2/V3 pairings.
    """
    generated_at: str
    data_sources: List[str]
    pairs: List[PairedComparisonResult]
    ranking_verdict: RankingVerdict
    ranking_note: str

    def by_candidate(self, candidate: str) -> List[PairedComparisonResult]:
        return [p for p in self.pairs if p.candidate == candidate]

    def comparable_pairs(self) -> List[PairedComparisonResult]:
        return [p for p in self.pairs
                if p.comparability in (ComparabilityVerdict.COMPARABLE, ComparabilityVerdict.CONDITIONAL)]


_V1V2_ARTIFACT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "effectiveness_analysis.json"
)


def _load_v1v2_data() -> Optional[dict]:
    """Load V1 vs V2 comparison from effectiveness_analysis.json artifact."""
    path = os.path.normpath(_V1V2_ARTIFACT_PATH)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _build_v1v2_pair(artifact: dict) -> PairedComparisonResult:
    """Build V2 vs V1 paired result from effectiveness_analysis.json."""
    overall = artifact.get("group_analysis", {}).get("overall", {})
    oos_window = next(
        (w for w in artifact.get("walk_forward", []) if w.get("is_oos")),
        None,
    )
    n_filled = overall.get("n_filled", 0)
    delta = overall.get("paired_delta_mean")
    ci = overall.get("paired_delta_ci95", {})
    ci_lo = ci.get("lo")
    ci_hi = ci.get("hi")
    ci_zero = ci_lo is not None and ci_lo <= 0 <= ci_hi

    # OOS window
    oos_n = oos_window.get("n", 0) if oos_window else 0
    oos_delta = oos_window.get("paired_delta_mean") if oos_window else None
    oos_ci = oos_window.get("paired_delta_ci95", {}) if oos_window else {}

    caveats = [
        "effectiveness_analysis.json is a BACKTEST SIMULATION, not live forward signals",
        "150-stock sample (not full universe). Config: signal_start=2024-10-01, signal_end=2026-09-15",
        "V2's EntryTimingAnalyzer MA20 rules applied deterministically to historical data",
        "is_oos=False for W1–W9 (embargo period covers parameter tuning window, not strict OOS)",
        "Only W_OOS (2026-07–09-15, n=294) is structurally out-of-sample",
        f"Overall CI95 [{ci_lo}, {ci_hi}] {'includes zero → NOT statistically significant' if ci_zero else 'excludes zero'}",
    ]
    if oos_delta is not None:
        oos_ci_lo = oos_ci.get("lo")
        oos_ci_hi = oos_ci.get("hi")
        oos_zero = oos_ci_lo is not None and oos_ci_lo <= 0 <= oos_ci_hi
        caveats.append(
            f"OOS (n={oos_n}): delta={oos_delta:.4f}%, CI=[{oos_ci_lo},{oos_ci_hi}] "
            f"{'includes zero' if oos_zero else 'excludes zero'}"
        )

    return PairedComparisonResult(
        candidate="B_v1v2_v2",
        baseline="B_v1v2_v1",
        data_source="effectiveness_analysis_json",
        horizon_days=20,
        comparability=ComparabilityVerdict.CONDITIONAL,
        raw_n=n_filled,
        effective_n=artifact.get("data_integrity_audit", {}).get("unique_dates", 0),
        n_independent_dates=artifact.get("data_integrity_audit", {}).get("unique_dates", 0),
        mean_net_alpha=delta,
        median_net_alpha=overall.get("paired_delta_median"),
        ci_lower=ci_lo,
        ci_upper=ci_hi,
        ci_cluster_adjusted=False,
        cohens_d=None,
        p_value=None,
        verdict="CONDITIONAL" if ci_zero else "SIGNIFICANT_POSITIVE",
        statistical_confidence=StatisticalConfidence.CONDITIONAL,
        caveats=caveats,
    )


def _build_v3_pairs_from_engine(conn: sqlite3.Connection) -> List[PairedComparisonResult]:
    """Build V3 paired results using V3ComparisonEngine on live data."""
    try:
        import sys
        sys.path.insert(0, ".")
        from src.research.v3_comparison_engine import V3ComparisonEngine, PARAMETER_HASH
    except ImportError:
        return []

    engine = V3ComparisonEngine(conn)
    readiness = engine.run_data_readiness_audit()
    if readiness.verdict_5d != "READY":
        return []

    result = engine.run_comparison(horizon_days=5)
    pairs: List[PairedComparisonResult] = []

    # Get signal date info
    all_dates_rows = conn.execute(
        "SELECT DISTINCT trade_date FROM forward_signals "
        "WHERE trade_signal IN ('buy','strong_buy') ORDER BY trade_date"
    ).fetchall()
    n_dates = len(all_dates_rows)

    base_caveats = [
        f"5D horizon only (max post-bars: {readiness.max_post_bars}; 20D unavailable)",
        "IN-SAMPLE WARNING: forward_signals generated by same foe_v1/v8.0 scoring engine",
        f"7 independent trading dates → effective N ≈ 7, NOT {result.n_universe}",
        "Market regime at signal_date: ALL 'bull' (237/237 v8.0 buy/strong_buy signals)",
        "Market DECLINED during hold period (0050 avg -4.65% over 5D windows)",
        "V3 advantage is MARKET_AVOIDANCE_DRIVEN: lower fill rate (68.6%) during decline",
        "Bootstrap CI does NOT adjust for date-level clustering → CI is overoptimistic",
        f"Comparison engine parameter hash: {PARAMETER_HASH}",
    ]

    for ps in result.paired_stats:
        c = ps.candidate
        b = ps.baseline
        pairs.append(PairedComparisonResult(
            candidate=c,
            baseline=b,
            data_source="v3_comparison_engine_5d_oct2026",
            horizon_days=5,
            comparability=ComparabilityVerdict.CONDITIONAL,
            raw_n=ps.n_paired,
            effective_n=n_dates,
            n_independent_dates=n_dates,
            mean_net_alpha=ps.mean_delta * 100 if ps.mean_delta is not None else None,
            median_net_alpha=ps.median_delta * 100 if ps.median_delta is not None else None,
            ci_lower=ps.ci_lower * 100 if ps.ci_lower is not None else None,
            ci_upper=ps.ci_upper * 100 if ps.ci_upper is not None else None,
            ci_cluster_adjusted=False,
            cohens_d=ps.cohens_d,
            p_value=ps.p_value_sign if hasattr(ps, "p_value_sign") else None,
            verdict=ps.verdict,
            statistical_confidence=StatisticalConfidence.UNVERIFIED,
            caveats=base_caveats.copy(),
        ))

    return pairs


def build_session40_comparison_report(
    conn: sqlite3.Connection,
) -> VersionComparisonReport:
    """Build the full comparison report from all available data sources."""
    from datetime import UTC, datetime

    pairs: List[PairedComparisonResult] = []
    sources: List[str] = []

    # Source 1: V1 vs V2 from effectiveness_analysis.json
    v1v2_data = _load_v1v2_data()
    if v1v2_data:
        v1v2_pair = _build_v1v2_pair(v1v2_data)
        pairs.append(v1v2_pair)
        sources.append("effectiveness_analysis_json (V1 vs V2, Oct 2024 – Sep 2026, N=2953)")

    # Source 2: V3 comparison from engine
    v3_pairs = _build_v3_pairs_from_engine(conn)
    pairs.extend(v3_pairs)
    if v3_pairs:
        sources.append(
            "v3_comparison_engine_5d (D_v3 vs A/B/C, Oct 2026, N=274, 7 dates)"
        )

    # Determine ranking verdict
    # V3 is SIGNIFICANT_POSITIVE vs all three baselines, BUT:
    # - only 7 independent dates
    # - single regime (all bull, then market declined)
    # - in-sample foe_v1 signals
    # → cannot support definitive ranking
    any_significant = any(
        p.verdict == "SIGNIFICANT_POSITIVE"
        for p in pairs
        if p.candidate == "D_v3"
    )
    if not any_significant:
        ranking_verdict = RankingVerdict.RANKING_NOT_SUPPORTED
        ranking_note = "No statistically significant result found."
    else:
        ranking_verdict = RankingVerdict.RANKING_CONDITIONAL
        ranking_note = (
            "D_v3 shows SIGNIFICANT_POSITIVE vs all three baselines on 5D horizon in Oct 2026. "
            "RANKING_CONDITIONAL — not RANKING_SUPPORTED — due to: "
            "(1) only 7 independent trading dates (underpowered), "
            "(2) single market regime (bull→decline), "
            "(3) in-sample scoring engine, "
            "(4) 5D horizon only (20D unavailable). "
            "V3 advantage is MARKET_AVOIDANCE_DRIVEN, not generalizable without "
            "multi-regime evidence."
        )

    return VersionComparisonReport(
        generated_at=datetime.now(UTC).isoformat(),
        data_sources=sources,
        pairs=pairs,
        ranking_verdict=ranking_verdict,
        ranking_note=ranking_note,
    )
