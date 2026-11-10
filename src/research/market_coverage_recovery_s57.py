"""
Market Coverage Recovery — Session 57

Evidence-based data gap classification, historical recovery feasibility,
and pipeline reliability architecture for Taiwan OHLCV data.

Key Classifications (S57):
- Oct08–Oct27: BENCHMARK_ONLY_HISTORICAL (not gap dates; outside focus window)
- Oct29/30/Nov02/03: GAP_BENCHMARK_ONLY (1 row each, only 0050)
- Nov04/05: PARTIAL_COVERAGE (exists but volume_null for many; warrants contamination)
- Nov06/09: DATE_MISSING (zero rows)

Recovery Feasibility:
- TWSE single-stock API: FEASIBLE_WITH_CAUTION (~1969 calls/date, ~65 min/date)
- TPEx historical: NOT_FEASIBLE (endpoint ignores date param)
- S50 research snapshot: PARTIAL (6 stocks on Oct29, up to 4 dates)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import List


# ── Enums ──────────────────────────────────────────────────────────────────────

class GapClassification(str, Enum):
    DATE_MISSING = "DATE_MISSING"                       # 0 rows in daily_prices
    BENCHMARK_ONLY = "BENCHMARK_ONLY"                   # only 0050 (1 row)
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"               # rows exist but incomplete
    FULL_COVERAGE = "FULL_COVERAGE"                     # complete OHLCV, all universe
    HISTORICAL_BACKFILL = "HISTORICAL_BACKFILL"         # pre-focus-window (Oct08–Oct27)


class RecoveryTier(str, Enum):
    T1_RESEARCH_SNAPSHOT = "T1_RESEARCH_SNAPSHOT"       # S50 manual verification data
    T2_TWSE_SINGLE_STOCK = "T2_TWSE_SINGLE_STOCK"       # per-stock historical API
    T3_TWSE_BULK_HIST = "T3_TWSE_BULK_HIST"             # bulk API (broken)
    T4_TPEX_BULK = "T4_TPEX_BULK"                       # TPEx bulk (date ignored)
    T5_MANUAL = "T5_MANUAL"                             # manual entry
    NOT_AVAILABLE = "NOT_AVAILABLE"


class RecoveryFeasibility(str, Enum):
    FEASIBLE_VERIFIED = "FEASIBLE_VERIFIED"             # proven working
    FEASIBLE_WITH_CAUTION = "FEASIBLE_WITH_CAUTION"     # works but risk/cost
    FEASIBLE_PARTIAL = "FEASIBLE_PARTIAL"               # only subset possible
    NOT_FEASIBLE = "NOT_FEASIBLE"                       # confirmed broken
    UNVERIFIED = "UNVERIFIED"


class AuthorizationStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    PENDING = "PENDING"
    NOT_REQUESTED = "NOT_REQUESTED"
    BLOCKED = "BLOCKED"


# ── Data Gap Inventory ─────────────────────────────────────────────────────────

@dataclass
class DailyPriceGapEntry:
    date: str                           # YYYY-MM-DD
    total_rows: int
    gap_classification: GapClassification
    ordinary_4d_rows: int               # 1000-9999 prefix only
    etf_rows: int                       # 00x prefix
    warrant_rows: int                   # 7xx/02x prefix
    volume_null_rows: int               # rows with NULL volume
    best_recovery_tier: RecoveryTier
    recovery_feasibility: RecoveryFeasibility
    pit_universe_estimate: int          # expected ordinary stock count
    s50_records_available: int          # records in _VERIFIED_RECORDS for this date
    authorization_status: AuthorizationStatus
    notes: str


def build_gap_inventory() -> List[DailyPriceGapEntry]:
    return [
        DailyPriceGapEntry(
            date="2026-10-08",
            total_rows=1,
            gap_classification=GapClassification.HISTORICAL_BACKFILL,
            ordinary_4d_rows=0,
            etf_rows=1,
            warrant_rows=0,
            volume_null_rows=0,
            best_recovery_tier=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_WITH_CAUTION,
            pit_universe_estimate=1969,
            s50_records_available=1,
            authorization_status=AuthorizationStatus.NOT_REQUESTED,
            notes="2330 close=240.5 available in S50. Outside primary focus window Oct29–Nov09.",
        ),
        DailyPriceGapEntry(
            date="2026-10-15",
            total_rows=1,
            gap_classification=GapClassification.HISTORICAL_BACKFILL,
            ordinary_4d_rows=0,
            etf_rows=1,
            warrant_rows=0,
            volume_null_rows=0,
            best_recovery_tier=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_WITH_CAUTION,
            pit_universe_estimate=1969,
            s50_records_available=1,
            authorization_status=AuthorizationStatus.NOT_REQUESTED,
            notes="2330 close=236.0 available in S50.",
        ),
        DailyPriceGapEntry(
            date="2026-10-19",
            total_rows=1,
            gap_classification=GapClassification.HISTORICAL_BACKFILL,
            ordinary_4d_rows=0,
            etf_rows=1,
            warrant_rows=0,
            volume_null_rows=0,
            best_recovery_tier=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_WITH_CAUTION,
            pit_universe_estimate=1969,
            s50_records_available=1,
            authorization_status=AuthorizationStatus.NOT_REQUESTED,
            notes="2330 close=240.0 available in S50.",
        ),
        DailyPriceGapEntry(
            date="2026-10-20",
            total_rows=1,
            gap_classification=GapClassification.HISTORICAL_BACKFILL,
            ordinary_4d_rows=0,
            etf_rows=1,
            warrant_rows=0,
            volume_null_rows=0,
            best_recovery_tier=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_WITH_CAUTION,
            pit_universe_estimate=1969,
            s50_records_available=1,
            authorization_status=AuthorizationStatus.NOT_REQUESTED,
            notes="2330 close=240.5 available in S50.",
        ),
        DailyPriceGapEntry(
            date="2026-10-27",
            total_rows=1,
            gap_classification=GapClassification.HISTORICAL_BACKFILL,
            ordinary_4d_rows=0,
            etf_rows=1,
            warrant_rows=0,
            volume_null_rows=0,
            best_recovery_tier=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_WITH_CAUTION,
            pit_universe_estimate=1969,
            s50_records_available=1,
            authorization_status=AuthorizationStatus.NOT_REQUESTED,
            notes="2330 close=249.5 available in S50.",
        ),
        DailyPriceGapEntry(
            date="2026-10-29",
            total_rows=1,
            gap_classification=GapClassification.BENCHMARK_ONLY,
            ordinary_4d_rows=0,
            etf_rows=1,
            warrant_rows=0,
            volume_null_rows=0,
            best_recovery_tier=RecoveryTier.T1_RESEARCH_SNAPSHOT,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_VERIFIED,
            pit_universe_estimate=1969,
            s50_records_available=6,
            authorization_status=AuthorizationStatus.PENDING,
            notes=(
                "S50 has 6 stocks: 2330/2454/2317 with FULL OHLCV+volume; "
                "2891/6505/3008 with OHLCV but volume=None. "
                "Full universe needs T2 (~1969 calls). AUTH01 PENDING."
            ),
        ),
        DailyPriceGapEntry(
            date="2026-10-30",
            total_rows=1,
            gap_classification=GapClassification.BENCHMARK_ONLY,
            ordinary_4d_rows=0,
            etf_rows=1,
            warrant_rows=0,
            volume_null_rows=0,
            best_recovery_tier=RecoveryTier.T1_RESEARCH_SNAPSHOT,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_VERIFIED,
            pit_universe_estimate=1969,
            s50_records_available=2,
            authorization_status=AuthorizationStatus.PENDING,
            notes=(
                "S50: 2330 O=2380/H=2380/L=2360/C=2370/V=36615931; "
                "2454 O=3820/H=3990/L=3805/C=3915/V=13044171. "
                "Full universe needs T2. AUTH01 PENDING."
            ),
        ),
        DailyPriceGapEntry(
            date="2026-11-02",
            total_rows=1,
            gap_classification=GapClassification.BENCHMARK_ONLY,
            ordinary_4d_rows=0,
            etf_rows=1,
            warrant_rows=0,
            volume_null_rows=0,
            best_recovery_tier=RecoveryTier.T1_RESEARCH_SNAPSHOT,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_VERIFIED,
            pit_universe_estimate=1969,
            s50_records_available=1,
            authorization_status=AuthorizationStatus.PENDING,
            notes=(
                "S50: 2330 O=2310/H=2345/L=2310/C=2330/V=41165068. "
                "Full universe needs T2. AUTH01 PENDING."
            ),
        ),
        DailyPriceGapEntry(
            date="2026-11-03",
            total_rows=1,
            gap_classification=GapClassification.BENCHMARK_ONLY,
            ordinary_4d_rows=0,
            etf_rows=1,
            warrant_rows=0,
            volume_null_rows=0,
            best_recovery_tier=RecoveryTier.T1_RESEARCH_SNAPSHOT,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_VERIFIED,
            pit_universe_estimate=1969,
            s50_records_available=1,
            authorization_status=AuthorizationStatus.PENDING,
            notes=(
                "S50: 2317 O=249.0/H=250.0/L=243.5/C=245.5/V=44139321. "
                "CORRECTION from S55/S56: close=245.5 (not 245.0). "
                "Full universe needs T2. AUTH01 PENDING."
            ),
        ),
        DailyPriceGapEntry(
            date="2026-11-04",
            total_rows=6957,
            gap_classification=GapClassification.PARTIAL_COVERAGE,
            ordinary_4d_rows=1969,
            etf_rows=159,
            warrant_rows=4829,
            volume_null_rows=5715,
            best_recovery_tier=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_PARTIAL,
            pit_universe_estimate=1969,
            s50_records_available=0,
            authorization_status=AuthorizationStatus.NOT_REQUESTED,
            notes=(
                "WARRANTS_CONTAMINATION: 4829 warrant rows included. "
                "TPEX_VOLUME_NULL: 5715 null amount rows = TPEx records (all null volume). "
                "881 ordinary stocks with null/zero volume (suspended/halted). "
                "OHLC valid for all rows. Skip ordinary volume imputation: "
                "null volume likely reflects genuine low/no-trade for those stocks."
            ),
        ),
        DailyPriceGapEntry(
            date="2026-11-05",
            total_rows=6589,
            gap_classification=GapClassification.PARTIAL_COVERAGE,
            ordinary_4d_rows=1967,
            etf_rows=159,
            warrant_rows=4463,
            volume_null_rows=4463,  # estimated, TPEx all null
            best_recovery_tier=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_PARTIAL,
            pit_universe_estimate=1969,
            s50_records_available=0,
            authorization_status=AuthorizationStatus.NOT_REQUESTED,
            notes=(
                "Similar structure to Nov04 but fewer rows (day before weekend). "
                "TPEx volume=NULL all records. 2 fewer ordinary stocks vs Nov04."
            ),
        ),
        DailyPriceGapEntry(
            date="2026-11-06",
            total_rows=0,
            gap_classification=GapClassification.DATE_MISSING,
            ordinary_4d_rows=0,
            etf_rows=0,
            warrant_rows=0,
            volume_null_rows=0,
            best_recovery_tier=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_WITH_CAUTION,
            pit_universe_estimate=1969,
            s50_records_available=2,
            authorization_status=AuthorizationStatus.PENDING,
            notes=(
                "S50 CLOSE_ONLY: 2330=2135.0, 2454=3390.0. "
                "Full universe needs T2. "
                "No BENCHMARK row present. "
                "SCHEDULER_NOT_TRIGGERED is likely root cause."
            ),
        ),
        DailyPriceGapEntry(
            date="2026-11-09",
            total_rows=0,
            gap_classification=GapClassification.DATE_MISSING,
            ordinary_4d_rows=0,
            etf_rows=0,
            warrant_rows=0,
            volume_null_rows=0,
            best_recovery_tier=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            recovery_feasibility=RecoveryFeasibility.FEASIBLE_WITH_CAUTION,
            pit_universe_estimate=1969,
            s50_records_available=2,
            authorization_status=AuthorizationStatus.PENDING,
            notes=(
                "S50 CLOSE_ONLY: 2330=2235.0 (CORRECTION from S56: not 2200.0), 2454=3725.0. "
                "Full universe needs T2. "
                "SCHEDULER_NOT_TRIGGERED likely root cause."
            ),
        ),
    ]


# ── Root Cause Evidence Ledger ─────────────────────────────────────────────────

@dataclass
class RootCauseEntry:
    code: str
    hypothesis: str
    evidence_type: str
    confidence: str
    implication: str
    remediation: str


def build_root_cause_ledger() -> List[RootCauseEntry]:
    return [
        RootCauseEntry(
            code="RC-01",
            hypothesis=(
                "TWSE_HIST_URL returns non-JSON for recent dates: "
                "cron job always fails on TWSE bulk historical fallback"
            ),
            evidence_type="S57 live probe: 3 retries, all JSONDecodeError",
            confidence="DIRECTLY_CONFIRMED",
            implication=(
                "Any code path that relies on TWSE_HIST_URL as primary source "
                "silently fails and falls back. The script currently uses "
                "TWSE_LATEST_URL as fallback, which returns WRONG DATE data."
            ),
            remediation=(
                "Remove TWSE_HIST_URL from active pipeline. "
                "Replace with TWSE_SINGLE_STOCK pattern or accept LATEST_URL with date validation."
            ),
        ),
        RootCauseEntry(
            code="RC-02",
            hypothesis=(
                "TWSE_LATEST_URL returns yesterday's data because cron runs "
                "early next morning — api_date is always T-1"
            ),
            evidence_type="S57 live probe: api_date=2026-11-09 on 2026-11-10",
            confidence="DIRECTLY_CONFIRMED",
            implication=(
                "Data is inserted with correct date (from cron config) but "
                "api_date in source is T-1. If date validation checks api_date vs "
                "requested_date, every insert would fail. "
                "RC-02 explains Nov06/09 DATE_MISSING: scheduler may have failed "
                "and fallback returned wrong-date data that was rejected."
            ),
            remediation=(
                "TWSE_LATEST_URL is correct for same-day use or T+1 cron. "
                "Add explicit api_date vs expected_date validation; "
                "log but do not fail if off-by-one (weekend/holiday aware)."
            ),
        ),
        RootCauseEntry(
            code="RC-03",
            hypothesis=(
                "TPEx_HIST_URL ignores the ?d= date parameter: "
                "always returns today's data with today's api_date"
            ),
            evidence_type=(
                "S57 live probe: d=1151029 → api_date=2026-11-10; "
                "d=1151104 → api_date=2026-11-10; both identical"
            ),
            confidence="DIRECTLY_CONFIRMED",
            implication=(
                "TPEx bulk historical is structurally unavailable via this endpoint. "
                "All historical TPEx data must be sourced per-stock. "
                "Nov04/05 TPEx entries have volume=NULL because today's bulk API "
                "returns NULL volume for all 5737 stocks by design."
            ),
            remediation=(
                "TPEx patch (L500-503) correctly captures this mismatch in summary['errors']. "
                "Long-term: use per-stock TPEx API if available, or accept NULL volume "
                "for TPEx stocks. Consider volume imputation warning in dashboard."
            ),
        ),
        RootCauseEntry(
            code="RC-04",
            hypothesis=(
                "SCHEDULER_NOT_TRIGGERED for Nov06/09: cron did not run "
                "or ran but no data was written (silent failure)"
            ),
            evidence_type=(
                "Nov06/09 have 0 rows (even benchmark 0050 missing). "
                "S50 had close data for 2330/2454 on those dates, confirming they were trading days."
            ),
            confidence="STRONGLY_SUPPORTED",
            implication=(
                "The pipeline did not execute on Nov06/09. "
                "Either the GitHub Actions cron was skipped or the script ran but "
                "raised an unhandled exception before writing any rows. "
                "Nov04/05 had 6957/6589 rows — Nov06 missing despite being adjacent."
            ),
            remediation=(
                "GitHub Actions cron audit required. Check workflow run history. "
                "Add minimum-row health check: alert if daily_prices count for date < 1000."
            ),
        ),
        RootCauseEntry(
            code="RC-05",
            hypothesis=(
                "Oct29/30/Nov02/03 benchmark-only: cron ran but only "
                "processed ETF/benchmark, not full universe"
            ),
            evidence_type=(
                "1 row per date = only 0050. "
                "TWSE_LATEST_URL was available (Nov06+). "
                "RC-02 timeline: pipeline may have used wrong-date validation."
            ),
            confidence="SUFFICIENT_EVIDENCE",
            implication=(
                "These dates are not fully recoverable without historical API. "
                "0050 (benchmark ETF) was processed but ordinary stocks failed or were excluded."
            ),
            remediation=(
                "Identify why pipeline only fetched benchmark. "
                "May be date-mismatch guard that rejected TWSE_LATEST_URL data "
                "because api_date ≠ requested_date."
            ),
        ),
    ]


# ── Recovery Feasibility Matrix ────────────────────────────────────────────────

@dataclass
class RecoveryFeasibilityRow:
    date: str
    tier_recommendation: RecoveryTier
    feasibility: RecoveryFeasibility
    request_count_estimate: int
    time_estimate_min: float
    ohlcv_quality: str
    universe_coverage_estimate_pct: float
    prerequisites: str
    authorization_needed: str


def build_recovery_feasibility_matrix() -> List[RecoveryFeasibilityRow]:
    return [
        RecoveryFeasibilityRow(
            date="2026-10-29",
            tier_recommendation=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            feasibility=RecoveryFeasibility.FEASIBLE_VERIFIED,
            request_count_estimate=1969,
            time_estimate_min=65.6,
            ohlcv_quality="FULL_OHLCV_WITH_VOLUME (confirmed for TWSE ordinary)",
            universe_coverage_estimate_pct=100.0,
            prerequisites=(
                "AUTH01 authorized, rate limit policy confirmed, "
                "TPEx per-stock API (if needed for TPEx-listed stocks)"
            ),
            authorization_needed="AUTH01 + rate-limit policy + terms verification",
        ),
        RecoveryFeasibilityRow(
            date="2026-10-30",
            tier_recommendation=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            feasibility=RecoveryFeasibility.FEASIBLE_VERIFIED,
            request_count_estimate=1969,
            time_estimate_min=65.6,
            ohlcv_quality="FULL_OHLCV_WITH_VOLUME (confirmed for 2330/2454)",
            universe_coverage_estimate_pct=100.0,
            prerequisites="Same as Oct29",
            authorization_needed="AUTH01 + rate-limit policy + terms verification",
        ),
        RecoveryFeasibilityRow(
            date="2026-11-02",
            tier_recommendation=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            feasibility=RecoveryFeasibility.FEASIBLE_VERIFIED,
            request_count_estimate=1969,
            time_estimate_min=65.6,
            ohlcv_quality="FULL_OHLCV_WITH_VOLUME (confirmed for 2330)",
            universe_coverage_estimate_pct=100.0,
            prerequisites="Same as Oct29",
            authorization_needed="AUTH01 + rate-limit policy + terms verification",
        ),
        RecoveryFeasibilityRow(
            date="2026-11-03",
            tier_recommendation=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            feasibility=RecoveryFeasibility.FEASIBLE_VERIFIED,
            request_count_estimate=1969,
            time_estimate_min=65.6,
            ohlcv_quality=(
                "FULL_OHLCV_WITH_VOLUME (confirmed for 2317; "
                "note: S55/S56 close was 245.0, actual=245.5)"
            ),
            universe_coverage_estimate_pct=100.0,
            prerequisites="Same as Oct29",
            authorization_needed="AUTH01 + rate-limit policy + terms verification",
        ),
        RecoveryFeasibilityRow(
            date="2026-11-06",
            tier_recommendation=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            feasibility=RecoveryFeasibility.FEASIBLE_WITH_CAUTION,
            request_count_estimate=1969,
            time_estimate_min=65.6,
            ohlcv_quality="FULL_OHLCV_WITH_VOLUME expected (TWSE single-stock)",
            universe_coverage_estimate_pct=100.0,
            prerequisites="Same as Oct29; TPEX volume will still be NULL",
            authorization_needed="AUTH01 + rate-limit policy + terms verification",
        ),
        RecoveryFeasibilityRow(
            date="2026-11-09",
            tier_recommendation=RecoveryTier.T2_TWSE_SINGLE_STOCK,
            feasibility=RecoveryFeasibility.FEASIBLE_WITH_CAUTION,
            request_count_estimate=1969,
            time_estimate_min=65.6,
            ohlcv_quality="FULL_OHLCV_WITH_VOLUME expected (TWSE single-stock)",
            universe_coverage_estimate_pct=100.0,
            prerequisites="Same as Oct29; TPEX volume will still be NULL",
            authorization_needed="AUTH01 + rate-limit policy + terms verification",
        ),
    ]


def compute_total_recovery_estimate(matrix: List[RecoveryFeasibilityRow]) -> dict:
    total_requests = sum(r.request_count_estimate for r in matrix)
    total_minutes = sum(r.time_estimate_min for r in matrix)
    return {
        "total_dates": len(matrix),
        "total_requests": total_requests,
        "total_minutes": round(total_minutes, 1),
        "total_hours": round(total_minutes / 60, 2),
        "http_pause_seconds": 2.0,
        "risk_level": "MEDIUM_HIGH",
        "rate_limit_risk": "IP_THROTTLE_POSSIBLE — TWSE rate limit policy unverified",
        "recommendation": "AUTHORIZE_PHASED: 1 date at a time, monitor for 429 errors",
    }


# ── Pipeline Reliability Architecture ─────────────────────────────────────────

@dataclass
class PipelineHealthCheck:
    check_id: str
    check_name: str
    trigger: str
    threshold: str
    action_on_fail: str
    currently_implemented: bool
    implementation_note: str


def build_pipeline_health_checks() -> List[PipelineHealthCheck]:
    return [
        PipelineHealthCheck(
            check_id="HC-01",
            check_name="MINIMUM_ROW_COUNT",
            trigger="After each daily price fetch",
            threshold="rows_inserted > 1000 for trading day",
            action_on_fail="Alert + write to error_log; do not mark day as complete",
            currently_implemented=False,
            implementation_note=(
                "No minimum row check in current backfill_daily_prices.py. "
                "Nov06/09 would have been caught immediately."
            ),
        ),
        PipelineHealthCheck(
            check_id="HC-02",
            check_name="API_DATE_VALIDATION",
            trigger="After each API response",
            threshold="api_date within 1 trading day of requested date",
            action_on_fail=(
                "Log WARNING; do not reject (off-by-1 acceptable for T+1 cron). "
                "Reject if api_date differs by >1 trading day."
            ),
            currently_implemented=False,
            implementation_note=(
                "TPEx patch adds error propagation for mismatch. "
                "TWSE mismatch (api_date=T-1 vs requested T) needs similar logic."
            ),
        ),
        PipelineHealthCheck(
            check_id="HC-03",
            check_name="VOLUME_NULL_RATE",
            trigger="After each daily price fetch",
            threshold="null_volume_pct < 80% (TPEx structural NULL is expected)",
            action_on_fail="Log INFO for TPEx; WARN for TWSE volume gaps",
            currently_implemented=False,
            implementation_note=(
                "Nov04: volume_null_rows=5715/6957=82% — this is expected (TPEx). "
                "Need to distinguish TPEx structural NULL from TWSE data errors."
            ),
        ),
        PipelineHealthCheck(
            check_id="HC-04",
            check_name="OHLC_SANITY",
            trigger="Before insert",
            threshold="high >= low, close in [low, high], all positive",
            action_on_fail="Reject row; log to error_summary",
            currently_implemented=False,
            implementation_note=(
                "Nov04: ohlc_invalid_rows=0 — currently passing, but check not explicit. "
                "Should be a hard validation."
            ),
        ),
        PipelineHealthCheck(
            check_id="HC-05",
            check_name="TRADING_DAY_CALENDAR_CONFIRM",
            trigger="Before fetch attempt",
            threshold="date is in TaiwanTradingCalendar_v1",
            action_on_fail="Skip fetch; log HOLIDAY_SKIP",
            currently_implemented=False,
            implementation_note=(
                "TaiwanTradingCalendar_v1 E2E verified in S56. "
                "Need to wire into daily pipeline pre-flight."
            ),
        ),
        PipelineHealthCheck(
            check_id="HC-06",
            check_name="DEDUP_ON_INSERT",
            trigger="Before INSERT",
            threshold="No existing row for (stock_id, date)",
            action_on_fail="SKIP or UPDATE depending on policy",
            currently_implemented=False,
            implementation_note=(
                "daily_prices UNIQUE(stock_id, date) assumed but not confirmed in schema. "
                "Need INSERT OR IGNORE or ON CONFLICT clause."
            ),
        ),
    ]


# ── Warrant Contamination Analysis ────────────────────────────────────────────

@dataclass
class UniverseContaminationReport:
    date: str
    total_rows: int
    ordinary_4d_rows: int
    etf_rows: int
    warrants_7xx: int
    warrants_02x: int
    contamination_pct: float
    research_denominator: int
    research_denominator_note: str


def build_contamination_report() -> UniverseContaminationReport:
    return UniverseContaminationReport(
        date="2026-11-04",
        total_rows=6957,
        ordinary_4d_rows=1969,
        etf_rows=159,
        warrants_7xx=4816,
        warrants_02x=13,
        contamination_pct=round((4816 + 13) / 6957 * 100, 1),
        research_denominator=1969,
        research_denominator_note=(
            "Coverage calculations must use 1969 (ordinary 4-digit 1000-9999) "
            "as denominator, NOT 6957. "
            "Warrants (4829) and ETFs (159) are NOT part of ordinary stock universe. "
            "S38/S39 official universe: 1996 common stocks (but 1969 is Nov04 actual count). "
            "Slight discrepancy may reflect newly listed/delisted stocks."
        ),
    )


# ── Main Report ────────────────────────────────────────────────────────────────

@dataclass
class CoverageRecoveryReport:
    audit_timestamp: str
    gap_inventory: List[DailyPriceGapEntry]
    root_cause_ledger: List[RootCauseEntry]
    recovery_feasibility_matrix: List[RecoveryFeasibilityRow]
    recovery_time_estimate: dict
    pipeline_health_checks: List[PipelineHealthCheck]
    contamination_report: UniverseContaminationReport


def build_coverage_recovery_report() -> CoverageRecoveryReport:
    matrix = build_recovery_feasibility_matrix()
    return CoverageRecoveryReport(
        audit_timestamp=datetime.now(timezone.utc).isoformat(),
        gap_inventory=build_gap_inventory(),
        root_cause_ledger=build_root_cause_ledger(),
        recovery_feasibility_matrix=matrix,
        recovery_time_estimate=compute_total_recovery_estimate(matrix),
        pipeline_health_checks=build_pipeline_health_checks(),
        contamination_report=build_contamination_report(),
    )
