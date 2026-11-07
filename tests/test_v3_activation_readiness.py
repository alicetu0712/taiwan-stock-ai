"""
tests/test_v3_activation_readiness.py — V3 Shadow Activation Readiness Tests
AR-01 to AR-40

RESEARCH ONLY — all DB writes use temporary in-memory SQLite.
No production table writes in any test.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from unittest.mock import patch

import pytest

from src.research.v3_activation_readiness import (
    TPEX_PROXY_MIN,
    TWSE_PROXY_MIN,
    ActivationVerdict,
    CronAcceptanceStatus,
    MarketGateVerdict,
    ReadonlyProductionAdapter,
    RequirementStatus,
    build_activation_readiness_report,
    build_cron_acceptance_report,
    build_market_data_gate_report,
    run_capture_outcome_isolation_test,
)
from src.research.v3_prospective_shadow import (
    MIN_COVERED_STOCKS,
    V3_PARAMETER_HASH,
    DataGateStatus,
    OutcomeMaturity,
    check_0050_gate,
    check_capture_window_gate,
    check_look_ahead_gate,
    check_market_coverage_gate,
    check_outcome_maturity,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_full_market_db(trade_date: str = "2026-11-06") -> sqlite3.Connection:
    """In-memory DB with 0050 + 5002 non-0050 stocks on trade_date."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE daily_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT, date TEXT, open REAL, high REAL, low REAL,
            close REAL, volume REAL, amount REAL, change_pct REAL
        );
        CREATE TABLE stocks (
            stock_id TEXT PRIMARY KEY, name TEXT, market TEXT
        );
    """)
    conn.execute(
        "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume, amount, change_pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("0050", trade_date, 99.0, 100.0, 98.0, 99.5, 50000.0, 4975000.0, -0.5)
    )
    for i in range(5002):
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume, amount, change_pct) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"{2000 + i}", trade_date, 50.0, 51.0, 49.0, 50.5, 1000.0, 50500.0, 0.0)
        )
    conn.commit()
    return conn


def _make_benchmark_only_db(trade_date: str = "2026-11-06") -> sqlite3.Connection:
    """In-memory DB with 0050 only (no non-0050 stocks)."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE daily_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT, date TEXT, open REAL, high REAL, low REAL,
            close REAL, volume REAL, amount REAL, change_pct REAL
        );
        CREATE TABLE stocks (stock_id TEXT PRIMARY KEY, name TEXT, market TEXT);
    """)
    conn.execute(
        "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume, amount, change_pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("0050", trade_date, 99.0, 100.0, 98.0, 99.5, 50000.0, 4975000.0, -0.5)
    )
    conn.commit()
    return conn


def _make_empty_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE daily_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT, date TEXT, open REAL, high REAL, low REAL,
            close REAL, volume REAL, amount REAL, change_pct REAL
        );
        CREATE TABLE stocks (stock_id TEXT PRIMARY KEY, name TEXT, market TEXT);
    """)
    return conn


def _make_twse_only_db(trade_date: str = "2026-11-06") -> sqlite3.Connection:
    """1800 non-0050 stocks (TWSE proxy passes, TPEx proxy fails)."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE daily_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT, date TEXT, open REAL, high REAL, low REAL,
            close REAL, volume REAL, amount REAL, change_pct REAL
        );
        CREATE TABLE stocks (stock_id TEXT PRIMARY KEY, name TEXT, market TEXT);
    """)
    conn.execute(
        "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume, amount, change_pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("0050", trade_date, 99.0, 100.0, 98.0, 99.5, 50000.0, 4975000.0, -0.5)
    )
    for i in range(1800):
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume, amount, change_pct) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"{2000 + i}", trade_date, 50.0, 51.0, 49.0, 50.5, 1000.0, 50500.0, 0.0)
        )
    conn.commit()
    return conn


def _make_readonly_adapter_from_conn(conn: sqlite3.Connection) -> "ReadonlyProductionAdapter":
    """Create a ReadonlyProductionAdapter wrapping an existing connection (for testing)."""
    adapter = ReadonlyProductionAdapter.__new__(ReadonlyProductionAdapter)
    adapter._path = ":memory:"
    adapter._conn = conn
    adapter._conn.row_factory = sqlite3.Row
    return adapter


# ── AR-01..08: Data Integrity Gates ───────────────────────────────────────────

def test_AR01_0050_gate_pass():
    """AR-01: 0050 gate PASS when data present for trade_date."""
    conn = _make_full_market_db("2026-11-06")
    r = check_0050_gate(conn, "2026-11-06")
    assert r.status == DataGateStatus.PASS
    assert r.stock_count == 1
    conn.close()


def test_AR02_0050_gate_fail_missing():
    """AR-02: 0050 gate FAIL when no 0050 data for trade_date."""
    conn = _make_empty_db()
    r = check_0050_gate(conn, "2026-11-06")
    assert r.status == DataGateStatus.FAIL_NO_0050
    assert r.stock_count == 0
    conn.close()


def test_AR03_market_coverage_pass_full_market():
    """AR-03: Market coverage gate PASS with full TWSE+TPEx data."""
    conn = _make_full_market_db("2026-11-06")
    r = check_market_coverage_gate(conn, "2026-11-06")
    assert r.status == DataGateStatus.PASS
    assert r.stock_count >= MIN_COVERED_STOCKS
    conn.close()


def test_AR04_market_coverage_fail_twse_only():
    """AR-04: Market coverage gate FAIL with TWSE-only data (1800 stocks < 5000)."""
    conn = _make_twse_only_db("2026-11-06")
    r = check_market_coverage_gate(conn, "2026-11-06")
    assert r.status == DataGateStatus.FAIL_PARTIAL_MARKET
    assert r.stock_count == 1800
    conn.close()


def test_AR05_market_coverage_fail_no_data():
    """AR-05: Market coverage gate FAIL when no non-0050 stocks present."""
    conn = _make_benchmark_only_db("2026-11-06")
    r = check_market_coverage_gate(conn, "2026-11-06")
    assert r.status == DataGateStatus.FAIL_PARTIAL_MARKET
    assert r.stock_count == 0
    conn.close()


def test_AR06_look_ahead_gate_pass():
    """AR-06: Look-ahead gate PASS when data_as_of <= trade_date."""
    r = check_look_ahead_gate("2026-11-06", "2026-11-06")
    assert r.status == DataGateStatus.PASS


def test_AR07_look_ahead_gate_fail():
    """AR-07: Look-ahead gate FAIL when data_as_of > trade_date (look-ahead detected)."""
    r = check_look_ahead_gate("2026-11-07", "2026-11-06")
    assert r.status == DataGateStatus.FAIL_LOOK_AHEAD
    assert "LOOK-AHEAD" in r.detail.upper()


def test_AR08_stale_data_capture_window():
    """AR-08: Capture window gate FAIL when captured on a later day."""
    r = check_capture_window_gate("2026-11-06", "2026-11-07T14:00:00+08:00")
    assert r.status == DataGateStatus.FAIL_STALE_DATA
    assert "LATE_CAPTURE" in r.detail


# ── AR-09..13: Cron Evidence ───────────────────────────────────────────────────

def test_AR09_cron_trigger_source_cannot_distinguish_external():
    """AR-09: trigger_source='cron_scheduled' set by isatty() — not proof of OS scheduler."""
    from src.research.v3_activation_readiness import build_cron_acceptance_report
    # Build with no cron log and no prospective writes
    with patch("src.research.v3_activation_readiness._STATE_FILE") as mock_state:
        mock_state.exists.return_value = True
        mock_state.read_text.return_value = json.dumps({
            "trigger_source": "cron_scheduled",
            "status": "BLOCKED_PARTIAL_MARKET",
            "run_at": "2026-11-05T10:28:50.814302+00:00",
        })
        with patch("src.research.v3_activation_readiness._CRON_LOG") as mock_log:
            mock_log.exists.return_value = False
            mock_log.stat.return_value.st_size = 0
            conn = sqlite3.connect(":memory:")
            conn.executescript("""
                CREATE TABLE hybrid_forward_decision (
                    id INTEGER PRIMARY KEY, capture_classification TEXT
                );
            """)
            conn.row_factory = sqlite3.Row
            adapter = _make_readonly_adapter_from_conn(conn)
            report = build_cron_acceptance_report(adapter)
            assert report.state_file_trigger_source == "cron_scheduled"
            assert not report.has_external_trigger_evidence
            assert report.acceptance_status in (
                CronAcceptanceStatus.PENDING, CronAcceptanceStatus.PENDING_SCHEDULED_WINDOW
            )
            conn.close()


def test_AR10_cron_pending_scheduled_window_before_1600():
    """AR-10: CRON_ACCEPTANCE_PENDING_SCHEDULED_WINDOW when Taiwan time < 16:00."""
    import pytz
    taiwan_tz = pytz.timezone("Asia/Taipei")
    before_cron = datetime(2026, 11, 6, 13, 0, 0, tzinfo=taiwan_tz)
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE hybrid_forward_decision (
            id INTEGER PRIMARY KEY, capture_classification TEXT
        );
    """)
    conn.row_factory = sqlite3.Row
    adapter = _make_readonly_adapter_from_conn(conn)
    with patch("src.research.v3_activation_readiness._STATE_FILE") as mock_state, \
         patch("src.research.v3_activation_readiness._CRON_LOG") as mock_log:
        mock_state.exists.return_value = False
        mock_log.exists.return_value = False
        report = build_cron_acceptance_report(adapter, current_taiwan_time=before_cron)
    assert report.acceptance_status == CronAcceptanceStatus.PENDING_SCHEDULED_WINDOW
    assert "16:00" in report.scheduled_window_note
    conn.close()


def test_AR11_cron_acceptance_pass_with_prospective_writes():
    """AR-11: CRON_ACCEPTANCE_PASS when at least one PROSPECTIVE decision exists."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE hybrid_forward_decision (
            id INTEGER PRIMARY KEY, capture_classification TEXT
        );
        INSERT INTO hybrid_forward_decision (capture_classification) VALUES ('PROSPECTIVE');
    """)
    conn.row_factory = sqlite3.Row
    adapter = _make_readonly_adapter_from_conn(conn)
    with patch("src.research.v3_activation_readiness._STATE_FILE") as mock_state, \
         patch("src.research.v3_activation_readiness._CRON_LOG") as mock_log:
        mock_state.exists.return_value = False
        mock_log.exists.return_value = False
        report = build_cron_acceptance_report(adapter)
    assert report.acceptance_status == CronAcceptanceStatus.PASS
    assert report.has_prospective_writes
    assert report.prospective_write_count == 1
    conn.close()


def test_AR12_cron_log_missing_means_no_external_trigger():
    """AR-12: hybrid_cron.log absent → no evidence of external cron invocation."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE hybrid_forward_decision (
            id INTEGER PRIMARY KEY, capture_classification TEXT
        );
    """)
    conn.row_factory = sqlite3.Row
    adapter = _make_readonly_adapter_from_conn(conn)
    with patch("src.research.v3_activation_readiness._STATE_FILE") as mock_state, \
         patch("src.research.v3_activation_readiness._CRON_LOG") as mock_log:
        mock_state.exists.return_value = True
        mock_state.read_text.return_value = json.dumps({
            "trigger_source": "cron_scheduled",
            "status": "BLOCKED_PARTIAL_MARKET",
        })
        mock_log.exists.return_value = False
        mock_log.stat.return_value.st_size = 0
        report = build_cron_acceptance_report(adapter)
    assert not report.has_external_trigger_evidence
    assert not report.cron_log_exists
    conn.close()


def test_AR13_failed_retry_all_blocked():
    """AR-13: Cron PENDING if all runs are BLOCKED_* (no prospective writes)."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE hybrid_forward_decision (
            id INTEGER PRIMARY KEY, capture_classification TEXT
        );
        CREATE TABLE hybrid_forward_run_log (
            id INTEGER PRIMARY KEY, run_id TEXT, trade_date TEXT,
            started_at TEXT, status TEXT, inserted_count INTEGER
        );
        INSERT INTO hybrid_forward_run_log VALUES
            (1, 'abc1', '2026-11-05', '2026-11-05T10:28:50Z', 'BLOCKED_PARTIAL_MARKET', 0);
    """)
    conn.row_factory = sqlite3.Row
    adapter = _make_readonly_adapter_from_conn(conn)
    with patch("src.research.v3_activation_readiness._STATE_FILE") as mock_state, \
         patch("src.research.v3_activation_readiness._CRON_LOG") as mock_log:
        mock_state.exists.return_value = False
        mock_log.exists.return_value = False
        report = build_cron_acceptance_report(adapter)
    assert report.acceptance_status in (
        CronAcceptanceStatus.PENDING, CronAcceptanceStatus.PENDING_SCHEDULED_WINDOW
    )
    assert not report.has_prospective_writes
    conn.close()


# ── AR-14..17: FM11 Related ────────────────────────────────────────────────────

def test_AR14_fm11_post_backfill_state_is_full_market():
    """AR-14: Real DB 2026-11-05 is FULL_MARKET_FRESH after backfill (FM11 fix)."""
    from src.research.full_market_freshness_gate import FreshnessStatus, check_market_freshness
    conn = sqlite3.connect("data/platform.db")
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.FULL_MARKET_FRESH
    assert not r.is_blocked
    assert r.non_benchmark_count >= MIN_COVERED_STOCKS


def test_AR15_benchmark_only_state_is_blocked():
    """AR-15: BENCHMARK_ONLY_UPDATED state is correctly blocked."""
    conn = _make_benchmark_only_db("2026-11-06")
    # Fake check_market_freshness using synthetic DB
    r = check_0050_gate(conn, "2026-11-06")
    assert r.status == DataGateStatus.PASS  # 0050 present
    r2 = check_market_coverage_gate(conn, "2026-11-06")
    assert r2.status == DataGateStatus.FAIL_PARTIAL_MARKET  # non-0050 missing
    conn.close()


def test_AR16_stale_snapshot_test_uses_real_db_state():
    """AR-16: FM11 failure was stale snapshot — not a gate logic regression."""
    # This test documents the FM11 root cause: the original test expected
    # BENCHMARK_ONLY_UPDATED but backfill made 2026-11-05 FULL_MARKET_FRESH.
    # Gate logic is correct; the test needed updating.
    conn = sqlite3.connect("data/platform.db")
    from src.research.full_market_freshness_gate import check_market_freshness
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    # 2026-11-05 IS FULL_MARKET_FRESH (post-backfill)
    assert r.non_benchmark_count >= 6500  # post-backfill: 6,588 stocks
    # Gate logic is NOT regressed — it correctly identifies the full market state


def test_AR17_clock_injection_for_date_dependent_tests():
    """AR-17: Date-dependent tests should inject dates, not read from real DB."""
    conn = _make_full_market_db("2026-11-07")  # synthetic future date
    r = check_0050_gate(conn, "2026-11-07")
    assert r.status == DataGateStatus.PASS  # independent of real DB state
    conn.close()


# ── AR-18..23: Shadow Architecture ────────────────────────────────────────────

def test_AR18_capture_new_record():
    """AR-18: Capturing a new decision returns NEW_RECORD."""
    results = run_capture_outcome_isolation_test()
    assert results["step6_first_capture"] == "NEW_RECORD"


def test_AR19_capture_duplicate_identical():
    """AR-19: Capturing same decision twice returns DUPLICATE_IDENTICAL."""
    results = run_capture_outcome_isolation_test()
    assert results["step7a_duplicate_identical"] == "DUPLICATE_IDENTICAL"


def test_AR20_capture_conflict_different_payload():
    """AR-20: Capturing same key with different payload returns CAPTURE_CONFLICT."""
    results = run_capture_outcome_isolation_test()
    assert results["step7b_capture_conflict"] == "CAPTURE_CONFLICT"


def test_AR21_decision_immutable_after_capture():
    """AR-21: Original decision is not overwritten by conflict or duplicate."""
    results = run_capture_outcome_isolation_test()
    assert results["step8_immutable"] is True


def test_AR22_outcome_separation_from_decision():
    """AR-22: Outcome maturity is checked separately from decision record."""
    results = run_capture_outcome_isolation_test()
    # For a brand-new 2026-11-06 decision, outcome bars don't exist yet
    assert results["step_maturity_5d"] == "MISSING_DATA"
    assert results["step_maturity_10d"] == "MISSING_DATA"
    assert results["step_maturity_20d"] == "MISSING_DATA"


def test_AR23_outcome_maturity_mature_path():
    """AR-23: Outcome MATURE when sufficient post-signal bars exist."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE daily_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT, date TEXT, open REAL, high REAL, low REAL,
            close REAL, volume REAL, amount REAL, change_pct REAL
        );
    """)
    # Insert 25 bars for 2330 after 2026-11-01
    for i in range(1, 26):
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume, amount, change_pct) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2330", f"2026-11-{i + 1:02d}", 580.0, 590.0, 570.0, 585.0, 1000.0, 585000.0, 0.0)
        )
    conn.commit()
    mat5, _ = check_outcome_maturity("2026-11-01", 5, conn, "2330")
    mat10, _ = check_outcome_maturity("2026-11-01", 10, conn, "2330")
    mat20, _ = check_outcome_maturity("2026-11-01", 20, conn, "2330")
    assert mat5 == OutcomeMaturity.MATURE
    assert mat10 == OutcomeMaturity.MATURE
    assert mat20 == OutcomeMaturity.MATURE
    conn.close()


# ── AR-24..30: Safety Tests ────────────────────────────────────────────────────

def test_AR24_readonly_adapter_blocks_insert():
    """AR-24: ReadonlyProductionAdapter raises PermissionError on INSERT."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (x TEXT)")
    adapter = _make_readonly_adapter_from_conn(conn)
    with pytest.raises(PermissionError):
        adapter.execute("INSERT INTO t VALUES (?)", ("x",))
    conn.close()


def test_AR25_readonly_adapter_blocks_update():
    """AR-25: ReadonlyProductionAdapter raises PermissionError on UPDATE."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (x TEXT)")
    adapter = _make_readonly_adapter_from_conn(conn)
    with pytest.raises(PermissionError):
        adapter.execute("UPDATE t SET x=? WHERE 1=1", ("y",))
    conn.close()


def test_AR26_readonly_adapter_blocks_delete():
    """AR-26: ReadonlyProductionAdapter raises PermissionError on DELETE."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (x TEXT)")
    adapter = _make_readonly_adapter_from_conn(conn)
    with pytest.raises(PermissionError):
        adapter.execute("DELETE FROM t WHERE 1=1")
    conn.close()


def test_AR27_readonly_adapter_allows_select():
    """AR-27: ReadonlyProductionAdapter allows SELECT."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    adapter = _make_readonly_adapter_from_conn(conn)
    r = adapter.fetchone("SELECT x FROM t")
    assert r[0] == 42
    conn.close()


def test_AR28_readonly_adapter_allows_pragma():
    """AR-28: ReadonlyProductionAdapter allows PRAGMA (read-only metadata)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (x INTEGER)")
    adapter = _make_readonly_adapter_from_conn(conn)
    rows = adapter.fetchall("PRAGMA table_info(t)")
    assert len(rows) == 1
    conn.close()


def test_AR29_isolation_test_no_production_writes():
    """AR-29: Synthetic isolation test makes no production writes."""
    results = run_capture_outcome_isolation_test()
    assert results["step13_no_production_writes"] is True


def test_AR30_isolation_test_all_steps_pass():
    """AR-30: All synthetic isolation test steps pass end-to-end."""
    results = run_capture_outcome_isolation_test()
    assert results["all_steps_pass"] is True


# ── AR-31..35: Market Data Gate Report ────────────────────────────────────────

def test_AR31_market_gate_report_pass_full_market():
    """AR-31: MarketDataGateReport returns PASS for full market data."""
    conn = _make_full_market_db("2026-11-06")
    adapter = _make_readonly_adapter_from_conn(conn)
    report = build_market_data_gate_report(adapter, "2026-11-06")
    assert report.gate_verdict == MarketGateVerdict.PASS
    assert report.non_0050_count >= MIN_COVERED_STOCKS
    assert report.benchmark_status == "PASS"
    conn.close()


def test_AR32_market_gate_report_blocked_no_0050():
    """AR-32: MarketDataGateReport blocked when 0050 missing."""
    conn = _make_empty_db()
    adapter = _make_readonly_adapter_from_conn(conn)
    report = build_market_data_gate_report(adapter, "2026-11-06")
    assert report.gate_verdict in (MarketGateVerdict.BLOCKED, MarketGateVerdict.NO_DATA)
    assert report.benchmark_status == "FAIL"
    conn.close()


def test_AR33_twse_proxy_threshold():
    """AR-33: TWSE proxy passes at >= 1500 non-0050 stocks."""
    assert TWSE_PROXY_MIN == 1_500
    # Verify threshold logic
    conn = _make_twse_only_db("2026-11-06")  # 1800 non-0050 stocks
    adapter = _make_readonly_adapter_from_conn(conn)
    report = build_market_data_gate_report(adapter, "2026-11-06")
    assert "PASS(proxy:twse_only)" in report.twse_status
    assert "FAIL(proxy:tpex_missing)" in report.tpex_status
    conn.close()


def test_AR34_tpex_proxy_requires_full_market():
    """AR-34: TPEx proxy requires >= 5000 non-0050 stocks."""
    assert TPEX_PROXY_MIN == MIN_COVERED_STOCKS  # 5000
    conn = _make_full_market_db("2026-11-06")
    adapter = _make_readonly_adapter_from_conn(conn)
    report = build_market_data_gate_report(adapter, "2026-11-06")
    assert "PASS(proxy:both_present)" in report.tpex_status
    conn.close()


def test_AR35_timestamp_provenance_field():
    """AR-35: MarketDataGateReport includes timestamp provenance field."""
    conn = _make_full_market_db("2026-11-06")
    adapter = _make_readonly_adapter_from_conn(conn)
    report = build_market_data_gate_report(adapter, "2026-11-06")
    assert report.timestamp_status in ("PROVENANCE_INFERRED", "PROVENANCE_UNAVAILABLE")
    assert "daily_prices" in report.source_provenance
    conn.close()


# ── AR-36..40: Activation Readiness Matrix ────────────────────────────────────

def test_AR36_activation_report_has_16_requirements():
    """AR-36: V3ActivationReadinessReport always has exactly 16 requirements."""
    report = build_activation_readiness_report()
    assert len(report.requirements) == 16


def test_AR37_activation_verdict_conditional_not_ready_today():
    """AR-37: Today (Nov 6, before 16:00) report is CONDITIONAL_NOT_READY."""
    import pytz
    taiwan_tz = pytz.timezone("Asia/Taipei")
    # Simulate 13:00 Taiwan
    t = datetime(2026, 11, 6, 13, 0, 0, tzinfo=taiwan_tz)
    report = build_activation_readiness_report(current_taiwan_time=t)
    # Should be CONDITIONAL_NOT_READY (data not yet available, cron not yet run)
    # R16 (Explicit Activation Approval) is always PENDING → never READY
    assert report.overall_verdict != ActivationVerdict.READY_FOR_ACTIVATION_APPROVAL
    assert report.overall_verdict in (
        ActivationVerdict.CONDITIONAL_NOT_READY, ActivationVerdict.BLOCKED
    )


def test_AR38_r16_explicit_approval_always_pending():
    """AR-38: Requirement 16 (Explicit Activation Approval) is always PENDING in Session 30."""
    report = build_activation_readiness_report()
    r16 = next(r for r in report.requirements if "Activation Approval" in r.requirement)
    assert r16.verdict == RequirementStatus.PENDING


def test_AR39_v3_parameter_hash_unchanged():
    """AR-39: V3 parameter hash is unchanged from Session 26 expected value."""
    assert V3_PARAMETER_HASH == "be43e8ca977d9fdd"
    from src.research.v3_backtest_engine import PARAMETER_HASH as BT_HASH
    from src.research.v3_comparison_engine import PARAMETER_HASH as CP_HASH
    assert BT_HASH == "be43e8ca977d9fdd"
    assert CP_HASH == "1feb7a6b294a063d"


def test_AR40_no_production_writes_throughout_session():
    """AR-40: Safety verification — no production table writes in this test file."""
    prod_tables = [
        "forward_signals", "hybrid_forward_decision", "daily_prices",
        "stocks", "actual_positions", "forward_outcome_evaluations",
    ]
    # Verify ReadonlyProductionAdapter blocks all DML
    conn = sqlite3.connect(":memory:")
    for table in prod_tables:
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY)")
    conn.commit()
    adapter = _make_readonly_adapter_from_conn(conn)
    for table in prod_tables:
        with pytest.raises(PermissionError):
            adapter.execute(f"INSERT INTO {table} (id) VALUES (1)")
        with pytest.raises(PermissionError):
            adapter.execute(f"DELETE FROM {table}")
        with pytest.raises(PermissionError):
            adapter.execute(f"UPDATE {table} SET id=2")
    conn.close()
    # run_capture_outcome_isolation_test uses only :memory: SQLite
    results = run_capture_outcome_isolation_test()
    assert results["step13_no_production_writes"] is True
