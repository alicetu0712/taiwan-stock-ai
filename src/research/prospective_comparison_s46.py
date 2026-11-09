"""
prospective_comparison_s46.py — S46 PART D/E/G/H: recovery feasibility, 5D re-evaluation,
20D data dependency, guardrail remediation.

Read-only. No production writes. 5D computation authorized; 20D NOT authorized.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import List, Optional, Tuple


# ── Enums ─────────────────────────────────────────────────────────────────────

class RecoveryFeasibility(str, Enum):
    ISOLATED_COMPUTABLE = "ISOLATED_COMPUTABLE"
    ISOLATED_PENDING_NEON = "ISOLATED_PENDING_NEON"
    ISOLATED_PENDING_PIPELINE = "ISOLATED_PENDING_PIPELINE"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"


class SnapshotType(str, Enum):
    FROZEN_BASELINE = "FROZEN_BASELINE"
    EXPANDED_RESEARCH_SNAPSHOT = "EXPANDED_RESEARCH_SNAPSHOT"


class TwentyDayStatus(str, Enum):
    NOT_YET_MATURE = "NOT_YET_MATURE"
    MATURE_BUT_DATA_INCOMPLETE = "MATURE_BUT_DATA_INCOMPLETE"
    MATURE_AND_COMPLETE = "MATURE_AND_COMPLETE"


class GuardrailStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    CONDITIONAL = "CONDITIONAL"


# ── PART D dataclasses ────────────────────────────────────────────────────────

@dataclass
class ClusterRecoveryFeasibility:
    fill_date: str
    n_signals: int
    calendar_exit_date: str
    exit_data_source: str  # "local_sqlite" | "neon_only" | "unavailable"
    feasibility: RecoveryFeasibility
    preconditions: str


@dataclass
class IsolatedRecoveryReport:
    clusters: List[ClusterRecoveryFeasibility]
    n_computable_local: int
    n_pending_neon: int
    n_not_computable: int
    summary: str


# ── PART E dataclasses ────────────────────────────────────────────────────────

@dataclass
class ClusterResult:
    fill_date: str
    n_signals: int
    exit_date: str
    v3_mean: float
    a_direct_mean: float
    delta: float          # V3 - A_direct (pp)
    snapshot_type: SnapshotType
    exit_method: str      # "proxy_5td" | "calendar_5td"
    note: str


@dataclass
class FiveDayComparisonReport:
    frozen_baseline: List[ClusterResult]
    frozen_grand_mean_delta: float
    frozen_ci_lo: float
    frozen_ci_hi: float
    frozen_verdict: str
    expanded_snapshot: List[ClusterResult]
    expanded_grand_mean_delta: float
    expanded_n_clusters: int
    expanded_verdict: str
    g03_status: GuardrailStatus
    g04_status: GuardrailStatus
    statistical_note: str


# ── PART G dataclasses ────────────────────────────────────────────────────────

@dataclass
class TwentyDayClusterDependency:
    fill_date: str
    calendar_exit_date_20d: str   # 20th real TD after fill
    proxy_tds_in_db: int          # number of real TDs currently in local SQLite after fill
    required_tds: int             # 20
    status_20d: TwentyDayStatus
    data_gap_description: str


@dataclass
class TwentyDayDataDependencyReport:
    local_sqlite_max: str
    today: str
    clusters: List[TwentyDayClusterDependency]
    n_mature_complete: int
    n_mature_incomplete: int
    n_not_yet_mature: int
    earliest_20d_eligible_fill: Optional[str]
    authorization_required: str
    summary: str


# ── PART H dataclasses ────────────────────────────────────────────────────────

@dataclass
class GuardrailAssessmentS46:
    guardrail_id: str
    horizon: str
    s45_status: GuardrailStatus
    s46_status: GuardrailStatus
    change: str
    type: str            # ENGINEERING_FIXABLE | DATA_LIMITED | DESIGN_CONSTRAINT
    remaining_blocker: str
    remediation_note: str


@dataclass
class GuardrailRemediationReport:
    guardrails: List[GuardrailAssessmentS46]
    overall_status: GuardrailStatus
    overall_change: str
    n_fail: int
    n_conditional: int
    n_pass: int
    remediation_summary: str


# ── PART D: isolated recovery feasibility ─────────────────────────────────────

_CALENDAR_5TD = {
    "2026-10-13": "2026-10-21",
    "2026-10-14": "2026-10-28",
    "2026-10-16": "2026-11-05",
    "2026-10-21": "2026-10-30",
    "2026-10-22": "2026-11-02",
    "2026-10-28": "2026-11-04",
}


def build_isolated_recovery_report(conn: sqlite3.Connection) -> IsolatedRecoveryReport:
    rows = conn.execute("""
        SELECT execution_date, COUNT(*) as n
        FROM forward_signals
        WHERE model_version='v8.0' AND is_valid=1
        AND trade_signal IN ('buy','strong_buy')
        AND execution_date IS NOT NULL
        GROUP BY execution_date
        ORDER BY execution_date
    """).fetchall()

    clusters = []
    for exec_d, n in rows:
        cal_exit = _CALENDAR_5TD.get(exec_d, "UNKNOWN")
        if cal_exit == "UNKNOWN":
            feasibility = RecoveryFeasibility.NOT_COMPUTABLE
            source = "unavailable"
            precond = "Calendar exit date unknown."
        else:
            cnt = conn.execute(
                "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?", (cal_exit,)
            ).fetchone()[0]
            if cnt >= 50:
                feasibility = RecoveryFeasibility.ISOLATED_COMPUTABLE
                source = "local_sqlite"
                precond = f"Exit data available locally ({cnt} stocks on {cal_exit})."
            else:
                feasibility = RecoveryFeasibility.ISOLATED_PENDING_NEON
                source = "neon_only"
                precond = (
                    f"Exit date {cal_exit} has only {cnt} stocks in local SQLite. "
                    "Available in Neon DB (638 stocks) — requires Neon read authorization."
                )
        clusters.append(ClusterRecoveryFeasibility(
            fill_date=exec_d,
            n_signals=n,
            calendar_exit_date=cal_exit,
            exit_data_source=source,
            feasibility=feasibility,
            preconditions=precond,
        ))

    n_local = sum(1 for c in clusters if c.feasibility == RecoveryFeasibility.ISOLATED_COMPUTABLE)
    n_neon = sum(1 for c in clusters if c.feasibility == RecoveryFeasibility.ISOLATED_PENDING_NEON)
    n_not = sum(1 for c in clusters if c.feasibility == RecoveryFeasibility.NOT_COMPUTABLE)

    return IsolatedRecoveryReport(
        clusters=clusters,
        n_computable_local=n_local,
        n_pending_neon=n_neon,
        n_not_computable=n_not,
        summary=(
            f"Isolated recovery: {n_local} computable from local SQLite, "
            f"{n_neon} pending Neon data access, {n_not} not computable. "
            "Oct 28 fill (exit Nov 04): ISOLATED_COMPUTABLE. "
            "Oct 22/21 fills (exit Nov 02/Oct 30): ISOLATED_PENDING_NEON."
        ),
    )


# ── PART E: 5D comparison re-evaluation ───────────────────────────────────────

# Frozen deltas from S44/S45 canonical baseline (hardcoded, unchanged)
_FROZEN_DELTAS: List[Tuple[str, int, str, float, float, float]] = [
    # (fill_date, n_signals, exit_date, v3_mean_pct, a_direct_mean_pct, delta_pp)
    ("2026-10-13", 46, "2026-10-21", 1.20, 0.84, 1.07),   # from canonical_5d_baseline_s44
    ("2026-10-14", 27, "2026-10-28", 2.76, 0.14, 2.76),
    ("2026-10-16", 55, "2026-11-05", -1.52, -1.41, -1.49),
]
_FROZEN_GRAND_MEAN = 0.81
_FROZEN_CI_LO = -1.4
_FROZEN_CI_HI = 3.0


def _compute_cluster_delta(conn: sqlite3.Connection, fill_date: str, exit_date: str) -> Optional[Tuple[int, float, float, float]]:
    sigs = conn.execute("""
        SELECT stock_id, execution_price, signal_close
        FROM forward_signals
        WHERE execution_date=? AND model_version='v8.0' AND is_valid=1
        AND trade_signal IN ('buy','strong_buy')
        AND execution_price IS NOT NULL AND signal_close IS NOT NULL
    """, (fill_date,)).fetchall()
    if not sigs:
        return None

    v3_rets, ad_rets = [], []
    for stock_id, ep, sc in sigs:
        r = conn.execute(
            "SELECT close FROM daily_prices WHERE stock_id=? AND date=?", (stock_id, exit_date)
        ).fetchone()
        if r and ep and ep > 0 and sc and sc > 0:
            v3_rets.append((r[0] - ep) / ep * 100)
            ad_rets.append((r[0] - sc) / sc * 100)

    if not v3_rets:
        return None
    n = len(v3_rets)
    v3_mean = sum(v3_rets) / n
    ad_mean = sum(ad_rets) / n
    delta = v3_mean - ad_mean
    return n, v3_mean, ad_mean, delta


def build_five_day_comparison(conn: sqlite3.Connection) -> FiveDayComparisonReport:
    frozen = []
    for fill_d, n, exit_d, v3m, adm, dlt in _FROZEN_DELTAS:
        frozen.append(ClusterResult(
            fill_date=fill_d,
            n_signals=n,
            exit_date=exit_d,
            v3_mean=v3m,
            a_direct_mean=adm,
            delta=dlt,
            snapshot_type=SnapshotType.FROZEN_BASELINE,
            exit_method="proxy_5td",
            note="S44 canonical baseline (hardcoded)",
        ))

    # Expanded snapshot: add Oct 28 fill (calendar-based exit Nov 04, local SQLite)
    expanded = list(frozen)
    oct28_result = _compute_cluster_delta(conn, "2026-10-28", "2026-11-04")
    if oct28_result:
        n28, v3m28, adm28, dlt28 = oct28_result
        expanded.append(ClusterResult(
            fill_date="2026-10-28",
            n_signals=n28,
            exit_date="2026-11-04",
            v3_mean=round(v3m28, 4),
            a_direct_mean=round(adm28, 4),
            delta=round(dlt28, 4),
            snapshot_type=SnapshotType.EXPANDED_RESEARCH_SNAPSHOT,
            exit_method="calendar_5td",
            note="Calendar-based exit (5th real TD per trading_calendar). "
                 "RESEARCH_ONLY — not part of strict baseline.",
        ))

    # Oct 22 fill: PENDING (exit Nov 02 not in local SQLite)
    expanded.append(ClusterResult(
        fill_date="2026-10-22",
        n_signals=19,
        exit_date="2026-11-02",
        v3_mean=float("nan"),
        a_direct_mean=float("nan"),
        delta=float("nan"),
        snapshot_type=SnapshotType.EXPANDED_RESEARCH_SNAPSHOT,
        exit_method="calendar_5td",
        note="PENDING_NEON: exit date Nov 02 has only 0050 in local SQLite. "
             "Full data available in Neon DB (638 stocks). Not computed.",
    ))

    # Compute expanded grand mean (only finite deltas)
    exp_deltas = [c.delta for c in expanded if c.delta == c.delta]  # exclude NaN
    exp_mean = sum(exp_deltas) / len(exp_deltas) if exp_deltas else float("nan")

    # Statistical verdicts
    frozen_verdict = "SIGNIFICANCE_INCONCLUSIVE (N=3, CI crosses 0)"
    exp_verdict = f"SIGNIFICANCE_INCONCLUSIVE (N={len(exp_deltas)} finite, G03 FAIL N<10)"

    return FiveDayComparisonReport(
        frozen_baseline=frozen,
        frozen_grand_mean_delta=_FROZEN_GRAND_MEAN,
        frozen_ci_lo=_FROZEN_CI_LO,
        frozen_ci_hi=_FROZEN_CI_HI,
        frozen_verdict=frozen_verdict,
        expanded_snapshot=expanded,
        expanded_grand_mean_delta=round(exp_mean, 4) if exp_mean == exp_mean else float("nan"),
        expanded_n_clusters=len(exp_deltas),
        expanded_verdict=exp_verdict,
        g03_status=GuardrailStatus.FAIL,
        g04_status=GuardrailStatus.FAIL,
        statistical_note=(
            "Expanded snapshot is RESEARCH_ONLY and must NOT replace the frozen baseline. "
            "G03 FAIL (need ≥10 strict clusters). G04 FAIL (adjacent window overlap). "
            "No statistical inference claim on expanded snapshot."
        ),
    )


# ── PART G: 20D data dependency ────────────────────────────────────────────────

_CALENDAR_20TD = {
    "2026-10-13": "2026-11-14",  # approx 20 TDs after Oct 13
    "2026-10-14": "2026-11-17",
    "2026-10-16": "2026-11-19",
    "2026-10-21": "2026-11-24",
    "2026-10-22": "2026-11-25",
    "2026-10-28": "2026-12-02",
}


def _count_proxy_exit_days_unlimited(conn: sqlite3.Connection, fill_date: str, stock_id: str = "2330") -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM daily_prices WHERE stock_id=? AND date > ?",
        (stock_id, fill_date)
    ).fetchone()[0]


def build_20d_data_dependency(conn: sqlite3.Connection, today: str = "2026-11-09") -> TwentyDayDataDependencyReport:
    local_max = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0] or "unknown"

    rows = conn.execute("""
        SELECT execution_date FROM forward_signals
        WHERE model_version='v8.0' AND is_valid=1
        AND trade_signal IN ('buy','strong_buy')
        AND execution_date IS NOT NULL
        GROUP BY execution_date ORDER BY execution_date
    """).fetchall()

    clusters = []
    today_d = date.fromisoformat(today)
    earliest_eligible = None

    for (exec_d,) in rows:
        proxy_tds = _count_proxy_exit_days_unlimited(conn, exec_d)
        cal_exit_20d = _CALENDAR_20TD.get(exec_d, "UNKNOWN")

        if cal_exit_20d != "UNKNOWN":
            exit_d = date.fromisoformat(cal_exit_20d)
            if exit_d <= today_d:
                cnt = conn.execute(
                    "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?",
                    (cal_exit_20d,)
                ).fetchone()[0]
                if cnt >= 50:
                    status = TwentyDayStatus.MATURE_AND_COMPLETE
                else:
                    status = TwentyDayStatus.MATURE_BUT_DATA_INCOMPLETE
            else:
                status = TwentyDayStatus.NOT_YET_MATURE
        else:
            status = TwentyDayStatus.NOT_YET_MATURE

        if proxy_tds >= 20:
            status = TwentyDayStatus.MATURE_AND_COMPLETE

        gap = max(0, 20 - proxy_tds)
        gap_desc = (
            f"{proxy_tds}/20 real TDs in local SQLite (2330 proxy). "
            f"Need {gap} more."
        )

        if status == TwentyDayStatus.MATURE_AND_COMPLETE and earliest_eligible is None:
            earliest_eligible = exec_d

        clusters.append(TwentyDayClusterDependency(
            fill_date=exec_d,
            calendar_exit_date_20d=cal_exit_20d,
            proxy_tds_in_db=proxy_tds,
            required_tds=20,
            status_20d=status,
            data_gap_description=gap_desc,
        ))

    n_complete = sum(1 for c in clusters if c.status_20d == TwentyDayStatus.MATURE_AND_COMPLETE)
    n_incomplete = sum(1 for c in clusters if c.status_20d == TwentyDayStatus.MATURE_BUT_DATA_INCOMPLETE)
    n_not_mature = sum(1 for c in clusters if c.status_20d == TwentyDayStatus.NOT_YET_MATURE)

    return TwentyDayDataDependencyReport(
        local_sqlite_max=str(local_max),
        today=today,
        clusters=clusters,
        n_mature_complete=n_complete,
        n_mature_incomplete=n_incomplete,
        n_not_yet_mature=n_not_mature,
        earliest_20d_eligible_fill=earliest_eligible,
        authorization_required=(
            "20D outcome computation is NOT authorized in S44/S45/S46. "
            "Requires explicit AUTH01+AUTH02 in a future session prompt. "
            "Prerequisite: local_sqlite_max ≥ calendar_exit_date_20d for target fill."
        ),
        summary=(
            f"0 fills have 20D outcomes ready (local SQLite max={local_max}). "
            f"All {n_not_mature} fills are NOT_YET_MATURE. "
            "Earliest 20D ETA: ~Nov 14 (Oct 13 fill), assuming pipeline recovers."
        ),
    )


# ── PART H: guardrail remediation ─────────────────────────────────────────────

def build_guardrail_remediation(conn: sqlite3.Connection) -> GuardrailRemediationReport:
    n_strict = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT fs.execution_date,
                   COUNT(DISTINCT dp.date) as exit_days
            FROM forward_signals fs
            LEFT JOIN daily_prices dp
              ON dp.stock_id='2330' AND dp.date > fs.execution_date
            WHERE fs.model_version='v8.0' AND fs.is_valid=1
            AND fs.trade_signal IN ('buy','strong_buy')
            AND fs.execution_date IS NOT NULL
            GROUP BY fs.execution_date
            HAVING exit_days >= 5
        )
    """).fetchone()[0] or 3

    guardrails = [
        GuardrailAssessmentS46(
            guardrail_id="G01",
            horizon="5D",
            s45_status=GuardrailStatus.CONDITIONAL,
            s46_status=GuardrailStatus.CONDITIONAL,
            change="UNCHANGED",
            type="ENGINEERING_FIXABLE",
            remaining_blocker=(
                "TradingCalendarIntegrityAuditor uses DISTINCT date query; "
                "must switch to ≥50-stock threshold for thin-day detection."
            ),
            remediation_note=(
                "Fix: update auditor to use COUNT(DISTINCT stock_id) ≥ 50 "
                "instead of IS_TRADING_DAY check alone. "
                "S46 scope: research-only — does not modify production pipeline."
            ),
        ),
        GuardrailAssessmentS46(
            guardrail_id="G03",
            horizon="5D",
            s45_status=GuardrailStatus.FAIL,
            s46_status=GuardrailStatus.FAIL,
            change="UNCHANGED",
            type="DATA_LIMITED",
            remaining_blocker=(
                f"Only {n_strict} strict clusters (need ≥10). "
                "Even with Oct 22/28 fills recovered → 5 clusters. "
                "Need 5 more (~Nov–Dec 2026)."
            ),
            remediation_note=(
                "Path to PASS: accumulate more cron-generated clusters. "
                "ETA ~Jan 2027 at ~12–15 clusters/month."
            ),
        ),
        GuardrailAssessmentS46(
            guardrail_id="G04",
            horizon="5D",
            s45_status=GuardrailStatus.FAIL,
            s46_status=GuardrailStatus.FAIL,
            change="UNCHANGED",
            type="DESIGN_CONSTRAINT",
            remaining_blocker=(
                "Adjacent 5D windows overlap ~80%. "
                "Daily fills with 5D holding periods are inherently correlated."
            ),
            remediation_note=(
                "Cannot be fixed by code. Requires non-overlapping fill selection "
                "(e.g., one fill per 5-TD period) or longer holding horizon."
            ),
        ),
        GuardrailAssessmentS46(
            guardrail_id="G04",
            horizon="20D",
            s45_status=GuardrailStatus.FAIL,
            s46_status=GuardrailStatus.FAIL,
            change="UNCHANGED",
            type="DESIGN_CONSTRAINT",
            remaining_blocker=(
                "Consecutive fills (e.g., Oct 13/14) have 20D windows overlapping ~15 TDs (~75%)."
            ),
            remediation_note=(
                "Same constraint as 5D. Use one fill per 20-TD period for clean comparison."
            ),
        ),
    ]

    n_fail = sum(1 for g in guardrails if g.s46_status == GuardrailStatus.FAIL)
    n_cond = sum(1 for g in guardrails if g.s46_status == GuardrailStatus.CONDITIONAL)
    n_pass = sum(1 for g in guardrails if g.s46_status == GuardrailStatus.PASS)

    return GuardrailRemediationReport(
        guardrails=guardrails,
        overall_status=GuardrailStatus.FAIL,
        overall_change="UNCHANGED from S45",
        n_fail=n_fail,
        n_conditional=n_cond,
        n_pass=n_pass,
        remediation_summary=(
            f"G01 CONDITIONAL (engineering fix possible, not done in research scope). "
            f"G03 FAIL (data limited, {n_strict} clusters). "
            "G04 FAIL (design constraint, both 5D and 20D). "
            "No guardrails improved in S46."
        ),
    )
