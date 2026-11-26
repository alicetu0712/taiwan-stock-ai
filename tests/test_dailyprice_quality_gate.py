"""
tests/test_dailyprice_quality_gate.py — DQ gate unit tests (DP01–DP20)

DP01–DP05  Happy-path TWSE/TPEx data
DP06–DP10  OHLC inconsistency (QG-1)
DP11–DP13  Price bounds (QG-2)
DP14–DP15  Negative volume (QG-3)
DP16–DP17  Intra-batch duplicates (QG-4)
DP18       Date mismatch (QG-5)
DP19       Coverage threshold (QG-6)
DP20       Missing benchmark 0050 (QG-7)
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date

import pandas as pd
import pytest  # noqa: F401 — used by pytest.approx

from src.research.dailyprice_quality_gate import (
    audit_existing_data,
    run_quality_gate,
)

TARGET = date(2026, 11, 5)


def _make_row(stock_id: str, **kwargs) -> dict:
    base = {
        "stock_id": stock_id,
        "date": TARGET,
        "open": 100.0,
        "high": 105.0,
        "low": 98.0,
        "close": 102.0,
        "volume": 5000.0,
        "amount": 510.0,
        "change_pct": 2.0,
    }
    base.update(kwargs)
    return base


def _df(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


# ── DP01–DP05: Happy path ──────────────────────────────────────────────────────


def test_DP01_valid_twse_batch_passes():
    rows = [_make_row("0050"), _make_row("2330"), _make_row("2317")]
    rows += [_make_row(str(i)) for i in range(300)]  # fill to threshold
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert result.passed


def test_DP02_valid_tpex_batch_passes():
    rows = [_make_row(str(i)) for i in range(60)]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TPEx")
    assert result.passed


def test_DP03_exact_threshold_passes():
    rows = [_make_row("0050")] + [_make_row(str(i)) for i in range(299)]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE", min_stocks=300)
    assert result.passed


def test_DP04_zero_volume_allowed():
    """Halted stocks can have volume=0."""
    rows = [_make_row("0050", volume=0.0)] + [_make_row(str(i)) for i in range(299)]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert result.passed


def test_DP05_none_change_pct_allowed():
    """change_pct can be None (not required by QG)."""
    rows = [_make_row("0050", change_pct=None)] + [
        _make_row(str(i)) for i in range(299)
    ]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert result.passed


# ── DP06–DP10: QG-1 OHLC inconsistency ───────────────────────────────────────


def test_DP06_low_above_close_fails_qg1():
    rows = [_make_row("0050", low=110.0, close=102.0)] + [
        _make_row(str(i)) for i in range(299)
    ]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert not result.passed
    checks = [i.check for i in result.issues]
    assert "QG-1" in checks


def test_DP07_high_below_open_fails_qg1():
    rows = [_make_row("0050", open=200.0, high=105.0)] + [
        _make_row(str(i)) for i in range(299)
    ]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert not result.passed
    assert any(i.check == "QG-1" for i in result.issues)


def test_DP08_zero_close_fails_qg1():
    rows = [_make_row("0050", close=0.0)] + [_make_row(str(i)) for i in range(299)]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert not result.passed


def test_DP09_negative_low_fails_qg1():
    rows = [_make_row("0050", low=-1.0, close=102.0, open=100.0, high=105.0)] + [
        _make_row(str(i)) for i in range(299)
    ]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert not result.passed


def test_DP10_ohlc_ok_multiple_stocks():
    """All valid → no QG-1 issues."""
    rows = [_make_row("0050")] + [_make_row(str(i)) for i in range(299)]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert all(i.check != "QG-1" for i in result.issues)


# ── DP11–DP13: QG-2 price bounds ──────────────────────────────────────────────


def test_DP11_close_too_low_fails_qg2():
    rows = [_make_row("0050", open=0.05, high=0.06, low=0.04, close=0.05)] + [
        _make_row(str(i)) for i in range(299)
    ]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert not result.passed
    assert any(i.check == "QG-2" for i in result.issues)


def test_DP12_close_too_high_fails_qg2():
    rows = [
        _make_row("0050", open=25000.0, high=25010.0, low=24990.0, close=25000.0)
    ] + [_make_row(str(i)) for i in range(299)]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert not result.passed
    assert any(i.check == "QG-2" for i in result.issues)


def test_DP13_boundary_prices_pass():
    """close=0.1 and close=20000 are exactly on bounds → pass."""
    # QG-2 uses strict < and >, boundaries are OK
    rows_low = [_make_row("0050", open=0.1, high=0.11, low=0.09, close=0.1)] + [
        _make_row(str(i)) for i in range(299)
    ]
    df = _df(*rows_low)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert result.passed or not any(i.check == "QG-2" for i in result.issues)


# ── DP14–DP15: QG-3 negative volume ──────────────────────────────────────────


def test_DP14_negative_volume_fails_qg3():
    rows = [_make_row("0050", volume=-100.0)] + [_make_row(str(i)) for i in range(299)]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert not result.passed
    assert any(i.check == "QG-3" for i in result.issues)


def test_DP15_zero_volume_passes_qg3():
    rows = [_make_row("0050", volume=0.0)] + [_make_row(str(i)) for i in range(299)]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert all(i.check != "QG-3" for i in result.issues)


# ── DP16–DP17: QG-4 duplicates ───────────────────────────────────────────────


def test_DP16_duplicate_stock_id_fails_qg4():
    rows = [_make_row("0050"), _make_row("0050")] + [
        _make_row(str(i)) for i in range(299)
    ]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert not result.passed
    assert any(i.check == "QG-4" for i in result.issues)


def test_DP17_no_duplicates_passes_qg4():
    rows = [_make_row("0050")] + [_make_row(str(i)) for i in range(299)]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert all(i.check != "QG-4" for i in result.issues)


# ── DP18: QG-5 date mismatch ─────────────────────────────────────────────────


def test_DP18_wrong_date_fails_qg5():
    wrong_date = date(2026, 10, 28)
    rows = [_make_row("0050", date=wrong_date)] + [
        _make_row(str(i)) for i in range(299)
    ]
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE")
    assert not result.passed
    assert any(i.check == "QG-5" for i in result.issues)


# ── DP19: QG-6 coverage threshold ─────────────────────────────────────────────


def test_DP19_below_threshold_fails_qg6():
    rows = [_make_row("0050"), _make_row("2330")]  # only 2 rows
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE", min_stocks=300)
    assert not result.passed
    assert any(i.check == "QG-6" for i in result.issues)


# ── DP20: QG-7 benchmark 0050 ─────────────────────────────────────────────────


def test_DP20_missing_0050_fails_qg7():
    rows = [_make_row(str(i)) for i in range(300)]  # no 0050
    df = _df(*rows)
    result = run_quality_gate(df, TARGET, "TWSE", require_benchmark=True)
    assert not result.passed
    assert any(i.check == "QG-7" for i in result.issues)


# ── audit_existing_data ───────────────────────────────────────────────────────


def test_audit_empty_db_fails(tmp_path):
    db_path = str(tmp_path / "empty_audit.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE daily_prices "
        "(id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
        "open REAL, high REAL, low REAL, close REAL, volume REAL)"
    )
    conn.commit()
    result = audit_existing_data(conn, TARGET, market="TWSE")
    conn.close()
    assert not result.passed
    assert any(i.check in ("QG-6", "QG-7") for i in result.issues)
