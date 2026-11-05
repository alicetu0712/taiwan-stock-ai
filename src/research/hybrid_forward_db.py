"""
hybrid_forward_db.py — Research SQLite schema + data access for Hybrid Forward Shadow

RESEARCH ONLY — writes to local SQLite only (data/platform.db research tables).
Does NOT touch production Neon PostgreSQL.

Design principles:
  1. hybrid_forward_decision:  IMMUTABLE after INSERT.  Never updated.
  2. hybrid_forward_outcome:   Separate table, one row per (decision_id, horizon,
                                calculation_version).  Append-only.
  3. hybrid_forward_run_log:   One row per daily run.  Status + counts.

Capture classification:
  PROSPECTIVE                 Signal date >= RULE_FREEZE_DATE AND captured
                              within MAX_PROSPECTIVE_CAPTURE_DAYS trading days.
  LATE_CAPTURE                Signal date >= RULE_FREEZE_DATE but captured late.
  RETROSPECTIVE_RECONSTRUCTION Signal date < RULE_FREEZE_DATE.
  INVALID_DATA                Data issues (insufficient history, stale data, etc.)
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

# ── Constants ─────────────────────────────────────────────────────────────────

RULE_FREEZE_DATE = date(2026, 11, 5)
RESEARCH_VERSION = "v2_research_v2"
CALCULATION_VERSION = "1.0"

# A capture is PROSPECTIVE if recorded within N trading days of signal_date
MAX_PROSPECTIVE_CAPTURE_DAYS = 1

# ── Capture classification ────────────────────────────────────────────────────

class CaptureClassification:
    PROSPECTIVE                 = "PROSPECTIVE"
    LATE_CAPTURE                = "LATE_CAPTURE"
    RETROSPECTIVE_RECONSTRUCTION = "RETROSPECTIVE_RECONSTRUCTION"
    INVALID_DATA                = "INVALID_DATA"


class OutcomeStatus:
    MATURED  = "MATURED"
    PENDING  = "PENDING"
    CONFLICT = "CONFLICT"
    INVALID  = "INVALID"


class RunStatus:
    SUCCESS                  = "SUCCESS"
    PARTIAL                  = "PARTIAL"
    SKIPPED_NON_TRADING_DAY  = "SKIPPED_NON_TRADING_DAY"
    BLOCKED_STALE_DATA       = "BLOCKED_STALE_DATA"
    BLOCKED_MISSING_SIGNALS  = "BLOCKED_MISSING_SIGNALS"
    BLOCKED_MISSING_OHLC     = "BLOCKED_MISSING_OHLC"
    FAILED                   = "FAILED"
    CONFLICT                 = "CONFLICT"


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class HybridForwardDecision:
    """Immutable record of one Hybrid forward shadow decision."""
    stock_id: str
    trade_date: date
    rule_version: str
    research_version: str
    v2_entry_label: str
    hybrid_action: str
    rule_reason: str
    rule_priority: int
    market_regime: str
    ma20_slope_pct: float
    ma20_trend: str
    ma20_gap_pct: Optional[float]
    feature_cutoff_date: date
    input_data_as_of: date              # most recent DailyPrice date available at capture
    input_data_hash: Optional[str]      # sha256 of input features
    decision_hash: str                  # sha256 of decision outputs
    capture_classification: str
    captured_at: datetime
    run_id: str


@dataclass
class HybridForwardOutcome:
    """Outcome for one decision × horizon (immutable after insert)."""
    decision_id: int
    stock_id: str
    trade_date: date
    rule_version: str
    horizon: str                        # '5d', '10d', '20d'
    maturity_date: date
    maturity_trading_days: int
    v1_net_return: Optional[float]
    v2_net_return: Optional[float]
    hybrid_net_return: Optional[float]
    hybrid_vs_v1_delta: Optional[float]
    hybrid_vs_v2_delta: Optional[float]
    data_source_version: str            # DailyPrice last date used
    calculation_version: str
    outcome_status: str
    calculated_at: datetime


@dataclass
class HybridForwardRunLog:
    """One record per daily shadow run."""
    run_id: str
    trade_date: date
    started_at: datetime
    finished_at: Optional[datetime]
    input_data_date: Optional[date]
    inserted_count: int
    skipped_count: int
    conflict_count: int
    error_count: int
    outcome_filled_count: int
    status: str
    error_summary: Optional[str]


# ── Schema SQL ────────────────────────────────────────────────────────────────

CREATE_DECISION_TABLE = """
CREATE TABLE IF NOT EXISTS hybrid_forward_decision (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id               TEXT    NOT NULL,
    trade_date             TEXT    NOT NULL,
    rule_version           TEXT    NOT NULL,
    research_version       TEXT    NOT NULL DEFAULT 'v2_research_v2',
    v2_entry_label         TEXT    NOT NULL,
    hybrid_action          TEXT    NOT NULL,
    rule_reason            TEXT    NOT NULL,
    rule_priority          INTEGER NOT NULL,
    market_regime          TEXT    NOT NULL,
    ma20_slope_pct         REAL    NOT NULL,
    ma20_trend             TEXT    NOT NULL,
    ma20_gap_pct           REAL,
    feature_cutoff_date    TEXT    NOT NULL,
    input_data_as_of       TEXT    NOT NULL,
    input_data_hash        TEXT,
    decision_hash          TEXT    NOT NULL,
    capture_classification TEXT    NOT NULL,
    captured_at            TEXT    NOT NULL,
    run_id                 TEXT    NOT NULL,
    UNIQUE(stock_id, trade_date, rule_version)
);
"""

CREATE_OUTCOME_TABLE = """
CREATE TABLE IF NOT EXISTS hybrid_forward_outcome (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id             INTEGER NOT NULL,
    stock_id                TEXT    NOT NULL,
    trade_date              TEXT    NOT NULL,
    rule_version            TEXT    NOT NULL,
    horizon                 TEXT    NOT NULL,
    maturity_date           TEXT    NOT NULL,
    maturity_trading_days   INTEGER NOT NULL,
    v1_net_return           REAL,
    v2_net_return           REAL,
    hybrid_net_return       REAL,
    hybrid_vs_v1_delta      REAL,
    hybrid_vs_v2_delta      REAL,
    data_source_version     TEXT    NOT NULL,
    calculation_version     TEXT    NOT NULL,
    outcome_status          TEXT    NOT NULL,
    calculated_at           TEXT    NOT NULL,
    UNIQUE(decision_id, horizon, calculation_version)
);
"""

CREATE_RUN_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS hybrid_forward_run_log (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id               TEXT    NOT NULL UNIQUE,
    trade_date           TEXT    NOT NULL,
    started_at           TEXT    NOT NULL,
    finished_at          TEXT,
    input_data_date      TEXT,
    inserted_count       INTEGER DEFAULT 0,
    skipped_count        INTEGER DEFAULT 0,
    conflict_count       INTEGER DEFAULT 0,
    error_count          INTEGER DEFAULT 0,
    outcome_filled_count INTEGER DEFAULT 0,
    status               TEXT    NOT NULL,
    error_summary        TEXT
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_hfd_trade_date ON hybrid_forward_decision(trade_date);",
    "CREATE INDEX IF NOT EXISTS idx_hfd_classification ON hybrid_forward_decision(capture_classification);",
    "CREATE INDEX IF NOT EXISTS idx_hfo_decision_id ON hybrid_forward_outcome(decision_id);",
    "CREATE INDEX IF NOT EXISTS idx_hfo_trade_date ON hybrid_forward_outcome(trade_date);",
    "CREATE INDEX IF NOT EXISTS idx_hfl_trade_date ON hybrid_forward_run_log(trade_date);",
]


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create all research tables if they don't exist. Safe to call repeatedly."""
    conn.execute(CREATE_DECISION_TABLE)
    conn.execute(CREATE_OUTCOME_TABLE)
    conn.execute(CREATE_RUN_LOG_TABLE)
    for idx_sql in CREATE_INDEXES:
        conn.execute(idx_sql)
    conn.commit()


# ── Hashing ───────────────────────────────────────────────────────────────────

def compute_input_data_hash(
    stock_id: str,
    trade_date: date,
    market_regime: str,
    ma20_slope_pct: float,
    ma20_trend: str,
    ma20_gap_pct: Optional[float],
    v2_entry_label: str,
    input_data_as_of: date,
) -> str:
    payload = json.dumps({
        "stock_id": stock_id,
        "trade_date": str(trade_date),
        "market_regime": market_regime,
        "ma20_slope_pct": round(ma20_slope_pct, 4),
        "ma20_trend": ma20_trend,
        "ma20_gap_pct": round(ma20_gap_pct, 4) if ma20_gap_pct is not None else None,
        "v2_entry_label": v2_entry_label,
        "input_data_as_of": str(input_data_as_of),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def compute_decision_hash(
    hybrid_action: str,
    rule_reason: str,
    rule_priority: int,
    rule_version: str,
) -> str:
    payload = json.dumps({
        "hybrid_action": hybrid_action,
        "rule_reason": rule_reason,
        "rule_priority": rule_priority,
        "rule_version": rule_version,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── Capture classification ────────────────────────────────────────────────────

def classify_capture(
    trade_date: date,
    captured_at: datetime,
    input_data_as_of: date,
    trading_days_since_trade: int,
) -> str:
    """
    Determine capture classification.

    PROSPECTIVE:   trade_date >= RULE_FREEZE_DATE AND captured within
                   MAX_PROSPECTIVE_CAPTURE_DAYS trading days.
    LATE_CAPTURE:  trade_date >= RULE_FREEZE_DATE but captured late.
    RETROSPECTIVE_RECONSTRUCTION: trade_date < RULE_FREEZE_DATE.
    INVALID_DATA:  Data not available for trade_date (input_data_as_of < trade_date).
    """
    if trade_date < RULE_FREEZE_DATE:
        return CaptureClassification.RETROSPECTIVE_RECONSTRUCTION

    if input_data_as_of < trade_date:
        # Data wasn't available for this trade_date at capture time
        return CaptureClassification.INVALID_DATA

    if trading_days_since_trade <= MAX_PROSPECTIVE_CAPTURE_DAYS:
        return CaptureClassification.PROSPECTIVE

    return CaptureClassification.LATE_CAPTURE


# ── Data access layer ─────────────────────────────────────────────────────────

def insert_decision(
    conn: sqlite3.Connection,
    decision: HybridForwardDecision,
) -> Optional[int]:
    """
    Insert an immutable decision record.

    Returns:
      int — newly inserted row id
      None — record already exists (idempotent skip)
      Raises ConflictError if same (stock_id, trade_date, rule_version) exists
             with a different decision_hash.
    """
    existing = conn.execute(
        "SELECT id, decision_hash FROM hybrid_forward_decision "
        "WHERE stock_id=? AND trade_date=? AND rule_version=?",
        (decision.stock_id, str(decision.trade_date), decision.rule_version),
    ).fetchone()

    if existing is not None:
        existing_id, existing_hash = existing
        if existing_hash == decision.decision_hash:
            return None  # identical repeat — idempotent skip
        raise ConflictError(
            f"Decision conflict for {decision.stock_id}/{decision.trade_date}: "
            f"existing_hash={existing_hash}, new_hash={decision.decision_hash}"
        )

    conn.execute(
        """
        INSERT INTO hybrid_forward_decision
          (stock_id, trade_date, rule_version, research_version,
           v2_entry_label, hybrid_action, rule_reason, rule_priority,
           market_regime, ma20_slope_pct, ma20_trend, ma20_gap_pct,
           feature_cutoff_date, input_data_as_of, input_data_hash,
           decision_hash, capture_classification, captured_at, run_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            decision.stock_id,
            str(decision.trade_date),
            decision.rule_version,
            decision.research_version,
            decision.v2_entry_label,
            decision.hybrid_action,
            decision.rule_reason,
            decision.rule_priority,
            decision.market_regime,
            decision.ma20_slope_pct,
            decision.ma20_trend,
            decision.ma20_gap_pct,
            str(decision.feature_cutoff_date),
            str(decision.input_data_as_of),
            decision.input_data_hash,
            decision.decision_hash,
            decision.capture_classification,
            decision.captured_at.isoformat(),
            decision.run_id,
        ),
    )
    row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return row_id


def insert_outcome(
    conn: sqlite3.Connection,
    outcome: HybridForwardOutcome,
) -> Optional[int]:
    """
    Insert an outcome record.

    Returns row id on insert, None on idempotent skip (identical existing),
    raises ConflictError if values differ for the same unique key.
    """
    existing = conn.execute(
        "SELECT id, hybrid_net_return FROM hybrid_forward_outcome "
        "WHERE decision_id=? AND horizon=? AND calculation_version=?",
        (outcome.decision_id, outcome.horizon, outcome.calculation_version),
    ).fetchone()

    if existing is not None:
        existing_id, existing_ret = existing
        if existing_ret == outcome.hybrid_net_return:
            return None
        raise ConflictError(
            f"Outcome conflict for decision_id={outcome.decision_id} "
            f"horizon={outcome.horizon}: existing={existing_ret}, new={outcome.hybrid_net_return}"
        )

    conn.execute(
        """
        INSERT INTO hybrid_forward_outcome
          (decision_id, stock_id, trade_date, rule_version, horizon,
           maturity_date, maturity_trading_days,
           v1_net_return, v2_net_return, hybrid_net_return,
           hybrid_vs_v1_delta, hybrid_vs_v2_delta,
           data_source_version, calculation_version,
           outcome_status, calculated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            outcome.decision_id,
            outcome.stock_id,
            str(outcome.trade_date),
            outcome.rule_version,
            outcome.horizon,
            str(outcome.maturity_date),
            outcome.maturity_trading_days,
            outcome.v1_net_return,
            outcome.v2_net_return,
            outcome.hybrid_net_return,
            outcome.hybrid_vs_v1_delta,
            outcome.hybrid_vs_v2_delta,
            outcome.data_source_version,
            outcome.calculation_version,
            outcome.outcome_status,
            outcome.calculated_at.isoformat(),
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def upsert_run_log(conn: sqlite3.Connection, log: HybridForwardRunLog) -> None:
    """Insert or update a run log entry."""
    conn.execute(
        """
        INSERT INTO hybrid_forward_run_log
          (run_id, trade_date, started_at, finished_at, input_data_date,
           inserted_count, skipped_count, conflict_count, error_count,
           outcome_filled_count, status, error_summary)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(run_id) DO UPDATE SET
          finished_at=excluded.finished_at,
          inserted_count=excluded.inserted_count,
          skipped_count=excluded.skipped_count,
          conflict_count=excluded.conflict_count,
          error_count=excluded.error_count,
          outcome_filled_count=excluded.outcome_filled_count,
          status=excluded.status,
          error_summary=excluded.error_summary
        """,
        (
            log.run_id,
            str(log.trade_date),
            log.started_at.isoformat(),
            log.finished_at.isoformat() if log.finished_at else None,
            str(log.input_data_date) if log.input_data_date else None,
            log.inserted_count,
            log.skipped_count,
            log.conflict_count,
            log.error_count,
            log.outcome_filled_count,
            log.status,
            log.error_summary,
        ),
    )
    conn.commit()


def get_pending_outcome_decisions(
    conn: sqlite3.Connection,
    cutoff_date: date,
    horizon: str,
    calculation_version: str,
) -> List[dict]:
    """
    Return decisions that:
      - Are PROSPECTIVE or LATE_CAPTURE (not retrospective)
      - Don't yet have an outcome for this horizon+calculation_version
      - Have trade_date <= cutoff_date (old enough to have matured)
    """
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT d.id, d.stock_id, d.trade_date, d.rule_version,
                   d.hybrid_action, d.v2_entry_label
            FROM hybrid_forward_decision d
            WHERE d.capture_classification IN ('PROSPECTIVE', 'LATE_CAPTURE')
              AND d.trade_date <= ?
              AND d.id NOT IN (
                  SELECT decision_id FROM hybrid_forward_outcome
                  WHERE horizon=? AND calculation_version=?
              )
            ORDER BY d.trade_date
            """,
            (str(cutoff_date), horizon, calculation_version),
        ).fetchall()
    ]


def get_operational_summary(conn: sqlite3.Connection) -> dict:
    """Return summary statistics for the monitoring dashboard."""
    result = {}

    # Latest run
    latest_run = conn.execute(
        "SELECT trade_date, status, started_at, inserted_count, conflict_count, input_data_date "
        "FROM hybrid_forward_run_log ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if latest_run:
        result["latest_run"] = dict(zip(
            ["trade_date", "status", "started_at", "inserted_count", "conflict_count",
             "input_data_date"],
            latest_run,
        ))
    else:
        result["latest_run"] = None

    # Decision counts by classification
    rows = conn.execute(
        "SELECT capture_classification, COUNT(*) FROM hybrid_forward_decision GROUP BY capture_classification"
    ).fetchall()
    result["decisions_by_classification"] = {r[0]: r[1] for r in rows}

    # Total decisions
    total = conn.execute("SELECT COUNT(*) FROM hybrid_forward_decision").fetchone()[0]
    result["total_decisions"] = total

    # Prospective only
    pros = conn.execute(
        "SELECT COUNT(*) FROM hybrid_forward_decision WHERE capture_classification='PROSPECTIVE'"
    ).fetchone()[0]
    result["prospective_decisions"] = pros

    # Outcome counts by horizon
    for horizon in ("5d", "10d", "20d"):
        matured = conn.execute(
            "SELECT COUNT(*) FROM hybrid_forward_outcome "
            "WHERE horizon=? AND outcome_status='MATURED'",
            (horizon,),
        ).fetchone()[0]
        result[f"matured_{horizon}"] = matured

    # Distinct trade dates (prospective only)
    dates = conn.execute(
        "SELECT COUNT(DISTINCT trade_date) FROM hybrid_forward_decision "
        "WHERE capture_classification='PROSPECTIVE'"
    ).fetchone()[0]
    result["prospective_trade_dates"] = dates

    # Distinct stocks (prospective only)
    stocks = conn.execute(
        "SELECT COUNT(DISTINCT stock_id) FROM hybrid_forward_decision "
        "WHERE capture_classification='PROSPECTIVE'"
    ).fetchone()[0]
    result["prospective_stocks"] = stocks

    # Consecutive failures
    rows2 = conn.execute(
        "SELECT status FROM hybrid_forward_run_log ORDER BY started_at DESC LIMIT 10"
    ).fetchall()
    consec_fail = 0
    for r in rows2:
        if r[0] in (RunStatus.FAILED, RunStatus.PARTIAL, RunStatus.CONFLICT):
            consec_fail += 1
        else:
            break
    result["consecutive_failures"] = consec_fail

    return result


def get_matured_performance(
    conn: sqlite3.Connection,
    horizon: str = "20d",
    classification_filter: str = "PROSPECTIVE",
) -> Optional[dict]:
    """
    Return matured performance stats for a given horizon.
    Only returns results for PROSPECTIVE (or specified) classifications.
    Returns None if no matured data yet.
    """
    rows = conn.execute(
        """
        SELECT o.hybrid_net_return, o.v1_net_return, o.v2_net_return,
               o.hybrid_vs_v1_delta, o.hybrid_vs_v2_delta
        FROM hybrid_forward_outcome o
        JOIN hybrid_forward_decision d ON d.id = o.decision_id
        WHERE o.horizon=? AND o.outcome_status='MATURED'
          AND d.capture_classification=?
        """,
        (horizon, classification_filter),
    ).fetchall()

    if not rows:
        return None

    n = len(rows)
    hyb_rets = [r[0] for r in rows if r[0] is not None]
    v1_rets = [r[1] for r in rows if r[1] is not None]
    v2_rets = [r[2] for r in rows if r[2] is not None]
    deltas_v1 = [r[3] for r in rows if r[3] is not None]
    deltas_v2 = [r[4] for r in rows if r[4] is not None]

    def _mean(lst):
        return round(sum(lst) / len(lst), 4) if lst else None

    return {
        "horizon": horizon,
        "n_matured": n,
        "hybrid_mean_ret": _mean(hyb_rets),
        "v1_mean_ret": _mean(v1_rets),
        "v2_mean_ret": _mean(v2_rets),
        "hybrid_vs_v1_mean_delta": _mean(deltas_v1),
        "hybrid_vs_v2_mean_delta": _mean(deltas_v2),
    }


# ── Error types ───────────────────────────────────────────────────────────────

class ConflictError(Exception):
    """Raised when a decision or outcome insert conflicts with an existing record."""


def new_run_id() -> str:
    return str(uuid.uuid4())[:8]
