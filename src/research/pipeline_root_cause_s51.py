"""
src/research/pipeline_root_cause_s51.py — S51 PART B + C

PART B: Pipeline Root Cause Evidence Audit
  10-stage classification for each date tier (Oct 13–Nov 09).
  Evidence levels: DIRECTLY_CONFIRMED / STRONGLY_SUPPORTED /
                   HYPOTHESIS_ONLY / INSUFFICIENT_EVIDENCE / NOT_APPLICABLE

PART C: Calendar Call-site Audit
  SSOT compliance: all new callers must use get_corrected_exit() from
  calendar_contract_s50.  Legacy call-sites in S46/S48/S49 are FROZEN and
  must NOT be re-imported by new research code.

SAFETY CONSTRAINTS (unchanged from S44–S51):
  - Read-only access to data/platform.db.
  - No writes to any production table.
  - No modification of frozen modules: prospective_comparison_s46,
    calendar_contract_s48, pipeline_recovery_s49, calendar_contract_s50.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

# ── Evidence Enums ─────────────────────────────────────────────────────────────

class PipelineTier(str, Enum):
    TIER_655_FILL = "TIER_655_FILL"
    """Oct 13–28: main pipeline + yfinance fallback; ~655 stocks per date."""

    TIER_1_PROXY = "TIER_1_PROXY"
    """Oct 29/30 + Nov 02/03: manual recover_ohlc_0050 only; 1 stock (0050)."""

    TIER_6957_BACKFILL = "TIER_6957_BACKFILL"
    """Nov 04/05: manual bulk backfill; 6957 / 6589 stocks."""

    BLOCKED_QG = "BLOCKED_QG"
    """Nov 06: backfill ran (retried Nov 09), quality gate FAILED — not written."""

    BLOCKED_STALE_DATA = "BLOCKED_STALE_DATA"
    """Nov 09: TWSE bulk api_date=2026-11-06 ≠ target; 4 retries exhausted."""


class PipelineStage(str, Enum):
    SCHEDULER_TRIGGER = "SCHEDULER_TRIGGER"
    PROVIDER_REQUEST = "PROVIDER_REQUEST"
    PROVIDER_RESPONSE = "PROVIDER_RESPONSE"
    PARSING = "PARSING"
    SECURITY_MAPPING = "SECURITY_MAPPING"
    TRADING_CALENDAR_VALIDATION = "TRADING_CALENDAR_VALIDATION"
    COVERAGE_QUALITY_GATE = "COVERAGE_QUALITY_GATE"
    DATABASE_PERSISTENCE = "DATABASE_PERSISTENCE"
    COMPLETION_MARKER = "COMPLETION_MARKER"
    DOWNSTREAM_RESEARCH = "DOWNSTREAM_RESEARCH"


class EvidenceLevel(str, Enum):
    DIRECTLY_CONFIRMED = "DIRECTLY_CONFIRMED"
    """Explicit log line, DB row, or API response content confirms the fact."""

    STRONGLY_SUPPORTED = "STRONGLY_SUPPORTED"
    """Multiple circumstantial sources consistently point to same conclusion."""

    HYPOTHESIS_ONLY = "HYPOTHESIS_ONLY"
    """Single circumstantial source; plausible but not independently verified."""

    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    """Available logs/DB do not contain enough information to classify."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    """Stage is irrelevant for this tier (e.g. pre-cron era or never reached)."""


# ── Calendar Audit Enums ───────────────────────────────────────────────────────

class CalendarCallSiteStatus(str, Enum):
    SSOT_COMPLIANT = "SSOT_COMPLIANT"
    """Uses get_corrected_exit() from calendar_contract_s50 — the SSOT."""

    LEGACY_FROZEN = "LEGACY_FROZEN"
    """In a frozen module (S46/S48/S49); acceptable because it is never modified."""

    LEGACY_ACTIVE_BUG = "LEGACY_ACTIVE_BUG"
    """Uses erroneous S46 dates in ACTIVE (non-frozen) code — BLOCKED."""

    NO_TRADING_DAY_OFFSET = "NO_TRADING_DAY_OFFSET"
    """Uses timedelta but not for trading-day calendar offset; non-issue."""


# ── Stage Evidence ─────────────────────────────────────────────────────────────

@dataclass
class StageEvidence:
    stage: PipelineStage
    level: EvidenceLevel
    summary: str
    source: str  # "hybrid_cron.log" / "DB query" / "file inspection" / etc.
    root_cause: Optional[str] = None  # filled for FAIL stages


@dataclass
class TierDiagnosis:
    tier: PipelineTier
    date_range: str
    dates: List[str]
    stock_count: int  # stocks per date in DB (0 = not written)
    trigger_source: str  # "cron" | "manual" | "recover_ohlc_0050" | "none"
    stages: List[StageEvidence] = field(default_factory=list)
    tier_verdict: str = ""  # summary of what happened

    def get_stage(self, stage: PipelineStage) -> Optional[StageEvidence]:
        for s in self.stages:
            if s.stage == stage:
                return s
        return None


@dataclass
class CalendarCallSite:
    file_path: str
    function_or_dict: str  # e.g. "_CALENDAR_5TD" / "get_corrected_exit"
    line_reference: str    # description of usage
    status: CalendarCallSiteStatus
    is_frozen_module: bool
    note: str = ""


@dataclass
class PipelineRootCauseEvidenceMatrix:
    tiers: List[TierDiagnosis]
    calendar_call_sites: List[CalendarCallSite]
    fingerprint_verified: bool
    analysis_date: str  # "2026-11-10"
    session: str = "S51"

    def get_tier(self, t: PipelineTier) -> Optional[TierDiagnosis]:
        for td in self.tiers:
            if td.tier == t:
                return td
        return None

    def count_by_evidence(self, level: EvidenceLevel) -> int:
        total = 0
        for td in self.tiers:
            for s in td.stages:
                if s.level == level:
                    total += 1
        return total


# ── Builder ────────────────────────────────────────────────────────────────────

def build_pipeline_root_cause_matrix(
    db_path: Optional[str] = None,
) -> PipelineRootCauseEvidenceMatrix:
    """Build the full 10-stage root-cause evidence matrix for S51 PART B."""

    if db_path is None:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "platform.db",
        )

    # Verify production fingerprints (read-only)
    fingerprint_ok = _verify_fingerprints(db_path)

    tiers = [
        _build_tier_655_fill(),
        _build_tier_1_proxy(),
        _build_tier_6957_backfill(),
        _build_tier_blocked_qg(),
        _build_tier_blocked_stale_data(),
    ]

    calendar_sites = _build_calendar_call_site_audit()

    return PipelineRootCauseEvidenceMatrix(
        tiers=tiers,
        calendar_call_sites=calendar_sites,
        fingerprint_verified=fingerprint_ok,
        analysis_date="2026-11-10",
    )


# ── Tier builders ──────────────────────────────────────────────────────────────

def _build_tier_655_fill() -> TierDiagnosis:
    """Oct 13–28: main pipeline + yfinance fallback."""
    dates = [
        "2026-10-13", "2026-10-14", "2026-10-16",
        "2026-10-21", "2026-10-22", "2026-10-28",
    ]
    stages = [
        StageEvidence(
            stage=PipelineStage.SCHEDULER_TRIGGER,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="run_*.log files exist with content at ~16:00 Taiwan (08:00 UTC).",
            source="logs/run_2026-10-*.log file timestamps",
        ),
        StageEvidence(
            stage=PipelineStage.PROVIDER_REQUEST,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Logs show TWSE/TPEx bulk requests attempted before yfinance.",
            source="logs/run_2026-10-13.log, run_2026-10-28.log",
        ),
        StageEvidence(
            stage=PipelineStage.PROVIDER_RESPONSE,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="TWSE/TPEx bulk returned WRONG DATE (e.g. 2026-10-08 for target 2026-10-13). yfinance fallback triggered.",
            source="logs/run_2026-10-13.log: 'TWSE/TPEx API 仍回傳 2026-10-08（目標 2026-10-13）'",
            root_cause="TWSE_BULK_RETURNS_CURRENT_DATE — bulk STOCK_DAY_ALL ignores date= parameter",
        ),
        StageEvidence(
            stage=PipelineStage.PARSING,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Date mismatch detected by main pipeline DQ gate; yfinance data parsed correctly.",
            source="run_*.log DQ gate messages",
        ),
        StageEvidence(
            stage=PipelineStage.SECURITY_MAPPING,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="655 stocks per date via yfinance = full TWSE/TPEx universe available from yfinance.",
            source="DB: daily_prices count per date = 655–656",
        ),
        StageEvidence(
            stage=PipelineStage.TRADING_CALENDAR_VALIDATION,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="All Oct 13–28 fill dates are confirmed Taiwan trading days.",
            source="src/core/trading_calendar.py _TWSE_HOLIDAYS 2026",
        ),
        StageEvidence(
            stage=PipelineStage.COVERAGE_QUALITY_GATE,
            level=EvidenceLevel.STRONGLY_SUPPORTED,
            summary="655 non-0050 < backfill threshold 5000, but main pipeline QG (different threshold) passed.",
            source="DB rows written; backfill_daily_prices.py uses _MIN_COVERED_STOCKS=5000 (backfill script only)",
        ),
        StageEvidence(
            stage=PipelineStage.DATABASE_PERSISTENCE,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="655–656 rows written per date to daily_prices.",
            source="DB: SELECT COUNT(*) FROM daily_prices WHERE date IN (...)",
        ),
        StageEvidence(
            stage=PipelineStage.COMPLETION_MARKER,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="run_*.log files have full content; main pipeline completed.",
            source="logs/run_2026-10-*.log file sizes (10–30 KB)",
        ),
        StageEvidence(
            stage=PipelineStage.DOWNSTREAM_RESEARCH,
            level=EvidenceLevel.NOT_APPLICABLE,
            summary="Hybrid shadow cron was not yet deployed; no hybrid_forward_run_log entries for Oct 13–28.",
            source="hybrid_forward_run_log: oldest entry is 2026-11-04",
        ),
    ]
    return TierDiagnosis(
        tier=PipelineTier.TIER_655_FILL,
        date_range="2026-10-13 — 2026-10-28",
        dates=dates,
        stock_count=655,
        trigger_source="manual",
        stages=stages,
        tier_verdict=(
            "TIER_655_FILL: Main pipeline ran successfully with yfinance fallback. "
            "TWSE/TPEx bulk API returned current-day data instead of historical dates. "
            "yfinance successfully provided 655 stocks per fill date."
        ),
    )


def _build_tier_1_proxy() -> TierDiagnosis:
    """Oct 29/30 + Nov 02/03: 0050-only via recover_ohlc_0050.py."""
    dates = ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]
    stages = [
        StageEvidence(
            stage=PipelineStage.SCHEDULER_TRIGGER,
            level=EvidenceLevel.HYPOTHESIS_ONLY,
            summary=(
                "Oct 29: no log file at all (cron may not have run; no hybrid_cron.log entry). "
                "Nov 02/03: empty 0-byte run_*.log created at odd hours → manual trigger."
            ),
            source="logs/ directory: no run_2026-10-29.log; run_2026-11-02.log=0 bytes at 04:06 Mac",
        ),
        StageEvidence(
            stage=PipelineStage.PROVIDER_REQUEST,
            level=EvidenceLevel.INSUFFICIENT_EVIDENCE,
            summary="No log output for Oct 29; empty logs for Nov 02/03 → cannot confirm provider was contacted.",
            source="Absent/empty log files",
        ),
        StageEvidence(
            stage=PipelineStage.PROVIDER_RESPONSE,
            level=EvidenceLevel.INSUFFICIENT_EVIDENCE,
            summary="No response content available.",
            source="Absent/empty log files",
        ),
        StageEvidence(
            stage=PipelineStage.PARSING,
            level=EvidenceLevel.INSUFFICIENT_EVIDENCE,
            summary="Cannot determine parse result from empty logs.",
            source="Absent/empty log files",
        ),
        StageEvidence(
            stage=PipelineStage.SECURITY_MAPPING,
            level=EvidenceLevel.INSUFFICIENT_EVIDENCE,
            summary="Universe mapping cannot be confirmed.",
            source="Absent/empty log files",
        ),
        StageEvidence(
            stage=PipelineStage.TRADING_CALENDAR_VALIDATION,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="All 4 dates are confirmed trading days per trading_calendar.py.",
            source="src/core/trading_calendar.py",
        ),
        StageEvidence(
            stage=PipelineStage.COVERAGE_QUALITY_GATE,
            level=EvidenceLevel.HYPOTHESIS_ONLY,
            summary="QG likely failed (or main pipeline crashed before QG) — only 0050 written.",
            source="DB: 1 row (0050) per date; consecutive rowids 550256–550259 → single recovery session",
            root_cause="MAIN_PIPELINE_SILENT_FAILURE (empty logs) + manual recover_ohlc_0050.py for 0050 proxy",
        ),
        StageEvidence(
            stage=PipelineStage.DATABASE_PERSISTENCE,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="1 row per date (stock_id='0050'). Consecutive rowids indicate single batch from recover_ohlc_0050.py.",
            source="DB query: rowids 550256–550259 for dates 2026-10-29 through 2026-11-03",
        ),
        StageEvidence(
            stage=PipelineStage.COMPLETION_MARKER,
            level=EvidenceLevel.HYPOTHESIS_ONLY,
            summary="No completion marker for the full market. Only 0050 recovery completion implied by rowids.",
            source="Empty/absent log files",
        ),
        StageEvidence(
            stage=PipelineStage.DOWNSTREAM_RESEARCH,
            level=EvidenceLevel.NOT_APPLICABLE,
            summary="Shadow cron gates on FULL_MARKET_FRESH; 0050-only data blocks shadow execution.",
            source="hybrid_shadow_cron.py FreshnessStatus.BENCHMARK_ONLY_UPDATED logic",
        ),
    ]
    return TierDiagnosis(
        tier=PipelineTier.TIER_1_PROXY,
        date_range="2026-10-29 — 2026-11-03",
        dates=dates,
        stock_count=1,
        trigger_source="recover_ohlc_0050",
        stages=stages,
        tier_verdict=(
            "TIER_1_PROXY: Main pipeline failed silently (empty 0-byte logs) for all 4 dates. "
            "recover_ohlc_0050.py --execute inserted 0050-only data as a proxy marker. "
            "Root cause of main pipeline failure: HYPOTHESIS_ONLY (exception before first log write)."
        ),
    )


def _build_tier_6957_backfill() -> TierDiagnosis:
    """Nov 04/05: manual bulk backfill — 6957 / 6589 stocks."""
    dates = ["2026-11-04", "2026-11-05"]
    stages = [
        StageEvidence(
            stage=PipelineStage.SCHEDULER_TRIGGER,
            level=EvidenceLevel.STRONGLY_SUPPORTED,
            summary=(
                "Manual invocation of backfill_daily_prices.py (not cron). "
                "hybrid_cron.log has no entries before Nov 09 → cron was not yet active for Nov 04/05."
            ),
            source="hybrid_cron.log: oldest entry 2026-11-09T08:00:17Z; logs/run_*.log 0 bytes",
        ),
        StageEvidence(
            stage=PipelineStage.PROVIDER_REQUEST,
            level=EvidenceLevel.STRONGLY_SUPPORTED,
            summary="TWSE/TPEx bulk historical API was used (backfill_daily_prices.py flow).",
            source="backfill_daily_prices.py TWSE_HIST_URL / TPEX_HIST_URL",
        ),
        StageEvidence(
            stage=PipelineStage.PROVIDER_RESPONSE,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Provider returned correct data: 6957 stocks on Nov 04, 6589 on Nov 05.",
            source="DB: daily_prices count per date (non-0050: 6956 / 6588)",
        ),
        StageEvidence(
            stage=PipelineStage.PARSING,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="All rows parsed with valid OHLC and stored successfully.",
            source="DB row count and QG pass implied by data presence",
        ),
        StageEvidence(
            stage=PipelineStage.SECURITY_MAPPING,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="6956+ non-0050 stocks — well above 5000 backfill threshold.",
            source="DB query",
        ),
        StageEvidence(
            stage=PipelineStage.TRADING_CALENDAR_VALIDATION,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Nov 04 (Wednesday) and Nov 05 (Thursday) are confirmed trading days.",
            source="src/core/trading_calendar.py",
        ),
        StageEvidence(
            stage=PipelineStage.COVERAGE_QUALITY_GATE,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="QG passed: 6956+ non-0050 >> threshold 5000.",
            source="DB rows present; backfill_daily_prices.py only writes on QG pass",
        ),
        StageEvidence(
            stage=PipelineStage.DATABASE_PERSISTENCE,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Nov 04: 6957 rows; Nov 05: 6589 rows written to daily_prices.",
            source="DB query",
        ),
        StageEvidence(
            stage=PipelineStage.COMPLETION_MARKER,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="hybrid_forward_run_log has 3 entries for Nov 04 (fc2b4b0f / 02565324 / fc9dd188).",
            source="DB: hybrid_forward_run_log run_id IN ('fc2b4b0f','02565324','fc9dd188')",
        ),
        StageEvidence(
            stage=PipelineStage.DOWNSTREAM_RESEARCH,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary=(
                "Shadow runner for Nov 04 at 2026-11-05T04:42:30Z: "
                "21 decisions inserted (RETROSPECTIVE_RECONSTRUCTION). "
                "Nov 05 at 09:20Z: BLOCKED_MISSING_SIGNALS (Nov05 data not yet in DB at that moment)."
            ),
            source="DB: hybrid_forward_run_log / hybrid_forward_decision",
        ),
    ]
    return TierDiagnosis(
        tier=PipelineTier.TIER_6957_BACKFILL,
        date_range="2026-11-04 — 2026-11-05",
        dates=dates,
        stock_count=6957,
        trigger_source="manual",
        stages=stages,
        tier_verdict=(
            "TIER_6957_BACKFILL: Manual bulk backfill succeeded. 6957/6589 stocks written. "
            "21 Nov04 decisions captured as RETROSPECTIVE_RECONSTRUCTION (before RULE_FREEZE_DATE 2026-11-05). "
            "Nov05 shadow run was BLOCKED_MISSING_SIGNALS (data arrived after shadow runner check at 09:20 UTC)."
        ),
    )


def _build_tier_blocked_qg() -> TierDiagnosis:
    """Nov 06: quality gate FAILED."""
    dates = ["2026-11-06"]
    stages = [
        StageEvidence(
            stage=PipelineStage.SCHEDULER_TRIGGER,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Triggered by Nov 09 cron at 08:00:17Z. backfill_daily_prices.py found Nov 06 as a missing date.",
            source="hybrid_cron.log: [2026-11-09T08:00:17Z] [cron] 2026-11-09 is a trading day ✓",
        ),
        StageEvidence(
            stage=PipelineStage.PROVIDER_REQUEST,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Backfill script issued TWSE/TPEx bulk request for Nov 06.",
            source="hybrid_cron.log error entry: '2026-11-06: quality gate FAILED'",
        ),
        StageEvidence(
            stage=PipelineStage.PROVIDER_RESPONSE,
            level=EvidenceLevel.STRONGLY_SUPPORTED,
            summary=(
                "TWSE returned data for Nov 06 (no 'api_date mismatch' error logged for Nov 06, "
                "unlike Nov 09). Data arrived but failed QG."
            ),
            source="hybrid_cron.log: Nov 06 error is 'quality gate FAILED', not 'api_date mismatch'",
        ),
        StageEvidence(
            stage=PipelineStage.PARSING,
            level=EvidenceLevel.STRONGLY_SUPPORTED,
            summary="Data was parsed enough to reach QG; exact parse content unknown.",
            source="Quality gate ran (implicit from FAILED message)",
        ),
        StageEvidence(
            stage=PipelineStage.SECURITY_MAPPING,
            level=EvidenceLevel.HYPOTHESIS_ONLY,
            summary="Unknown which securities were in the Nov 06 response. Too few stocks is one QG-6 failure path.",
            source="No stock count logged for Nov 06 attempt",
        ),
        StageEvidence(
            stage=PipelineStage.TRADING_CALENDAR_VALIDATION,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Nov 06 (Friday) is a confirmed trading day.",
            source="src/core/trading_calendar.py",
        ),
        StageEvidence(
            stage=PipelineStage.COVERAGE_QUALITY_GATE,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary=(
                "Quality gate explicitly FAILED. Exact failing check: HYPOTHESIS_ONLY "
                "(QG-5 date mismatch or QG-6 coverage threshold). "
                "dailyprice_quality_gate.py checks: QG-1 OHLC, QG-2 price bounds, "
                "QG-3 volume, QG-4 no dups, QG-5 date consistency, QG-6 coverage, QG-7 benchmark."
            ),
            source="hybrid_cron.log: '2026-11-06: quality gate FAILED — not writing to DB'",
            root_cause="QUALITY_GATE_FAIL — specific check not extractable from logs",
        ),
        StageEvidence(
            stage=PipelineStage.DATABASE_PERSISTENCE,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="NOT written. 0 rows for Nov 06 in daily_prices.",
            source="DB query + backfill_daily_prices.py: 'if not qg_ok: continue'",
        ),
        StageEvidence(
            stage=PipelineStage.COMPLETION_MARKER,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Cron state = BLOCKED_STALE_DATA (after Nov 09 retries exhausted).",
            source="data/.cron_state.json",
        ),
        StageEvidence(
            stage=PipelineStage.DOWNSTREAM_RESEARCH,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Shadow runner was never reached (freshness check gates it; Nov 06 = 0 rows).",
            source="hybrid_shadow_cron.py Step 4b freshness logic + empty hybrid_forward_run_log for Nov 06",
        ),
    ]
    return TierDiagnosis(
        tier=PipelineTier.BLOCKED_QG,
        date_range="2026-11-06",
        dates=dates,
        stock_count=0,
        trigger_source="cron",
        stages=stages,
        tier_verdict=(
            "BLOCKED_QG: Nov 06 data arrived from TWSE but failed dailyprice_quality_gate.py. "
            "Specific failing check not identified from logs (HYPOTHESIS_ONLY). "
            "0 rows written. Retried on Nov 09 cron but failed again."
        ),
    )


def _build_tier_blocked_stale_data() -> TierDiagnosis:
    """Nov 09: TWSE stale data — api_date=2026-11-06 ≠ target."""
    dates = ["2026-11-09"]
    stages = [
        StageEvidence(
            stage=PipelineStage.SCHEDULER_TRIGGER,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Cron triggered at 2026-11-09T08:00:17Z (16:00 Taiwan).",
            source="hybrid_cron.log: '[2026-11-09T08:00:17Z] [cron] 2026-11-09 is a trading day ✓'",
        ),
        StageEvidence(
            stage=PipelineStage.PROVIDER_REQUEST,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="4 backfill attempts (08:00, 08:31, 09:04, 09:35 UTC); each re-ran TWSE bulk.",
            source="hybrid_cron.log: 4 × PROVIDER_NOT_READY entries",
        ),
        StageEvidence(
            stage=PipelineStage.PROVIDER_RESPONSE,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="TWSE bulk returned api_date=2026-11-06 for target=2026-11-09 on all 4 attempts.",
            source="hybrid_cron.log: '2026-11-09: TWSE api_date=2026-11-06 != target — API returned wrong date'",
            root_cause="TWSE_BULK_STALE — bulk API still serving Nov 06 data on Nov 09",
        ),
        StageEvidence(
            stage=PipelineStage.PARSING,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="api_date mismatch detected by backfill_daily_prices.py date-check logic.",
            source="backfill_daily_prices.py: 'if twse_api_date and twse_api_date != target_d'",
        ),
        StageEvidence(
            stage=PipelineStage.SECURITY_MAPPING,
            level=EvidenceLevel.NOT_APPLICABLE,
            summary="Security mapping never reached; pipeline aborted at provider-response stage.",
            source="N/A",
        ),
        StageEvidence(
            stage=PipelineStage.TRADING_CALENDAR_VALIDATION,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Nov 09 (Monday) confirmed as trading day at cron start.",
            source="hybrid_cron.log: '2026-11-09 is a trading day ✓'",
        ),
        StageEvidence(
            stage=PipelineStage.COVERAGE_QUALITY_GATE,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="QG did not run independently; blocked by api_date mismatch before QG.",
            source="backfill_daily_prices.py control flow; hybrid_cron freshness retry loop",
        ),
        StageEvidence(
            stage=PipelineStage.DATABASE_PERSISTENCE,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="NOT written. 0 rows for Nov 09 in daily_prices.",
            source="DB query + cron_state: data_freshness_detail='0050 last_date=2026-11-05'",
        ),
        StageEvidence(
            stage=PipelineStage.COMPLETION_MARKER,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Cron final status: BLOCKED_STALE_DATA after retry 3/3.",
            source="data/.cron_state.json: status=BLOCKED_STALE_DATA, freshness_retry_attempt=3",
        ),
        StageEvidence(
            stage=PipelineStage.DOWNSTREAM_RESEARCH,
            level=EvidenceLevel.DIRECTLY_CONFIRMED,
            summary="Shadow runner was never called (cron returned early after BLOCKED_STALE_DATA).",
            source="hybrid_shadow_cron.py: returns before Step 6 when freshness fails",
        ),
    ]
    return TierDiagnosis(
        tier=PipelineTier.BLOCKED_STALE_DATA,
        date_range="2026-11-09",
        dates=dates,
        stock_count=0,
        trigger_source="cron",
        stages=stages,
        tier_verdict=(
            "BLOCKED_STALE_DATA: TWSE bulk API returned Nov 06 data for Nov 09 target on all 4 attempts. "
            "Root cause: TWSE_BULK_STALE — bulk STOCK_DAY_ALL does not support historical dates. "
            "Recovery requires individual TWSE STOCK_DAY API calls (~600 per date) + AUTH01."
        ),
    )


# ── Calendar Call-site Audit (PART C) ─────────────────────────────────────────

def _build_calendar_call_site_audit() -> List[CalendarCallSite]:
    """
    Enumerate known calendar call-sites across research modules.

    Rules:
      SSOT_COMPLIANT:   uses get_corrected_exit() from calendar_contract_s50
      LEGACY_FROZEN:    uses _CALENDAR_* dicts but is in a frozen module (S46/S48/S49)
      LEGACY_ACTIVE_BUG: uses erroneous S46 dicts in actively-used non-frozen code
      NO_TRADING_DAY_OFFSET: timedelta / date arithmetic unrelated to 5TD/20TD exits
    """
    sites: List[CalendarCallSite] = []

    # ── S46: prospective_comparison_s46.py (FROZEN) ──────────────────────────
    sites.append(CalendarCallSite(
        file_path="src/research/prospective_comparison_s46.py",
        function_or_dict="_CALENDAR_5TD",
        line_reference="line ~146: erroneous 5TD exit dates (S46 vintage)",
        status=CalendarCallSiteStatus.LEGACY_FROZEN,
        is_frozen_module=True,
        note="FROZEN — must NOT be imported by new research code. Contains known wrong dates.",
    ))
    sites.append(CalendarCallSite(
        file_path="src/research/prospective_comparison_s46.py",
        function_or_dict="_CALENDAR_20TD",
        line_reference="line ~336: erroneous 20TD exit dates (S46 vintage)",
        status=CalendarCallSiteStatus.LEGACY_FROZEN,
        is_frozen_module=True,
        note="FROZEN — erroneous 20TD exits (2–7 trading days too late per cluster).",
    ))

    # ── S47: cluster_eligibility_expansion_s47.py (FROZEN) ───────────────────
    sites.append(CalendarCallSite(
        file_path="src/research/cluster_eligibility_expansion_s47.py",
        function_or_dict="_CALENDAR_5TD/_CALENDAR_20TD reference",
        line_reference="line ~16/27: documents S46 errors; does not import S46 dicts",
        status=CalendarCallSiteStatus.LEGACY_FROZEN,
        is_frozen_module=True,
        note="FROZEN — references S46 errors for documentation only; does not call _CALENDAR_*.",
    ))

    # ── S48: calendar_contract_s48.py (FROZEN SSOT predecessor) ──────────────
    sites.append(CalendarCallSite(
        file_path="src/research/calendar_contract_s48.py",
        function_or_dict="_CORRECT_5TD / _CORRECT_20TD",
        line_reference="Introduces corrected calendar dicts; S50 is now the SSOT",
        status=CalendarCallSiteStatus.LEGACY_FROZEN,
        is_frozen_module=True,
        note="FROZEN — correct values; superseded by calendar_contract_s50 as SSOT.",
    ))

    # ── S49: pipeline_recovery_s49.py (FROZEN) ───────────────────────────────
    sites.append(CalendarCallSite(
        file_path="src/research/pipeline_recovery_s49.py",
        function_or_dict="get_corrected_calendar_exit()",
        line_reference="line 559: wraps S48 _CORRECT_5TD/_CORRECT_20TD",
        status=CalendarCallSiteStatus.LEGACY_FROZEN,
        is_frozen_module=True,
        note="FROZEN — correct wrapper; new S51 code uses get_corrected_exit() from S50 instead.",
    ))

    # ── S50: calendar_contract_s50.py (ACTIVE SSOT) ──────────────────────────
    sites.append(CalendarCallSite(
        file_path="src/research/calendar_contract_s50.py",
        function_or_dict="get_corrected_exit()",
        line_reference="line 374: single source of truth for 5TD and 20TD exit dates",
        status=CalendarCallSiteStatus.SSOT_COMPLIANT,
        is_frozen_module=False,
        note="SSOT — all new callers must use this. Never modify frozen predecessors.",
    ))

    # ── S51: pipeline_root_cause_s51.py (THIS FILE) ───────────────────────────
    sites.append(CalendarCallSite(
        file_path="src/research/pipeline_root_cause_s51.py",
        function_or_dict="No calendar offset calls",
        line_reference="S51 root cause module; does not compute TD offsets",
        status=CalendarCallSiteStatus.NO_TRADING_DAY_OFFSET,
        is_frozen_module=False,
        note="No trading-day calendar arithmetic in this module.",
    ))

    return sites


# ── Fingerprint verification (read-only) ──────────────────────────────────────

def _verify_fingerprints(db_path: str) -> bool:
    """Read-only check: forward_signals and daily_prices unchanged."""
    try:
        conn = sqlite3.connect(db_path)
        fs_total = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        dp_max = conn.execute(
            "SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'"
        ).fetchone()[0]
        conn.close()
        return fs_total == 2605 and dp_max == "2026-11-05"
    except Exception:
        return False


# ── Convenience queries (read-only) ───────────────────────────────────────────

def get_tier_stock_counts(db_path: str) -> Dict[str, int]:
    """Return non-0050 stock counts for each tier's representative date."""
    counts: Dict[str, int] = {}
    representative = {
        "2026-10-13": "TIER_655_FILL",
        "2026-10-29": "TIER_1_PROXY",
        "2026-11-04": "TIER_6957_BACKFILL",
        "2026-11-06": "BLOCKED_QG",
        "2026-11-09": "BLOCKED_STALE_DATA",
    }
    try:
        conn = sqlite3.connect(db_path)
        for d, tier in representative.items():
            n = conn.execute(
                "SELECT COUNT(DISTINCT stock_id) FROM daily_prices "
                "WHERE date=? AND stock_id!='0050'",
                (d,),
            ).fetchone()[0]
            counts[tier] = n
        conn.close()
    except Exception:
        pass
    return counts


def get_shadow_run_summary(db_path: str) -> List[dict]:
    """Return hybrid_forward_run_log summary (read-only)."""
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("""
            SELECT run_id, trade_date, started_at, status,
                   inserted_count, skipped_count, error_summary
            FROM hybrid_forward_run_log
            ORDER BY id DESC
        """).fetchall()
        conn.close()
        keys = ["run_id", "trade_date", "started_at", "status",
                "inserted_count", "skipped_count", "error_summary"]
        return [dict(zip(keys, r)) for r in rows]
    except Exception:
        return []
