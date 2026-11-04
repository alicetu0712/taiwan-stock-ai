"""
tests/test_execution_simulator.py — OHLC-based execution simulation tests.

Tests (ES):
  ES01 — V1 NEXT_OPEN entry at open of first post-signal bar
  ES02 — V2 ENTRY_READY same as V1 (NEXT_OPEN)
  ES03 — V2 WAIT_FOR_PULLBACK fills when LOW ≤ MA20_est × 1.03 (SA-1)
  ES04 — V2 WAIT_FOR_PULLBACK expires without trigger → NO_FILL / EXPIRED
  ES05 — V2 WAIT_FOR_BREAKOUT fills when CLOSE > prior_20d_high (SA-2)
  ES06 — V2 WAIT_FOR_BREAKOUT expires → NO_FILL / EXPIRED
  ES07 — Skip labels (TOO_EXTENDED etc.) → no fill immediately
  ES08 — Stop hit during hold → exit at stop_price
  ES09 — Target hit during hold → exit at target_price
  ES10 — SA-3: same-day stop + target → STOP FIRST (exit at stop_price)
  ES11 — SA-4: gap down through stop on entry → exit at open
  ES12 — SA-4: gap down on hold day → exit at open
  ES13 — SA-5: 20-bar hold expiry → exit at close
  ES14 — No OHLCV after signal → no fill / INSUFFICIENT_HIST
  ES15 — net_return_pct = gross - 0.585% (SA-6)
  ES16 — MAE tracked correctly (worst low below entry)
  ES17 — MFE tracked correctly (best high above entry)
  ES18 — R-Multiple: (exit - fill) / (fill - stop)
  ES19 — No look-ahead: trigger from previous close only, entry at NEXT open
  ES20 — V2 WAIT_FOR_PULLBACK: second-day trigger (not first-day)
  ES21 — V1 uses DIRECT_NEXT_OPEN entry_order_type
  ES22 — WAIT_FOR_PULLBACK uses CONFIRMED_NEXT_OPEN entry_order_type
  ES23 — ma20_trigger_price() = stop/(1-0.03)×(1+0.03) ≈ stop×1.062
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from src.research.execution_simulator import (
    ENTRY_CONFIRMED_NEXT_OPEN,
    ENTRY_DIRECT_NEXT_OPEN,
    EXPIRY_DAYS,
    EXIT_AMBIGUOUS_STOP,
    EXIT_GAP_STOP,
    EXIT_HOLD_EXPIRY,
    EXIT_STOP,
    EXIT_TARGET,
    FEES_PCT,
    HOLD_DAYS,
    MA20_TRIGGER_BUFFER,
    NO_FILL_EXPIRED,
    NO_FILL_NO_HIST,
    NO_FILL_SKIP_LABEL,
    STOP_BUFFER,
    EntryTimingExecutionSimulator,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ohlcv(
    start_date: date,
    n: int,
    open_price: float = 100.0,
    close_price: float = 100.0,
    high_offset: float = 2.0,
    low_offset: float = -2.0,
    volume: int = 1_000_000,
) -> pd.DataFrame:
    """n flat OHLCV bars from start_date."""
    rows = []
    for i in range(n):
        d = start_date + timedelta(days=i)
        rows.append({
            "date": d,
            "open": open_price,
            "high": close_price + high_offset,
            "low": close_price + low_offset,
            "close": close_price,
            "volume": volume,
        })
    return pd.DataFrame(rows)


def _custom_ohlcv(rows):
    """Build OHLCV from list of (date, open, high, low, close, volume)."""
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


sim = EntryTimingExecutionSimulator()
SIGNAL_DATE = date(2026, 6, 1)


# ── Basic Entry Tests ─────────────────────────────────────────────────────────

class TestV1Entry:
    def test_ES01_v1_next_open_entry(self):
        ohlcv = _make_ohlcv(SIGNAL_DATE + timedelta(days=1), 25, open_price=102.0)
        t = sim.simulate_v1(SIGNAL_DATE, "T01", stop_price=90.0, target_price=130.0, ohlcv=ohlcv)
        assert t.filled is True
        assert t.fill_date == SIGNAL_DATE + timedelta(days=1)
        assert t.fill_price == 102.0

    def test_ES02_v2_entry_ready_same_as_v1(self):
        ohlcv = _make_ohlcv(SIGNAL_DATE + timedelta(days=1), 25, open_price=105.0)
        t = sim.simulate_v2(
            SIGNAL_DATE, "T02", "ENTRY_READY",
            planned_entry=103.0, stop_price=90.0, target_price=130.0, ohlcv=ohlcv,
        )
        assert t.filled is True
        assert t.fill_price == 105.0
        assert t.fill_date == SIGNAL_DATE + timedelta(days=1)

    def test_ES14_no_ohlcv_no_fill(self):
        t = sim.simulate_v1(SIGNAL_DATE, "T14", stop_price=90.0, target_price=130.0,
                            ohlcv=pd.DataFrame())
        assert t.filled is False
        assert t.no_fill_reason == NO_FILL_NO_HIST


# ── WAIT_FOR_PULLBACK Tests ────────────────────────────────────────────────────

class TestWaitForPullback:
    def test_ES03_pullback_trigger_sa1(self):
        """Fill when LOW ≤ MA20_est × 1.03. MA20_est = stop / 0.97."""
        stop = 92.23  # MA20 = 95.08, threshold = 97.93
        ma20_est = stop / 0.97
        threshold = ma20_est * 1.03  # ≈97.9

        # Day 1: low = 100 (above threshold), no trigger
        # Day 2: low = 97.0 (below threshold), trigger
        rows = [
            (SIGNAL_DATE + timedelta(days=1), 103.0, 105.0, 100.0, 103.0, 1_000_000),
            (SIGNAL_DATE + timedelta(days=2), 101.0, 103.0, 97.0, 101.0, 1_000_000),
            # Day after trigger: entry
            (SIGNAL_DATE + timedelta(days=3), 100.5, 115.0, 95.0, 110.0, 1_000_000),
        ] + [
            (SIGNAL_DATE + timedelta(days=4 + i), 110.0, 112.0, 108.0, 110.0, 1_000_000)
            for i in range(25)
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v2(
            SIGNAL_DATE, "T03", "WAIT_FOR_PULLBACK",
            planned_entry=103.0, stop_price=stop, target_price=130.0,
            ohlcv=ohlcv, expiry_days=EXPIRY_DAYS,
        )
        assert t.filled is True
        # Entry is at OPEN of bar AFTER the trigger bar (day 3 = day+3)
        assert t.fill_date == SIGNAL_DATE + timedelta(days=3)
        assert t.fill_price == 100.5
        assert "[SA-1]" in t.simulation_note

    def test_ES04_pullback_expires(self):
        """No trigger within expiry_days → no fill / EXPIRED."""
        ohlcv = _make_ohlcv(
            SIGNAL_DATE + timedelta(days=1), 30,
            open_price=110.0, close_price=110.0,
            high_offset=2.0, low_offset=-2.0,  # low = 108, well above pullback zone
        )
        t = sim.simulate_v2(
            SIGNAL_DATE, "T04", "WAIT_FOR_PULLBACK",
            planned_entry=103.0, stop_price=92.0, target_price=130.0,
            ohlcv=ohlcv, expiry_days=EXPIRY_DAYS,
        )
        assert t.filled is False
        assert t.no_fill_reason == NO_FILL_EXPIRED

    def test_ES20_pullback_trigger_on_second_day(self):
        """Trigger on day 2, not day 1 (first day has low above threshold)."""
        stop = 90.0
        ma20_est = stop / 0.97
        threshold = ma20_est * 1.03  # ≈95.56

        rows = [
            (SIGNAL_DATE + timedelta(days=1), 100.0, 102.0, 97.0, 100.0, 1_000_000),  # low=97>95.56? 97>95.56 yes → triggers
        ]
        # Actually 97 > 95.56, so it SHOULD trigger on day 1.
        # To have day-2 trigger: need day 1 low > 95.56
        rows = [
            (SIGNAL_DATE + timedelta(days=1), 100.0, 102.0, 96.5, 100.0, 1_000_000),  # 96.5 > 95.56 → triggers
        ]
        # 96.5 > 95.56 triggers too. Need a higher threshold to avoid day-1 trigger.
        stop2 = 85.0
        ma20_est2 = stop2 / 0.97  # ≈87.6
        threshold2 = ma20_est2 * 1.03  # ≈90.2

        # Day 1 low = 95.0 > 90.2 → no trigger
        # Day 2 low = 89.0 < 90.2 → trigger
        rows2 = [
            (SIGNAL_DATE + timedelta(days=1), 100.0, 102.0, 95.0, 100.0, 1_000_000),
            (SIGNAL_DATE + timedelta(days=2), 100.0, 101.0, 89.0,  99.0, 1_000_000),
            (SIGNAL_DATE + timedelta(days=3),  98.0, 110.0, 97.0, 108.0, 1_000_000),
        ] + [
            (SIGNAL_DATE + timedelta(days=4 + i), 108.0, 110.0, 106.0, 109.0, 1_000_000)
            for i in range(25)
        ]
        ohlcv2 = _custom_ohlcv(rows2)
        t = sim.simulate_v2(
            SIGNAL_DATE, "T20", "WAIT_FOR_PULLBACK",
            planned_entry=100.0, stop_price=85.0, target_price=130.0,
            ohlcv=ohlcv2, expiry_days=EXPIRY_DAYS,
        )
        assert t.filled is True
        # Entry bar is day 3 (bar after day-2 trigger)
        assert t.fill_date == SIGNAL_DATE + timedelta(days=3)


# ── WAIT_FOR_BREAKOUT Tests ────────────────────────────────────────────────────

class TestWaitForBreakout:
    def test_ES05_breakout_trigger_sa2(self):
        """Fill when CLOSE > prior_20d_high."""
        prior_high = 108.0
        # Day 1: close = 106 (no breakout)
        # Day 2: close = 109 (breakout!)
        rows = [
            (SIGNAL_DATE + timedelta(days=1), 105.0, 107.0, 103.0, 106.0, 1_000_000),
            (SIGNAL_DATE + timedelta(days=2), 107.0, 110.0, 105.0, 109.0, 1_200_000),
            # Day after breakout: entry
            (SIGNAL_DATE + timedelta(days=3), 110.0, 115.0, 108.0, 112.0, 1_000_000),
        ] + [
            (SIGNAL_DATE + timedelta(days=4 + i), 112.0, 114.0, 110.0, 113.0, 1_000_000)
            for i in range(25)
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v2(
            SIGNAL_DATE, "T05", "WAIT_FOR_BREAKOUT",
            planned_entry=105.0, stop_price=90.0, target_price=130.0,
            ohlcv=ohlcv, prior_20d_high=prior_high, expiry_days=EXPIRY_DAYS,
        )
        assert t.filled is True
        # Entry: OPEN of bar after breakout trigger (day 3)
        assert t.fill_date == SIGNAL_DATE + timedelta(days=3)
        assert t.fill_price == 110.0
        assert "[SA-2]" in t.simulation_note

    def test_ES06_breakout_expires(self):
        """No close > prior_20d_high within expiry → no fill / EXPIRED."""
        ohlcv = _make_ohlcv(SIGNAL_DATE + timedelta(days=1), 20, close_price=100.0)
        t = sim.simulate_v2(
            SIGNAL_DATE, "T06", "WAIT_FOR_BREAKOUT",
            planned_entry=100.0, stop_price=90.0, target_price=130.0,
            ohlcv=ohlcv, prior_20d_high=110.0, expiry_days=EXPIRY_DAYS,
        )
        assert t.filled is False
        assert t.no_fill_reason == NO_FILL_EXPIRED


# ── Skip Labels ────────────────────────────────────────────────────────────────

class TestSkipLabels:
    @pytest.mark.parametrize("label", [
        "TOO_EXTENDED", "NO_VALID_SETUP",
        "RISK_REWARD_UNFAVORABLE", "INSUFFICIENT_DATA",
    ])
    def test_ES07_skip_labels_no_fill(self, label):
        ohlcv = _make_ohlcv(SIGNAL_DATE + timedelta(days=1), 30)
        t = sim.simulate_v2(
            SIGNAL_DATE, "T07", label,
            planned_entry=100.0, stop_price=90.0, target_price=130.0, ohlcv=ohlcv,
        )
        assert t.filled is False
        assert t.no_fill_reason == NO_FILL_SKIP_LABEL


# ── Exit Rules ────────────────────────────────────────────────────────────────

class TestExitRules:
    def test_ES08_stop_hit(self):
        """Stop hit during hold → exit at stop_price."""
        stop = 90.0
        target = 130.0
        # Entry at 100, then price falls below stop on day 3
        rows = [
            (SIGNAL_DATE + timedelta(days=1), 100.0, 105.0, 98.0, 102.0, 1_000_000),  # entry day
            (SIGNAL_DATE + timedelta(days=2), 102.0, 104.0, 95.0, 101.0, 1_000_000),  # hold day 1
            (SIGNAL_DATE + timedelta(days=3), 100.0, 102.0, 88.0,  89.0, 1_000_000),  # hold day 2: low < stop
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v1(SIGNAL_DATE, "T08", stop_price=stop, target_price=target, ohlcv=ohlcv)
        assert t.filled is True
        assert t.stop_hit is True
        assert t.exit_reason == EXIT_STOP
        assert t.exit_price == stop

    def test_ES09_target_hit(self):
        """Target hit → exit at target_price."""
        stop = 90.0
        target = 115.0
        rows = [
            (SIGNAL_DATE + timedelta(days=1), 100.0, 102.0, 98.0, 101.0, 1_000_000),  # entry
            (SIGNAL_DATE + timedelta(days=2), 101.0, 116.0, 100.0, 114.0, 1_000_000),  # high > target
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v1(SIGNAL_DATE, "T09", stop_price=stop, target_price=target, ohlcv=ohlcv)
        assert t.filled is True
        assert t.target_hit is True
        assert t.exit_reason == EXIT_TARGET
        assert t.exit_price == target

    def test_ES10_sa3_ambiguous_stop_first(self):
        """SA-3: same day LOW ≤ stop AND HIGH ≥ target → STOP FIRST."""
        stop = 90.0
        target = 115.0
        rows = [
            (SIGNAL_DATE + timedelta(days=1), 100.0, 102.0, 98.0, 100.0, 1_000_000),  # entry
            (SIGNAL_DATE + timedelta(days=2), 100.0, 118.0, 88.0, 100.0, 1_000_000),  # ambiguous!
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v1(SIGNAL_DATE, "T10", stop_price=stop, target_price=target, ohlcv=ohlcv)
        assert t.filled is True
        assert t.ambiguous_day is True
        assert t.stop_hit is True
        assert t.exit_reason == EXIT_AMBIGUOUS_STOP
        assert t.exit_price == stop

    def test_ES11_sa4_gap_down_on_entry(self):
        """SA-4: OPEN ≤ stop on entry day → exit at open."""
        stop = 95.0
        rows = [
            (SIGNAL_DATE + timedelta(days=1), 93.0, 97.0, 91.0, 94.0, 1_000_000),  # open < stop
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v1(SIGNAL_DATE, "T11", stop_price=stop, target_price=130.0, ohlcv=ohlcv)
        assert t.filled is True
        assert t.gap_slippage is True
        assert t.exit_reason == EXIT_GAP_STOP
        assert t.exit_price == 93.0  # exit at open (gap)

    def test_ES12_sa4_gap_down_on_hold_day(self):
        """SA-4: gap down through stop on a hold day → exit at open."""
        stop = 95.0
        rows = [
            (SIGNAL_DATE + timedelta(days=1), 100.0, 102.0, 98.0, 100.0, 1_000_000),  # entry ok
            (SIGNAL_DATE + timedelta(days=2), 100.0, 103.0, 97.0, 101.0, 1_000_000),  # hold day 1 ok
            (SIGNAL_DATE + timedelta(days=3),  93.0,  95.0,  91.0, 92.0, 1_000_000),  # hold day 2: open < stop
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v1(SIGNAL_DATE, "T12", stop_price=stop, target_price=130.0, ohlcv=ohlcv)
        assert t.filled is True
        assert t.gap_slippage is True
        assert t.exit_reason == EXIT_GAP_STOP
        assert t.exit_price == 93.0

    def test_ES13_sa5_hold_expiry(self):
        """SA-5: after HOLD_DAYS bars → exit at CLOSE of last bar."""
        ohlcv = _make_ohlcv(
            SIGNAL_DATE + timedelta(days=1),
            HOLD_DAYS + 5,  # more than enough
            open_price=100.0, close_price=105.0,
            high_offset=2.0, low_offset=-2.0,  # high=107, low=103 — not stop/target
        )
        t = sim.simulate_v1(SIGNAL_DATE, "T13", stop_price=80.0, target_price=200.0, ohlcv=ohlcv)
        assert t.filled is True
        assert t.exit_reason == EXIT_HOLD_EXPIRY
        assert t.days_held == HOLD_DAYS


# ── P&L and Risk Metrics ───────────────────────────────────────────────────────

class TestPnlMetrics:
    def test_ES15_net_return_deducts_fees(self):
        """net_return = gross - 0.585% (SA-6)."""
        rows = [
            (SIGNAL_DATE + timedelta(days=1), 100.0, 102.0, 98.0, 100.0, 1_000_000),
        ] + [
            (SIGNAL_DATE + timedelta(days=2 + i), 100.0, 102.0, 98.0, 110.0, 1_000_000)
            for i in range(HOLD_DAYS)
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v1(SIGNAL_DATE, "T15", stop_price=80.0, target_price=200.0, ohlcv=ohlcv)
        assert t.filled is True
        assert t.exit_reason == EXIT_HOLD_EXPIRY
        assert t.gross_return_pct is not None
        assert t.net_return_pct is not None
        assert abs(t.net_return_pct - (t.gross_return_pct - FEES_PCT)) < 0.0001

    def test_ES16_mae_tracked(self):
        """MAE = worst low below entry / entry * 100."""
        fill = 100.0
        worst_low = 92.0  # MAE = (100 - 92) / 100 * 100 = 8%
        rows = [
            (SIGNAL_DATE + timedelta(days=1), fill, fill + 2, fill - 2, fill, 1_000_000),
        ] + [
            (SIGNAL_DATE + timedelta(days=2 + i),
             fill, fill + 2, worst_low if i == 3 else fill - 2, fill, 1_000_000)
            for i in range(HOLD_DAYS)
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v1(SIGNAL_DATE, "T16", stop_price=80.0, target_price=200.0, ohlcv=ohlcv)
        assert t.filled is True
        assert t.mae_pct is not None
        assert abs(t.mae_pct - 8.0) < 0.01

    def test_ES17_mfe_tracked(self):
        """MFE = best high above entry / entry * 100."""
        fill = 100.0
        best_high = 115.0  # MFE = (115 - 100) / 100 * 100 = 15%
        rows = [
            (SIGNAL_DATE + timedelta(days=1), fill, fill + 2, fill - 2, fill, 1_000_000),
        ] + [
            (SIGNAL_DATE + timedelta(days=2 + i),
             fill, best_high if i == 5 else fill + 2, fill - 2, fill, 1_000_000)
            for i in range(HOLD_DAYS)
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v1(SIGNAL_DATE, "T17", stop_price=80.0, target_price=200.0, ohlcv=ohlcv)
        assert t.filled is True
        assert t.mfe_pct is not None
        assert abs(t.mfe_pct - 15.0) < 0.01

    def test_ES18_r_multiple(self):
        """R-Multiple = (exit - fill) / (fill - stop)."""
        fill = 100.0
        stop = 90.0  # risk = 10
        target = 120.0  # reward = 20 → R=2.0
        rows = [
            (SIGNAL_DATE + timedelta(days=1), fill, fill + 2, fill - 2, fill, 1_000_000),
            (SIGNAL_DATE + timedelta(days=2), fill, 121.0, fill - 1, fill, 1_000_000),  # target hit
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v1(SIGNAL_DATE, "T18", stop_price=stop, target_price=target, ohlcv=ohlcv)
        assert t.filled is True
        assert t.target_hit is True
        # R-multiple = (120 - 100) / (100 - 90) = 2.0
        assert abs(t.r_multiple - 2.0) < 0.01


# ── No Look-ahead Tests ───────────────────────────────────────────────────────

class TestNoLookAhead:
    def test_ES19_no_lookahead_trigger_requires_next_open_entry(self):
        """
        WAIT_FOR_BREAKOUT: trigger on day D (close > prior_high) →
        entry must be at OPEN of day D+1 (NOT day D close or high).
        """
        prior_high = 108.0
        # Day 1: close = 109 (breakout) but we cannot enter at 109.
        # Entry must be at OPEN of day 2.
        rows = [
            (SIGNAL_DATE + timedelta(days=1), 107.0, 110.0, 105.0, 109.0, 1_200_000),  # trigger
            (SIGNAL_DATE + timedelta(days=2), 111.0, 115.0, 109.0, 113.0, 1_000_000),  # entry here
        ] + [
            (SIGNAL_DATE + timedelta(days=3 + i), 113.0, 115.0, 111.0, 114.0, 1_000_000)
            for i in range(25)
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v2(
            SIGNAL_DATE, "T19", "WAIT_FOR_BREAKOUT",
            planned_entry=107.0, stop_price=90.0, target_price=130.0,
            ohlcv=ohlcv, prior_20d_high=prior_high,
        )
        assert t.filled is True
        # Entry must be on day 2, NOT day 1 (the trigger day)
        assert t.fill_date == SIGNAL_DATE + timedelta(days=2), (
            f"Expected entry on day+2, got {t.fill_date}. "
            "Look-ahead bias: should not enter on the same bar that triggers."
        )
        # Entry price must be day 2's OPEN (111.0), not day 1's close (109.0)
        assert t.fill_price == 111.0, (
            f"Expected fill at 111.0 (day+2 open), got {t.fill_price}. "
            "Must use next-day open, not trigger-day close."
        )


# ── Entry Order Type Tests (SA-1 clarification) ───────────────────────────────

class TestEntryOrderType:
    def test_ES21_v1_direct_next_open(self):
        """V1 baseline uses DIRECT_NEXT_OPEN — no trigger condition."""
        ohlcv = _make_ohlcv(SIGNAL_DATE + timedelta(days=1), 25)
        t = sim.simulate_v1(SIGNAL_DATE, "T21", stop_price=80.0, target_price=130.0, ohlcv=ohlcv)
        assert t.entry_order_type == ENTRY_DIRECT_NEXT_OPEN

    def test_ES22_wait_pullback_confirmed_next_open(self):
        """WAIT_FOR_PULLBACK uses CONFIRMED_NEXT_OPEN — enters only after trigger candle."""
        # Build enough bars so the trigger fires
        stop = 90.0
        threshold = EntryTimingExecutionSimulator.ma20_trigger_price(stop)
        # Trigger on day 1 (low < threshold), entry on day 2
        rows = [
            (SIGNAL_DATE + timedelta(days=1), 100.0, 102.0, threshold - 1.0, 100.0, 1_000_000),
            (SIGNAL_DATE + timedelta(days=2), 100.0, 102.0, 98.0, 100.0, 1_000_000),
        ] + [
            (SIGNAL_DATE + timedelta(days=3 + i), 100.0, 102.0, 98.0, 100.0, 1_000_000)
            for i in range(25)
        ]
        ohlcv = _custom_ohlcv(rows)
        t = sim.simulate_v2(
            SIGNAL_DATE, "T22", "WAIT_FOR_PULLBACK",
            planned_entry=stop / (1 - STOP_BUFFER),  # MA20_estimate
            stop_price=stop, target_price=130.0, ohlcv=ohlcv,
        )
        assert t.entry_order_type == ENTRY_CONFIRMED_NEXT_OPEN

    def test_ES23_ma20_trigger_price_formula(self):
        """MA20_trigger = stop / (1-STOP_BUFFER) × (1+MA20_TRIGGER_BUFFER)."""
        stop = 92.23
        expected = (stop / (1.0 - STOP_BUFFER)) * (1.0 + MA20_TRIGGER_BUFFER)
        got = EntryTimingExecutionSimulator.ma20_trigger_price(stop)
        assert abs(got - expected) < 0.001, f"Expected {expected:.4f}, got {got:.4f}"
