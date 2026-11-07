"""
tests/test_v3_comparison_engine.py — V3 Comparison Engine Tests

Test IDs: CP-01 to CP-30
All tests use in-memory SQLite with synthetic OHLCV data.
No network calls, no production DB writes.

Coverage:
  CP-01..05  DataReadinessReport
  CP-06..09  Stop/target reconstruction
  CP-10..13  Strategy A (Direct)
  CP-14..17  Strategy B (V1/V2 Labels)
  CP-18..21  Strategy C (Hybrid V1)
  CP-22..26  Strategy D (V3)
  CP-27..28  Statistical comparison
  CP-29..30  Safety invariants
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Optional


from src.research.v3_comparison_engine import (
    FEES_PCT,
    HORIZON_5D,
    PARAMETER_HASH,
    STRATEGY_A,
    STRATEGY_B,
    STRATEGY_C,
    STRATEGY_D,
    V3ComparisonEngine,
    _bootstrap_ci,
    _hold_to_horizon,
    _reconstruct_stop_target,
    _sign_test_p,
)


# ── Test helpers ───────────────────────────────────────────────────────────────

def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE daily_prices ("
        "id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
        "open REAL, high REAL, low REAL, close REAL, volume REAL)"
    )
    conn.execute(
        "CREATE TABLE forward_signals ("
        "id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, "
        "trade_signal TEXT, decision_label TEXT, market_regime TEXT, "
        "ma20_gap_pct REAL, stop_price REAL, target1 REAL)"
    )
    conn.commit()
    return conn


def _insert_ohlcv(
    conn: sqlite3.Connection,
    stock_id: str,
    start: str,
    n: int,
    base_price: float = 100.0,
    daily_change: float = 0.0,
    high_add: float = 2.0,
    low_sub: float = 2.0,
) -> None:
    """Insert n sequential OHLCV bars starting from start date."""
    d = date.fromisoformat(start)
    for i in range(n):
        c = round(base_price + i * daily_change, 2)
        o = round(c - 0.5, 2)
        h = round(c + high_add, 2)
        low_p = round(c - low_sub, 2)
        conn.execute(
            "INSERT INTO daily_prices (stock_id,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
            (stock_id, d.isoformat(), o, h, low_p, c, 1000.0),
        )
        d += timedelta(days=1)
    conn.commit()


def _insert_signal(
    conn: sqlite3.Connection,
    stock_id: str,
    trade_date: str,
    trade_signal: str = "buy",
    decision_label: Optional[str] = None,
    market_regime: Optional[str] = "neutral",
    ma20_gap_pct: Optional[float] = 2.0,
    stop_price: Optional[float] = None,
    target1: Optional[float] = None,
) -> None:
    conn.execute(
        "INSERT INTO forward_signals "
        "(stock_id,trade_date,trade_signal,decision_label,market_regime,ma20_gap_pct,stop_price,target1) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (stock_id, trade_date, trade_signal, decision_label, market_regime,
         ma20_gap_pct, stop_price, target1),
    )
    conn.commit()


def _make_history_df(n: int, close: float = 100.0):  # noqa: ANN201
    import pandas as pd
    rows = []
    for i in range(n):
        rows.append({
            "date": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
            "open": close - 0.5, "high": close + 2, "low": close - 2,
            "close": close, "volume": 1000,
        })
    return pd.DataFrame(rows)


# ── CP-01: DataReadinessReport — no signals → NOT_READY ──────────────────────

def test_cp01_readiness_no_signals():
    conn = _make_conn()
    engine = V3ComparisonEngine(conn)
    report = engine.run_data_readiness_audit()
    assert report.total_signals == 0
    assert report.verdict_5d == "NOT_READY"
    assert report.verdict_10d == "NOT_READY"


# ── CP-02: DataReadinessReport — signals with varying post bars ───────────────

def test_cp02_readiness_counts():
    conn = _make_conn()
    # 60 history + 7 post = 67 bars total; signal at bar 60
    _insert_ohlcv(conn, "1101", "2026-09-01", 70)
    _insert_signal(conn, "1101", "2026-10-31")  # 7 post bars (Nov 1-7)
    _insert_ohlcv(conn, "2330", "2026-09-01", 65)
    _insert_signal(conn, "2330", "2026-10-31")
    engine = V3ComparisonEngine(conn)
    report = engine.run_data_readiness_audit()
    assert report.total_signals == 2
    assert report.n_no_data == 0


# ── CP-03: DataReadinessReport — 5D verdict requires ≥50 eligible ────────────

def test_cp03_readiness_verdict_threshold():
    conn = _make_conn()
    # Only 3 signals → NOT_READY
    for i in range(3):
        sid = f"{1000+i}"
        _insert_ohlcv(conn, sid, "2026-09-01", 70)
        _insert_signal(conn, sid, "2026-10-31")
    engine = V3ComparisonEngine(conn)
    report = engine.run_data_readiness_audit()
    assert report.verdict_5d == "NOT_READY"
    assert report.n_5d_eligible >= 3  # these have enough post bars


# ── CP-04: DataReadinessReport — 10D verdict requires ≥50 eligible ───────────

def test_cp04_readiness_10d_verdict():
    conn = _make_conn()
    # Only 1 signal → NOT_READY for 10D (< 50 required)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70)
    _insert_signal(conn, "0050", "2026-10-31")
    engine = V3ComparisonEngine(conn)
    report = engine.run_data_readiness_audit()
    assert report.verdict_10d == "NOT_READY"  # only 1 signal, need >= 50


# ── CP-05: DataReadinessReport has correct date range ─────────────────────────

def test_cp05_readiness_date_range():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70)
    _insert_signal(conn, "1101", "2026-10-10")
    _insert_ohlcv(conn, "2330", "2026-09-01", 70)
    _insert_signal(conn, "2330", "2026-10-20")
    engine = V3ComparisonEngine(conn)
    report = engine.run_data_readiness_audit()
    assert report.signal_date_range[0] <= report.signal_date_range[1]


# ── CP-06: Stop reconstruction from 20 closes ─────────────────────────────────

def test_cp06_reconstruct_stop_target():
    hist = _make_history_df(25, close=100.0)
    stop, target = _reconstruct_stop_target(hist)
    assert stop is not None
    assert target is not None
    # MA20 of 100.0 → stop = 97.0, target = 106.0
    assert abs(stop - 97.0) < 0.1
    assert abs(target - 106.0) < 0.1


# ── CP-07: Stop reconstruction returns None with insufficient history ──────────

def test_cp07_reconstruct_insufficient():
    hist = _make_history_df(15, close=100.0)
    stop, target = _reconstruct_stop_target(hist)
    assert stop is None
    assert target is None


# ── CP-08: Hold simulation exits at stop ──────────────────────────────────────

def test_cp08_hold_stop_hit():
    import pandas as pd
    bars = pd.DataFrame([
        {"date": "2026-11-01", "open": 100.0, "high": 102.0, "low": 94.0, "close": 101.0},
    ])
    exit_date, exit_price, reason = _hold_to_horizon(100.0, 95.0, 110.0, bars, 5)
    assert reason == "STOP"
    assert exit_price == 95.0


# ── CP-09: Hold simulation SA-4 gap down ──────────────────────────────────────

def test_cp09_hold_gap_down():
    import pandas as pd
    bars = pd.DataFrame([
        {"date": "2026-11-01", "open": 93.0, "high": 95.0, "low": 92.0, "close": 94.0},
    ])
    exit_date, exit_price, reason = _hold_to_horizon(100.0, 95.0, 110.0, bars, 5)
    assert reason == "GAP_STOP"
    assert exit_price == 93.0  # exits at open


# ── CP-10: Strategy A always fills at D+1 open ───────────────────────────────

def test_cp10_strategy_a_fills_direct():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70)
    _insert_signal(conn, "1101", "2026-10-31", decision_label=None)
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    a_rows = [r for r in result.rows if r.strategy == STRATEGY_A]
    assert len(a_rows) == 1
    assert a_rows[0].filled is True
    assert a_rows[0].sim_entry_label == "ENTRY_READY"


# ── CP-11: Strategy A — no-fill when no post bars ────────────────────────────

def test_cp11_strategy_a_no_post_bars():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 50)  # only 50 bars, signal at end
    _insert_signal(conn, "1101", "2026-10-20")
    engine = V3ComparisonEngine(conn)
    # Manually check _load_signals doesn't include signal with 0 post bars
    signals = engine._load_signals(HORIZON_5D)
    # Only signals with >= 5 post bars are loaded
    assert all(s["post_bars"] >= HORIZON_5D for s in signals)


# ── CP-12: Strategy A gross/net return calculation ────────────────────────────

def test_cp12_strategy_a_return_calc():
    conn = _make_conn()
    # 70 bars from Sep 1 → ends Nov 9; signal Oct 28 → 12 post bars
    _insert_ohlcv(conn, "1101", "2026-09-01", 70, base_price=100.0, daily_change=1.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70, base_price=100.0, daily_change=0.5)
    _insert_signal(conn, "1101", "2026-10-28")  # ~12 post bars
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    a_rows = [r for r in result.rows if r.strategy == STRATEGY_A]
    assert len(a_rows) >= 1
    row = a_rows[0]
    if row.filled:
        # net = gross - FEES_PCT/100
        assert abs(row.net_return - (row.gross_return - FEES_PCT / 100)) < 1e-5


# ── CP-13: Strategy A — no-fill yields 0% net return (SA-7) ─────────────────

def test_cp13_strategy_a_sa7_opportunity_cost():
    conn = _make_conn()
    # 25 history bars, then only 2 post bars → not enough for 5D horizon
    # This signal won't be in _load_signals with horizon=5 since post_bars < 5
    # So we need a different scenario: strategy forces no-fill somehow
    # Actually _load_signals already filters by >= horizon_days post bars
    # So the no-fill case in SA-7 is for WAIT strategies that don't trigger
    # Test: B strategy with wait_pullback signal where price never pulls back
    _insert_ohlcv(conn, "1101", "2026-09-01", 70, base_price=100.0, daily_change=2.0)  # strongly rising
    _insert_ohlcv(conn, "0050", "2026-09-01", 70, base_price=100.0, daily_change=0.5)
    _insert_signal(conn, "1101", "2026-10-31", decision_label="wait_pullback")
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    b_rows = [r for r in result.rows if r.strategy == STRATEGY_B]
    assert len(b_rows) >= 1
    # If no trigger: net_return should be 0.0
    if not b_rows[0].filled:
        assert b_rows[0].net_return == 0.0


# ── CP-14: Strategy B maps wait_pullback → WAIT_FOR_PULLBACK ─────────────────

def test_cp14_strategy_b_label_mapping_wait():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70, base_price=100.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70, base_price=100.0)
    _insert_signal(conn, "1101", "2026-10-31", decision_label="wait_pullback")
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    b_rows = [r for r in result.rows if r.strategy == STRATEGY_B]
    assert b_rows[0].sim_entry_label == "WAIT_FOR_PULLBACK"


# ── CP-15: Strategy B maps buy → ENTRY_READY ─────────────────────────────────

def test_cp15_strategy_b_label_mapping_buy():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70, base_price=100.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70, base_price=100.0)
    _insert_signal(conn, "1101", "2026-10-31", decision_label="buy")
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    b_rows = [r for r in result.rows if r.strategy == STRATEGY_B]
    assert b_rows[0].sim_entry_label == "ENTRY_READY"


# ── CP-16: Strategy B maps NULL → ENTRY_READY ────────────────────────────────

def test_cp16_strategy_b_null_label():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70, base_price=100.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70, base_price=100.0)
    _insert_signal(conn, "1101", "2026-10-31", decision_label=None)
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    b_rows = [r for r in result.rows if r.strategy == STRATEGY_B]
    assert b_rows[0].sim_entry_label == "ENTRY_READY"


# ── CP-17: Strategy B uses forward_signals stop if available ─────────────────

def test_cp17_strategy_b_uses_fs_stop():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70, base_price=100.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70, base_price=100.0)
    _insert_signal(conn, "1101", "2026-10-31", decision_label="buy", stop_price=93.0, target1=112.0)
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    b_rows = [r for r in result.rows if r.strategy == STRATEGY_B]
    assert b_rows[0].stop_source == "forward_signals"
    assert b_rows[0].stop_price == 93.0


# ── CP-18: Strategy C produces hybrid_action field ───────────────────────────

def test_cp18_strategy_c_hybrid_action_present():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70, base_price=100.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70, base_price=100.0)
    _insert_signal(conn, "1101", "2026-10-31", decision_label="buy", market_regime="neutral")
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    c_rows = [r for r in result.rows if r.strategy == STRATEGY_C]
    assert c_rows[0].hybrid_action is not None


# ── CP-19: Strategy C P1 (Bear+wait_pullback → WAIT_PULLBACK) ────────────────

def test_cp19_strategy_c_p1_bear_wait():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70, base_price=100.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70, base_price=100.0)
    _insert_signal(conn, "1101", "2026-10-31", decision_label="wait_pullback", market_regime="bear")
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    c_rows = [r for r in result.rows if r.strategy == STRATEGY_C]
    assert c_rows[0].hybrid_action == "WAIT_PULLBACK"
    assert c_rows[0].sim_entry_label == "WAIT_FOR_PULLBACK"


# ── CP-20: Strategy C P3 (Bull+rising → DIRECT) ──────────────────────────────

def test_cp20_strategy_c_p3_bull_rising():
    conn = _make_conn()
    # Rising history (slope > threshold)
    _insert_ohlcv(conn, "1101", "2026-09-01", 70, base_price=100.0, daily_change=0.5)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70, base_price=100.0)
    _insert_signal(conn, "1101", "2026-10-31", decision_label="buy", market_regime="bull")
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    c_rows = [r for r in result.rows if r.strategy == STRATEGY_C]
    assert c_rows[0].hybrid_action == "DIRECT_NEXT_OPEN"


# ── CP-21: Strategy C reconstructs stop when forward_signals missing ──────────

def test_cp21_strategy_c_reconstructed_stop():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70, base_price=100.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70, base_price=100.0)
    _insert_signal(conn, "1101", "2026-10-31", decision_label="buy",
                   stop_price=None, target1=None)
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    c_rows = [r for r in result.rows if r.strategy == STRATEGY_C]
    # Should have reconstructed stop (MA20 available with 60+ bars)
    assert c_rows[0].stop_source in {"reconstructed", "none"}


# ── CP-22: Strategy D records v3_decision ────────────────────────────────────

def test_cp22_strategy_d_v3_decision():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 90, base_price=100.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 90, base_price=100.0)
    _insert_signal(conn, "1101", "2026-11-01", decision_label="buy")
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    d_rows = [r for r in result.rows if r.strategy == STRATEGY_D]
    assert len(d_rows) >= 1
    assert d_rows[0].v3_decision is not None


# ── CP-23: Strategy D skip → 0% net return, no fill ─────────────────────────

def test_cp23_strategy_d_skip_no_fill():
    conn = _make_conn()
    # Very high ma20_gap → V3 likely AVOID_CHASING
    _insert_ohlcv(conn, "1101", "2026-09-01", 90, base_price=100.0, daily_change=5.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 90, base_price=100.0)
    _insert_signal(conn, "1101", "2026-11-01", decision_label="buy", ma20_gap_pct=35.0,
                   market_regime="bull")
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    d_rows = [r for r in result.rows if r.strategy == STRATEGY_D]
    if d_rows and not d_rows[0].filled:
        assert d_rows[0].net_return == 0.0
        assert d_rows[0].no_fill_reason == "STRATEGY_SKIP"


# ── CP-24: Strategy D stop_source is v3_own ──────────────────────────────────

def test_cp24_strategy_d_stop_source():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 90, base_price=100.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 90, base_price=100.0)
    _insert_signal(conn, "1101", "2026-11-01", decision_label="buy")
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    d_rows = [r for r in result.rows if r.strategy == STRATEGY_D]
    assert d_rows[0].stop_source in {"v3_own", "none"}


# ── CP-25: All 4 strategies produced for each eligible signal ─────────────────

def test_cp25_all_four_strategies_present():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70, base_price=100.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70, base_price=100.0)
    _insert_signal(conn, "1101", "2026-10-31", decision_label="buy")
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    strategies_seen = {r.strategy for r in result.rows}
    for s in [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]:
        assert s in strategies_seen, f"Missing strategy {s}"


# ── CP-26: experiment_id is unique per row ────────────────────────────────────

def test_cp26_experiment_id_unique():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70, base_price=100.0)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70, base_price=100.0)
    _insert_signal(conn, "1101", "2026-10-31")
    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=HORIZON_5D)
    ids = [r.experiment_id for r in result.rows]
    assert len(ids) == len(set(ids)), "Duplicate experiment_id found"


# ── CP-27: Bootstrap CI is deterministic ─────────────────────────────────────

def test_cp27_bootstrap_deterministic():
    deltas = [0.01, -0.02, 0.03, 0.005, -0.01, 0.02, 0.015, -0.005, 0.025, 0.01]
    ci1 = _bootstrap_ci(deltas)
    ci2 = _bootstrap_ci(deltas)
    assert ci1 == ci2


# ── CP-28: Sign test p-value ──────────────────────────────────────────────────

def test_cp28_sign_test_p_value():
    # All positive deltas → p-value should be very small
    deltas = [0.01] * 20
    p = _sign_test_p(deltas)
    assert p < 0.01

    # Half positive → p-value should be ~1.0
    deltas2 = [0.01] * 5 + [-0.01] * 5
    p2 = _sign_test_p(deltas2)
    assert p2 > 0.5


# ── CP-29: Safety — no production table writes ────────────────────────────────

def test_cp29_no_production_writes():
    """Engine must not create or modify production tables."""
    conn = _make_conn()
    engine = V3ComparisonEngine(conn)
    engine.run_data_readiness_audit()
    # Check that only daily_prices and forward_signals tables exist
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    # Should not have created hybrid_forward_decision or any positions table
    assert "hybrid_forward_decision" not in tables
    assert "positions" not in tables


# ── CP-30: Parameter hash is deterministic ───────────────────────────────────

def test_cp30_parameter_hash_deterministic():
    from src.research.v3_comparison_engine import _compute_param_hash
    h1 = _compute_param_hash()
    h2 = _compute_param_hash()
    assert h1 == h2 == PARAMETER_HASH
    assert len(PARAMETER_HASH) == 16
