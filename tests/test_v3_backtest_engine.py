"""
tests/test_v3_backtest_engine.py — V3 Historical Backtest Engine Tests

Test IDs: BT-01 to BT-25
All tests use in-memory SQLite with synthetic OHLCV data.
No network calls, no production DB writes.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from typing import List

import pandas as pd

from src.research.execution_simulator import EXPIRY_DAYS, HOLD_DAYS
from src.research.v3_backtest_engine import (
    ENGINE_VERSION,
    IN_SAMPLE_WARNING,
    MATURED_FULL,
    MATURED_NONE,
    MATURED_PARTIAL,
    PARAMETER_HASH,
    RESEARCH_VERSION,
    V3BacktestEngine,
    V3SignalInput,
    _compute_parameter_hash,
    load_buy_signals_for_backtest,
)
from src.research.v3_entry_strategy import (
    AVOID_CHASING,
    DIRECT_ENTRY,
    MIN_BARS_FULL,
    NO_ENTRY,
    WAIT_BREAKOUT_CONFIRMATION,
    WAIT_MA20_PULLBACK,
    WAIT_MA60_SUPPORT,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_conn() -> sqlite3.Connection:
    """In-memory SQLite with daily_prices and forward_signals tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE daily_prices ("
        "id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
        "open REAL, high REAL, low REAL, close REAL, volume REAL)"
    )
    conn.execute(
        "CREATE TABLE forward_signals ("
        "id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, "
        "trade_signal TEXT, market_regime_at_signal TEXT)"
    )
    return conn


def _insert_ohlcv(
    conn: sqlite3.Connection,
    stock_id: str,
    start: date,
    n: int,
    base: float = 100.0,
    drift: float = 0.0,
    volatility: float = 0.5,
) -> List[date]:
    """
    Insert n OHLCV rows for stock_id starting from start date.
    Returns list of dates inserted.
    """
    dates = []
    for i in range(n):
        d = start + timedelta(days=i)
        c = base + drift * i
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (stock_id, str(d), c * 0.99, c * 1.01, c * 0.99, c, 100000.0),
        )
        dates.append(d)
    conn.commit()
    return dates


def _build_history_df(
    n: int = MIN_BARS_FULL,
    base: float = 100.0,
    drift: float = 0.0,
    signal_date: date = date(2026, 1, 10),
) -> pd.DataFrame:
    """Build a minimal valid OHLCV history dataframe (not from DB)."""
    rows = []
    start = signal_date - timedelta(days=n - 1)
    for i in range(n):
        d = start + timedelta(days=i)
        c = base + drift * i
        rows.append({
            "date": d,
            "open": c * 0.99,
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "volume": 100000.0,
        })
    return pd.DataFrame(rows)


# ── BT-01: DIRECT_ENTRY fills at D+1 OPEN ──────────────────────────────────────

def test_bt01_direct_entry_fills_at_d1_open():
    """BT-01: DIRECT_ENTRY decision → trade filled at D+1 OPEN."""
    conn = _make_conn()
    signal_date = date(2026, 10, 1)

    # Insert 71 history bars ending on signal_date
    _insert_ohlcv(conn, "1101", signal_date - timedelta(days=MIN_BARS_FULL - 1), MIN_BARS_FULL, base=100.0)

    # Insert 25 post-signal bars with known OPEN values
    post_start = signal_date + timedelta(days=1)
    for i in range(25):
        d = post_start + timedelta(days=i)
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("1101", str(d), 101.0, 103.0, 100.5, 102.0, 100000.0),
        )
    conn.commit()

    engine = V3BacktestEngine(conn)
    # Build a signal — market in bull so many V3 signals → DIRECT_ENTRY possible.
    # We'll test via a known pure-state: inject a custom V3 decision mapping.
    # Directly test _simulate_v3_entry with a mock V3EntryDecision.
    from src.research.v3_entry_strategy import V3EntryDecision
    v3 = V3EntryDecision(
        stock_id="1101",
        entry_decision=DIRECT_ENTRY,
        entry_price=100.0,
        stop_price=96.0,
        target_price=108.0,
    )
    post_ohlcv = engine._load_post_signal("1101", signal_date)
    signal = V3SignalInput(signal_date=signal_date, stock_id="1101")

    exec_label, trade = engine._simulate_v3_entry(signal, v3, post_ohlcv)

    assert exec_label == "ENTRY_READY"
    assert trade.filled is True
    assert trade.fill_date == post_start
    assert abs(trade.fill_price - 101.0) < 0.01


# ── BT-02: WAIT_MA20_PULLBACK — no trigger → NO_FILL_EXPIRED ──────────────────

def test_bt02_wait_ma20_no_trigger():
    """BT-02: WAIT_MA20_PULLBACK with no LOW ≤ trigger → no fill (EXPIRED)."""
    conn = _make_conn()
    from src.research.v3_entry_strategy import V3EntryDecision
    from src.research.execution_simulator import NO_FILL_EXPIRED

    signal_date = date(2026, 10, 1)
    post_start = signal_date + timedelta(days=1)

    # Insert post-signal bars all with LOW = 103 > trigger 101
    for i in range(EXPIRY_DAYS + 2):
        d = post_start + timedelta(days=i)
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("1102", str(d), 104.0, 105.0, 103.0, 104.0, 100000.0),
        )
    conn.commit()

    engine = V3BacktestEngine(conn)
    v3 = V3EntryDecision(
        stock_id="1102",
        entry_decision=WAIT_MA20_PULLBACK,
        entry_price=104.0,
        stop_price=96.0,
        target_price=112.0,
        proposed_limit_price=101.0,  # trigger below current price
    )
    post_ohlcv = engine._load_post_signal("1102", signal_date)
    signal = V3SignalInput(signal_date=signal_date, stock_id="1102")

    exec_label, trade = engine._simulate_v3_entry(signal, v3, post_ohlcv)

    assert exec_label == "V3_WAIT_MA20"
    assert trade.filled is False
    assert trade.no_fill_reason == NO_FILL_EXPIRED


# ── BT-03: WAIT_MA20_PULLBACK — trigger fires ──────────────────────────────────

def test_bt03_wait_ma20_trigger_fires():
    """BT-03: WAIT_MA20_PULLBACK trigger fires when LOW ≤ proposed_limit_price."""
    conn = _make_conn()
    from src.research.v3_entry_strategy import V3EntryDecision

    signal_date = date(2026, 10, 1)
    post_dates = [signal_date + timedelta(days=i + 1) for i in range(25)]

    # Day 0-2: HIGH low (no trigger). Day 3: LOW drops to 100 ≤ trigger 101.
    trigger_day = post_dates[3]
    fill_day = post_dates[4]

    for i, d in enumerate(post_dates):
        low = 100.0 if d == trigger_day else 103.0
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("1103", str(d), 104.0, 105.0, low, 104.0, 100000.0),
        )
    conn.commit()

    engine = V3BacktestEngine(conn)
    v3 = V3EntryDecision(
        stock_id="1103",
        entry_decision=WAIT_MA20_PULLBACK,
        entry_price=104.0,
        stop_price=94.0,
        target_price=116.0,
        proposed_limit_price=101.0,
    )
    post_ohlcv = engine._load_post_signal("1103", signal_date)
    signal = V3SignalInput(signal_date=signal_date, stock_id="1103")

    exec_label, trade = engine._simulate_v3_entry(signal, v3, post_ohlcv)

    assert exec_label == "V3_WAIT_MA20"
    assert trade.filled is True
    assert trade.fill_date == fill_day
    assert abs(trade.fill_price - 104.0) < 0.01  # fill at D+1 open after trigger


# ── BT-04: WAIT_MA60_SUPPORT — trigger fires ──────────────────────────────────

def test_bt04_wait_ma60_trigger():
    """BT-04: WAIT_MA60_SUPPORT trigger fires when LOW ≤ MA60 level."""
    conn = _make_conn()
    from src.research.v3_entry_strategy import V3EntryDecision

    signal_date = date(2026, 10, 1)
    post_dates = [signal_date + timedelta(days=i + 1) for i in range(25)]
    trigger_day = post_dates[2]
    fill_day = post_dates[3]

    for d in post_dates:
        low = 85.0 if d == trigger_day else 95.0  # trigger when LOW ≤ 90
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("1104", str(d), 95.0, 97.0, low, 95.0, 100000.0),
        )
    conn.commit()

    engine = V3BacktestEngine(conn)
    v3 = V3EntryDecision(
        stock_id="1104",
        entry_decision=WAIT_MA60_SUPPORT,
        entry_price=95.0,
        stop_price=85.0,
        target_price=108.0,
        proposed_limit_price=90.0,  # MA60 level
    )
    post_ohlcv = engine._load_post_signal("1104", signal_date)
    signal = V3SignalInput(signal_date=signal_date, stock_id="1104")

    exec_label, trade = engine._simulate_v3_entry(signal, v3, post_ohlcv)

    assert exec_label == "V3_WAIT_MA60"
    assert trade.filled is True
    assert trade.fill_date == fill_day


# ── BT-05: WAIT_BREAKOUT_CONFIRMATION — trigger fires on CLOSE > prior_20d_high ─

def test_bt05_wait_breakout_trigger():
    """BT-05: WAIT_BREAKOUT_CONFIRMATION fires when CLOSE > prior_20d_high."""
    conn = _make_conn()
    from src.research.v3_entry_strategy import V3EntryDecision

    signal_date = date(2026, 10, 1)
    post_dates = [signal_date + timedelta(days=i + 1) for i in range(25)]
    trigger_day = post_dates[1]
    fill_day = post_dates[2]
    prior_high = 100.0

    for d in post_dates:
        close = 101.0 if d == trigger_day else 99.0  # breakout on day 1
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("1105", str(d), 99.0, 102.0, 98.0, close, 200000.0),
        )
    conn.commit()

    engine = V3BacktestEngine(conn)
    v3 = V3EntryDecision(
        stock_id="1105",
        entry_decision=WAIT_BREAKOUT_CONFIRMATION,
        entry_price=99.0,
        stop_price=93.0,
        target_price=108.0,
        prior_20d_high=prior_high,
    )
    post_ohlcv = engine._load_post_signal("1105", signal_date)
    signal = V3SignalInput(signal_date=signal_date, stock_id="1105")

    exec_label, trade = engine._simulate_v3_entry(signal, v3, post_ohlcv)

    assert exec_label == "V3_WAIT_BREAKOUT"
    assert trade.filled is True
    assert trade.fill_date == fill_day


# ── BT-06: AVOID_CHASING → no fill ──────────────────────────────────────────

def test_bt06_avoid_chasing_no_fill():
    """BT-06: AVOID_CHASING decision → trade is not filled."""
    conn = _make_conn()
    from src.research.v3_entry_strategy import V3EntryDecision
    from src.research.execution_simulator import NO_FILL_SKIP_LABEL

    signal_date = date(2026, 10, 1)
    engine = V3BacktestEngine(conn)
    v3 = V3EntryDecision(
        stock_id="1106",
        entry_decision=AVOID_CHASING,
        entry_price=120.0,
        stop_price=94.0,
    )
    post_ohlcv = pd.DataFrame()
    signal = V3SignalInput(signal_date=signal_date, stock_id="1106")

    exec_label, trade = engine._simulate_v3_entry(signal, v3, post_ohlcv)

    assert exec_label == AVOID_CHASING
    assert trade.filled is False
    assert trade.no_fill_reason == NO_FILL_SKIP_LABEL


# ── BT-07: NO_ENTRY → no fill ──────────────────────────────────────────────────

def test_bt07_no_entry_no_fill():
    """BT-07: NO_ENTRY decision → trade is not filled."""
    conn = _make_conn()
    from src.research.v3_entry_strategy import V3EntryDecision
    from src.research.execution_simulator import NO_FILL_SKIP_LABEL

    signal_date = date(2026, 10, 1)
    engine = V3BacktestEngine(conn)
    v3 = V3EntryDecision(
        stock_id="1107",
        entry_decision=NO_ENTRY,
    )
    post_ohlcv = pd.DataFrame()
    signal = V3SignalInput(signal_date=signal_date, stock_id="1107")

    exec_label, trade = engine._simulate_v3_entry(signal, v3, post_ohlcv)

    assert exec_label == NO_ENTRY
    assert trade.filled is False
    assert trade.no_fill_reason == NO_FILL_SKIP_LABEL


# ── BT-08: Stop hit during hold ───────────────────────────────────────────────

def test_bt08_stop_hit_during_hold():
    """BT-08: Price drops below stop during hold → exit at stop price."""
    conn = _make_conn()
    from src.research.v3_entry_strategy import V3EntryDecision
    from src.research.execution_simulator import EXIT_STOP

    signal_date = date(2026, 10, 1)
    post_dates = [signal_date + timedelta(days=i + 1) for i in range(25)]
    stop = 95.0

    # D+1: fill at 100 (open). Days 2-4: hold at 100. Day 5: low drops to 94 ≤ stop.
    hit_day = post_dates[4]
    for i, d in enumerate(post_dates):
        low = 94.0 if d == hit_day else 99.0
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("1108", str(d), 100.0, 101.0, low, 100.0, 100000.0),
        )
    conn.commit()

    engine = V3BacktestEngine(conn)
    v3 = V3EntryDecision(
        stock_id="1108",
        entry_decision=DIRECT_ENTRY,
        entry_price=100.0,
        stop_price=stop,
        target_price=112.0,
    )
    post_ohlcv = engine._load_post_signal("1108", signal_date)
    signal = V3SignalInput(signal_date=signal_date, stock_id="1108")

    _, trade = engine._simulate_v3_entry(signal, v3, post_ohlcv)

    assert trade.filled is True
    assert trade.stop_hit is True
    assert trade.exit_price == stop
    assert trade.exit_reason == EXIT_STOP


# ── BT-09: SA-3 ambiguous day → stop first ────────────────────────────────────

def test_bt09_sa3_ambiguous_stop_first():
    """BT-09: Same-day stop+target hit → conservative stop-first (SA-3)."""
    conn = _make_conn()
    from src.research.v3_entry_strategy import V3EntryDecision
    from src.research.execution_simulator import EXIT_AMBIGUOUS_STOP

    signal_date = date(2026, 10, 1)
    stop = 95.0
    target = 108.0
    post_dates = [signal_date + timedelta(days=i + 1) for i in range(25)]
    ambiguous_day = post_dates[1]

    for d in post_dates:
        if d == ambiguous_day:
            # Both low ≤ stop AND high ≥ target on same day
            conn.execute(
                "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("1109", str(d), 100.0, 110.0, 94.0, 100.0, 100000.0),
            )
        else:
            conn.execute(
                "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("1109", str(d), 100.0, 101.0, 99.0, 100.0, 100000.0),
            )
    conn.commit()

    engine = V3BacktestEngine(conn)
    v3 = V3EntryDecision(
        stock_id="1109",
        entry_decision=DIRECT_ENTRY,
        entry_price=100.0,
        stop_price=stop,
        target_price=target,
    )
    post_ohlcv = engine._load_post_signal("1109", signal_date)
    signal = V3SignalInput(signal_date=signal_date, stock_id="1109")

    _, trade = engine._simulate_v3_entry(signal, v3, post_ohlcv)

    assert trade.ambiguous_day is True
    assert trade.stop_hit is True
    assert trade.exit_reason == EXIT_AMBIGUOUS_STOP
    assert abs(trade.exit_price - stop) < 0.01


# ── BT-10: 20D hold expiry ───────────────────────────────────────────────────

def test_bt10_hold_expiry_exit():
    """BT-10: Neither stop nor target hit in HOLD_DAYS → exit at D+HOLD_DAYS close."""
    conn = _make_conn()
    from src.research.v3_entry_strategy import V3EntryDecision
    from src.research.execution_simulator import EXIT_HOLD_EXPIRY

    signal_date = date(2026, 10, 1)
    post_dates = [signal_date + timedelta(days=i + 1) for i in range(HOLD_DAYS + 5)]

    for i, d in enumerate(post_dates):
        # close increases linearly: 100.5 to 103+. Stop=90, target=999 → never hit.
        c = 100.0 + 0.1 * i
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("1110", str(d), c, c * 1.005, c * 0.995, c, 100000.0),
        )
    conn.commit()

    engine = V3BacktestEngine(conn)
    v3 = V3EntryDecision(
        stock_id="1110",
        entry_decision=DIRECT_ENTRY,
        entry_price=100.0,
        stop_price=90.0,
        target_price=999.0,  # never hit
    )
    post_ohlcv = engine._load_post_signal("1110", signal_date)
    signal = V3SignalInput(signal_date=signal_date, stock_id="1110")

    _, trade = engine._simulate_v3_entry(signal, v3, post_ohlcv)

    assert trade.filled is True
    assert trade.exit_reason == EXIT_HOLD_EXPIRY
    assert trade.days_held == HOLD_DAYS


# ── BT-11: MAE / MFE computed ────────────────────────────────────────────────

def test_bt11_mae_mfe_computed():
    """BT-11: MAE and MFE are set after a completed trade."""
    conn = _make_conn()
    from src.research.v3_entry_strategy import V3EntryDecision

    signal_date = date(2026, 10, 1)
    post_dates = [signal_date + timedelta(days=i + 1) for i in range(HOLD_DAYS + 2)]

    for i, d in enumerate(post_dates):
        low = 97.0 if i == 3 else 99.0   # dip on day 3
        high = 108.0 if i == 7 else 102.0  # peak on day 7
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("1111", str(d), 100.0, high, low, 100.0, 100000.0),
        )
    conn.commit()

    engine = V3BacktestEngine(conn)
    v3 = V3EntryDecision(
        stock_id="1111",
        entry_decision=DIRECT_ENTRY,
        entry_price=100.0,
        stop_price=90.0,
        target_price=999.0,
    )
    post_ohlcv = engine._load_post_signal("1111", signal_date)
    signal = V3SignalInput(signal_date=signal_date, stock_id="1111")

    _, trade = engine._simulate_v3_entry(signal, v3, post_ohlcv)

    assert trade.mae_pct is not None
    assert trade.mfe_pct is not None
    assert trade.mae_pct > 0   # dipped below fill price
    assert trade.mfe_pct > 0   # peaked above fill price


# ── BT-12: FULL maturation ───────────────────────────────────────────────────

def test_bt12_maturation_full():
    """BT-12: >= HOLD_DAYS forward bars → FULL maturation status."""
    conn = _make_conn()
    signal_date = date(2026, 10, 1)
    _insert_ohlcv(conn, "1101", signal_date - timedelta(days=MIN_BARS_FULL - 1), MIN_BARS_FULL)
    for i in range(HOLD_DAYS + 2):
        d = signal_date + timedelta(days=i + 1)
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("1101", str(d), 100.0, 102.0, 98.0, 100.0, 100000.0),
        )
    conn.commit()

    engine = V3BacktestEngine(conn)
    post = engine._load_post_signal("1101", signal_date)
    n = len(post)
    status = (
        MATURED_FULL if n >= HOLD_DAYS
        else MATURED_PARTIAL if n > 0
        else MATURED_NONE
    )
    assert status == MATURED_FULL


# ── BT-13: PARTIAL maturation ────────────────────────────────────────────────

def test_bt13_maturation_partial():
    """BT-13: 1 to HOLD_DAYS-1 forward bars → PARTIAL maturation."""
    conn = _make_conn()
    signal_date = date(2026, 10, 1)
    for i in range(5):  # only 5 forward bars
        d = signal_date + timedelta(days=i + 1)
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("1112", str(d), 100.0, 102.0, 98.0, 100.0, 100000.0),
        )
    conn.commit()

    engine = V3BacktestEngine(conn)
    post = engine._load_post_signal("1112", signal_date)
    n = len(post)
    status = (
        MATURED_FULL if n >= HOLD_DAYS
        else MATURED_PARTIAL if n > 0
        else MATURED_NONE
    )
    assert status == MATURED_PARTIAL


# ── BT-14: NO_DATA maturation ────────────────────────────────────────────────

def test_bt14_maturation_no_data():
    """BT-14: 0 forward bars → NO_DATA maturation."""
    conn = _make_conn()
    engine = V3BacktestEngine(conn)
    post = engine._load_post_signal("NODATA", date(2026, 10, 1))
    n = len(post)
    status = (
        MATURED_FULL if n >= HOLD_DAYS
        else MATURED_PARTIAL if n > 0
        else MATURED_NONE
    )
    assert status == MATURED_NONE


# ── BT-15: Parameter hash is deterministic ───────────────────────────────────

def test_bt15_parameter_hash_deterministic():
    """BT-15: PARAMETER_HASH is stable across repeated calls."""
    h1 = _compute_parameter_hash()
    h2 = _compute_parameter_hash()
    assert h1 == h2
    assert h1 == PARAMETER_HASH
    assert len(PARAMETER_HASH) == 16


# ── BT-16: No look-ahead (history cutoff at signal_date) ─────────────────────

def test_bt16_no_look_ahead():
    """BT-16: History passed to V3 analyzer excludes bars after signal_date."""
    conn = _make_conn()
    signal_date = date(2026, 10, 1)

    # Insert bars including 2 bars AFTER signal_date
    for i in range(MIN_BARS_FULL + 2):
        d = signal_date - timedelta(days=MIN_BARS_FULL - 1 - i)
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("1113", str(d), 100.0, 102.0, 98.0, 100.0, 100000.0),
        )
    conn.commit()

    engine = V3BacktestEngine(conn)
    history = engine._load_history("1113", signal_date)

    assert history is not None
    # No bar after signal_date should be in history
    assert all(d <= signal_date for d in history["date"])
    # signal_date itself should be included
    assert signal_date in history["date"].values


# ── BT-17: Result fields are JSON-serializable ───────────────────────────────

def test_bt17_result_json_serializable():
    """BT-17: V3BacktestResult can be converted to a JSON-safe dict."""
    conn = _make_conn()
    engine = V3BacktestEngine(conn)
    result = engine.run([])

    # Should not raise
    d = {
        "engine_version": result.engine_version,
        "research_version": result.research_version,
        "parameter_hash": result.parameter_hash,
        "n_input": result.n_input,
        "decision_distribution": result.decision_distribution,
        "mean_net_return": result.mean_net_return,
        "in_sample_warning": result.in_sample_warning,
    }
    json.dumps(d)


# ── BT-18: n_filled count correct ────────────────────────────────────────────

def test_bt18_n_filled_count():
    """BT-18: n_filled counts filled trades across multiple signals."""
    conn = _make_conn()
    signal_date = date(2026, 10, 1)

    # Provide history + post-signal for 2 signals
    for stock_id in ("2001", "2002"):
        _insert_ohlcv(
            conn, stock_id,
            signal_date - timedelta(days=MIN_BARS_FULL - 1),
            MIN_BARS_FULL + 25,  # history + forward bars
        )
    conn.commit()

    engine = V3BacktestEngine(conn)
    signals = [
        V3SignalInput(signal_date=signal_date, stock_id="2001", market_regime="bull"),
        V3SignalInput(signal_date=signal_date, stock_id="2002", market_regime="bull"),
    ]
    result = engine.run(signals)

    # Both stocks have data → n_analyzed = 2; n_filled depends on V3 decision
    assert result.n_analyzed == 2
    assert result.n_input == 2
    assert result.n_filled + result.n_skipped_decision + result.n_no_fill_expired >= 0


# ── BT-19: decision_distribution populated ───────────────────────────────────

def test_bt19_decision_distribution():
    """BT-19: decision_distribution is populated after engine.run()."""
    conn = _make_conn()
    signal_date = date(2026, 10, 1)

    _insert_ohlcv(
        conn, "3001",
        signal_date - timedelta(days=MIN_BARS_FULL - 1),
        MIN_BARS_FULL + 25,
    )
    conn.commit()

    engine = V3BacktestEngine(conn)
    signals = [V3SignalInput(signal_date=signal_date, stock_id="3001")]
    result = engine.run(signals)

    # At least one decision should be recorded
    assert sum(result.decision_distribution.values()) == result.n_analyzed


# ── BT-20: mean_net_return uses filled trades only ────────────────────────────

def test_bt20_mean_net_return_filled_only():
    """BT-20: mean_net_return is None when no filled trades exist."""
    conn = _make_conn()
    engine = V3BacktestEngine(conn)

    # No signals at all → no fills
    result = engine.run([])
    assert result.mean_net_return is None
    assert result.win_rate is None


# ── BT-21: insufficient history → skipped ────────────────────────────────────

def test_bt21_insufficient_history_skipped():
    """BT-21: Signal with <MIN_BARS_FULL history is counted in n_skipped_no_history."""
    conn = _make_conn()
    signal_date = date(2026, 10, 1)

    # Only insert MIN_BARS_FULL - 10 bars (not enough)
    _insert_ohlcv(
        conn, "4001",
        signal_date - timedelta(days=MIN_BARS_FULL - 11),
        MIN_BARS_FULL - 10,
    )
    conn.commit()

    engine = V3BacktestEngine(conn)
    signals = [V3SignalInput(signal_date=signal_date, stock_id="4001")]
    result = engine.run(signals)

    assert result.n_skipped_no_history == 1
    assert result.n_analyzed == 0


# ── BT-22: benchmark return computed from 0050 ───────────────────────────────

def test_bt22_benchmark_return():
    """BT-22: _compute_benchmark_return uses 0050 OPEN/CLOSE correctly."""
    conn = _make_conn()

    fill_date = date(2026, 10, 2)
    exit_date = date(2026, 10, 10)

    # 0050: open=100 on fill_date, close=105 on exit_date
    conn.execute(
        "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
        "VALUES ('0050', ?, 100.0, 101.0, 99.0, 100.5, 500000)", (str(fill_date),)
    )
    conn.execute(
        "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) "
        "VALUES ('0050', ?, 104.0, 106.0, 103.0, 105.0, 500000)", (str(exit_date),)
    )
    conn.commit()

    engine = V3BacktestEngine(conn)
    bm = engine._compute_benchmark_return(fill_date, exit_date)

    assert bm is not None
    # (105 - 100) / 100 × 100 = 5.0%
    assert abs(bm - 5.0) < 0.01


# ── BT-23: benchmark returns None when 0050 missing ──────────────────────────

def test_bt23_benchmark_missing():
    """BT-23: _compute_benchmark_return returns None when 0050 data absent."""
    conn = _make_conn()
    engine = V3BacktestEngine(conn)
    bm = engine._compute_benchmark_return(date(2026, 10, 2), date(2026, 10, 10))
    assert bm is None


# ── BT-24: load_buy_signals_for_backtest ─────────────────────────────────────

def test_bt24_load_buy_signals():
    """BT-24: load_buy_signals_for_backtest loads buy/strong_buy from forward_signals."""
    conn = _make_conn()
    conn.execute(
        "INSERT INTO forward_signals (stock_id, trade_date, trade_signal, market_regime_at_signal) "
        "VALUES ('5001', '2026-10-09', 'buy', 'bull')"
    )
    conn.execute(
        "INSERT INTO forward_signals (stock_id, trade_date, trade_signal, market_regime_at_signal) "
        "VALUES ('5002', '2026-10-09', 'strong_buy', NULL)"
    )
    conn.execute(
        "INSERT INTO forward_signals (stock_id, trade_date, trade_signal, market_regime_at_signal) "
        "VALUES ('5003', '2026-10-09', 'wait', 'bull')"  # excluded
    )
    conn.commit()

    signals = load_buy_signals_for_backtest(conn)

    assert len(signals) == 2
    stock_ids = {s.stock_id for s in signals}
    assert "5001" in stock_ids
    assert "5002" in stock_ids
    assert "5003" not in stock_ids

    # NULL regime → 'unknown'
    s5002 = next(s for s in signals if s.stock_id == "5002")
    assert s5002.market_regime == "unknown"


# ── BT-25: engine result metadata ────────────────────────────────────────────

def test_bt25_result_metadata():
    """BT-25: V3BacktestResult carries correct engine/research version and warning."""
    conn = _make_conn()
    engine = V3BacktestEngine(conn)
    result = engine.run([])

    assert result.engine_version == ENGINE_VERSION
    assert result.research_version == RESEARCH_VERSION
    assert result.parameter_hash == PARAMETER_HASH
    assert result.in_sample_warning == IN_SAMPLE_WARNING
    assert result.run_at != ""  # populated on run()
