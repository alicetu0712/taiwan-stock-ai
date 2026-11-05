"""
storage_adapter.py — Abstract storage interface for Hybrid Forward Shadow research data.

RESEARCH ONLY — no production Neon PostgreSQL writes.

Design:
  ResearchStorageProtocol — structural typing interface (Protocol)
  SQLiteResearchStorage   — concrete implementation using local data/platform.db
  PostgreSQLResearchStorage — stub; raises NotImplementedError with setup instructions

Usage:
  with SQLiteResearchStorage(db_path) as store:
      store.insert_decision(d)
      store.get_operational_summary()

The runner (run_hybrid_forward_shadow.py) uses hybrid_forward_db functions directly.
This adapter is for future callers (dashboard, tests, GH Actions) that need a
backend-agnostic interface.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional, runtime_checkable

try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol  # type: ignore[assignment]

from src.research.hybrid_forward_db import (
    ConflictError,
    HybridForwardDecision,
    HybridForwardOutcome,
    HybridForwardRunLog,
    ensure_schema,
    get_matured_performance,
    get_operational_summary,
    insert_decision,
    insert_outcome,
    upsert_run_log,
)

__all__ = [
    "ResearchStorageProtocol",
    "SQLiteResearchStorage",
    "PostgreSQLResearchStorage",
    "StorageHealthStatus",
    "ConflictError",
]


# ── Health status constants ───────────────────────────────────────────────────

class StorageHealthStatus:
    HEALTHY  = "HEALTHY"
    DEGRADED = "DEGRADED"
    BLOCKED  = "BLOCKED"
    UNKNOWN  = "UNKNOWN"


# ── Protocol (structural typing) ──────────────────────────────────────────────

@runtime_checkable
class ResearchStorageProtocol(Protocol):
    """
    Structural protocol for research storage backends.
    Both SQLiteResearchStorage and PostgreSQLResearchStorage satisfy this interface.
    """

    def ensure_schema(self) -> None: ...
    def insert_decision(self, decision: HybridForwardDecision) -> Optional[int]: ...
    def insert_outcome(self, outcome: HybridForwardOutcome) -> Optional[int]: ...
    def upsert_run_log(self, log: HybridForwardRunLog) -> None: ...
    def get_operational_summary(self) -> dict: ...
    def get_matured_performance(
        self, horizon: str = "20d", classification_filter: str = "PROSPECTIVE"
    ) -> Optional[dict]: ...
    def health_check(self) -> dict: ...
    def get_storage_info(self) -> dict: ...
    def close(self) -> None: ...


# ── SQLite implementation ─────────────────────────────────────────────────────

class SQLiteResearchStorage:
    """
    SQLite-backed research storage using data/platform.db.

    Thread safety: SQLite in WAL mode is safe for one writer + multiple readers.
    Concurrent writes from separate processes must be serialised externally
    (e.g. via GitHub Actions concurrency group: hybrid-forward-shadow).

    Usage:
        with SQLiteResearchStorage("data/platform.db") as store:
            store.insert_decision(d)
    """

    RESEARCH_TABLES = (
        "hybrid_forward_decision",
        "hybrid_forward_outcome",
        "hybrid_forward_run_log",
    )

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "SQLiteResearchStorage":
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        # Enable WAL for better concurrent read safety
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(self._conn)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def _c(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError(
                "SQLiteResearchStorage not open — use as context manager"
            )
        return self._conn

    # ── Schema ────────────────────────────────────────────────────────────────

    def ensure_schema(self) -> None:
        ensure_schema(self._c)

    # ── Write operations ──────────────────────────────────────────────────────

    def insert_decision(self, decision: HybridForwardDecision) -> Optional[int]:
        """
        Append-only decision insert.
        Returns row_id on new insert, None on idempotent skip.
        Raises ConflictError if same PK has a different decision_hash.
        """
        return insert_decision(self._c, decision)

    def insert_outcome(self, outcome: HybridForwardOutcome) -> Optional[int]:
        """
        Append-only outcome insert.
        Returns row_id on new insert, None on idempotent skip.
        Raises ConflictError if same (decision_id, horizon, calculation_version)
        has a different hybrid_net_return.
        """
        return insert_outcome(self._c, outcome)

    def upsert_run_log(self, log: HybridForwardRunLog) -> None:
        """Insert or update a run log entry (upsert by run_id)."""
        upsert_run_log(self._c, log)

    def commit(self) -> None:
        """Explicit commit — use after a batch of inserts for atomicity."""
        self._c.commit()

    # ── Read operations ───────────────────────────────────────────────────────

    def get_operational_summary(self) -> dict:
        return get_operational_summary(self._c)

    def get_matured_performance(
        self, horizon: str = "20d", classification_filter: str = "PROSPECTIVE"
    ) -> Optional[dict]:
        return get_matured_performance(self._c, horizon, classification_filter)

    # ── Health & metadata ─────────────────────────────────────────────────────

    def health_check(self) -> dict:
        """
        Returns a health dict suitable for the dashboard.
        Does NOT expose db path, credentials, or sensitive info.

        Returns:
          status: HEALTHY | DEGRADED | BLOCKED | UNKNOWN
          tables_present: list of found research tables
          tables_missing: list of expected but missing research tables
          last_checked_utc: ISO timestamp of this check
        """
        result = {
            "backend": "sqlite",
            "status": StorageHealthStatus.UNKNOWN,
            "tables_present": [],
            "tables_missing": [],
            "last_checked_utc": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }

        try:
            existing_tables = {
                r[0]
                for r in self._c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            present = [t for t in self.RESEARCH_TABLES if t in existing_tables]
            missing = [t for t in self.RESEARCH_TABLES if t not in existing_tables]
            result["tables_present"] = present
            result["tables_missing"] = missing

            # Ping: simple read
            self._c.execute("SELECT 1").fetchone()

            if missing:
                result["status"] = StorageHealthStatus.DEGRADED
            else:
                result["status"] = StorageHealthStatus.HEALTHY

        except Exception as exc:
            result["status"] = StorageHealthStatus.BLOCKED
            result["error"] = type(exc).__name__

        return result

    def get_storage_info(self) -> dict:
        """
        Returns non-sensitive storage metadata for the dashboard.
        Path is masked to show only the filename, not the full absolute path.
        """
        db_name = os.path.basename(self._db_path)
        file_exists = os.path.exists(self._db_path)
        file_size_kb: Optional[float] = None
        if file_exists:
            try:
                file_size_kb = round(os.path.getsize(self._db_path) / 1024, 1)
            except OSError:
                pass

        return {
            "backend": "sqlite",
            "db_name": db_name,              # filename only, not full path
            "file_exists": file_exists,
            "file_size_kb": file_size_kb,
            "environment": "local_research",
            "is_production": False,
        }


# ── PostgreSQL stub ───────────────────────────────────────────────────────────

class PostgreSQLResearchStorage:
    """
    STUB — Not yet implemented. Raises NotImplementedError on all operations.

    To implement Option C (dedicated research PostgreSQL):

    1. Provision a new PostgreSQL instance SEPARATE from production Neon.
       (Neon free tier, Supabase free tier, or a local Docker PG instance.)

    2. Set the following environment variables:
         RESEARCH_PG_URL=postgresql://user:password@host:5432/research_db
       Do NOT reuse NEON_URL — that is production data.

    3. Create the schema (equivalent to hybrid_forward_db SCHEMA_SQL):
         CREATE TABLE hybrid_forward_decision (
             id               SERIAL PRIMARY KEY,
             stock_id         TEXT NOT NULL,
             trade_date       DATE NOT NULL,
             rule_version     TEXT NOT NULL,
             research_version TEXT NOT NULL DEFAULT 'v2_research_v2',
             v2_entry_label   TEXT NOT NULL,
             hybrid_action    TEXT NOT NULL,
             rule_reason      TEXT NOT NULL,
             rule_priority    INTEGER NOT NULL,
             market_regime    TEXT NOT NULL,
             ma20_slope_pct   REAL NOT NULL,
             ma20_trend       TEXT NOT NULL,
             ma20_gap_pct     REAL,
             feature_cutoff_date DATE NOT NULL,
             input_data_as_of    DATE NOT NULL,
             input_data_hash     TEXT,
             decision_hash       TEXT NOT NULL,
             capture_classification TEXT NOT NULL,
             captured_at         TIMESTAMPTZ NOT NULL,
             run_id              TEXT NOT NULL,
             UNIQUE(stock_id, trade_date, rule_version)
         );
         -- (similar for hybrid_forward_outcome, hybrid_forward_run_log)

    4. Add psycopg2-binary to requirements.txt.

    5. Replace the stub methods below with real psycopg2 calls that mirror
       the SQLite logic in hybrid_forward_db.py.

    6. Set RESEARCH_STORAGE_BACKEND=postgresql in environment.

    SECURITY NOTE:
       RESEARCH_PG_URL must NEVER equal NEON_URL (production).
       Add a startup check that asserts the two URLs differ.
    """

    def __init__(self, pg_url: Optional[str] = None) -> None:
        self._pg_url = pg_url or os.environ.get("RESEARCH_PG_URL", "")
        if not self._pg_url:
            raise ValueError(
                "PostgreSQLResearchStorage requires RESEARCH_PG_URL env var. "
                "See class docstring for setup instructions."
            )

    def __enter__(self) -> "PostgreSQLResearchStorage":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        pass  # connection management TBD

    def ensure_schema(self) -> None:
        raise NotImplementedError(
            "PostgreSQLResearchStorage is a stub. "
            "See class docstring for implementation instructions."
        )

    def insert_decision(self, decision: HybridForwardDecision) -> Optional[int]:
        raise NotImplementedError

    def insert_outcome(self, outcome: HybridForwardOutcome) -> Optional[int]:
        raise NotImplementedError

    def upsert_run_log(self, log: HybridForwardRunLog) -> None:
        raise NotImplementedError

    def get_operational_summary(self) -> dict:
        raise NotImplementedError

    def get_matured_performance(
        self, horizon: str = "20d", classification_filter: str = "PROSPECTIVE"
    ) -> Optional[dict]:
        raise NotImplementedError

    def health_check(self) -> dict:
        return {
            "backend": "postgresql",
            "status": StorageHealthStatus.BLOCKED,
            "error": "PostgreSQLResearchStorage not yet implemented — see class docstring",
            "last_checked_utc": datetime.now(timezone.utc).isoformat(),
        }

    def get_storage_info(self) -> dict:
        return {
            "backend": "postgresql",
            "environment": "research_pg_stub",
            "is_production": False,
            "note": "Not yet implemented",
        }


# ── Factory ───────────────────────────────────────────────────────────────────

def get_research_storage(db_path: Optional[str] = None) -> SQLiteResearchStorage:
    """
    Factory that returns the appropriate storage backend.

    Currently always returns SQLiteResearchStorage (Option D / local cron).
    When RESEARCH_STORAGE_BACKEND=postgresql is set AND RESEARCH_PG_URL is configured,
    returns PostgreSQLResearchStorage (Option C) — once the stub is implemented.

    For GitHub Actions Option A (artifact cache), the SQLite file is restored
    from cache before this factory is called, so SQLiteResearchStorage works
    transparently with Option A persistence.
    """
    backend = os.environ.get("RESEARCH_STORAGE_BACKEND", "sqlite").lower()

    if backend == "postgresql":
        pg_url = os.environ.get("RESEARCH_PG_URL", "")
        if not pg_url:
            raise ValueError(
                "RESEARCH_STORAGE_BACKEND=postgresql requires RESEARCH_PG_URL. "
                "See PostgreSQLResearchStorage docstring."
            )
        # Safety check: must not equal production Neon URL
        neon_url = os.environ.get("NEON_URL", "")
        if neon_url and pg_url == neon_url:
            raise ValueError(
                "SECURITY: RESEARCH_PG_URL must not equal NEON_URL (production database). "
                "Provision a separate research PostgreSQL instance."
            )
        return PostgreSQLResearchStorage(pg_url)  # type: ignore[return-value]

    # Default: SQLite
    if db_path is None:
        from config import DB_PATH as _db_path
        db_path = str(_db_path)
    return SQLiteResearchStorage(db_path)
