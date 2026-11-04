"""
execution_simulator.py — OHLC-based entry timing execution simulation.

RESEARCH ONLY — NOT A LIVE TRADING SYSTEM.

Simulation Assumptions (SA) — explicitly labelled, do NOT imply official strategy rules:

  SA-1  WAIT_FOR_PULLBACK trigger: daily LOW ≤ MA20_est × 1.03,
        where MA20_est = stop_price / (1 - 0.03). Entry at next-day OPEN.
  SA-2  WAIT_FOR_BREAKOUT trigger: daily CLOSE > prior_20d_high. Entry at next-day OPEN.
  SA-3  Same-day stop/target ambiguity (LOW ≤ stop AND HIGH ≥ target): STOP-FIRST.
  SA-4  Gap-down through stop: exit at OPEN of that day (gap slippage).
  SA-5  Standard hold period: 20 trading days from entry. Exit at CLOSE on day +20.
  SA-6  Taiwan round-trip fees: buy 0.1425% + sell 0.4425% = 0.585%.
  SA-7  Unfilled V2 in Full Opportunity Set: 0% return over same 20-day window.

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

FEES_PCT = 0.585          # SA-6: round-trip Taiwan fees
EXPIRY_DAYS = 10          # trading days window for WAIT_FOR_* labels
HOLD_DAYS = 20            # SA-5: standard hold after entry
STOP_BUFFER = 0.03        # mirrors EntryTimingAnalyzer (stop = MA20 * (1 - STOP_BUFFER))

# V2 labels that trigger conditional entry logic
_WAIT_PULLBACK_LABEL = "WAIT_FOR_PULLBACK"
_WAIT_BREAKOUT_LABEL = "WAIT_FOR_BREAKOUT"
_ENTRY_READY_LABEL = "ENTRY_READY"

# Labels that explicitly skip entry
_SKIP_LABELS = {
    "TOO_EXTENDED",
    "NO_VALID_SETUP",
    "RISK_REWARD_UNFAVORABLE",
    "INSUFFICIENT_DATA",
}

# Exit reasons
EXIT_TARGET = "TARGET"
EXIT_STOP = "STOP"
EXIT_HOLD_EXPIRY = "HOLD_20D"
EXIT_GAP_STOP = "GAP_STOP"
EXIT_AMBIGUOUS_STOP = "AMBIGUOUS_STOP_FIRST"

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
    planned_entry: float = 0.0   # entry_price from signal (today's close proxy)
    stop_price: float = 0.0
    target_price: float = 0.0
    prior_20d_high: Optional[float] = None

    # ── Entry result ──────────────────────────────────────────────────────────
    filled: bool = False
    fill_date: Optional[date] = None
    fill_price: Optional[float] = None
    no_fill_reason: Optional[str] = None
    expiration_date: Optional[date] = None

    # ── Exit result ───────────────────────────────────────────────────────────
    exit_date: Optional[date] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # TARGET / STOP / HOLD_20D / GAP_STOP / AMBIGUOUS_STOP_FIRST

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
    ambiguous_day: bool = False    # SA-3: same day stop & target triggered
    gap_slippage: bool = False     # SA-4: open < stop on entry or hold day
    simulation_note: str = ""


@dataclass
class BacktestComparison:
    """Aggregate results for V1 vs V2 three-way comparison."""

    # ── Counts ────────────────────────────────────────────────────────────────
    v1_eligible: int = 0
    v2_entry_ready: int = 0
    v2_wait_pullback: int = 0
    v2_wait_breakout: int = 0
    v2_skip_labels: int = 0
    v2_filled: int = 0
    v2_no_fill: int = 0

    # ── Fill rate ─────────────────────────────────────────────────────────────
    fill_rate_pct: Optional[float] = None
    avg_waiting_days: Optional[float] = None

    # ── Comparison A: Signal Selection ────────────────────────────────────────
    # V2 ENTRY_READY vs V1 eligible (uses SAME V1 return data — equal price entry)
    v1_mean_ret_20d: Optional[float] = None
    v1_median_ret_20d: Optional[float] = None
    v1_win_rate: Optional[float] = None
    v1_ci_95: Optional[dict] = None
    v2_selection_mean_ret_20d: Optional[float] = None
    v2_selection_win_rate: Optional[float] = None
    v2_selection_ci_95: Optional[dict] = None

    # ── Comparison B: Filled Trades only ──────────────────────────────────────
    # SA warning: selection bias — only filled V2 trades included
    v2_filled_mean_ret_20d: Optional[float] = None
    v2_filled_win_rate: Optional[float] = None
    v2_filled_mae_mean: Optional[float] = None
    v2_filled_mfe_mean: Optional[float] = None
    v2_filled_r_multiple_mean: Optional[float] = None
    v2_filled_stop_hit_rate: Optional[float] = None
    v2_filled_target_hit_rate: Optional[float] = None

    # ── Comparison C: Full Opportunity Set ────────────────────────────────────
    # Main comparison: same V1 eligible pool, V2 filled + V2 no-fill (0%)
    v2_fos_mean_ret_20d: Optional[float] = None
    v2_fos_median_ret_20d: Optional[float] = None
    v2_fos_win_rate: Optional[float] = None
    v2_fos_ci_95: Optional[dict] = None
    opportunity_cost_mean: Optional[float] = None  # V2_FOS_ret - V1_ret per signal

    # ── Notes ─────────────────────────────────────────────────────────────────
    return_source_note: str = (
        "SIMULATION: V1 uses actual ForwardSignal.fwd_return_20d (NEXT_OPEN proxy). "
        "V2 simulated trades use OHLC-based exit rules (SA-3 through SA-5). "
        "Returns NOT directly comparable without matching entry-price adjustment."
    )
    simulation_assumptions: List[str] = field(default_factory=list)


# ── Main Simulator ────────────────────────────────────────────────────────────

class EntryTimingExecutionSimulator:
    """
    Simulate V1 and V2 entry timing using daily OHLCV bars.

    Call pattern:
        sim = EntryTimingExecutionSimulator()
        trade = sim.simulate_v1(signal_date, stock_id, stop, target, ohlcv_after_signal)
        trade = sim.simulate_v2(signal_date, stock_id, entry_label, ...)
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
        V1 baseline: enter at OPEN of the FIRST bar after signal_date.
        Ohlcv must have columns: date, open, high, low, close (volume optional).
        Only bars with date > signal_date are used.
        """
        trade = SimulatedTrade(
            signal_date=signal_date,
            stock_id=stock_id,
            entry_label="V1_NEXT_OPEN",
            stop_price=stop_price,
            target_price=target_price,
        )

        post = self._filter_post_signal(ohlcv, signal_date)
        if post.empty:
            trade.no_fill_reason = NO_FILL_NO_HIST
            trade.simulation_note = "No OHLCV data after signal_date"
            return trade

        # Entry: OPEN of first post-signal bar
        entry_row = post.iloc[0]
        fill_price = float(entry_row["open"])

        # SA-4: gap down through stop on entry day
        gap_slippage = fill_price <= stop_price
        if gap_slippage:
            trade.gap_slippage = True
            trade.filled = True
            trade.fill_date = entry_row["date"]
            trade.fill_price = fill_price
            trade.exit_date = entry_row["date"]
            trade.exit_price = fill_price  # exit at fill (immediate stop)
            trade.exit_reason = EXIT_GAP_STOP
            trade.stop_hit = True
            trade.days_held = 0
            self._compute_pnl(trade)
            return trade

        trade.filled = True
        trade.fill_date = entry_row["date"]
        trade.fill_price = fill_price

        # Hold window: next HOLD_DAYS bars after entry
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
        V2: conditional entry based on entry_label.
        ENTRY_READY → same as V1 NEXT_OPEN.
        WAIT_FOR_PULLBACK → SA-1 trigger.
        WAIT_FOR_BREAKOUT → SA-2 trigger.
        Skip labels → no fill.
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
        )

        # Labels that skip entry immediately
        if entry_label in _SKIP_LABELS:
            trade.no_fill_reason = NO_FILL_SKIP_LABEL
            trade.simulation_note = f"[SA] Label '{entry_label}' skips entry in simulation"
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

        # Unknown label — treat as skip
        trade.no_fill_reason = NO_FILL_SKIP_LABEL
        trade.simulation_note = f"Unknown entry_label '{entry_label}'"
        return trade

    # ── Private helpers ───────────────────────────────────────────────────────

    def _filter_post_signal(self, ohlcv: pd.DataFrame, signal_date: date) -> pd.DataFrame:
        """Return rows with date strictly after signal_date, sorted ascending."""
        if ohlcv is None or ohlcv.empty:
            return pd.DataFrame()
        df = ohlcv.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df[df["date"] > signal_date].sort_values("date").reset_index(drop=True)
        return df

    def _fill_next_open(self, trade: SimulatedTrade, post: pd.DataFrame) -> SimulatedTrade:
        """ENTRY_READY / V1-equivalent: enter at OPEN of first post-signal bar."""
        entry_row = post.iloc[0]
        fill_price = float(entry_row["open"])

        # SA-4: gap down
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

    def _wait_for_pullback(
        self,
        trade: SimulatedTrade,
        post: pd.DataFrame,
        expiry_days: int,
    ) -> SimulatedTrade:
        """
        SA-1: Scan for daily LOW ≤ MA20_estimate × 1.03.
        MA20_estimate = stop_price / (1 - STOP_BUFFER).
        Entry at OPEN of the NEXT bar after trigger.
        Expiry: expiry_days bars from signal.
        """
        window = post.iloc[:expiry_days]
        trade.expiration_date = window.iloc[-1]["date"] if not window.empty else None

        # MA20 estimate from stop_price
        ma20_est = trade.stop_price / (1.0 - STOP_BUFFER)
        pullback_threshold = ma20_est * (1.0 + 0.03)  # within +3% of MA20

        for i, row in window.iterrows():
            if float(row["low"]) <= pullback_threshold:
                # Triggered on this bar — enter at OPEN of NEXT bar
                next_idx = i + 1
                if next_idx >= len(post):
                    # No next bar available — treat as expired
                    break
                entry_row = post.iloc[next_idx]
                fill_price = float(entry_row["open"])

                trade.filled = True
                trade.fill_date = entry_row["date"]
                trade.fill_price = fill_price
                trade.waiting_days = (entry_row["date"] - trade.signal_date).days
                trade.simulation_note = "[SA-1] WAIT_FOR_PULLBACK trigger"

                # SA-4: gap down through stop
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
        trade.simulation_note = f"[SA-1] WAIT_FOR_PULLBACK: no trigger in {expiry_days} bars"
        return trade

    def _wait_for_breakout(
        self,
        trade: SimulatedTrade,
        post: pd.DataFrame,
        prior_20d_high: Optional[float],
        expiry_days: int,
    ) -> SimulatedTrade:
        """
        SA-2: Scan for CLOSE > prior_20d_high.
        Entry at OPEN of NEXT bar after trigger.
        Expiry: expiry_days bars from signal.
        """
        if prior_20d_high is None or prior_20d_high <= 0:
            trade.no_fill_reason = NO_FILL_NO_HIST
            trade.simulation_note = "WAIT_FOR_BREAKOUT: prior_20d_high not provided"
            return trade

        window = post.iloc[:expiry_days]
        trade.expiration_date = window.iloc[-1]["date"] if not window.empty else None

        for i, row in window.iterrows():
            if float(row["close"]) > prior_20d_high:
                # Triggered — enter at next bar's OPEN
                next_idx = i + 1
                if next_idx >= len(post):
                    break
                entry_row = post.iloc[next_idx]
                fill_price = float(entry_row["open"])

                trade.filled = True
                trade.fill_date = entry_row["date"]
                trade.fill_price = fill_price
                trade.waiting_days = (entry_row["date"] - trade.signal_date).days
                trade.simulation_note = "[SA-2] WAIT_FOR_BREAKOUT trigger"

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
        trade.simulation_note = f"[SA-2] WAIT_FOR_BREAKOUT: no close > {prior_20d_high} in {expiry_days} bars"
        return trade

    def _run_hold(self, trade: SimulatedTrade, hold_bars: pd.DataFrame) -> None:
        """
        Scan hold_bars for stop/target/expiry. Modifies trade in place.
        SA-3: same-day stop + target → STOP FIRST.
        SA-4: gap down (open < stop) → exit at open.
        SA-5: after HOLD_DAYS bars → exit at close.
        """
        if hold_bars.empty:
            # No data to hold — exit at fill price (edge case)
            trade.exit_date = trade.fill_date
            trade.exit_price = trade.fill_price
            trade.exit_reason = EXIT_HOLD_EXPIRY
            trade.days_held = 0
            self._compute_pnl(trade)
            return

        fp = trade.fill_price
        mae_low = fp  # track worst low seen
        mfe_high = fp  # track best high seen

        for day_num, (_, row) in enumerate(hold_bars.iterrows()):
            day_open = float(row["open"])
            day_high = float(row["high"])
            day_low = float(row["low"])
            day_close = float(row["close"])

            # Update MAE/MFE
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

            # SA-3: ambiguous — both on same day → stop first
            if stop_hit and target_hit:
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

            # SA-5: last bar of hold window
            if day_num == len(hold_bars) - 1:
                trade.exit_date = row["date"]
                trade.exit_price = day_close
                trade.exit_reason = EXIT_HOLD_EXPIRY
                trade.days_held = day_num + 1
                break
        else:
            # Loop exhausted without hitting any exit (< HOLD_DAYS bars available)
            last = hold_bars.iloc[-1]
            trade.exit_date = last["date"]
            trade.exit_price = float(last["close"])
            trade.exit_reason = EXIT_HOLD_EXPIRY
            trade.days_held = len(hold_bars)

        # MAE / MFE %
        if fp and fp > 0:
            trade.mae_pct = round((fp - mae_low) / fp * 100.0, 4)
            trade.mfe_pct = round((mfe_high - fp) / fp * 100.0, 4)

        self._compute_pnl(trade)

    def _compute_pnl(self, trade: SimulatedTrade) -> None:
        """Fill gross_return_pct, net_return_pct, r_multiple."""
        if trade.fill_price and trade.exit_price:
            fp = trade.fill_price
            ep = trade.exit_price
            gross = (ep - fp) / fp * 100.0
            trade.gross_return_pct = round(gross, 4)
            trade.net_return_pct = round(gross - trade.fees_pct, 4)

            risk = fp - trade.stop_price
            if risk > 0:
                trade.r_multiple = round((ep - fp) / risk, 3)
