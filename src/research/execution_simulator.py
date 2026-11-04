"""
execution_simulator.py — OHLC-based entry timing execution simulation.

RESEARCH ONLY — NOT A LIVE TRADING SYSTEM.

Simulation Assumptions (SA) — explicitly labelled:

  SA-1  WAIT_FOR_PULLBACK trigger:
        When entry_label = WAIT_FOR_PULLBACK, the stock is currently trading
        ABOVE the MA20 pullback zone (ma20_gap > +3%).  We wait for the stock
        to pull back INTO the zone.

        MA20_estimate = stop_price / (1 - STOP_BUFFER)
        trigger_threshold = MA20_estimate × (1 + STOP_BUFFER)
                           = stop_price / (1 - STOP_BUFFER) × (1 + STOP_BUFFER)
                           ≈ stop_price × 1.062  [with STOP_BUFFER = 0.03]

        Trigger fires when: daily LOW ≤ trigger_threshold
        Entry type: CONFIRMED_NEXT_OPEN — enter at OPEN of the NEXT bar
                    after the trigger candle closes.  NOT a same-day limit order.
        Rationale: avoids using intra-day data to assume same-day fill.

  SA-2  WAIT_FOR_BREAKOUT trigger:
        Trigger fires when: daily CLOSE > prior_20d_high
        Entry type: CONFIRMED_NEXT_OPEN — enter at OPEN of the NEXT bar.

  SA-3  Same-day stop/target ambiguity (LOW ≤ stop AND HIGH ≥ target): STOP-FIRST.
  SA-4  Gap-down through stop: exit at OPEN of that day (gap slippage).
  SA-5  Standard hold period: 20 trading days from entry. Exit at CLOSE on day +20.
  SA-6  Taiwan round-trip fees: buy 0.1425% + sell 0.4425% = 0.585%.
  SA-7  Unfilled V2 in Full Opportunity Set: 0% return over same 20-day window.

Entry order types:
  DIRECT_NEXT_OPEN     — V1 baseline / ENTRY_READY: enter at OPEN of D+1,
                         no prior condition required.
  CONFIRMED_NEXT_OPEN  — WAIT_FOR_*: enter at OPEN of the bar AFTER trigger
                         candle.  Conservative; avoids same-day fill assumption.

FORBIDDEN: Do NOT modify MODEL_VERSION, BUY/STRONG_BUY thresholds, ForwardSignals,
           ACTUAL/PAPER positions, or any v8.0 decisions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

FEES_PCT = 0.585          # SA-6: round-trip Taiwan fees (buy 0.1425% + sell 0.4425%)
EXPIRY_DAYS = 10          # trading-day window for WAIT_FOR_* labels
HOLD_DAYS = 20            # SA-5: standard hold after fill
STOP_BUFFER = 0.03        # mirrors EntryTimingAnalyzer (stop = MA20 × (1 - STOP_BUFFER))

# SA-1: WAIT_FOR_PULLBACK trigger threshold = MA20_est × (1 + MA20_TRIGGER_BUFFER)
# where MA20_est = stop_price / (1 - STOP_BUFFER)
MA20_TRIGGER_BUFFER = STOP_BUFFER   # enter when price in top of MA20 zone (+3% above MA20)

# V2 entry label constants
_WAIT_PULLBACK_LABEL = "WAIT_FOR_PULLBACK"
_WAIT_BREAKOUT_LABEL = "WAIT_FOR_BREAKOUT"
_ENTRY_READY_LABEL = "ENTRY_READY"

# Labels that explicitly skip entry (not counted in FOS)
_SKIP_LABELS = frozenset({
    "TOO_EXTENDED",
    "NO_VALID_SETUP",
    "RISK_REWARD_UNFAVORABLE",
    "INSUFFICIENT_DATA",
})

# Entry order types (for SimulatedTrade.entry_order_type)
ENTRY_DIRECT_NEXT_OPEN = "DIRECT_NEXT_OPEN"
ENTRY_CONFIRMED_NEXT_OPEN = "CONFIRMED_NEXT_OPEN"

# Exit reasons
EXIT_TARGET = "TARGET"
EXIT_STOP = "STOP"
EXIT_HOLD_EXPIRY = "HOLD_20D"
EXIT_GAP_STOP = "GAP_STOP"
EXIT_AMBIGUOUS_STOP = "AMBIGUOUS_STOP_FIRST"

# No-fill reasons
NO_FILL_EXPIRED = "EXPIRED"
NO_FILL_SKIP_LABEL = "LABEL_SKIP"
NO_FILL_NO_HIST = "INSUFFICIENT_HIST"
NO_FILL_NO_TRIGGER = "NO_TRIGGER"


@dataclass
class SimulatedTrade:
    """Full record for one simulated trade (or no-fill)."""

    # ── Signal info ───────────────────────────────────────────────────────────
    signal_date: date
    stock_id: str
    entry_label: str
    v1_decision_label: Optional[str] = None

    # ── Signal parameters ─────────────────────────────────────────────────────
    # planned_entry:
    #   ENTRY_READY / V1  → signal-day close (proxy for D+1 OPEN)
    #   WAIT_FOR_PULLBACK → MA20_estimate = stop_price / (1 - STOP_BUFFER)
    #                       (the actual pullback target level)
    #   WAIT_FOR_BREAKOUT → signal-day close (prior_20d_high used for trigger)
    planned_entry: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    prior_20d_high: Optional[float] = None

    # ── Entry order classification ────────────────────────────────────────────
    # DIRECT_NEXT_OPEN     — no waiting condition; fill at D+1 OPEN
    # CONFIRMED_NEXT_OPEN  — wait for trigger candle, fill at next bar OPEN
    entry_order_type: str = ENTRY_DIRECT_NEXT_OPEN

    # ── Entry result ──────────────────────────────────────────────────────────
    filled: bool = False
    fill_date: Optional[date] = None
    fill_price: Optional[float] = None
    no_fill_reason: Optional[str] = None
    expiration_date: Optional[date] = None

    # ── Exit result ───────────────────────────────────────────────────────────
    exit_date: Optional[date] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None

    # ── Timing ────────────────────────────────────────────────────────────────
    waiting_days: int = 0   # calendar days from signal to fill
    days_held: int = 0      # trading days from fill to exit

    # ── P&L ───────────────────────────────────────────────────────────────────
    gross_return_pct: Optional[float] = None
    fees_pct: float = FEES_PCT
    net_return_pct: Optional[float] = None

    # ── Risk metrics ──────────────────────────────────────────────────────────
    r_multiple: Optional[float] = None   # (exit - fill) / (fill - stop)
    mae_pct: Optional[float] = None      # max adverse excursion %
    mfe_pct: Optional[float] = None      # max favorable excursion %
    stop_hit: bool = False
    target_hit: bool = False

    # ── Flags ─────────────────────────────────────────────────────────────────
    ambiguous_day: bool = False    # SA-3
    gap_slippage: bool = False     # SA-4
    simulation_note: str = ""


@dataclass
class BacktestComparison:
    """Aggregate results for V1 vs V2 three-way comparison."""

    v1_eligible: int = 0
    v2_entry_ready: int = 0
    v2_wait_pullback: int = 0
    v2_wait_breakout: int = 0
    v2_skip_labels: int = 0
    v2_filled: int = 0
    v2_no_fill: int = 0

    fill_rate_pct: Optional[float] = None
    avg_waiting_days: Optional[float] = None

    v1_mean_ret_20d: Optional[float] = None
    v1_median_ret_20d: Optional[float] = None
    v1_win_rate: Optional[float] = None
    v1_ci_95: Optional[dict] = None
    v2_selection_mean_ret_20d: Optional[float] = None
    v2_selection_win_rate: Optional[float] = None
    v2_selection_ci_95: Optional[dict] = None

    v2_filled_mean_ret_20d: Optional[float] = None
    v2_filled_win_rate: Optional[float] = None
    v2_filled_mae_mean: Optional[float] = None
    v2_filled_mfe_mean: Optional[float] = None
    v2_filled_r_multiple_mean: Optional[float] = None
    v2_filled_stop_hit_rate: Optional[float] = None
    v2_filled_target_hit_rate: Optional[float] = None

    v2_fos_mean_ret_20d: Optional[float] = None
    v2_fos_median_ret_20d: Optional[float] = None
    v2_fos_win_rate: Optional[float] = None
    v2_fos_ci_95: Optional[dict] = None
    performance_delta: Optional[float] = None  # V2_FOS_mean - V1_OHLC_mean

    simulation_assumptions: List[str] = field(default_factory=list)


# ── Main Simulator ────────────────────────────────────────────────────────────

class EntryTimingExecutionSimulator:
    """
    Simulate V1 and V2 entry timing using daily OHLCV bars.

    V1 baseline:  buy at D+1 OPEN (DIRECT_NEXT_OPEN), same stop/target.
    V2 candidate: conditional entry based on entry_label (WAIT_FOR_* uses
                  CONFIRMED_NEXT_OPEN after trigger bar).

    Usage:
        sim = EntryTimingExecutionSimulator()
        v1 = sim.simulate_v1(signal_date, stock_id, stop, target, ohlcv)
        v2 = sim.simulate_v2(signal_date, stock_id, entry_label, ...)
    """

    def simulate_v1(
        self,
        signal_date: date,
        stock_id: str,
        stop_price: float,
        target_price: float,
        ohlcv: pd.DataFrame,
    ) -> SimulatedTrade:
        """
        V1 baseline: enter at OPEN of the FIRST bar strictly after signal_date.
        DIRECT_NEXT_OPEN — no trigger condition, immediate market entry.
        """
        trade = SimulatedTrade(
            signal_date=signal_date,
            stock_id=stock_id,
            entry_label="V1_NEXT_OPEN",
            stop_price=stop_price,
            target_price=target_price,
            entry_order_type=ENTRY_DIRECT_NEXT_OPEN,
        )

        post = self._filter_post_signal(ohlcv, signal_date)
        if post.empty:
            trade.no_fill_reason = NO_FILL_NO_HIST
            trade.simulation_note = "No OHLCV data after signal_date"
            return trade

        entry_row = post.iloc[0]
        fill_price = float(entry_row["open"])
        trade.planned_entry = fill_price  # actual D+1 open

        # SA-4: gap down through stop on entry day
        if fill_price <= stop_price:
            trade.gap_slippage = True
            trade.filled = True
            trade.fill_date = entry_row["date"]
            trade.fill_price = fill_price
            trade.exit_date = entry_row["date"]
            trade.exit_price = fill_price
            trade.exit_reason = EXIT_GAP_STOP
            trade.stop_hit = True
            trade.days_held = 0
            self._compute_pnl(trade)
            return trade

        trade.filled = True
        trade.fill_date = entry_row["date"]
        trade.fill_price = fill_price

        hold_bars = post.iloc[1 : 1 + HOLD_DAYS]
        self._run_hold(trade, hold_bars)
        return trade

    def simulate_v2(
        self,
        signal_date: date,
        stock_id: str,
        entry_label: str,
        planned_entry: float,
        stop_price: float,
        target_price: float,
        ohlcv: pd.DataFrame,
        prior_20d_high: Optional[float] = None,
        v1_decision_label: Optional[str] = None,
        expiry_days: int = EXPIRY_DAYS,
    ) -> SimulatedTrade:
        """
        V2 conditional entry.

        entry_label = ENTRY_READY   → DIRECT_NEXT_OPEN (same as V1)
        entry_label = WAIT_FOR_PULLBACK → SA-1 trigger, CONFIRMED_NEXT_OPEN
        entry_label = WAIT_FOR_BREAKOUT → SA-2 trigger, CONFIRMED_NEXT_OPEN
        entry_label in _SKIP_LABELS → no fill

        planned_entry for WAIT_FOR_PULLBACK should be MA20_estimate
        (= stop_price / (1 - STOP_BUFFER)), NOT the signal-day close.
        """
        trade = SimulatedTrade(
            signal_date=signal_date,
            stock_id=stock_id,
            entry_label=entry_label,
            v1_decision_label=v1_decision_label,
            planned_entry=planned_entry,
            stop_price=stop_price,
            target_price=target_price,
            prior_20d_high=prior_20d_high,
            entry_order_type=(
                ENTRY_CONFIRMED_NEXT_OPEN
                if entry_label in (_WAIT_PULLBACK_LABEL, _WAIT_BREAKOUT_LABEL)
                else ENTRY_DIRECT_NEXT_OPEN
            ),
        )

        if entry_label in _SKIP_LABELS:
            trade.no_fill_reason = NO_FILL_SKIP_LABEL
            trade.simulation_note = f"[SA] Label '{entry_label}' skips entry"
            return trade

        post = self._filter_post_signal(ohlcv, signal_date)
        if post.empty:
            trade.no_fill_reason = NO_FILL_NO_HIST
            return trade

        if entry_label == _ENTRY_READY_LABEL:
            return self._fill_next_open(trade, post)

        if entry_label == _WAIT_PULLBACK_LABEL:
            return self._wait_for_pullback(trade, post, expiry_days)

        if entry_label == _WAIT_BREAKOUT_LABEL:
            return self._wait_for_breakout(trade, post, prior_20d_high, expiry_days)

        trade.no_fill_reason = NO_FILL_SKIP_LABEL
        trade.simulation_note = f"Unknown entry_label '{entry_label}'"
        return trade

    # ── Private helpers ───────────────────────────────────────────────────────

    def _filter_post_signal(self, ohlcv: pd.DataFrame, signal_date: date) -> pd.DataFrame:
        """Return bars strictly after signal_date, sorted ascending."""
        if ohlcv is None or ohlcv.empty:
            return pd.DataFrame()
        df = ohlcv.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df[df["date"] > signal_date].sort_values("date").reset_index(drop=True)
        return df

    def _fill_next_open(self, trade: SimulatedTrade, post: pd.DataFrame) -> SimulatedTrade:
        """ENTRY_READY: DIRECT_NEXT_OPEN — enter at OPEN of first post-signal bar."""
        entry_row = post.iloc[0]
        fill_price = float(entry_row["open"])

        if fill_price <= trade.stop_price:
            trade.gap_slippage = True
            trade.filled = True
            trade.fill_date = entry_row["date"]
            trade.fill_price = fill_price
            trade.exit_date = entry_row["date"]
            trade.exit_price = fill_price
            trade.exit_reason = EXIT_GAP_STOP
            trade.stop_hit = True
            trade.days_held = 0
            self._compute_pnl(trade)
            return trade

        trade.filled = True
        trade.fill_date = entry_row["date"]
        trade.fill_price = fill_price
        hold_bars = post.iloc[1 : 1 + HOLD_DAYS]
        self._run_hold(trade, hold_bars)
        return trade

    @staticmethod
    def ma20_trigger_price(stop_price: float) -> float:
        """
        SA-1: derive the pullback trigger threshold from stop_price.

        stop_price = MA20 × (1 - STOP_BUFFER)   [EntryTimingAnalyzer definition]
        → MA20_estimate = stop_price / (1 - STOP_BUFFER)
        → trigger = MA20_estimate × (1 + MA20_TRIGGER_BUFFER)
                  = stop_price / (1 - STOP_BUFFER) × (1 + MA20_TRIGGER_BUFFER)

        Fires when daily LOW ≤ trigger, meaning price has entered the MA20 zone.
        """
        ma20_est = stop_price / (1.0 - STOP_BUFFER)
        return ma20_est * (1.0 + MA20_TRIGGER_BUFFER)

    @staticmethod
    def ma20_estimate(stop_price: float) -> float:
        """Return MA20 estimate from stop_price (inverse of EntryTimingAnalyzer's stop formula)."""
        return stop_price / (1.0 - STOP_BUFFER)

    def _wait_for_pullback(
        self,
        trade: SimulatedTrade,
        post: pd.DataFrame,
        expiry_days: int,
    ) -> SimulatedTrade:
        """
        SA-1: WAIT_FOR_PULLBACK — CONFIRMED_NEXT_OPEN.

        Trigger: daily LOW ≤ MA20_estimate × (1 + MA20_TRIGGER_BUFFER).
        Entry: OPEN of the NEXT bar after trigger candle.

        MA20_estimate is derived from stop_price because V2ShadowSignal stores
        stop (not MA20 directly).  This is an approximation that is exact when
        EntryTimingAnalyzer set stop = MA20 × (1 - STOP_BUFFER).
        """
        trigger_threshold = self.ma20_trigger_price(trade.stop_price)
        window = post.iloc[:expiry_days]
        trade.expiration_date = window.iloc[-1]["date"] if not window.empty else None

        for i, row in window.iterrows():
            if float(row["low"]) <= trigger_threshold:
                # Trigger fires — enter at OPEN of NEXT bar (CONFIRMED_NEXT_OPEN)
                next_idx = i + 1
                if next_idx >= len(post):
                    break  # no next bar → treat as expired
                entry_row = post.iloc[next_idx]
                fill_price = float(entry_row["open"])

                trade.filled = True
                trade.fill_date = entry_row["date"]
                trade.fill_price = fill_price
                trade.waiting_days = (entry_row["date"] - trade.signal_date).days
                trade.simulation_note = (
                    f"[SA-1] WAIT_FOR_PULLBACK trigger: LOW {float(row['low']):.2f}"
                    f" ≤ threshold {trigger_threshold:.2f}"
                    f" (MA20_est×1.03); fill at next OPEN {fill_price:.2f}"
                )

                if fill_price <= trade.stop_price:
                    trade.gap_slippage = True
                    trade.exit_date = entry_row["date"]
                    trade.exit_price = fill_price
                    trade.exit_reason = EXIT_GAP_STOP
                    trade.stop_hit = True
                    self._compute_pnl(trade)
                    return trade

                hold_start = next_idx + 1
                hold_bars = post.iloc[hold_start : hold_start + HOLD_DAYS]
                self._run_hold(trade, hold_bars)
                return trade

        trade.no_fill_reason = NO_FILL_EXPIRED
        trade.simulation_note = (
            f"[SA-1] WAIT_FOR_PULLBACK: no trigger (LOW ≤ {trigger_threshold:.2f})"
            f" in {expiry_days} bars"
        )
        return trade

    def _wait_for_breakout(
        self,
        trade: SimulatedTrade,
        post: pd.DataFrame,
        prior_20d_high: Optional[float],
        expiry_days: int,
    ) -> SimulatedTrade:
        """
        SA-2: WAIT_FOR_BREAKOUT — CONFIRMED_NEXT_OPEN.
        Trigger: CLOSE > prior_20d_high.  Entry at OPEN of NEXT bar.
        """
        if prior_20d_high is None or prior_20d_high <= 0:
            trade.no_fill_reason = NO_FILL_NO_HIST
            trade.simulation_note = "WAIT_FOR_BREAKOUT: prior_20d_high not provided"
            return trade

        window = post.iloc[:expiry_days]
        trade.expiration_date = window.iloc[-1]["date"] if not window.empty else None

        for i, row in window.iterrows():
            if float(row["close"]) > prior_20d_high:
                next_idx = i + 1
                if next_idx >= len(post):
                    break
                entry_row = post.iloc[next_idx]
                fill_price = float(entry_row["open"])

                trade.filled = True
                trade.fill_date = entry_row["date"]
                trade.fill_price = fill_price
                trade.waiting_days = (entry_row["date"] - trade.signal_date).days
                trade.simulation_note = (
                    f"[SA-2] WAIT_FOR_BREAKOUT: CLOSE {float(row['close']):.2f}"
                    f" > prior_high {prior_20d_high:.2f}; fill at {fill_price:.2f}"
                )

                if fill_price <= trade.stop_price:
                    trade.gap_slippage = True
                    trade.exit_date = entry_row["date"]
                    trade.exit_price = fill_price
                    trade.exit_reason = EXIT_GAP_STOP
                    trade.stop_hit = True
                    self._compute_pnl(trade)
                    return trade

                hold_start = next_idx + 1
                hold_bars = post.iloc[hold_start : hold_start + HOLD_DAYS]
                self._run_hold(trade, hold_bars)
                return trade

        trade.no_fill_reason = NO_FILL_EXPIRED
        trade.simulation_note = (
            f"[SA-2] WAIT_FOR_BREAKOUT: no CLOSE > {prior_20d_high:.2f}"
            f" in {expiry_days} bars"
        )
        return trade

    def _run_hold(self, trade: SimulatedTrade, hold_bars: pd.DataFrame) -> None:
        """
        Scan hold_bars for stop/target/expiry. Modifies trade in place.
        SA-3: same-day stop + target → stop first.
        SA-4: gap down (open ≤ stop) → exit at open.
        SA-5: last hold bar → exit at close.
        """
        if hold_bars.empty:
            trade.exit_date = trade.fill_date
            trade.exit_price = trade.fill_price
            trade.exit_reason = EXIT_HOLD_EXPIRY
            trade.days_held = 0
            self._compute_pnl(trade)
            return

        fp = trade.fill_price
        mae_low = fp
        mfe_high = fp

        for day_num, (_, row) in enumerate(hold_bars.iterrows()):
            day_open = float(row["open"])
            day_high = float(row["high"])
            day_low = float(row["low"])
            day_close = float(row["close"])

            mae_low = min(mae_low, day_low)
            mfe_high = max(mfe_high, day_high)

            # SA-4: gap down through stop
            if day_open <= trade.stop_price:
                trade.gap_slippage = True
                trade.exit_date = row["date"]
                trade.exit_price = day_open
                trade.exit_reason = EXIT_GAP_STOP
                trade.stop_hit = True
                trade.days_held = day_num + 1
                break

            stop_hit = day_low <= trade.stop_price
            target_hit = day_high >= trade.target_price

            if stop_hit and target_hit:
                # SA-3: ambiguous → stop first
                trade.ambiguous_day = True
                trade.exit_date = row["date"]
                trade.exit_price = trade.stop_price
                trade.exit_reason = EXIT_AMBIGUOUS_STOP
                trade.stop_hit = True
                trade.days_held = day_num + 1
                break
            elif stop_hit:
                trade.exit_date = row["date"]
                trade.exit_price = trade.stop_price
                trade.exit_reason = EXIT_STOP
                trade.stop_hit = True
                trade.days_held = day_num + 1
                break
            elif target_hit:
                trade.exit_date = row["date"]
                trade.exit_price = trade.target_price
                trade.exit_reason = EXIT_TARGET
                trade.target_hit = True
                trade.days_held = day_num + 1
                break

            if day_num == len(hold_bars) - 1:
                # SA-5: hold expiry
                trade.exit_date = row["date"]
                trade.exit_price = day_close
                trade.exit_reason = EXIT_HOLD_EXPIRY
                trade.days_held = day_num + 1
                break
        else:
            last = hold_bars.iloc[-1]
            trade.exit_date = last["date"]
            trade.exit_price = float(last["close"])
            trade.exit_reason = EXIT_HOLD_EXPIRY
            trade.days_held = len(hold_bars)

        if fp and fp > 0:
            trade.mae_pct = round((fp - mae_low) / fp * 100.0, 4)
            trade.mfe_pct = round((mfe_high - fp) / fp * 100.0, 4)

        self._compute_pnl(trade)

    def _compute_pnl(self, trade: SimulatedTrade) -> None:
        """Compute gross_return_pct, net_return_pct, r_multiple."""
        if trade.fill_price and trade.exit_price:
            fp = trade.fill_price
            ep = trade.exit_price
            gross = (ep - fp) / fp * 100.0
            trade.gross_return_pct = round(gross, 4)
            trade.net_return_pct = round(gross - trade.fees_pct, 4)

            risk = fp - trade.stop_price
            if risk > 0:
                trade.r_multiple = round((ep - fp) / risk, 3)
