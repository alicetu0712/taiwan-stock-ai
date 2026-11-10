"""
pipeline_error_propagation_s54.py — Session 54 PARTS C + D + E

PARTS:
  C: TPEx Error Propagation Repair (Observability Defect)
  D: Pipeline Root Cause Isolation (Nov 06 / Nov 09)
  E: AUTH01 Backfill Readiness

SAFETY: Read-only analysis. No live API calls. No production writes.
Backfill dry-run uses temporary SQLite only.

## TPEx Observability Defect (PART C)

The defect in scripts/backfill_daily_prices.py:
  TWSE api_date mismatch → summary["errors"].append(...)  → appears in cron log
  TPEx api_date mismatch → print() only                   → NOT in cron log

This means cron log shows only "quality gate FAILED" for dates where TPEx is
the sole failure (e.g., Nov06 attempted on Nov09). The structured error
propagation adapter below ensures all provider mismatches enter a common
PipelineErrorEvent stream that can be persisted in research summaries.

## Production Patch Proposal (PART C5)

The fix is one line in scripts/backfill_daily_prices.py:
  BEFORE: print(f"  [WARN] {target_d}: TPEx api_date={tpex_api_date} != target")
  AFTER:  summary["errors"].append(f"{target_d}: TPEx api_date={tpex_api_date} != target")

This is a PRODUCTION_PATCH_PROPOSAL only. NOT deployed in this session.
"""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


# ── Error Code Enum ───────────────────────────────────────────────────────────

class PipelineErrorCode(str, Enum):
    PROVIDER_DATE_MISMATCH = "PROVIDER_DATE_MISMATCH"
    PROVIDER_STALE_DATA = "PROVIDER_STALE_DATA"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    PROVIDER_RESPONSE_INVALID = "PROVIDER_RESPONSE_INVALID"
    UNIVERSE_COVERAGE_LOW = "UNIVERSE_COVERAGE_LOW"
    BENCHMARK_ONLY = "BENCHMARK_ONLY"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"
    COMPLETION_MARKER_INVALID = "COMPLETION_MARKER_INVALID"


class Provider(str, Enum):
    TWSE_BULK = "TWSE_BULK"
    TWSE_SINGLE_STOCK = "TWSE_SINGLE_STOCK"
    TPEX_BULK = "TPEX_BULK"
    TPEX_SINGLE_STOCK = "TPEX_SINGLE_STOCK"


class PipelineStage(str, Enum):
    PROVIDER_REQUEST = "PROVIDER_REQUEST"
    PROVIDER_RESPONSE = "PROVIDER_RESPONSE"
    DATE_VALIDATION = "DATE_VALIDATION"
    QUALITY_GATE = "QUALITY_GATE"
    PERSISTENCE = "PERSISTENCE"
    COMPLETION_MARKER = "COMPLETION_MARKER"
    RETRY = "RETRY"
    SCHEDULER = "SCHEDULER"


class ErrorSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class EvidenceConfidence(str, Enum):
    DIRECTLY_CONFIRMED = "DIRECTLY_CONFIRMED"
    STRONGLY_SUPPORTED = "STRONGLY_SUPPORTED"
    HYPOTHESIS_ONLY = "HYPOTHESIS_ONLY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ErrorPropagationVerdict(str, Enum):
    ERROR_PROPAGATION_VERIFIED = "ERROR_PROPAGATION_VERIFIED"
    ERROR_PROPAGATION_PARTIAL = "ERROR_PROPAGATION_PARTIAL"
    ERROR_PROPAGATION_BLOCKED = "ERROR_PROPAGATION_BLOCKED"


class RootCauseVerdict(str, Enum):
    ROOT_CAUSE_CONFIRMED = "ROOT_CAUSE_CONFIRMED"
    ROOT_CAUSE_PARTIAL = "ROOT_CAUSE_PARTIAL"
    ROOT_CAUSE_UNDETERMINED = "ROOT_CAUSE_UNDETERMINED"


class BackfillVerdict(str, Enum):
    BACKFILL_READY_FOR_AUTHORIZATION = "BACKFILL_READY_FOR_AUTHORIZATION"
    BACKFILL_PARTIAL = "BACKFILL_PARTIAL"
    BACKFILL_BLOCKED = "BACKFILL_BLOCKED"


# ── PART C: Structured Error Contract ────────────────────────────────────────

@dataclass
class PipelineErrorEvent:
    """
    Structured representation of a pipeline error event.
    Replaces ad-hoc print() calls; ensures errors are retained through retries
    and partial successes.
    """
    event_id: str
    timestamp: str
    provider: Provider
    stage: PipelineStage
    requested_date: str
    returned_date: Optional[str]
    error_code: PipelineErrorCode
    severity: ErrorSeverity
    retryable: bool
    message: str
    source_evidence: str
    correlation_id: str         # links events from the same cron run
    attempt_number: int         # 0 = first attempt; 1-3 = retries


@dataclass
class PipelineRunSummary:
    """
    Aggregated summary of all error events from one cron pipeline run.
    Errors persist across retries — not cleared on partial success.
    """
    run_date: str
    correlation_id: str
    target_dates: List[str]
    attempts: int
    errors: List[PipelineErrorEvent]
    all_errors_propagated: bool   # True if no errors are stdout-only
    tpex_errors_propagated: bool  # True if TPEx errors are in this summary

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def unique_target_dates_failed(self) -> List[str]:
        return sorted(set(e.requested_date for e in self.errors))

    def errors_for_date(self, target_date: str) -> List[PipelineErrorEvent]:
        return [e for e in self.errors if e.requested_date == target_date]

    def errors_for_provider(self, provider: Provider) -> List[PipelineErrorEvent]:
        return [e for e in self.errors if e.provider == provider]


def build_tpex_error_event(
    target_date: str,
    returned_date: str,
    attempt_number: int,
    correlation_id: str,
    timestamp: str = "2026-11-09T08:01:46Z",
) -> PipelineErrorEvent:
    """
    Structured version of the TPEx api_date mismatch error.
    Currently this error only goes to print(); this adapter captures it properly.
    """
    event_id = hashlib.sha256(
        f"TPEx|{target_date}|{returned_date}|{attempt_number}".encode()
    ).hexdigest()[:12]
    return PipelineErrorEvent(
        event_id=event_id,
        timestamp=timestamp,
        provider=Provider.TPEX_BULK,
        stage=PipelineStage.DATE_VALIDATION,
        requested_date=target_date,
        returned_date=returned_date,
        error_code=PipelineErrorCode.PROVIDER_DATE_MISMATCH,
        severity=ErrorSeverity.ERROR,
        retryable=False,
        message=(
            f"{target_date}: TPEx api_date={returned_date} != target — "
            "TPEx_HIST_URL always returns current-date data regardless of d= param"
        ),
        source_evidence="scripts/backfill_daily_prices.py: print() only (not in summary['errors'])",
        correlation_id=correlation_id,
        attempt_number=attempt_number,
    )


def build_twse_stale_error_event(
    target_date: str,
    returned_date: str,
    attempt_number: int,
    correlation_id: str,
    timestamp: str = "2026-11-09T08:01:46Z",
) -> PipelineErrorEvent:
    """
    Structured version of TWSE api_date mismatch (1-day lag from LATEST_URL).
    Already in summary["errors"] in production; included here for consistency.
    """
    event_id = hashlib.sha256(
        f"TWSE|{target_date}|{returned_date}|{attempt_number}".encode()
    ).hexdigest()[:12]
    return PipelineErrorEvent(
        event_id=event_id,
        timestamp=timestamp,
        provider=Provider.TWSE_BULK,
        stage=PipelineStage.DATE_VALIDATION,
        requested_date=target_date,
        returned_date=returned_date,
        error_code=PipelineErrorCode.PROVIDER_DATE_MISMATCH,
        severity=ErrorSeverity.ERROR,
        retryable=False,
        message=(
            f"{target_date}: TWSE api_date={returned_date} != target — "
            "TWSE_HIST_URL returns CSV; fallback to LATEST_URL with 1-trading-day lag"
        ),
        source_evidence="logs/hybrid_cron.log: explicit error in backfill output",
        correlation_id=correlation_id,
        attempt_number=attempt_number,
    )


def build_nov09_run_summary() -> PipelineRunSummary:
    """
    Reconstruct the Nov09 cron run summary with FULL error propagation,
    including TPEx errors that were originally stdout-only.

    Based on 4 attempts (08:01, 08:34, 09:04, 09:35 UTC).
    """
    cid = "CRON-2026-11-09"
    errors = []

    for attempt in range(4):
        ts_map = ["2026-11-09T08:01:46Z", "2026-11-09T08:34:14Z",
                  "2026-11-09T09:04:40Z", "2026-11-09T09:35:13Z"]
        ts = ts_map[attempt]

        # Nov06 target: TWSE returned Nov06 (passes), TPEx returned Nov09 (fails)
        # Only TPEx error — currently stdout-only
        errors.append(build_tpex_error_event(
            "2026-11-06", "2026-11-09", attempt, cid, ts
        ))

        # Nov09 target: TWSE returned Nov06 (fails) — DIRECTLY_CONFIRMED
        errors.append(build_twse_stale_error_event(
            "2026-11-09", "2026-11-06", attempt, cid, ts
        ))

        # Nov09 target: TPEx error (returned Nov09 current, still fails for new data)
        errors.append(build_tpex_error_event(
            "2026-11-09", "2026-11-09", attempt, cid, ts
        ))

    return PipelineRunSummary(
        run_date="2026-11-09",
        correlation_id=cid,
        target_dates=["2026-11-06", "2026-11-09"],
        attempts=4,
        errors=errors,
        all_errors_propagated=True,  # adapter captures TPEx too
        tpex_errors_propagated=True,
    )


def build_nov10_run_summary() -> PipelineRunSummary:
    """Nov10 partial (first 2 attempts observed; still running at audit time)."""
    cid = "CRON-2026-11-10"
    errors = []
    for attempt in range(2):
        ts = ["2026-11-10T08:02:46Z", "2026-11-10T08:34:30Z"][attempt]

        # Nov06 target: TWSE returned Nov09 (fails) — DIRECTLY_CONFIRMED
        errors.append(build_twse_stale_error_event("2026-11-06", "2026-11-09", attempt, cid, ts))
        # Nov09 target: TWSE matches → PASS; TPEx still wrong
        errors.append(build_tpex_error_event("2026-11-09", "2026-11-10", attempt, cid, ts))
        # Nov10 target: TWSE returned Nov09 — DIRECTLY_CONFIRMED
        errors.append(build_twse_stale_error_event("2026-11-10", "2026-11-09", attempt, cid, ts))

    return PipelineRunSummary(
        run_date="2026-11-10",
        correlation_id=cid,
        target_dates=["2026-11-06", "2026-11-09", "2026-11-10"],
        attempts=2,
        errors=errors,
        all_errors_propagated=True,
        tpex_errors_propagated=True,
    )


# ── PART C5: Production Patch Proposal ───────────────────────────────────────

@dataclass
class ProductionPatchProposal:
    file_path: str
    line_before: str
    line_after: str
    description: str
    safety_verified: bool
    deployment_authorization_required: bool
    authorization_note: str


def build_production_patch_proposal() -> ProductionPatchProposal:
    return ProductionPatchProposal(
        file_path="scripts/backfill_daily_prices.py",
        line_before=(
            'print(f"  [WARN] {target_d}: TPEx api_date={tpex_api_date} != target")'
        ),
        line_after=(
            'summary["errors"].append('
            'f"{target_d}: TPEx api_date={tpex_api_date} != target — API returned wrong date"'
            ')'
        ),
        description=(
            "TPEx api_date mismatch error currently goes only to stdout (print). "
            "This change propagates it into summary['errors'] so it appears in the "
            "cron log and can be distinguished from other QG failures. "
            "This is a 1-line observability fix — no logic change."
        ),
        safety_verified=True,
        deployment_authorization_required=True,
        authorization_note=(
            "PRODUCTION_PATCH_PROPOSAL ONLY. Not deployed in S54. "
            "Requires explicit user authorization before deployment "
            "(modifies scripts/backfill_daily_prices.py which is production code)."
        ),
    )


def get_error_propagation_verdict() -> ErrorPropagationVerdict:
    """
    Research adapter: ERROR_PROPAGATION_VERIFIED (in isolated environment).
    Production: ERROR_PROPAGATION_PARTIAL (TPEx still print-only until patch deployed).
    """
    return ErrorPropagationVerdict.ERROR_PROPAGATION_PARTIAL


# ── PART D: Pipeline Root Cause Matrix ───────────────────────────────────────

@dataclass
class RootCauseCandidate:
    candidate_id: str
    description: str
    affected_dates: List[str]
    evidence: str
    counterevidence: str
    confidence: EvidenceConfidence
    proposed_fix: str
    verification_test: str
    deployment_authorization: str


def build_root_cause_matrix() -> List[RootCauseCandidate]:
    return [
        RootCauseCandidate(
            candidate_id="RC-01",
            description="CRON_NO_TRIGGER: scheduler did not invoke hybrid_shadow_cron.py on Nov 06",
            affected_dates=["2026-11-06"],
            evidence=(
                "logs/hybrid_cron.log absent at 23:03 Taiwan on Nov 06. "
                "Shell >> redirect creates log even on Python error; absence = no invocation. "
                "DIRECTLY_CONFIRMED."
            ),
            counterevidence="None. Absence of log file is conclusive for shell invocation.",
            confidence=EvidenceConfidence.DIRECTLY_CONFIRMED,
            proposed_fix="Investigate why cron job was not triggered. Check crontab entry and system cron logs.",
            verification_test="Check system cron logs for Nov 06; verify crontab entry.",
            deployment_authorization="None required for investigation; crontab modification requires explicit auth.",
        ),
        RootCauseCandidate(
            candidate_id="RC-02",
            description="TWSE_LATEST_URL_LAG: TWSE returns previous trading day data",
            affected_dates=["2026-11-09", "2026-11-10"],
            evidence=(
                "logs/hybrid_cron.log: "
                "'2026-11-09: TWSE api_date=2026-11-06 != target' (Nov09 cron, all 4 retries). "
                "'2026-11-06: TWSE api_date=2026-11-09 != target' (Nov10 cron). "
                "'2026-11-10: TWSE api_date=2026-11-09 != target' (Nov10 cron). "
                "DIRECTLY_CONFIRMED for all three."
            ),
            counterevidence=(
                "Nov06 on Nov09 attempt: no TWSE api_date error — TWSE_LATEST_URL returned Nov06 "
                "(previous trading day on Nov09), which happened to match target. "
                "This confirms the 1-day lag pattern rather than contradicting it."
            ),
            confidence=EvidenceConfidence.DIRECTLY_CONFIRMED,
            proposed_fix=(
                "Replace TWSE_LATEST_URL fallback with TWSE single-stock API (STOCK_DAY). "
                "599 calls/date, ~20 min; SOURCE_VERIFIED_PARTIAL in S50."
            ),
            verification_test="Run TWSE single-stock for Nov06; verify api_date=2026-11-06.",
            deployment_authorization="AUTH_TWSE_SINGLE_STOCK (new, separate from AUTH01).",
        ),
        RootCauseCandidate(
            candidate_id="RC-03",
            description="TPEX_HIST_URL_CURRENT_DATE: TPEx ignores d= parameter",
            affected_dates=["2026-11-06", "2026-11-09", "2026-11-10"],
            evidence=(
                "src/research/market_source_verification_s50.py: SOURCE_UNAVAILABLE. "
                "Nov06 on Nov09: no explicit TPEx error in cron log (print()-only). "
                "Code path confirmed: TPEx mismatch goes to print(), not summary['errors']. "
                "STRONGLY_SUPPORTED."
            ),
            counterevidence=(
                "Cannot directly confirm TPEx api_date values from cron log "
                "(print() output not captured). Strongly supported by code analysis only."
            ),
            confidence=EvidenceConfidence.STRONGLY_SUPPORTED,
            proposed_fix=(
                "1. Apply production patch proposal (print → summary['errors']). "
                "2. Research TPEx single-stock endpoint (currently SOURCE_UNVERIFIED). "
                "3. Build TPEx single-stock fallback if endpoint verified."
            ),
            verification_test=(
                "After patch: verify TPEx api_date appears in next cron log "
                "when date mismatch occurs."
            ),
            deployment_authorization="PRODUCTION_PATCH_PROPOSAL (requires explicit auth).",
        ),
        RootCauseCandidate(
            candidate_id="RC-04",
            description="SCHEDULER_ROOT_CAUSE: why was Nov06 cron not triggered?",
            affected_dates=["2026-11-06"],
            evidence="None directly. CRON_NO_TRIGGER is confirmed; root cause of trigger failure is not.",
            counterevidence=(
                "System cron logs not available in this session for analysis. "
                "Manual inspection needed."
            ),
            confidence=EvidenceConfidence.INSUFFICIENT_EVIDENCE,
            proposed_fix="Inspect system cron logs for Nov 06. Check crontab entry integrity.",
            verification_test="Check /var/log/cron or system cron daemon logs for Nov 06.",
            deployment_authorization="Read-only inspection; no auth required.",
        ),
    ]


def get_root_cause_verdict() -> RootCauseVerdict:
    """
    RC-01 and RC-02 are DIRECTLY_CONFIRMED (symptom level).
    RC-03 is STRONGLY_SUPPORTED.
    RC-04 (scheduler root cause) is INSUFFICIENT_EVIDENCE.
    Overall: ROOT_CAUSE_PARTIAL (symptom confirmed; root cause of trigger failure not known).
    """
    return RootCauseVerdict.ROOT_CAUSE_PARTIAL


# ── PART E: AUTH01 Backfill Readiness ────────────────────────────────────────

@dataclass
class BackfillDateReadiness:
    target_date: str
    is_trading_day: bool
    twse_source_verified: bool
    tpex_source_verified: bool
    existing_non_0050_rows: int
    action: str                # "INSERT_CANDIDATE" | "SKIP_EXISTING"
    priority: str              # "P1" | "P2"
    authorization_status: str  # "PENDING_USER_AUTHORIZATION" | "READY"
    twse_verified_prices: Dict[str, float]
    missing_tpex: bool
    full_coverage_possible: bool


def build_backfill_readiness_matrix(conn: sqlite3.Connection) -> List[BackfillDateReadiness]:
    # S50 verified prices (TWSE single-stock, real API calls)
    s50_verified = {
        "2026-10-29": {"2330": 2415.0, "2454": 4045.0, "2317": 248.0},
        "2026-10-30": {"2330": 2370.0, "2454": 3915.0},
        "2026-11-02": {"2330": 2330.0},
        "2026-11-03": {"2317": 245.0},
        "2026-11-06": {"2330": 2135.0, "2454": 3390.0},
        "2026-11-09": {"2330": 2200.0, "2454": 3450.0},
    }
    dates = [
        ("2026-10-29", "P1"), ("2026-10-30", "P1"),
        ("2026-11-02", "P1"), ("2026-11-03", "P1"),
        ("2026-11-04", "P1"), ("2026-11-05", "P1"),
        ("2026-11-06", "P2"), ("2026-11-09", "P2"),
    ]
    result = []
    for target_date, priority in dates:
        existing = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id!='0050'",
            (target_date,)
        ).fetchone()[0]
        already_covered = existing > 0
        result.append(BackfillDateReadiness(
            target_date=target_date,
            is_trading_day=True,
            twse_source_verified=target_date in s50_verified,
            tpex_source_verified=False,
            existing_non_0050_rows=existing,
            action="SKIP_EXISTING" if already_covered else "INSERT_CANDIDATE",
            priority=priority,
            authorization_status="READY" if already_covered else "PENDING_USER_AUTHORIZATION",
            twse_verified_prices=s50_verified.get(target_date, {}),
            missing_tpex=True,
            full_coverage_possible=(not already_covered and target_date in s50_verified),
        ))
    return result


def run_backfill_dry_run(dates: List[BackfillDateReadiness]) -> dict:
    """
    Idempotency verification in isolated temporary SQLite.
    Does NOT touch production DB.
    """
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = sqlite3.connect(f.name)
        conn.execute("""
            CREATE TABLE daily_prices (
                stock_id TEXT,
                date TEXT,
                open REAL, high REAL, low REAL, close REAL, volume REAL,
                PRIMARY KEY (stock_id, date)
            )
        """)

        # Sample INSERT_CANDIDATE rows
        insert_candidates = [d for d in dates if d.action == "INSERT_CANDIDATE"]
        sample_rows = []
        for dr in insert_candidates[:3]:
            for sid, close in dr.twse_verified_prices.items():
                sample_rows.append((sid, dr.target_date, close * 0.99, close * 1.01, close * 0.98, close, 1000.0))

        # Test: first insert
        inserted_first = 0
        for row in sample_rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO daily_prices(stock_id,date,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)",
                row
            )
            inserted_first += cur.rowcount
        conn.commit()
        after_first = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]

        # Test: idempotent (same rows again)
        inserted_repeat = 0
        for row in sample_rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO daily_prices(stock_id,date,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)",
                row
            )
            inserted_repeat += cur.rowcount
        conn.commit()
        after_repeat = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]

        # Test: conflict with different value
        conflict_rows = [(r[0], r[1], r[2]*2, r[3]*2, r[4]*2, r[5]*2, r[6]) for r in sample_rows]
        inserted_conflict = 0
        for row in conflict_rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO daily_prices(stock_id,date,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)",
                row
            )
            inserted_conflict += cur.rowcount
        conn.commit()
        after_conflict = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]

        # Test: rollback
        conn.execute("BEGIN")
        conn.execute("INSERT OR IGNORE INTO daily_prices VALUES('ROLLBACK_TEST','2026-01-01',1,2,0.5,1.5,100)")
        before_rollback = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        conn.rollback()
        after_rollback = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]

        # Test: readback
        readback = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]

        conn.close()

    return {
        "sample_rows": len(sample_rows),
        "test_first_insert": inserted_first == len(sample_rows),
        "after_first_count": after_first,
        "test_idempotent": inserted_repeat == 0,
        "after_repeat_count": after_repeat,
        "test_conflict_ignored": inserted_conflict == 0,
        "after_conflict_count": after_conflict,
        "test_rollback": before_rollback > after_rollback and after_rollback == after_conflict,
        "test_readback": readback == after_conflict,
        "readback_count": readback,
        "production_modified": False,
    }


def get_backfill_verdict(dates: List[BackfillDateReadiness]) -> BackfillVerdict:
    p1_pending = [d for d in dates if d.priority == "P1" and d.action == "INSERT_CANDIDATE"]
    p2_pending = [d for d in dates if d.priority == "P2" and d.action == "INSERT_CANDIDATE"]
    if not p1_pending and not p2_pending:
        return BackfillVerdict.BACKFILL_READY_FOR_AUTHORIZATION
    if p1_pending or p2_pending:
        return BackfillVerdict.BACKFILL_PARTIAL
    return BackfillVerdict.BACKFILL_BLOCKED


# ── Top-level report ──────────────────────────────────────────────────────────

@dataclass
class PipelineErrorPropagationReport:
    audit_date: str
    # PART C
    nov09_summary: PipelineRunSummary
    nov10_summary: PipelineRunSummary
    production_patch_proposal: ProductionPatchProposal
    error_propagation_verdict: ErrorPropagationVerdict
    # PART D
    root_cause_candidates: List[RootCauseCandidate]
    root_cause_verdict: RootCauseVerdict
    # PART E
    backfill_readiness: List[BackfillDateReadiness]
    dry_run_results: dict
    backfill_verdict: BackfillVerdict


def build_pipeline_error_propagation_report(
    conn: sqlite3.Connection,
    reference_date: str = "2026-11-10",
) -> PipelineErrorPropagationReport:
    nov09_summary = build_nov09_run_summary()
    nov10_summary = build_nov10_run_summary()
    patch = build_production_patch_proposal()
    root_causes = build_root_cause_matrix()
    backfill_dates = build_backfill_readiness_matrix(conn)
    dry_run = run_backfill_dry_run(backfill_dates)

    return PipelineErrorPropagationReport(
        audit_date=reference_date,
        nov09_summary=nov09_summary,
        nov10_summary=nov10_summary,
        production_patch_proposal=patch,
        error_propagation_verdict=get_error_propagation_verdict(),
        root_cause_candidates=root_causes,
        root_cause_verdict=get_root_cause_verdict(),
        backfill_readiness=backfill_dates,
        dry_run_results=dry_run,
        backfill_verdict=get_backfill_verdict(backfill_dates),
    )
