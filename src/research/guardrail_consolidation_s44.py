"""
PART H (P7): Guardrail Consolidation — Session 44.

Integrates S42-S43 guardrail findings into a unified consolidated view.
Explicitly distinguishes between:
  - Engineering-fixable issues (can be corrected by code/data changes)
  - Data-limited issues (require time/data accumulation; cannot be engineered away)

Updated with S44 finding: full v8.0 signal range is Oct 09-28 (not Oct 09-16).
This adds 2 more incomplete fill clusters (fill Oct 22, Oct 28) to the picture,
but does NOT change the strict cluster count or guardrail verdicts.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class GuardrailType(str, Enum):
    ENGINEERING_FIXABLE = "ENGINEERING_FIXABLE"
    DATA_LIMITED = "DATA_LIMITED"
    DESIGN_CONSTRAINT = "DESIGN_CONSTRAINT"


class GuardrailVerdictS44(str, Enum):
    PASS = "PASS"
    CONDITIONAL = "CONDITIONAL"
    FAIL = "FAIL"


@dataclass(frozen=True)
class ConsolidatedGuardrail:
    guardrail_id: str
    name: str
    guardrail_type: GuardrailType
    s42_verdict: GuardrailVerdictS44
    s43_verdict: GuardrailVerdictS44
    s44_verdict: GuardrailVerdictS44
    finding: str
    fix_type: str
    path_to_pass: str
    eta_to_pass: str


@dataclass(frozen=True)
class GuardrailConsolidationReport:
    session: int
    scope_note: str
    guardrails: tuple[ConsolidatedGuardrail, ...]
    n_pass: int
    n_conditional: int
    n_fail: int
    n_engineering_fixable: int
    n_data_limited: int
    n_design_constraint: int
    overall_verdict: GuardrailVerdictS44
    s44_additions: str


_GUARDRAILS = [
    ConsolidatedGuardrail(
        "G01", "Trading Calendar Integrity",
        GuardrailType.ENGINEERING_FIXABLE,
        GuardrailVerdictS44.FAIL,
        GuardrailVerdictS44.CONDITIONAL,
        GuardrailVerdictS44.CONDITIONAL,
        (
            "v6.0 signals excluded in S43 strict pool → 0% non-TD rate for v8.0 signals. "
            "Thin days (Oct 15/19/20) correctly skipped by NEXT_OPEN. "
            "Remaining: calendar source uses DISTINCT date query (includes thin days)."
        ),
        "ENGINEERING_FIXABLE: update TradingCalendarIntegrityAuditor to use ≥50-stock threshold",
        "Replace DISTINCT date query with COUNT(DISTINCT stock_id)>=50 filter",
        "Next session that updates TradingCalendarIntegrityAuditor",
    ),
    ConsolidatedGuardrail(
        "G02", "Metric Label Integrity",
        GuardrailType.ENGINEERING_FIXABLE,
        GuardrailVerdictS44.PASS,
        GuardrailVerdictS44.PASS,
        GuardrailVerdictS44.PASS,
        "S41 corrected all alpha label mismatches (CR-B01-B06). Labels are explicit.",
        "No action needed",
        "Already PASS",
        "N/A",
    ),
    ConsolidatedGuardrail(
        "G03", "Cluster Count Adequacy (≥10)",
        GuardrailType.DATA_LIMITED,
        GuardrailVerdictS44.FAIL,
        GuardrailVerdictS44.FAIL,
        GuardrailVerdictS44.FAIL,
        (
            "S43 strict: 3 complete 5D clusters. "
            "S44 full range: 3 complete + 3 incomplete = 6 total fill clusters. "
            "Strict count remains 3; still far below threshold of 10."
        ),
        "DATA_LIMITED: cannot engineer more clusters from existing data",
        "Accumulate Nov-Dec 2026 cron signals. Each month adds ~12-15 fill clusters.",
        "~Jan 2027 for 10+ strict clusters",
    ),
    ConsolidatedGuardrail(
        "G04", "Holding Period Non-Overlap",
        GuardrailType.DESIGN_CONSTRAINT,
        GuardrailVerdictS44.FAIL,
        GuardrailVerdictS44.FAIL,
        GuardrailVerdictS44.FAIL,
        (
            "Adjacent fill clusters (Oct 13/14/16) have ~80% overlapping 5D windows. "
            "fill Oct 13 (exits Oct 28) and fill Oct 14 (exits Nov 04) share Oct 14-28. "
            "S44 addition: fill Oct 22 (exits ~Nov 25) also overlaps adjacent clusters."
        ),
        "DESIGN_CONSTRAINT: inherent to daily signal cadence + 5D holding period",
        "Use weekly or monthly signals (non-overlapping); or use HAC-corrected SE; or 20D window",
        "20D windows are non-overlapping if clusters spaced ≥4 weeks apart (~Jan 2027)",
    ),
    ConsolidatedGuardrail(
        "G05", "Signal Independence",
        GuardrailType.ENGINEERING_FIXABLE,
        GuardrailVerdictS44.PASS,
        GuardrailVerdictS44.PASS,
        GuardrailVerdictS44.PASS,
        "Cluster-level aggregation used (not signal-level). Correctly implemented.",
        "No action needed",
        "Already PASS",
        "N/A",
    ),
    ConsolidatedGuardrail(
        "G06", "Outcome Contamination (20D vs 5D)",
        GuardrailType.ENGINEERING_FIXABLE,
        GuardrailVerdictS44.PASS,
        GuardrailVerdictS44.PASS,
        GuardrailVerdictS44.PASS,
        "5D and 20D analyses are strictly separated. 20D outcomes not yet computed.",
        "No action needed",
        "Already PASS",
        "N/A",
    ),
    ConsolidatedGuardrail(
        "G07", "Benchmark Consistency",
        GuardrailType.ENGINEERING_FIXABLE,
        GuardrailVerdictS44.PASS,
        GuardrailVerdictS44.PASS,
        GuardrailVerdictS44.PASS,
        "S42 CR-B04 corrected benchmark dates. 0050 computed from same fill/exit dates.",
        "No action needed",
        "Already PASS",
        "N/A",
    ),
    ConsolidatedGuardrail(
        "G08", "Multiple Comparison Correction",
        GuardrailType.ENGINEERING_FIXABLE,
        GuardrailVerdictS44.CONDITIONAL,
        GuardrailVerdictS44.CONDITIONAL,
        GuardrailVerdictS44.CONDITIONAL,
        (
            "3 simultaneous comparisons (A/B/C) without Bonferroni. "
            "Since all 3 are SIGNIFICANCE_INCONCLUSIVE, Bonferroni does not change verdict."
        ),
        "Minor: report as family-wise analysis",
        "Add Bonferroni note to research reports",
        "Next research report revision",
    ),
    ConsolidatedGuardrail(
        "G09", "No Look-Ahead Leakage",
        GuardrailType.ENGINEERING_FIXABLE,
        GuardrailVerdictS44.PASS,
        GuardrailVerdictS44.PASS,
        GuardrailVerdictS44.PASS,
        "NEXT_OPEN architecture verified. foe_v1 engine unchanged. No future data in signals.",
        "No action needed",
        "Already PASS",
        "N/A",
    ),
    ConsolidatedGuardrail(
        "G10", "Sample Universe Stability (ETF)",
        GuardrailType.ENGINEERING_FIXABLE,
        GuardrailVerdictS44.CONDITIONAL,
        GuardrailVerdictS44.CONDITIONAL,
        GuardrailVerdictS44.CONDITIONAL,
        (
            "1.8% ETF-like signals in Oct 2026 pool (stock_id LIKE '00%'). "
            "Official ETF rate: 9.52% (S38). stocks table lacks stock_type column."
        ),
        "Minor: add stock_type column to stocks table (non-research change)",
        "Add stock_type column; filter ETFs from comparison pool",
        "Requires schema change to stocks table (future session)",
    ),
]


def build_guardrail_consolidation_report(conn: sqlite3.Connection) -> GuardrailConsolidationReport:
    # Verify current DB state matches S44 scope
    full_v8_dates = conn.execute(
        "SELECT DISTINCT trade_date FROM forward_signals "
        "WHERE model_version='v8.0' AND trade_signal IN ('buy','strong_buy') "
        "ORDER BY trade_date"
    ).fetchall()
    n_v8_signal_dates = len(full_v8_dates)

    scope_note = (
        f"S44 scope: ALL v8.0 signals (Oct 09-28). "
        f"v8.0 signal dates: {n_v8_signal_dates}. "
        f"Fill clusters: 6 total (3 strict-5D-complete, 3 incomplete). "
        "G03/G04 verdicts unchanged by S44 scope expansion."
    )

    guardrails = tuple(_GUARDRAILS)
    n_pass = sum(1 for g in guardrails if g.s44_verdict == GuardrailVerdictS44.PASS)
    n_cond = sum(1 for g in guardrails if g.s44_verdict == GuardrailVerdictS44.CONDITIONAL)
    n_fail = sum(1 for g in guardrails if g.s44_verdict == GuardrailVerdictS44.FAIL)

    n_eng = sum(1 for g in guardrails if g.guardrail_type == GuardrailType.ENGINEERING_FIXABLE)
    n_data = sum(1 for g in guardrails if g.guardrail_type == GuardrailType.DATA_LIMITED)
    n_design = sum(1 for g in guardrails if g.guardrail_type == GuardrailType.DESIGN_CONSTRAINT)

    overall = (
        GuardrailVerdictS44.FAIL if n_fail > 0 else
        GuardrailVerdictS44.CONDITIONAL if n_cond > 0 else
        GuardrailVerdictS44.PASS
    )

    return GuardrailConsolidationReport(
        session=44,
        scope_note=scope_note,
        guardrails=guardrails,
        n_pass=n_pass,
        n_conditional=n_cond,
        n_fail=n_fail,
        n_engineering_fixable=n_eng,
        n_data_limited=n_data,
        n_design_constraint=n_design,
        overall_verdict=overall,
        s44_additions=(
            "S44 extends scope to full v8.0 range (Oct 09-28). "
            "New finding: fill Oct 22 (n=23) and fill Oct 28 (n=19) are additional incomplete clusters. "
            "They do NOT change G03 (still <10 strict clusters) or G04 (overlap still present). "
            "G01 path-to-PASS identified: update calendar source to ≥50-stock threshold."
        ),
    )
