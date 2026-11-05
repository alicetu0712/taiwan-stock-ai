"""
tests/test_dailyprice_backfill.py — Backfill script unit tests (BF01–BF20)

BF01–BF05  Safety checks (SQLite verification)
BF06–BF10  Missing-date detection
BF11–BF13  TWSE response parsing helpers
BF14–BF16  TPEx response parsing helpers
BF17–BF19  Dry-run / idempotency
BF20       run_backfill full flow with mocked API
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import date
from typing import List
from unittest.mock import patch

import pandas as pd
import pytest

from scripts.backfill_daily_prices import (
    _find_missing_dates,
    _strip_num,
    _to_roc_param,
    _verify_sqlite,
    _write_df_to_sqlite,
    run_backfill,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_sqlite(dates_for_0050: List[str] = None) -> str:
    """Create a temp SQLite with daily_prices and optional 0050 rows."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = f.name
    f.close()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE daily_prices ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "stock_id TEXT NOT NULL, date TEXT NOT NULL, "
        "open REAL, high REAL, low REAL, close REAL, "
        "volume REAL, amount REAL, change_pct REAL, "
        "UNIQUE(stock_id, date))"
    )
    if dates_for_0050:
        for d in dates_for_0050:
            conn.execute(
                "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
                "VALUES ('0050', ?, 100.0, 105.0, 98.0, 102.0, 5000.0)",
                (d,),
            )
    conn.commit()
    conn.close()
    return db_path


def _make_valid_df(n_stocks: int, target_date: date) -> pd.DataFrame:
    rows = [
        {
            "stock_id": "0050" if i == 0 else str(1000 + i),
            "date": target_date,
            "open": 100.0, "high": 105.0, "low": 98.0,
            "close": 102.0, "volume": 5000.0, "amount": 510.0, "change_pct": 2.0,
        }
        for i in range(n_stocks)
    ]
    return pd.DataFrame(rows)


# ── BF01–BF05: Safety checks ──────────────────────────────────────────────────

def test_BF01_valid_sqlite_passes_verification():
    db = _make_sqlite()
    try:
        _verify_sqlite(db)  # should not raise
    finally:
        os.unlink(db)


def test_BF02_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        _verify_sqlite("/tmp/nonexistent_research.db")


def test_BF03_non_sqlite_file_raises():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(b"This is not a SQLite file header at all\x00\x00")
        path = f.name
    try:
        with pytest.raises(ValueError, match="not a SQLite file"):
            _verify_sqlite(path)
    finally:
        os.unlink(path)


def test_BF04_sqlite_header_check():
    """Verify the magic bytes check catches non-SQLite files."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(b"\x50\x4b\x03\x04" + b"\x00" * 100)  # ZIP magic
        path = f.name
    try:
        with pytest.raises(ValueError):
            _verify_sqlite(path)
    finally:
        os.unlink(path)


def test_BF05_roc_param_conversion():
    """_to_roc_param converts Gregorian to ROC date string."""
    assert _to_roc_param(date(2026, 10, 29)) == "1151029"
    assert _to_roc_param(date(2026, 11, 5)) == "1151105"
    assert _to_roc_param(date(2025, 1, 15)) == "1140115"


# ── BF06–BF10: Missing-date detection ────────────────────────────────────────

def test_BF06_all_dates_missing():
    db = _make_sqlite(dates_for_0050=[])
    conn = sqlite3.connect(db)
    missing = _find_missing_dates(conn, date(2026, 11, 3), date(2026, 11, 5))
    conn.close()
    os.unlink(db)
    # 11-03 Mon, 11-04 Tue, 11-05 Wed = 3 trading days
    assert len(missing) == 3
    assert date(2026, 11, 3) in missing
    assert date(2026, 11, 4) in missing
    assert date(2026, 11, 5) in missing


def test_BF07_some_dates_already_present():
    db = _make_sqlite(dates_for_0050=["2026-11-03", "2026-11-04"])
    conn = sqlite3.connect(db)
    # min_covered_stocks=0: legacy 0050-only mode (test DB has no non-0050 stocks)
    missing = _find_missing_dates(conn, date(2026, 11, 3), date(2026, 11, 5), min_covered_stocks=0)
    conn.close()
    os.unlink(db)
    # Only 11-05 missing
    assert missing == [date(2026, 11, 5)]


def test_BF08_weekends_excluded():
    db = _make_sqlite()
    conn = sqlite3.connect(db)
    # Range that includes weekend: 2026-10-30 (Fri) to 2026-11-02 (Mon)
    missing = _find_missing_dates(conn, date(2026, 10, 30), date(2026, 11, 2))
    conn.close()
    os.unlink(db)
    # 10-30 Fri + 11-02 Mon = 2 trading days; 10-31 Sat + 11-01 Sun excluded
    assert date(2026, 10, 31) not in missing  # Saturday
    assert date(2026, 11, 1) not in missing   # Sunday
    assert date(2026, 10, 30) in missing
    assert date(2026, 11, 2) in missing


def test_BF09_all_dates_present_returns_empty():
    db = _make_sqlite(dates_for_0050=["2026-11-05"])
    conn = sqlite3.connect(db)
    # min_covered_stocks=0: legacy 0050-only mode (test DB has no non-0050 stocks)
    missing = _find_missing_dates(conn, date(2026, 11, 5), date(2026, 11, 5), min_covered_stocks=0)
    conn.close()
    os.unlink(db)
    assert missing == []


def test_BF10_holiday_excluded():
    """10-09-2026 is a holiday (國慶日補假), should NOT appear in missing."""
    db = _make_sqlite()
    conn = sqlite3.connect(db)
    missing = _find_missing_dates(conn, date(2026, 10, 9), date(2026, 10, 9))
    conn.close()
    os.unlink(db)
    # 10-09 is a holiday per TaiwanTradingCalendar
    assert date(2026, 10, 9) not in missing


# ── BF11–BF13: _strip_num helper ─────────────────────────────────────────────

def test_BF11_strip_num_normal():
    assert _strip_num("1,234,567.89") == pytest.approx(1234567.89)


def test_BF12_strip_num_dash_returns_none():
    assert _strip_num("--") is None
    assert _strip_num("-") is None
    assert _strip_num("") is None


def test_BF13_strip_num_no_comma():
    assert _strip_num("108.25") == pytest.approx(108.25)


# ── BF14–BF16: _write_df_to_sqlite ───────────────────────────────────────────

def test_BF14_write_inserts_new_rows():
    db = _make_sqlite()
    conn = sqlite3.connect(db)
    df = _make_valid_df(5, date(2026, 11, 5))
    inserted, skipped = _write_df_to_sqlite(conn, df)
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
    conn.close()
    os.unlink(db)
    assert inserted == 5
    assert skipped == 0
    assert count == 5


def test_BF15_write_idempotent_on_duplicate():
    db = _make_sqlite(dates_for_0050=["2026-11-05"])
    conn = sqlite3.connect(db)
    df = _make_valid_df(1, date(2026, 11, 5))  # 0050 on 2026-11-05 already exists
    inserted, skipped = _write_df_to_sqlite(conn, df)
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) FROM daily_prices WHERE stock_id='0050' AND date='2026-11-05'"
    ).fetchone()[0]
    conn.close()
    os.unlink(db)
    assert inserted == 0
    assert skipped == 1
    assert count == 1  # not duplicated


def test_BF16_write_partial_overlap():
    """Some rows new, some already exist → correct inserted/skipped counts."""
    db = _make_sqlite(dates_for_0050=["2026-11-05"])
    conn = sqlite3.connect(db)
    df = _make_valid_df(3, date(2026, 11, 5))  # 0050 (exists), 1001, 1002
    inserted, skipped = _write_df_to_sqlite(conn, df)
    conn.commit()
    conn.close()
    os.unlink(db)
    assert inserted == 2   # 1001 + 1002 new
    assert skipped == 1    # 0050 duplicate


# ── BF17–BF19: dry-run + run_backfill ────────────────────────────────────────

def test_BF17_dryrun_does_not_write():
    db = _make_sqlite(dates_for_0050=["2026-10-28"])

    target_date = date(2026, 10, 29)
    valid_df = _make_valid_df(350, target_date)

    with patch("scripts.backfill_daily_prices.fetch_twse_historical") as mock_twse, \
         patch("scripts.backfill_daily_prices.fetch_tpex_historical") as mock_tpex, \
         patch("scripts.backfill_daily_prices.time.sleep"):
        mock_twse.return_value = (valid_df, target_date)
        mock_tpex.return_value = (pd.DataFrame(), None)
        summary = run_backfill(
            start=target_date, end=target_date, execute=False, db_path=db
        )

    conn = sqlite3.connect(db)
    count = conn.execute(
        f"SELECT COUNT(*) FROM daily_prices WHERE date='{target_date}'"
    ).fetchone()[0]
    conn.close()
    os.unlink(db)

    assert count == 0  # dry-run: nothing written
    assert summary["total_inserted"] == 0


def test_BF18_execute_writes_rows():
    db = _make_sqlite(dates_for_0050=["2026-10-28"])

    target_date = date(2026, 10, 29)
    valid_df = _make_valid_df(350, target_date)

    with patch("scripts.backfill_daily_prices.fetch_twse_historical") as mock_twse, \
         patch("scripts.backfill_daily_prices.fetch_tpex_historical") as mock_tpex, \
         patch("scripts.backfill_daily_prices.time.sleep"):
        mock_twse.return_value = (valid_df, target_date)
        mock_tpex.return_value = (pd.DataFrame(), None)
        summary = run_backfill(
            start=target_date, end=target_date, execute=True, db_path=db
        )

    conn = sqlite3.connect(db)
    count = conn.execute(
        f"SELECT COUNT(*) FROM daily_prices WHERE date='{target_date}'"
    ).fetchone()[0]
    conn.close()
    os.unlink(db)

    assert count == 350
    assert summary["total_inserted"] == 350
    assert summary["dates_processed"] == 1


def test_BF19_qg_failure_blocks_write():
    """If quality gate fails (< min_stocks), nothing is written even with --execute."""
    db = _make_sqlite(dates_for_0050=["2026-10-28"])

    target_date = date(2026, 10, 29)
    too_few_rows = _make_valid_df(5, target_date)  # only 5 rows → QG-6 fails

    with patch("scripts.backfill_daily_prices.fetch_twse_historical") as mock_twse, \
         patch("scripts.backfill_daily_prices.fetch_tpex_historical") as mock_tpex, \
         patch("scripts.backfill_daily_prices.time.sleep"):
        mock_twse.return_value = (too_few_rows, target_date)
        mock_tpex.return_value = (pd.DataFrame(), None)
        summary = run_backfill(
            start=target_date, end=target_date, execute=True, db_path=db
        )

    conn = sqlite3.connect(db)
    count = conn.execute(
        f"SELECT COUNT(*) FROM daily_prices WHERE date='{target_date}'"
    ).fetchone()[0]
    conn.close()
    os.unlink(db)

    assert count == 0  # QG blocked the write
    assert len(summary["errors"]) > 0


# ── BF20: Full flow ───────────────────────────────────────────────────────────

def test_BF20_full_backfill_two_dates():
    """Run backfill for 2 consecutive trading days with mocked API; verify both committed."""
    db = _make_sqlite(dates_for_0050=["2026-10-28"])

    dates_to_fill = [date(2026, 10, 29), date(2026, 10, 30)]

    def mock_twse(d):
        return _make_valid_df(320, d), d

    def mock_tpex(d):
        small = pd.DataFrame([{
            "stock_id": f"6{i:03d}", "date": d,
            "open": 50.0, "high": 52.0, "low": 49.0,
            "close": 51.0, "volume": 300.0, "amount": 15.0, "change_pct": 1.0
        } for i in range(60)])
        return small, d

    with patch("scripts.backfill_daily_prices.fetch_twse_historical", side_effect=mock_twse), \
         patch("scripts.backfill_daily_prices.fetch_tpex_historical", side_effect=mock_tpex), \
         patch("scripts.backfill_daily_prices.time.sleep"):
        summary = run_backfill(
            start=dates_to_fill[0], end=dates_to_fill[-1],
            execute=True, db_path=db,
        )

    conn = sqlite3.connect(db)
    for d in dates_to_fill:
        cnt = conn.execute(
            f"SELECT COUNT(*) FROM daily_prices WHERE date='{d}'"
        ).fetchone()[0]
        assert cnt == 320 + 60, f"Expected 380 rows on {d}, got {cnt}"
    conn.close()
    os.unlink(db)

    assert summary["dates_processed"] == 2
    assert summary["total_inserted"] == (320 + 60) * 2
    assert len(summary["errors"]) == 0


# ── BF21–BF23: Coverage-aware missing date detection ─────────────────────────

def test_BF21_find_missing_detects_low_coverage_even_when_0050_present():
    """Date with 0050 but < 1,000 non-0050 stocks = still missing (needs fetch)."""
    db = _make_sqlite(dates_for_0050=["2026-11-05"])
    conn = sqlite3.connect(db)
    # Insert only 5 non-0050 stocks for 2026-11-05
    for i in range(5):
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) VALUES (?,?,100,105,98,102,5000)",
            (str(2000 + i), "2026-11-05"),
        )
    conn.commit()
    # With default threshold (1000), 5 stocks < 1000 → still missing
    missing = _find_missing_dates(conn, date(2026, 11, 5), date(2026, 11, 5))
    conn.close()
    os.unlink(db)
    assert date(2026, 11, 5) in missing


def test_BF22_find_missing_passes_when_coverage_met():
    """Date with 0050 AND >= _MIN_COVERED_STOCKS non-0050 stocks = not missing.

    Uses 5,100 stocks (> 5,000 threshold) — represents a full TWSE+TPEx day.
    1,100 was the old value when threshold was 1,000; that value is no longer sufficient.
    """
    db = _make_sqlite(dates_for_0050=["2026-11-05"])
    conn = sqlite3.connect(db)
    for i in range(5_100):  # > _MIN_COVERED_STOCKS (5,000); represents TWSE+TPEx universe
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) VALUES (?,?,100,105,98,102,5000)",
            (str(2000 + i), "2026-11-05"),
        )
    conn.commit()
    missing = _find_missing_dates(conn, date(2026, 11, 5), date(2026, 11, 5))
    conn.close()
    os.unlink(db)
    assert date(2026, 11, 5) not in missing


def test_BF24_twse_only_1976_in_missing_dates():
    """Date with TWSE-only (~1,976 non-0050) must stay in missing_dates → backfill retries TPEx.

    With _MIN_COVERED_STOCKS=5,000: 1,976 < 5,000 → date is still missing → TPEx will be re-fetched.
    With old threshold=1,000: 1,976 >= 1,000 → date would appear covered → TPEx never retried.
    """
    db = _make_sqlite(dates_for_0050=["2026-11-05"])
    conn = sqlite3.connect(db)
    for i in range(1_976):  # TWSE-only count (4-digit stocks, no TPEx)
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) VALUES (?,?,100,105,98,102,5000)",
            (str(2000 + i), "2026-11-05"),
        )
    conn.commit()
    missing = _find_missing_dates(conn, date(2026, 11, 5), date(2026, 11, 5))
    conn.close()
    os.unlink(db)
    assert date(2026, 11, 5) in missing, (
        "TWSE-only (1,976 stocks) should be in missing_dates so TPEx can be re-fetched"
    )


def test_BF23_find_missing_legacy_mode_respects_min_zero():
    """min_covered_stocks=0 → 0050-only mode (legacy): 0050 present = covered."""
    db = _make_sqlite(dates_for_0050=["2026-11-05"])
    conn = sqlite3.connect(db)
    # No non-0050 stocks — but legacy mode ignores coverage
    missing = _find_missing_dates(conn, date(2026, 11, 5), date(2026, 11, 5), min_covered_stocks=0)
    conn.close()
    os.unlink(db)
    assert date(2026, 11, 5) not in missing  # 0050 present = not missing in legacy mode
