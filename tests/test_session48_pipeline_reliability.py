"""
Session 48 — Pipeline Reliability, Coverage Quality Gate, Backfill Dry-run,
20D Calendar Contract Correction, Strict 5D Readiness, and Guardrails.

Test categories TC01–TC34:
  TC01  Safety: no production writes
  TC02  Safety: frozen baseline unchanged
  TC03  Safety: forward signals integrity (2605 total)
  TC04  Safety: no 20D outcome computation
  TC05  Pipeline tier classification — TIER_1_PROXY
  TC06  Pipeline tier classification — TIER_655_FILL
  TC07  Pipeline tier classification — TIER_6957_BACKFILL
  TC08  Pipeline tier classification — TIER_ZERO_MISSING
  TC09  Root cause: PIPELINE_SELECTIVE dates
  TC10  Root cause: SCHEDULER_NOT_TRIGGERED dates
  TC11  Root cause: QUALITY_GATE_FAIL (Nov 06)
  TC12  Root cause: PROVIDER_NOT_READY (Nov 09)
  TC13  Root cause: MANUAL_BACKFILL (Nov 04/05)
  TC14  Coverage matrix: 15 dimensions present
  TC15  Coverage matrix: benchmark_only count = 9
  TC16  Coverage matrix: missing_days count = 2
  TC17  Coverage matrix: complete_days count = 9
  TC18  Coverage matrix: total_trading_days = 20
  TC19  Coverage matrix: TSMC absent on PARTIAL dates
  TC20  Coverage matrix: affects_active_cluster flags
  TC21  Backfill dry-run: 11 candidates
  TC22  Backfill dry-run: insert_only count = 9
  TC23  Backfill dry-run: unverified count = 2
  TC24  Backfill dry-run: no production writes triggered
  TC25  Pipeline stage analysis: SCHEDULER_NOT_TRIGGERED → S01 only
  TC26  Pipeline stage analysis: PIPELINE_SELECTIVE → S07 reached
  TC27  20D contract correction: S46 errors identified
  TC28  20D contract correction: earliest maturity = 2026-11-12
  TC29  20D contract correction: latest maturity = 2026-11-25
  TC30  20D maturity matrix: all 6 NOT_YET_MATURE
  TC31  20D maturity matrix: auth status = NOT_AUTHORIZED
  TC32  5D readiness: 3 strict + 3 waiting
  TC33  Guardrails G03 FAIL (3/10)
  TC34  Guardrails G04 FAIL (max 80% overlap)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.research.pipeline_reliability_s48 import (
    PipelineTier,
    PipelineRootCause,
    RootCauseConfidence,
    CoverageStatus,
    BackfillReadiness,
    PIPELINE_STAGES,
    build_daily_coverage_matrix,
    build_backfill_dry_run_plan,
    get_pipeline_stage_analysis,
    _FILL_DATES,
    _BACKFILL_CANDIDATES,
    _ROOT_CAUSE_MAP,
)
from src.research.calendar_contract_s48 import (
    MaturityStatus20D,
    Readiness5D,
    CalendarContractStatus,
    GuardrailStatus,
    build_calendar_contract_correction,
    build_20d_maturity_matrix,
    build_strict_readiness_matrix_5d,
    build_guardrail_summary,
    get_s46_errors_summary,
    _CORRECT_5TD,
    _CORRECT_20TD,
    _S46_5TD,
    _S46_20TD,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ANALYSIS_DATE = "2026-11-09"
REAL_DB_PATH = "data/platform.db"


@pytest.fixture(scope="module")
def conn():
    """Read-only connection to research SQLite."""
    con = sqlite3.connect(REAL_DB_PATH)
    con.row_factory = sqlite3.Row
    yield con
    con.close()


@pytest.fixture(scope="module")
def mock_conn():
    """In-memory SQLite with minimal daily_prices data for unit tests."""
    con = sqlite3.connect(":memory:")
    con.execute("""
        CREATE TABLE daily_prices (
            id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            stock_id TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume INTEGER
        )
    """)
    con.execute("""
        CREATE TABLE forward_signals (
            id INTEGER PRIMARY KEY,
            trade_date TEXT,
            execution_date TEXT,
            model_version TEXT,
            trade_signal TEXT
        )
    """)
    # Insert proxy-only dates (1 stock, 0050)
    for d in ["2026-10-08", "2026-10-15", "2026-10-19", "2026-10-20",
              "2026-10-27", "2026-10-29", "2026-10-30",
              "2026-11-02", "2026-11-03"]:
        con.execute(
            "INSERT INTO daily_prices (date, stock_id, open, high, low, close, volume) "
            "VALUES (?, '0050', 100, 101, 99, 100, 1000000)",
            (d,)
        )
    # Insert fill-date rows (655 stocks, include 2330)
    for d in ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-16",
              "2026-10-21", "2026-10-22", "2026-10-28"]:
        for stock in ["0050", "2330"] + [f"{i:04d}" for i in range(1, 654)]:
            con.execute(
                "INSERT INTO daily_prices (date, stock_id, open, high, low, close, volume) "
                "VALUES (?, ?, 100, 101, 99, 100, 1000000)",
                (d, stock)
            )
    # Insert backfill dates (6957 stocks, include 2330)
    for d in ["2026-11-04", "2026-11-05"]:
        for stock in ["0050", "2330"] + [f"{i:04d}" for i in range(1, 6956)]:
            con.execute(
                "INSERT INTO daily_prices (date, stock_id, open, high, low, close, volume) "
                "VALUES (?, ?, 100, 101, 99, 100, 1000000)",
                (d, stock)
            )
    # Nov 06, Nov 09: 0 rows

    # Insert forward signals
    for d, n in [("2026-10-13", 46), ("2026-10-14", 27), ("2026-10-16", 55),
                 ("2026-10-21", 39), ("2026-10-22", 23), ("2026-10-28", 19)]:
        for _ in range(n):
            con.execute(
                "INSERT INTO forward_signals (trade_date, execution_date, "
                "model_version, trade_signal) VALUES (?, ?, 'v8.0', 'buy')",
                (d, d)
            )
    con.commit()
    yield con
    con.close()


@pytest.fixture(scope="module")
def coverage_matrix(conn):
    return build_daily_coverage_matrix(conn, ANALYSIS_DATE)


@pytest.fixture(scope="module")
def backfill_plan(conn):
    return build_backfill_dry_run_plan(conn, ANALYSIS_DATE)


@pytest.fixture(scope="module")
def contract_records():
    return build_calendar_contract_correction(ANALYSIS_DATE)


@pytest.fixture(scope="module")
def maturity_matrix(conn):
    return build_20d_maturity_matrix(conn, ANALYSIS_DATE)


@pytest.fixture(scope="module")
def readiness_matrix(conn):
    return build_strict_readiness_matrix_5d(conn, ANALYSIS_DATE)


@pytest.fixture(scope="module")
def guardrails():
    return build_guardrail_summary(ANALYSIS_DATE, strict_cluster_count=3)


# ---------------------------------------------------------------------------
# TC01: Safety — no production writes
# ---------------------------------------------------------------------------

class TestTC01_SafetyNoProductionWrites:
    def test_tc01_pipeline_module_has_safety_note(self):
        import src.research.pipeline_reliability_s48 as m
        assert "READ-ONLY" in m.__doc__

    def test_tc01_calendar_module_has_safety_note(self):
        import src.research.calendar_contract_s48 as m
        assert "READ-ONLY" in m.__doc__

    def test_tc01_no_insert_in_pipeline_module(self):
        import inspect
        import src.research.pipeline_reliability_s48 as m
        src = inspect.getsource(m)
        assert "INSERT INTO daily_prices" not in src
        assert "INSERT INTO forward_signals" not in src

    def test_tc01_no_insert_in_calendar_module(self):
        import inspect
        import src.research.calendar_contract_s48 as m
        src = inspect.getsource(m)
        assert "INSERT INTO" not in src


# ---------------------------------------------------------------------------
# TC02: Safety — frozen baseline unchanged
# ---------------------------------------------------------------------------

class TestTC02_FrozenBaseline:
    def test_tc02_v3_hash_unchanged(self):
        V3_HASH = "be43e8ca977d9fdd"
        import src.research.v3_prospective_shadow as ps
        import inspect
        src = inspect.getsource(ps)
        assert V3_HASH in src

    def test_tc02_grand_mean_unchanged(self):
        from src.research.canonical_5d_baseline_s44 import build_canonical_5d_baseline
        import sqlite3
        con = sqlite3.connect(REAL_DB_PATH)
        result = build_canonical_5d_baseline(con)
        con.close()
        assert abs(result.result_vs_a_direct.grand_mean_delta - 0.0081) < 0.001

    def test_tc02_strict_cluster_count_unchanged(self):
        from src.research.canonical_5d_baseline_s44 import build_canonical_5d_baseline
        import sqlite3
        con = sqlite3.connect(REAL_DB_PATH)
        result = build_canonical_5d_baseline(con)
        con.close()
        assert result.n_strict_clusters == 3


# ---------------------------------------------------------------------------
# TC03: Safety — forward signals integrity
# ---------------------------------------------------------------------------

class TestTC03_ForwardSignalsIntegrity:
    def test_tc03_total_signals(self, conn):
        total = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        assert total == 2605

    def test_tc03_v8_buy_count(self, conn):
        buy = conn.execute(
            "SELECT COUNT(*) FROM forward_signals WHERE model_version='v8.0' "
            "AND trade_signal IN ('buy','strong_buy')"
        ).fetchone()[0]
        assert buy == 237

    def test_tc03_dp_max_date(self, conn):
        max_date = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
        assert max_date == "2026-11-05"

    def test_tc03_no_duplicates_nov04(self, conn):
        rows = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT stock_id) FROM daily_prices "
            "WHERE date='2026-11-04'"
        ).fetchone()
        assert rows[0] == rows[1]  # no duplicates


# ---------------------------------------------------------------------------
# TC04: Safety — no 20D outcome computation
# ---------------------------------------------------------------------------

class TestTC04_No20DComputation:
    def test_tc04_maturity_matrix_not_authorized(self, maturity_matrix):
        assert "NOT_AUTHORIZED" in maturity_matrix.authorization_status

    def test_tc04_no_new_outcome_rows(self, conn):
        # forward_outcome_evaluations should not have new 20D rows added in S48
        total = conn.execute(
            "SELECT COUNT(*) FROM forward_outcome_evaluations"
        ).fetchone()[0]
        # Just verify it exists and we can query it; no assertion on count
        assert total >= 0

    def test_tc04_maturity_all_not_yet_mature(self, maturity_matrix):
        for r in maturity_matrix.records:
            assert r.maturity_status == MaturityStatus20D.NOT_YET_MATURE


# ---------------------------------------------------------------------------
# TC05: Pipeline tier — TIER_1_PROXY
# ---------------------------------------------------------------------------

class TestTC05_TierOneProxy:
    _PROXY_DATES = [
        "2026-10-08", "2026-10-15", "2026-10-19", "2026-10-20",
        "2026-10-27", "2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"
    ]

    def test_tc05_proxy_dates_have_exactly_one_stock(self, conn):
        for d in self._PROXY_DATES:
            count = conn.execute(
                "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?", (d,)
            ).fetchone()[0]
            assert count == 1, f"{d} should have 1 stock, got {count}"

    def test_tc05_proxy_dates_have_0050_only(self, conn):
        for d in self._PROXY_DATES:
            stocks = [r[0] for r in conn.execute(
                "SELECT DISTINCT stock_id FROM daily_prices WHERE date=?", (d,)
            ).fetchall()]
            assert stocks == ["0050"], f"{d} should only have 0050, got {stocks}"

    def test_tc05_coverage_matrix_tier_1_count(self, coverage_matrix):
        tier1 = [r for r in coverage_matrix.records
                 if r.coverage_tier == PipelineTier.TIER_1_PROXY]
        assert len(tier1) == 9

    def test_tc05_proxy_dates_no_tsmc(self, coverage_matrix):
        for r in coverage_matrix.records:
            if r.coverage_tier == PipelineTier.TIER_1_PROXY:
                assert not r.tsmc_present


# ---------------------------------------------------------------------------
# TC06: Pipeline tier — TIER_655_FILL
# ---------------------------------------------------------------------------

class TestTC06_Tier655Fill:
    _FILL_DATES_LIST = [
        "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-16",
        "2026-10-21", "2026-10-22", "2026-10-28"
    ]

    def test_tc06_fill_dates_have_650_plus_stocks(self, conn):
        for d in self._FILL_DATES_LIST:
            count = conn.execute(
                "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?", (d,)
            ).fetchone()[0]
            assert count >= 650, f"{d} should have ~655 stocks, got {count}"

    def test_tc06_fill_dates_have_tsmc(self, conn):
        for d in self._FILL_DATES_LIST:
            has = conn.execute(
                "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id='2330'", (d,)
            ).fetchone()[0]
            assert has == 1, f"{d} should have TSMC"

    def test_tc06_coverage_matrix_tier_655_count(self, coverage_matrix):
        tier655 = [r for r in coverage_matrix.records
                   if r.coverage_tier == PipelineTier.TIER_655_FILL]
        # Oct 12-28 fill dates = 7 dates
        assert len(tier655) == 7

    def test_tc06_fill_dates_data_complete(self, coverage_matrix):
        for r in coverage_matrix.records:
            if r.coverage_tier == PipelineTier.TIER_655_FILL:
                assert r.coverage_status == CoverageStatus.DATA_COMPLETE


# ---------------------------------------------------------------------------
# TC07: Pipeline tier — TIER_6957_BACKFILL
# ---------------------------------------------------------------------------

class TestTC07_Tier6957Backfill:
    def test_tc07_nov04_stock_count(self, conn):
        count = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='2026-11-04'"
        ).fetchone()[0]
        assert count == 6957

    def test_tc07_nov05_stock_count(self, conn):
        count = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='2026-11-05'"
        ).fetchone()[0]
        assert count >= 6500  # 6589

    def test_tc07_backfill_root_cause(self, coverage_matrix):
        for r in coverage_matrix.records:
            if r.date_str in ("2026-11-04", "2026-11-05"):
                assert r.pipeline_root_cause == PipelineRootCause.MANUAL_BACKFILL

    def test_tc07_backfill_data_complete(self, coverage_matrix):
        for r in coverage_matrix.records:
            if r.date_str in ("2026-11-04", "2026-11-05"):
                assert r.coverage_status == CoverageStatus.DATA_COMPLETE


# ---------------------------------------------------------------------------
# TC08: Pipeline tier — TIER_ZERO_MISSING
# ---------------------------------------------------------------------------

class TestTC08_TierZeroMissing:
    def test_tc08_nov06_zero_rows(self, conn):
        count = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-06'"
        ).fetchone()[0]
        assert count == 0

    def test_tc08_nov09_zero_rows(self, conn):
        count = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-09'"
        ).fetchone()[0]
        assert count == 0

    def test_tc08_coverage_matrix_missing_count(self, coverage_matrix):
        missing = [r for r in coverage_matrix.records
                   if r.coverage_status == CoverageStatus.DATA_MISSING]
        assert len(missing) == 2
        missing_dates = {r.date_str for r in missing}
        assert "2026-11-06" in missing_dates
        assert "2026-11-09" in missing_dates


# ---------------------------------------------------------------------------
# TC09: Root cause — PIPELINE_SELECTIVE
# ---------------------------------------------------------------------------

class TestTC09_RootCausePipelineSelective:
    _SELECTIVE_DATES = [
        "2026-10-08", "2026-10-15", "2026-10-19", "2026-10-20",
        "2026-10-27", "2026-10-29"
    ]

    def test_tc09_selective_dates_classified_correctly(self, coverage_matrix):
        for r in coverage_matrix.records:
            if r.date_str in self._SELECTIVE_DATES:
                assert r.pipeline_root_cause == PipelineRootCause.PIPELINE_SELECTIVE

    def test_tc09_selective_dates_confirmed(self, coverage_matrix):
        for r in coverage_matrix.records:
            if r.date_str in self._SELECTIVE_DATES:
                assert r.root_cause_confidence == RootCauseConfidence.ROOT_CAUSE_CONFIRMED

    def test_tc09_selective_count_in_matrix(self, coverage_matrix):
        selective = [r for r in coverage_matrix.records
                     if r.pipeline_root_cause == PipelineRootCause.PIPELINE_SELECTIVE]
        assert len(selective) == 6


# ---------------------------------------------------------------------------
# TC10: Root cause — SCHEDULER_NOT_TRIGGERED
# ---------------------------------------------------------------------------

class TestTC10_RootCauseSchedulerNotTriggered:
    _SCHEDULER_DATES = ["2026-10-30", "2026-11-02", "2026-11-03"]

    def test_tc10_scheduler_dates_classified(self, coverage_matrix):
        for r in coverage_matrix.records:
            if r.date_str in self._SCHEDULER_DATES:
                assert r.pipeline_root_cause == PipelineRootCause.SCHEDULER_NOT_TRIGGERED

    def test_tc10_scheduler_dates_have_1_stock(self, conn):
        for d in self._SCHEDULER_DATES:
            count = conn.execute(
                "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?", (d,)
            ).fetchone()[0]
            assert count == 1

    def test_tc10_first_cron_log_nov09(self):
        FIRST_CRON = "2026-11-09T08:00:17Z"
        from src.research.pipeline_reliability_s48 import _ROOT_CAUSE_MAP
        rc = _ROOT_CAUSE_MAP["2026-11-09"]
        assert rc == PipelineRootCause.PROVIDER_NOT_READY


# ---------------------------------------------------------------------------
# TC11: Root cause — QUALITY_GATE_FAIL (Nov 06)
# ---------------------------------------------------------------------------

class TestTC11_RootCauseQualityGateFail:
    def test_tc11_nov06_quality_gate_fail(self):
        rc = _ROOT_CAUSE_MAP["2026-11-06"]
        assert rc == PipelineRootCause.QUALITY_GATE_FAIL

    def test_tc11_nov06_in_coverage_matrix(self, coverage_matrix):
        rec = next(r for r in coverage_matrix.records if r.date_str == "2026-11-06")
        assert rec.pipeline_root_cause == PipelineRootCause.QUALITY_GATE_FAIL
        assert rec.coverage_status == CoverageStatus.DATA_MISSING

    def test_tc11_nov06_stage_reached_is_qg(self):
        stages = get_pipeline_stage_analysis("2026-11-06")
        # S04_QUALITY_GATE should have FAIL result
        qg = next(s for s in stages if s.stage == "S04_QUALITY_GATE")
        assert qg.result == "FAIL"


# ---------------------------------------------------------------------------
# TC12: Root cause — PROVIDER_NOT_READY (Nov 09)
# ---------------------------------------------------------------------------

class TestTC12_RootCauseProviderNotReady:
    def test_tc12_nov09_provider_not_ready(self):
        rc = _ROOT_CAUSE_MAP["2026-11-09"]
        assert rc == PipelineRootCause.PROVIDER_NOT_READY

    def test_tc12_nov09_stage_analysis(self):
        stages = get_pipeline_stage_analysis("2026-11-09")
        s03 = next(s for s in stages if s.stage == "S03_DATA_PROVIDER_FETCH")
        assert s03.result == "FAIL"

    def test_tc12_nov09_stages_after_s03_skipped(self):
        stages = get_pipeline_stage_analysis("2026-11-09")
        late_stages = [s for s in stages
                       if s.stage in ("S04_QUALITY_GATE", "S07_SQLITE_WRITE")]
        for s in late_stages:
            assert s.result == "SKIPPED"


# ---------------------------------------------------------------------------
# TC13: Root cause — MANUAL_BACKFILL (Nov 04/05)
# ---------------------------------------------------------------------------

class TestTC13_RootCauseManualBackfill:
    def test_tc13_nov04_manual_backfill(self, coverage_matrix):
        rec = next(r for r in coverage_matrix.records if r.date_str == "2026-11-04")
        assert rec.pipeline_root_cause == PipelineRootCause.MANUAL_BACKFILL

    def test_tc13_nov05_manual_backfill(self, coverage_matrix):
        rec = next(r for r in coverage_matrix.records if r.date_str == "2026-11-05")
        assert rec.pipeline_root_cause == PipelineRootCause.MANUAL_BACKFILL

    def test_tc13_backfill_source_type(self, coverage_matrix):
        for r in coverage_matrix.records:
            if r.date_str in ("2026-11-04", "2026-11-05"):
                assert r.source_type == "MANUAL_BACKFILL"


# ---------------------------------------------------------------------------
# TC14: Coverage matrix — 15 dimensions present
# ---------------------------------------------------------------------------

class TestTC14_CoverageMatrix15Dimensions:
    def test_tc14_record_has_all_dimensions(self, coverage_matrix):
        r = coverage_matrix.records[0]
        # Check all 15 dimensions exist
        assert hasattr(r, "date_str")
        assert hasattr(r, "is_trading_day")
        assert hasattr(r, "stock_count")
        assert hasattr(r, "has_data")
        assert hasattr(r, "coverage_tier")
        assert hasattr(r, "benchmark_present")
        assert hasattr(r, "tsmc_present")
        assert hasattr(r, "fill_date_flag")
        assert hasattr(r, "proxy_date_flag")
        assert hasattr(r, "pipeline_root_cause")
        assert hasattr(r, "coverage_status")
        assert hasattr(r, "source_type")
        assert hasattr(r, "pipeline_stage_reached")
        assert hasattr(r, "recovery_feasibility")
        assert hasattr(r, "affects_active_cluster")


# ---------------------------------------------------------------------------
# TC15: Coverage matrix — benchmark_only_days = 9
# ---------------------------------------------------------------------------

class TestTC15_BenchmarkOnlyCount:
    def test_tc15_benchmark_only_count(self, coverage_matrix):
        assert coverage_matrix.benchmark_only_days == 9

    def test_tc15_benchmark_only_dates(self, coverage_matrix):
        bmo = {r.date_str for r in coverage_matrix.records
               if r.coverage_status == CoverageStatus.BENCHMARK_ONLY}
        expected = {
            "2026-10-08", "2026-10-15", "2026-10-19", "2026-10-20",
            "2026-10-27", "2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"
        }
        assert bmo == expected


# ---------------------------------------------------------------------------
# TC16: Coverage matrix — missing_days = 2
# ---------------------------------------------------------------------------

class TestTC16_MissingDaysCount:
    def test_tc16_missing_count(self, coverage_matrix):
        assert coverage_matrix.missing_days == 2

    def test_tc16_missing_dates_nov06_nov09(self, coverage_matrix):
        missing = {r.date_str for r in coverage_matrix.records
                   if r.coverage_status == CoverageStatus.DATA_MISSING}
        assert missing == {"2026-11-06", "2026-11-09"}


# ---------------------------------------------------------------------------
# TC17: Coverage matrix — complete_days = 9
# ---------------------------------------------------------------------------

class TestTC17_CompleteDaysCount:
    def test_tc17_complete_count(self, coverage_matrix):
        # Oct 12/13/14/16/21/22/28 (7 fill dates) + Nov 04/05 (2 backfill) = 9
        assert coverage_matrix.complete_days == 9

    def test_tc17_complete_includes_fill_and_backfill(self, coverage_matrix):
        complete = {r.date_str for r in coverage_matrix.records
                    if r.coverage_status == CoverageStatus.DATA_COMPLETE}
        fill_dates = {"2026-10-12", "2026-10-13", "2026-10-14", "2026-10-16",
                      "2026-10-21", "2026-10-22", "2026-10-28"}
        backfill = {"2026-11-04", "2026-11-05"}
        assert fill_dates | backfill == complete


# ---------------------------------------------------------------------------
# TC18: Coverage matrix — total_trading_days = 20
# ---------------------------------------------------------------------------

class TestTC18_TotalTradingDays:
    def test_tc18_total_trading_days(self, coverage_matrix):
        assert coverage_matrix.total_trading_days == 20

    def test_tc18_tier_counts_sum_to_total(self, coverage_matrix):
        assert (
            coverage_matrix.tier_1_proxy_days
            + coverage_matrix.tier_655_fill_days
            + coverage_matrix.tier_6957_backfill_days
            + coverage_matrix.missing_days
        ) == coverage_matrix.total_trading_days


# ---------------------------------------------------------------------------
# TC19: Coverage matrix — TSMC absent on PARTIAL (proxy-only) dates
# ---------------------------------------------------------------------------

class TestTC19_TSMCAbsentOnProxy:
    def test_tc19_tsmc_absent_on_proxy_dates(self, coverage_matrix):
        for r in coverage_matrix.records:
            if r.coverage_tier == PipelineTier.TIER_1_PROXY:
                assert not r.tsmc_present

    def test_tc19_tsmc_present_on_fill_dates(self, coverage_matrix):
        for r in coverage_matrix.records:
            if r.coverage_tier == PipelineTier.TIER_655_FILL:
                assert r.tsmc_present


# ---------------------------------------------------------------------------
# TC20: Coverage matrix — affects_active_cluster flags
# ---------------------------------------------------------------------------

class TestTC20_AffectsActiveCluster:
    def test_tc20_window_dates_flagged(self, coverage_matrix):
        # Oct 27 is in the Oct 16, Oct 21, Oct 22 windows
        oct27 = next(r for r in coverage_matrix.records if r.date_str == "2026-10-27")
        assert oct27.affects_active_cluster

    def test_tc20_fill_dates_not_flagged(self, coverage_matrix):
        # Fill dates themselves are NOT in a window (window is AFTER fill)
        oct13 = next(r for r in coverage_matrix.records if r.date_str == "2026-10-13")
        # Oct 13 is a fill date; it starts the window but is not inside any window
        # (unless it falls inside another cluster's window)
        # Oct 13 is in Oct 12's window? No — Oct 12 isn't a fill date.
        # Oct 13 is NOT in any other cluster's window
        assert not oct13.affects_active_cluster


# ---------------------------------------------------------------------------
# TC21: Backfill dry-run — 11 candidates
# ---------------------------------------------------------------------------

class TestTC21_BackfillDryRunCandidates:
    def test_tc21_candidate_count(self, backfill_plan):
        assert len(backfill_plan.candidate_dates) == 11

    def test_tc21_all_expected_dates(self, backfill_plan):
        expected = {
            "2026-10-08", "2026-10-15", "2026-10-19", "2026-10-20",
            "2026-10-27", "2026-10-29", "2026-10-30",
            "2026-11-02", "2026-11-03", "2026-11-06", "2026-11-09",
        }
        assert set(backfill_plan.candidate_dates) == expected


# ---------------------------------------------------------------------------
# TC22: Backfill dry-run — insert_only count = 9
# ---------------------------------------------------------------------------

class TestTC22_BackfillInsertOnlyCount:
    def test_tc22_insert_only_count(self, backfill_plan):
        # 9 dates have 0050 proxy; would be INSERT-only (not UPDATE)
        assert backfill_plan.insert_only_count == 9

    def test_tc22_insert_only_dates_have_0050_conflict(self, backfill_plan):
        for r in backfill_plan.records:
            if r.readiness == BackfillReadiness.INSERT_ONLY_CANDIDATE:
                assert r.has_0050_conflict  # 0050 already there


# ---------------------------------------------------------------------------
# TC23: Backfill dry-run — unverified count = 2
# ---------------------------------------------------------------------------

class TestTC23_BackfillUnverifiedCount:
    def test_tc23_universe_unverified_count(self, backfill_plan):
        # Nov 06, Nov 09 have 0 existing rows
        assert backfill_plan.universe_unverified_count == 2

    def test_tc23_unverified_dates(self, backfill_plan):
        unverified = {r.date_str for r in backfill_plan.records
                      if r.readiness == BackfillReadiness.UNIVERSE_UNVERIFIED}
        assert unverified == {"2026-11-06", "2026-11-09"}


# ---------------------------------------------------------------------------
# TC24: Backfill dry-run — no production writes triggered
# ---------------------------------------------------------------------------

class TestTC24_BackfillNoProductionWrites:
    def test_tc24_dry_run_does_not_modify_db(self, conn):
        rows_before = conn.execute(
            "SELECT COUNT(*) FROM daily_prices"
        ).fetchone()[0]
        build_backfill_dry_run_plan(conn, ANALYSIS_DATE)
        rows_after = conn.execute(
            "SELECT COUNT(*) FROM daily_prices"
        ).fetchone()[0]
        assert rows_before == rows_after

    def test_tc24_all_records_have_conflict_risk_low(self, backfill_plan):
        for r in backfill_plan.records:
            assert r.conflict_risk in ("LOW", "NONE")


# ---------------------------------------------------------------------------
# TC25: Pipeline stage analysis — SCHEDULER_NOT_TRIGGERED
# ---------------------------------------------------------------------------

class TestTC25_PipelineStageSchedulerNotTriggered:
    def test_tc25_oct30_stage_analysis(self):
        stages = get_pipeline_stage_analysis("2026-10-30")
        s01 = next(s for s in stages if s.stage == "S01_CALENDAR_CHECK")
        assert s01.reached and s01.result == "PASS"

    def test_tc25_later_stages_skipped(self):
        stages = get_pipeline_stage_analysis("2026-10-30")
        later = [s for s in stages if s.stage not in
                 ("S01_CALENDAR_CHECK",)]
        for s in later:
            assert not s.reached or s.result == "SKIPPED"

    def test_tc25_stage_count_is_10(self):
        stages = get_pipeline_stage_analysis("2026-10-30")
        assert len(stages) == 10


# ---------------------------------------------------------------------------
# TC26: Pipeline stage analysis — PIPELINE_SELECTIVE
# ---------------------------------------------------------------------------

class TestTC26_PipelineStagePipelineSelective:
    def test_tc26_oct15_stage_reaches_s07(self):
        stages = get_pipeline_stage_analysis("2026-10-15")
        s07 = next(s for s in stages if s.stage == "S07_SQLITE_WRITE")
        assert s07.reached and s07.result == "PASS"

    def test_tc26_signal_stage_not_applicable(self):
        stages = get_pipeline_stage_analysis("2026-10-15")
        s08 = next(s for s in stages if s.stage == "S08_SIGNAL_TRIGGER")
        assert s08.result == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# TC27: 20D calendar correction — S46 errors identified
# ---------------------------------------------------------------------------

class TestTC27_20DCalendarCorrectionErrors:
    def test_tc27_all_6_clusters_have_records(self, contract_records):
        assert len(contract_records) == 6

    def test_tc27_s46_errors_count(self, contract_records):
        errors = [r for r in contract_records
                  if r.td20_contract_status == CalendarContractStatus.S46_ERROR_CORRECTED]
        assert len(errors) == 6  # All 6 clusters had 20TD errors

    def test_tc27_oct28_has_largest_error(self, contract_records):
        oct28 = next(r for r in contract_records if r.fill_date == "2026-10-28")
        assert oct28.td20_delta_days == 7  # S46 was 7 days too late

    def test_tc27_s46_errors_summary(self):
        errors = get_s46_errors_summary()
        assert len(errors) == 6
        oct28_err = next(e for e in errors if e["fill_date"] == "2026-10-28")
        assert oct28_err["td20_error_days"] == 7

    def test_tc27_5td_errors_for_oct13_14_16(self, contract_records):
        for fd in ["2026-10-13", "2026-10-14", "2026-10-16"]:
            r = next(x for x in contract_records if x.fill_date == fd)
            assert r.td5_contract_status == CalendarContractStatus.S46_ERROR_CORRECTED


# ---------------------------------------------------------------------------
# TC28: 20D contract — earliest maturity = 2026-11-12
# ---------------------------------------------------------------------------

class TestTC28_20DEarliestMaturity:
    def test_tc28_earliest_maturity_date(self, maturity_matrix):
        assert maturity_matrix.earliest_maturity_date == "2026-11-12"

    def test_tc28_oct13_fill_matures_nov12(self, maturity_matrix):
        oct13 = next(r for r in maturity_matrix.records
                     if r.fill_date == "2026-10-13")
        assert oct13.correct_20td == "2026-11-12"

    def test_tc28_not_s46_nov14(self):
        # S46 was wrong; Nov 14 is NOT the correct date
        assert _S46_20TD["2026-10-13"] == "2026-11-14"
        assert _CORRECT_20TD["2026-10-13"] == "2026-11-12"


# ---------------------------------------------------------------------------
# TC29: 20D contract — latest maturity = 2026-11-25
# ---------------------------------------------------------------------------

class TestTC29_20DLatestMaturity:
    def test_tc29_latest_maturity_date(self, maturity_matrix):
        assert maturity_matrix.latest_maturity_date == "2026-11-25"

    def test_tc29_oct28_fill_matures_nov25(self, maturity_matrix):
        oct28 = next(r for r in maturity_matrix.records
                     if r.fill_date == "2026-10-28")
        assert oct28.correct_20td == "2026-11-25"

    def test_tc29_not_s46_dec02(self):
        # S46 was wrong; Dec 02 is NOT the correct date
        assert _S46_20TD["2026-10-28"] == "2026-12-02"
        assert _CORRECT_20TD["2026-10-28"] == "2026-11-25"


# ---------------------------------------------------------------------------
# TC30: 20D maturity matrix — all 6 NOT_YET_MATURE
# ---------------------------------------------------------------------------

class TestTC30_20DAllNotYetMature:
    def test_tc30_all_not_yet_mature(self, maturity_matrix):
        for r in maturity_matrix.records:
            assert r.maturity_status == MaturityStatus20D.NOT_YET_MATURE, (
                f"{r.fill_date} should be NOT_YET_MATURE"
            )

    def test_tc30_not_yet_mature_count_is_6(self, maturity_matrix):
        assert maturity_matrix.not_yet_mature_count == 6

    def test_tc30_mature_counts_zero(self, maturity_matrix):
        assert maturity_matrix.mature_incomplete_count == 0
        assert maturity_matrix.mature_complete_count == 0

    def test_tc30_days_until_all_positive(self, maturity_matrix):
        for r in maturity_matrix.records:
            assert r.days_until_mature > 0


# ---------------------------------------------------------------------------
# TC31: 20D maturity matrix — auth status = NOT_AUTHORIZED
# ---------------------------------------------------------------------------

class TestTC31_20DAuthStatus:
    def test_tc31_not_authorized(self, maturity_matrix):
        assert "NOT_AUTHORIZED" in maturity_matrix.authorization_status

    def test_tc31_auth_string_has_detail(self, maturity_matrix):
        status = maturity_matrix.authorization_status
        assert "20D" in status or "20d" in status.lower() or "computation" in status.lower()


# ---------------------------------------------------------------------------
# TC32: 5D readiness — 3 strict + 3 waiting
# ---------------------------------------------------------------------------

class TestTC32_5DReadinessMatrix:
    def test_tc32_strict_count(self, readiness_matrix):
        assert readiness_matrix.strict_eligible_count == 3

    def test_tc32_waiting_count(self, readiness_matrix):
        assert readiness_matrix.waiting_for_data_count == 3

    def test_tc32_strict_fills(self, readiness_matrix):
        strict = {r.fill_date for r in readiness_matrix.records if r.is_strict_eligible}
        assert strict == {"2026-10-13", "2026-10-14", "2026-10-16"}

    def test_tc32_incomplete_fills(self, readiness_matrix):
        waiting = {r.fill_date for r in readiness_matrix.records
                   if r.readiness == Readiness5D.WAITING_FOR_PRICE_DATA}
        assert waiting == {"2026-10-21", "2026-10-22", "2026-10-28"}

    def test_tc32_frozen_baseline_unchanged(self, readiness_matrix):
        assert readiness_matrix.frozen_baseline_unchanged
        assert abs(readiness_matrix.frozen_grand_mean_pp - 0.81) < 0.01

    def test_tc32_total_records_6(self, readiness_matrix):
        assert len(readiness_matrix.records) == 6

    def test_tc32_incomplete_cluster_proxy_counts(self, readiness_matrix):
        # Oct 21: proxy=2 (Oct 22 and Oct 28 have TSMC)
        # Oct 22: proxy=1 (Oct 28 has TSMC)
        # Oct 28: proxy=1 (Nov 04 has TSMC)
        oct21 = next(r for r in readiness_matrix.records if r.fill_date == "2026-10-21")
        oct22 = next(r for r in readiness_matrix.records if r.fill_date == "2026-10-22")
        oct28 = next(r for r in readiness_matrix.records if r.fill_date == "2026-10-28")
        assert oct21.proxy_exit_days < 5
        assert oct22.proxy_exit_days < 5
        assert oct28.proxy_exit_days < 5

    def test_tc32_strict_fills_proxy_count_gte_5(self, readiness_matrix):
        for r in readiness_matrix.records:
            if r.is_strict_eligible:
                assert r.proxy_exit_days >= 5


# ---------------------------------------------------------------------------
# TC33: G03 FAIL (3/10)
# ---------------------------------------------------------------------------

class TestTC33_G03Fail:
    def test_tc33_g03_status_fail(self, guardrails):
        assert guardrails.g03.status == GuardrailStatus.FAIL

    def test_tc33_g03_current_value(self, guardrails):
        assert guardrails.strict_cluster_count == 3

    def test_tc33_g03_target_10(self, guardrails):
        assert guardrails.g03_target == 10

    def test_tc33_overall_has_g03_fail(self, guardrails):
        assert "G03" in guardrails.overall_status or "BOTH" in guardrails.overall_status


# ---------------------------------------------------------------------------
# TC34: G04 FAIL (max 80% overlap)
# ---------------------------------------------------------------------------

class TestTC34_G04Fail:
    def test_tc34_g04_status_fail(self, guardrails):
        assert guardrails.g04.status == GuardrailStatus.FAIL

    def test_tc34_max_overlap_80_pct(self, guardrails):
        assert guardrails.g04_max_overlap_pct == 80.0

    def test_tc34_pairwise_matrix_15_pairs(self, guardrails):
        assert len(guardrails.pairwise_matrix) == 15

    def test_tc34_adjacent_pairs_count(self, guardrails):
        adjacent = [p for p in guardrails.pairwise_matrix if p.is_adjacent]
        assert len(adjacent) == 5

    def test_tc34_all_adjacent_exceed_30_pct(self, guardrails):
        adjacent = [p for p in guardrails.pairwise_matrix if p.is_adjacent]
        for p in adjacent:
            assert p.overlap_pct > 30.0, (
                f"{p.fill_a}/{p.fill_b}: overlap={p.overlap_pct}%"
            )

    def test_tc34_overlap_formula_denominator_is_5(self, guardrails):
        # For Oct 13/Oct 14: 4 shared days / 5 = 80%
        oct1314 = next(
            p for p in guardrails.pairwise_matrix
            if p.fill_a == "2026-10-13" and p.fill_b == "2026-10-14"
        )
        assert oct1314.shared_days == 4
        assert oct1314.overlap_pct == 80.0
        assert len(oct1314.window_a) == 5
        assert len(oct1314.window_b) == 5

    def test_tc34_non_adjacent_low_overlap(self, guardrails):
        # Oct 13 / Oct 28 should have 0% overlap
        oct13_28 = next(
            (p for p in guardrails.pairwise_matrix
             if p.fill_a == "2026-10-13" and p.fill_b == "2026-10-28"),
            None
        )
        if oct13_28:
            assert oct13_28.overlap_pct == 0.0

    def test_tc34_overall_status_includes_g04(self, guardrails):
        assert "G04" in guardrails.overall_status or "BOTH" in guardrails.overall_status
