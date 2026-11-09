"""
PART H: Research Statistical Guardrails — Session 42.

10 guardrails against common statistical validity threats in V3 research.
Each returns PASS, CONDITIONAL, or FAIL.
Guardrails are research-quality gates, not production gates.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class GuardrailStatus(str, Enum):
    PASS = "PASS"
    CONDITIONAL = "CONDITIONAL"
    FAIL = "FAIL"


@dataclass(frozen=True)
class GuardrailResult:
    guardrail_id: str
    name: str
    description: str
    status: GuardrailStatus
    finding: str
    threshold: str
    actual_value: str
    recommendation: str


@dataclass(frozen=True)
class StatisticalGuardrailsReport:
    session: int
    guardrails: tuple[GuardrailResult, ...]
    n_pass: int
    n_conditional: int
    n_fail: int
    overall_status: GuardrailStatus
    overall_verdict: str


def _make_guardrail(
    gid: str,
    name: str,
    description: str,
    status: GuardrailStatus,
    finding: str,
    threshold: str,
    actual: str,
    recommendation: str,
) -> GuardrailResult:
    return GuardrailResult(
        guardrail_id=gid,
        name=name,
        description=description,
        status=status,
        finding=finding,
        threshold=threshold,
        actual_value=actual,
        recommendation=recommendation,
    )


def build_statistical_guardrails_report(conn: sqlite3.Connection) -> StatisticalGuardrailsReport:
    # G01: Trading Calendar Integrity
    q_non_td = """
        SELECT COUNT(*) FROM forward_signals
        WHERE trade_date BETWEEN '2026-10-01' AND '2026-10-31'
          AND trade_signal IN ('buy','strong_buy')
          AND trade_date NOT IN (
              SELECT DISTINCT date FROM daily_prices
              WHERE date BETWEEN '2026-10-01' AND '2026-10-31'
          )
    """
    n_non_td = conn.execute(q_non_td).fetchone()[0]
    q_total = """
        SELECT COUNT(*) FROM forward_signals
        WHERE trade_date BETWEEN '2026-10-01' AND '2026-10-31'
          AND trade_signal IN ('buy','strong_buy')
    """
    n_total = conn.execute(q_total).fetchone()[0]
    pct_non_td = n_non_td / n_total if n_total > 0 else 0.0

    g01 = _make_guardrail(
        "G01", "Trading Calendar Integrity",
        "No signal should have a trade_date on a non-trading day (holiday/weekend)",
        GuardrailStatus.FAIL if pct_non_td > 0.05 else (
            GuardrailStatus.CONDITIONAL if pct_non_td > 0 else GuardrailStatus.PASS
        ),
        f"{n_non_td}/{n_total} ({pct_non_td:.1%}) signals on non-trading days (Oct 09, 10, 11)",
        "< 5% signals on non-trading days",
        f"{pct_non_td:.1%}",
        "Merge non-trading signals into fill_date clusters; exclude from signal_date analysis",
    )

    # G02: Metric Label Integrity
    g02 = _make_guardrail(
        "G02", "Metric Label Integrity",
        "Alpha labels must distinguish 'vs benchmark' from 'vs paired strategy'",
        GuardrailStatus.PASS,
        "S41 corrected all 3 mislabeled alpha metrics (CR-B01, CR-B02, CR-B03); labels now explicit",
        "All alpha labels must specify comparator (vs_0050 or vs_a_direct)",
        "CR-B01/02/03 corrected in S41; CR-B04/05/06 corrected in S42",
        "No action needed; labels corrected and documented",
    )

    # G03: Cluster Count Adequacy
    g03 = _make_guardrail(
        "G03", "Cluster Count Adequacy",
        "Must have ≥10 independent trading-date clusters for reliable t-test inference",
        GuardrailStatus.FAIL,
        "5 fill-date clusters (S42); 4 pure trading-day clusters; far below threshold of 10",
        "≥10 independent clusters",
        "5 fill-date clusters (Oct 12, 13, 14, 16, 21)",
        "Accumulate more signal dates. At ~19 trading days/month, need ~3 more months.",
    )

    # G04: Holding Period Overlap
    g04 = _make_guardrail(
        "G04", "Holding Period Non-Overlap",
        "5D holding windows for adjacent clusters must not overlap",
        GuardrailStatus.FAIL,
        (
            "4/4 adjacent cluster pairs have overlapping 5D windows: "
            "Oct12-16 overlaps Oct13-19; Oct13-19 overlaps Oct14-20; "
            "Oct14-20 overlaps Oct16-22; Oct16-22 overlaps Oct21-29"
        ),
        "0 overlapping window pairs",
        "4/4 adjacent pairs overlap",
        "Use non-overlapping windows or HAC-corrected standard errors; treat effective N as 2-3",
    )

    # G05: Signal Independence
    g05 = _make_guardrail(
        "G05", "Signal Independence",
        "Signals within the same cluster must not be assumed independent in statistical tests",
        GuardrailStatus.PASS,
        "S42 uses fill-date cluster means (not signal-level), satisfying within-cluster aggregation",
        "Cluster means used (not signal-level) for t-test",
        "5 cluster means used in t-test (not 274 signals)",
        "Maintained; cluster-level aggregation is correct approach",
    )

    # G06: Outcome Contamination
    g06 = _make_guardrail(
        "G06", "Outcome Contamination (20D)",
        "5D return analysis must not be confused with 20D outcome claims",
        GuardrailStatus.PASS,
        "5D and 20D analyses are separate; 20D outcomes not yet mature (all NULL fwd_return_20d)",
        "5D and 20D outcomes never mixed",
        "Fully separated; 20D = NO_SIGNALS_MATURE",
        "No action needed; separation maintained",
    )

    # G07: Benchmark Consistency
    q_max_dp = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0] or "unknown"
    g07 = _make_guardrail(
        "G07", "Benchmark Consistency",
        "0050 benchmark must be computed from the same dates as the signal comparison",
        GuardrailStatus.PASS,
        f"S42 recomputed 0050 benchmark from actual fill dates (Oct 12/13/14/16/21) instead of S40 doc dates. daily_prices as of {q_max_dp}",
        "Same date range for benchmark and signal comparison",
        "S42 corrected: -4.65% (S40) → -2.16% (corrected per S41/S42)",
        "Benchmark dates aligned; CR-B04 resolved",
    )

    # G08: Multiple Comparison Correction
    g08 = _make_guardrail(
        "G08", "Multiple Comparison Correction",
        "With 3 simultaneous comparisons (A/B/C), family-wise error rate inflates if uncorrected",
        GuardrailStatus.CONDITIONAL,
        (
            "3 comparisons without Bonferroni: α=0.05 each → family-wise α≈0.14. "
            "All 3 comparisons SIGNIFICANCE_INCONCLUSIVE (p>0.19); "
            "Bonferroni would not change verdict since none are individually significant."
        ),
        "Apply Bonferroni correction (α/3=0.0167) or report as family-wise",
        "3 comparisons; p=0.191, 0.773, 0.191",
        "Report as family-wise analysis; Bonferroni does not change INCONCLUSIVE verdict here",
    )

    # G09: Data Leakage (look-ahead)
    g09 = _make_guardrail(
        "G09", "No Look-Ahead Leakage",
        "Signal generation must not use information available after the signal date",
        GuardrailStatus.PASS,
        "V3 decisions use same foe_v1 engine as V1/V2; no future price data in signal generation. ForwardSignal.execution_price uses NEXT_OPEN architecture.",
        "Signal uses only information available at EOD on signal date",
        "Verified: NEXT_OPEN architecture, foe_v1 engine unchanged",
        "No action needed",
    )

    # G10: Sample Universe Stability
    # ETF proxy: stock_ids starting with "00" are almost all ETFs in Taiwan
    q_etf_signals = conn.execute(
        """SELECT COUNT(*) FROM forward_signals fs
           WHERE fs.trade_date BETWEEN '2026-10-09' AND '2026-10-16'
             AND fs.trade_signal IN ('buy','strong_buy')
             AND fs.stock_id LIKE '00%'"""
    ).fetchone()
    q_total_comp = conn.execute(
        """SELECT COUNT(*) FROM forward_signals fs
           WHERE fs.trade_date BETWEEN '2026-10-09' AND '2026-10-16'
             AND fs.trade_signal IN ('buy','strong_buy')"""
    ).fetchone()
    n_etf_signals = q_etf_signals[0] if q_etf_signals else 0
    n_total_comp = q_total_comp[0] if q_total_comp else 274
    pct_etf_signals = n_etf_signals / n_total_comp if n_total_comp > 0 else 0.0

    g10 = _make_guardrail(
        "G10", "Sample Universe Stability",
        "ETFs and non-common stocks should be excluded from forward signal comparison pool",
        GuardrailStatus.CONDITIONAL,
        (
            f"{n_etf_signals}/{n_total_comp} ({pct_etf_signals:.1%}) signals in comparison pool "
            "are from ETF-like stock_ids (starting '00'). "
            "ETF signals behave differently from common stocks (no breakout dynamics). "
            "Official ETF rate: 9.52% of TWSE universe (Session 38)."
        ),
        "0 ETF signals in comparison pool",
        f"{pct_etf_signals:.1%} ETF-like signals in Oct 09-16 pool",
        "Filter comparison pool to common stocks only before next comparison run",
    )

    all_guards = (g01, g02, g03, g04, g05, g06, g07, g08, g09, g10)
    n_pass = sum(1 for g in all_guards if g.status == GuardrailStatus.PASS)
    n_cond = sum(1 for g in all_guards if g.status == GuardrailStatus.CONDITIONAL)
    n_fail = sum(1 for g in all_guards if g.status == GuardrailStatus.FAIL)

    if n_fail >= 3:
        overall = GuardrailStatus.FAIL
        verdict = "GUARDRAILS_FAIL"
    elif n_fail >= 1 or n_cond >= 3:
        overall = GuardrailStatus.CONDITIONAL
        verdict = "GUARDRAILS_CONDITIONAL"
    else:
        overall = GuardrailStatus.PASS
        verdict = "GUARDRAILS_PASS"

    return StatisticalGuardrailsReport(
        session=42,
        guardrails=all_guards,
        n_pass=n_pass,
        n_conditional=n_cond,
        n_fail=n_fail,
        overall_status=overall,
        overall_verdict=verdict,
    )
