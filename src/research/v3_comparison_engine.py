"""
v3_comparison_engine.py — Fair V3 vs Baseline Performance Comparison.

RESEARCH ONLY — NOT A LIVE TRADING SYSTEM.

Compares four strategies on the same (stock_id, signal_date) universe:
  A: Direct Next Open  — always ENTRY_READY, fill at D+1 OPEN
  B: V1/V2 Labels      — map forward_signals.decision_label to entry label
  C: Hybrid V1         — apply HybridDecisionService rules (P1–P4)
  D: V3                — apply V3EntryTimingAnalyzer decisions

Fair Comparison Contract:
  - Same (stock_id, signal_date) universe per horizon
  - Same stop/target policy: Baselines A/B/C use MA20*(1-0.03); D uses V3 own
  - Same exit rules: stop-or-target-or-horizon
  - Same fees: FEES_PCT = 0.585%
  - Same benchmark: 0050 gross return (open[fill_date] → close[exit_date])
  - No-fills: 0% return (SA-7 opportunity cost)

Horizons: 5D (default), 10D (where available)

FORBIDDEN: Do NOT write to any production table. Do NOT modify MODEL_VERSION,
           ForwardSignals, execution_simulator.py, or v3_entry_strategy.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.research.execution_simulator import FEES_PCT
from src.research.hybrid_entry_strategy import (
    HybridAction,
    HybridDecisionService,
    HybridStrategyConfig,
)
from src.research.v3_entry_strategy import (
    AVOID_CHASING,
    DIRECT_ENTRY,
    INSUFFICIENT_DATA,
    NO_ENTRY,
    STOP_BUFFER,
    WAIT_BREAKOUT_CONFIRMATION,
    WAIT_MA20_PULLBACK,
    WAIT_MA60_SUPPORT,
    V3EntryTimingAnalyzer,
)

logger = logging.getLogger(__name__)

# ── Engine constants ───────────────────────────────────────────────────────────

COMPARISON_VERSION = "comp_v1"
ENGINE_ID = "v3_comparison_v1"

STRATEGY_A = "A_direct"
STRATEGY_B = "B_v1v2"
STRATEGY_C = "C_hybrid"
STRATEGY_D = "D_v3"
ALL_STRATEGIES = [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]

HORIZON_5D = 5
HORIZON_10D = 10
DEFAULT_HORIZONS = [HORIZON_5D, HORIZON_10D]

MIN_BARS_5D = 5
MIN_BARS_10D = 10

# Stop/target reconstruction for Baselines A/B/C
_STOP_BUFFER = STOP_BUFFER          # 0.03 → stop = MA20 * (1 - 0.03)
_TARGET_MULT = 1.06                 # target = MA20 * (1 + 0.06) → 2:1 R/R
_MA20_TRIGGER_BUFFER = _STOP_BUFFER  # pullback zone: LOW ≤ MA20 * (1 + 0.03)
_MIN_HISTORY_BARS = 20               # minimum bars for MA20 on signal_date

# Decision label constants (from forward_signals)
_FS_WAIT_PULLBACK = "wait_pullback"
_FS_BUY = "buy"
_FS_STRONG_BUY = "strong_buy"

# V1/V2 entry labels (simulation)
_ENTRY_READY = "ENTRY_READY"
_WAIT_FOR_PULLBACK = "WAIT_FOR_PULLBACK"

# No-fill reasons
_NO_FILL_NO_HIST = "INSUFFICIENT_HIST"
_NO_FILL_SKIP = "STRATEGY_SKIP"
_NO_FILL_NO_TRIGGER = "NO_TRIGGER"
_NO_FILL_EXPIRED = "EXPIRED"

# Exit reasons
_EXIT_STOP = "STOP"
_EXIT_GAP_STOP = "GAP_STOP"
_EXIT_AMBIGUOUS_STOP = "AMBIGUOUS_STOP_FIRST"
_EXIT_TARGET = "TARGET"
_EXIT_HORIZON = "HORIZON"


# ── Parameter hash ─────────────────────────────────────────────────────────────

def _compute_param_hash() -> str:
    params = {
        "comparison_version": COMPARISON_VERSION,
        "strategies": ALL_STRATEGIES,
        "horizons": DEFAULT_HORIZONS,
        "stop_buffer": _STOP_BUFFER,
        "target_mult": _TARGET_MULT,
        "fees_pct": FEES_PCT,
        "min_history_bars": _MIN_HISTORY_BARS,
        "benchmark_stock": "0050",
        "no_fill_return": 0.0,
        "sa3_ambiguous": "stop_first",
        "sa4_gap_down": "open",
    }
    raw = json.dumps(params, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


PARAMETER_HASH = _compute_param_hash()


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class DataReadinessReport:
    """Per-horizon audit of signal universe maturity."""
    run_at: str
    total_signals: int
    n_5d_eligible: int    # post_bars >= 5
    n_10d_eligible: int   # post_bars >= 10
    n_no_data: int        # post_bars == 0
    max_post_bars: int
    min_post_bars: int
    signal_date_range: Tuple[str, str]
    verdict_5d: str       # READY / NOT_READY
    verdict_10d: str
    note: str


@dataclass
class ComparisonRow:
    """One row per (stock_id, signal_date, strategy, horizon_days)."""

    # Identity
    experiment_id: str          # "{stock_id}_{signal_date}_{strategy}_{horizon}d"
    stock_id: str
    signal_date: str
    strategy: str               # A_direct / B_v1v2 / C_hybrid / D_v3
    horizon_days: int

    # Signal features
    original_label: Optional[str]       # forward_signals.decision_label
    market_regime: Optional[str]
    ma20_gap_pct: Optional[float]
    n_post_bars: int

    # Stop/target
    stop_price: Optional[float]
    target_price: Optional[float]
    stop_source: str            # "forward_signals" / "reconstructed" / "v3_own" / "none"

    # Strategy decision
    sim_entry_label: str        # ENTRY_READY / WAIT_FOR_PULLBACK / V3_WAIT_MA20 / SKIP / etc.
    hybrid_action: Optional[str] = None
    v3_decision: Optional[str] = None

    # Trade outcome
    filled: bool = False
    fill_date: Optional[str] = None
    fill_price: Optional[float] = None
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # STOP / TARGET / HORIZON / GAP_STOP
    no_fill_reason: Optional[str] = None

    # Returns (SA-7: no-fill → 0.0)
    gross_return: float = 0.0
    net_return: float = 0.0
    benchmark_return: Optional[float] = None
    gross_alpha: Optional[float] = None
    net_alpha: Optional[float] = None

    # Notes
    simulation_note: str = ""


@dataclass
class StrategyStats:
    """Aggregate statistics for one strategy × horizon."""
    strategy: str
    horizon_days: int
    n_signals: int
    n_filled: int
    fill_rate: float
    mean_gross_return: float
    mean_net_return: float
    median_net_return: float
    win_rate: float              # net > 0 (fills only)
    mean_net_alpha: Optional[float]
    n_benchmark_paired: int


@dataclass
class PairedStats:
    """Statistical comparison of D vs one baseline strategy."""
    candidate: str              # always D_v3
    baseline: str               # A / B / C
    horizon_days: int
    n_paired: int               # signals where both strategies have net_alpha
    mean_delta: float           # mean(D_net_alpha - base_net_alpha)
    median_delta: float
    ci_lower: float             # 95% bootstrap CI
    ci_upper: float
    p_value_sign: float         # two-sided sign test
    cohens_d: float
    verdict: str                # SIGNIFICANT_POSITIVE / SIGNIFICANT_NEGATIVE / INCONCLUSIVE / INSUFFICIENT_DATA


@dataclass
class ComparisonResult:
    """Full V3 vs Baseline comparison output."""
    engine_id: str
    comparison_version: str
    parameter_hash: str
    run_at: str
    horizon_days: int
    in_sample_warning: str
    data_readiness: DataReadinessReport
    n_universe: int             # signals included at this horizon
    rows: List[ComparisonRow]
    strategy_stats: Dict[str, StrategyStats]
    paired_stats: List[PairedStats]  # D vs A, D vs B, D vs C
    subgroup_analysis: Dict        # by setup_type / regime / ma20_gap_quintile


# ── Helper functions ───────────────────────────────────────────────────────────

def _load_ohlcv(conn: sqlite3.Connection, stock_id: str, as_of: str) -> pd.DataFrame:
    """Load OHLCV history up to and including as_of date (no look-ahead)."""
    rows = conn.execute(
        "SELECT date, open, high, low, close, volume "
        "FROM daily_prices WHERE stock_id=? AND date<=? ORDER BY date",
        (stock_id, as_of),
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def _load_post_ohlcv(conn: sqlite3.Connection, stock_id: str, signal_date: str) -> pd.DataFrame:
    """Load OHLCV after signal_date (strictly post-signal, no look-ahead)."""
    rows = conn.execute(
        "SELECT date, open, high, low, close, volume "
        "FROM daily_prices WHERE stock_id=? AND date>? ORDER BY date",
        (stock_id, signal_date),
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def _reconstruct_stop_target(history: pd.DataFrame) -> Tuple[Optional[float], Optional[float]]:
    """
    Reconstruct stop and target from last 20 closes.
    stop = MA20 * (1 - 0.03), target = MA20 * (1 + 0.06).
    Returns (stop, target) or (None, None) if insufficient history.
    """
    if len(history) < 20:
        return None, None
    ma20 = float(history["close"].iloc[-20:].mean())
    stop = round(ma20 * (1 - _STOP_BUFFER), 4)
    target = round(ma20 * _TARGET_MULT, 4)
    return stop, target


def _compute_ma20_slope_pct(history: pd.DataFrame) -> Optional[float]:
    """
    Compute MA20 slope as pct change of MA20 over last 10 bars.
    Used by Hybrid V1 (ma20_slope_pct input).
    Returns None if insufficient history.
    """
    if len(history) < 30:
        return None
    closes = history["close"].values.astype(float)
    n = len(closes)
    # MA20 at current bar and 10 bars ago
    ma20_now = float(np.mean(closes[n - 20:n]))
    ma20_prev = float(np.mean(closes[n - 30:n - 10]))
    if ma20_prev == 0:
        return None
    return round((ma20_now - ma20_prev) / ma20_prev * 100, 4)


def _get_prior_20d_high(history: pd.DataFrame) -> Optional[float]:
    """Prior 20D high from history (excludes current bar, i.e. last 21 close)."""
    if len(history) < 21:
        return None
    highs = history["high"].values.astype(float)
    return float(np.max(highs[-21:-1]))


def _simulate_direct(post: pd.DataFrame) -> Tuple[bool, Optional[str], Optional[float]]:
    """DIRECT_NEXT_OPEN: fill at OPEN of first post-signal bar."""
    if post.empty:
        return False, None, None
    row = post.iloc[0]
    return True, str(row["date"]), float(row["open"])


def _simulate_wait_pullback(post: pd.DataFrame, ma20: float) -> Tuple[bool, Optional[str], Optional[float], str]:
    """
    WAIT_FOR_PULLBACK trigger: LOW ≤ MA20 * (1 + STOP_BUFFER).
    Fill at OPEN of bar AFTER trigger candle.
    Returns (filled, fill_date, fill_price, reason).
    """
    trigger_threshold = ma20 * (1 + _MA20_TRIGGER_BUFFER)
    for i, row in post.iterrows():
        if float(row["low"]) <= trigger_threshold:
            # Fill at OPEN of NEXT bar
            if i + 1 < len(post):
                fill_row = post.iloc[post.index.get_loc(i) + 1]
                return True, str(fill_row["date"]), float(fill_row["open"]), ""
            # Trigger on last bar — no next bar to fill
            return False, None, None, _NO_FILL_EXPIRED
    return False, None, None, _NO_FILL_NO_TRIGGER


def _simulate_wait_level(
    post: pd.DataFrame, trigger_price: float
) -> Tuple[bool, Optional[str], Optional[float], str]:
    """
    Generic wait-for-level: trigger when LOW ≤ trigger_price.
    Fill at OPEN of bar AFTER trigger candle.
    Used for WAIT_MA20_PULLBACK and WAIT_MA60_SUPPORT in V3.
    """
    for i, row in post.iterrows():
        if float(row["low"]) <= trigger_price:
            loc = post.index.get_loc(i)
            if loc + 1 < len(post):
                fill_row = post.iloc[loc + 1]
                return True, str(fill_row["date"]), float(fill_row["open"]), ""
            return False, None, None, _NO_FILL_EXPIRED
    return False, None, None, _NO_FILL_NO_TRIGGER


def _simulate_wait_breakout(
    post: pd.DataFrame, prior_20d_high: float
) -> Tuple[bool, Optional[str], Optional[float], str]:
    """
    WAIT_FOR_BREAKOUT trigger: CLOSE > prior_20d_high.
    Fill at OPEN of bar AFTER trigger candle.
    """
    for i, row in post.iterrows():
        if float(row["close"]) > prior_20d_high:
            loc = post.index.get_loc(i)
            if loc + 1 < len(post):
                fill_row = post.iloc[loc + 1]
                return True, str(fill_row["date"]), float(fill_row["open"]), ""
            return False, None, None, _NO_FILL_EXPIRED
    return False, None, None, _NO_FILL_NO_TRIGGER


def _hold_to_horizon(
    fill_price: float,
    stop_price: Optional[float],
    target_price: Optional[float],
    hold_bars: pd.DataFrame,
    horizon_days: int,
) -> Tuple[str, float, str]:
    """
    Simulate hold from fill through horizon, applying SA-3/SA-4.
    Returns (exit_date, exit_price, exit_reason).
    """
    bars = hold_bars.iloc[:horizon_days]
    if bars.empty:
        # No bars to hold — exits at fill_price (data boundary)
        return hold_bars.index[0] if not hold_bars.empty else "", fill_price, _EXIT_HORIZON

    for _, row in bars.iterrows():
        o, h, low_p = float(row["open"]), float(row["high"]), float(row["low"])
        exit_date = str(row["date"])

        # SA-4: gap down through stop → exit at open
        if stop_price is not None and o <= stop_price:
            return exit_date, o, _EXIT_GAP_STOP

        # SA-3: ambiguous day — both stop and target reachable intrabar → stop first
        stop_hit = stop_price is not None and low_p <= stop_price
        target_hit = target_price is not None and h >= target_price
        if stop_hit and target_hit:
            return exit_date, stop_price, _EXIT_AMBIGUOUS_STOP

        if stop_hit:
            return exit_date, stop_price, _EXIT_STOP

        if target_hit:
            return exit_date, target_price, _EXIT_TARGET

    # Horizon expiry: exit at CLOSE of last bar
    last = bars.iloc[-1]
    return str(last["date"]), float(last["close"]), _EXIT_HORIZON


def _benchmark_return(
    conn: sqlite3.Connection, fill_date: str, exit_date: str
) -> Optional[float]:
    """0050 gross return: open[fill_date] → close[exit_date]."""
    rows = conn.execute(
        "SELECT date, open, close FROM daily_prices "
        "WHERE stock_id='0050' AND date IN (?,?) ORDER BY date",
        (fill_date, exit_date),
    ).fetchall()
    if len(rows) < 2:
        return None
    d = {r[0]: r for r in rows}
    if fill_date not in d or exit_date not in d:
        return None
    entry_open = float(d[fill_date][1])
    exit_close = float(d[exit_date][2])
    if entry_open == 0:
        return None
    return round((exit_close - entry_open) / entry_open, 6)


def _benchmark_return_range(
    conn: sqlite3.Connection, start_date: str, horizon_days: int
) -> Optional[float]:
    """
    0050 benchmark for no-fill: open[D+1] → close[D+horizon].
    start_date = signal_date; we need the first post-signal bar's open.
    """
    rows = conn.execute(
        "SELECT date, open, close FROM daily_prices "
        "WHERE stock_id='0050' AND date>? ORDER BY date LIMIT ?",
        (start_date, horizon_days),
    ).fetchall()
    if len(rows) < horizon_days:
        return None
    entry_open = float(rows[0][1])
    exit_close = float(rows[-1][2])
    if entry_open == 0:
        return None
    return round((exit_close - entry_open) / entry_open, 6)


# ── Bootstrap statistics ───────────────────────────────────────────────────────

def _bootstrap_ci(
    deltas: List[float], n_boot: int = 10_000, ci: float = 0.95
) -> Tuple[float, float]:
    rng = np.random.default_rng(seed=42)
    n = len(deltas)
    arr = np.array(deltas)
    boot_means = [float(np.mean(rng.choice(arr, size=n, replace=True))) for _ in range(n_boot)]
    alpha = (1 - ci) / 2
    return float(np.percentile(boot_means, alpha * 100)), float(np.percentile(boot_means, (1 - alpha) * 100))


def _sign_test_p(deltas: List[float]) -> float:
    """Two-sided sign test p-value (exact binomial under H0: p=0.5)."""
    from math import comb
    arr = [d for d in deltas if d != 0.0]
    if not arr:
        return 1.0
    n = len(arr)
    k = sum(1 for d in arr if d > 0)
    # P(X >= k) + P(X <= n-k) under Bin(n, 0.5)
    total = 2 ** n
    p_one = sum(comb(n, i) for i in range(k, n + 1)) / total
    p_other = sum(comb(n, i) for i in range(0, n - k + 1)) / total
    return min(2 * min(p_one, p_other), 1.0)


def _cohens_d(deltas: List[float]) -> float:
    if len(deltas) < 2:
        return 0.0
    arr = np.array(deltas)
    std = float(np.std(arr, ddof=1))
    if std == 0:
        return 0.0
    return float(np.mean(arr) / std)


def _paired_stats(candidate_rows: List[ComparisonRow], baseline_rows: List[ComparisonRow], horizon: int) -> PairedStats:
    """Compute paired statistics for D vs one baseline, keyed by (stock_id, signal_date)."""
    baseline_strategy = baseline_rows[0].strategy if baseline_rows else "?"
    base_map = {(r.stock_id, r.signal_date): r.net_alpha for r in baseline_rows if r.net_alpha is not None}
    cand_map = {(r.stock_id, r.signal_date): r.net_alpha for r in candidate_rows if r.net_alpha is not None}
    pairs = [(cand_map[k] - base_map[k]) for k in cand_map if k in base_map]

    if len(pairs) < 5:
        return PairedStats(
            candidate=STRATEGY_D, baseline=baseline_strategy, horizon_days=horizon,
            n_paired=len(pairs), mean_delta=0.0, median_delta=0.0,
            ci_lower=0.0, ci_upper=0.0, p_value_sign=1.0, cohens_d=0.0,
            verdict="INSUFFICIENT_DATA",
        )

    ci_lo, ci_hi = _bootstrap_ci(pairs)
    p_val = _sign_test_p(pairs)
    d = _cohens_d(pairs)
    mean_d = float(np.mean(pairs))

    if ci_lo > 0:
        verdict = "SIGNIFICANT_POSITIVE"
    elif ci_hi < 0:
        verdict = "SIGNIFICANT_NEGATIVE"
    else:
        verdict = "INCONCLUSIVE"

    return PairedStats(
        candidate=STRATEGY_D, baseline=baseline_strategy, horizon_days=horizon,
        n_paired=len(pairs), mean_delta=round(mean_d, 6),
        median_delta=round(float(np.median(pairs)), 6),
        ci_lower=round(ci_lo, 6), ci_upper=round(ci_hi, 6),
        p_value_sign=round(p_val, 4), cohens_d=round(d, 4),
        verdict=verdict,
    )


def _strategy_stats(rows: List[ComparisonRow], strategy: str, horizon: int) -> StrategyStats:
    subset = [r for r in rows if r.strategy == strategy and r.horizon_days == horizon]
    n = len(subset)
    if n == 0:
        return StrategyStats(strategy=strategy, horizon_days=horizon, n_signals=0,
                             n_filled=0, fill_rate=0.0, mean_gross_return=0.0,
                             mean_net_return=0.0, median_net_return=0.0,
                             win_rate=0.0, mean_net_alpha=None, n_benchmark_paired=0)
    filled = [r for r in subset if r.filled]
    n_filled = len(filled)
    net_returns = [r.net_return for r in subset]
    filled_nets = [r.net_return for r in filled]
    alphas = [r.net_alpha for r in subset if r.net_alpha is not None]
    win_rate = round(sum(1 for x in filled_nets if x > 0) / max(n_filled, 1), 4) if filled_nets else 0.0
    return StrategyStats(
        strategy=strategy, horizon_days=horizon, n_signals=n, n_filled=n_filled,
        fill_rate=round(n_filled / n, 4),
        mean_gross_return=round(float(np.mean([r.gross_return for r in subset])), 6),
        mean_net_return=round(float(np.mean(net_returns)), 6),
        median_net_return=round(float(np.median(net_returns)), 6),
        win_rate=win_rate,
        mean_net_alpha=round(float(np.mean(alphas)), 6) if alphas else None,
        n_benchmark_paired=len(alphas),
    )


# ── Subgroup analysis ──────────────────────────────────────────────────────────

def _subgroup_mean_net_alpha(rows: List[ComparisonRow], strategy: str, horizon: int) -> Dict:
    subset = [r for r in rows if r.strategy == strategy and r.horizon_days == horizon]

    def group_stats(groups: Dict[str, List[float]]) -> Dict:
        return {k: {"n": len(v), "mean_net_alpha": round(float(np.mean(v)), 6)}
                for k, v in groups.items() if v}

    # By V3 decision (strategy D) or sim_entry_label
    by_decision: Dict[str, List[float]] = {}
    by_regime: Dict[str, List[float]] = {}
    by_gap_quintile: Dict[str, List[float]] = {}

    for r in subset:
        alpha = r.net_alpha
        if alpha is None:
            continue
        label = r.v3_decision or r.sim_entry_label or "unknown"
        by_decision.setdefault(label, []).append(alpha)
        regime = r.market_regime or "unknown"
        by_regime.setdefault(regime, []).append(alpha)
        if r.ma20_gap_pct is not None:
            q = "Q1_<-5%" if r.ma20_gap_pct < -5 else \
                "Q2_-5to0" if r.ma20_gap_pct < 0 else \
                "Q3_0to5" if r.ma20_gap_pct < 5 else \
                "Q4_5to10" if r.ma20_gap_pct < 10 else "Q5_>10%"
            by_gap_quintile.setdefault(q, []).append(alpha)

    return {
        "by_decision": group_stats(by_decision),
        "by_regime": group_stats(by_regime),
        "by_ma20_gap_quintile": group_stats(by_gap_quintile),
    }


# ── Main Engine ────────────────────────────────────────────────────────────────

class V3ComparisonEngine:
    """
    Fair V3 vs Baseline Performance Comparison Engine.

    Usage:
        engine = V3ComparisonEngine(conn)
        report = engine.run_data_readiness_audit()
        result_5d = engine.run_comparison(horizon_days=5)
        result_10d = engine.run_comparison(horizon_days=10)
    """

    IN_SAMPLE_WARNING = (
        "IN-SAMPLE WARNING: These signals are drawn from forward_signals which were "
        "generated by the same MODEL_VERSION v8.0 used in the V3 analyzer. "
        "Results cannot be used to validate the scoring model itself. "
        "Research use only — not for production deployment decisions."
    )

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._v3 = V3EntryTimingAnalyzer()
        self._hybrid_svc = HybridDecisionService(HybridStrategyConfig())

    # ── Data Readiness ─────────────────────────────────────────────────────────

    def run_data_readiness_audit(self) -> DataReadinessReport:
        """Classify signal universe by maturity. Returns DataReadinessReport."""
        rows = self._conn.execute(
            "SELECT fs.trade_date, fs.stock_id, "
            "  (SELECT COUNT(*) FROM daily_prices dp "
            "   WHERE dp.stock_id=fs.stock_id AND dp.date > fs.trade_date) as post_bars "
            "FROM forward_signals fs "
            "WHERE fs.trade_signal IN ('buy','strong_buy')"
        ).fetchall()

        if not rows:
            return DataReadinessReport(
                run_at=datetime.now(UTC).isoformat(), total_signals=0,
                n_5d_eligible=0, n_10d_eligible=0, n_no_data=0,
                max_post_bars=0, min_post_bars=0,
                signal_date_range=("N/A", "N/A"),
                verdict_5d="NOT_READY", verdict_10d="NOT_READY",
                note="No buy/strong_buy signals found.",
            )

        post_bars = [r[2] for r in rows]
        dates = sorted(set(r[0] for r in rows))
        n_5d = sum(1 for b in post_bars if b >= MIN_BARS_5D)
        n_10d = sum(1 for b in post_bars if b >= MIN_BARS_10D)
        n_no = sum(1 for b in post_bars if b == 0)
        return DataReadinessReport(
            run_at=datetime.now(UTC).isoformat(),
            total_signals=len(rows),
            n_5d_eligible=n_5d,
            n_10d_eligible=n_10d,
            n_no_data=n_no,
            max_post_bars=max(post_bars),
            min_post_bars=min(post_bars),
            signal_date_range=(dates[0], dates[-1]),
            verdict_5d="READY" if n_5d >= 50 else "NOT_READY",
            verdict_10d="READY" if n_10d >= 50 else "NOT_READY",
            note=(
                f"5D: {n_5d}/{len(rows)} eligible. "
                f"10D: {n_10d}/{len(rows)} eligible. "
                f"No 20D windows available (max {max(post_bars)} post bars)."
            ),
        )

    # ── Main comparison run ────────────────────────────────────────────────────

    def run_comparison(self, horizon_days: int = HORIZON_5D) -> ComparisonResult:
        """
        Run all 4 strategies on eligible universe for given horizon.
        Returns ComparisonResult.
        """
        readiness = self.run_data_readiness_audit()
        signals = self._load_signals(horizon_days)
        rows: List[ComparisonRow] = []

        for sig in signals:
            stock_id = sig["stock_id"]
            signal_date = sig["trade_date"]
            history = _load_ohlcv(self._conn, stock_id, signal_date)
            post = _load_post_ohlcv(self._conn, stock_id, signal_date)

            # Limit post to horizon for fair comparison
            post_h = post.iloc[:horizon_days].reset_index(drop=True)
            if post_h.empty:
                continue

            # Per-signal features (computed from history)
            ma20 = self._compute_ma20(history)
            stop_recon, target_recon = _reconstruct_stop_target(history) if ma20 else (None, None)
            ma20_slope = _compute_ma20_slope_pct(history)

            # Strategy A: Direct
            rows.append(self._run_strategy_a(sig, post_h, history, stop_recon, target_recon, horizon_days))
            # Strategy B: V1/V2 Labels
            rows.append(self._run_strategy_b(sig, post_h, history, ma20, stop_recon, target_recon, horizon_days))
            # Strategy C: Hybrid V1
            rows.append(self._run_strategy_c(sig, post_h, history, ma20, stop_recon, target_recon, ma20_slope, horizon_days))
            # Strategy D: V3
            rows.append(self._run_strategy_d(sig, post, post_h, history, horizon_days))

        # Compute statistics
        stats = {s: _strategy_stats(rows, s, horizon_days) for s in ALL_STRATEGIES}
        d_rows = [r for r in rows if r.strategy == STRATEGY_D]
        paired = [
            _paired_stats(d_rows, [r for r in rows if r.strategy == s], horizon_days)
            for s in [STRATEGY_A, STRATEGY_B, STRATEGY_C]
        ]
        subgroups = _subgroup_mean_net_alpha(rows, STRATEGY_D, horizon_days)

        return ComparisonResult(
            engine_id=ENGINE_ID,
            comparison_version=COMPARISON_VERSION,
            parameter_hash=PARAMETER_HASH,
            run_at=datetime.now(UTC).isoformat(),
            horizon_days=horizon_days,
            in_sample_warning=self.IN_SAMPLE_WARNING,
            data_readiness=readiness,
            n_universe=len(signals),
            rows=rows,
            strategy_stats=stats,
            paired_stats=paired,
            subgroup_analysis=subgroups,
        )

    # ── Signal loading ─────────────────────────────────────────────────────────

    def _load_signals(self, horizon_days: int) -> List[Dict]:
        """
        Load buy/strong_buy signals with sufficient post data.
        Columns aliased to internal names (market_regime, ma20_gap_pct)
        from their production names (market_regime_at_signal, ma20_gap).
        """
        # Detect which column names the DB uses (production vs test fixture)
        col_info = {r[1] for r in self._conn.execute("PRAGMA table_info(forward_signals)").fetchall()}
        regime_col = "market_regime_at_signal" if "market_regime_at_signal" in col_info else "market_regime"
        gap_col = "ma20_gap" if "ma20_gap" in col_info else "ma20_gap_pct"

        rows = self._conn.execute(
            f"SELECT fs.stock_id, fs.trade_date, fs.trade_signal, "
            f"  fs.decision_label, fs.{regime_col} AS market_regime, "
            f"  fs.{gap_col} AS ma20_gap_pct, "
            f"  fs.stop_price, fs.target1, "
            f"  (SELECT COUNT(*) FROM daily_prices dp "
            f"   WHERE dp.stock_id=fs.stock_id AND dp.date > fs.trade_date) as post_bars "
            f"FROM forward_signals fs "
            f"WHERE fs.trade_signal IN ('buy','strong_buy') "
            f"  AND (SELECT COUNT(*) FROM daily_prices dp "
            f"       WHERE dp.stock_id=fs.stock_id AND dp.date > fs.trade_date) >= ? "
            f"ORDER BY fs.trade_date, fs.stock_id",
            (horizon_days,),
        ).fetchall()
        cols = ["stock_id", "trade_date", "trade_signal", "decision_label",
                "market_regime", "ma20_gap_pct", "stop_price", "target1", "post_bars"]
        return [dict(zip(cols, r)) for r in rows]

    # ── Per-signal feature helpers ─────────────────────────────────────────────

    def _compute_ma20(self, history: pd.DataFrame) -> Optional[float]:
        if len(history) < 20:
            return None
        return float(history["close"].iloc[-20:].mean())

    def _make_row(self, sig: Dict, strategy: str, horizon_days: int) -> ComparisonRow:
        """Scaffold a ComparisonRow with signal metadata."""
        stock_id = sig["stock_id"]
        signal_date = sig["trade_date"]
        return ComparisonRow(
            experiment_id=f"{stock_id}_{signal_date}_{strategy}_{horizon_days}d",
            stock_id=stock_id,
            signal_date=signal_date,
            strategy=strategy,
            horizon_days=horizon_days,
            original_label=sig.get("decision_label"),
            market_regime=sig.get("market_regime"),
            ma20_gap_pct=float(sig["ma20_gap_pct"]) if sig.get("ma20_gap_pct") is not None else None,
            n_post_bars=int(sig.get("post_bars", 0)),
            stop_price=None,
            target_price=None,
            stop_source="none",
            sim_entry_label="ENTRY_READY",
        )

    def _apply_fill_and_hold(
        self, row: ComparisonRow, post_h: pd.DataFrame,
        fill_date: Optional[str], fill_price: Optional[float],
        no_fill_reason: Optional[str], stop: Optional[float], target: Optional[float],
        signal_date: str, horizon_days: int,
    ) -> None:
        """Apply fill outcome and hold simulation to row (mutates in-place)."""
        if fill_price is None or fill_date is None:
            row.filled = False
            row.no_fill_reason = no_fill_reason
            row.gross_return = 0.0
            row.net_return = 0.0
            bm = _benchmark_return_range(self._conn, signal_date, horizon_days)
            row.benchmark_return = bm
            row.net_alpha = round(-bm, 6) if bm is not None else None
            row.gross_alpha = row.net_alpha
            return

        # Find hold bars: post fill date
        hold_bars = post_h[post_h["date"] > fill_date].reset_index(drop=True)
        remaining = horizon_days - len(post_h[post_h["date"] <= fill_date])
        if remaining <= 0 or hold_bars.empty:
            # Filled on last horizon bar; exit at fill price (no hold)
            row.filled = True
            row.fill_date = fill_date
            row.fill_price = fill_price
            row.exit_date = fill_date
            row.exit_price = fill_price
            row.exit_reason = _EXIT_HORIZON
            row.gross_return = 0.0
            row.net_return = round(-FEES_PCT / 100, 6)
            bm = _benchmark_return(self._conn, fill_date, fill_date)
            row.benchmark_return = bm
            row.net_alpha = round(row.net_return - bm, 6) if bm is not None else None
            row.gross_alpha = round(row.gross_return - bm, 6) if bm is not None else None
            return

        exit_date, exit_price, exit_reason = _hold_to_horizon(
            fill_price, stop, target, hold_bars, remaining
        )
        gross = round((exit_price - fill_price) / fill_price, 6)
        net = round(gross - FEES_PCT / 100, 6)
        bm = _benchmark_return(self._conn, fill_date, exit_date)

        row.filled = True
        row.fill_date = fill_date
        row.fill_price = round(fill_price, 4)
        row.exit_date = exit_date
        row.exit_price = round(exit_price, 4)
        row.exit_reason = exit_reason
        row.gross_return = gross
        row.net_return = net
        row.benchmark_return = bm
        row.net_alpha = round(net - bm, 6) if bm is not None else None
        row.gross_alpha = round(gross - bm, 6) if bm is not None else None

    # ── Strategy A: Direct Next Open ───────────────────────────────────────────

    def _run_strategy_a(
        self, sig: Dict, post_h: pd.DataFrame, history: pd.DataFrame,
        stop_recon: Optional[float], target_recon: Optional[float], horizon_days: int,
    ) -> ComparisonRow:
        row = self._make_row(sig, STRATEGY_A, horizon_days)
        row.sim_entry_label = _ENTRY_READY
        stop, target, source = self._pick_stop_target(sig, stop_recon, target_recon)
        row.stop_price = stop
        row.target_price = target
        row.stop_source = source

        filled, fill_date, fill_price = _simulate_direct(post_h)
        no_fill_reason = _NO_FILL_NO_HIST if not filled else None
        self._apply_fill_and_hold(row, post_h, fill_date, fill_price,
                                  no_fill_reason, stop, target, sig["trade_date"], horizon_days)
        return row

    # ── Strategy B: V1/V2 Labels ───────────────────────────────────────────────

    def _run_strategy_b(
        self, sig: Dict, post_h: pd.DataFrame, history: pd.DataFrame,
        ma20: Optional[float], stop_recon: Optional[float], target_recon: Optional[float],
        horizon_days: int,
    ) -> ComparisonRow:
        row = self._make_row(sig, STRATEGY_B, horizon_days)
        orig = sig.get("decision_label")
        stop, target, source = self._pick_stop_target(sig, stop_recon, target_recon)
        row.stop_price = stop
        row.target_price = target
        row.stop_source = source

        # Map label
        if orig == _FS_WAIT_PULLBACK:
            row.sim_entry_label = _WAIT_FOR_PULLBACK
            if ma20 is None:
                row.no_fill_reason = _NO_FILL_NO_HIST
                row.gross_return = 0.0
                row.net_return = 0.0
                bm = _benchmark_return_range(self._conn, sig["trade_date"], horizon_days)
                row.benchmark_return = bm
                row.net_alpha = round(-bm, 6) if bm is not None else None
                row.gross_alpha = row.net_alpha
                return row
            filled, fill_date, fill_price, reason = _simulate_wait_pullback(post_h, ma20)
            no_fill_reason = reason if not filled else None
        else:
            row.sim_entry_label = _ENTRY_READY
            filled, fill_date, fill_price = _simulate_direct(post_h)
            no_fill_reason = _NO_FILL_NO_HIST if not filled else None

        self._apply_fill_and_hold(row, post_h, fill_date, fill_price,
                                  no_fill_reason, stop, target, sig["trade_date"], horizon_days)
        return row

    # ── Strategy C: Hybrid V1 ──────────────────────────────────────────────────

    def _run_strategy_c(
        self, sig: Dict, post_h: pd.DataFrame, history: pd.DataFrame,
        ma20: Optional[float], stop_recon: Optional[float], target_recon: Optional[float],
        ma20_slope: Optional[float], horizon_days: int,
    ) -> ComparisonRow:
        row = self._make_row(sig, STRATEGY_C, horizon_days)
        stop, target, source = self._pick_stop_target(sig, stop_recon, target_recon)
        row.stop_price = stop
        row.target_price = target
        row.stop_source = source

        # Map forward_signals.decision_label to V1/V2 label
        orig = sig.get("decision_label")
        v2_label = _WAIT_FOR_PULLBACK if orig == _FS_WAIT_PULLBACK else _ENTRY_READY
        regime = sig.get("market_regime") or "unknown"
        slope_pct = ma20_slope or 0.0
        ma20_trend = self._hybrid_svc.classify_ma20_trend(slope_pct)

        hdec = self._hybrid_svc.decide(
            stock_id=sig["stock_id"], signal_date=sig["trade_date"],
            v2_entry_label=v2_label, market_regime=regime,
            ma20_trend=ma20_trend, ma20_slope_pct=slope_pct,
            ma20_gap_pct=float(sig["ma20_gap_pct"]) if sig.get("ma20_gap_pct") is not None else None,
        )
        row.hybrid_action = hdec.hybrid_action.value

        if hdec.hybrid_action == HybridAction.WAIT_PULLBACK:
            row.sim_entry_label = _WAIT_FOR_PULLBACK
            if ma20 is None:
                row.no_fill_reason = _NO_FILL_NO_HIST
                row.gross_return = 0.0
                row.net_return = 0.0
                bm = _benchmark_return_range(self._conn, sig["trade_date"], horizon_days)
                row.benchmark_return = bm
                row.net_alpha = round(-bm, 6) if bm is not None else None
                row.gross_alpha = row.net_alpha
                return row
            filled, fill_date, fill_price, reason = _simulate_wait_pullback(post_h, ma20)
            no_fill_reason = reason if not filled else None
        else:
            row.sim_entry_label = _ENTRY_READY
            filled, fill_date, fill_price = _simulate_direct(post_h)
            no_fill_reason = _NO_FILL_NO_HIST if not filled else None

        self._apply_fill_and_hold(row, post_h, fill_date, fill_price,
                                  no_fill_reason, stop, target, sig["trade_date"], horizon_days)
        return row

    # ── Strategy D: V3 ────────────────────────────────────────────────────────

    def _run_strategy_d(
        self, sig: Dict, post_full: pd.DataFrame, post_h: pd.DataFrame,
        history: pd.DataFrame, horizon_days: int,
    ) -> ComparisonRow:
        row = self._make_row(sig, STRATEGY_D, horizon_days)
        regime = sig.get("market_regime") or "unknown"

        v3dec = self._v3.analyze(
            stock_id=sig["stock_id"], history=history, market_regime=regime
        )
        row.v3_decision = v3dec.entry_decision

        # V3 uses its own stop/target
        stop = float(v3dec.stop_price) if v3dec.stop_price else None
        target = float(v3dec.target_price) if v3dec.target_price else None
        row.stop_price = stop
        row.target_price = target
        row.stop_source = "v3_own" if stop is not None else "none"

        # Skip decisions
        _SKIP = {AVOID_CHASING, NO_ENTRY, INSUFFICIENT_DATA}
        if v3dec.entry_decision in _SKIP:
            row.sim_entry_label = "SKIP"
            row.no_fill_reason = _NO_FILL_SKIP
            row.gross_return = 0.0
            row.net_return = 0.0
            bm = _benchmark_return_range(self._conn, sig["trade_date"], horizon_days)
            row.benchmark_return = bm
            row.net_alpha = round(-bm, 6) if bm is not None else None
            row.gross_alpha = row.net_alpha
            return row

        # Entry simulation
        trigger_price = float(v3dec.proposed_limit_price) if v3dec.proposed_limit_price else None
        prior_20d_high = _get_prior_20d_high(history) if len(history) >= 21 else None

        if v3dec.entry_decision == DIRECT_ENTRY:
            row.sim_entry_label = "DIRECT_ENTRY"
            filled, fill_date, fill_price = _simulate_direct(post_h)
            no_fill_reason = _NO_FILL_NO_HIST if not filled else None

        elif v3dec.entry_decision in {WAIT_MA20_PULLBACK, WAIT_MA60_SUPPORT}:
            row.sim_entry_label = v3dec.entry_decision
            if trigger_price is None:
                row.no_fill_reason = _NO_FILL_NO_HIST
                filled, fill_date, fill_price = False, None, None
                no_fill_reason = _NO_FILL_NO_HIST
            else:
                filled, fill_date, fill_price, reason = _simulate_wait_level(post_h, trigger_price)
                no_fill_reason = reason if not filled else None

        elif v3dec.entry_decision == WAIT_BREAKOUT_CONFIRMATION:
            row.sim_entry_label = "WAIT_BREAKOUT_CONFIRMATION"
            if prior_20d_high is None:
                filled, fill_date, fill_price, no_fill_reason = False, None, None, _NO_FILL_NO_HIST
            else:
                filled, fill_date, fill_price, reason = _simulate_wait_breakout(post_h, prior_20d_high)
                no_fill_reason = reason if not filled else None

        else:
            row.sim_entry_label = v3dec.entry_decision
            filled, fill_date, fill_price = False, None, None
            no_fill_reason = _NO_FILL_SKIP

        fill_price_v = fill_price if filled else None
        self._apply_fill_and_hold(row, post_h, fill_date, fill_price_v,
                                  no_fill_reason, stop, target, sig["trade_date"], horizon_days)
        return row

    # ── Stop/target selection ──────────────────────────────────────────────────

    def _pick_stop_target(
        self, sig: Dict, stop_recon: Optional[float], target_recon: Optional[float]
    ) -> Tuple[Optional[float], Optional[float], str]:
        """
        For Baselines A/B/C: prefer forward_signals stop/target, fall back to reconstructed.
        Returns (stop, target, source).
        """
        fs_stop = sig.get("stop_price")
        fs_target = sig.get("target1")
        if fs_stop is not None:
            return float(fs_stop), (float(fs_target) if fs_target else target_recon), "forward_signals"
        if stop_recon is not None:
            return stop_recon, target_recon, "reconstructed"
        return None, None, "none"


# ── Public loader ──────────────────────────────────────────────────────────────

def load_comparison_signals(conn: sqlite3.Connection, horizon_days: int = HORIZON_5D) -> List[Dict]:
    """Load buy/strong_buy signals eligible for the given horizon (public helper)."""
    engine = V3ComparisonEngine(conn)
    return engine._load_signals(horizon_days)
