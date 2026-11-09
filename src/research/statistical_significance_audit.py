"""
Statistical significance audit for Session 41.

Key finding: 274 forward signals span only 7 trading dates → effective N = 7.
Session 40's bootstrap CI treats signals as independent (N=274), which is incorrect.
Cluster-corrected analysis (grouping by date) shows CI includes zero for all 3 comparisons.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

import numpy as np
from scipy import stats


class SignificanceVerdict(str, Enum):
    SIGNIFICANT_POSITIVE = "SIGNIFICANT_POSITIVE"
    SIGNIFICANT_NEGATIVE = "SIGNIFICANT_NEGATIVE"
    SIGNIFICANCE_INCONCLUSIVE = "SIGNIFICANCE_INCONCLUSIVE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ClusterWarning(str, Enum):
    MICRO_CLUSTER = "MICRO_CLUSTER"       # date with n < 10 signals
    EXTREME_OUTLIER = "EXTREME_OUTLIER"   # date mean > 2 sd from grand mean
    NONE = "NONE"


@dataclass(frozen=True)
class DateClusterStats:
    signal_date: str
    n_signals: int
    mean_delta: float    # D_v3 - baseline for this date
    std_delta: float
    warning: ClusterWarning


@dataclass(frozen=True)
class ClusteredTestResult:
    candidate: str
    baseline: str
    n_clusters: int
    n_signals_total: int
    grand_mean: float
    cluster_std: float
    cluster_se: float
    t_statistic: float
    p_value_ttest: float
    ci_lower_95: float
    ci_upper_95: float
    ci_includes_zero: bool
    n_positive_dates: int
    p_value_sign: float
    uncorrected_verdict: str    # S40 verdict (bootstrap, signal-level)
    corrected_verdict: SignificanceVerdict
    downgraded: bool            # True if corrected ≠ uncorrected
    cluster_details: tuple[DateClusterStats, ...]
    micro_cluster_dates: tuple[str, ...]  # dates with n < 10
    extreme_outlier_dates: tuple[str, ...]


@dataclass(frozen=True)
class LeaveOneDateOutResult:
    comparison: str
    dropped_date: str
    n_remaining_dates: int
    grand_mean: float
    ci_lower: float
    ci_upper: float
    sign_change: bool  # True if sign flips from full analysis


@dataclass(frozen=True)
class SignificanceAuditReport:
    session: int
    comparisons: tuple[ClusteredTestResult, ...]
    lodo_results: tuple[LeaveOneDateOutResult, ...]
    documentation_discrepancy_note: str
    overall_verdict: str
    s40_verdicts_downgraded: int  # how many SIGNIFICANT_POSITIVE downgraded
    effective_n: int
    recommendation: str


def _compute_cluster_stats(
    strat_returns: dict[str, dict[tuple, float]],
    candidate: str,
    baseline: str,
) -> tuple[dict[str, list[float]], dict[str, DateClusterStats]]:
    """Return per-date delta lists and DateClusterStats."""
    date_deltas: dict[str, list[float]] = defaultdict(list)
    for key, cand_ret in strat_returns[candidate].items():
        if key in strat_returns[baseline]:
            base_ret = strat_returns[baseline][key]
            sig_date = key[1]
            date_deltas[sig_date].append(cand_ret - base_ret)

    cluster_stats: dict[str, DateClusterStats] = {}
    grand_mean = np.mean([np.mean(d) for d in date_deltas.values()])
    grand_std = np.std([np.mean(d) for d in date_deltas.values()], ddof=1)

    for dt, deltas in sorted(date_deltas.items()):
        n = len(deltas)
        m = float(np.mean(deltas))
        sd = float(np.std(deltas, ddof=1)) if n > 1 else 0.0

        if n < 10:
            w = ClusterWarning.MICRO_CLUSTER
        elif grand_std > 0 and abs(m - grand_mean) > 2 * grand_std:
            w = ClusterWarning.EXTREME_OUTLIER
        else:
            w = ClusterWarning.NONE

        cluster_stats[dt] = DateClusterStats(
            signal_date=dt,
            n_signals=n,
            mean_delta=m,
            std_delta=sd,
            warning=w,
        )

    return dict(date_deltas), cluster_stats


def _run_clustered_test(
    strat_returns: dict[str, dict[tuple, float]],
    candidate: str,
    baseline: str,
    uncorrected_verdict: str = "SIGNIFICANT_POSITIVE",
) -> ClusteredTestResult:
    date_deltas, cluster_stats = _compute_cluster_stats(strat_returns, candidate, baseline)

    if len(date_deltas) < 2:
        return ClusteredTestResult(
            candidate=candidate, baseline=baseline,
            n_clusters=len(date_deltas), n_signals_total=0,
            grand_mean=0.0, cluster_std=0.0, cluster_se=0.0,
            t_statistic=0.0, p_value_ttest=1.0,
            ci_lower_95=0.0, ci_upper_95=0.0, ci_includes_zero=True,
            n_positive_dates=0, p_value_sign=1.0,
            uncorrected_verdict=uncorrected_verdict,
            corrected_verdict=SignificanceVerdict.INSUFFICIENT_DATA,
            downgraded=True,
            cluster_details=(),
            micro_cluster_dates=(), extreme_outlier_dates=(),
        )

    cluster_means = [float(np.mean(d)) for d in date_deltas.values()]
    n = len(cluster_means)
    grand_mean = float(np.mean(cluster_means))
    cluster_std = float(np.std(cluster_means, ddof=1))
    cluster_se = cluster_std / np.sqrt(n)

    t_stat, p_ttest = stats.ttest_1samp(cluster_means, 0)
    t_crit = float(stats.t.ppf(0.975, df=n - 1))
    ci_lower = grand_mean - t_crit * cluster_se
    ci_upper = grand_mean + t_crit * cluster_se
    ci_includes_zero = ci_lower <= 0.0 <= ci_upper

    n_pos = sum(1 for m in cluster_means if m > 0)
    binom_result = stats.binomtest(n_pos, n, 0.5)
    p_sign = float(binom_result.pvalue)

    if ci_includes_zero:
        corrected = SignificanceVerdict.SIGNIFICANCE_INCONCLUSIVE
    elif grand_mean > 0:
        corrected = SignificanceVerdict.SIGNIFICANT_POSITIVE
    else:
        corrected = SignificanceVerdict.SIGNIFICANT_NEGATIVE

    downgraded = (
        uncorrected_verdict == SignificanceVerdict.SIGNIFICANT_POSITIVE
        and corrected != SignificanceVerdict.SIGNIFICANT_POSITIVE
    )

    micro_dates = tuple(
        cs.signal_date for cs in cluster_stats.values()
        if cs.warning == ClusterWarning.MICRO_CLUSTER
    )
    outlier_dates = tuple(
        cs.signal_date for cs in cluster_stats.values()
        if cs.warning == ClusterWarning.EXTREME_OUTLIER
    )

    total_signals = sum(len(d) for d in date_deltas.values())

    return ClusteredTestResult(
        candidate=candidate, baseline=baseline,
        n_clusters=n, n_signals_total=total_signals,
        grand_mean=grand_mean, cluster_std=cluster_std, cluster_se=cluster_se,
        t_statistic=float(t_stat), p_value_ttest=float(p_ttest),
        ci_lower_95=ci_lower, ci_upper_95=ci_upper, ci_includes_zero=ci_includes_zero,
        n_positive_dates=n_pos, p_value_sign=p_sign,
        uncorrected_verdict=uncorrected_verdict,
        corrected_verdict=corrected,
        downgraded=downgraded,
        cluster_details=tuple(cluster_stats.values()),
        micro_cluster_dates=micro_dates,
        extreme_outlier_dates=outlier_dates,
    )


def _run_lodo(
    strat_returns: dict[str, dict[tuple, float]],
    candidate: str,
    baseline: str,
    full_grand_mean: float,
) -> list[LeaveOneDateOutResult]:
    date_deltas, _ = _compute_cluster_stats(strat_returns, candidate, baseline)
    all_dates = sorted(date_deltas.keys())
    comparison_label = f"{candidate}_vs_{baseline}"
    results = []

    for drop_date in all_dates:
        remaining = [
            float(np.mean(date_deltas[dt]))
            for dt in all_dates
            if dt != drop_date
        ]
        n = len(remaining)
        if n < 2:
            continue
        gm = float(np.mean(remaining))
        se = float(np.std(remaining, ddof=1)) / np.sqrt(n)
        t_crit = float(stats.t.ppf(0.975, df=n - 1))
        ci_lo = gm - t_crit * se
        ci_hi = gm + t_crit * se
        sign_change = (full_grand_mean > 0) != (gm > 0)

        results.append(LeaveOneDateOutResult(
            comparison=comparison_label,
            dropped_date=drop_date,
            n_remaining_dates=n,
            grand_mean=gm,
            ci_lower=ci_lo,
            ci_upper=ci_hi,
            sign_change=sign_change,
        ))

    return results


def build_session41_significance_audit(conn: sqlite3.Connection) -> SignificanceAuditReport:
    from research.v3_comparison_engine import V3ComparisonEngine

    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=5)

    strat_returns: dict[str, dict[tuple, float]] = defaultdict(dict)
    for row in result.rows:
        key = (row.stock_id, row.signal_date)
        strat_returns[row.strategy][key] = row.net_return

    pairs = [
        ("D_v3", "A_direct", "SIGNIFICANT_POSITIVE"),
        ("D_v3", "B_v1v2", "SIGNIFICANT_POSITIVE"),
        ("D_v3", "C_hybrid", "SIGNIFICANT_POSITIVE"),
    ]

    comparisons = []
    lodo_all = []

    for cand, base, s40_verdict in pairs:
        ct = _run_clustered_test(strat_returns, cand, base, s40_verdict)
        comparisons.append(ct)
        lodo_all.extend(_run_lodo(strat_returns, cand, base, ct.grand_mean))

    n_downgraded = sum(1 for c in comparisons if c.downgraded)

    # Determine effective N (count unique signal dates across all strategies)
    all_signal_dates = set()
    for strat in strat_returns.values():
        for _, sig_date in strat.keys():
            all_signal_dates.add(sig_date)
    effective_n = len(all_signal_dates)

    discrepancy_note = (
        "S40 documentation stated signal dates were 2026-10-12 to 2026-10-28 (7 dates). "
        "Actual V3ComparisonEngine used 2026-10-09 to 2026-10-16 (7 dates: 09,10,11,12,13,14,16). "
        "274 = 99+4+4+46+27+55+39 confirms Oct 09-16 set. "
        "0050 returns in S40 doc (-6.09%,...,-10.58%) do NOT match actual (-1.60%,...,-2.14%). "
        "S40 market avoidance attribution numbers require re-verification."
    )

    if n_downgraded == 3:
        overall = "ALL_S40_SIGNIFICANT_POSITIVE_DOWNGRADED_TO_SIGNIFICANCE_INCONCLUSIVE"
    elif n_downgraded > 0:
        overall = "PARTIAL_DOWNGRADE"
    else:
        overall = "NO_DOWNGRADE"

    recommendation = (
        "Session 40 SIGNIFICANT_POSITIVE verdicts must be formally retracted. "
        "Corrected verdict: SIGNIFICANCE_INCONCLUSIVE for all 3 comparisons. "
        "Minimum requirement for valid claim: ≥25 independent trading dates."
    )

    return SignificanceAuditReport(
        session=41,
        comparisons=tuple(comparisons),
        lodo_results=tuple(lodo_all),
        documentation_discrepancy_note=discrepancy_note,
        overall_verdict=overall,
        s40_verdicts_downgraded=n_downgraded,
        effective_n=effective_n,
        recommendation=recommendation,
    )
