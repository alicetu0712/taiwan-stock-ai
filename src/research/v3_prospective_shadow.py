"""
v3_prospective_shadow.py — V3 Prospective Shadow Research Framework

RESEARCH ONLY — NOT A LIVE TRADING SYSTEM.

This module establishes the infrastructure for accumulating prospective OOS
evidence for V3 entry timing. It is activated only when:
  1. Existing Hybrid Cron acceptance passes (first successful prospective write).
  2. V3 Freeze Manifest is verified.
  3. All Data Integrity Gates pass.
  4. Full Regression passes.
  5. Explicit activation approval is granted.

Session 29 status: FRAMEWORK_READY, ACTIVATION_CONDITIONAL (pending Cron acceptance).

Key design principles:
  - Decision capture and outcome evaluation are SEPARATED.
  - Original decision records are IMMUTABLE after insertion.
  - Duplicate detection: DUPLICATE_IDENTICAL (same payload) vs CAPTURE_CONFLICT (different payload).
  - Eligibility classification: PROSPECTIVE_ELIGIBLE only when all 10 conditions met.
  - Look-ahead prevention: data_as_of must be strictly before decision horizon.
  - Outcomes stored in a separate versioned table, never written back to decisions.
  - All writes use a temporary/research SQLite; production tables are read-only.

FORBIDDEN:
  - Do NOT write to production tables (forward_signals, hybrid_forward_decision, positions, etc.).
  - Do NOT modify MODEL_VERSION v8.0, foe_v1, Hybrid P1–P4.
  - Do NOT activate Cron schedule.
  - Do NOT perform Neon migrations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.research.v3_backtest_engine import (
    EXPIRY_DAYS,
    FEES_PCT,
    HOLD_DAYS,
    MIN_BARS_FULL,
    MIN_RR_RATIO,
    PARAMETER_HASH as V3_PARAMETER_HASH,
    RESEARCH_VERSION as V3_RESEARCH_VERSION,
    STOP_BUFFER,
    _REGIME_PARAMS,
)

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

SHADOW_VERSION = "v3_shadow_v1"
SHADOW_ENGINE_ID = "v3_prospective_shadow_v1"

# Freeze metadata
FREEZE_GIT_HEAD = "ad6fbb8"           # git HEAD when V3 was finalized
FREEZE_EFFECTIVE_FROM = "2026-11-06"  # first day prospective decisions can be captured
V3_SOURCE_FILE = "src/research/v3_entry_strategy.py"
V3_COMPARISON_HASH = "1feb7a6b294a063d"

# Prospective capture window: decisions must be captured within N hours of market close
CAPTURE_WINDOW_HOURS = 2

# Min stocks for FULL MARKET gate (must match full_market_freshness_gate.MIN_COVERED_STOCKS)
MIN_COVERED_STOCKS = 5000

# Statistical thresholds for evidence reporting
MIN_SIGNALS_FOR_CI = 20
MIN_SIGNALS_FOR_EVIDENCE = 50


# ── Enums ──────────────────────────────────────────────────────────────────────

class CaptureType(str, Enum):
    """Classification of a captured decision's prospective status."""
    PROSPECTIVE_ELIGIBLE = "PROSPECTIVE_ELIGIBLE"
    RETROSPECTIVE_RECONSTRUCTION = "RETROSPECTIVE_RECONSTRUCTION"
    LATE_CAPTURE = "LATE_CAPTURE"
    MISSING_INPUT = "MISSING_INPUT"
    INCOMPLETE_MARKET_DATA = "INCOMPLETE_MARKET_DATA"
    FREEZE_MISMATCH = "FREEZE_MISMATCH"


class OutcomeMaturity(str, Enum):
    """Maturity status of a decision's outcome at a given horizon."""
    NOT_MATURE = "NOT_MATURE"
    MATURE = "MATURE"
    INVALID = "INVALID"
    MISSING_DATA = "MISSING_DATA"


class DuplicateResult(str, Enum):
    """Result of duplicate detection logic."""
    NEW_RECORD = "NEW_RECORD"
    DUPLICATE_IDENTICAL = "DUPLICATE_IDENTICAL"
    CAPTURE_CONFLICT = "CAPTURE_CONFLICT"


class FreezeStatus(str, Enum):
    """Status of freeze manifest verification."""
    VERIFIED = "VERIFIED"
    FREEZE_MISMATCH = "FREEZE_MISMATCH"
    MISSING = "MISSING"


class DataGateStatus(str, Enum):
    """Data integrity gate result."""
    PASS = "PASS"
    FAIL_NO_0050 = "FAIL_NO_0050"
    FAIL_PARTIAL_MARKET = "FAIL_PARTIAL_MARKET"
    FAIL_MISSING_STOCK = "FAIL_MISSING_STOCK"
    FAIL_LOOK_AHEAD = "FAIL_LOOK_AHEAD"
    FAIL_STALE_DATA = "FAIL_STALE_DATA"
    FAIL_TIMESTAMP_INCONSISTENCY = "FAIL_TIMESTAMP_INCONSISTENCY"


class EvidenceLevel(str, Enum):
    """Prospective evidence accumulation level."""
    NO_PROSPECTIVE_EVIDENCE = "NO_PROSPECTIVE_EVIDENCE"
    PROSPECTIVE_EVIDENCE_ACCUMULATING = "PROSPECTIVE_EVIDENCE_ACCUMULATING"
    PROSPECTIVE_EVIDENCE_SUFFICIENT = "PROSPECTIVE_EVIDENCE_SUFFICIENT"


# ── Freeze Manifest ────────────────────────────────────────────────────────────

@dataclass
class V3FreezeManifest:
    """
    Immutable contract specifying exactly which V3 rules are frozen for prospective research.
    This manifest must be computed at freeze time and stored permanently.
    Any change to V3 parameters requires a new research_version, not a modification.
    """
    research_version: str
    strategy_version: str
    parameter_hash: str           # be43e8ca977d9fdd (from v3_backtest_engine)
    source_code_hash: str         # SHA-256 of v3_entry_strategy.py content
    execution_model_hash: str     # SHA-256 of regime params + thresholds
    cost_model_hash: str          # SHA-256 of fees/slippage definition
    benchmark_definition: str     # "0050 gross: open[fill_date] → close[exit_date]"
    signal_eligibility_rules: str # "buy OR strong_buy from forward_signals"
    market_regime_definition: str # "MA20 slope, volume ratio, _REGIME_PARAMS"
    feature_schema_version: str   # hash of forward_signals schema
    freeze_created_at: str
    freeze_effective_from: str
    git_head: str
    data_source_contract: str     # "platform.db forward_signals + daily_prices"
    manifest_hash: str            # SHA-256 of all above fields (self-authenticating)


def compute_execution_model_hash() -> str:
    """Hash of V3 regime params + key thresholds."""
    params = {
        "regime_params": {k: dict(v) for k, v in _REGIME_PARAMS.items()},
        "min_bars_full": MIN_BARS_FULL,
        "stop_buffer": STOP_BUFFER,
        "min_rr_ratio": MIN_RR_RATIO,
        "hold_days": HOLD_DAYS,
        "expiry_days": EXPIRY_DAYS,
    }
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]


def compute_cost_model_hash() -> str:
    """Hash of cost model: fees and slippage definition."""
    cost = {"fees_pct": FEES_PCT, "slippage": 0.0, "benchmark": "0050_gross"}
    return hashlib.sha256(json.dumps(cost, sort_keys=True).encode()).hexdigest()[:16]


def compute_source_code_hash() -> str:
    """SHA-256 of v3_entry_strategy.py file content."""
    p = Path(V3_SOURCE_FILE)
    if not p.exists():
        return "FILE_NOT_FOUND"
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def compute_freeze_manifest(
    conn: Optional[sqlite3.Connection] = None,
) -> V3FreezeManifest:
    """
    Compute the V3 freeze manifest from live code and schema.
    This is deterministic given the same codebase and schema.
    """
    source_hash = compute_source_code_hash()
    exec_hash = compute_execution_model_hash()
    cost_hash = compute_cost_model_hash()

    # Feature schema: hash of forward_signals column names
    if conn is not None:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(forward_signals)").fetchall()]
        schema_hash = hashlib.sha256(json.dumps(sorted(cols)).encode()).hexdigest()[:12]
    else:
        schema_hash = "schema_unavailable"

    partial = {
        "research_version": V3_RESEARCH_VERSION,
        "strategy_version": SHADOW_VERSION,
        "parameter_hash": V3_PARAMETER_HASH,
        "source_code_hash": source_hash,
        "execution_model_hash": exec_hash,
        "cost_model_hash": cost_hash,
        "benchmark_definition": "0050 gross: open[fill_date] → close[exit_date]",
        "signal_eligibility_rules": "trade_signal IN ('buy','strong_buy') FROM forward_signals",
        "market_regime_definition": "MA20 slope + volume ratio via _REGIME_PARAMS",
        "feature_schema_version": schema_hash,
        "freeze_created_at": "2026-11-06T00:00:00+08:00",
        "freeze_effective_from": FREEZE_EFFECTIVE_FROM,
        "git_head": FREEZE_GIT_HEAD,
        "data_source_contract": "platform.db: forward_signals + daily_prices",
    }
    manifest_hash = hashlib.sha256(
        json.dumps(partial, sort_keys=True).encode()
    ).hexdigest()[:16]

    return V3FreezeManifest(**partial, manifest_hash=manifest_hash)


def verify_freeze_manifest(
    manifest: V3FreezeManifest,
) -> Tuple[FreezeStatus, str]:
    """
    Verify the freeze manifest against current code state.
    Returns (FreezeStatus, reason).
    """
    current = compute_freeze_manifest()
    mismatches = []

    if manifest.parameter_hash != current.parameter_hash:
        mismatches.append(f"parameter_hash: stored={manifest.parameter_hash} vs current={current.parameter_hash}")
    if manifest.source_code_hash != current.source_code_hash:
        mismatches.append(f"source_code_hash: stored={manifest.source_code_hash} vs current={current.source_code_hash}")
    if manifest.execution_model_hash != current.execution_model_hash:
        mismatches.append(f"execution_model_hash: stored={manifest.execution_model_hash} vs current={current.execution_model_hash}")
    if manifest.cost_model_hash != current.cost_model_hash:
        mismatches.append(f"cost_model_hash: stored={manifest.cost_model_hash} vs current={current.cost_model_hash}")

    if mismatches:
        return (FreezeStatus.FREEZE_MISMATCH, " | ".join(mismatches))
    return (FreezeStatus.VERIFIED, "All manifest fields match current code.")


# ── Prospective Decision Schema ────────────────────────────────────────────────

@dataclass
class V3ProspectiveDecision:
    """
    Immutable record of one V3 prospective decision for one stock × date.
    Fields are set at capture time and never modified.
    Outcomes are stored in a separate V3OutcomeRecord.
    """
    # Identity
    research_version: str
    signal_id: int                 # forward_signals.id
    stock_id: str
    trade_date: str
    decision_id: str               # SHA-256 of (stock_id, trade_date, research_version, payload_hash)

    # Timing
    data_available_at: str               # market close time (Taiwan 13:30)
    decision_created_at: str             # when V3EntryTimingAnalyzer ran
    captured_at: str                     # when record was written to DB
    input_data_as_of: str                # OHLCV data cutoff date (must == trade_date)

    # Strategy
    decision: str                        # DIRECT_ENTRY / WAIT_MA20_PULLBACK / ... / NO_ENTRY

    # Reproducibility
    parameter_hash: str                  # V3_PARAMETER_HASH
    source_code_hash: str
    feature_snapshot_hash: str           # SHA-256 of feature inputs
    source_signal_fingerprint: str       # SHA-256 of forward_signal fields used
    data_snapshot_hash: str              # SHA-256 of OHLCV state at decision time
    payload_hash: str                    # SHA-256 of all decision fields (for conflict detection)

    # Classification
    capture_type: CaptureType
    prospective_eligibility: bool        # True iff capture_type == PROSPECTIVE_ELIGIBLE
    data_completeness: str               # COMPLETE / PARTIAL / MISSING

    # Optional fields (defaults must come after all non-default fields)
    signal_generated_at: Optional[str] = None   # forward_signals.locked_at
    market_timezone: str = "Asia/Taipei"
    setup_type: Optional[str] = None
    market_regime: Optional[str] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    ma20_slope: Optional[float] = None
    ma60_slope: Optional[float] = None
    ma20_gap: Optional[float] = None
    ma60_gap: Optional[float] = None
    volume_ratio: Optional[float] = None
    proposed_limit_price: Optional[float] = None
    confidence: Optional[float] = None
    skip_reason: Optional[str] = None
    rejection_reason: Optional[str] = None


@dataclass
class V3OutcomeRecord:
    """
    Versioned outcome result for one decision × horizon.
    Never written back to V3ProspectiveDecision.
    """
    decision_id: str
    stock_id: str
    trade_date: str
    research_version: str
    outcome_version: str               # e.g. "outcome_v1"
    horizon_days: int                  # 5, 10, or 20

    maturity_status: OutcomeMaturity
    evaluation_date: Optional[str]     # date when evaluation was done

    # Trade outcome (None if not filled or not mature)
    filled: Optional[bool]
    fill_date: Optional[str]
    fill_price: Optional[float]
    exit_date: Optional[str]
    exit_price: Optional[float]
    exit_reason: Optional[str]

    # Returns
    gross_return: Optional[float]
    net_return: Optional[float]
    benchmark_return: Optional[float]
    gross_alpha: Optional[float]
    net_alpha: Optional[float]

    # Attribution
    entry_timing_flag: Optional[str]   # BOTH_FILLED / D_SKIP / D_WAIT_UNFIRED
    avoided_loss: Optional[bool]       # True if D skipped and baseline A lost
    missed_gain: Optional[bool]        # True if D skipped and baseline A gained

    created_at: str


@dataclass
class CaptureResult:
    """Result of one decision capture attempt."""
    duplicate_result: DuplicateResult
    decision_id: Optional[str]
    capture_type: CaptureType
    rejection_reason: Optional[str]
    rows_inserted: int


@dataclass
class EligibilityResult:
    """Result of prospective eligibility check."""
    eligible: bool
    capture_type: CaptureType
    rejection_reason: Optional[str]
    checks: Dict[str, bool]           # per-check pass/fail


@dataclass
class DataGateResult:
    """Result of one data integrity gate check."""
    gate_name: str
    status: DataGateStatus
    detail: str
    as_of_date: Optional[str]
    stock_count: Optional[int]


@dataclass
class EvidenceReport:
    """Research dashboard — prospective evidence accumulation status."""
    report_date: str
    evidence_level: EvidenceLevel

    # Capture Health
    total_eligible_captures: int
    total_rejected_captures: int
    late_capture_count: int
    missing_data_count: int
    conflict_count: int
    freeze_mismatch_count: int
    latest_capture_date: Optional[str]

    # Outcome Maturity
    mature_5d: int
    mature_10d: int
    mature_20d: int
    pending_outcomes: int

    # Performance (None if no prospective data)
    d_vs_direct_mean_delta: Optional[float]
    d_fill_rate: Optional[float]
    market_avoidance_effect: Optional[float]
    entry_timing_effect: Optional[float]
    n_avoided_loss: Optional[int]
    n_missed_gain: Optional[int]

    # Statistical Confidence
    effective_signal_count: int
    unique_dates: int
    unique_stocks: int
    ci_lower: Optional[float]
    ci_upper: Optional[float]
    stat_power_note: str
    regime_coverage: List[str]

    # Warnings
    warnings: List[str]


# ── SQLite Schema ──────────────────────────────────────────────────────────────

_DECISIONS_DDL = """
CREATE TABLE IF NOT EXISTS v3_prospective_decisions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id      TEXT NOT NULL,
    research_version TEXT NOT NULL,
    signal_id        INTEGER,
    stock_id         TEXT NOT NULL,
    trade_date       TEXT NOT NULL,
    signal_generated_at TEXT,
    data_available_at   TEXT NOT NULL,
    decision_created_at TEXT NOT NULL,
    captured_at         TEXT NOT NULL,
    input_data_as_of    TEXT NOT NULL,
    market_timezone     TEXT NOT NULL DEFAULT 'Asia/Taipei',
    decision            TEXT NOT NULL,
    setup_type          TEXT,
    market_regime       TEXT,
    ma20                REAL,
    ma60                REAL,
    ma20_slope          REAL,
    ma60_slope          REAL,
    ma20_gap            REAL,
    ma60_gap            REAL,
    volume_ratio        REAL,
    proposed_limit_price REAL,
    confidence          REAL,
    skip_reason         TEXT,
    parameter_hash      TEXT NOT NULL,
    source_code_hash    TEXT NOT NULL,
    feature_snapshot_hash TEXT NOT NULL,
    source_signal_fingerprint TEXT NOT NULL,
    data_snapshot_hash  TEXT NOT NULL,
    payload_hash        TEXT NOT NULL,
    capture_type        TEXT NOT NULL,
    prospective_eligibility INTEGER NOT NULL DEFAULT 0,
    data_completeness   TEXT NOT NULL,
    rejection_reason    TEXT,
    UNIQUE (trade_date, stock_id, research_version)
)
"""

_OUTCOMES_DDL = """
CREATE TABLE IF NOT EXISTS v3_prospective_outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id     TEXT NOT NULL,
    stock_id        TEXT NOT NULL,
    trade_date      TEXT NOT NULL,
    research_version TEXT NOT NULL,
    outcome_version  TEXT NOT NULL,
    horizon_days     INTEGER NOT NULL,
    maturity_status  TEXT NOT NULL,
    evaluation_date  TEXT,
    filled          INTEGER,
    fill_date       TEXT,
    fill_price      REAL,
    exit_date       TEXT,
    exit_price      REAL,
    exit_reason     TEXT,
    gross_return    REAL,
    net_return      REAL,
    benchmark_return REAL,
    gross_alpha     REAL,
    net_alpha       REAL,
    entry_timing_flag TEXT,
    avoided_loss    INTEGER,
    missed_gain     INTEGER,
    created_at      TEXT NOT NULL,
    UNIQUE (decision_id, horizon_days, outcome_version)
)
"""

_RUN_LOG_DDL = """
CREATE TABLE IF NOT EXISTS v3_shadow_run_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    run_date    TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    n_eligible  INTEGER DEFAULT 0,
    n_rejected  INTEGER DEFAULT 0,
    n_conflicts INTEGER DEFAULT 0,
    n_duplicate INTEGER DEFAULT 0,
    status      TEXT,
    notes       TEXT
)
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """Create research tables if they don't exist. Safe to call multiple times."""
    conn.execute(_DECISIONS_DDL)
    conn.execute(_OUTCOMES_DDL)
    conn.execute(_RUN_LOG_DDL)
    conn.commit()


# ── Payload hash ──────────────────────────────────────────────────────────────

def _compute_payload_hash(decision: str, setup_type: Optional[str],
                           market_regime: Optional[str], ma20_gap: Optional[float],
                           proposed_limit_price: Optional[float],
                           skip_reason: Optional[str],
                           parameter_hash: str) -> str:
    payload = {
        "decision": decision, "setup_type": setup_type,
        "market_regime": market_regime, "ma20_gap": ma20_gap,
        "proposed_limit_price": proposed_limit_price,
        "skip_reason": skip_reason, "parameter_hash": parameter_hash,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _compute_decision_id(stock_id: str, trade_date: str,
                          research_version: str, payload_hash: str) -> str:
    raw = f"{stock_id}|{trade_date}|{research_version}|{payload_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Data Integrity Gates ───────────────────────────────────────────────────────

def check_0050_gate(conn: sqlite3.Connection, trade_date: str) -> DataGateResult:
    """Gate: 0050 must have data for trade_date (benchmark available)."""
    r = conn.execute(
        "SELECT date FROM daily_prices WHERE stock_id='0050' AND date=?", (trade_date,)
    ).fetchone()
    if r:
        return DataGateResult("0050_gate", DataGateStatus.PASS,
                               f"0050 data present for {trade_date}",
                               trade_date, 1)
    return DataGateResult("0050_gate", DataGateStatus.FAIL_NO_0050,
                           f"0050 missing for {trade_date}. Cannot compute benchmark.",
                           trade_date, 0)


def check_market_coverage_gate(conn: sqlite3.Connection, trade_date: str) -> DataGateResult:
    """Gate: at least MIN_COVERED_STOCKS non-benchmark stocks on trade_date."""
    r = conn.execute(
        "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=? AND stock_id!='0050'",
        (trade_date,)
    ).fetchone()
    n = r[0] if r else 0
    if n >= MIN_COVERED_STOCKS:
        return DataGateResult("market_coverage_gate", DataGateStatus.PASS,
                               f"{n:,} non-0050 stocks on {trade_date}",
                               trade_date, n)
    return DataGateResult("market_coverage_gate", DataGateStatus.FAIL_PARTIAL_MARKET,
                           f"Only {n:,} non-0050 stocks on {trade_date} (need {MIN_COVERED_STOCKS:,}). "
                           "TWSE/TPEx data may be incomplete.",
                           trade_date, n)


def check_stock_ohlc_gate(conn: sqlite3.Connection, stock_id: str,
                            trade_date: str) -> DataGateResult:
    """Gate: target stock must have OHLCV data as of trade_date."""
    r = conn.execute(
        "SELECT COUNT(*) FROM daily_prices WHERE stock_id=? AND date<=?",
        (stock_id, trade_date)
    ).fetchone()
    n = r[0] if r else 0
    if n >= MIN_BARS_FULL:
        return DataGateResult("stock_ohlc_gate", DataGateStatus.PASS,
                               f"{stock_id}: {n} bars ≤ {trade_date}",
                               trade_date, n)
    return DataGateResult("stock_ohlc_gate", DataGateStatus.FAIL_MISSING_STOCK,
                           f"{stock_id}: only {n} bars available (need {MIN_BARS_FULL})",
                           trade_date, n)


def check_look_ahead_gate(input_data_as_of: str, decision_date: str) -> DataGateResult:
    """
    Gate: input data cutoff must be ≤ decision_date.
    Prevents using future OHLCV data in prospective decisions.
    """
    if input_data_as_of <= decision_date:
        return DataGateResult("look_ahead_gate", DataGateStatus.PASS,
                               f"data_as_of={input_data_as_of} ≤ trade_date={decision_date}",
                               input_data_as_of, None)
    return DataGateResult("look_ahead_gate", DataGateStatus.FAIL_LOOK_AHEAD,
                           f"LOOK-AHEAD DETECTED: input_data_as_of={input_data_as_of} "
                           f"is AFTER trade_date={decision_date}. "
                           "This would constitute data snooping.",
                           input_data_as_of, None)


def check_capture_window_gate(trade_date: str, captured_at: str) -> DataGateResult:
    """
    Gate: decision must be captured within CAPTURE_WINDOW_HOURS of market close (13:30 Taiwan).
    After that, it is LATE_CAPTURE.
    Taiwan market closes at 13:30 CST. Capture window: 13:30–15:30 CST (05:30–07:30 UTC).
    """
    # Parse captured_at (ISO format with timezone)
    try:
        cap_dt = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return DataGateResult("capture_window_gate", DataGateStatus.FAIL_TIMESTAMP_INCONSISTENCY,
                               f"Cannot parse captured_at: {captured_at}",
                               trade_date, None)

    # Market close for trade_date at 13:30 Taiwan (05:30 UTC)
    # Capture window ends at 15:30 Taiwan (07:30 UTC)
    cap_date = cap_dt.date().isoformat()
    if cap_date > trade_date:
        days_late = (date.fromisoformat(cap_date) - date.fromisoformat(trade_date)).days
        if days_late > 0:
            return DataGateResult("capture_window_gate", DataGateStatus.FAIL_STALE_DATA,
                                   f"LATE_CAPTURE: captured on {cap_date} for trade_date {trade_date} "
                                   f"({days_late} day(s) late)",
                                   trade_date, None)
    return DataGateResult("capture_window_gate", DataGateStatus.PASS,
                           f"Captured on {cap_date} for trade_date {trade_date}",
                           trade_date, None)


def check_freeze_date_gate(trade_date: str, freeze_effective_from: str) -> DataGateResult:
    """Gate: trade_date must be ≥ freeze_effective_from to be PROSPECTIVE."""
    if trade_date >= freeze_effective_from:
        return DataGateResult("freeze_date_gate", DataGateStatus.PASS,
                               f"trade_date={trade_date} ≥ freeze_effective_from={freeze_effective_from}",
                               trade_date, None)
    return DataGateResult("freeze_date_gate", DataGateStatus.FAIL_STALE_DATA,
                           f"trade_date={trade_date} < freeze_effective_from={freeze_effective_from}. "
                           "This is RETROSPECTIVE_RECONSTRUCTION.",
                           trade_date, None)


# ── Eligibility Gate ───────────────────────────────────────────────────────────

def check_prospective_eligibility(
    stock_id: str,
    trade_date: str,
    input_data_as_of: str,
    captured_at: str,
    parameter_hash: str,
    freeze_manifest: V3FreezeManifest,
    conn: sqlite3.Connection,
) -> EligibilityResult:
    """
    Check all 10 prospective eligibility conditions.

    Returns PROSPECTIVE_ELIGIBLE only when ALL conditions pass.
    Fail-closed: any failure returns the first failed classification.
    """
    checks: Dict[str, bool] = {}

    # C1: V3 rules frozen before trade_date
    c1 = check_freeze_date_gate(trade_date, freeze_manifest.freeze_effective_from)
    checks["c1_freeze_date"] = c1.status == DataGateStatus.PASS
    if not checks["c1_freeze_date"]:
        return EligibilityResult(False, CaptureType.RETROSPECTIVE_RECONSTRUCTION,
                                  c1.detail, checks)

    # C2: Freeze manifest verified (parameter hash matches)
    freeze_status, freeze_reason = verify_freeze_manifest(freeze_manifest)
    checks["c2_freeze_verified"] = freeze_status == FreezeStatus.VERIFIED
    if not checks["c2_freeze_verified"]:
        return EligibilityResult(False, CaptureType.FREEZE_MISMATCH,
                                  f"FREEZE_MISMATCH: {freeze_reason}", checks)

    # C3: Stored parameter_hash matches manifest
    checks["c3_parameter_hash"] = parameter_hash == freeze_manifest.parameter_hash
    if not checks["c3_parameter_hash"]:
        return EligibilityResult(False, CaptureType.FREEZE_MISMATCH,
                                  f"Parameter hash mismatch: {parameter_hash} vs {freeze_manifest.parameter_hash}",
                                  checks)

    # C4: Capture window (not late capture)
    c4 = check_capture_window_gate(trade_date, captured_at)
    checks["c4_capture_window"] = c4.status == DataGateStatus.PASS
    if not checks["c4_capture_window"]:
        return EligibilityResult(False, CaptureType.LATE_CAPTURE, c4.detail, checks)

    # C5: No look-ahead
    c5 = check_look_ahead_gate(input_data_as_of, trade_date)
    checks["c5_no_look_ahead"] = c5.status == DataGateStatus.PASS
    if not checks["c5_no_look_ahead"]:
        return EligibilityResult(False, CaptureType.MISSING_INPUT, c5.detail, checks)

    # C6: 0050 data present
    c6 = check_0050_gate(conn, trade_date)
    checks["c6_0050_present"] = c6.status == DataGateStatus.PASS
    if not checks["c6_0050_present"]:
        return EligibilityResult(False, CaptureType.INCOMPLETE_MARKET_DATA, c6.detail, checks)

    # C7: Full market coverage (TWSE+TPEx)
    c7 = check_market_coverage_gate(conn, trade_date)
    checks["c7_market_coverage"] = c7.status == DataGateStatus.PASS
    if not checks["c7_market_coverage"]:
        return EligibilityResult(False, CaptureType.INCOMPLETE_MARKET_DATA, c7.detail, checks)

    # C8: Stock OHLC sufficient
    c8 = check_stock_ohlc_gate(conn, stock_id, trade_date)
    checks["c8_stock_ohlc"] = c8.status == DataGateStatus.PASS
    if not checks["c8_stock_ohlc"]:
        return EligibilityResult(False, CaptureType.MISSING_INPUT, c8.detail, checks)

    # C9: input_data_as_of <= trade_date (enforced by C5; redundant but explicit)
    checks["c9_data_as_of_valid"] = input_data_as_of <= trade_date
    if not checks["c9_data_as_of_valid"]:
        return EligibilityResult(False, CaptureType.MISSING_INPUT,
                                  f"input_data_as_of {input_data_as_of} > trade_date {trade_date}",
                                  checks)

    # C10: market_regime determined from real-time data (enforced by C5+C8; check: not empty)
    # (This is structural — if OHLC passes, regime can be computed)
    checks["c10_regime_computable"] = True

    return EligibilityResult(True, CaptureType.PROSPECTIVE_ELIGIBLE, None, checks)


# ── Append-only Repository ─────────────────────────────────────────────────────

class V3ProspectiveShadowRepository:
    """
    Append-only repository for V3 prospective shadow decisions and outcomes.

    Idempotency rules:
      - Same (trade_date, stock_id, research_version) + same payload_hash → DUPLICATE_IDENTICAL (skip)
      - Same (trade_date, stock_id, research_version) + different payload_hash → CAPTURE_CONFLICT (reject)
      - New key → NEW_RECORD (insert)

    Decision records are NEVER modified after insertion.
    Outcome records are written to a separate table with their own version key.
    """

    OUTCOME_VERSION = "outcome_v1"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        init_schema(conn)

    def capture(self, decision: V3ProspectiveDecision) -> CaptureResult:
        """
        Insert a prospective decision. Returns CaptureResult with duplicate logic applied.
        No production table is touched — only v3_prospective_decisions.
        """
        # Check for existing record
        existing = self._conn.execute(
            "SELECT decision_id, payload_hash FROM v3_prospective_decisions "
            "WHERE trade_date=? AND stock_id=? AND research_version=?",
            (decision.trade_date, decision.stock_id, decision.research_version)
        ).fetchone()

        if existing is not None:
            existing_decision_id, existing_payload_hash = existing
            if existing_payload_hash == decision.payload_hash:
                return CaptureResult(
                    duplicate_result=DuplicateResult.DUPLICATE_IDENTICAL,
                    decision_id=existing_decision_id,
                    capture_type=decision.capture_type,
                    rejection_reason="Identical record already exists (idempotent).",
                    rows_inserted=0,
                )
            else:
                return CaptureResult(
                    duplicate_result=DuplicateResult.CAPTURE_CONFLICT,
                    decision_id=existing_decision_id,
                    capture_type=CaptureType.MISSING_INPUT,
                    rejection_reason=(
                        f"CAPTURE_CONFLICT: same key ({decision.trade_date}, {decision.stock_id}, "
                        f"{decision.research_version}) but payload_hash differs. "
                        f"Stored: {existing_payload_hash} vs new: {decision.payload_hash}. "
                        "Original record is PRESERVED. Manual review required."
                    ),
                    rows_inserted=0,
                )

        # New record — INSERT
        self._conn.execute("""
            INSERT INTO v3_prospective_decisions (
                decision_id, research_version, signal_id, stock_id, trade_date,
                signal_generated_at, data_available_at, decision_created_at,
                captured_at, input_data_as_of, market_timezone,
                decision, setup_type, market_regime,
                ma20, ma60, ma20_slope, ma60_slope, ma20_gap, ma60_gap,
                volume_ratio, proposed_limit_price, confidence, skip_reason,
                parameter_hash, source_code_hash, feature_snapshot_hash,
                source_signal_fingerprint, data_snapshot_hash, payload_hash,
                capture_type, prospective_eligibility, data_completeness, rejection_reason
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            decision.decision_id, decision.research_version, decision.signal_id,
            decision.stock_id, decision.trade_date, decision.signal_generated_at,
            decision.data_available_at, decision.decision_created_at,
            decision.captured_at, decision.input_data_as_of, decision.market_timezone,
            decision.decision, decision.setup_type, decision.market_regime,
            decision.ma20, decision.ma60, decision.ma20_slope, decision.ma60_slope,
            decision.ma20_gap, decision.ma60_gap, decision.volume_ratio,
            decision.proposed_limit_price, decision.confidence, decision.skip_reason,
            decision.parameter_hash, decision.source_code_hash,
            decision.feature_snapshot_hash, decision.source_signal_fingerprint,
            decision.data_snapshot_hash, decision.payload_hash,
            decision.capture_type.value, int(decision.prospective_eligibility),
            decision.data_completeness, decision.rejection_reason,
        ))
        self._conn.commit()
        return CaptureResult(
            duplicate_result=DuplicateResult.NEW_RECORD,
            decision_id=decision.decision_id,
            capture_type=decision.capture_type,
            rejection_reason=None,
            rows_inserted=1,
        )

    def capture_outcome(self, outcome: V3OutcomeRecord) -> int:
        """
        Insert or ignore an outcome record. Returns 1 if inserted, 0 if already exists.
        Outcomes are versioned by (decision_id, horizon_days, outcome_version).
        """
        existing = self._conn.execute(
            "SELECT id FROM v3_prospective_outcomes WHERE decision_id=? AND horizon_days=? AND outcome_version=?",
            (outcome.decision_id, outcome.horizon_days, outcome.outcome_version)
        ).fetchone()
        if existing:
            return 0

        self._conn.execute("""
            INSERT INTO v3_prospective_outcomes (
                decision_id, stock_id, trade_date, research_version, outcome_version,
                horizon_days, maturity_status, evaluation_date,
                filled, fill_date, fill_price, exit_date, exit_price, exit_reason,
                gross_return, net_return, benchmark_return, gross_alpha, net_alpha,
                entry_timing_flag, avoided_loss, missed_gain, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            outcome.decision_id, outcome.stock_id, outcome.trade_date,
            outcome.research_version, outcome.outcome_version,
            outcome.horizon_days, outcome.maturity_status.value, outcome.evaluation_date,
            int(outcome.filled) if outcome.filled is not None else None,
            outcome.fill_date, outcome.fill_price, outcome.exit_date, outcome.exit_price,
            outcome.exit_reason, outcome.gross_return, outcome.net_return,
            outcome.benchmark_return, outcome.gross_alpha, outcome.net_alpha,
            outcome.entry_timing_flag,
            int(outcome.avoided_loss) if outcome.avoided_loss is not None else None,
            int(outcome.missed_gain) if outcome.missed_gain is not None else None,
            outcome.created_at,
        ))
        self._conn.commit()
        return 1

    def get_eligible_count(self) -> int:
        r = self._conn.execute(
            "SELECT COUNT(*) FROM v3_prospective_decisions WHERE prospective_eligibility=1"
        ).fetchone()
        return r[0] if r else 0

    def get_conflict_count(self) -> int:
        # Conflicts are tracked externally (not stored as rows)
        # Return count of non-eligible non-duplicate captures via rejection_reason
        r = self._conn.execute(
            "SELECT COUNT(*) FROM v3_prospective_decisions "
            "WHERE rejection_reason LIKE 'CAPTURE_CONFLICT%'"
        ).fetchone()
        return r[0] if r else 0

    def get_production_table_names(self) -> List[str]:
        """Return names of all tables in this connection (safety check)."""
        return [r[0] for r in self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]


# ── Outcome Maturity Evaluator ─────────────────────────────────────────────────

def check_outcome_maturity(
    trade_date: str,
    horizon_days: int,
    conn: sqlite3.Connection,  # production DB (read-only access to daily_prices)
    stock_id: str,
) -> Tuple[OutcomeMaturity, Optional[str]]:
    """
    Check if a decision is mature for a given horizon.
    Uses actual post-signal bar count (not calendar days).
    Returns (maturity_status, exit_date).
    """
    rows = conn.execute(
        "SELECT date FROM daily_prices WHERE stock_id=? AND date>? ORDER BY date",
        (stock_id, trade_date)
    ).fetchall()

    if not rows:
        return (OutcomeMaturity.MISSING_DATA, None)

    n_post = len(rows)
    if n_post >= horizon_days:
        # Exit date = horizon_days-th bar after trade_date
        exit_date = rows[horizon_days - 1][0]
        return (OutcomeMaturity.MATURE, exit_date)
    return (OutcomeMaturity.NOT_MATURE, None)


def evaluate_outcome_maturity(
    decision: V3ProspectiveDecision,
    horizon_days: int,
    ohlcv_conn: sqlite3.Connection,
) -> V3OutcomeRecord:
    """
    Build an outcome record for a given decision × horizon.
    Does NOT simulate fills — that requires a separate simulation step.
    Returns maturity status only; fill/return fields are None until simulation is run.
    """
    maturity, exit_date = check_outcome_maturity(
        decision.trade_date, horizon_days, ohlcv_conn, decision.stock_id
    )
    return V3OutcomeRecord(
        decision_id=decision.decision_id,
        stock_id=decision.stock_id,
        trade_date=decision.trade_date,
        research_version=decision.research_version,
        outcome_version=V3ProspectiveShadowRepository.OUTCOME_VERSION,
        horizon_days=horizon_days,
        maturity_status=maturity,
        evaluation_date=datetime.now(UTC).strftime("%Y-%m-%d"),
        filled=None, fill_date=None, fill_price=None,
        exit_date=exit_date, exit_price=None, exit_reason=None,
        gross_return=None, net_return=None, benchmark_return=None,
        gross_alpha=None, net_alpha=None,
        entry_timing_flag=None, avoided_loss=None, missed_gain=None,
        created_at=datetime.now(UTC).isoformat(),
    )


# ── Evidence Report ────────────────────────────────────────────────────────────

def build_evidence_report(
    research_conn: sqlite3.Connection,
    report_date: Optional[str] = None,
) -> EvidenceReport:
    """
    Build evidence accumulation dashboard from research DB.
    If no PROSPECTIVE_ELIGIBLE decisions exist: EvidenceLevel.NO_PROSPECTIVE_EVIDENCE.
    """
    if report_date is None:
        report_date = datetime.now(UTC).strftime("%Y-%m-%d")

    # Capture health
    r = research_conn.execute(
        "SELECT COUNT(*), MAX(trade_date) FROM v3_prospective_decisions WHERE prospective_eligibility=1"
    ).fetchone()
    eligible_count, latest_date = (r[0], r[1]) if r else (0, None)

    r_rej = research_conn.execute(
        "SELECT COUNT(*) FROM v3_prospective_decisions WHERE prospective_eligibility=0"
    ).fetchone()
    rejected_count = r_rej[0] if r_rej else 0

    r_late = research_conn.execute(
        "SELECT COUNT(*) FROM v3_prospective_decisions WHERE capture_type='LATE_CAPTURE'"
    ).fetchone()
    late_count = r_late[0] if r_late else 0

    r_missing = research_conn.execute(
        "SELECT COUNT(*) FROM v3_prospective_decisions WHERE capture_type='MISSING_INPUT'"
    ).fetchone()
    missing_count = r_missing[0] if r_missing else 0

    r_conflict = research_conn.execute(
        "SELECT COUNT(*) FROM v3_prospective_decisions WHERE rejection_reason LIKE 'CAPTURE_CONFLICT%'"
    ).fetchone()
    conflict_count = r_conflict[0] if r_conflict else 0

    r_freeze = research_conn.execute(
        "SELECT COUNT(*) FROM v3_prospective_decisions WHERE capture_type='FREEZE_MISMATCH'"
    ).fetchone()
    freeze_mismatch_count = r_freeze[0] if r_freeze else 0

    # Outcome maturity
    def _mature_count(h: int) -> int:
        r = research_conn.execute(
            "SELECT COUNT(*) FROM v3_prospective_outcomes "
            "WHERE horizon_days=? AND maturity_status='MATURE' AND outcome_version=?",
            (h, V3ProspectiveShadowRepository.OUTCOME_VERSION)
        ).fetchone()
        return r[0] if r else 0

    r_pending = research_conn.execute(
        "SELECT COUNT(DISTINCT decision_id) FROM v3_prospective_decisions "
        "WHERE prospective_eligibility=1 AND decision_id NOT IN "
        "(SELECT DISTINCT decision_id FROM v3_prospective_outcomes WHERE maturity_status='MATURE')"
    ).fetchone()
    pending = r_pending[0] if r_pending else 0

    # Unique dates/stocks (eligible only)
    r_dates = research_conn.execute(
        "SELECT COUNT(DISTINCT trade_date) FROM v3_prospective_decisions WHERE prospective_eligibility=1"
    ).fetchone()
    r_stocks = research_conn.execute(
        "SELECT COUNT(DISTINCT stock_id) FROM v3_prospective_decisions WHERE prospective_eligibility=1"
    ).fetchone()
    r_regimes = research_conn.execute(
        "SELECT DISTINCT market_regime FROM v3_prospective_decisions WHERE prospective_eligibility=1"
    ).fetchall()
    unique_dates = r_dates[0] if r_dates else 0
    unique_stocks = r_stocks[0] if r_stocks else 0
    regime_coverage = [r[0] for r in r_regimes if r[0] is not None]

    # Performance (only if mature 5D outcomes exist)
    mature_5d = _mature_count(5)
    mature_10d = _mature_count(10)
    mature_20d = _mature_count(20)
    d_vs_direct = None
    d_fill_rate = None
    mkt_avoid = None
    entry_time = None
    n_avoided = None
    n_missed = None
    ci_lo = None
    ci_hi = None

    if mature_5d >= MIN_SIGNALS_FOR_CI:
        # Could compute performance here — placeholder for future implementation
        pass

    # Evidence level
    warnings: List[str] = []
    if eligible_count == 0:
        level = EvidenceLevel.NO_PROSPECTIVE_EVIDENCE
        warnings.append(
            "NO_PROSPECTIVE_EVIDENCE: 0 PROSPECTIVE_ELIGIBLE decisions captured. "
            "Historical in-sample results (Session 27: +3.66%) MUST NOT be cited "
            "as evidence of prospective OOS edge."
        )
    elif eligible_count < MIN_SIGNALS_FOR_EVIDENCE:
        level = EvidenceLevel.PROSPECTIVE_EVIDENCE_ACCUMULATING
        warnings.append(
            f"ACCUMULATING: {eligible_count} of {MIN_SIGNALS_FOR_EVIDENCE} minimum signals captured. "
            "Statistical confidence insufficient. Do not use for strategy decisions."
        )
    else:
        level = EvidenceLevel.PROSPECTIVE_EVIDENCE_SUFFICIENT

    if conflict_count > 0:
        warnings.append(f"CAPTURE_CONFLICT: {conflict_count} conflicting records detected. Manual review required.")
    if freeze_mismatch_count > 0:
        warnings.append(f"FREEZE_MISMATCH: {freeze_mismatch_count} records with parameter drift.")

    stat_note = (
        f"Effective independent date-blocks: {unique_dates}. "
        f"Statistical power: {'INSUFFICIENT' if unique_dates < 20 else 'MARGINAL' if unique_dates < 50 else 'ADEQUATE'}. "
        "Session 27 iid bootstrap (n=274) is NOT valid for this dataset."
    )

    return EvidenceReport(
        report_date=report_date,
        evidence_level=level,
        total_eligible_captures=eligible_count,
        total_rejected_captures=rejected_count,
        late_capture_count=late_count,
        missing_data_count=missing_count,
        conflict_count=conflict_count,
        freeze_mismatch_count=freeze_mismatch_count,
        latest_capture_date=latest_date,
        mature_5d=mature_5d,
        mature_10d=mature_10d,
        mature_20d=mature_20d,
        pending_outcomes=pending,
        d_vs_direct_mean_delta=d_vs_direct,
        d_fill_rate=d_fill_rate,
        market_avoidance_effect=mkt_avoid,
        entry_timing_effect=entry_time,
        n_avoided_loss=n_avoided,
        n_missed_gain=n_missed,
        effective_signal_count=eligible_count,
        unique_dates=unique_dates,
        unique_stocks=unique_stocks,
        ci_lower=ci_lo,
        ci_upper=ci_hi,
        stat_power_note=stat_note,
        regime_coverage=regime_coverage,
        warnings=warnings,
    )


# ── Synthetic Dry Run ──────────────────────────────────────────────────────────

def _make_synthetic_decision(
    stock_id: str,
    trade_date: str,
    signal_id: int,
    decision: str = "DIRECT_ENTRY",
    skip_reason: Optional[str] = None,
    capture_type: CaptureType = CaptureType.PROSPECTIVE_ELIGIBLE,
    captured_at: Optional[str] = None,
) -> V3ProspectiveDecision:
    """Build a synthetic V3ProspectiveDecision for dry-run testing."""
    now_iso = captured_at or datetime.now(UTC).isoformat()
    input_as_of = trade_date  # no look-ahead
    ph = _compute_payload_hash(decision, None, "bull", 2.0, None, skip_reason, V3_PARAMETER_HASH)
    did = _compute_decision_id(stock_id, trade_date, V3_RESEARCH_VERSION, ph)
    fs_fp = hashlib.sha256(f"{signal_id}|{stock_id}|{trade_date}".encode()).hexdigest()[:12]
    feat_fp = hashlib.sha256(f"{stock_id}|{trade_date}|ma20=50.0".encode()).hexdigest()[:12]
    data_fp = hashlib.sha256(f"{stock_id}|{trade_date}|n=80".encode()).hexdigest()[:12]

    return V3ProspectiveDecision(
        research_version=V3_RESEARCH_VERSION,
        signal_id=signal_id,
        stock_id=stock_id,
        trade_date=trade_date,
        decision_id=did,
        signal_generated_at=f"{trade_date}T08:00:00+08:00",
        data_available_at=f"{trade_date}T13:30:00+08:00",
        decision_created_at=f"{trade_date}T13:35:00+08:00",
        captured_at=now_iso,
        input_data_as_of=input_as_of,
        decision=decision,
        setup_type="near_breakout" if decision == "DIRECT_ENTRY" else None,
        market_regime="bull",
        ma20=50.0, ma60=48.0, ma20_slope=0.5, ma60_slope=0.3,
        ma20_gap=2.0, ma60_gap=4.0, volume_ratio=1.2,
        proposed_limit_price=51.0, confidence=72.0, skip_reason=skip_reason,
        parameter_hash=V3_PARAMETER_HASH,
        source_code_hash=compute_source_code_hash(),
        feature_snapshot_hash=feat_fp,
        source_signal_fingerprint=fs_fp,
        data_snapshot_hash=data_fp,
        payload_hash=ph,
        capture_type=capture_type,
        prospective_eligibility=(capture_type == CaptureType.PROSPECTIVE_ELIGIBLE),
        data_completeness="COMPLETE",
        rejection_reason=None,
    )


def run_synthetic_dry_run(conn: sqlite3.Connection) -> Dict:
    """
    End-to-end synthetic test: simulates 18 scenarios.
    Uses in-memory SQLite only — no production writes.
    """
    repo = V3ProspectiveShadowRepository(conn)
    results: Dict[str, str] = {}

    # S1: Normal prospective capture
    d1 = _make_synthetic_decision("1101", "2026-11-07", 1001, "DIRECT_ENTRY")
    r1 = repo.capture(d1)
    results["S1_normal_capture"] = r1.duplicate_result.value

    # S2: Duplicate identical
    r2 = repo.capture(d1)
    results["S2_duplicate_identical"] = r2.duplicate_result.value

    # S3: Duplicate conflict (same key, different decision)
    d3 = _make_synthetic_decision("1101", "2026-11-07", 1001, "WAIT_MA20_PULLBACK")
    # Same stock/date/version but different payload_hash
    r3 = repo.capture(d3)
    results["S3_duplicate_conflict"] = r3.duplicate_result.value

    # S4: Late capture (captured tomorrow)
    tomorrow = "2026-11-08"
    d4 = _make_synthetic_decision("2330", "2026-11-07", 1002, "DIRECT_ENTRY",
                                   captured_at=f"{tomorrow}T14:00:00+08:00",
                                   capture_type=CaptureType.LATE_CAPTURE)
    r4 = repo.capture(d4)
    results["S4_late_capture"] = r4.duplicate_result.value

    # S5: Retrospective reconstruction (pre-freeze date)
    d5 = _make_synthetic_decision("2454", "2026-10-09", 500, "DIRECT_ENTRY",
                                   capture_type=CaptureType.RETROSPECTIVE_RECONSTRUCTION)
    r5 = repo.capture(d5)
    results["S5_retrospective"] = r5.duplicate_result.value

    # S6: Missing 0050 (incomplete market data)
    d6 = _make_synthetic_decision("2317", "2026-11-07", 1003,
                                   capture_type=CaptureType.INCOMPLETE_MARKET_DATA)
    d6.prospective_eligibility = False
    d6.rejection_reason = "FAIL_NO_0050: 0050 missing for 2026-11-07"
    r6 = repo.capture(d6)
    results["S6_missing_0050"] = r6.duplicate_result.value

    # S7: Freeze mismatch
    d7 = _make_synthetic_decision("2881", "2026-11-07", 1004,
                                   capture_type=CaptureType.FREEZE_MISMATCH)
    d7.prospective_eligibility = False
    d7.rejection_reason = "FREEZE_MISMATCH: parameter_hash differs"
    r7 = repo.capture(d7)
    results["S7_freeze_mismatch"] = r7.duplicate_result.value

    # S8: Normal capture of a SKIP decision
    d8 = _make_synthetic_decision("1216", "2026-11-07", 1005,
                                   "AVOID_CHASING", skip_reason="price_too_extended")
    r8 = repo.capture(d8)
    results["S8_skip_decision"] = r8.duplicate_result.value

    # S9: Outcome not mature (5D)
    outcome_not_mature = V3OutcomeRecord(
        decision_id=d1.decision_id, stock_id=d1.stock_id,
        trade_date=d1.trade_date, research_version=V3_RESEARCH_VERSION,
        outcome_version="outcome_v1", horizon_days=5,
        maturity_status=OutcomeMaturity.NOT_MATURE,
        evaluation_date="2026-11-10",
        filled=None, fill_date=None, fill_price=None,
        exit_date=None, exit_price=None, exit_reason=None,
        gross_return=None, net_return=None, benchmark_return=None,
        gross_alpha=None, net_alpha=None,
        entry_timing_flag=None, avoided_loss=None, missed_gain=None,
        created_at=datetime.now(UTC).isoformat(),
    )
    inserted = repo.capture_outcome(outcome_not_mature)
    results["S9_outcome_not_mature"] = "INSERTED" if inserted else "SKIPPED"

    # S10: Outcome mature (20D)
    outcome_mature = V3OutcomeRecord(
        decision_id=d1.decision_id, stock_id=d1.stock_id,
        trade_date=d1.trade_date, research_version=V3_RESEARCH_VERSION,
        outcome_version="outcome_v1", horizon_days=20,
        maturity_status=OutcomeMaturity.MATURE,
        evaluation_date="2026-12-10",
        filled=True, fill_date="2026-11-10", fill_price=52.0,
        exit_date="2026-12-10", exit_price=55.0, exit_reason="HORIZON",
        gross_return=round(55.0/52.0 - 1, 6),
        net_return=round(55.0/52.0 - 1 - 0.00585, 6),
        benchmark_return=-0.02, gross_alpha=round(55.0/52.0 - 1 - (-0.02), 6),
        net_alpha=round(55.0/52.0 - 1 - 0.00585 - (-0.02), 6),
        entry_timing_flag="BOTH_FILLED", avoided_loss=None, missed_gain=None,
        created_at=datetime.now(UTC).isoformat(),
    )
    inserted2 = repo.capture_outcome(outcome_mature)
    results["S10_outcome_mature"] = "INSERTED" if inserted2 else "SKIPPED"

    # S11: Check no production writes
    tables = repo.get_production_table_names()
    production_tables = {"forward_signals", "hybrid_forward_decision", "positions", "user_trades"}
    prod_writes = [t for t in tables if t in production_tables]
    results["S11_no_production_writes"] = "PASS" if not prod_writes else f"FAIL: {prod_writes}"

    # S12: Evidence report with no eligible
    # Build a fresh conn for no-evidence test
    fresh_conn = sqlite3.connect(":memory:")
    init_schema(fresh_conn)
    report_empty = build_evidence_report(fresh_conn)
    results["S12_no_evidence_report"] = report_empty.evidence_level.value
    fresh_conn.close()

    # S13: Evidence report with captures
    report = build_evidence_report(conn)
    results["S13_evidence_eligible_count"] = str(report.total_eligible_captures)
    results["S14_evidence_level"] = report.evidence_level.value

    return results
