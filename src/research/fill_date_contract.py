"""
PART D: Fill-Date Comparison Contract — Session 43.

Defines requirements for a fair V1/V2/V3 comparison:
- Same tradable universe (v8.0 signals only)
- Same execution calendar (stock-specific price availability)
- Same holding period definition (5 trading days per stock)
- Same benchmark

Defines STRICT vs CONDITIONAL pairing policies.

Key correction from S43: v6.0 signals must be excluded.
5D window requires 5 stock-specific exit days after fill_date.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class PairingVerdict(str, Enum):
    STRICTLY_COMPARABLE = "STRICTLY_COMPARABLE"
    CONDITIONALLY_COMPARABLE = "CONDITIONALLY_COMPARABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class ComparisonDimension(str, Enum):
    TRADABLE_UNIVERSE = "TRADABLE_UNIVERSE"
    ENTRY_OPPORTUNITY = "ENTRY_OPPORTUNITY"
    MARKET_CALENDAR = "MARKET_CALENDAR"
    PRICE_AVAILABILITY = "PRICE_AVAILABILITY"
    HOLDING_PERIOD = "HOLDING_PERIOD"
    BENCHMARK = "BENCHMARK"
    TRANSACTION_COSTS = "TRANSACTION_COSTS"
    CAPITAL_EXPOSURE = "CAPITAL_EXPOSURE"
    MODEL_VERSION = "MODEL_VERSION"
    OUTCOME_MATURITY = "OUTCOME_MATURITY"


@dataclass(frozen=True)
class ContractDimension:
    dimension: ComparisonDimension
    requirement: str
    s42_status: str    # what S42 did
    s43_status: str    # corrected status in S43
    verdict: PairingVerdict
    notes: str


@dataclass(frozen=True)
class SignalCohort:
    cohort_id: str
    signal_dates: tuple[str, ...]
    model_version: str
    n_signals: int
    n_with_execution_date: int
    n_with_complete_5d_window: int
    pairing_verdict: PairingVerdict
    exclusion_reasons: tuple[str, ...]


@dataclass(frozen=True)
class FillDateComparisonContract:
    session: int
    contract_dimensions: tuple[ContractDimension, ...]
    cohorts: tuple[SignalCohort, ...]
    n_strict_eligible: int
    n_conditional_eligible: int
    n_not_comparable: int
    strict_signal_dates: tuple[str, ...]    # signal dates passing strict filter
    conditional_signal_dates: tuple[str, ...]  # additional dates in conditional
    excluded_signal_dates: tuple[str, ...]
    overall_verdict: PairingVerdict
    comparison_note: str


def _count_complete_5d(conn: sqlite3.Connection, signal_date: str, fill_date: str) -> int:
    stocks = [r[0] for r in conn.execute(
        "SELECT stock_id FROM forward_signals WHERE trade_date=? AND trade_signal IN ('buy','strong_buy') AND model_version='v8.0'",
        (signal_date,)
    ).fetchall()]
    if not stocks:
        return 0
    complete = 0
    for s in stocks:
        rows = conn.execute(
            "SELECT date FROM daily_prices WHERE stock_id=? AND date>? ORDER BY date LIMIT 5",
            (s, fill_date)
        ).fetchall()
        if len(rows) >= 5:
            complete += 1
    return complete


def build_fill_date_comparison_contract(conn: sqlite3.Connection) -> FillDateComparisonContract:
    # Contract dimensions
    dims = (
        ContractDimension(
            ComparisonDimension.MODEL_VERSION,
            "All compared signals must use same model_version (v8.0 for production)",
            "Mixed: v6.0 (Oct 09-11) + v8.0 (Oct 12-16) in same cluster",
            "v8.0 STRICT: exclude v6.0 signals from comparison pool",
            PairingVerdict.CONDITIONALLY_COMPARABLE,
            "v6.0 signals in Oct 09-11 must be excluded for a fair v8.0 comparison",
        ),
        ContractDimension(
            ComparisonDimension.TRADABLE_UNIVERSE,
            "Common stocks only (stock_id NOT like '00%') with v8.0 model",
            "All signals including ETF-like stocks",
            "Filter to v8.0 signals; note ETF presence (G10 CONDITIONAL)",
            PairingVerdict.CONDITIONALLY_COMPARABLE,
            "ETF contamination ~0.7%; minor but unresolved",
        ),
        ContractDimension(
            ComparisonDimension.MARKET_CALENDAR,
            "execution_date must be a real trading day (≥50 stocks in daily_prices)",
            "Used next-TD from daily_prices including 0050-only thin days",
            "Use stock-specific execution_date from forward_signals (skips thin days correctly)",
            PairingVerdict.STRICTLY_COMPARABLE,
            "execution_date correctly skips thin days (Oct 15, 19, 20)",
        ),
        ContractDimension(
            ComparisonDimension.PRICE_AVAILABILITY,
            "5 stock-specific exit dates must exist in daily_prices after fill_date",
            "LIMIT 5 query per stock; some clusters incomplete (Oct 21 cluster)",
            "Verify 5 exit dates per stock; exclude incomplete signals",
            PairingVerdict.CONDITIONALLY_COMPARABLE,
            "Oct 21 cluster: most stocks lack 5 exit dates (data gap Oct 22-28, Nov 04-05)",
        ),
        ContractDimension(
            ComparisonDimension.HOLDING_PERIOD,
            "5 trading days per stock, same exit date approach for all strategies",
            "5 calendar days (horizon_days=5) in V3ComparisonEngine",
            "5 stock-specific trading days (LIMIT 5 after fill_date in daily_prices)",
            PairingVerdict.CONDITIONALLY_COMPARABLE,
            "V3ComparisonEngine uses calendar days; this contract uses trading days",
        ),
        ContractDimension(
            ComparisonDimension.BENCHMARK,
            "0050 returns computed from same fill/exit dates as signals",
            "S40: wrong dates used (-4.65%). S42: corrected (-2.16%)",
            "Compute 0050 from stock-specific fill/exit dates per cluster",
            PairingVerdict.STRICTLY_COMPARABLE,
            "S42 CR-B04 corrected; maintained in S43",
        ),
        ContractDimension(
            ComparisonDimension.TRANSACTION_COSTS,
            "Same FEES_PCT=0.00585 (0.585%) for all strategies",
            "0.585% applied uniformly",
            "0.585% maintained; identical for all strategies",
            PairingVerdict.STRICTLY_COMPARABLE,
            "No change needed",
        ),
        ContractDimension(
            ComparisonDimension.ENTRY_OPPORTUNITY,
            "V3 and A_direct must have same available signals to decide on",
            "Same forward_signals pool used for all strategies",
            "Same pool; decision differences are from strategy logic only",
            PairingVerdict.STRICTLY_COMPARABLE,
            "V3 may WAIT or AVOID on signals that A_direct enters immediately",
        ),
        ContractDimension(
            ComparisonDimension.OUTCOME_MATURITY,
            "5D window fully within available daily_prices data",
            "Oct 21 cluster used even though exit data is sparse",
            "Flag Oct 21 cluster as INCOMPLETE; exclude from strict comparison",
            PairingVerdict.CONDITIONALLY_COMPARABLE,
            "Oct 21 cluster: exit dates Oct 22+Oct 28 only (need Nov 04+ for 5D)",
        ),
    )

    # Classify signal date cohorts
    signal_dates = [
        ("2026-10-09", "2026-10-12", "v6.0"),  # fill Oct 12
        ("2026-10-10", "2026-10-12", "v6.0"),
        ("2026-10-11", "2026-10-12", "v6.0"),
        ("2026-10-12", "2026-10-13", "v8.0"),  # fill Oct 13
        ("2026-10-13", "2026-10-14", "v8.0"),  # fill Oct 14
        ("2026-10-14", "2026-10-16", "v8.0"),  # fill Oct 16
        ("2026-10-16", "2026-10-21", "v8.0"),  # fill Oct 21 (INCOMPLETE)
    ]

    cohorts = []
    strict_dates = []
    conditional_dates = []
    excluded_dates = []

    for sd, fd, mv in signal_dates:
        n_total = conn.execute(
            "SELECT COUNT(*) FROM forward_signals WHERE trade_date=? AND trade_signal IN ('buy','strong_buy')",
            (sd,)
        ).fetchone()[0]
        n_with_exec = conn.execute(
            "SELECT COUNT(*) FROM forward_signals WHERE trade_date=? AND trade_signal IN ('buy','strong_buy') AND execution_date IS NOT NULL",
            (sd,)
        ).fetchone()[0]
        n_complete = _count_complete_5d(conn, sd, fd) if mv == "v8.0" else 0

        if mv == "v6.0":
            verdict = PairingVerdict.NOT_COMPARABLE
            reasons = ("model_version_v6.0_not_v8.0", "non_trading_day_signal")
            excluded_dates.append(sd)
        elif fd == "2026-10-21":
            # Check if exit data is insufficient
            # 5 days after Oct 21: Oct 22, Oct 28, Nov 04, Nov 05 → only 4
            verdict = PairingVerdict.CONDITIONALLY_COMPARABLE
            reasons = ("fill_date_oct21_exit_data_incomplete",)
            conditional_dates.append(sd)
        else:
            verdict = PairingVerdict.STRICTLY_COMPARABLE
            reasons = ()
            strict_dates.append(sd)

        cohorts.append(SignalCohort(
            cohort_id=f"{sd}_{mv}",
            signal_dates=(sd,),
            model_version=mv,
            n_signals=n_total,
            n_with_execution_date=n_with_exec,
            n_with_complete_5d_window=n_complete,
            pairing_verdict=verdict,
            exclusion_reasons=reasons,
        ))

    n_strict = sum(c.n_signals for c in cohorts if c.pairing_verdict == PairingVerdict.STRICTLY_COMPARABLE)
    n_cond = sum(c.n_signals for c in cohorts if c.pairing_verdict == PairingVerdict.CONDITIONALLY_COMPARABLE)
    n_excl = sum(c.n_signals for c in cohorts if c.pairing_verdict == PairingVerdict.NOT_COMPARABLE)

    n_strict_dates = len(strict_dates)
    if n_strict_dates >= 3:
        overall = PairingVerdict.STRICTLY_COMPARABLE
        note = f"{n_strict_dates} strict signal dates ({n_strict} signals), {len(conditional_dates)} conditional, {len(excluded_dates)} excluded"
    elif n_strict_dates + len(conditional_dates) >= 2:
        overall = PairingVerdict.CONDITIONALLY_COMPARABLE
        note = f"Only {n_strict_dates} strict dates; overall CONDITIONAL"
    else:
        overall = PairingVerdict.NOT_COMPARABLE
        note = "Insufficient comparable signal dates"

    return FillDateComparisonContract(
        session=43,
        contract_dimensions=dims,
        cohorts=tuple(cohorts),
        n_strict_eligible=n_strict,
        n_conditional_eligible=n_cond,
        n_not_comparable=n_excl,
        strict_signal_dates=tuple(strict_dates),
        conditional_signal_dates=tuple(conditional_dates),
        excluded_signal_dates=tuple(excluded_dates),
        overall_verdict=overall,
        comparison_note=note,
    )
