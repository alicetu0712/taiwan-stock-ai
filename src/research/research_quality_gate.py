"""
ResearchUniverseQualityGate — research-only module.

12-check quality gate for the research signal universe.
Verdict levels: PASS / CONDITIONAL / FAIL / UNVERIFIED
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


GATE_VERSION = "v1.0"
SOURCE_SESSION = "session38"


class GateVerdict(str, Enum):
    PASS = "PASS"
    CONDITIONAL = "CONDITIONAL"
    FAIL = "FAIL"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class GateCheckResult:
    check_id: str           # e.g. QG-01
    check_name: str
    verdict: GateVerdict
    finding: str
    threshold: str
    actual_value: str
    remediation: Optional[str] = None


@dataclass
class QualityGateReport:
    gate_version: str
    checks: List[GateCheckResult]
    overall_verdict: GateVerdict
    summary: str

    def by_verdict(self, v: GateVerdict) -> List[GateCheckResult]:
        return [c for c in self.checks if c.verdict == v]

    @property
    def pass_count(self) -> int:
        return len(self.by_verdict(GateVerdict.PASS))

    @property
    def fail_count(self) -> int:
        return len(self.by_verdict(GateVerdict.FAIL))

    @property
    def conditional_count(self) -> int:
        return len(self.by_verdict(GateVerdict.CONDITIONAL))

    @property
    def unverified_count(self) -> int:
        return len(self.by_verdict(GateVerdict.UNVERIFIED))


def _verdict(condition: bool, on_fail: GateVerdict = GateVerdict.FAIL) -> GateVerdict:
    return GateVerdict.PASS if condition else on_fail


def run_session38_quality_gate() -> QualityGateReport:
    """
    Runs the 12-check quality gate using Session 38 official-verified findings.

    All inputs are from Session 37/38 data gathering; no DB reads required.
    """
    checks: List[GateCheckResult] = []

    # ------------------------------------------------------------------ #
    # QG-01: Official classification coverage                             #
    # ------------------------------------------------------------------ #
    checks.append(GateCheckResult(
        check_id="QG-01",
        check_name="Official classification coverage",
        verdict=GateVerdict.PASS,
        finding=(
            "TWSE 1099 + TPEx 897 = 1996 official common stocks. "
            "All 410 FS v8.0 unique stocks classified by official source."
        ),
        threshold="100% of signal stock_ids classified",
        actual_value="100% (410/410 classified; 368 TWSE common, 42 ETF, 0 unknown)",
        remediation=None,
    ))

    # ------------------------------------------------------------------ #
    # QG-02: ETF contamination in ForwardSignals                          #
    # ------------------------------------------------------------------ #
    checks.append(GateCheckResult(
        check_id="QG-02",
        check_name="ETF contamination in v8.0 ForwardSignals",
        verdict=GateVerdict.FAIL,
        finding=(
            "213 of 2236 v8.0 signals (9.52%) are from 42 ETF stock_ids "
            "(all 0-prefix, confirmed not in TWSE/TPEx common stock lists). "
            "Official classification: 0050=元大台灣50, 0056=元大高股息, etc."
        ),
        threshold="ETF contamination < 1%",
        actual_value="9.52% (213/2236)",
        remediation=(
            "Filter ForwardSignals by security_type='TWSE_COMMON_ACTIVE' using "
            "SecurityClassificationService. Remove 42 ETF stock_ids from signal pool."
        ),
    ))

    # ------------------------------------------------------------------ #
    # QG-03: TPEx inclusion                                               #
    # ------------------------------------------------------------------ #
    checks.append(GateCheckResult(
        check_id="QG-03",
        check_name="TPEx common stock inclusion",
        verdict=GateVerdict.FAIL,
        finding=(
            "0 of 897 official TPEx common stocks are in ForwardSignals v8.0. "
            "895 TPEx stocks appear as orphans in daily_prices but are excluded "
            "from the stocks master and signal computation pipeline."
        ),
        threshold="TPEx common stocks represented in signals OR explicitly excluded by design",
        actual_value="0% (0/897) — absent, not explicitly excluded by design",
        remediation=(
            "Either (a) add 897 TPEx stocks to stocks master + backtest training, "
            "or (b) document explicit design decision to exclude TPEx from universe."
        ),
    ))

    # ------------------------------------------------------------------ #
    # QG-04: Survivorship bias — delisted stocks                          #
    # ------------------------------------------------------------------ #
    checks.append(GateCheckResult(
        check_id="QG-04",
        check_name="Survivorship bias (delisted stocks)",
        verdict=GateVerdict.FAIL,
        finding=(
            "826-entry stocks master has 0 security_status='delisted' rows. "
            "99 stocks in master are NOT in current TWSE API → probable delistings "
            "(96 with zero price days, 3 delisted mid-era). "
            "No historical delisting records loaded."
        ),
        threshold="Delisted stocks during study period documented and handled",
        actual_value="99 probable delistings; 0 explicit delisted_date records",
        remediation=(
            "Obtain TWSE historical delisting data. Mark 99 stocks with delisted_date. "
            "Verify 3 mid-era delistings (2867, 6806, 6288) are properly handled in backtest."
        ),
    ))

    # ------------------------------------------------------------------ #
    # QG-05: Train-test universe alignment                                #
    # ------------------------------------------------------------------ #
    checks.append(GateCheckResult(
        check_id="QG-05",
        check_name="Train-test universe alignment",
        verdict=GateVerdict.FAIL,
        finding=(
            "Training era: ~720 TWSE common/day (all in master, 0 ETF). "
            "Forward era: 368 TWSE common + 42 ETF = 410 unique. "
            "Only 394 of 826 master stocks present on ForwardSignal dates (48%). "
            "SIGNIFICANT_MISMATCH confirmed by UniverseAlignmentAuditor."
        ),
        threshold="Forward universe ≥ 70% overlap with training universe",
        actual_value="48% master coverage on signal dates; ETF contamination absent in training, present in forward",
        remediation=(
            "Investigate why only 394 of 826 master stocks had prices on Oct 12–28. "
            "Fix data loading pipeline or document as deliberate scope change."
        ),
    ))

    # ------------------------------------------------------------------ #
    # QG-06: Stock master completeness (TWSE)                             #
    # ------------------------------------------------------------------ #
    checks.append(GateCheckResult(
        check_id="QG-06",
        check_name="TWSE stock master completeness",
        verdict=GateVerdict.FAIL,
        finding=(
            "715 of 1099 TWSE common stocks are in master (65.1%). "
            "384 TWSE common stocks are missing from master: "
            "70 are new IPOs (after Jul 2024), 314 existed before backtest start."
        ),
        threshold="≥ 95% of TWSE common stocks in master (allowing ≤ 5% for recent IPOs)",
        actual_value="65.1% (715/1099 TWSE, 0/897 TPEx)",
        remediation=(
            "Load 314 pre-existing TWSE stocks that are absent from master. "
            "Design IPO inclusion policy for 70 new stocks."
        ),
    ))

    # ------------------------------------------------------------------ #
    # QG-07: source_price_date population                                 #
    # ------------------------------------------------------------------ #
    checks.append(GateCheckResult(
        check_id="QG-07",
        check_name="source_price_date populated in ForwardSignals",
        verdict=GateVerdict.UNVERIFIED,
        finding=(
            "Session 36 confirmed source_price_date column exists in forward_signals schema. "
            "Population rate for v8.0 signals not fully verified in this session."
        ),
        threshold="100% of v8.0 signals have non-NULL source_price_date",
        actual_value="UNVERIFIED — requires DB query",
        remediation="Run: SELECT COUNT(*) FROM forward_signals WHERE model_version='v8.0' AND source_price_date IS NULL",
    ))

    # ------------------------------------------------------------------ #
    # QG-08: Point-in-time universe for backtesting                       #
    # ------------------------------------------------------------------ #
    checks.append(GateCheckResult(
        check_id="QG-08",
        check_name="Point-in-time universe for backtesting",
        verdict=GateVerdict.FAIL,
        finding=(
            "Backtest uses current stocks master (826 entries loaded at build time). "
            "No point-in-time snapshot of which stocks were listed on each backtest date. "
            "Stocks that were listed Jan 2025 may appear in Jul 2024 backtest signals. "
            "This is a look-ahead bias in the selection universe."
        ),
        threshold="Backtest uses point-in-time listing records",
        actual_value="Current master used; no historical listing date filtering",
        remediation=(
            "Add listing_date to stocks master. Filter signal candidates to "
            "stocks listed ≥ N days before signal date."
        ),
    ))

    # ------------------------------------------------------------------ #
    # QG-09: Corporate action adjustment                                  #
    # ------------------------------------------------------------------ #
    checks.append(GateCheckResult(
        check_id="QG-09",
        check_name="Corporate action adjustment in price data",
        verdict=GateVerdict.UNVERIFIED,
        finding=(
            "daily_prices stores raw close prices. It is unknown whether prices "
            "are adjusted for dividends, stock splits, or rights offerings. "
            "Unadjusted prices cause look-back errors in return calculations."
        ),
        threshold="Prices confirmed adjusted OR adjustment impact quantified",
        actual_value="UNVERIFIED — price adjustment status not documented",
        remediation="Verify with data provider whether daily_prices are adjusted or raw.",
    ))

    # ------------------------------------------------------------------ #
    # QG-10: ForwardSignals count reconciliation                          #
    # ------------------------------------------------------------------ #
    checks.append(GateCheckResult(
        check_id="QG-10",
        check_name="ForwardSignals count reconciliation",
        verdict=GateVerdict.PASS,
        finding=(
            "2605 total = 2236 v8.0 (is_valid=True) + 369 v6.0 (is_valid=False). "
            "Verified in Session 37. No duplicate stock_id+date+model_version records."
        ),
        threshold="Total = sum of all model_version groups; 0 duplicates",
        actual_value="COUNT_RECONCILED (Session 37)",
        remediation=None,
    ))

    # ------------------------------------------------------------------ #
    # QG-11: DailyPrice coverage on signal dates                          #
    # ------------------------------------------------------------------ #
    checks.append(GateCheckResult(
        check_id="QG-11",
        check_name="DailyPrice coverage on ForwardSignal dates",
        verdict=GateVerdict.CONDITIONAL,
        finding=(
            "Oct 12–28, 2026 signal dates: 394–395 master stocks present per day "
            "(48% of master). Full-market coverage requires ~1,069+ stocks. "
            "Signal computation on 48% of universe creates selection bias vs "
            "training era which had ~720/826 master stocks (87%)."
        ),
        threshold="≥ 80% of training-era stock count on signal dates",
        actual_value="48% (394/826 master); 55% if including 203 TWSE orphans",
        remediation="Investigate Oct 2026 DailyPrice loading pipeline. Backfill if authorized.",
    ))

    # ------------------------------------------------------------------ #
    # QG-12: Genuine prospective evidence                                 #
    # ------------------------------------------------------------------ #
    checks.append(GateCheckResult(
        check_id="QG-12",
        check_name="Genuine prospective evidence for V3",
        verdict=GateVerdict.FAIL,
        finding=(
            "All 21 hybrid_forward_decision rows are RETROSPECTIVE_RECONSTRUCTION "
            "(captured_at 2026-11-05T04:42:30, computed retroactively). "
            "0 decisions made prospectively before the signal date. "
            "V3's 20d outcome window expires 2026-12-02 — no outcomes yet."
        ),
        threshold="≥ 1 prospective decision with actual outcome",
        actual_value="0 genuine prospective decisions",
        remediation="Wait for 2026-12-02 outcome window. Requires cron to run first.",
    ))

    # Overall verdict
    fail_count = sum(1 for c in checks if c.verdict == GateVerdict.FAIL)
    cond_count = sum(1 for c in checks if c.verdict == GateVerdict.CONDITIONAL)
    unverified_count = sum(1 for c in checks if c.verdict == GateVerdict.UNVERIFIED)
    pass_count = sum(1 for c in checks if c.verdict == GateVerdict.PASS)

    if fail_count >= 5:
        overall = GateVerdict.FAIL
    elif fail_count > 0:
        overall = GateVerdict.CONDITIONAL
    elif cond_count > 0 or unverified_count > 0:
        overall = GateVerdict.CONDITIONAL
    else:
        overall = GateVerdict.PASS

    summary = (
        f"PASS: {pass_count}, CONDITIONAL: {cond_count}, "
        f"FAIL: {fail_count}, UNVERIFIED: {unverified_count}. "
        f"Overall: {overall.value}."
    )

    return QualityGateReport(
        gate_version=GATE_VERSION,
        checks=checks,
        overall_verdict=overall,
        summary=summary,
    )
