"""
v3_backtest_engine.py — V3 Entry Timing Historical Backtest Engine

RESEARCH ONLY — NOT A LIVE TRADING SYSTEM.

Backtest pipeline per signal:
  1. Load OHLCV history up to and including signal_date (strict no look-ahead).
  2. Run V3EntryTimingAnalyzer → V3EntryDecision.
  3. Map V3 decision to execution model.
  4. Load post-signal OHLCV; simulate the trade.
  5. Compute 0050 benchmark return over same fill/exit window.
  6. Aggregate into V3BacktestResult.

Time-causality guarantees:
  - History  = daily_prices WHERE date <= signal_date  (no future data)
  - Forward  = daily_prices WHERE date >  signal_date  (strictly after)
  - Benchmark uses same fill/exit dates as the trade
  - No cross-signal information leakage

V3 decision → execution mapping:
  DIRECT_ENTRY             → fill at D+1 OPEN (DIRECT_NEXT_OPEN)
  WAIT_MA20_PULLBACK       → trigger when LOW ≤ proposed_limit_price (MA20 level)
                             fill at OPEN of NEXT bar (CONFIRMED_NEXT_OPEN)
  WAIT_MA60_SUPPORT        → trigger when LOW ≤ proposed_limit_price (MA60 level)
                             fill at OPEN of NEXT bar (CONFIRMED_NEXT_OPEN)
  WAIT_BREAKOUT_CONFIRMATION → trigger when CLOSE > prior_20d_high
                             fill at OPEN of NEXT bar (CONFIRMED_NEXT_OPEN)
  AVOID_CHASING            → no fill (counted as skip)
  NO_ENTRY                 → no fill (counted as skip)
  INSUFFICIENT_DATA        → no fill (counted as skip)

Conservative intrabar rules (all inherited from execution_simulator.py):
  SA-3: same-day stop + target ambiguity → stop first (INTRABAR_SEQUENCE_UNKNOWN)
  SA-4: gap down through stop at open → exit at open (gap slippage)
  SA-5: 20-trading-day hold expiry → exit at close

FORBIDDEN: Do NOT write to any production table (Neon or SQLite hybrid_forward_decision,
           forward_signals, positions). Do NOT modify execution_simulator.py or
           v3_entry_strategy.py.  Do NOT change MODEL_VERSION v8.0.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Dict, List, Optional

import pandas as pd

from src.research.execution_simulator import (
    ENTRY_CONFIRMED_NEXT_OPEN,
    ENTRY_DIRECT_NEXT_OPEN,
    EXIT_GAP_STOP,
    EXPIRY_DAYS,
    FEES_PCT,
    HOLD_DAYS,
    NO_FILL_EXPIRED,
    NO_FILL_NO_HIST,
    NO_FILL_SKIP_LABEL,
    EntryTimingExecutionSimulator,
    SimulatedTrade,
)
from src.research.v3_entry_strategy import (
    AVOID_CHASING,
    DIRECT_ENTRY,
    INSUFFICIENT_DATA,
    MIN_BARS_FULL,
    MIN_RR_RATIO,
    NO_ENTRY,
    RESEARCH_VERSION,
    STOP_BUFFER,
    WAIT_BREAKOUT_CONFIRMATION,
    WAIT_MA20_PULLBACK,
    WAIT_MA60_SUPPORT,
    V3EntryDecision,
    V3EntryTimingAnalyzer,
    _REGIME_PARAMS,
)

logger = logging.getLogger(__name__)

# ── Version ────────────────────────────────────────────────────────────────────

ENGINE_VERSION = "v3_backtest_v1"

# ── Maturation status ──────────────────────────────────────────────────────────

MATURED_FULL = "FULL"      # >= HOLD_DAYS forward trading bars available
MATURED_PARTIAL = "PARTIAL"  # 1 to HOLD_DAYS-1 forward bars
MATURED_NONE = "NO_DATA"   # 0 forward bars

# ── Decisions that skip execution ─────────────────────────────────────────────

_SKIP_DECISIONS = frozenset({AVOID_CHASING, NO_ENTRY, INSUFFICIENT_DATA})

# ── In-sample warning ──────────────────────────────────────────────────────────

IN_SAMPLE_WARNING = (
    "RESEARCH ONLY — IN-SAMPLE. V3 parameters were not derived from an "
    "independent held-out set. Results may not generalise. "
    "Walk-forward or true OOS required before any production consideration."
)


def _compute_parameter_hash() -> str:
    """Deterministic SHA-256 of all frozen V3 research parameters."""
    params = {
        "research_version": RESEARCH_VERSION,
        "engine_version": ENGINE_VERSION,
        "regime_params": {k: dict(v) for k, v in _REGIME_PARAMS.items()},
        "min_bars_full": MIN_BARS_FULL,
        "stop_buffer": STOP_BUFFER,
        "min_rr_ratio": MIN_RR_RATIO,
        "fees_pct": FEES_PCT,
        "hold_days": HOLD_DAYS,
        "expiry_days": EXPIRY_DAYS,
    }
    return hashlib.sha256(
        json.dumps(params, sort_keys=True).encode()
    ).hexdigest()[:16]


PARAMETER_HASH = _compute_parameter_hash()


# ── Input / output dataclasses ─────────────────────────────────────────────────

@dataclass
class V3SignalInput:
    """One candidate signal to replay through the V3 backtest."""

    signal_date: date
    stock_id: str
    market_regime: str = "unknown"
    source: str = "forward_signals"  # audit trail


@dataclass
class V3BacktestRow:
    """Full record for one signal through the V3 backtest engine."""

    signal: V3SignalInput
    v3_decision: V3EntryDecision
    exec_label: str           # execution label derived from V3 decision
    trade: SimulatedTrade     # filled or no-fill SimulatedTrade
    maturation_status: str    # FULL / PARTIAL / NO_DATA
    n_forward_bars: int       # actual forward bars available
    benchmark_return_20d: Optional[float] = None  # 0050 gross return over same window
    alpha_20d: Optional[float] = None             # trade.net_return_pct - benchmark gross


@dataclass
class V3BacktestResult:
    """Aggregate result from one V3BacktestEngine.run() call."""

    engine_version: str = ENGINE_VERSION
    research_version: str = RESEARCH_VERSION
    parameter_hash: str = PARAMETER_HASH
    run_at: str = ""
    in_sample_warning: str = IN_SAMPLE_WARNING

    # Input counts
    n_input: int = 0
    n_analyzed: int = 0
    n_skipped_no_history: int = 0   # insufficient OHLCV bars before signal_date
    n_skipped_decision: int = 0     # AVOID_CHASING / NO_ENTRY / INSUFFICIENT_DATA

    # Trade fill counts
    n_filled: int = 0
    n_no_fill_expired: int = 0      # waited but trigger never fired
    n_full_matured: int = 0          # filled + >= HOLD_DAYS forward bars
    n_partial_matured: int = 0       # filled + 1 to HOLD_DAYS-1 forward bars

    # Distributions
    decision_distribution: Dict[str, int] = field(default_factory=dict)
    setup_distribution: Dict[str, int] = field(default_factory=dict)

    # Performance — filled trades only
    mean_net_return: Optional[float] = None
    median_net_return: Optional[float] = None
    win_rate: Optional[float] = None
    mean_alpha_20d: Optional[float] = None

    # Raw records (all signals, including skips)
    rows: List[V3BacktestRow] = field(default_factory=list)


# ── Main engine ────────────────────────────────────────────────────────────────

class V3BacktestEngine:
    """
    Historical backtest engine for V3 entry timing strategy.

    Parameters
    ----------
    conn : sqlite3.Connection
        Read-only connection to platform.db. Engine never writes.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._analyzer = V3EntryTimingAnalyzer()
        self._sim = EntryTimingExecutionSimulator()

    def run(self, signals: List[V3SignalInput]) -> V3BacktestResult:
        """
        Run V3 backtest over the given signal list.

        Each signal is processed independently (no cross-signal leakage).
        Returns V3BacktestResult with per-signal rows and aggregate stats.
        """
        result = V3BacktestResult(
            run_at=datetime.now(UTC).isoformat(),
            n_input=len(signals),
        )

        for signal in signals:
            # ── 1. Load history (no look-ahead) ──────────────────────────────
            history = self._load_history(signal.stock_id, signal.signal_date)
            if history is None or len(history) < MIN_BARS_FULL:
                result.n_skipped_no_history += 1
                continue

            # ── 2. Run V3 analyzer ────────────────────────────────────────────
            v3 = self._analyzer.analyze(
                signal.stock_id, history, signal.market_regime
            )
            result.n_analyzed += 1

            dec = v3.entry_decision
            result.decision_distribution[dec] = (
                result.decision_distribution.get(dec, 0) + 1
            )
            result.setup_distribution[v3.setup_type] = (
                result.setup_distribution.get(v3.setup_type, 0) + 1
            )

            # ── 3. Skip if V3 says no entry ───────────────────────────────────
            if dec in _SKIP_DECISIONS:
                result.n_skipped_decision += 1
                skip_trade = SimulatedTrade(
                    signal_date=signal.signal_date,
                    stock_id=signal.stock_id,
                    entry_label=dec,
                    stop_price=v3.stop_price or 0.0,
                    target_price=v3.target_price or 0.0,
                    no_fill_reason=NO_FILL_SKIP_LABEL,
                    simulation_note=f"V3 decision={dec}; no entry attempted",
                )
                result.rows.append(V3BacktestRow(
                    signal=signal,
                    v3_decision=v3,
                    exec_label=dec,
                    trade=skip_trade,
                    maturation_status=MATURED_NONE,
                    n_forward_bars=0,
                ))
                continue

            # ── 4. Load post-signal OHLCV ─────────────────────────────────────
            post_ohlcv = self._load_post_signal(signal.stock_id, signal.signal_date)
            n_forward = len(post_ohlcv)
            maturation = (
                MATURED_FULL if n_forward >= HOLD_DAYS
                else MATURED_PARTIAL if n_forward > 0
                else MATURED_NONE
            )

            # ── 5. Simulate trade ─────────────────────────────────────────────
            exec_label, trade = self._simulate_v3_entry(signal, v3, post_ohlcv)

            if trade.filled:
                result.n_filled += 1
                if maturation == MATURED_FULL:
                    result.n_full_matured += 1
                else:
                    result.n_partial_matured += 1
            elif trade.no_fill_reason == NO_FILL_EXPIRED:
                result.n_no_fill_expired += 1

            # ── 6. Compute benchmark ──────────────────────────────────────────
            bm_return = None
            alpha = None
            if trade.filled and trade.fill_date and trade.exit_date:
                bm_return = self._compute_benchmark_return(
                    trade.fill_date, trade.exit_date
                )
                if bm_return is not None and trade.net_return_pct is not None:
                    alpha = round(trade.net_return_pct - bm_return, 4)

            result.rows.append(V3BacktestRow(
                signal=signal,
                v3_decision=v3,
                exec_label=exec_label,
                trade=trade,
                maturation_status=maturation,
                n_forward_bars=n_forward,
                benchmark_return_20d=bm_return,
                alpha_20d=alpha,
            ))

        # ── 7. Aggregate performance ──────────────────────────────────────────
        filled_returns = [
            row.trade.net_return_pct
            for row in result.rows
            if row.trade.filled and row.trade.net_return_pct is not None
        ]
        if filled_returns:
            n = len(filled_returns)
            result.mean_net_return = round(sum(filled_returns) / n, 4)
            result.win_rate = round(
                sum(1 for r in filled_returns if r > 0) / n * 100.0, 2
            )
            sorted_rets = sorted(filled_returns)
            mid = n // 2
            result.median_net_return = (
                sorted_rets[mid] if n % 2 == 1
                else round((sorted_rets[mid - 1] + sorted_rets[mid]) / 2, 4)
            )

        alpha_values = [
            row.alpha_20d for row in result.rows if row.alpha_20d is not None
        ]
        if alpha_values:
            result.mean_alpha_20d = round(
                sum(alpha_values) / len(alpha_values), 4
            )

        return result

    # ── Simulation dispatch ────────────────────────────────────────────────────

    def _simulate_v3_entry(
        self,
        signal: V3SignalInput,
        v3: V3EntryDecision,
        post_ohlcv: pd.DataFrame,
    ) -> tuple:
        """
        Map V3 decision to execution model and simulate the trade.

        Returns (exec_label, SimulatedTrade).
        """
        dec = v3.entry_decision

        stop_price = v3.stop_price or 0.0
        # If target unavailable, use sentinel so target never fires spuriously.
        target_price = v3.target_price if (v3.target_price and v3.target_price > 0) else 999999.0

        trade = SimulatedTrade(
            signal_date=signal.signal_date,
            stock_id=signal.stock_id,
            entry_label=dec,
            v1_decision_label=v3.setup_type,
            planned_entry=v3.entry_price or 0.0,
            stop_price=stop_price,
            target_price=target_price,
            prior_20d_high=v3.prior_20d_high,
            entry_order_type=ENTRY_DIRECT_NEXT_OPEN,
        )

        if dec in _SKIP_DECISIONS:
            trade.no_fill_reason = NO_FILL_SKIP_LABEL
            trade.simulation_note = f"V3 decision={dec}; no entry attempted"
            return dec, trade

        if post_ohlcv.empty:
            trade.no_fill_reason = NO_FILL_NO_HIST
            trade.simulation_note = "No post-signal OHLCV data"
            return dec, trade

        if dec == DIRECT_ENTRY:
            exec_label = "ENTRY_READY"
            trade.entry_order_type = ENTRY_DIRECT_NEXT_OPEN
            self._sim._fill_next_open(trade, post_ohlcv)

        elif dec == WAIT_MA20_PULLBACK:
            exec_label = "V3_WAIT_MA20"
            trade.entry_order_type = ENTRY_CONFIRMED_NEXT_OPEN
            limit_price = v3.proposed_limit_price
            if not limit_price or limit_price <= 0:
                trade.no_fill_reason = NO_FILL_NO_HIST
                trade.simulation_note = "WAIT_MA20_PULLBACK: proposed_limit_price not set"
                return exec_label, trade
            self._simulate_wait_level(trade, post_ohlcv, limit_price)

        elif dec == WAIT_MA60_SUPPORT:
            exec_label = "V3_WAIT_MA60"
            trade.entry_order_type = ENTRY_CONFIRMED_NEXT_OPEN
            limit_price = v3.proposed_limit_price
            if not limit_price or limit_price <= 0:
                trade.no_fill_reason = NO_FILL_NO_HIST
                trade.simulation_note = "WAIT_MA60_SUPPORT: proposed_limit_price not set (no MA60)"
                return exec_label, trade
            self._simulate_wait_level(trade, post_ohlcv, limit_price)

        elif dec == WAIT_BREAKOUT_CONFIRMATION:
            exec_label = "V3_WAIT_BREAKOUT"
            trade.entry_order_type = ENTRY_CONFIRMED_NEXT_OPEN
            self._sim._wait_for_breakout(
                trade, post_ohlcv, v3.prior_20d_high, EXPIRY_DAYS
            )

        else:
            # Fallback: unknown decision (should not happen)
            exec_label = dec
            trade.no_fill_reason = NO_FILL_SKIP_LABEL
            trade.simulation_note = f"Unhandled V3 decision: {dec}"

        return exec_label, trade

    def _simulate_wait_level(
        self,
        trade: SimulatedTrade,
        post: pd.DataFrame,
        trigger_price: float,
        expiry_days: int = EXPIRY_DAYS,
    ) -> None:
        """
        V3 level-trigger: fire when daily LOW ≤ trigger_price.
        Entry: OPEN of the NEXT bar after trigger candle (CONFIRMED_NEXT_OPEN).

        Unlike execution_simulator._wait_for_pullback which derives the trigger
        from stop_price, V3 uses the actual MA level (MA20 or MA60) stored in
        proposed_limit_price — more precise, no stop-price approximation needed.

        SA-3 / SA-4 / SA-5 intrabar rules apply via _run_hold.
        """
        window = post.iloc[:expiry_days]
        trade.expiration_date = window.iloc[-1]["date"] if not window.empty else None

        for i, row in window.iterrows():
            if float(row["low"]) <= trigger_price:
                next_idx = i + 1
                if next_idx >= len(post):
                    break  # trigger fired but no next bar → treat as expired
                entry_row = post.iloc[next_idx]
                fill_price = float(entry_row["open"])

                trade.filled = True
                trade.fill_date = entry_row["date"]
                trade.fill_price = fill_price
                trade.waiting_days = (entry_row["date"] - trade.signal_date).days
                trade.simulation_note = (
                    f"V3 level trigger: LOW {float(row['low']):.2f}"
                    f" ≤ {trigger_price:.2f}; fill next OPEN {fill_price:.2f}"
                )

                # SA-4: gap down through stop on entry day
                if fill_price <= trade.stop_price:
                    trade.gap_slippage = True
                    trade.exit_date = entry_row["date"]
                    trade.exit_price = fill_price
                    trade.exit_reason = EXIT_GAP_STOP
                    trade.stop_hit = True
                    self._sim._compute_pnl(trade)
                    return

                hold_start = next_idx + 1
                hold_bars = post.iloc[hold_start : hold_start + HOLD_DAYS]
                self._sim._run_hold(trade, hold_bars)
                return

        trade.no_fill_reason = NO_FILL_EXPIRED
        trade.simulation_note = (
            f"V3 level trigger: no LOW ≤ {trigger_price:.2f}"
            f" in {expiry_days} bars"
        )

    # ── Data loading ───────────────────────────────────────────────────────────

    def _load_history(
        self,
        stock_id: str,
        as_of_date: date,
    ) -> Optional[pd.DataFrame]:
        """
        Load OHLCV up to and including as_of_date (no look-ahead guarantee).
        Returns None when no rows found.
        """
        rows = self._conn.execute(
            "SELECT date, open, high, low, close, volume FROM daily_prices "
            "WHERE stock_id = ? AND date <= ? ORDER BY date",
            (stock_id, str(as_of_date)),
        ).fetchall()
        if not rows:
            return None
        df = pd.DataFrame(
            rows, columns=["date", "open", "high", "low", "close", "volume"]
        )
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df

    def _load_post_signal(
        self,
        stock_id: str,
        signal_date: date,
    ) -> pd.DataFrame:
        """Load OHLCV bars strictly after signal_date."""
        rows = self._conn.execute(
            "SELECT date, open, high, low, close, volume FROM daily_prices "
            "WHERE stock_id = ? AND date > ? ORDER BY date",
            (stock_id, str(signal_date)),
        ).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(
            rows, columns=["date", "open", "high", "low", "close", "volume"]
        )
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df

    def _compute_benchmark_return(
        self,
        fill_date: date,
        exit_date: date,
    ) -> Optional[float]:
        """
        0050 gross return: OPEN of fill_date to CLOSE of exit_date.

        Returns None when 0050 data is unavailable for one or both dates.
        Does not subtract fees (benchmark held passively; alpha accounts for V3 fees).
        """
        rows = self._conn.execute(
            "SELECT date, open, close FROM daily_prices "
            "WHERE stock_id='0050' AND date IN (?, ?) ORDER BY date",
            (str(fill_date), str(exit_date)),
        ).fetchall()
        if len(rows) < 2:
            return None
        entry_price = float(rows[0][1])   # open of fill_date
        exit_price = float(rows[-1][2])   # close of exit_date
        if entry_price <= 0:
            return None
        return round((exit_price - entry_price) / entry_price * 100.0, 4)


# ── Convenience loader ─────────────────────────────────────────────────────────

def load_buy_signals_for_backtest(conn: sqlite3.Connection) -> List[V3SignalInput]:
    """
    Load buy/strong_buy signals from forward_signals as V3SignalInput.

    Uses stored market_regime_at_signal if available, else 'unknown'.
    Returns one input per (stock_id, trade_date) pair, deduped.
    """
    rows = conn.execute(
        "SELECT DISTINCT stock_id, trade_date, market_regime_at_signal "
        "FROM forward_signals WHERE trade_signal IN ('buy', 'strong_buy') "
        "ORDER BY trade_date, stock_id"
    ).fetchall()
    return [
        V3SignalInput(
            signal_date=date.fromisoformat(row[1]),
            stock_id=row[0],
            market_regime=row[2] or "unknown",
            source="forward_signals",
        )
        for row in rows
    ]
