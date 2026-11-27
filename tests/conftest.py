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


def _apply_schema(conn: sqlite3.Connection) -> None:
    """Apply canonical SQLAlchemy schema to any SQLite connection.

    Source: src/database.py Base.metadata — permanent DDL consistency guarantee.
    Does not read from or write to any application data.
    """
    from sqlalchemy.schema import CreateTable
    from src.database import Base

    temp_engine = create_engine("sqlite:///:memory:", echo=False)
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(temp_engine))
        conn.execute(ddl)
    conn.commit()
    temp_engine.dispose()


def _make_schema_conn() -> sqlite3.Connection:
    """Create :memory: SQLite with canonical schema via SQLAlchemy DDL emission.

    Uses CreateTable().compile() to generate DDL strings from SQLAlchemy model
    metadata, then executes them on a fresh sqlite3 :memory: connection.
    This ensures permanent consistency with src/database.py without manual DDL.

    Note: SQLAlchemy :memory: engines and sqlite3.connect(":memory:") are
    always separate, independent DB instances. We use CreateTable to bridge them.
    """
    conn = sqlite3.connect(":memory:")
    _apply_schema(conn)
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
# S78C.8B — File-backed isolated database infrastructure
# ---------------------------------------------------------------------------


class IsolatedFileDb:
    """Owned file-backed SQLite database with explicit lifecycle.

    Context manager: creates the database file, applies canonical schema,
    closes the connection and removes owned artifacts on exit (normal or exception).

    path must reside under a registered pytest temp root (_PYTEST_TEMP_ROOT).
    Parent directory is never deleted; only the owned DB file (and WAL/SHM) is removed.
    seed=True applies _SYNTHETIC_DAILY_PRICES via _seed().
    """

    def __init__(self, path: str, seed: bool = False):
        self._path = path
        self._seed = seed
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self._conn = sqlite3.connect(self._path)
        try:
            _apply_schema(self._conn)
            if self._seed:
                _seed(self._conn)
        except Exception:
            self._conn.close()
            self._conn = None
            try:
                os.remove(self._path)
            except FileNotFoundError:
                pass
            raise
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        try:
            os.remove(self._path)
        except FileNotFoundError:
            pass
        for suffix in ("-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except FileNotFoundError:
                pass
        return False


@pytest.fixture()
def ci_file_conn(tmp_path):
    """File-backed SQLite in pytest temp root, with canonical schema (zero rows).

    Function-scoped. Each test gets an independent file at tmp_path/ci_test.db.
    Compatible with the SQLite Isolation Guard (path is under _PYTEST_TEMP_ROOT).

    Use when the test requires: close/reopen behavior, multiple connections,
    transaction rollback, or file-level persistence between operations.
    """
    db_path = str(tmp_path / "ci_test.db")
    conn = sqlite3.connect(db_path)
    try:
        _apply_schema(conn)
    except Exception:
        conn.close()
        raise
    yield conn
    conn.close()


@pytest.fixture()
def ci_file_conn_with_data(tmp_path):
    """File-backed SQLite seeded with 12 synthetic OHLC rows.

    Function-scoped. Same seed profile as ci_conn_with_data, file-backed.
    Compatible with the SQLite Isolation Guard.
    """
    db_path = str(tmp_path / "ci_test_data.db")
    conn = sqlite3.connect(db_path)
    try:
        _apply_schema(conn)
        _seed(conn)
    except Exception:
        conn.close()
        raise
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

# ── Coverage data directory (S78C.6B.4 Option A) ─────────────────────────────
# Derive repo root from the already-verified tests/fixtures canonical path.
# _TESTS_FIXTURES_CANONICAL = {repo_root}/tests/fixtures  →  two parents up = repo root.
_REPO_ROOT: str = os.path.realpath(
    os.path.dirname(os.path.dirname(_TESTS_FIXTURES_CANONICAL))
)
_EXPECTED_COV_DIR: str = os.path.join(_REPO_ROOT, ".ci_cov_data")

# Reject a pre-existing symlink: it could silently redirect coverage writes.
if os.path.islink(_EXPECTED_COV_DIR):
    raise AssertionError(
        f"COVERAGE GUARD: .ci_cov_data exists as a symlink at {_EXPECTED_COV_DIR!r}. "
        "Pre-existing symlinks are rejected (fail-closed). "
        "Remove the symlink before running tests."
    )

os.makedirs(_EXPECTED_COV_DIR, exist_ok=True)

# Resolve canonical path AFTER creation to guard against TOCTOU or bind mounts.
_COVERAGE_DATA_DIR: str = os.path.realpath(_EXPECTED_COV_DIR)

# Validate: must be exactly {repo_root}/.ci_cov_data — no deeper, no aliases.
if (
    os.path.dirname(_COVERAGE_DATA_DIR) != _REPO_ROOT
    or os.path.basename(_COVERAGE_DATA_DIR) != ".ci_cov_data"
):
    raise AssertionError(
        f"COVERAGE GUARD: {_COVERAGE_DATA_DIR!r} did not resolve to "
        f"{{repo_root}}/.ci_cov_data (repo_root={_REPO_ROOT!r}). "
        "Refusing to register (fail-closed)."
    )

# Guard against accidental collision with protected roots.
_prod_db_parent: str = os.path.dirname(_PRODUCTION_DB_CANONICAL)
if _COVERAGE_DATA_DIR in (_REPO_ROOT, _prod_db_parent, _TESTS_FIXTURES_CANONICAL):
    raise AssertionError(
        f"COVERAGE GUARD: coverage dir {_COVERAGE_DATA_DIR!r} collides with "
        "a protected path. Refusing to register (fail-closed)."
    )

# Working-directory consistency: pyproject.toml data_file = ".ci_cov_data/.coverage"
# is a relative path resolved from cwd. Fail-closed if cwd is not the repo root.
_cwd_resolved_cov: str = os.path.realpath(os.path.join(os.getcwd(), ".ci_cov_data"))
if _cwd_resolved_cov != _COVERAGE_DATA_DIR:
    raise AssertionError(
        f"COVERAGE GUARD: cwd {os.getcwd()!r} is not the repository root. "
        f"pyproject.toml data_file would resolve to {_cwd_resolved_cov!r} "
        f"instead of {_COVERAGE_DATA_DIR!r}. "
        "Run pytest from the repository root (fail-closed)."
    )

# COVERAGE_FILE env var: if set, it must resolve inside _COVERAGE_DATA_DIR.
_cov_env_file: str = os.environ.get("COVERAGE_FILE", "")
if _cov_env_file:
    _cov_env_canonical: str = os.path.realpath(os.path.abspath(_cov_env_file))
    try:
        Path(_cov_env_canonical).relative_to(_COVERAGE_DATA_DIR)
    except ValueError:
        raise AssertionError(
            f"COVERAGE GUARD: COVERAGE_FILE={_cov_env_file!r} resolves to "
            f"{_cov_env_canonical!r}, outside registered dir {_COVERAGE_DATA_DIR!r}. "
            "Unset COVERAGE_FILE or point it into .ci_cov_data/ (fail-closed)."
        )

# Register at import time — NOT via fixture — so this entry persists through
# session-scoped fixture teardown (which removes only pytest's temp root).
# Coverage's Central.finish() fires inside pytest_runtestloop wrapper, after
# fixture teardown but before pytest_sessionfinish; this entry must still be present.
_PYTEST_TEMP_ROOT.append(_COVERAGE_DATA_DIR)

# Save original BEFORE installing the guard so _guarded_connect can call it.
_original_sqlite_connect = sqlite3.connect


def _validate_coverage_uri_query(query: str, database) -> None:
    """Validate query parameters of a file:/// URI (coverage combine path).

    Only CI-verified values are accepted:
      mode=ro          (required; observed in GitHub CI check_hot_journal traceback)
      immutable=1      (optional; observed in older coverage combine step)
    All other mode values, immutable=0, unknown keys, duplicates, and missing mode are rejected.
    """
    _ALLOWED_KEYS = frozenset({"mode", "immutable"})
    _ALLOWED_MODE = frozenset({"ro"})         # only mode=ro verified from CI
    _ALLOWED_IMMUTABLE = frozenset({"1"})     # only immutable=1 verified from CI
    try:
        params = urllib.parse.parse_qs(query, strict_parsing=True, keep_blank_values=True)
    except ValueError:
        raise AssertionError(
            f"ISOLATION GUARD: malformed URI query string blocked: {database!r}"
        )
    unknown = set(params.keys()) - _ALLOWED_KEYS
    if unknown:
        raise AssertionError(
            f"ISOLATION GUARD: unauthorized URI query parameters "
            f"{sorted(unknown)!r} blocked: {database!r}"
        )
    for key, values in params.items():
        if len(values) != 1:
            raise AssertionError(
                f"ISOLATION GUARD: duplicate URI query parameter {key!r} blocked: {database!r}"
            )
    # mode=ro is required; immutable is optional (if present, must be 1).
    if "mode" not in params:
        raise AssertionError(
            f"ISOLATION GUARD: missing required URI query parameter 'mode' blocked: {database!r}. "
            "Coverage URIs require mode=ro."
        )
    if params["mode"][0] not in _ALLOWED_MODE:
        raise AssertionError(
            f"ISOLATION GUARD: unauthorized URI mode {params['mode'][0]!r} blocked: {database!r}"
        )
    if "immutable" in params and params["immutable"][0] not in _ALLOWED_IMMUTABLE:
        raise AssertionError(
            f"ISOLATION GUARD: unauthorized URI immutable value "
            f"{params['immutable'][0]!r} blocked: {database!r}"
        )


def _resolve_db_path(database, uri_explicit: bool = False) -> str | None:
    """Normalize a sqlite3.connect 'database' argument to a canonical absolute path.

    uri_explicit: True when sqlite3.connect was called with uri=True.
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

    # file:// URI — file:///path (empty authority) is allowed when uri=True;
    # file://host/path (non-empty authority) is never supported.
    if raw.startswith("file://"):
        if not uri_explicit:
            raise AssertionError(
                f"ISOLATION GUARD: authority-based URI not supported: {database!r}. "
                "Use file:path or a plain filesystem path."
            )
        try:
            parsed = urllib.parse.urlparse(raw)
        except Exception:
            raise AssertionError(
                f"ISOLATION GUARD: malformed file:// URI blocked: {database!r}"
            )
        if parsed.netloc:  # non-empty authority (file://host/path)
            raise AssertionError(
                f"ISOLATION GUARD: authority-based URI not supported: {database!r}. "
                "Use file:///absolute/path."
            )
        if parsed.fragment:
            raise AssertionError(
                f"ISOLATION GUARD: URI fragment not supported: {database!r}"
            )
        # Percent-encoded paths are unverified and rejected (B3).
        # CI coverage URIs use plain absolute paths with no encoding.
        if "%" in parsed.path:
            raise AssertionError(
                f"ISOLATION GUARD: percent-encoded URI path not supported: {database!r}. "
                "Coverage URIs use plain absolute paths."
            )
        # Empty or absent query is unverified; CI format always includes ?mode=ro&immutable=1.
        if not parsed.query:
            raise AssertionError(
                f"ISOLATION GUARD: file:// URI without query parameters not supported: {database!r}. "
                "Coverage URIs require a non-empty query (e.g. ?mode=ro&immutable=1)."
            )
        _validate_coverage_uri_query(parsed.query, database)
        raw = urllib.parse.unquote(parsed.path)
        # Resolve to canonical path and enforce coverage-only scope (B1).
        # file:/// URIs are exclusively for .ci_cov_data artifacts — not for
        # pytest tmp dirs, fixtures, or any other path in _PYTEST_TEMP_ROOT.
        try:
            resolved_uri = os.path.realpath(os.path.abspath(raw))
        except (ValueError, OSError, TypeError) as exc:
            raise AssertionError(
                f"ISOLATION GUARD: unresolvable URI path blocked: {database!r}. Error: {exc}"
            ) from exc
        if not _is_under(resolved_uri, _COVERAGE_DATA_DIR):
            raise AssertionError(
                f"ISOLATION GUARD: file:// URI path outside coverage data directory blocked: "
                f"{database!r}. Resolved: {resolved_uri!r}. "
                f"Expected under {_COVERAGE_DATA_DIR!r}."
            )
        return resolved_uri  # validated; skip the plain-path resolution below

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
    resolved = _resolve_db_path(database, uri_explicit=bool(kwargs.get("uri", False)))

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


def _guard_identity_check(connect_ref) -> None:
    """Pure identity check — raises AssertionError if connect_ref is not _guarded_connect.

    Does not read or modify sqlite3.connect. Caller supplies the reference to check.
    Used by get_active_guard() and directly testable without touching global state.
    """
    if connect_ref is not _guarded_connect:
        raise AssertionError(
            "GUARD FAILURE: provided connect_ref is not _guarded_connect. "
            f"Found: {connect_ref!r}."
        )


def get_active_guard():
    """Return the installed Guard function; raise AssertionError if not active.

    Use when test code must capture the Guard reference before patching
    sqlite3.connect, or when a helper needs to verify-then-capture the Guard
    identity in one atomic operation. Does not modify sqlite3.connect.
    """
    _guard_identity_check(sqlite3.connect)
    return _guarded_connect


@pytest.fixture()
def ci_guard_identity():
    """Guard identity contract fixture (function-scoped).

    Returns the active _guarded_connect reference after re-verifying it is
    installed. Fails closed if the Guard has been replaced between tests.
    Does not modify sqlite3.connect.

    Re-verified on each invocation (function-scoped). Complements the per-test
    Guard liveness check in _block_production_sqlite_paths.
    """
    return get_active_guard()


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
