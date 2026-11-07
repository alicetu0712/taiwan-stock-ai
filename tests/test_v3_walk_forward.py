"""
tests/test_v3_walk_forward.py — V3 Walk-forward Validation & Attribution Tests

Test IDs: WF-01 to WF-40
All tests use in-memory SQLite with synthetic data.
No network calls, no production DB writes.

Coverage:
  WF-01..06  Research Exposure Audit
  WF-07..12  Walk-forward Protocol Validator
  WF-13..20  Edge Attribution (E1/E2/E3)
  WF-21..25  Attribution Reconciliation
  WF-26..29  Date-Block Bootstrap
  WF-30..33  Cost Sensitivity
  WF-34..36  Regime Analysis
  WF-37..40  Safety Invariants
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import List, Optional

from src.research.v3_walk_forward import (
    AttributionLabel,
    FinalPerformanceVerdict,
    LeakageStatus,
    NextStageVerdict,
    StatPowerStatus,
    WFVerdict,
    V3WalkForwardEngine,
    build_exposure_audit,
    build_walk_forward_protocol,
    compute_cost_sensitivity,
    compute_edge_attribution,
    compute_regime_analysis,
    date_block_bootstrap,
    stock_cluster_bootstrap,
)
from src.research.v3_comparison_engine import (
    STRATEGY_A,
    STRATEGY_B,
    STRATEGY_C,
    STRATEGY_D,
    ComparisonRow,
    ComparisonResult,
    DataReadinessReport,
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
        "ma20_gap_pct REAL, stop_price REAL, target1 REAL, locked_at TEXT)"
    )
    conn.commit()
    return conn


def _insert_ohlcv(conn: sqlite3.Connection, stock_id: str, start: str, n: int,
                  base_price: float = 100.0, daily_change: float = 0.0) -> None:
    d = date.fromisoformat(start)
    for i in range(n):
        c = round(base_price + i * daily_change, 2)
        conn.execute(
            "INSERT INTO daily_prices (stock_id,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
            (stock_id, d.isoformat(), c - 0.5, c + 2, c - 2, c, 1000.0),
        )
        d += timedelta(days=1)
    conn.commit()


def _insert_signal(conn: sqlite3.Connection, stock_id: str, trade_date: str,
                   trade_signal: str = "buy", decision_label: Optional[str] = None,
                   market_regime: str = "neutral",
                   locked_at: str = "2026-10-08 16:00:00") -> None:
    conn.execute(
        "INSERT INTO forward_signals "
        "(stock_id,trade_date,trade_signal,decision_label,market_regime,ma20_gap_pct,locked_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (stock_id, trade_date, trade_signal, decision_label, market_regime, 2.0, locked_at),
    )
    conn.commit()


def _make_comp_row(stock_id: str, signal_date: str, strategy: str,
                   filled: bool = True, net_return: float = 0.0,
                   net_alpha: Optional[float] = None,
                   no_fill_reason: Optional[str] = None,
                   sim_entry_label: str = "ENTRY_READY",
                   market_regime: str = "bull",
                   ma20_gap_pct: float = 2.0) -> ComparisonRow:
    return ComparisonRow(
        experiment_id=f"{stock_id}_{signal_date}_{strategy}_5d",
        stock_id=stock_id,
        signal_date=signal_date,
        strategy=strategy,
        horizon_days=5,
        original_label="buy",
        market_regime=market_regime,
        ma20_gap_pct=ma20_gap_pct,
        n_post_bars=5,
        stop_price=97.0,
        target_price=106.0,
        stop_source="reconstructed",
        sim_entry_label=sim_entry_label,
        filled=filled,
        fill_date=signal_date if filled else None,
        fill_price=100.0 if filled else None,
        exit_date=signal_date if filled else None,
        exit_price=100.0 + net_return * 100 if filled else None,
        exit_reason="HORIZON" if filled else None,
        no_fill_reason=no_fill_reason,
        gross_return=net_return + 0.00585,
        net_return=net_return,
        benchmark_return=0.0,
        net_alpha=net_alpha,
    )


def _make_mock_comp_result(rows: List[ComparisonRow]) -> ComparisonResult:
    """Build a minimal ComparisonResult from pre-built rows."""
    return ComparisonResult(
        engine_id="test",
        comparison_version="test",
        parameter_hash="test",
        run_at="2026-11-06",
        horizon_days=5,
        in_sample_warning="test",
        data_readiness=DataReadinessReport(
            run_at="2026-11-06", total_signals=len(rows) // 4,
            n_5d_eligible=len(rows) // 4, n_10d_eligible=0, n_no_data=0,
            max_post_bars=5, min_post_bars=5,
            signal_date_range=("2026-10-09", "2026-10-28"),
            verdict_5d="READY", verdict_10d="NOT_READY", note="test",
        ),
        n_universe=len(rows) // 4,
        rows=rows,
        strategy_stats={},
        paired_stats=[],
        subgroup_analysis={},
    )


# ── WF-01: Exposure audit classifies signals correctly ────────────────────────

def test_wf01_exposure_classification():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70)
    _insert_signal(conn, "1101", "2026-10-31")
    audit = build_exposure_audit(conn)
    assert audit.classification == LeakageStatus.RESEARCH_EXPOSED_HISTORY
    assert audit.has_true_holdout is False
    assert audit.has_prospective_oos is False


# ── WF-02: Exposure audit populates date fields ───────────────────────────────

def test_wf02_exposure_dates():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70)
    _insert_signal(conn, "1101", "2026-10-31", locked_at="2026-10-28 10:00:00")
    audit = build_exposure_audit(conn)
    assert audit.v3_design_date == "2026-11-06"
    assert "2026-10-28" in audit.signal_creation_range[1]


# ── WF-03: Exposure audit with no signals ─────────────────────────────────────

def test_wf03_exposure_no_signals():
    conn = _make_conn()
    audit = build_exposure_audit(conn)
    assert audit.total_signals == 0
    # Classification still applies
    assert audit.classification == LeakageStatus.RESEARCH_EXPOSED_HISTORY


# ── WF-04: Exposure audit counts unique stocks and dates ─────────────────────

def test_wf04_exposure_counts():
    conn = _make_conn()
    for i in range(5):
        sid = f"{1000+i}"
        _insert_ohlcv(conn, sid, "2026-09-01", 70)
        _insert_signal(conn, sid, "2026-10-31")
    _insert_ohlcv(conn, "2000", "2026-09-01", 70)
    _insert_signal(conn, "2000", "2026-10-28")
    audit = build_exposure_audit(conn)
    assert audit.total_signals == 6
    assert audit.unique_stocks == 6
    assert audit.unique_signal_dates == 2


# ── WF-05: Exposure audit reason contains key terms ──────────────────────────

def test_wf05_exposure_reason_text():
    conn = _make_conn()
    audit = build_exposure_audit(conn)
    assert "RESEARCH_EXPOSED" in audit.classification_reason or "V3" in audit.classification_reason


# ── WF-06: Exposure audit note mentions prospective OOS ──────────────────────

def test_wf06_exposure_note():
    conn = _make_conn()
    audit = build_exposure_audit(conn)
    assert "Prospective" in audit.note or "Nov" in audit.note


# ── WF-07: Walk-forward returns INSUFFICIENT_WALK_FORWARD_DATA with real data ─

def test_wf07_wf_insufficient():
    conn = _make_conn()
    # 10 signal dates all within 20 days
    for i in range(10):
        sid = f"{1000+i}"
        _insert_ohlcv(conn, sid, "2026-09-01", 70)
        _insert_signal(conn, sid, f"2026-10-{9+i:02d}")
    result = build_walk_forward_protocol(conn)
    assert result.verdict == WFVerdict.INSUFFICIENT_WALK_FORWARD_DATA


# ── WF-08: Walk-forward n_feasible_windows = 0 ───────────────────────────────

def test_wf08_wf_no_feasible_windows():
    conn = _make_conn()
    result = build_walk_forward_protocol(conn)
    assert result.n_feasible_windows == 0


# ── WF-09: Walk-forward provides infeasibility reasons ───────────────────────

def test_wf09_wf_reasons_nonempty():
    conn = _make_conn()
    for i in range(5):
        _insert_signal(conn, f"{1000+i}", f"2026-10-{9+i:02d}")
    result = build_walk_forward_protocol(conn)
    assert len(result.infeasibility_reasons) > 0


# ── WF-10: Walk-forward builds hypothetical window for visibility ─────────────

def test_wf10_wf_hypothetical_window():
    conn = _make_conn()
    for i in range(10):
        _insert_signal(conn, f"{1000+i}", f"2026-10-{9+i:02d}")
    result = build_walk_forward_protocol(conn)
    # May or may not build hypothetical depending on date count
    # Key: feasible=False for all windows
    for w in result.windows:
        assert w.feasible is False


# ── WF-11: Walk-forward recommendation text present ──────────────────────────

def test_wf11_wf_recommendation():
    conn = _make_conn()
    result = build_walk_forward_protocol(conn)
    assert len(result.recommendation) > 10


# ── WF-12: Walk-forward parameter hash matches comparison engine ──────────────

def test_wf12_wf_parameter_hash():
    from src.research.v3_walk_forward import COMPARISON_HASH
    conn = _make_conn()
    result = build_walk_forward_protocol(conn)
    assert result.parameter_hash == COMPARISON_HASH


# ── WF-13: E1 attribution — both-filled uses net_return difference ────────────

def test_wf13_e1_both_filled():
    # D fills: -2%, A fills: -3% → E1 delta = +1%
    rows = [
        _make_comp_row("1101", "2026-10-09", STRATEGY_D, filled=True, net_return=-0.02, net_alpha=0.0),
        _make_comp_row("1101", "2026-10-09", STRATEGY_A, filled=True, net_return=-0.03, net_alpha=0.0),
        _make_comp_row("1101", "2026-10-09", STRATEGY_B, filled=True, net_return=-0.03),
        _make_comp_row("1101", "2026-10-09", STRATEGY_C, filled=True, net_return=-0.03),
    ]
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    # E1: both filled, D-A = -0.02 - (-0.03) = +0.01
    assert abs(attr.e1_case.mean_delta_net_return - 0.01) < 1e-6
    assert attr.e1_case.n_signals == 1


# ── WF-14: E2a attribution — D skip, A fill ───────────────────────────────────

def test_wf14_e2a_skip():
    # D skips (0%), A fills -4% → E2a delta = +4%
    rows = [
        _make_comp_row("1101", "2026-10-09", STRATEGY_D, filled=False,
                       net_return=0.0, no_fill_reason="STRATEGY_SKIP",
                       sim_entry_label="SKIP"),
        _make_comp_row("1101", "2026-10-09", STRATEGY_A, filled=True, net_return=-0.04),
        _make_comp_row("1101", "2026-10-09", STRATEGY_B, filled=True, net_return=-0.04),
        _make_comp_row("1101", "2026-10-09", STRATEGY_C, filled=True, net_return=-0.04),
    ]
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    assert abs(attr.e2a_case.mean_delta_net_return - 0.04) < 1e-6
    assert attr.e2a_case.n_signals == 1


# ── WF-15: E2b attribution — D wait unfired, A fill ──────────────────────────

def test_wf15_e2b_wait():
    rows = [
        _make_comp_row("1101", "2026-10-09", STRATEGY_D, filled=False,
                       net_return=0.0, no_fill_reason="NO_TRIGGER",
                       sim_entry_label="WAIT_MA20_PULLBACK"),
        _make_comp_row("1101", "2026-10-09", STRATEGY_A, filled=True, net_return=-0.05),
        _make_comp_row("1101", "2026-10-09", STRATEGY_B, filled=True, net_return=-0.05),
        _make_comp_row("1101", "2026-10-09", STRATEGY_C, filled=True, net_return=-0.05),
    ]
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    assert abs(attr.e2b_case.mean_delta_net_return - 0.05) < 1e-6
    assert attr.e2b_case.n_signals == 1


# ── WF-16: E2a counts avoided losses vs missed gains ─────────────────────────

def test_wf16_e2a_avoidance_counts():
    # 3 skips: 2 would have been losers, 1 winner
    signals = ["2026-10-09", "2026-10-10", "2026-10-11"]
    a_nets = [-0.03, -0.05, 0.02]
    rows = []
    for sig_date, a_net in zip(signals, a_nets):
        rows.append(_make_comp_row("1101", sig_date, STRATEGY_D, filled=False,
                                   net_return=0.0, no_fill_reason="STRATEGY_SKIP",
                                   sim_entry_label="SKIP"))
        rows.append(_make_comp_row("1101", sig_date, STRATEGY_A, filled=True, net_return=a_net))
        rows.append(_make_comp_row("1101", sig_date, STRATEGY_B, filled=True, net_return=a_net))
        rows.append(_make_comp_row("1101", sig_date, STRATEGY_C, filled=True, net_return=a_net))
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    assert attr.e2_avoided_loss_count == 2
    assert attr.e2_missed_gain_count == 1


# ── WF-17: E3 exposure rate matches filled count ─────────────────────────────

def test_wf17_e3_exposure():
    # 1 filled D, 1 skipped D, 2 A filled → D fill rate = 50%
    rows = [
        _make_comp_row("1101", "2026-10-09", STRATEGY_D, filled=True, net_return=-0.02),
        _make_comp_row("1101", "2026-10-09", STRATEGY_A, filled=True, net_return=-0.03),
        _make_comp_row("1101", "2026-10-09", STRATEGY_B, filled=True, net_return=-0.03),
        _make_comp_row("1101", "2026-10-09", STRATEGY_C, filled=True, net_return=-0.03),
        _make_comp_row("2330", "2026-10-09", STRATEGY_D, filled=False, net_return=0.0,
                       no_fill_reason="STRATEGY_SKIP", sim_entry_label="SKIP"),
        _make_comp_row("2330", "2026-10-09", STRATEGY_A, filled=True, net_return=-0.04),
        _make_comp_row("2330", "2026-10-09", STRATEGY_B, filled=True, net_return=-0.04),
        _make_comp_row("2330", "2026-10-09", STRATEGY_C, filled=True, net_return=-0.04),
    ]
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    assert abs(attr.d_fill_rate - 0.5) < 1e-6
    assert attr.a_fill_rate == 1.0


# ── WF-18: E3 exposure-matched A return ──────────────────────────────────────

def test_wf18_e3_exposure_matched():
    # D fills 1/2 (50%). A fills -3% per signal avg.
    # Exposure-matched A = -3% × 50% = -1.5%
    rows = [
        _make_comp_row("1101", "2026-10-09", STRATEGY_D, filled=True, net_return=-0.02),
        _make_comp_row("1101", "2026-10-09", STRATEGY_A, filled=True, net_return=-0.03),
        _make_comp_row("1101", "2026-10-09", STRATEGY_B, filled=True, net_return=-0.03),
        _make_comp_row("1101", "2026-10-09", STRATEGY_C, filled=True, net_return=-0.03),
        _make_comp_row("2330", "2026-10-09", STRATEGY_D, filled=False, net_return=0.0,
                       no_fill_reason="STRATEGY_SKIP", sim_entry_label="SKIP"),
        _make_comp_row("2330", "2026-10-09", STRATEGY_A, filled=True, net_return=-0.03),
        _make_comp_row("2330", "2026-10-09", STRATEGY_B, filled=True, net_return=-0.03),
        _make_comp_row("2330", "2026-10-09", STRATEGY_C, filled=True, net_return=-0.03),
    ]
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    assert abs(attr.exposure_matched_a_return - (-0.015)) < 1e-5


# ── WF-19: Attribution label MARKET_AVOIDANCE_DRIVEN when E2 >> E1 ───────────

def test_wf19_attribution_label_avoidance():
    # E2 large positive, E1 small negative → MARKET_AVOIDANCE_DRIVEN
    rows = []
    # 10 skips (E2a large): D=0, A=-5% each
    for i in range(10):
        d = f"2026-10-{9+i:02d}"
        rows.append(_make_comp_row(f"{1000+i}", d, STRATEGY_D, filled=False,
                                   net_return=0.0, no_fill_reason="STRATEGY_SKIP",
                                   sim_entry_label="SKIP"))
        rows.append(_make_comp_row(f"{1000+i}", d, STRATEGY_A, filled=True, net_return=-0.05))
        rows.append(_make_comp_row(f"{1000+i}", d, STRATEGY_B, filled=True, net_return=-0.05))
        rows.append(_make_comp_row(f"{1000+i}", d, STRATEGY_C, filled=True, net_return=-0.05))
    # 1 both-filled: D=-3%, A=-2.9% (small E1)
    rows.append(_make_comp_row("9999", "2026-10-20", STRATEGY_D, filled=True, net_return=-0.03))
    rows.append(_make_comp_row("9999", "2026-10-20", STRATEGY_A, filled=True, net_return=-0.029))
    rows.append(_make_comp_row("9999", "2026-10-20", STRATEGY_B, filled=True, net_return=-0.029))
    rows.append(_make_comp_row("9999", "2026-10-20", STRATEGY_C, filled=True, net_return=-0.029))
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    assert attr.attribution_label == AttributionLabel.MARKET_AVOIDANCE_DRIVEN


# ── WF-20: Attribution label ENTRY_TIMING_DRIVEN when E1 >> E2 ───────────────

def test_wf20_attribution_label_timing():
    # Many both-filled with large E1, no skips
    rows = []
    for i in range(10):
        d = f"2026-10-{9+i:02d}"
        rows.append(_make_comp_row(f"{1000+i}", d, STRATEGY_D, filled=True, net_return=0.05))
        rows.append(_make_comp_row(f"{1000+i}", d, STRATEGY_A, filled=True, net_return=-0.05))
        rows.append(_make_comp_row(f"{1000+i}", d, STRATEGY_B, filled=True, net_return=-0.05))
        rows.append(_make_comp_row(f"{1000+i}", d, STRATEGY_C, filled=True, net_return=-0.05))
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    assert attr.attribution_label in {AttributionLabel.ENTRY_TIMING_DRIVEN, AttributionLabel.MIXED_ATTRIBUTION}


# ── WF-21: Reconciliation sums correctly ─────────────────────────────────────

def test_wf21_reconciliation_exact():
    rows = []
    # Mix: 2 both-filled, 1 skip, 1 wait
    for sig, nr_d, nr_a, filled, skip in [
        ("2026-10-09", -0.02, -0.03, True, False),
        ("2026-10-10", -0.04, -0.03, True, False),
        ("2026-10-11", 0.0, -0.05, False, True),   # skip
        ("2026-10-12", 0.0, -0.02, False, False),  # wait unfired
    ]:
        rows.append(_make_comp_row("1101", sig, STRATEGY_D, filled=filled,
                                   net_return=nr_d,
                                   no_fill_reason="STRATEGY_SKIP" if skip else ("NO_TRIGGER" if not filled else None),
                                   sim_entry_label="SKIP" if skip else "WAIT_MA20_PULLBACK" if not filled else "DIRECT_ENTRY"))
        rows.append(_make_comp_row("1101", sig, STRATEGY_A, filled=True, net_return=nr_a))
        rows.append(_make_comp_row("1101", sig, STRATEGY_B, filled=True, net_return=nr_a))
        rows.append(_make_comp_row("1101", sig, STRATEGY_C, filled=True, net_return=nr_a))
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    r = attr.reconciliation
    assert r.reconciliation_check is True, f"Residual too large: {r.residual}"
    assert abs(r.residual) < 1e-6


# ── WF-22: Reconciliation N_total matches ─────────────────────────────────────

def test_wf22_reconciliation_n():
    rows = []
    for i in range(6):
        d = f"2026-10-{9+i:02d}"
        for s in [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]:
            rows.append(_make_comp_row(f"{1000+i}", d, s, filled=True, net_return=-0.02))
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    assert attr.reconciliation.n_total == 6


# ── WF-23: Reconciliation overall_delta matches observed ─────────────────────

def test_wf23_reconciliation_overall():
    # D: -2%, A: -4% → overall = +2%
    rows = [
        _make_comp_row("1101", "2026-10-09", STRATEGY_D, filled=True, net_return=-0.02),
        _make_comp_row("1101", "2026-10-09", STRATEGY_A, filled=True, net_return=-0.04),
        _make_comp_row("1101", "2026-10-09", STRATEGY_B, filled=True, net_return=-0.04),
        _make_comp_row("1101", "2026-10-09", STRATEGY_C, filled=True, net_return=-0.04),
    ]
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    assert abs(attr.reconciliation.overall_delta_net_return - 0.02) < 1e-6


# ── WF-24: Attribution selection bias warning present ─────────────────────────

def test_wf24_e1_selection_bias_warning():
    rows = [
        _make_comp_row("1101", "2026-10-09", s, filled=True, net_return=-0.02)
        for s in [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]
    ]
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    assert "SELECTION BIAS" in attr.e1_case.selection_bias_warning


# ── WF-25: Attribution experiment_id contains horizon ─────────────────────────

def test_wf25_experiment_id():
    rows = [
        _make_comp_row("1101", "2026-10-09", s, filled=True, net_return=-0.02)
        for s in [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]
    ]
    comp = _make_mock_comp_result(rows)
    attr = compute_edge_attribution(comp)
    assert "5d" in attr.experiment_id


# ── WF-26: Date-block bootstrap returns effective_n_warning when n < 5 ────────

def test_wf26_date_block_insufficient():
    # Only 3 date-blocks
    rows_d, rows_a = [], []
    for i in range(3):
        d = f"2026-10-{9+i:02d}"
        for j in range(5):
            rows_d.append(_make_comp_row(f"{1000+j}", d, STRATEGY_D, net_return=-0.02))
            rows_a.append(_make_comp_row(f"{1000+j}", d, STRATEGY_A, net_return=-0.03))
    result = date_block_bootstrap(rows_d, rows_a)
    assert result.n_date_blocks == 3
    # Insufficient for CI
    assert "insufficient" in result.effective_n_warning.lower()


# ── WF-27: Date-block bootstrap is deterministic ─────────────────────────────

def test_wf27_date_block_deterministic():
    rows_d, rows_a = [], []
    for i in range(10):
        d = f"2026-10-{9+i:02d}"
        rows_d.append(_make_comp_row("1101", d, STRATEGY_D, net_return=-0.02))
        rows_a.append(_make_comp_row("1101", d, STRATEGY_A, net_return=-0.03))
    r1 = date_block_bootstrap(rows_d, rows_a)
    r2 = date_block_bootstrap(rows_d, rows_a)
    assert r1.ci_lower == r2.ci_lower
    assert r1.ci_upper == r2.ci_upper


# ── WF-28: Stock-cluster bootstrap uses stock_id as unit ─────────────────────

def test_wf28_stock_cluster():
    rows_d, rows_a = [], []
    for i in range(20):  # 20 stocks
        sid = f"{1000+i}"
        d = "2026-10-09"
        rows_d.append(_make_comp_row(sid, d, STRATEGY_D, net_return=-0.02))
        rows_a.append(_make_comp_row(sid, d, STRATEGY_A, net_return=-0.03))
    result = stock_cluster_bootstrap(rows_d, rows_a)
    assert result.n_stock_clusters == 20


# ── WF-29: Stock-cluster bootstrap observed mean correct ─────────────────────

def test_wf29_stock_cluster_mean():
    rows_d, rows_a = [], []
    for i in range(10):
        sid = f"{1000+i}"
        d = "2026-10-09"
        rows_d.append(_make_comp_row(sid, d, STRATEGY_D, net_return=-0.02))
        rows_a.append(_make_comp_row(sid, d, STRATEGY_A, net_return=-0.04))
    result = stock_cluster_bootstrap(rows_d, rows_a)
    # D-A = -0.02 - (-0.04) = +0.02
    assert abs(result.observed_mean - 0.02) < 1e-5


# ── WF-30: Cost sensitivity returns all scenarios ────────────────────────────

def test_wf30_cost_scenarios_all_present():
    rows = []
    for i in range(5):
        d = f"2026-10-{9+i:02d}"
        for s in [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]:
            rows.append(_make_comp_row(f"{1000+i}", d, s, filled=True, net_return=-0.02))
    comp = _make_mock_comp_result(rows)
    results = compute_cost_sensitivity(comp)
    scenario_ids = {r.scenario_id for r in results}
    from src.research.v3_walk_forward import COST_SCENARIOS
    assert scenario_ids == set(COST_SCENARIOS.keys())


# ── WF-31: Cost sensitivity base scenario matches observed ───────────────────

def test_wf31_cost_base_scenario():
    rows = []
    for s in [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]:
        rows.append(_make_comp_row("1101", "2026-10-09", s, filled=True,
                                   net_return=-0.02 if s == STRATEGY_D else -0.03))
    comp = _make_mock_comp_result(rows)
    results = compute_cost_sensitivity(comp)
    base = next(r for r in results if r.scenario_id == "base")
    # D-A delta should be +0.01 in base
    assert abs(base.mean_delta - 0.01) < 1e-5


# ── WF-32: Conservative scenario reduces advantage ───────────────────────────

def test_wf32_conservative_reduces_advantage():
    rows = []
    for s in [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]:
        rows.append(_make_comp_row("1101", "2026-10-09", s, filled=True,
                                   net_return=-0.02 if s == STRATEGY_D else -0.03))
    comp = _make_mock_comp_result(rows)
    results = compute_cost_sensitivity(comp)
    base = next(r for r in results if r.scenario_id == "base")
    cons = next(r for r in results if r.scenario_id == "conservative")
    # Conservative should reduce D-A advantage (higher costs hurt fills more)
    assert cons.mean_delta <= base.mean_delta + 1e-6


# ── WF-33: Cost sensitivity result has verdict field ─────────────────────────

def test_wf33_cost_verdict():
    rows = []
    for s in [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]:
        rows.append(_make_comp_row("1101", "2026-10-09", s, filled=True, net_return=-0.02))
    comp = _make_mock_comp_result(rows)
    results = compute_cost_sensitivity(comp)
    for r in results:
        assert r.verdict in {"COST_SENSITIVE_EDGE", "ROBUST", "MARGINAL"}


# ── WF-34: Regime analysis groups by market_regime ───────────────────────────

def test_wf34_regime_groups():
    rows = []
    for regime, dates in [("bull", ["2026-10-09", "2026-10-10"]),
                           ("bear", ["2026-10-11"])]:
        for d in dates:
            for s in [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]:
                rows.append(_make_comp_row("1101", d, s, net_return=-0.02,
                                           market_regime=regime))
    comp = _make_mock_comp_result(rows)
    results = compute_regime_analysis(comp)
    regimes = {r.regime for r in results}
    assert "bull" in regimes
    assert "bear" in regimes


# ── WF-35: Regime analysis stat_power insufficient for small n ────────────────

def test_wf35_regime_stat_power():
    rows = []
    for s in [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]:
        rows.append(_make_comp_row("1101", "2026-10-09", s, net_return=-0.02,
                                   market_regime="bull"))
    comp = _make_mock_comp_result(rows)
    results = compute_regime_analysis(comp)
    bull = next(r for r in results if r.regime == "bull")
    assert bull.stat_power == StatPowerStatus.INSUFFICIENT_STATISTICAL_POWER


# ── WF-36: Regime analysis shows all regimes including negative ───────────────

def test_wf36_all_regimes_reported():
    rows = []
    for regime, dates in [("bull", ["2026-10-09"]), ("bear", ["2026-10-10"])]:
        for d in dates:
            for s in [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]:
                rows.append(_make_comp_row("1101", d, s, net_return=-0.03,
                                           market_regime=regime))
    comp = _make_mock_comp_result(rows)
    results = compute_regime_analysis(comp)
    # Even negative-performing regimes should appear
    assert len(results) == 2


# ── WF-37: Safety — no production table writes ───────────────────────────────

def test_wf37_no_production_writes():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70)
    _insert_signal(conn, "1101", "2026-10-28")
    engine = V3WalkForwardEngine(conn)
    engine.run()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "hybrid_forward_decision" not in tables
    assert "positions" not in tables


# ── WF-38: Safety — final verdict is PROSPECTIVE_SHADOW_CONDITIONAL ──────────

def test_wf38_next_stage_verdict():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70)
    _insert_signal(conn, "1101", "2026-10-28")
    engine = V3WalkForwardEngine(conn)
    report = engine.run()
    assert report.next_stage_verdict == NextStageVerdict.PROSPECTIVE_SHADOW_CONDITIONAL


# ── WF-39: Safety — performance verdict is INSUFFICIENT_EVIDENCE ─────────────

def test_wf39_performance_verdict():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70)
    _insert_signal(conn, "1101", "2026-10-28")
    engine = V3WalkForwardEngine(conn)
    report = engine.run()
    assert report.performance_verdict == FinalPerformanceVerdict.INSUFFICIENT_EVIDENCE


# ── WF-40: Safety — in_sample_warning non-empty ──────────────────────────────

def test_wf40_in_sample_warning():
    conn = _make_conn()
    _insert_ohlcv(conn, "1101", "2026-09-01", 70)
    _insert_ohlcv(conn, "0050", "2026-09-01", 70)
    _insert_signal(conn, "1101", "2026-10-28")
    engine = V3WalkForwardEngine(conn)
    report = engine.run()
    assert len(report.in_sample_warning) > 20
