"""
Phase F POC (S78C.5.2 final) — isolated session50 tests with negative/guard cases.

Changes from S78C.5.1 (27 tests → 35 tests):
  B1 restored: test_all_records_date_match_verified, test_etf_non_standard_57
  B2 added:    TestN04 — conflict detection (price mismatch → CONFLICT_REVIEW,
               price match → SKIP_EXISTING). Tests backfill business logic.
  B4 added:    TestN05 — isolation guard verification (guard blocks production
               path; allows :memory:; no Neon/prod credentials in environment).

Authorization note (Phase B, S78C.5.1 correction):
  S78C.5 reported "46/46 trading safety tests PASS" in Phase H. Those were run
  from hotfix-78c worktree and exceeded the ≤30 test authorization. Corrected:
  this file contains only tests from fix-ci-78c5. No Trading Safety tests here.

Data provenance:
  Synthetic data in conftest._SYNTHETIC_DAILY_PRICES and _VERIFIED_RECORDS in
  market_source_verification_s50.py are both derived from S50 PART B real API
  investigation (2026-11-10). They are reference-derived fixtures, NOT
  independent market data verification or production data quality audits.

B2 deferred:
  "Date inconsistency" negative cases: not applicable — candidate dates are
  hardcoded constants, not DB-driven. DEFERRED to 78C.6A.
  "Coverage insufficiency" (retrieval_success_rate): computed from hardcoded
  _VERIFIED_RECORDS count / 599 expected; not DB-driven. DEFERRED to 78C.6A.

B4 deferred:
  Network connection blocking and subprocess isolation are beyond conftest
  monkeypatch scope. No external API calls or subprocess calls exist in the
  imported modules (verified by grep). DEFERRED to 78C.6A.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from src.research.market_source_verification_s50 import (
    BackfillAction,
    SourceVerificationLevel,
    build_backfill_candidate_manifest,
    validate_manifest_idempotency_in_temp_sqlite,
)

# ---------------------------------------------------------------------------
# Module-level fixtures (function scope — matches ci_safe_conn scope)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# P01–P04: Matrix structure — schema-only DB
# ---------------------------------------------------------------------------


class TestP01_MatrixBuildsFromEmptyDB:

    def test_builds_without_error(self, source_matrix_safe):
        assert source_matrix_safe is not None

    def test_eleven_date_summaries(self, source_matrix_safe):
        assert len(source_matrix_safe.date_summaries) == 11

    def test_dates_are_correct(self, source_matrix_safe):
        dates = {s.date for s in source_matrix_safe.date_summaries}
        expected = {
            "2026-10-08",
            "2026-10-15",
            "2026-10-19",
            "2026-10-20",
            "2026-10-27",
            "2026-10-29",
            "2026-10-30",
            "2026-11-02",
            "2026-11-03",
            "2026-11-06",
            "2026-11-09",
        }
        assert dates == expected

    def test_provider_verdicts_present(self, source_matrix_safe):
        assert "TWSE_SINGLE_STOCK" in source_matrix_safe.provider_verdicts
        assert "TWSE_BULK_HISTORICAL" in source_matrix_safe.provider_verdicts


# ---------------------------------------------------------------------------
# P05–P08: Source verdicts (all hardcoded in _DATE_SOURCE_VERDICT)
# ---------------------------------------------------------------------------


class TestP05_SourceVerdicts:

    def test_all_dates_source_verified_partial(self, source_matrix_safe):
        for ds in source_matrix_safe.date_summaries:
            assert (
                ds.source_verdict == SourceVerificationLevel.SOURCE_VERIFIED_PARTIAL
            ), f"{ds.date}: {ds.source_verdict}"

    def test_n_verified_partial_eleven_n_unavailable_zero(self, source_matrix_safe):
        assert source_matrix_safe.n_dates_source_verified_partial == 11
        assert source_matrix_safe.n_dates_source_unavailable == 0

    def test_n_upgraded_is_two(self, source_matrix_safe):
        assert source_matrix_safe.n_dates_upgraded == 2

    def test_nov06_nov09_have_upgrade_notes_others_do_not(self, source_matrix_safe):
        upgraded = {
            ds.date
            for ds in source_matrix_safe.date_summaries
            if ds.upgrade_from_prior is not None
        }
        assert upgraded == {"2026-11-06", "2026-11-09"}


# ---------------------------------------------------------------------------
# P09–P12: Verified records (hardcoded in _VERIFIED_RECORDS — DB-independent)
# ---------------------------------------------------------------------------


class TestP09_VerifiedRecordsFromHardcodedData:
    """
    Verified records originate from _VERIFIED_RECORDS constant, not from DB.
    Assertions confirm hardcoded S50 research evidence, not production data.
    """

    def test_at_least_ten_records(self, source_matrix_safe):
        assert len(source_matrix_safe.verified_records) >= 10

    def test_all_records_have_close_price(self, source_matrix_safe):
        for r in source_matrix_safe.verified_records:
            assert r.close_price is not None and r.close_price > 0

    def test_all_records_source_provider_twse(self, source_matrix_safe):
        for r in source_matrix_safe.verified_records:
            assert r.source_provider == "TWSE_SINGLE_STOCK"

    def test_all_records_date_match_verified(self, source_matrix_safe):
        # Verifies S50 date_match_verified field for every record.
        # This field confirms the API returned data for the queried date
        # (not a different date — a known issue with TWSE bulk APIs).
        for r in source_matrix_safe.verified_records:
            assert (
                r.date_match_verified is True
            ), f"{r.stock_id} {r.date}: date_match_verified={r.date_match_verified}"


# ---------------------------------------------------------------------------
# P13–P15: Specific price assertions (hardcoded — independent of DB content)
# ---------------------------------------------------------------------------


class TestP13_PriceAssertions:
    """
    Identical assertions to test_session50 TC05.
    Pass regardless of DB state because _VERIFIED_RECORDS is a hardcoded constant.
    If build_verified_historical_source_matrix begins reading prices from the DB
    in a future change, these tests would need synthetic data to pass.
    """

    def test_nov06_tsmc_close_is_2135(self, source_matrix_safe):
        r = next(
            r
            for r in source_matrix_safe.verified_records
            if r.date == "2026-11-06" and r.stock_id == "2330"
        )
        assert r.close_price == 2135.0

    def test_nov09_tsmc_close_is_2235(self, source_matrix_safe):
        r = next(
            r
            for r in source_matrix_safe.verified_records
            if r.date == "2026-11-09" and r.stock_id == "2330"
        )
        assert r.close_price == 2235.0

    def test_oct29_tsmc_close_is_2415(self, source_matrix_safe):
        r = next(
            r
            for r in source_matrix_safe.verified_records
            if r.date == "2026-10-29" and r.stock_id == "2330"
        )
        assert r.close_price == 2415.0


# ---------------------------------------------------------------------------
# P16–P19: Universe composition (fully hardcoded in _UNIVERSE_COMPOSITION)
# ---------------------------------------------------------------------------


class TestP16_UniverseComposition:

    def test_total_stocks_656(self, source_matrix_safe):
        uc = source_matrix_safe.universe_composition
        assert uc["total_stocks"] == 656

    def test_four_digit_numeric_599(self, source_matrix_safe):
        uc = source_matrix_safe.universe_composition
        assert uc["four_digit_numeric"] == 599

    def test_etf_non_standard_57(self, source_matrix_safe):
        # Restored from S78C.5 (dropped in S78C.5.1 to meet 30-test limit).
        uc = source_matrix_safe.universe_composition
        assert uc["etf_or_non_standard"] == 57

    def test_total_eq_four_digit_plus_etf(self, source_matrix_safe):
        uc = source_matrix_safe.universe_composition
        assert (
            uc["total_stocks"] == uc["four_digit_numeric"] + uc["etf_or_non_standard"]
        )


# ---------------------------------------------------------------------------
# P20–P22: Backfill manifest
# ---------------------------------------------------------------------------


class TestP20_BackfillManifest:

    def test_builds_without_error(self, backfill_safe):
        assert backfill_safe is not None

    def test_all_candidates_have_fingerprint(self, backfill_safe):
        for c in backfill_safe.candidates:
            assert c.source_record_fingerprint is not None
            assert len(c.source_record_fingerprint) == 12

    def test_idempotency_second_run_zero(self, backfill_safe):
        # validate_manifest_idempotency_in_temp_sqlite uses its own :memory: DB
        result = validate_manifest_idempotency_in_temp_sqlite(backfill_safe)
        assert result["second_run_inserts"] == 0
        assert result["idempotent"] is True


# ---------------------------------------------------------------------------
# N01–N03: Empty DB exposes DB-sourced fields explicitly
# ---------------------------------------------------------------------------


class TestN01_EmptyDBExposesDBSourcedFields:
    """
    With schema-only DB (zero rows), DB-sourced fields are 0 / False.
    These tests make the fixture's limitation explicit and visible, rather
    than hiding it behind assertions that happen to pass on hardcoded data.
    """

    def test_existing_stock_count_zero_on_empty_db(self, source_matrix_safe):
        for ds in source_matrix_safe.date_summaries:
            assert (
                ds.existing_stock_count == 0
            ), f"{ds.date}: expected 0, got {ds.existing_stock_count}"

    def test_benchmark_0050_not_present_on_empty_db(self, source_matrix_safe):
        for ds in source_matrix_safe.date_summaries:
            assert (
                ds.benchmark_0050_present is False
            ), f"{ds.date}: expected no 0050 on empty DB"

    def test_all_candidates_insert_on_empty_db(self, backfill_safe):
        """Empty DB → no existing rows → every verified record is INSERT_CANDIDATE."""
        for c in backfill_safe.candidates:
            assert c.proposed_action in (
                BackfillAction.INSERT_CANDIDATE,
                BackfillAction.VALIDATION_FAILED,
            ), f"Unexpected action {c.proposed_action} for {c.stock_id}/{c.trade_date}"


# ---------------------------------------------------------------------------
# N04–N05: Schema constraints
# ---------------------------------------------------------------------------


class TestN04_SchemaConstraints:

    def test_unique_constraint_prevents_duplicate_stock_date(self, ci_safe_conn):
        ci_safe_conn.execute(
            "INSERT INTO daily_prices (stock_id, date, close) VALUES ('2330','2026-10-29',2415.0)"
        )
        ci_safe_conn.commit()
        with pytest.raises(Exception):
            ci_safe_conn.execute(
                "INSERT INTO daily_prices (stock_id, date, close) VALUES ('2330','2026-10-29',2415.0)"
            )

    def test_missing_table_raises_operational_error(self):
        """Reproduces the CI root cause: a no-schema connection fails exactly as in CI."""
        bare_conn = sqlite3.connect(":memory:")
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            bare_conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()
        bare_conn.close()


# ---------------------------------------------------------------------------
# N06–N07: Function-scope isolation
# ---------------------------------------------------------------------------


class TestN06_FunctionScopeIsolation:
    """Proves that writes in one test do not contaminate another test."""

    def test_write_is_local_to_this_test(self, ci_safe_conn):
        ci_safe_conn.execute(
            "INSERT INTO daily_prices (stock_id, date, close) VALUES ('TEST','2026-01-01',100.0)"
        )
        ci_safe_conn.commit()
        n = ci_safe_conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        assert n == 1

    def test_other_test_sees_zero_rows(self, ci_safe_conn):
        """A different test invocation gets a fresh connection — write from above is gone."""
        n = ci_safe_conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        assert n == 0, (
            "Function-scope isolation broken: a row from another test is visible. "
            "ci_safe_conn must be function-scoped."
        )


# ---------------------------------------------------------------------------
# N08–N10: B2 — Backfill conflict detection (price mismatch negative cases)
# ---------------------------------------------------------------------------


class TestN08_BackfillConflictDetection:
    """
    B2 negative cases for build_backfill_candidate_manifest():
    When the DB already has a close price that differs by >0.01% from the
    verified record, the function must detect CONFLICT_REVIEW (not INSERT).
    When prices match, it must detect SKIP_EXISTING (not INSERT).
    """

    def test_conflict_review_on_price_mismatch(self, ci_safe_conn):
        # _VERIFIED_RECORDS has TSMC 2026-10-29 close=2415.0
        # Insert 2420.0 (diff ≈ 0.21%) → should detect CONFLICT_REVIEW
        ci_safe_conn.execute(
            "INSERT INTO daily_prices (stock_id, date, close) VALUES ('2330','2026-10-29',2420.0)"
        )
        ci_safe_conn.commit()
        manifest = build_backfill_candidate_manifest(ci_safe_conn)
        tsmc_oct29 = next(
            c
            for c in manifest.candidates
            if c.stock_id == "2330" and c.trade_date == "2026-10-29"
        )
        assert (
            tsmc_oct29.proposed_action == BackfillAction.CONFLICT_REVIEW
        ), f"Expected CONFLICT_REVIEW for price mismatch, got {tsmc_oct29.proposed_action}"
        assert tsmc_oct29.existing_record_status == "EXISTS"

    def test_skip_existing_on_price_match(self, ci_safe_conn):
        # Exact price match → SKIP_EXISTING (no conflict)
        ci_safe_conn.execute(
            "INSERT INTO daily_prices (stock_id, date, close) VALUES ('2330','2026-10-29',2415.0)"
        )
        ci_safe_conn.commit()
        manifest = build_backfill_candidate_manifest(ci_safe_conn)
        tsmc_oct29 = next(
            c
            for c in manifest.candidates
            if c.stock_id == "2330" and c.trade_date == "2026-10-29"
        )
        assert (
            tsmc_oct29.proposed_action == BackfillAction.SKIP_EXISTING
        ), f"Expected SKIP_EXISTING for price match, got {tsmc_oct29.proposed_action}"


# ---------------------------------------------------------------------------
# N11–N14: B4 — Isolation guard verification
# ---------------------------------------------------------------------------


class TestN11_IsolationGuard:
    """
    B4 executable isolation: verifies the _block_production_sqlite_paths
    autouse fixture is active and correctly guarding this test session.
    """

    def test_guard_blocks_production_db_path(self):
        """Guard must raise AssertionError when production path is requested."""
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect("data/platform.db")

    def test_guard_allows_memory_connections(self):
        """Guard must NOT block :memory: connections."""
        conn = sqlite3.connect(":memory:")
        conn.close()

    def test_no_neon_url_in_environment(self):
        """Production Neon credentials must not be present in test environment."""
        assert (
            "NEON_URL" not in os.environ
        ), "NEON_URL found in test environment — production credential leak"

    def test_no_production_database_url(self):
        """DATABASE_URL must not reference a production endpoint."""
        db_url = os.environ.get("DATABASE_URL", "")
        assert (
            "neon.tech" not in db_url
        ), f"Production DATABASE_URL detected: {db_url!r}"
        assert (
            "platform.db" not in db_url
        ), f"Production SQLite path in DATABASE_URL: {db_url!r}"


# ---------------------------------------------------------------------------
# N12–N19: Module-scoped fixture isolation (8 new guard tests — S78C.6A.1)
# ---------------------------------------------------------------------------


class TestN12_ModuleScopeIsolation:
    """Isolation evidence for ci_module_conn (module-scoped) and scope gap documentation.

    Scope gap: _block_production_sqlite_paths is function-scoped (monkeypatch).
    Module-scoped fixtures fire BEFORE function-scoped fixtures → guard does NOT
    intercept module-scoped sqlite3.connect() calls.

    Design consequence:
    - CI-safe module-scoped fixtures MUST use :memory: by construction.
    - Production-audit module-scoped fixtures (conn → platform.db) are intentionally
      outside the guard's scope. They create an empty file in CI (expected OperationalError).
    - Python monkeypatch ≠ OS-level sandbox. These tests prove Python-level protection only.
    """

    def test_ci_module_conn_is_memory_database(self, ci_module_conn):
        rows = ci_module_conn.execute("PRAGMA database_list").fetchall()
        assert any(
            row[2] == "" for row in rows
        ), "ci_module_conn must be :memory: (empty file path in PRAGMA database_list)"

    def test_ci_module_conn_has_daily_prices_schema(self, ci_module_conn):
        tables = {
            r[0]
            for r in ci_module_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert (
            "daily_prices" in tables
        ), f"daily_prices missing from ci_module_conn schema: {tables}"

    def test_ci_module_conn_starts_with_zero_rows(self, ci_module_conn):
        n = ci_module_conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        assert n == 0, f"ci_module_conn must start empty, found {n} rows"

    def test_ci_module_conn_not_platform_db_path(self, ci_module_conn):
        rows = ci_module_conn.execute("PRAGMA database_list").fetchall()
        for row in rows:
            assert (
                "platform.db" not in row[2]
            ), f"ci_module_conn points to production path: {row[2]!r}"

    def test_function_scoped_guard_active_during_test_body(self):
        # Guard IS active for test bodies (function scope)
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect("data/platform.db")

    def test_no_anthropic_api_key_in_test_environment(self):
        # Prevents accidental API calls to Anthropic during tests
        assert (
            "ANTHROPIC_API_KEY" not in os.environ
        ), "ANTHROPIC_API_KEY found — LLM API calls could be triggered accidentally"

    def test_no_postgres_in_database_url(self):
        db_url = os.environ.get("DATABASE_URL", "")
        assert (
            "postgres" not in db_url.lower()
        ), f"PostgreSQL DATABASE_URL in test env: {db_url[:30]!r}"

    def test_src_database_import_does_not_create_engine(self):
        # src.database defines ORM Base and models but must not connect at import time.
        # C1 verified zero sqlite3.connect() calls during import; this test verifies
        # no module-level engine variable exists that could hold an open connection.
        import src.database as db_module

        assert (
            not hasattr(db_module, "engine") or db_module.engine is None
        ), "src.database has module-level engine — may hold open DB connection"
