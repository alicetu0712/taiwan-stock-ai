"""
PART E: Corrected 5D Comparison — Session 43.

Applies S43 v8.0-strict filter to the S42 5-cluster analysis:
  1. Exclude fill Oct 12 cluster (all v6.0 signals; 107 excluded)
  2. Flag fill Oct 21 cluster as INCOMPLETE (only 4 exit days in daily_prices)
  3. Report v8.0-strict result using 3 complete fill clusters (fill Oct 13, 14, 16)

S42 (5 clusters, mixed v6.0+v8.0): grand mean vs A_direct = +1.21%
S43 strict (3 clusters, v8.0 only):  grand mean vs A_direct = +0.81%

Both remain SIGNIFICANCE_INCONCLUSIVE (CI includes zero at 95%).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum

try:
    import numpy as np
    from scipy import stats

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


class S43ClusterStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE_EXIT = "INCOMPLETE_EXIT"
    EXCLUDED_V60 = "EXCLUDED_V60"
    EXCLUDED_NO_DATA = "EXCLUDED_NO_DATA"


class S43ComparisonVerdict(str, Enum):
    SIGNIFICANCE_INCONCLUSIVE = "SIGNIFICANCE_INCONCLUSIVE"
    SIGNIFICANT_POSITIVE = "SIGNIFICANT_POSITIVE"
    SIGNIFICANT_NEGATIVE = "SIGNIFICANT_NEGATIVE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class S43ClusterRecord:
    fill_date: str
    signal_dates: tuple[str, ...]
    model_versions: tuple[str, ...]
    n_signals: int
    status: S43ClusterStatus
    exclusion_reason: str
    # v8.0-only deltas (from S42 Bash analysis; None if excluded)
    delta_vs_a_direct: float | None
    delta_vs_b_v1v2: float | None
    delta_vs_c_hybrid: float | None


@dataclass(frozen=True)
class S43StrictComparisonResult:
    comparator: str
    n_clusters_total: int
    n_clusters_strict: int
    n_clusters_excluded: int
    n_clusters_incomplete: int
    cluster_deltas: tuple[float, ...]
    grand_mean_delta: float
    ci_lower: float
    ci_upper: float
    ci_includes_zero: bool
    t_statistic: float
    p_value: float
    verdict: S43ComparisonVerdict


@dataclass(frozen=True)
class CorrectedFiveDayComparisonS43:
    session: int
    evaluation_note: str
    # Cluster-level records
    all_clusters: tuple[S43ClusterRecord, ...]
    strict_fill_dates: tuple[str, ...]
    conditional_fill_dates: tuple[str, ...]
    excluded_fill_dates: tuple[str, ...]
    # Comparison results (strict only)
    result_vs_a_direct: S43StrictComparisonResult
    result_vs_b_v1v2: S43StrictComparisonResult
    result_vs_c_hybrid: S43StrictComparisonResult
    # S42 reference
    s42_all5_vs_a: float
    s43_strict3_vs_a: float
    # Verdict
    overall_verdict: str


# Cluster-level deltas verified from S42 Bash analysis
_CLUSTER_DATA = [
    # (fill_date, signal_dates, model_version, n_signals, delta_a, delta_b, delta_c)
    ("2026-10-12", ("2026-10-09", "2026-10-10", "2026-10-11"), "v6.0", 107,
     None, None, None),  # EXCLUDED: all v6.0
    ("2026-10-13", ("2026-10-12",), "v8.0", 46,
     0.0120, 0.0084, 0.0107),
    ("2026-10-14", ("2026-10-13",), "v8.0", 27,
     0.0276, 0.0014, 0.0276),
    ("2026-10-16", ("2026-10-14",), "v8.0", 55,
     -0.0152, -0.0141, -0.0149),
    ("2026-10-21", ("2026-10-16",), "v8.0", 39,
     0.0099, 0.0074, 0.0109),  # INCOMPLETE: only 4 exit days
]


def _run_test(deltas: list[float]) -> tuple[float, float, float, float, float, bool, S43ComparisonVerdict]:
    if len(deltas) < 2:
        m = sum(deltas) / len(deltas) if deltas else 0.0
        return m, m - 0.05, m + 0.05, 0.0, 1.0, True, S43ComparisonVerdict.INSUFFICIENT_DATA
    if not HAS_SCIPY:
        m = sum(deltas) / len(deltas)
        return m, m - 0.03, m + 0.03, 0.0, 1.0, True, S43ComparisonVerdict.INSUFFICIENT_DATA
    arr = np.array(deltas)
    m = float(arr.mean())
    n = len(arr)
    se = float(arr.std(ddof=1) / (n ** 0.5))
    if se == 0:
        return m, m, m, 0.0, 1.0, True, S43ComparisonVerdict.INSUFFICIENT_DATA
    t_crit = float(stats.t.ppf(0.975, df=n - 1))
    ci_lo = m - t_crit * se
    ci_hi = m + t_crit * se
    t_stat = m / se
    p_val = float(stats.t.sf(abs(t_stat), df=n - 1) * 2)
    includes_zero = ci_lo <= 0 <= ci_hi
    if includes_zero:
        v = S43ComparisonVerdict.SIGNIFICANCE_INCONCLUSIVE
    elif m > 0:
        v = S43ComparisonVerdict.SIGNIFICANT_POSITIVE
    else:
        v = S43ComparisonVerdict.SIGNIFICANT_NEGATIVE
    return m, ci_lo, ci_hi, t_stat, p_val, includes_zero, v


def build_corrected_5d_comparison_s43(conn: sqlite3.Connection) -> CorrectedFiveDayComparisonS43:
    # Build cluster records
    clusters = []
    for fd, sig_dates, mv, n_sigs, da, db, dc in _CLUSTER_DATA:
        if mv == "v6.0":
            status = S43ClusterStatus.EXCLUDED_V60
            reason = "All signals are v6.0; excluded from v8.0 comparison"
        elif fd == "2026-10-21":
            # Verify: how many exit days exist for a representative stock?
            check = conn.execute(
                "SELECT COUNT(*) FROM daily_prices WHERE stock_id='2330' AND date > '2026-10-21' AND date <= '2026-11-30'"
            ).fetchone()[0]
            if check < 5:
                status = S43ClusterStatus.INCOMPLETE_EXIT
                reason = f"Only {check} exit days available for 2330; need 5 for complete 5D window"
            else:
                status = S43ClusterStatus.COMPLETE
                reason = ""
        else:
            status = S43ClusterStatus.COMPLETE
            reason = ""

        clusters.append(S43ClusterRecord(
            fill_date=fd,
            signal_dates=sig_dates,
            model_versions=(mv,),
            n_signals=n_sigs,
            status=status,
            exclusion_reason=reason,
            delta_vs_a_direct=da,
            delta_vs_b_v1v2=db,
            delta_vs_c_hybrid=dc,
        ))

    # Categorize fill dates
    strict_fds = tuple(c.fill_date for c in clusters if c.status == S43ClusterStatus.COMPLETE)
    conditional_fds = tuple(c.fill_date for c in clusters if c.status == S43ClusterStatus.INCOMPLETE_EXIT)
    excluded_fds = tuple(c.fill_date for c in clusters if c.status == S43ClusterStatus.EXCLUDED_V60)

    def _make_result(comparator: str, attr: str) -> S43StrictComparisonResult:
        strict_deltas = [getattr(c, attr) for c in clusters if c.status == S43ClusterStatus.COMPLETE and getattr(c, attr) is not None]
        m, ci_lo, ci_hi, t_stat, p_val, includes_zero, v = _run_test(strict_deltas)
        return S43StrictComparisonResult(
            comparator=comparator,
            n_clusters_total=len(clusters),
            n_clusters_strict=len(strict_fds),
            n_clusters_excluded=len(excluded_fds),
            n_clusters_incomplete=len(conditional_fds),
            cluster_deltas=tuple(strict_deltas),
            grand_mean_delta=m,
            ci_lower=ci_lo,
            ci_upper=ci_hi,
            ci_includes_zero=includes_zero,
            t_statistic=t_stat,
            p_value=p_val,
            verdict=v,
        )

    r_a = _make_result("A_direct", "delta_vs_a_direct")
    r_b = _make_result("B_v1v2", "delta_vs_b_v1v2")
    r_c = _make_result("C_hybrid", "delta_vs_c_hybrid")

    return CorrectedFiveDayComparisonS43(
        session=43,
        evaluation_note=(
            "v8.0-strict analysis: excludes fill Oct 12 (107 v6.0 signals) and "
            "marks fill Oct 21 as INCOMPLETE (insufficient exit data). "
            "3 complete fill clusters used: fill Oct 13 (+1.20%), Oct 14 (+2.76%), Oct 16 (-1.52%)."
        ),
        all_clusters=tuple(clusters),
        strict_fill_dates=strict_fds,
        conditional_fill_dates=conditional_fds,
        excluded_fill_dates=excluded_fds,
        result_vs_a_direct=r_a,
        result_vs_b_v1v2=r_b,
        result_vs_c_hybrid=r_c,
        s42_all5_vs_a=0.0121,
        s43_strict3_vs_a=r_a.grand_mean_delta,
        overall_verdict=(
            "SIGNIFICANCE_INCONCLUSIVE"
            if r_a.verdict == S43ComparisonVerdict.SIGNIFICANCE_INCONCLUSIVE
            else str(r_a.verdict)
        ),
    )
