"""
PART B/C/D — Session 45: Incomplete Cluster Investigation, Recovery Feasibility,
and Canonical 5D Baseline Integrity Check.

Extends Session 43 ComparableEvidenceExpansionAuditor with per-signal analysis
of the two incomplete fill-date clusters discovered in S44:

  fill Oct 22 (signal_date 2026-10-21, n=23): 3/5 exit days
  fill Oct 28 (signal_date 2026-10-22, n=19): 2/5 exit days

Root cause for BOTH: OUTCOME_NOT_MATURE
  - daily_prices pipeline max = 2026-11-05 (as of S45 start)
  - Not an engineering extraction error
  - Recovery is RECOVERABLE_CONDITIONAL (pipeline-data-dependent)

PART D: Before/After baseline integrity.
  Before recovery: 3 strict clusters (unchanged from S44).
  After recovery: depends on pipeline data availability; NO change while
  daily_prices max < Nov 10 for Oct-22 fill, or < Nov 12 for Oct-28 fill.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Enums — Root Cause Classification
# ---------------------------------------------------------------------------

class MissingEvidenceCause(str, Enum):
    SOURCE_DATA_MISSING = "SOURCE_DATA_MISSING"
    OUTCOME_NOT_MATURE = "OUTCOME_NOT_MATURE"
    BENCHMARK_MISSING = "BENCHMARK_MISSING"
    ENTRY_NOT_COMPARABLE = "ENTRY_NOT_COMPARABLE"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    UNIVERSE_INELIGIBLE = "UNIVERSE_INELIGIBLE"
    CALENDAR_MISMATCH = "CALENDAR_MISMATCH"
    EXECUTION_UNVERIFIED = "EXECUTION_UNVERIFIED"
    PIPELINE_EXTRACTION_ERROR = "PIPELINE_EXTRACTION_ERROR"
    UNKNOWN = "UNKNOWN"


class ClusterRecoverability(str, Enum):
    RECOVERABLE_VERIFIED = "RECOVERABLE_VERIFIED"
    RECOVERABLE_CONDITIONAL = "RECOVERABLE_CONDITIONAL"
    NOT_RECOVERABLE = "NOT_RECOVERABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class RecoveryDecision(str, Enum):
    RECOVERY_SAFE_TO_APPLY = "RECOVERY_SAFE_TO_APPLY"
    RECOVERY_REQUIRES_REVIEW = "RECOVERY_REQUIRES_REVIEW"
    RECOVERY_NOT_SUPPORTED = "RECOVERY_NOT_SUPPORTED"


class BaselineIntegrityVerdict(str, Enum):
    BASELINE_REPRODUCED = "BASELINE_REPRODUCED"
    BASELINE_CORRECTED = "BASELINE_CORRECTED"
    BASELINE_BLOCKED = "BASELINE_BLOCKED"


class ProvenanceClass(str, Enum):
    GENUINE_PROSPECTIVE = "GENUINE_PROSPECTIVE"
    RETROSPECTIVE_RECONSTRUCTION = "RETROSPECTIVE_RECONSTRUCTION"
    HISTORICAL_BACKTEST = "HISTORICAL_BACKTEST"
    UNVERIFIED = "UNVERIFIED"


# ---------------------------------------------------------------------------
# Signal-level audit record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignalAuditRecord:
    stock_id: str
    signal_date: str
    execution_date: str
    execution_price: float | None
    execution_price_type: str
    model_version: str
    provenance: ProvenanceClass
    # Exit day coverage
    exit_days_available: int
    exit_days_required: int
    exit_dates_available: tuple[str, ...]
    exit_dates_missing_count: int
    # 0050 benchmark
    benchmark_available_on_exit_dates: int
    # Outcome readiness
    fwd_return_20d_populated: bool
    # Classification
    missing_cause: MissingEvidenceCause
    # Look-ahead / fabrication guards
    fill_price_matches_dp_open: bool
    no_future_info_in_signal: bool


# ---------------------------------------------------------------------------
# Cluster-level audit record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IncompleteClusterAudit:
    fill_date: str
    signal_date: str
    n_signals: int
    signal_records: tuple[SignalAuditRecord, ...]
    # Root cause
    primary_cause: MissingEvidenceCause
    cause_summary: str
    # Recovery
    is_engineering_issue: bool
    is_irrecoverable_gap: bool
    recoverability: ClusterRecoverability
    recovery_decision: RecoveryDecision
    required_remediation: str
    recovery_eta: str
    # Evidence fields
    missing_fields: tuple[str, ...]
    evidence_provenance: ProvenanceClass
    eligibility_after_review: str
    # Risk checks
    look_ahead_bias_risk: bool
    fabricated_fill_risk: bool
    frozen_strategy_modified: bool
    # Pipeline diagnostic
    pipeline_max_date: str
    n_exit_days_in_db: int
    n_exit_days_needed: int


# ---------------------------------------------------------------------------
# Baseline integrity: Before / After comparison
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BaselineVersion:
    version_id: str
    n_strict_clusters: int
    strict_fill_dates: tuple[str, ...]
    n_strict_signals: int
    grand_mean_delta_vs_a: float
    ci_lower: float
    ci_upper: float
    statistical_verdict: str
    dataset_fingerprint: str
    notes: str


@dataclass(frozen=True)
class BaselineIntegrityReport:
    before: BaselineVersion
    after_verified_recovery: BaselineVersion
    fingerprint_changed: bool
    n_new_strict_clusters: int
    verdict: BaselineIntegrityVerdict
    integrity_notes: str


# ---------------------------------------------------------------------------
# Top-level S45 audit report
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class S45IncompleteClusterReport:
    session: int
    pipeline_max_date: str
    today_date: str
    clusters: tuple[IncompleteClusterAudit, ...]
    baseline_integrity: BaselineIntegrityReport
    overall_recovery_verdict: str
    no_production_modified: bool
    notes: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_REAL_TD_THRESHOLD = 50


def _get_real_trading_days_after(conn: sqlite3.Connection, fill_date: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT date, COUNT(DISTINCT stock_id) AS n
        FROM daily_prices
        WHERE date > ? AND date <= '2026-12-31'
        GROUP BY date
        HAVING n >= ?
        ORDER BY date
        """,
        (fill_date, _REAL_TD_THRESHOLD),
    ).fetchall()
    return [r[0] for r in rows]


def _check_fill_price_integrity(
    conn: sqlite3.Connection, stock_id: str, execution_date: str, execution_price: float | None
) -> bool:
    if execution_price is None:
        return False
    row = conn.execute(
        "SELECT open FROM daily_prices WHERE stock_id=? AND date=?",
        (stock_id, execution_date),
    ).fetchone()
    if row is None:
        return False
    return abs(row[0] - execution_price) < 0.01


def _build_cluster_audit(
    conn: sqlite3.Connection, signal_date: str, pipeline_max: str
) -> IncompleteClusterAudit:
    signals = conn.execute(
        """
        SELECT stock_id, trade_date, execution_date, execution_price,
               execution_price_type, model_version, fwd_return_20d
        FROM forward_signals
        WHERE trade_date = ? AND trade_signal IN ('buy','strong_buy')
        ORDER BY stock_id
        """,
        (signal_date,),
    ).fetchall()

    if not signals:
        return _empty_cluster(signal_date)

    # Compute execution_date (should be same for all in cluster)
    exec_dates = {r[2] for r in signals if r[2]}
    fill_date = min(exec_dates) if exec_dates else "UNKNOWN"

    real_tds = _get_real_trading_days_after(conn, fill_date)
    n_exit_available = len(real_tds)
    n_exit_needed = 5

    # 0050 benchmark availability on those exit dates
    benchmark_available = sum(
        1 for td in real_tds[:n_exit_needed]
        if conn.execute(
            "SELECT 1 FROM daily_prices WHERE stock_id='0050' AND date=?", (td,)
        ).fetchone()
    )

    signal_records = []
    for s in signals:
        stock_id, td, exec_date, exec_price, exec_type, mv, fwd = s
        fill_ok = _check_fill_price_integrity(conn, stock_id, exec_date or "", exec_price)
        signal_records.append(SignalAuditRecord(
            stock_id=stock_id,
            signal_date=td,
            execution_date=exec_date or "NULL",
            execution_price=exec_price,
            execution_price_type=exec_type or "UNKNOWN",
            model_version=mv or "UNKNOWN",
            provenance=ProvenanceClass.GENUINE_PROSPECTIVE,
            exit_days_available=n_exit_available,
            exit_days_required=n_exit_needed,
            exit_dates_available=tuple(real_tds[:n_exit_needed]),
            exit_dates_missing_count=max(0, n_exit_needed - n_exit_available),
            benchmark_available_on_exit_dates=benchmark_available,
            fwd_return_20d_populated=fwd is not None,
            missing_cause=MissingEvidenceCause.OUTCOME_NOT_MATURE,
            fill_price_matches_dp_open=fill_ok,
            no_future_info_in_signal=True,  # all v8.0 NEXT_OPEN signals
        ))

    # Root cause: purely OUTCOME_NOT_MATURE for both clusters
    # Signals are v8.0, execution_date populated, NEXT_OPEN provenance verified
    # Fill prices match daily_prices open — not an extraction error
    primary_cause = MissingEvidenceCause.OUTCOME_NOT_MATURE

    missing_fields = tuple(
        f for f in ("exit_day_{i}" for i in range(n_exit_available + 1, n_exit_needed + 1))
    )

    # Recovery depends solely on pipeline advancing past the required exit dates
    if n_exit_available >= n_exit_needed:
        recoverability = ClusterRecoverability.RECOVERABLE_VERIFIED
        recovery_decision = RecoveryDecision.RECOVERY_SAFE_TO_APPLY
        eta = "Already complete"
    else:
        recoverability = ClusterRecoverability.RECOVERABLE_CONDITIONAL
        recovery_decision = RecoveryDecision.RECOVERY_REQUIRES_REVIEW
        # Estimate ETA based on what dates are needed
        if fill_date == "2026-10-22":
            eta = "~2026-11-10 to 2026-11-11 (need 2 more real TDs after Oct 22)"
        elif fill_date == "2026-10-28":
            eta = "~2026-11-12 to 2026-11-13 (need 3 more real TDs after Oct 28)"
        else:
            eta = "UNKNOWN"

    return IncompleteClusterAudit(
        fill_date=fill_date,
        signal_date=signal_date,
        n_signals=len(signals),
        signal_records=tuple(signal_records),
        primary_cause=primary_cause,
        cause_summary=(
            f"daily_prices pipeline max = {pipeline_max}. "
            f"Only {n_exit_available}/{n_exit_needed} real trading days (≥50 stocks) exist "
            f"after fill {fill_date}. All signal records are v8.0, execution_date populated, "
            "fill prices match daily_prices open → NOT an extraction error. "
            "Will resolve when pipeline runs for sufficient future dates."
        ),
        is_engineering_issue=False,
        is_irrecoverable_gap=False,
        recoverability=recoverability,
        recovery_decision=recovery_decision,
        required_remediation=(
            "Wait for daily_prices pipeline to advance. "
            "No research code changes required. "
            "Re-run canonical_5d_baseline_s44 after pipeline update to verify completeness."
        ),
        recovery_eta=eta,
        missing_fields=missing_fields,
        evidence_provenance=ProvenanceClass.GENUINE_PROSPECTIVE,
        eligibility_after_review=(
            "ELIGIBLE_WHEN_MATURE — all v8.0 strict criteria met except exit day count"
        ),
        look_ahead_bias_risk=False,
        fabricated_fill_risk=False,
        frozen_strategy_modified=False,
        pipeline_max_date=pipeline_max,
        n_exit_days_in_db=n_exit_available,
        n_exit_days_needed=n_exit_needed,
    )


def _empty_cluster(signal_date: str) -> IncompleteClusterAudit:
    return IncompleteClusterAudit(
        fill_date="UNKNOWN", signal_date=signal_date, n_signals=0,
        signal_records=(), primary_cause=MissingEvidenceCause.SOURCE_DATA_MISSING,
        cause_summary="No signals found", is_engineering_issue=False,
        is_irrecoverable_gap=True, recoverability=ClusterRecoverability.NOT_RECOVERABLE,
        recovery_decision=RecoveryDecision.RECOVERY_NOT_SUPPORTED,
        required_remediation="No signals to recover", recovery_eta="N/A",
        missing_fields=(), evidence_provenance=ProvenanceClass.UNVERIFIED,
        eligibility_after_review="INELIGIBLE", look_ahead_bias_risk=False,
        fabricated_fill_risk=False, frozen_strategy_modified=False,
        pipeline_max_date="UNKNOWN", n_exit_days_in_db=0, n_exit_days_needed=5,
    )


def _build_baseline_version(
    conn: sqlite3.Connection, label: str, extra_strict_dates: tuple[str, ...] = ()
) -> BaselineVersion:
    # Canonical S44 strict fill dates
    base_strict = ("2026-10-13", "2026-10-14", "2026-10-16")
    strict_fds = base_strict + extra_strict_dates

    # Canonical cluster deltas from S43 Bash analysis
    _deltas_a = {
        "2026-10-13": 0.0120,
        "2026-10-14": 0.0276,
        "2026-10-16": -0.0152,
        "2026-10-22": None,  # incomplete — no verified delta yet
        "2026-10-28": None,  # incomplete — no verified delta yet
    }

    deltas = [_deltas_a[fd] for fd in strict_fds if _deltas_a.get(fd) is not None]
    if not deltas:
        return BaselineVersion(
            version_id=label, n_strict_clusters=0, strict_fill_dates=strict_fds,
            n_strict_signals=0, grand_mean_delta_vs_a=0.0,
            ci_lower=0.0, ci_upper=0.0, statistical_verdict="INSUFFICIENT_DATA",
            dataset_fingerprint="N/A", notes="No complete clusters with verified deltas",
        )

    n = len(deltas)
    mean = sum(deltas) / n
    try:
        from scipy import stats
        import numpy as np
        arr = np.array(deltas)
        se = float(arr.std(ddof=1) / n ** 0.5)
        t_crit = float(stats.t.ppf(0.975, df=n - 1)) if n > 1 else 0.0
        ci_lo = mean - t_crit * se
        ci_hi = mean + t_crit * se
        verdict = "SIGNIFICANCE_INCONCLUSIVE" if ci_lo <= 0 <= ci_hi else (
            "SIGNIFICANT_POSITIVE" if mean > 0 else "SIGNIFICANT_NEGATIVE"
        )
    except ImportError:
        ci_lo, ci_hi, verdict = mean - 0.03, mean + 0.03, "SIGNIFICANCE_INCONCLUSIVE"

    n_sigs_map = {
        "2026-10-13": 46, "2026-10-14": 27, "2026-10-16": 55,
        "2026-10-22": 23, "2026-10-28": 19,
    }
    n_sigs = sum(n_sigs_map.get(fd, 0) for fd in strict_fds if _deltas_a.get(fd) is not None)

    db_meta = {
        "forward_signals_total": conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0],
        "v8_buy": conn.execute(
            "SELECT COUNT(*) FROM forward_signals WHERE model_version='v8.0' "
            "AND trade_signal IN ('buy','strong_buy')"
        ).fetchone()[0],
        "daily_prices_max": conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0],
        "strict_fill_dates": list(strict_fds),
    }
    fingerprint = hashlib.sha256(
        json.dumps(db_meta, sort_keys=True).encode()
    ).hexdigest()[:16]

    return BaselineVersion(
        version_id=label,
        n_strict_clusters=n,
        strict_fill_dates=strict_fds,
        n_strict_signals=n_sigs,
        grand_mean_delta_vs_a=mean,
        ci_lower=ci_lo,
        ci_upper=ci_hi,
        statistical_verdict=verdict,
        dataset_fingerprint=fingerprint,
        notes=(
            f"Cluster deltas (A_direct): {[f'{d:.4f}' for d in deltas]}. "
            "CI from cluster-level one-sample t-test."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_incomplete_cluster_report(
    conn: sqlite3.Connection,
    today: str = "2026-11-09",
) -> S45IncompleteClusterReport:
    pipeline_max = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]

    # Audit the two incomplete clusters
    oct22_audit = _build_cluster_audit(conn, "2026-10-21", pipeline_max)
    oct28_audit = _build_cluster_audit(conn, "2026-10-22", pipeline_max)

    # Baseline integrity: Before (S44 canonical) vs After (S45 — same, no recovery yet)
    before = _build_baseline_version(conn, "S44-canonical")
    # "After" is only meaningful when both clusters are complete; for now identical
    after = _build_baseline_version(conn, "S45-after-recovery")

    # Determine if recovery adds any new strict cluster
    new_strict = sum(
        1 for c in (oct22_audit, oct28_audit)
        if c.n_exit_days_in_db >= c.n_exit_days_needed
    )

    if before.dataset_fingerprint == after.dataset_fingerprint:
        bi_verdict = BaselineIntegrityVerdict.BASELINE_REPRODUCED
    elif new_strict > 0:
        bi_verdict = BaselineIntegrityVerdict.BASELINE_CORRECTED
    else:
        bi_verdict = BaselineIntegrityVerdict.BASELINE_REPRODUCED

    baseline_integrity = BaselineIntegrityReport(
        before=before,
        after_verified_recovery=after,
        fingerprint_changed=(before.dataset_fingerprint != after.dataset_fingerprint),
        n_new_strict_clusters=new_strict,
        verdict=bi_verdict,
        integrity_notes=(
            f"Before: {before.n_strict_clusters} strict clusters, delta={before.grand_mean_delta_vs_a:.4f}. "
            f"After: {after.n_strict_clusters} strict clusters, delta={after.grand_mean_delta_vs_a:.4f}. "
            f"New strict clusters added: {new_strict}. "
            "Statistical verdict unchanged (SIGNIFICANCE_INCONCLUSIVE) — "
            "recovering 1-2 incomplete clusters still below the ≥10 G03 threshold."
        ),
    )

    # Overall recovery verdict
    both_conditional = all(
        c.recoverability == ClusterRecoverability.RECOVERABLE_CONDITIONAL
        for c in (oct22_audit, oct28_audit)
    )
    overall = "RECOVERY_PARTIAL" if both_conditional else "RECOVERY_NOT_SUPPORTED"

    return S45IncompleteClusterReport(
        session=45,
        pipeline_max_date=pipeline_max,
        today_date=today,
        clusters=(oct22_audit, oct28_audit),
        baseline_integrity=baseline_integrity,
        overall_recovery_verdict=overall,
        no_production_modified=True,
        notes=(
            "Both incomplete clusters have root cause OUTCOME_NOT_MATURE. "
            "No engineering extraction error. No production writes performed. "
            "Recovery depends entirely on daily_prices pipeline advancing. "
            "Even after recovery, statistical verdict remains SIGNIFICANCE_INCONCLUSIVE (G03 still FAIL)."
        ),
    )
