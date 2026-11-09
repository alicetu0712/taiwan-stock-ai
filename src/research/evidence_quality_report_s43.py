"""
PART I: Execution-Date Evidence Quality Report — Session 43.

Rates the overall evidence quality across 10 dimensions, incorporating
S43 findings from Parts B-H.

Each dimension is scored 0-10:
  0-3: Critically weak
  4-6: Conditional
  7-9: Adequate
  10:  Strong

Overall score translates to an activation readiness verdict.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class QualityDimension(str, Enum):
    EXECUTION_INTEGRITY = "EXECUTION_INTEGRITY"
    SIGNAL_PROVENANCE = "SIGNAL_PROVENANCE"
    CALENDAR_ACCURACY = "CALENDAR_ACCURACY"
    SAMPLE_COMPLETENESS = "SAMPLE_COMPLETENESS"
    STATISTICAL_POWER = "STATISTICAL_POWER"
    WINDOW_INDEPENDENCE = "WINDOW_INDEPENDENCE"
    BENCHMARK_ALIGNMENT = "BENCHMARK_ALIGNMENT"
    MODEL_VERSION_PURITY = "MODEL_VERSION_PURITY"
    OUTCOME_MATURITY = "OUTCOME_MATURITY"
    EVIDENCE_EXPANDABILITY = "EVIDENCE_EXPANDABILITY"


class QualityGrade(str, Enum):
    STRONG = "STRONG"
    ADEQUATE = "ADEQUATE"
    CONDITIONAL = "CONDITIONAL"
    WEAK = "WEAK"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class QualityDimensionRecord:
    dimension: QualityDimension
    score: float                     # 0-10
    grade: QualityGrade
    s42_score: float | None          # reference from S42
    delta: float | None              # improvement (+) or regression (-)
    key_finding: str
    limiting_factors: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class ExecutionDateEvidenceQualityReport:
    session: int
    evaluation_date: str
    dimension_records: tuple[QualityDimensionRecord, ...]
    # Aggregates
    mean_score: float
    median_score: float
    n_strong: int
    n_adequate: int
    n_conditional: int
    n_weak: int
    n_critical: int
    # Dimension rankings (by score, descending)
    strongest_dimension: str
    weakest_dimension: str
    # Comparison to S42
    s42_mean_score: float | None
    score_delta: float | None
    # Activation readiness
    activation_eligible: bool
    activation_blockers: tuple[str, ...]
    overall_verdict: str


def _grade(score: float) -> QualityGrade:
    if score >= 8.5:
        return QualityGrade.STRONG
    if score >= 6.5:
        return QualityGrade.ADEQUATE
    if score >= 4.0:
        return QualityGrade.CONDITIONAL
    if score >= 2.0:
        return QualityGrade.WEAK
    return QualityGrade.CRITICAL


_DIMENSION_DATA = [
    QualityDimensionRecord(
        dimension=QualityDimension.EXECUTION_INTEGRITY,
        score=7.5,
        grade=QualityGrade.ADEQUATE,
        s42_score=5.0,
        delta=2.5,
        key_finding=(
            "All execution_date values computed from NEXT_OPEN pipeline, fully documented. "
            "Oct 14→Oct 16 and Oct 16→Oct 21 anomalies explained (thin day skips). "
            "Partial because v6.0 signals have NULL execution_date."
        ),
        limiting_factors=(
            "107 signals (v6.0) have NULL execution_date",
            "No actual broker fills — all SIMULATED_FILL",
        ),
        next_action="Exclude v6.0 signals in strict analysis (done in S43 contract)",
    ),
    QualityDimensionRecord(
        dimension=QualityDimension.SIGNAL_PROVENANCE,
        score=7.0,
        grade=QualityGrade.ADEQUATE,
        s42_score=4.0,
        delta=3.0,
        key_finding=(
            "v6.0 / v8.0 model version distinction established. "
            "locked_at field documents generation time. "
            "Signal dates vs execution dates formally defined."
        ),
        limiting_factors=(
            "trade_date unreliable as actual execution date without calendar validation",
            "v6.0 signals generated on holidays/weekends",
        ),
        next_action="Always filter by model_version='v8.0' for production comparisons",
    ),
    QualityDimensionRecord(
        dimension=QualityDimension.CALENDAR_ACCURACY,
        score=6.0,
        grade=QualityGrade.CONDITIONAL,
        s42_score=3.0,
        delta=3.0,
        key_finding=(
            "Real trading days (≥50 stocks) = 14 dates in Oct-Nov 2026. "
            "Thin days identified. NEXT_OPEN correctly skips thin days. "
            "v8.0-strict pool has 0% non-trading day signals."
        ),
        limiting_factors=(
            "daily_prices calendar source includes thin days when queried by DISTINCT date",
            "Official calendar cross-verification not completed",
        ),
        next_action="Use ≥50-stock threshold for official trading day definition",
    ),
    QualityDimensionRecord(
        dimension=QualityDimension.SAMPLE_COMPLETENESS,
        score=4.5,
        grade=QualityGrade.CONDITIONAL,
        s42_score=4.0,
        delta=0.5,
        key_finding=(
            "v8.0-strict sample: 128 signals across 3 fill dates. "
            "fill Oct 21 excluded (incomplete exit data: only 4 of 5 required days). "
            "Data gap Oct 23-27 affects all clusters."
        ),
        limiting_factors=(
            "Only 3 complete fill clusters",
            "Data gap Oct 23-27 creates sparse exit pricing",
            "fill Oct 21 cluster unusable for 5D analysis",
        ),
        next_action="Wait for Nov 2026+ data accumulation",
    ),
    QualityDimensionRecord(
        dimension=QualityDimension.STATISTICAL_POWER,
        score=2.5,
        grade=QualityGrade.WEAK,
        s42_score=2.0,
        delta=0.5,
        key_finding=(
            "N=3 strict clusters. t-test requires N≥10 for reliable inference. "
            "95% CI for D_v3 vs A_direct: [-1.4%, +3.0%] (strict). "
            "p=0.37 — insufficient evidence to reject null."
        ),
        limiting_factors=(
            "Only 3 independent fill clusters",
            "Window overlap violates independence assumption",
            "No bootstrap or non-parametric validation possible with N=3",
        ),
        next_action="Accumulate 7+ independent fill clusters before retesting",
    ),
    QualityDimensionRecord(
        dimension=QualityDimension.WINDOW_INDEPENDENCE,
        score=2.0,
        grade=QualityGrade.WEAK,
        s42_score=2.0,
        delta=0.0,
        key_finding=(
            "Adjacent fill clusters share 4 out of 5 holding days. "
            "fill Oct 13 and fill Oct 14 overlap 80%. "
            "t-test independence assumption violated."
        ),
        limiting_factors=(
            "Consecutive daily fill dates create near-fully-overlapping 5D windows",
            "Cannot reduce overlap without changing signal generation frequency",
        ),
        next_action="Need 1-week spacing between fill dates to achieve <50% overlap",
    ),
    QualityDimensionRecord(
        dimension=QualityDimension.BENCHMARK_ALIGNMENT,
        score=7.5,
        grade=QualityGrade.ADEQUATE,
        s42_score=4.5,
        delta=3.0,
        key_finding=(
            "0050 benchmark corrected in S42 (CR-B04: wrong dates → correct fill/exit dates). "
            "S43 maintains corrected computation. "
            "Benchmark dates match signal fill dates."
        ),
        limiting_factors=(
            "0050 is market cap weighted index; may not perfectly represent common stock universe",
        ),
        next_action="No change needed; current implementation adequate",
    ),
    QualityDimensionRecord(
        dimension=QualityDimension.MODEL_VERSION_PURITY,
        score=8.0,
        grade=QualityGrade.STRONG,
        s42_score=5.0,
        delta=3.0,
        key_finding=(
            "S43 strict filter: v8.0-only signals confirmed. "
            "v6.0 signals fully excluded from comparison pool. "
            "NonTradingDayAuditor confirms 100% of non-TD signals are v6.0."
        ),
        limiting_factors=(
            "ETF contamination ~0.7% remains (G10 CONDITIONAL)",
        ),
        next_action="Optionally filter ETF stocks when stocks table gains stock_type column",
    ),
    QualityDimensionRecord(
        dimension=QualityDimension.OUTCOME_MATURITY,
        score=3.5,
        grade=QualityGrade.WEAK,
        s42_score=3.0,
        delta=0.5,
        key_finding=(
            "5D windows: 3 complete clusters. fill Oct 21 incomplete. "
            "20D windows: 0 complete clusters (data insufficient). "
            "Earliest 20D completion: ~Nov 25 2026."
        ),
        limiting_factors=(
            "daily_prices max = 2026-11-05; most 20D windows not completable",
            "fill Oct 21 cluster lacks 5th exit day",
        ),
        next_action="Wait for daily_prices to accumulate through Nov 25 2026",
    ),
    QualityDimensionRecord(
        dimension=QualityDimension.EVIDENCE_EXPANDABILITY,
        score=3.0,
        grade=QualityGrade.WEAK,
        s42_score=3.0,
        delta=0.0,
        key_finding=(
            "NO_NEW_ELIGIBLE_WINDOW: forward_signals only has Oct 2026. "
            "stock_research.db is empty. "
            "New evidence requires waiting for cron accumulation."
        ),
        limiting_factors=(
            "No historical signal archives",
            "Retrospective reconstruction would introduce look-ahead bias",
        ),
        next_action="Accumulate Nov-Dec 2026 cron data; re-evaluate Q1 2027",
    ),
]


def build_evidence_quality_report(conn: sqlite3.Connection) -> ExecutionDateEvidenceQualityReport:
    records = tuple(_DIMENSION_DATA)

    scores = [r.score for r in records]
    mean_score = sum(scores) / len(scores)

    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    median_score = (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) / 2 if n % 2 == 0 else sorted_scores[n // 2]

    n_strong = sum(1 for r in records if r.grade == QualityGrade.STRONG)
    n_adequate = sum(1 for r in records if r.grade == QualityGrade.ADEQUATE)
    n_conditional = sum(1 for r in records if r.grade == QualityGrade.CONDITIONAL)
    n_weak = sum(1 for r in records if r.grade == QualityGrade.WEAK)
    n_critical = sum(1 for r in records if r.grade == QualityGrade.CRITICAL)

    sorted_by_score = sorted(records, key=lambda r: r.score, reverse=True)
    strongest = sorted_by_score[0].dimension.value
    weakest = sorted_by_score[-1].dimension.value

    # S42 reference mean
    s42_scores = [r.s42_score for r in records if r.s42_score is not None]
    s42_mean = sum(s42_scores) / len(s42_scores) if s42_scores else None
    delta = mean_score - s42_mean if s42_mean else None

    # Activation eligibility
    activation_blockers = []
    for r in records:
        if r.grade in (QualityGrade.WEAK, QualityGrade.CRITICAL):
            activation_blockers.append(
                f"{r.dimension.value} ({r.score:.1f}/10): {r.limiting_factors[0] if r.limiting_factors else ''}"
            )

    activation_eligible = len(activation_blockers) == 0

    if activation_eligible:
        verdict = "ACTIVATION_ELIGIBLE"
    elif n_critical > 0:
        verdict = "ACTIVATION_BLOCKED_CRITICAL"
    elif n_weak > 2:
        verdict = "ACTIVATION_BLOCKED_INSUFFICIENT"
    else:
        verdict = "ACTIVATION_CONDITIONAL"

    return ExecutionDateEvidenceQualityReport(
        session=43,
        evaluation_date="2026-11-09",
        dimension_records=records,
        mean_score=mean_score,
        median_score=median_score,
        n_strong=n_strong,
        n_adequate=n_adequate,
        n_conditional=n_conditional,
        n_weak=n_weak,
        n_critical=n_critical,
        strongest_dimension=strongest,
        weakest_dimension=weakest,
        s42_mean_score=s42_mean,
        score_delta=delta,
        activation_eligible=activation_eligible,
        activation_blockers=tuple(activation_blockers),
        overall_verdict=verdict,
    )
