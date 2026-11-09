"""
PART G (P6): 20D Research Execution Plan — Session 44.

Design-only. NOT authorized for execution in this session.
Documents the step-by-step procedure for conducting the 20D outcome analysis
when authorized in a future session.

Authorization required items are explicitly listed at the end.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PlanStepStatus(str, Enum):
    PRECONDITION = "PRECONDITION"
    EXECUTION_STEP = "EXECUTION_STEP"
    VALIDATION_STEP = "VALIDATION_STEP"
    ABORT_CONDITION = "ABORT_CONDITION"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"


class PreconditionStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    step_type: PlanStepStatus
    description: str
    implementation_note: str
    precondition_status: PreconditionStatus
    blocking_until: str


@dataclass(frozen=True)
class AbortCondition:
    condition_id: str
    trigger: str
    action: str
    recovery: str


@dataclass(frozen=True)
class AuthorizationItem:
    item_id: str
    description: str
    who_must_authorize: str
    current_status: str


@dataclass(frozen=True)
class TwentyDayResearchExecutionPlan:
    session: int
    plan_version: str
    plan_status: str
    # Preconditions
    eligibility_preconditions: tuple[PlanStep, ...]
    # Execution procedure
    execution_steps: tuple[PlanStep, ...]
    # Abort conditions
    abort_conditions: tuple[AbortCondition, ...]
    # Authorization checklist
    authorization_items: tuple[AuthorizationItem, ...]
    n_preconditions_pass: int
    n_preconditions_fail: int
    earliest_eligible_execution_date: str
    plan_notes: str


_PRECONDITIONS = [
    PlanStep(
        "P01", PlanStepStatus.PRECONDITION,
        "Outcome maturity: all target fill clusters have 20 stock-specific trading days available",
        "Verify via maturity_reconciliation_20d_s44.TwentyDayMaturityReconciliation: "
        "all target records have maturity_status=MATURE_AND_COMPLETE",
        PreconditionStatus.FAIL,
        "~2026-11-24 (fill Oct 13 earliest completion date)",
    ),
    PlanStep(
        "P02", PlanStepStatus.PRECONDITION,
        "Price completeness: daily_prices has data for all stocks through outcome_end_date",
        "Verify: for each signal in target clusters, EXISTS daily_prices for stock on outcome_end_date",
        PreconditionStatus.FAIL,
        "~2026-11-24 (same as P01)",
    ),
    PlanStep(
        "P03", PlanStepStatus.PRECONDITION,
        "Benchmark completeness: 0050 price available on all fill/exit dates",
        "Verify: SELECT date FROM daily_prices WHERE stock_id='0050' AND date IN (...exit_dates...)",
        PreconditionStatus.FAIL,
        "Same as P01; 0050 data needed through outcome_end_date",
    ),
    PlanStep(
        "P04", PlanStepStatus.PRECONDITION,
        "Universe verified: target signals confirmed as v8.0 common stocks",
        "Verify via clean_research_universe + fill_date_contract strict pool",
        PreconditionStatus.PASS,
        "Already verified in S43-S44",
    ),
    PlanStep(
        "P05", PlanStepStatus.PRECONDITION,
        "Execution provenance verified: all execution_date values confirmed as NEXT_OPEN_SIMULATED",
        "Verify via execution_date_auditor: execution_type_verdict = NEXT_OPEN_SIMULATED",
        PreconditionStatus.PASS,
        "Already verified in S43",
    ),
    PlanStep(
        "P06", PlanStepStatus.PRECONDITION,
        "Strategy version verified: V3 parameter hash = be43e8ca977d9fdd",
        "Check PARAMETER_HASH in v3_backtest_engine",
        PreconditionStatus.PASS,
        "Already verified",
    ),
    PlanStep(
        "P07", PlanStepStatus.PRECONDITION,
        "Research authorization granted for 20D outcome computation",
        "Must be granted in a future session prompt — NOT granted by S44",
        PreconditionStatus.FAIL,
        "Requires explicit future session authorization",
    ),
]

_EXECUTION_STEPS = [
    PlanStep(
        "E01", PlanStepStatus.EXECUTION_STEP,
        "Create read-only DB snapshot at execution time",
        "sqlite3.connect(DB_PATH, uri=True) with 'mode=ro'; compute dataset fingerprint",
        PreconditionStatus.UNKNOWN,
        "After P01-P07 pass",
    ),
    PlanStep(
        "E02", PlanStepStatus.EXECUTION_STEP,
        "Build canonical 5D/20D signal pool using fill_date_contract strict criteria",
        "Re-run fill_date_contract with 20D completeness check; apply v8.0 and ETF filters",
        PreconditionStatus.UNKNOWN,
        "After E01",
    ),
    PlanStep(
        "E03", PlanStepStatus.EXECUTION_STEP,
        "Compute per-signal 20D gross return: (exit_close - fill_open) / fill_open",
        "Stock-specific: 20th trading day after fill_date in daily_prices",
        PreconditionStatus.UNKNOWN,
        "After E02",
    ),
    PlanStep(
        "E04", PlanStepStatus.EXECUTION_STEP,
        "Apply FEES_PCT=0.00585 to get net_return",
        "net_return = gross_return - 0.00585",
        PreconditionStatus.UNKNOWN,
        "After E03",
    ),
    PlanStep(
        "E05", PlanStepStatus.EXECUTION_STEP,
        "Compute 0050 benchmark return for same fill/exit dates",
        "Use same date range as signal fill/exit; apply same FEES_PCT",
        PreconditionStatus.UNKNOWN,
        "After E02",
    ),
    PlanStep(
        "E06", PlanStepStatus.EXECUTION_STEP,
        "Aggregate to fill-date cluster means for V3 and each comparator",
        "cluster_mean = mean(net_return for all signals in fill_date cluster)",
        PreconditionStatus.UNKNOWN,
        "After E04",
    ),
    PlanStep(
        "E07", PlanStepStatus.EXECUTION_STEP,
        "Run cluster-aware paired comparison (D_v3 - A_direct per cluster)",
        "delta_i = cluster_mean_v3[i] - cluster_mean_a_direct[i]",
        PreconditionStatus.UNKNOWN,
        "After E06",
    ),
    PlanStep(
        "E08", PlanStepStatus.EXECUTION_STEP,
        "Apply cluster-level t-test on delta vector",
        "t-test on [delta_1, delta_2, ..., delta_n]; CI at 95%",
        PreconditionStatus.UNKNOWN,
        "After E07",
    ),
    PlanStep(
        "E09", PlanStepStatus.EXECUTION_STEP,
        "Apply statistical guardrails (G01-G10)",
        "Run statistical_guardrails.build_statistical_guardrails_report with 20D scope",
        PreconditionStatus.UNKNOWN,
        "After E08",
    ),
    PlanStep(
        "E10", PlanStepStatus.EXECUTION_STEP,
        "Generate reproducibility manifest",
        "Run reproducibility_manifest_s44.build_reproducibility_manifest",
        PreconditionStatus.UNKNOWN,
        "After E08",
    ),
    PlanStep(
        "E11", PlanStepStatus.EXECUTION_STEP,
        "Write results to stock_research.db (research artifact only, not platform.db)",
        "Use storage_adapter.SQLiteResearchStorage; never write to platform.db",
        PreconditionStatus.UNKNOWN,
        "After E09",
    ),
    PlanStep(
        "E12", PlanStepStatus.EXECUTION_STEP,
        "Generate evidence quality report and final verdict",
        "Update evidence_quality_report with 20D findings",
        PreconditionStatus.UNKNOWN,
        "After E09",
    ),
]

_ABORT_CONDITIONS = [
    AbortCondition(
        "A01", "Any signal has outcome_end_date > MAX(daily_prices.date)",
        "ABORT: Immature outcome detected. Do not use partial returns.",
        "Re-evaluate after daily_prices extends to cover all outcome_end_dates",
    ),
    AbortCondition(
        "A02", "Missing price for any stock on fill_date or outcome_end_date",
        "EXCLUDE that signal from comparison; flag in report as MISSING_PRICE",
        "If >10% of signals excluded: abort and report DATA_QUALITY_FAIL",
    ),
    AbortCondition(
        "A03", "V3 parameter hash ≠ be43e8ca977d9fdd",
        "ABORT: Strategy parameters changed. Do not compare with historical results.",
        "Investigation required; do not proceed until hash verified",
    ),
    AbortCondition(
        "A04", "Any code attempts to write to platform.db",
        "ABORT: Production write detected. Rollback immediately.",
        "Research code must only write to stock_research.db",
    ),
    AbortCondition(
        "A05", "Dataset fingerprint at execution time ≠ manifest fingerprint",
        "ABORT: Dataset changed between planning and execution.",
        "Re-compute plan with updated dataset fingerprint",
    ),
    AbortCondition(
        "A06", "model_version contamination detected (v6.0 signals in strict pool)",
        "EXCLUDE v6.0 signals; re-verify fill_date_contract",
        "Report contamination; do not proceed without clean strict pool",
    ),
]

_AUTHORIZATION_ITEMS = [
    AuthorizationItem(
        "AUTH01", "Execute 20D outcome return computation",
        "Session prompt (future session)",
        "BLOCKED — not authorized by S44",
    ),
    AuthorizationItem(
        "AUTH02", "Write 20D outcome returns to any database",
        "Session prompt (future session)",
        "BLOCKED — not authorized by S44",
    ),
    AuthorizationItem(
        "AUTH03", "Use 20D results to update V3 activation status",
        "Session prompt (future session) + sufficient evidence (G03/G04 must pass)",
        "BLOCKED — G03 and G04 still FAIL",
    ),
    AuthorizationItem(
        "AUTH04", "Activate V3 in production",
        "Explicit activation authorization (separate from research authorization)",
        "BLOCKED — multiple preconditions unmet",
    ),
    AuthorizationItem(
        "AUTH05", "Modify cron / Stage B probe",
        "Explicitly declined in S36; requires separate session authorization",
        "BLOCKED — Stage B not authorized",
    ),
]


def build_20d_execution_plan() -> TwentyDayResearchExecutionPlan:
    n_pass = sum(1 for p in _PRECONDITIONS if p.precondition_status == PreconditionStatus.PASS)
    n_fail = sum(1 for p in _PRECONDITIONS if p.precondition_status == PreconditionStatus.FAIL)

    return TwentyDayResearchExecutionPlan(
        session=44,
        plan_version="v1.0-s44",
        plan_status="DESIGN_ONLY_NOT_AUTHORIZED",
        eligibility_preconditions=tuple(_PRECONDITIONS),
        execution_steps=tuple(_EXECUTION_STEPS),
        abort_conditions=tuple(_ABORT_CONDITIONS),
        authorization_items=tuple(_AUTHORIZATION_ITEMS),
        n_preconditions_pass=n_pass,
        n_preconditions_fail=n_fail,
        earliest_eligible_execution_date="~2026-11-24 (fill Oct 13 20D window complete)",
        plan_notes=(
            f"{n_pass}/{len(_PRECONDITIONS)} preconditions pass. "
            f"{n_fail} preconditions fail (outcome not yet mature; authorization not granted). "
            "This plan cannot be self-authorized. Future session must explicitly grant AUTH01+AUTH02."
        ),
    )
