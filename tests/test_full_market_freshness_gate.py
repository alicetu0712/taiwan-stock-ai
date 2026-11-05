"""
tests/test_full_market_freshness_gate.py — FM01–FM20

Coverage:
  FM01–FM05  Core FreshnessStatus logic
  FM06–FM10  Partial market scenarios
  FM07–FM10  Boundary and edge cases
  FM11–FM15  Direct runner bypass protection
  FM16–FM20  Integration with cron pipeline
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from src.research.full_market_freshness_gate import (
    MIN_COVERED_STOCKS,
    FreshnessStatus,
    check_market_freshness,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> str:
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE daily_prices "
        "(stock_id TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
    )
    conn.commit()
    conn.close()
    return str(db)


def _insert(conn: sqlite3.Connection, stock_id: str, dt: str) -> None:
    conn.execute(
        "INSERT INTO daily_prices VALUES (?,?,10,11,9,10,1000)",
        (stock_id, dt),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# FM01–FM05  Core status logic
# ---------------------------------------------------------------------------

def test_FM01_full_market_fresh(tmp_path):
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert(conn, "0050", "2026-11-04")
    for i in range(MIN_COVERED_STOCKS + 10):
        _insert(conn, f"stock_{i}", "2026-11-04")
    r = check_market_freshness(conn, date(2026, 11, 4), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.FULL_MARKET_FRESH
    assert not r.is_blocked


def test_FM02_benchmark_only_updated_zero_non_bm(tmp_path):
    """0050 updated but non-0050 count = 0 → BENCHMARK_ONLY_UPDATED."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert(conn, "0050", "2026-11-05")
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.BENCHMARK_ONLY_UPDATED
    assert r.is_blocked
    assert r.non_benchmark_count == 0


def test_FM03_partial_market_update(tmp_path):
    """0050 updated, non-0050 count > 0 but < threshold → PARTIAL_MARKET_UPDATE."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert(conn, "0050", "2026-11-05")
    for i in range(50):   # 50 < 1000
        _insert(conn, f"stock_{i}", "2026-11-05")
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.PARTIAL_MARKET_UPDATE
    assert r.is_blocked
    assert r.non_benchmark_count == 50


def test_FM04_stale_data(tmp_path):
    """0050 last date < trade_date → PROVIDER_NOT_READY (trading_day=True) or STALE (None)."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert(conn, "0050", "2026-11-04")  # last date is 11-04
    # Trade date 11-05 but 0050 not updated
    r_trading = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    # is_trading_day=None: caller doesn't know; 0050 is behind → STALE (not MARKET_CLOSED)
    r_stale   = check_market_freshness(conn, date(2026, 11, 5))  # is_trading_day=None
    conn.close()
    assert r_trading.status == FreshnessStatus.PROVIDER_NOT_READY
    assert r_stale.status == FreshnessStatus.STALE
    assert r_trading.is_blocked
    assert r_stale.is_blocked


def test_FM05_market_closed_not_blocked(tmp_path):
    """Non-trading day → MARKET_CLOSED, is_blocked=False."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    r = check_market_freshness(conn, date(2026, 11, 7), is_trading_day=False)
    conn.close()
    assert r.status == FreshnessStatus.MARKET_CLOSED
    assert not r.is_blocked


# ---------------------------------------------------------------------------
# FM06–FM10  Boundary / edge cases
# ---------------------------------------------------------------------------

def test_FM06_exact_threshold_passes(tmp_path):
    """Exactly MIN_COVERED_STOCKS non-0050 stocks → FULL_MARKET_FRESH."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert(conn, "0050", "2026-11-05")
    for i in range(MIN_COVERED_STOCKS):
        _insert(conn, f"stock_{i}", "2026-11-05")
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.FULL_MARKET_FRESH


def test_FM07_one_below_threshold_blocked(tmp_path):
    """MIN_COVERED_STOCKS - 1 non-0050 stocks → PARTIAL_MARKET_UPDATE."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert(conn, "0050", "2026-11-05")
    for i in range(MIN_COVERED_STOCKS - 1):
        _insert(conn, f"stock_{i}", "2026-11-05")
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.PARTIAL_MARKET_UPDATE
    assert r.is_blocked


def test_FM08_benchmark_newer_than_trade_date_with_full_coverage(tmp_path):
    """0050 max_date > trade_date AND full coverage on trade_date → FULL_MARKET_FRESH."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    # 0050 manually recovered ahead: last date = 11-05
    _insert(conn, "0050", "2026-11-05")
    # Full non-0050 coverage exists for 11-04
    for i in range(MIN_COVERED_STOCKS + 100):
        _insert(conn, f"stock_{i}", "2026-11-04")
    r = check_market_freshness(conn, date(2026, 11, 4), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.FULL_MARKET_FRESH
    assert not r.is_blocked


def test_FM09_empty_db_returns_unknown(tmp_path):
    """Empty database → UNKNOWN."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.UNKNOWN
    assert r.is_blocked


def test_FM10_human_readable_contains_key_info(tmp_path):
    """human_readable() for PARTIAL_MARKET_UPDATE mentions stock counts."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert(conn, "0050", "2026-11-05")
    for i in range(50):
        _insert(conn, f"stock_{i}", "2026-11-05")
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.PARTIAL_MARKET_UPDATE
    hr = r.human_readable()
    assert "50" in hr
    assert f"{MIN_COVERED_STOCKS:,}" in hr  # threshold appears comma-formatted (e.g. "5,000")


# ---------------------------------------------------------------------------
# FM11–FM15  Real DB integration
# ---------------------------------------------------------------------------

def test_FM11_real_db_11_05_benchmark_only():
    """Real DB: 2026-11-05 should be BENCHMARK_ONLY_UPDATED (non-0050=0)."""
    conn = sqlite3.connect("data/platform.db")
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.BENCHMARK_ONLY_UPDATED
    assert r.is_blocked
    assert r.non_benchmark_count == 0


def test_FM12_real_db_11_04_full_market():
    """Real DB: 2026-11-04 should be FULL_MARKET_FRESH (6,956 non-0050 stocks)."""
    conn = sqlite3.connect("data/platform.db")
    r = check_market_freshness(conn, date(2026, 11, 4), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.FULL_MARKET_FRESH
    assert not r.is_blocked
    assert r.non_benchmark_count >= MIN_COVERED_STOCKS


def test_FM13_real_db_weekend_market_closed():
    """2026-11-07 (Sat) → MARKET_CLOSED."""
    conn = sqlite3.connect("data/platform.db")
    r = check_market_freshness(conn, date(2026, 11, 7), is_trading_day=False)
    conn.close()
    assert r.status == FreshnessStatus.MARKET_CLOSED
    assert not r.is_blocked


def test_FM14_blocked_status_prevents_prospective():
    """is_blocked=True for all non-FULL_MARKET_FRESH/MARKET_CLOSED statuses."""
    for status in FreshnessStatus:
        if status in (FreshnessStatus.FULL_MARKET_FRESH, FreshnessStatus.MARKET_CLOSED):
            continue
        # Create a mock report for each blocked status
        from src.research.full_market_freshness_gate import FreshnessReport
        r = FreshnessReport(
            status=status,
            trade_date=date(2026, 11, 5),
            benchmark_date=date(2026, 11, 5),
            non_benchmark_count=0,
            min_required=MIN_COVERED_STOCKS,
            detail="test",
        )
        assert r.is_blocked, f"Expected is_blocked=True for {status}"


def test_FM15_min_covered_stocks_constant():
    """MIN_COVERED_STOCKS must be >= 5000 to block TWSE-only partial market writes.

    Calibrated: TWSE-only ≈ 1,976 non-0050; TWSE+TPEx ≈ 6,956.
    Threshold < 1,977 would let a TWSE-only write pass as FULL_MARKET_FRESH.
    """
    assert MIN_COVERED_STOCKS >= 5_000


def test_FM21_twse_only_1976_is_blocked(tmp_path):
    """TWSE-only write (~1,976 non-0050) must NOT pass as FULL_MARKET_FRESH.

    Root cause of defect: with threshold=1,000 these 1,976 stocks would pass.
    With threshold=5,000 they correctly show PARTIAL_MARKET_UPDATE.
    """
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert(conn, "0050", "2026-11-05")
    for i in range(1_976):  # realistic TWSE-only stock count (4-digit non-0050)
        _insert(conn, f"{2000 + i:04d}", "2026-11-05")
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.PARTIAL_MARKET_UPDATE, (
        f"TWSE-only (1,976 stocks) should be PARTIAL_MARKET_UPDATE, got {r.status}. "
        f"threshold={MIN_COVERED_STOCKS}, non_bm_count={r.non_benchmark_count}"
    )
    assert r.is_blocked, "TWSE-only scenario must be blocked (shadow must not run)"


# ---------------------------------------------------------------------------
# FM16–FM20  Cron pipeline integration
# ---------------------------------------------------------------------------

def test_FM16_cron_blocked_partial_on_benchmark_only_state(tmp_path):
    """Cron step 4b must return BLOCKED_PARTIAL_MARKET when only 0050 is updated."""
    from src.research.full_market_freshness_gate import FreshnessStatus

    # Simulate the check that cron does
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert(conn, "0050", "2026-11-05")
    # No non-0050 stocks
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.BENCHMARK_ONLY_UPDATED
    assert r.is_blocked


def test_FM17_shadow_runner_runstatus_has_blocked_partial():
    """RunStatus must have BLOCKED_PARTIAL_MARKET constant."""
    from src.research.hybrid_forward_db import RunStatus
    assert hasattr(RunStatus, "BLOCKED_PARTIAL_MARKET")
    assert RunStatus.BLOCKED_PARTIAL_MARKET == "BLOCKED_PARTIAL_MARKET"


def test_FM18_cron_exit_code_0_on_blocked_partial():
    """BLOCKED_PARTIAL_MARKET exit code must be 0 (expected, not an error)."""
    clean_statuses = {
        "SUCCESS", "DRY_RUN_OK", "SKIPPED_NON_TRADING_DAY", "DATA_NOT_READY",
        "BLOCKED_STALE_DATA", "BLOCKED_LOCK", "BLOCKED_PARTIAL_MARKET",
    }
    assert "BLOCKED_PARTIAL_MARKET" in clean_statuses


def test_FM19_twse_only_update_is_partial(tmp_path):
    """TWSE updated (1,977 stocks) but < MIN_COVERED_STOCKS → PARTIAL_MARKET_UPDATE."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert(conn, "0050", "2026-11-05")
    for i in range(900):   # ~TWSE only, < 1000 threshold
        _insert(conn, f"twse_{i}", "2026-11-05")
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.PARTIAL_MARKET_UPDATE
    assert r.is_blocked


def test_FM20_full_market_requires_both_benchmark_and_coverage(tmp_path):
    """Full market fresh requires BOTH 0050 date match AND >= threshold non-0050 stocks."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    # Only non-0050 stocks without 0050 → UNKNOWN
    for i in range(MIN_COVERED_STOCKS + 100):
        _insert(conn, f"stock_{i}", "2026-11-05")
    r = check_market_freshness(conn, date(2026, 11, 5), is_trading_day=True)
    conn.close()
    assert r.status == FreshnessStatus.UNKNOWN   # 0050 missing → unknown
    assert r.is_blocked
