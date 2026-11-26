"""
CI test infrastructure — shared fixtures for isolated, production-DB-free tests.
S78C.5.1 revision: function scope, SQLAlchemy-generated schema, negative case support.

Design decisions (S78C.5.1 Phase C):

1. Scope: function (not session)
   - Session scope requires proof that no test writes to the shared connection.
   - Current POC tests are read-only, but session scope creates fragility for future tests.
   - Function scope guarantees each test gets an independent :memory: connection.
   - Performance cost: negligible (~1ms per fixture creation for :memory: SQLite).

2. Schema generation: SQLAlchemy Base.metadata.create_all()
   - S78C.5 handwritten DDL diverged in two places:
     (a) `date TEXT` vs canonical `date DATE`
     (b) `id INTEGER PRIMARY KEY AUTOINCREMENT` vs SQLAlchemy-emitted form
   - Using ORM-generated DDL ensures permanent consistency with src/database.py models.
   - No manual DDL to maintain or diverge.

3. Production access: SQLAlchemy engine uses `sqlite:///:memory:` exclusively.
   - No DATABASE_URL, no NEON_URL, no data/platform.db path.
   - `config.py` constructs DB_PATH at module level but does not connect at import time.
   - Verified: `src.database` has no module-level engine attribute.

4. Synthetic data provenance:
   - `_SYNTHETIC_DAILY_PRICES` values are DERIVED from `_VERIFIED_RECORDS` in
     src/research/market_source_verification_s50.py (S50 PART B real API investigation).
   - These are reference-derived fixtures, NOT independent market data verification.
   - Tests using `ci_conn_with_data` assert internal code correctness against known inputs,
     not production data integrity.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine

from src.research.market_source_verification_s50 import (
    build_backfill_candidate_manifest,
    build_verified_historical_source_matrix,
)


def _make_schema_conn() -> sqlite3.Connection:
    """Create :memory: SQLite with canonical schema via SQLAlchemy DDL emission.

    Uses CreateTable().compile() to generate DDL strings from SQLAlchemy model
    metadata, then executes them on a fresh sqlite3 :memory: connection.
    This ensures permanent consistency with src/database.py without manual DDL.

    Note: SQLAlchemy :memory: engines and sqlite3.connect(":memory:") are
    always separate, independent DB instances. We use CreateTable to bridge them.
    """
    from sqlalchemy.schema import CreateTable

    from src.database import Base

    conn = sqlite3.connect(":memory:")
    temp_engine = create_engine("sqlite:///:memory:", echo=False)
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(temp_engine))
        conn.execute(ddl)
    conn.commit()
    temp_engine.dispose()
    return conn


# ---------------------------------------------------------------------------
# Synthetic data (reference-derived from _VERIFIED_RECORDS in s50 module)
# ---------------------------------------------------------------------------

_SYNTHETIC_DAILY_PRICES = [
    # (date, stock_id, open, high, low, close, volume)
    # Reference source: src/research/market_source_verification_s50._VERIFIED_RECORDS
    # S50 PART B real TWSE single-stock API investigation (2026-11-10)
    ("2026-10-29", "2330", 2420.0, 2425.0, 2390.0, 2415.0, 18403916),
    ("2026-10-29", "2454", 4205.0, 4225.0, 4000.0, 4045.0, 6867223),
    ("2026-10-29", "2317", 250.0, 253.5, 247.0, 248.0, 21358260),
    ("2026-10-30", "2330", 2380.0, 2380.0, 2360.0, 2370.0, 36615931),
    ("2026-10-30", "2454", 3820.0, 3990.0, 3805.0, 3915.0, 13044171),
    ("2026-11-02", "2330", 2310.0, 2345.0, 2310.0, 2330.0, 41165068),
    ("2026-11-03", "2317", 249.0, 250.0, 243.5, 245.5, 44139321),
    ("2026-11-06", "2330", None, None, None, 2135.0, None),
    ("2026-11-06", "2454", None, None, None, 3390.0, None),
    ("2026-11-09", "2330", None, None, None, 2235.0, None),
    ("2026-11-09", "2454", None, None, None, 3725.0, None),
    # 0050 benchmark present on a representative date
    ("2026-10-29", "0050", 190.0, 191.0, 189.0, 190.5, 5000000),
]


def _seed(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO daily_prices "
        "(date, stock_id, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
        _SYNTHETIC_DAILY_PRICES,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Fixtures — function scope (one fresh connection per test)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ci_module_conn():
    """Module-scoped :memory: SQLite with canonical schema.

    Shared by all tests in a module. Use for module-scoped fixtures (source_matrix,
    backfill_manifest) that need a stable connection across the module's test run.

    Safe for CI: :memory: is always allowed by _block_production_sqlite_paths.

    Scope note: module-scoped fixtures fire BEFORE function-scoped fixtures.
    This fixture is safe by construction (:memory:), not via monkeypatch protection.
    """
    conn = _make_schema_conn()
    yield conn
    conn.close()


@pytest.fixture()
def ci_safe_conn():
    """Fresh :memory: SQLite with canonical schema, zero data rows.

    Function-scoped: each test gets its own independent connection.
    Use when the code under test only needs the table to exist
    (COUNT queries returning 0 are acceptable for logic tests).

    ISOLATION GUARANTEE: each invocation creates a new :memory: instance.
    sqlite3.connect(":memory:") always returns a distinct, independent DB.
    """
    conn = _make_schema_conn()
    yield conn
    conn.close()


@pytest.fixture()
def ci_conn_with_data():
    """Fresh :memory: SQLite seeded with 12 synthetic OHLC rows.

    Function-scoped. Data provenance: reference-derived from _VERIFIED_RECORDS
    (src/research/market_source_verification_s50.py). NOT independent market
    data verification — tests using this fixture verify code correctness against
    known reference inputs, not production data integrity.
    """
    conn = _make_schema_conn()
    _seed(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# B4 — Executable production isolation guard
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _block_production_sqlite_paths(monkeypatch):
    """Autouse guard: raises AssertionError if any test attempts to open a
    production SQLite path. Applies to every test function in this session.

    Allowed: sqlite3.connect(":memory:")
    Blocked: any path containing "platform.db"

    Uses monkeypatch so the patch auto-reverts after each test with no
    state bleed across tests.

    Coverage: guards sqlite3.connect() calls made by application code,
    fixtures, and test bodies. Does not guard SQLAlchemy's internal driver
    calls for :memory: (those pass ":memory:" which is explicitly allowed).

    Limitation: does not block `from sqlite3 import connect` aliases;
    no such pattern exists in the POC or imported modules (verified by grep).
    """
    _original = sqlite3.connect
    _BLOCKED = "platform.db"

    def _guarded(database, *args, **kwargs):
        db_str = str(database)
        if db_str != ":memory:" and _BLOCKED in db_str:
            raise AssertionError(
                f"ISOLATION GUARD: production SQLite path blocked: {database!r}. "
                "Use ci_safe_conn or ci_conn_with_data fixtures instead."
            )
        return _original(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", _guarded)


# ---------------------------------------------------------------------------
# Pytest marks
# ---------------------------------------------------------------------------


@pytest.fixture()
def source_matrix_safe(ci_safe_conn):
    """VerifiedHistoricalSourceMatrix built from :memory: schema-only DB."""
    return build_verified_historical_source_matrix(ci_safe_conn)


@pytest.fixture()
def backfill_safe(ci_safe_conn):
    """BackfillCandidateManifest built from :memory: schema-only DB."""
    return build_backfill_candidate_manifest(ci_safe_conn)


# ---------------------------------------------------------------------------
# Pytest marks
# ---------------------------------------------------------------------------


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "production_audit: marks tests that assert production-DB-specific values "
        "(row counts, specific prices from live platform.db). "
        "Excluded from CI via addopts; run locally with -m production_audit.",
    )
