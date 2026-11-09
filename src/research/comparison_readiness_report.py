"""
comparison_readiness_report.py — research-only module.

V1V2V3ComparisonReadinessReport: 10-dimension readiness check to determine
whether a credible ranking of V1/V2/V3 is currently possible.

Also contains HistoricalResearchEligibilityGate (12 checks) and
StrategyComparisonFramework (paired/portfolio/coverage comparison).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


REPORT_VERSION = "v1.0"
SOURCE_SESSION = "session39"

# Standard transaction cost (from v3_comparison_engine.py)
FEES_PCT = 0.585  # buy + sell combined


class ReadinessStatus(str, Enum):
    READY = "READY"
    CONDITIONAL = "CONDITIONAL"
    BLOCKED = "BLOCKED"
    UNVERIFIED = "UNVERIFIED"


class EligibilityVerdict(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    CONDITIONAL = "CONDITIONAL"
    INELIGIBLE = "INELIGIBLE"
    UNVERIFIED = "UNVERIFIED"


class ComparabilityVerdict(str, Enum):
    COMPARABLE = "COMPARABLE"
    CONDITIONAL = "CONDITIONAL"
    NOT_COMPARABLE = "NOT_COMPARABLE"


# ---------------------------------------------------------------------------
# HistoricalResearchEligibilityGate — 12 checks
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EligibilityCheck:
    check_id: str
    check_name: str
    verdict: EligibilityVerdict
    finding: str
    threshold: str
    actual: str
    note: Optional[str] = None


@dataclass
class EligibilityGateReport:
    checks: List[EligibilityCheck]
    overall_verdict: EligibilityVerdict
    summary: str
    point_in_time_flag: bool  # True if POINT_IN_TIME_UNIVERSE_UNVERIFIED applies

    def by_verdict(self, v: EligibilityVerdict) -> List[EligibilityCheck]:
        return [c for c in self.checks if c.verdict == v]


def run_historical_eligibility_gate() -> EligibilityGateReport:
    """
    12-check gate using Session 37/38/39 data gathering findings.
    All findings are verified in prior sessions — no DB reads required.
    """
    checks: List[EligibilityCheck] = []

    # EG-01: Official security classification
    checks.append(EligibilityCheck(
        check_id="EG-01",
        check_name="Official security classification",
        verdict=EligibilityVerdict.ELIGIBLE,
        finding="100% of FS v8.0 unique stocks classified by official TWSE/TPEx API (Session 38).",
        threshold="All stock_ids classifiable by official source",
        actual="410/410 classified; 368 TWSE common, 42 ETF, 0 unknown",
    ))

    # EG-02: Point-in-time universe
    checks.append(EligibilityCheck(
        check_id="EG-02",
        check_name="Point-in-time universe",
        verdict=EligibilityVerdict.INELIGIBLE,
        finding=(
            "stocks master has NO listing_date column. Cannot verify which stocks "
            "were listed on each backtest signal date. Stocks that IPO'd in Jan 2025 "
            "may appear in Jul 2024 backtest signals."
        ),
        threshold="Backtest filters candidates to stocks listed ≥ 1 day before signal date",
        actual="POINT_IN_TIME_UNIVERSE_UNVERIFIED — no listing_date in schema",
        note="POINT_IN_TIME_UNIVERSE_UNVERIFIED — do not infer current listing status as past status",
    ))

    # EG-03: Trading date validity
    checks.append(EligibilityCheck(
        check_id="EG-03",
        check_name="Trading date validity",
        verdict=EligibilityVerdict.CONDITIONAL,
        finding=(
            "v8.0 signal dates: Oct 12–28, 2026 (7 dates). "
            "These are valid TWSE trading days confirmed by TradingCalendarService. "
            "v6.0 signal dates (Oct 9–11) are invalid (is_valid=False). "
            "Backtest era (Jul 2024–May 2026): trading calendar validated."
        ),
        threshold="All signal dates are valid TWSE trading days",
        actual="CONDITIONAL — v8.0 valid, v6.0 invalid (excluded), backtest era OK",
    ))

    # EG-04: Market data coverage
    checks.append(EligibilityCheck(
        check_id="EG-04",
        check_name="Market data coverage on signal dates",
        verdict=EligibilityVerdict.CONDITIONAL,
        finding=(
            "Oct 12–28, 2026 (forward era): 394–395 of 826 master stocks (48%). "
            "Backtest era (Jul 2024–May 2026): 713–724 stocks/day (~87%). "
            "48% forward coverage creates universe bias vs 87% backtest coverage."
        ),
        threshold="≥ 80% of training-era stock count per date",
        actual="Forward era: 48% — CONDITIONAL; Backtest era: 87% — OK",
    ))

    # EG-05: Benchmark availability
    checks.append(EligibilityCheck(
        check_id="EG-05",
        check_name="Benchmark (0050) availability",
        verdict=EligibilityVerdict.CONDITIONAL,
        finding=(
            "0050 price data exists in daily_prices for backtest era and partial forward era. "
            "0050 is an ETF (confirmed Session 38) — using it as benchmark is valid, "
            "but it is ALSO in the signal pool as a contamination source."
        ),
        threshold="0050 prices available for all signal dates + 20D outlook",
        actual="CONDITIONAL — available, but 0050 also contaminates FS v8.0",
    ))

    # EG-06: Price freshness
    checks.append(EligibilityCheck(
        check_id="EG-06",
        check_name="Price freshness (source_price_date)",
        verdict=EligibilityVerdict.UNVERIFIED,
        finding=(
            "source_price_date column exists in forward_signals schema. "
            "Population rate for v8.0 not verified in this session. "
            "Stale prices at signal computation create look-ahead or stale-data bias."
        ),
        threshold="100% of v8.0 signals have non-NULL source_price_date",
        actual="UNVERIFIED — population rate requires DB query",
    ))

    # EG-07: Corporate action adjustment
    checks.append(EligibilityCheck(
        check_id="EG-07",
        check_name="Corporate action adjustment",
        verdict=EligibilityVerdict.UNVERIFIED,
        finding=(
            "Whether daily_prices are adjusted for dividends, splits, rights is unknown. "
            "Unadjusted prices distort 20D/60D return calculations when corporate "
            "actions occur within the holding period."
        ),
        threshold="Prices confirmed adjusted OR adjustment impact quantified",
        actual="UNVERIFIED — data provider documentation not available",
    ))

    # EG-08: Missing outcomes (fwd_return)
    checks.append(EligibilityCheck(
        check_id="EG-08",
        check_name="Missing outcomes (fwd_return_20d)",
        verdict=EligibilityVerdict.INELIGIBLE,
        finding=(
            "0 of 2236 v8.0 ForwardSignals have fwd_return_20d populated. "
            "20D window expires 2026-12-02 earliest. "
            "No return data available for any v8.0 signal."
        ),
        threshold="≥ 1 signal with fwd_return_20d for outcome analysis",
        actual="0/2236 non-NULL — INELIGIBLE for outcome-based comparison",
    ))

    # EG-09: Duplicate signals
    checks.append(EligibilityCheck(
        check_id="EG-09",
        check_name="Duplicate signals",
        verdict=EligibilityVerdict.ELIGIBLE,
        finding=(
            "Session 37 confirmed: 0 duplicate (stock_id, trade_date, model_version) "
            "combinations in forward_signals. Count reconciled: 2605=2236+369."
        ),
        threshold="0 duplicate (stock_id, trade_date, model_version) rows",
        actual="0 duplicates — ELIGIBLE",
    ))

    # EG-10: Overlapping samples
    checks.append(EligibilityCheck(
        check_id="EG-10",
        check_name="Overlapping hold-period samples",
        verdict=EligibilityVerdict.CONDITIONAL,
        finding=(
            "v8.0 signals span Oct 12–28 (7 dates). With 20D hold, signals from Oct 12 "
            "and Oct 28 have overlapping outcome windows (Oct 12+20D = Nov 11, "
            "Oct 28+20D = Nov 25). "
            "Cluster-aware inference required for significance testing."
        ),
        threshold="Non-overlapping samples OR cluster-robust standard errors used",
        actual="CONDITIONAL — overlapping windows; cluster inference required",
    ))

    # EG-11: Look-ahead bias
    checks.append(EligibilityCheck(
        check_id="EG-11",
        check_name="Look-ahead bias",
        verdict=EligibilityVerdict.CONDITIONAL,
        finding=(
            "NEXT_OPEN execution (execution_price_type verified in schema) reduces "
            "close-price look-ahead bias. However: (a) point-in-time listing dates "
            "not verified (EG-02), (b) source_price_date not verified (EG-06). "
            "Market regime inputs may use same-day data."
        ),
        threshold="No look-ahead in security selection, prices, or regime inputs",
        actual="CONDITIONAL — NEXT_OPEN entry verified; two look-ahead sources UNVERIFIED",
    ))

    # EG-12: Survivorship bias
    checks.append(EligibilityCheck(
        check_id="EG-12",
        check_name="Survivorship bias",
        verdict=EligibilityVerdict.INELIGIBLE,
        finding=(
            "stocks master has 0 delisted_date records. "
            "99 probable delistings in master (Session 38). "
            "96 have 0 price data (delisted before Jul 2024). "
            "3 delisted mid-era (2867, 6806, 6288) — handling unverified. "
            "Selection pool excludes ALL delisted stocks, inflating historical returns."
        ),
        threshold="Delisted stocks during study period documented + handled",
        actual="INELIGIBLE — 0 delisted_date records; 99 probable delistings unhandled",
    ))

    # Overall verdict
    ineligible = sum(1 for c in checks if c.verdict == EligibilityVerdict.INELIGIBLE)
    unverified = sum(1 for c in checks if c.verdict == EligibilityVerdict.UNVERIFIED)
    conditional = sum(1 for c in checks if c.verdict == EligibilityVerdict.CONDITIONAL)
    eligible = sum(1 for c in checks if c.verdict == EligibilityVerdict.ELIGIBLE)

    if ineligible >= 2:
        overall = EligibilityVerdict.INELIGIBLE
    elif ineligible == 1 or unverified >= 2:
        overall = EligibilityVerdict.CONDITIONAL
    elif conditional > 0 or unverified > 0:
        overall = EligibilityVerdict.CONDITIONAL
    else:
        overall = EligibilityVerdict.ELIGIBLE

    point_in_time_flag = any(
        "POINT_IN_TIME_UNIVERSE_UNVERIFIED" in (c.note or "")
        for c in checks
    )

    summary = (
        f"ELIGIBLE: {eligible}, CONDITIONAL: {conditional}, "
        f"INELIGIBLE: {ineligible}, UNVERIFIED: {unverified}. "
        f"Overall: {overall.value}."
    )
    if point_in_time_flag:
        summary += " POINT_IN_TIME_UNIVERSE_UNVERIFIED applies."

    return EligibilityGateReport(
        checks=checks,
        overall_verdict=overall,
        summary=summary,
        point_in_time_flag=point_in_time_flag,
    )


# ---------------------------------------------------------------------------
# StrategyComparisonFramework — fair comparison contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ComparisonContract:
    """
    Shared framework constraints for a valid V1/V2/V3 comparison.
    All three versions MUST use these when comparing results.
    """
    eligible_universe: str
    evaluation_period: str
    benchmark: str
    trading_calendar: str
    fees_pct: float
    capital_assumption: str
    position_sizing: str
    outcome_definition: str
    dedup_policy: str
    source_session: str = SOURCE_SESSION


@dataclass
class PairedComparisonResult:
    """Result of comparing two strategy versions on the same (stock_id, date) sample."""
    v1_id: str
    v2_id: str
    matched_pairs: int
    v1_only: int      # signals in V1 not in V2 (V2 filtered out)
    v2_only: int      # signals in V2 not in V1 (V1 didn't generate)
    verdict: ComparabilityVerdict
    note: str


@dataclass
class CoverageComparison:
    """Counts trading opportunities per version on a common universe."""
    version_id: str
    total_signals: int
    eligible_signals: int
    unique_stocks: int
    unique_dates: int
    fill_rate_pct: float


@dataclass
class MissingnessAnalysis:
    """Documents which samples cannot be compared due to missing data."""
    total_signals: int
    missing_outcome: int      # fwd_return_20d is NULL
    missing_prices: int       # no daily_prices for the stock/date
    etf_contaminated: int     # stock_id is ETF
    universe_mismatch: int    # signal date has < 50% coverage
    comparable_signals: int
    comparability_verdict: ComparabilityVerdict
    note: str


class StrategyComparisonFramework:
    """
    Implements the fair comparison contract for V1/V2/V3.

    All three strategies MUST be evaluated on:
    - Same eligible universe (Dataset B — verified common stocks only)
    - Same benchmark (0050 gross return over same period)
    - Same fees (FEES_PCT = 0.585%)
    - Same exit rules (stop_price or target1 or 20D horizon)
    - Same deduplication (20D dedup for significance testing)
    """

    CONTRACT = ComparisonContract(
        eligible_universe="Dataset B (verified TWSE/TPEx common stocks only)",
        evaluation_period="Same trading dates for all versions",
        benchmark="0050 gross return (open[fill_date] → close[exit_date])",
        trading_calendar="Taiwan Stock Exchange trading calendar (TradingCalendarService)",
        fees_pct=FEES_PCT,
        capital_assumption="Equal weight per signal; no leverage",
        position_sizing="1 unit per signal (no sizing variation between versions)",
        outcome_definition="Net return = gross return - fees_pct (buy+sell)",
        dedup_policy=(
            "For statistical inference: 20D deduplication by stock_id "
            "(non-overlapping samples only). "
            "Raw N reported separately."
        ),
    )

    def assess_session39_comparability(self) -> MissingnessAnalysis:
        """
        Current comparability assessment using Session 36–39 findings.
        All inputs from prior data gathering — no DB reads.
        """
        total_v8 = 2236
        etf = 213                    # Session 38: 9.52% ETF contamination
        missing_outcome = 2236       # 0 fwd_return_20d available
        universe_mismatch = 0        # Can't quantify without outcome data
        missing_prices = 0           # Prices exist for signal dates

        comparable = total_v8 - etf - missing_outcome

        return MissingnessAnalysis(
            total_signals=total_v8,
            missing_outcome=missing_outcome,
            missing_prices=missing_prices,
            etf_contaminated=etf,
            universe_mismatch=universe_mismatch,
            comparable_signals=max(0, comparable),
            comparability_verdict=ComparabilityVerdict.NOT_COMPARABLE,
            note=(
                "0 signals have fwd_return_20d (expires 2026-12-02). "
                "No outcome-based comparison is currently possible. "
                "In-sample backtest comparison (Sessions 27–28) is the only "
                "available evidence, but is in-sample and subject to biases."
            ),
        )


# ---------------------------------------------------------------------------
# V1V2V3ComparisonReadinessReport
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReadinessDimension:
    name: str
    status: ReadinessStatus
    finding: str
    blocker: Optional[str] = None


@dataclass
class V1V2V3ComparisonReadinessReport:
    dimensions: List[ReadinessDimension]
    ranking_supported: bool
    overall_verdict: str
    minimum_viable_improvements: List[str]
    source_session: str = SOURCE_SESSION

    def by_status(self, s: ReadinessStatus) -> List[ReadinessDimension]:
        return [d for d in self.dimensions if d.status == s]

    @property
    def blocked_count(self) -> int:
        return len(self.by_status(ReadinessStatus.BLOCKED))

    @property
    def ready_count(self) -> int:
        return len(self.by_status(ReadinessStatus.READY))


def build_session39_readiness_report() -> V1V2V3ComparisonReadinessReport:
    """
    10-dimension readiness report using Session 36–39 findings.
    """
    dims: List[ReadinessDimension] = [
        ReadinessDimension(
            name="Version Definition",
            status=ReadinessStatus.CONDITIONAL,
            finding=(
                "V3 (VERIFIED, hash be43e8ca), Hybrid_V1 (VERIFIED, frozen 6602c3b). "
                "V1 / V2 (PARTIAL — EntryTimingAnalyzer parameters unversioned; "
                "BUY/STRONG_BUY thresholds historically unversioned)."
            ),
            blocker=None,
        ),
        ReadinessDimension(
            name="Clean Universe",
            status=ReadinessStatus.CONDITIONAL,
            finding=(
                "Dataset B available: 2023 signals, 368 TWSE common stocks. "
                "9.52% ETF contamination removed. "
                "CONDITIONAL: 314 pre-existing TWSE stocks missing from master; "
                "selection pool is 65.1% of TWSE only."
            ),
            blocker=None,
        ),
        ReadinessDimension(
            name="Historical Coverage",
            status=ReadinessStatus.CONDITIONAL,
            finding=(
                "Backtest era (Jul 2024–May 2026): 87% coverage, clean TWSE-only. "
                "Forward era (Oct 2026): 48% coverage, universe mismatch. "
                "CONDITIONAL for backtest; BLOCKED for forward era."
            ),
            blocker=None,
        ),
        ReadinessDimension(
            name="Outcome Availability",
            status=ReadinessStatus.BLOCKED,
            finding=(
                "0 of 2236 v8.0 signals have fwd_return_20d. "
                "Earliest outcomes available 2026-12-02. "
                "Without outcomes, NO performance comparison is possible."
            ),
            blocker="fwd_return_20d = NULL for all v8.0 signals. No outcomes until 2026-12-02.",
        ),
        ReadinessDimension(
            name="Matched Samples (V1 vs V2 vs V3)",
            status=ReadinessStatus.BLOCKED,
            finding=(
                "0 comparable matched pairs exist for outcome analysis. "
                "In-sample backtest (Sessions 27): D vs A/B/C computed, but "
                "V1 (B_v1v2) and V2 (Entry Timing filtered) comparison not separately extracted. "
                "No cross-version matched-pair outcome table."
            ),
            blocker="No outcome data; no matched-pair outcome table persisted.",
        ),
        ReadinessDimension(
            name="Risk Assumptions",
            status=ReadinessStatus.CONDITIONAL,
            finding=(
                "Exit rule: stop_price or target1 or 20D horizon — consistent across versions. "
                "CONDITIONAL: stop_price values in ForwardSignals may differ between "
                "strategy A/B/C/D in comparison engine (B/C/D use their own stop reconstruction)."
            ),
            blocker=None,
        ),
        ReadinessDimension(
            name="Transaction Costs",
            status=ReadinessStatus.READY,
            finding=(
                "FEES_PCT = 0.585% (buy+sell) hardcoded in v3_comparison_engine.py. "
                "Same value documented in execution_simulator.py. "
                "Consistent across all strategy variants."
            ),
            blocker=None,
        ),
        ReadinessDimension(
            name="Statistical Power",
            status=ReadinessStatus.BLOCKED,
            finding=(
                "0 outcome observations. For 20D dedup sample, would need ≥ 30 "
                "non-overlapping stock-periods for minimal power. "
                "Even with outcomes, 7 signal dates × ~290 stocks / 20D dedup ≈ very small N."
            ),
            blocker=(
                "0 outcomes. Even after Dec 2026, estimated dedup N ≈ 290–360 "
                "(7 dates × ~50 stocks/date / dedup); borderline power."
            ),
        ),
        ReadinessDimension(
            name="Out-of-Sample Evidence",
            status=ReadinessStatus.BLOCKED,
            finding=(
                "0 walk-forward windows (Session 28: MARKET_AVOIDANCE_DRIVEN). "
                "0 genuine prospective decisions (Session 36). "
                "In-sample comparison only. All '21 decisions' are RETROSPECTIVE."
            ),
            blocker="0 OOS windows; 0 genuine prospective evidence.",
        ),
        ReadinessDimension(
            name="Prospective Evidence",
            status=ReadinessStatus.BLOCKED,
            finding=(
                "Cron root cause INCONCLUSIVE (Stage B not authorized). "
                "Even if cron ran, first prospective outcomes not until 2026-12-02. "
                "Cannot rank versions without genuine prospective signal outcomes."
            ),
            blocker="Cron not running; Stage B not authorized; 0 prospective decisions.",
        ),
    ]

    blocked_count = sum(1 for d in dims if d.status == ReadinessStatus.BLOCKED)
    ranking_supported = blocked_count == 0

    overall = (
        "RANKING_NOT_SUPPORTED" if not ranking_supported
        else "RANKING_CONDITIONAL"
    )

    improvements: List[str] = [
        "1. Wait for 2026-12-02 (first fwd_return_20d available) — unblocks Outcome Availability",
        "2. Authorize Stage B cron probe → resolve cron root cause → first real prospective signal",
        "3. Extract matched-pair backtest results (V1/V2/V3 on same stock/date) from Sessions 27-28",
        "4. Add listing_date to stocks master → resolve point-in-time universe",
        "5. Verify source_price_date population (EG-06) and corporate action status (EG-07)",
    ]

    return V1V2V3ComparisonReadinessReport(
        dimensions=dims,
        ranking_supported=ranking_supported,
        overall_verdict=overall,
        minimum_viable_improvements=improvements,
    )
