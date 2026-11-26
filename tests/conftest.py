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

import os
import sqlite3
import urllib.parse
from pathlib import Path

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
# B4 — Session-level fail-closed isolation guard (S78C.6B.2)
# ---------------------------------------------------------------------------

_PRODUCTION_DB_CANONICAL: str = os.path.realpath(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "platform.db",
    )
)
_TESTS_FIXTURES_CANONICAL: str = os.path.realpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
)

# Populated by _register_pytest_temp_root (session-scoped autouse).
# Guard allows any path under these roots.
_PYTEST_TEMP_ROOT: list = []

# Save original BEFORE installing the guard so _guarded_connect can call it.
_original_sqlite_connect = sqlite3.connect


def _resolve_db_path(database) -> str | None:
    """Normalize a sqlite3.connect 'database' argument to a canonical absolute path.

    Returns None for ':memory:' (always allowed).
    Raises AssertionError for empty paths, unsupported URI schemes, or
    paths that cannot be resolved.
    """
    if isinstance(database, bytes):
        try:
            raw = database.decode("utf-8")
        except UnicodeDecodeError:
            raise AssertionError(
                f"ISOLATION GUARD: bytes input with non-UTF-8 encoding blocked: {database!r}"
            )
    elif hasattr(database, "__fspath__"):
        raw = os.fspath(database)
    else:
        raw = str(database)

    if raw == ":memory:":
        return None

    if not raw or not raw.strip():
        raise AssertionError(
            f"ISOLATION GUARD: empty path blocked (would create unnamed temp file): {database!r}"
        )

    # file://host/path authority-based URI → not supported by this codebase
    if raw.startswith("file://"):
        raise AssertionError(
            f"ISOLATION GUARD: authority-based URI not supported: {database!r}. "
            "Use file:path or a plain filesystem path."
        )

    # Unknown URI scheme (e.g. ftp://, http://)
    if "://" in raw and not raw.startswith("file:"):
        raise AssertionError(
            f"ISOLATION GUARD: unsupported URI scheme blocked: {database!r}"
        )

    # file: URI (file:path or file:/path or file:///abs/path)
    if raw.startswith("file:"):
        path_part = raw[5:]
        q = path_part.find("?")
        if q >= 0:
            path_part = path_part[:q]
        try:
            path_part = urllib.parse.unquote(path_part)
        except Exception:
            pass
        raw = path_part

    try:
        return os.path.realpath(os.path.abspath(raw))
    except (ValueError, OSError, TypeError) as exc:
        raise AssertionError(
            f"ISOLATION GUARD: unresolvable path blocked: {database!r}. Error: {exc}"
        ) from exc


def _is_under(child_str: str, parent_str: str) -> bool:
    try:
        Path(child_str).relative_to(parent_str)
        return True
    except ValueError:
        return False


def _guarded_connect(database, *args, **kwargs):
    """Fail-closed sqlite3.connect guard (S78C.6B.2).

    Allow list (checked in order):
      1. ':memory:' — always allowed.
      2. _PRODUCTION_DB_CANONICAL — always BLOCKED (highest priority).
      3. Hardlink alias of production DB — blocked when production DB file exists.
      4. tests/fixtures/ root — explicitly allowed for read-only snapshots.
      5. Registered pytest session temp roots — allowed for test DBs.
      6. Everything else — BLOCKED (fail-closed).

    Installed at conftest import time (session scope) so module-scoped and
    session-scoped fixtures are covered, not just function-scoped ones.
    """
    resolved = _resolve_db_path(database)

    if resolved is None:  # :memory:
        return _original_sqlite_connect(database, *args, **kwargs)

    # Production DB always blocked
    if resolved == _PRODUCTION_DB_CANONICAL:
        raise AssertionError(
            f"ISOLATION GUARD: production SQLite path blocked: {database!r}. "
            "Use ci_safe_conn or ci_conn_with_data fixtures instead."
        )

    # Hardlink alias: same inode+device as production DB
    if os.path.exists(_PRODUCTION_DB_CANONICAL) and os.path.exists(resolved):
        try:
            prod_st = os.stat(_PRODUCTION_DB_CANONICAL)
            res_st = os.stat(resolved)
            if prod_st.st_ino == res_st.st_ino and prod_st.st_dev == res_st.st_dev:
                raise AssertionError(
                    f"ISOLATION GUARD: hardlink alias to production DB blocked: {database!r}"
                )
        except OSError:
            pass

    # tests/fixtures/ is explicitly allowed
    if _is_under(resolved, _TESTS_FIXTURES_CANONICAL):
        return _original_sqlite_connect(database, *args, **kwargs)

    # Registered pytest session temp roots
    for root in _PYTEST_TEMP_ROOT:
        if _is_under(resolved, root):
            return _original_sqlite_connect(database, *args, **kwargs)

    # Fail-closed: unregistered path
    allowed = ", ".join(
        [repr(_TESTS_FIXTURES_CANONICAL)] + [repr(r) for r in _PYTEST_TEMP_ROOT]
    )
    raise AssertionError(
        f"ISOLATION GUARD: unregistered database path blocked (fail-closed): {database!r}. "
        f"Resolved: {resolved!r}. "
        f"Allowed roots: ':memory:', {allowed}. "
        "Use tmp_path fixture or ci_safe_conn for test databases."
    )


# Install at import time — covers collection, session, module, and function scopes.
sqlite3.connect = _guarded_connect


@pytest.fixture(scope="session", autouse=True)
def _register_pytest_temp_root(tmp_path_factory):
    """Register the pytest session temp root as an allowed path for the guard."""
    temp_root = str(tmp_path_factory.getbasetemp().resolve())
    _PYTEST_TEMP_ROOT.append(temp_root)
    yield
    if temp_root in _PYTEST_TEMP_ROOT:
        _PYTEST_TEMP_ROOT.remove(temp_root)


@pytest.fixture(autouse=True)
def _block_production_sqlite_paths():
    """Guard liveness check (S78C.6B.2). Guard is installed at conftest import time.

    This fixture verifies the session-level guard is still active at the start
    of every test. If the guard has been patched out, the test suite will fail
    loudly rather than silently allowing production DB access.
    """
    assert sqlite3.connect is _guarded_connect, (
        "GUARD FAILURE: session-level guard has been patched out. "
        "sqlite3.connect no longer points to _guarded_connect. "
        "Do not replace sqlite3.connect in fixtures or test bodies."
    )


def pytest_sessionfinish(session, exitstatus):
    """Restore sqlite3.connect to original after all tests complete."""
    sqlite3.connect = _original_sqlite_connect
    _PYTEST_TEMP_ROOT.clear()


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
