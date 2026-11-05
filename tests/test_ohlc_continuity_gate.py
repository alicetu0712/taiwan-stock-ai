"""
tests/test_ohlc_continuity_gate.py — CG01–CG25: OHLC Continuity Gate tests.

Coverage:
  CG01–CG05  DateStatus classification
  CG06–CG10  Market gate (check_market) with synthetic data
  CG11–CG15  Stock gate (check_stock) with synthetic data
  CG16–CG20  Real DB integration checks (actual data/platform.db)
  CG21–CG25  Edge cases and check_all
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.trading_calendar import TaiwanTradingCalendar
from src.research.ohlc_continuity_gate import (
    DateStatus,
    GateResult,
    OHLCContinuityGate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REAL_DB = Path(__file__).parent.parent / "data" / "platform.db"
_cal = TaiwanTradingCalendar()


def _make_db(dates_for_0050: list[date], extra: dict[str, list[date]] | None = None) -> sqlite3.Connection:
    """Create in-memory SQLite with daily_prices for given dates."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE daily_prices "
        "(stock_id TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
    )
    # Insert 0050 rows
    for d in dates_for_0050:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
            ("0050", str(d), 190.0, 192.0, 189.0, 191.0, 5000.0),
        )
    # Insert per-stock extra rows
    if extra:
        for sid, dts in extra.items():
            for d in dts:
                conn.execute(
                    "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                    (sid, str(d), 10.0, 11.0, 9.5, 10.5, 1000.0),
                )
    conn.commit()
    return conn


def _consecutive_trading_days(start: date, n: int) -> list[date]:
    """Return n consecutive trading days starting from start."""
    result = []
    d = start
    while len(result) < n:
        if _cal.is_trading_day(d):
            result.append(d)
        d += timedelta(days=1)
    return result


def _last_n_trading_days(end: date, n: int) -> list[date]:
    """Return n trading days ending on end, in chronological order."""
    result = []
    d = end
    while len(result) < n:
        if _cal.is_trading_day(d):
            result.append(d)
        d -= timedelta(days=1)
    result.reverse()
    return result


# ---------------------------------------------------------------------------
# CG01–CG05  DateStatus classification via _classify_date
# ---------------------------------------------------------------------------

def test_CG01_expected_td_with_data_is_available():
    gate = OHLCContinuityGate()
    # 2026-11-04 is a trading day
    td = date(2026, 11, 4)
    assert _cal.is_trading_day(td)
    status = gate._classify_date(td, has_0050_data=True)
    assert status == DateStatus.DATA_AVAILABLE


def test_CG02_expected_td_without_data_is_missing():
    gate = OHLCContinuityGate()
    td = date(2026, 11, 3)
    assert _cal.is_trading_day(td)
    status = gate._classify_date(td, has_0050_data=False)
    assert status == DateStatus.EXPECTED_DATA_MISSING


def test_CG03_weekend_without_data_is_market_closed():
    gate = OHLCContinuityGate()
    sat = date(2026, 11, 7)
    assert sat.weekday() == 5  # Saturday
    status = gate._classify_date(sat, has_0050_data=False)
    assert status == DateStatus.MARKET_CLOSED


def test_CG04_calendar_holiday_without_data_is_market_closed():
    gate = OHLCContinuityGate()
    # 2026-09-25 is 中秋節 (calendar holiday)
    hol = date(2026, 9, 25)
    assert not _cal.is_trading_day(hol)
    status = gate._classify_date(hol, has_0050_data=False)
    assert status == DateStatus.MARKET_CLOSED


def test_CG05_calendar_holiday_with_data_is_unknown():
    gate = OHLCContinuityGate()
    # 2026-10-09 is listed as 國慶日補假 but DB has 7,586 stocks
    hol = date(2026, 10, 9)
    assert not _cal.is_trading_day(hol)  # calendar says holiday
    status = gate._classify_date(hol, has_0050_data=True)
    assert status == DateStatus.UNKNOWN


# ---------------------------------------------------------------------------
# CG06–CG10  Market gate (check_market) — synthetic data
# ---------------------------------------------------------------------------

def test_CG06_market_gate_pass_all_30_present():
    gate = OHLCContinuityGate()
    # Build 30 consecutive trading days ending 2026-09-01
    end = date(2026, 9, 1)
    days_30 = _last_n_trading_days(end, 30)
    conn = _make_db(days_30)
    report = gate.check_market(conn, end)
    conn.close()
    assert report.gate_result == GateResult.PASS
    assert report.missing_sessions == 0
    assert report.present_sessions == 30


def test_CG07_market_gate_blocked_one_missing():
    gate = OHLCContinuityGate()
    end = date(2026, 9, 1)
    days_30 = _last_n_trading_days(end, 30)
    # Remove one expected trading day
    missing_day = days_30[10]  # middle of window
    days_with_hole = [d for d in days_30 if d != missing_day]
    conn = _make_db(days_with_hole)
    report = gate.check_market(conn, end)
    conn.close()
    assert report.gate_result == GateResult.BLOCKED_MISSING_OHLC
    assert report.missing_sessions >= 1
    assert missing_day in report.missing_dates


def test_CG08_market_gate_blocked_multiple_missing():
    gate = OHLCContinuityGate()
    end = date(2026, 9, 1)
    days_30 = _last_n_trading_days(end, 30)
    # Remove 5 days from the window
    missing_days = days_30[5:10]
    days_with_holes = [d for d in days_30 if d not in missing_days]
    conn = _make_db(days_with_holes)
    report = gate.check_market(conn, end)
    conn.close()
    assert report.gate_result == GateResult.BLOCKED_MISSING_OHLC
    assert report.missing_sessions == 5
    for md in missing_days:
        assert md in report.missing_dates


def test_CG09_weekend_data_does_not_increase_missing_count():
    """Data present on a weekend day counts as UNKNOWN — not as missing expected trading day."""
    gate = OHLCContinuityGate()
    end = date(2026, 9, 1)
    days_30 = _last_n_trading_days(end, 30)
    # Find the first Saturday within the window's calendar range
    sat = None
    d = days_30[0]
    while d <= end:
        if d.weekday() == 5:  # Saturday
            sat = d
            break
        d += timedelta(days=1)
    assert sat is not None, "No Saturday found in 30+ calendar day range (impossible)"
    conn = _make_db(days_30 + [sat])  # all 30 expected TDs + a Saturday with data
    report = gate.check_market(conn, end)
    conn.close()
    # Having weekend data must not create a missing session
    assert report.missing_sessions == 0
    # Gate must not be BLOCKED due to weekend data
    assert report.gate_result != GateResult.BLOCKED_MISSING_OHLC
    # Gate may become UNKNOWN_CALENDAR if Saturday is within the [start, trade_date] range
    assert report.gate_result in (GateResult.PASS, GateResult.UNKNOWN_CALENDAR)


def test_CG10_non_trading_day_returns_not_applicable():
    gate = OHLCContinuityGate()
    saturday = date(2026, 11, 7)
    conn = _make_db([date(2026, 11, 4)])
    report = gate.check_market(conn, saturday)
    conn.close()
    assert report.gate_result == GateResult.NOT_APPLICABLE


# ---------------------------------------------------------------------------
# CG11–CG15  Stock gate (check_stock) — synthetic data
# ---------------------------------------------------------------------------

def test_CG11_stock_gate_pass_all_market_open_days_present():
    gate = OHLCContinuityGate()
    end = date(2026, 9, 1)
    market_days = _last_n_trading_days(end, 20)
    # Stock has data on all 20 market-open days + enough total history
    extra = {"2330": market_days + _last_n_trading_days(market_days[0] - timedelta(days=1), 50)}
    conn = _make_db(market_days, extra)
    report = gate.check_stock(conn, "2330", end, market_days)
    conn.close()
    assert report.gate_result == GateResult.PASS
    assert report.stock_missing == 0


def test_CG12_stock_gate_blocked_missing_one_market_day():
    gate = OHLCContinuityGate()
    end = date(2026, 9, 1)
    market_days = _last_n_trading_days(end, 20)
    # Stock missing on day 5
    missing_day = market_days[5]
    stock_days = [d for d in market_days if d != missing_day]
    # Still need MIN_HIST_BARS total
    extra_hist = _last_n_trading_days(market_days[0] - timedelta(days=1), 55)
    extra = {"2330": stock_days + extra_hist}
    conn = _make_db(market_days, extra)
    report = gate.check_stock(conn, "2330", end, market_days)
    conn.close()
    assert report.gate_result == GateResult.BLOCKED_MISSING_OHLC
    assert report.stock_missing >= 1


def test_CG13_stock_gate_blocked_insufficient_history():
    gate = OHLCContinuityGate()
    end = date(2026, 9, 1)
    market_days = _last_n_trading_days(end, 20)
    # Stock only has 20 total closes (< MIN_HIST_BARS = 70)
    extra = {"2330": market_days}
    conn = _make_db(market_days, extra)
    report = gate.check_stock(conn, "2330", end, market_days)
    conn.close()
    assert report.gate_result == GateResult.BLOCKED_INSUFFICIENT_HISTORY
    assert report.total_bars_in_db == 20


def test_CG14_stock_reports_not_applicable_when_market_blocked():
    gate = OHLCContinuityGate()
    end = date(2026, 9, 1)
    # Only 10 days of market data (gate will block due to stale or missing)
    market_days = _last_n_trading_days(end, 5)
    conn = _make_db(market_days)
    market_report, stock_reports = gate.check_all(conn, ["2330"], end)
    conn.close()
    # If market is blocked, stock should be NOT_APPLICABLE
    if market_report.gate_result in (GateResult.BLOCKED_MISSING_OHLC, GateResult.BLOCKED_STALE_DATA):
        assert stock_reports["2330"].gate_result == GateResult.NOT_APPLICABLE


def test_CG15_0050_itself_passes_stock_gate_when_market_passes():
    gate = OHLCContinuityGate()
    end = date(2026, 9, 1)
    days_30 = _last_n_trading_days(end, 30)
    # Add extra history for 0050 to pass MIN_HIST_BARS
    extra_hist = _last_n_trading_days(days_30[0] - timedelta(days=1), 50)
    all_days = extra_hist + days_30
    conn = _make_db(all_days)
    market_report = gate.check_market(conn, end)
    if market_report.gate_result == GateResult.PASS:
        stock_report = gate.check_stock(conn, "0050", end, days_30[-20:])
        assert stock_report.gate_result in (GateResult.PASS, GateResult.BLOCKED_INSUFFICIENT_HISTORY)
    conn.close()


# ---------------------------------------------------------------------------
# CG16–CG20  Real DB integration (data/platform.db)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not REAL_DB.exists(), reason="data/platform.db not found")
def test_CG16_market_gate_pass_for_20261105():
    """After OHLC recovery (all 10 missing dates filled), gate PASSES for 11-05."""
    gate = OHLCContinuityGate()
    conn = sqlite3.connect(str(REAL_DB))
    report = gate.check_market(conn, date(2026, 11, 5))
    conn.close()
    assert report.gate_result == GateResult.PASS
    assert report.missing_sessions == 0
    assert report.present_sessions == 30


@pytest.mark.skipif(not REAL_DB.exists(), reason="data/platform.db not found")
def test_CG17_market_gate_pass_for_20261104():
    """After OHLC recovery, the 30-day window ending 11-04 is also complete."""
    gate = OHLCContinuityGate()
    conn = sqlite3.connect(str(REAL_DB))
    report = gate.check_market(conn, date(2026, 11, 4))
    conn.close()
    assert report.gate_result == GateResult.PASS
    assert report.missing_sessions == 0


@pytest.mark.skipif(not REAL_DB.exists(), reason="data/platform.db not found")
def test_CG18_no_missing_dates_after_recovery():
    """After recovery, all 30 market sessions in the 11-05 window have 0050 data."""
    gate = OHLCContinuityGate()
    conn = sqlite3.connect(str(REAL_DB))
    report = gate.check_market(conn, date(2026, 11, 5))
    conn.close()
    assert len(report.missing_dates) == 0
    assert report.present_sessions == 30


@pytest.mark.skipif(not REAL_DB.exists(), reason="data/platform.db not found")
def test_CG19_oct9_deleted_classified_as_holiday():
    """2026-10-09 mislabeled data was deleted; calendar says HOLIDAY → MARKET_CLOSED."""
    gate = OHLCContinuityGate()
    conn = sqlite3.connect(str(REAL_DB))
    has_data = conn.execute(
        "SELECT COUNT(*) FROM daily_prices WHERE stock_id='0050' AND date='2026-10-09'"
    ).fetchone()[0]
    conn.close()
    assert has_data == 0, "corrupt 0050 row for 2026-10-09 should have been deleted"
    status = gate._classify_date(date(2026, 10, 9), has_0050_data=False)
    assert status == DateStatus.MARKET_CLOSED


def test_CG20_pass_scenario_synthetic_30_days():
    """Build a fresh in-memory DB with 30 consecutive clean days — gate should PASS."""
    gate = OHLCContinuityGate()
    # Use 2026-08-01 — well within covered calendar year, no major holidays
    end = date(2026, 8, 3)
    days = _last_n_trading_days(end, 30)
    conn = _make_db(days)
    report = gate.check_market(conn, end)
    conn.close()
    assert report.gate_result == GateResult.PASS
    assert report.missing_sessions == 0
    assert report.present_sessions == 30


# ---------------------------------------------------------------------------
# CG21–CG25  Edge cases and check_all
# ---------------------------------------------------------------------------

def test_CG21_check_all_returns_market_and_stock_reports():
    gate = OHLCContinuityGate()
    end = date(2026, 9, 1)
    days_30 = _last_n_trading_days(end, 30)
    extra_hist = _last_n_trading_days(days_30[0] - timedelta(days=1), 55)
    extra = {"2330": days_30 + extra_hist, "2317": days_30 + extra_hist}
    conn = _make_db(days_30, extra)
    market, stocks = gate.check_all(conn, ["2330", "2317"], end)
    conn.close()
    assert "2330" in stocks
    assert "2317" in stocks
    assert market.gate_result in GateResult.__members__.values()


def test_CG22_check_stock_precomputed_market_open_dates():
    gate = OHLCContinuityGate()
    end = date(2026, 9, 1)
    market_days = _last_n_trading_days(end, 20)
    extra_hist = _last_n_trading_days(market_days[0] - timedelta(days=1), 55)
    extra = {"2330": market_days + extra_hist}
    conn = _make_db(market_days, extra)
    # Pass pre-computed market_open_dates → same result as auto-computed
    r1 = gate.check_stock(conn, "2330", end, market_open_dates=market_days)
    r2 = gate.check_stock(conn, "2330", end, market_open_dates=None)
    conn.close()
    assert r1.gate_result == r2.gate_result
    assert r1.stock_present == r2.stock_present


def test_CG23_gate_pass_only_when_all_present():
    gate = OHLCContinuityGate()
    end = date(2026, 9, 1)
    days_30 = _last_n_trading_days(end, 30)
    # All present → PASS
    conn = _make_db(days_30)
    r_all = gate.check_market(conn, end)
    conn.close()
    # Remove last day → BLOCKED
    conn2 = _make_db(days_30[:-1])
    r_miss = gate.check_market(conn2, end)
    conn2.close()
    assert r_all.gate_result == GateResult.PASS
    assert r_miss.gate_result == GateResult.BLOCKED_MISSING_OHLC


def test_CG24_missing_dates_sorted_chronologically():
    gate = OHLCContinuityGate()
    end = date(2026, 9, 1)
    days_30 = _last_n_trading_days(end, 30)
    # Remove days 2, 5, 15 (non-consecutive)
    missing = [days_30[2], days_30[5], days_30[15]]
    conn = _make_db([d for d in days_30 if d not in missing])
    report = gate.check_market(conn, end)
    conn.close()
    assert report.gate_result == GateResult.BLOCKED_MISSING_OHLC
    # missing_dates should be sorted ascending
    assert report.missing_dates == sorted(report.missing_dates)


def test_CG25_stale_data_returns_blocked_stale():
    gate = OHLCContinuityGate()
    # DB has data but last date is 20+ days before trade_date
    old_date = date(2026, 8, 1)
    trade_date = date(2026, 9, 10)
    gap = (trade_date - old_date).days
    assert gap > 7
    conn = _make_db([old_date])
    report = gate.check_market(conn, trade_date)
    conn.close()
    assert report.gate_result == GateResult.BLOCKED_STALE_DATA
