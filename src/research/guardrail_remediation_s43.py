"""
PART G: Guardrail Remediation Analysis — Session 43.

For each S42 guardrail that FAILED or was CONDITIONAL, documents:
  - before state (S42 finding)
  - root cause
  - remediation action taken in S43
  - after state
  - remaining blockers

S42 guardrail summary:
  G01 FAIL    — 39.1% non-trading day signals
  G02 PASS    — trading day completeness
  G03 FAIL    — cluster count < 5
  G04 FAIL    — window overlap between clusters
  G05 PASS    — benchmark availability
  G06 PASS    — model version coverage
  G07 PASS    — signal count per cluster
  G08 CONDITIONAL — fees applied
  G09 PASS    — execution type documented
  G10 CONDITIONAL — ETF contamination

S43 remediations:
  G01: v6.0 exclusion reduces non-TD rate to 0% (strict v8.0 set only)
       Remaining: thin-day ambiguity (Oct 15/19/20) in calendar
  G03: still 3-4 strict clusters; not remediable without more data
  G04: 5D windows from adjacent fill dates still overlap
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class GuardrailStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    CONDITIONAL = "CONDITIONAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RemediationStatus(str, Enum):
    FULLY_REMEDIATED = "FULLY_REMEDIATED"
    PARTIALLY_REMEDIATED = "PARTIALLY_REMEDIATED"
    NOT_REMEDIABLE = "NOT_REMEDIABLE"
    NO_ACTION_NEEDED = "NO_ACTION_NEEDED"


@dataclass(frozen=True)
class GuardrailRemediationRecord:
    guardrail_id: str
    guardrail_name: str
    s42_status: GuardrailStatus
    s42_finding: str
    root_cause: str
    remediation_action: str
    s43_status: GuardrailStatus
    s43_finding: str
    remediation_status: RemediationStatus
    remaining_blockers: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class GuardrailRemediationReport:
    session: int
    records: tuple[GuardrailRemediationRecord, ...]
    n_fully_remediated: int
    n_partially_remediated: int
    n_not_remediable: int
    n_no_action_needed: int
    n_pass_after_remediation: int
    n_fail_after_remediation: int
    n_conditional_after_remediation: int
    overall_status: str


_REMEDIATION_DATA = [
    GuardrailRemediationRecord(
        guardrail_id="G01",
        guardrail_name="Calendar Integrity",
        s42_status=GuardrailStatus.FAIL,
        s42_finding="39.1% (107/274) of signals generated on non-trading days (Oct 09-11)",
        root_cause=(
            "v6.0 cron bug: ran on National Day holiday (Oct 09-10) and Sunday (Oct 11). "
            "v6.0 was replaced by v8.0 on Oct 12. "
            "These signals contaminate the comparison pool."
        ),
        remediation_action=(
            "S43 FillDateComparisonContract excludes v6.0 signals. "
            "v8.0-strict pool (Oct 12-16 signal dates) has 0 non-trading day signals. "
            "Thin days (Oct 15, 19, 20) correctly skipped by NEXT_OPEN engine."
        ),
        s43_status=GuardrailStatus.CONDITIONAL,
        s43_finding=(
            "v8.0-strict pool: 0% non-trading day rate (PASS). "
            "Thin days (Oct 15, 19, 20) still present in daily_prices calendar — "
            "NEXT_OPEN correctly skips them, but calendar definition remains CONDITIONAL."
        ),
        remediation_status=RemediationStatus.PARTIALLY_REMEDIATED,
        remaining_blockers=(
            "Thin days (Oct 15, 19, 20) still counted as 'trading days' by DISTINCT date query. "
            "Must use ≥50-stock threshold for official calendar.",
        ),
        notes="From FAIL to CONDITIONAL; not fully PASS until calendar source corrected.",
    ),
    GuardrailRemediationRecord(
        guardrail_id="G02",
        guardrail_name="Trading Day Completeness",
        s42_status=GuardrailStatus.PASS,
        s42_finding="Trading day calendar covers all comparison dates",
        root_cause="N/A — was PASS",
        remediation_action="No action needed. NEXT_OPEN engine uses stock-specific dates correctly.",
        s43_status=GuardrailStatus.PASS,
        s43_finding="PASS maintained. Stock-specific execution_date verified.",
        remediation_status=RemediationStatus.NO_ACTION_NEEDED,
        remaining_blockers=(),
        notes="",
    ),
    GuardrailRemediationRecord(
        guardrail_id="G03",
        guardrail_name="Sufficient Cluster Count (≥5)",
        s42_status=GuardrailStatus.FAIL,
        s42_finding="Only 5 fill-date clusters (minimum requirement: 5+, ideal: 10+)",
        root_cause=(
            "Only 2 months of forward_signals exist (Oct-Nov 2026). "
            "Cron has only been running since Oct 2026. "
            "Data expansion requires time."
        ),
        remediation_action=(
            "S43 strict analysis uses only 3 complete clusters (fill Oct 13, 14, 16). "
            "Cannot create more clusters from existing data. "
            "EvidenceExpansionAuditor confirms NO_NEW_ELIGIBLE_WINDOW."
        ),
        s43_status=GuardrailStatus.FAIL,
        s43_finding=(
            "Still only 3 complete v8.0 clusters. "
            "Statistical power insufficient for SIGNIFICANCE conclusions."
        ),
        remediation_status=RemediationStatus.NOT_REMEDIABLE,
        remaining_blockers=(
            "Cannot accumulate more clusters without waiting for more signal data. "
            "Nov-Dec 2026 cron accumulation is the only path forward.",
        ),
        notes="Fundamental data scarcity; not a correctness issue.",
    ),
    GuardrailRemediationRecord(
        guardrail_id="G04",
        guardrail_name="Window Overlap < 50%",
        s42_status=GuardrailStatus.FAIL,
        s42_finding="Adjacent 5D windows (fill Oct 13 and Oct 14) overlap 4 out of 5 days",
        root_cause=(
            "Signal generation is daily; adjacent fill dates create consecutive 5D windows. "
            "fill Oct 13 (exit Oct 28) and fill Oct 14 (exit Nov 04) share Oct 14-28. "
            "80% overlap between adjacent clusters."
        ),
        remediation_action=(
            "No structural fix possible without non-overlapping signal generation. "
            "Could use 1D or 2D windows if sufficient data exists; not applicable here. "
            "Or skip every other cluster; reduces evidence further."
        ),
        s43_status=GuardrailStatus.FAIL,
        s43_finding=(
            "Windows still overlap. fill Oct 13 / fill Oct 14 / fill Oct 16 share "
            "trading days within their respective 5D windows."
        ),
        remediation_status=RemediationStatus.NOT_REMEDIABLE,
        remaining_blockers=(
            "Overlap is inherent to daily signal generation + 5D window combination. "
            "Requires either longer holding period (non-overlapping) or fewer signals per week.",
        ),
        notes="Affects statistical independence assumption of t-test.",
    ),
    GuardrailRemediationRecord(
        guardrail_id="G05",
        guardrail_name="Benchmark Availability",
        s42_status=GuardrailStatus.PASS,
        s42_finding="0050 price available for all comparison dates",
        root_cause="N/A — was PASS",
        remediation_action="No action needed.",
        s43_status=GuardrailStatus.PASS,
        s43_finding="PASS maintained. 0050 available on all fill dates.",
        remediation_status=RemediationStatus.NO_ACTION_NEEDED,
        remaining_blockers=(),
        notes="",
    ),
    GuardrailRemediationRecord(
        guardrail_id="G06",
        guardrail_name="Model Version Coverage",
        s42_status=GuardrailStatus.PASS,
        s42_finding="v8.0 signals present on all comparison dates",
        root_cause="N/A — was PASS",
        remediation_action="S43 strengthens this: explicitly isolates v8.0 signals only.",
        s43_status=GuardrailStatus.PASS,
        s43_finding="PASS maintained and strengthened by v8.0-strict filter.",
        remediation_status=RemediationStatus.NO_ACTION_NEEDED,
        remaining_blockers=(),
        notes="",
    ),
    GuardrailRemediationRecord(
        guardrail_id="G07",
        guardrail_name="Signal Count Per Cluster ≥ 10",
        s42_status=GuardrailStatus.PASS,
        s42_finding="All 5 clusters have n ≥ 10 signals",
        root_cause="N/A — was PASS",
        remediation_action="No action needed. 3 strict clusters: n=46, 27, 55.",
        s43_status=GuardrailStatus.PASS,
        s43_finding="PASS maintained. Min cluster size = 27 (fill Oct 14).",
        remediation_status=RemediationStatus.NO_ACTION_NEEDED,
        remaining_blockers=(),
        notes="",
    ),
    GuardrailRemediationRecord(
        guardrail_id="G08",
        guardrail_name="Transaction Costs Applied",
        s42_status=GuardrailStatus.CONDITIONAL,
        s42_finding="FEES_PCT=0.00585 applied but not verified against broker schedule",
        root_cause="Research assumption; not from live broker confirmation.",
        remediation_action="Maintained in S43. No new data to verify against broker.",
        s43_status=GuardrailStatus.CONDITIONAL,
        s43_finding="CONDITIONAL maintained. Same 0.585% assumption.",
        remediation_status=RemediationStatus.NO_ACTION_NEEDED,
        remaining_blockers=("Fee schedule unverified against live broker rates.",),
        notes="Reasonable assumption; small sensitivity (±0.1%).",
    ),
    GuardrailRemediationRecord(
        guardrail_id="G09",
        guardrail_name="Execution Type Documented",
        s42_status=GuardrailStatus.PASS,
        s42_finding="NEXT_OPEN documented; not actual broker fills",
        root_cause="N/A — was PASS",
        remediation_action=(
            "S43 ExecutionDateIntegrityReport strengthens this: "
            "formal DateFieldDefinition for all 5 date fields."
        ),
        s43_status=GuardrailStatus.PASS,
        s43_finding="PASS strengthened. All execution fields formally defined.",
        remediation_status=RemediationStatus.NO_ACTION_NEEDED,
        remaining_blockers=(),
        notes="",
    ),
    GuardrailRemediationRecord(
        guardrail_id="G10",
        guardrail_name="ETF Contamination < 5%",
        s42_status=GuardrailStatus.CONDITIONAL,
        s42_finding="ETF contamination ~0.7% (by stock_id LIKE '00%' proxy); minor",
        root_cause="stocks table has no stock_type column; classification via stock_id prefix.",
        remediation_action=(
            "S43 analysis uses same ETF proxy. "
            "No new classification data available. "
            "Official classification completed in S38 but not queryable from research modules."
        ),
        s43_status=GuardrailStatus.CONDITIONAL,
        s43_finding="CONDITIONAL maintained. ETF proxy rate remains ~0.7%. Under 5% threshold.",
        remediation_status=RemediationStatus.NO_ACTION_NEEDED,
        remaining_blockers=("stocks table lacks stock_type column for precise ETF classification.",),
        notes="Minor issue; below 5% threshold.",
    ),
]


def build_guardrail_remediation_report(conn: sqlite3.Connection) -> GuardrailRemediationReport:
    records = tuple(_REMEDIATION_DATA)

    n_full = sum(1 for r in records if r.remediation_status == RemediationStatus.FULLY_REMEDIATED)
    n_part = sum(1 for r in records if r.remediation_status == RemediationStatus.PARTIALLY_REMEDIATED)
    n_no = sum(1 for r in records if r.remediation_status == RemediationStatus.NOT_REMEDIABLE)
    n_na = sum(1 for r in records if r.remediation_status == RemediationStatus.NO_ACTION_NEEDED)
    n_pass = sum(1 for r in records if r.s43_status == GuardrailStatus.PASS)
    n_fail = sum(1 for r in records if r.s43_status == GuardrailStatus.FAIL)
    n_cond = sum(1 for r in records if r.s43_status == GuardrailStatus.CONDITIONAL)

    # Determine overall
    if n_fail == 0 and n_cond == 0:
        overall = "GUARDRAILS_PASS"
    elif n_fail == 0:
        overall = "GUARDRAILS_CONDITIONAL"
    else:
        overall = "GUARDRAILS_FAIL"

    return GuardrailRemediationReport(
        session=43,
        records=records,
        n_fully_remediated=n_full,
        n_partially_remediated=n_part,
        n_not_remediable=n_no,
        n_no_action_needed=n_na,
        n_pass_after_remediation=n_pass,
        n_fail_after_remediation=n_fail,
        n_conditional_after_remediation=n_cond,
        overall_status=overall,
    )
