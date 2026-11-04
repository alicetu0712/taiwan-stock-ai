"""
backtest_full.py — V1 vs V2 three-way fair backtest (Part D).

RESEARCH ONLY — NOT A LIVE TRADING SYSTEM.

Comparison definitions:
  A) Signal Selection: V2 ENTRY_READY vs V1 all BUY/STRONG_BUY using
     SAME fwd_return_20d data. Shows signal quality difference only.
  B) Filled Trades: V2 filled simulated trades vs V1 baseline.
     WARNING: selection bias — only V2 trades that filled are included.
  C) Full Opportunity Set (main): same V1 signal pool, V2 filled trades
     receive simulated returns; V2 no-fill signals receive 0% (SA-7).
     This is the definitive comparison for entry timing advantage.

Return note:
  V1 uses ForwardSignal.fwd_return_20d (actual next-open proxy).
  V2 uses OHLC simulation (SA-3 through SA-5).
  Returns are NOT directly comparable without entry-price adjustment.
"""

from __future__ import annotations

import logging
import random
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.research.execution_simulator import (
    EntryTimingExecutionSimulator,
    SimulatedTrade,
)

logger = logging.getLogger(__name__)

_ACTIONABLE_V1 = ("BUY", "STRONG_BUY")
_ENTRY_READY = "ENTRY_READY"
_FILLABLE = ("ENTRY_READY", "WAIT_FOR_PULLBACK", "WAIT_FOR_BREAKOUT")


def _bootstrap_ci(
    returns: List[float],
    n_boot: int = 1000,
    seed: int = 42,
) -> Optional[Dict]:
    if len(returns) < 10:
        return None
    rng = random.Random(seed)
    n = len(returns)
    boot_means = []
    for _ in range(n_boot):
        sample = [returns[rng.randint(0, n - 1)] for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    lo = boot_means[int(0.025 * n_boot)]
    hi = boot_means[int(0.975 * n_boot)]
    return {"lo": round(lo, 4), "hi": round(hi, 4)}


def _stats(rets: List[float]) -> Dict:
    n = len(rets)
    if n == 0:
        return {"count": 0, "mean": None, "median": None, "win_rate": None, "ci_95": None}
    rets_sorted = sorted(rets)
    mean = round(sum(rets) / n, 4)
    mid = n // 2
    median = rets_sorted[mid] if n % 2 else round(
        (rets_sorted[mid - 1] + rets_sorted[mid]) / 2, 4
    )
    win_rate = round(sum(1 for r in rets if r > 0) / n * 100, 2)
    return {
        "count": n, "mean": mean, "median": median,
        "win_rate": win_rate, "ci_95": _bootstrap_ci(rets),
    }


def run_full_backtest(
    research_session,
    prod_session,
    from_date: date,
    to_date: date,
    research_version: str = "v2_research_v2",
    v1_labels: Tuple[str, ...] = _ACTIONABLE_V1,
    expiry_days: int = 10,
) -> Dict:
    """
    Run three-way V1 vs V2 comparison.

    research_session: session on research DB (V2ShadowSignal).
    prod_session: session on production DB (DailyPrice, ForwardSignal).
    Returns a dict with keys: v1_stats, v2_selection_stats, v2_filled_stats,
    v2_fos_stats, fill_rate_pct, avg_waiting_days, trades, notes.
    """
    from src.database import DailyPrice, ForwardSignal
    from src.research.models import V2ShadowSignal

    sim = EntryTimingExecutionSimulator()

    # ── Load V2 shadow signals ────────────────────────────────────────────────
    shadows = (
        research_session.query(V2ShadowSignal)
        .filter(
            V2ShadowSignal.research_version == research_version,
            V2ShadowSignal.trade_date >= from_date,
            V2ShadowSignal.trade_date <= to_date,
            V2ShadowSignal.v1_decision_label.in_(list(v1_labels)),
        )
        .order_by(V2ShadowSignal.trade_date, V2ShadowSignal.stock_id)
        .all()
    )

    if not shadows:
        return _empty_result(f"No v2 signals ({research_version}) found in [{from_date}, {to_date}]")

    stock_ids = list({s.stock_id for s in shadows})

    # ── Load post-signal OHLCV in bulk ────────────────────────────────────────
    ohlcv_cutoff = to_date + timedelta(days=35)  # enough for HOLD_DAYS=20 + buffer
    ohlcv_rows = (
        prod_session.query(DailyPrice)
        .filter(
            DailyPrice.stock_id.in_(stock_ids),
            DailyPrice.date >= from_date,
            DailyPrice.date <= ohlcv_cutoff,
        )
        .order_by(DailyPrice.stock_id, DailyPrice.date)
        .all()
    )
    ohlcv_by_stock: Dict[str, pd.DataFrame] = {}
    for row in ohlcv_rows:
        sid = row.stock_id
        if sid not in ohlcv_by_stock:
            ohlcv_by_stock[sid] = []
        ohlcv_by_stock[sid].append({
            "date": row.date,
            "open": float(row.close),   # SA: use close as open proxy if open not available
            "high": float(row.high) if row.high else float(row.close),
            "low": float(row.low) if row.low else float(row.close),
            "close": float(row.close),
            "volume": int(row.volume) if row.volume else 1,
        })
    ohlcv_df: Dict[str, pd.DataFrame] = {
        sid: pd.DataFrame(rows) for sid, rows in ohlcv_by_stock.items()
    }

    # ── Load V1 returns from ForwardSignal ────────────────────────────────────
    fs_lookup: Dict[Tuple[date, str], float] = {}
    fs_rows = (
        prod_session.query(ForwardSignal)
        .filter(
            ForwardSignal.stock_id.in_(stock_ids),
            ForwardSignal.trade_date >= from_date,
            ForwardSignal.trade_date <= to_date,
            ForwardSignal.decision_label.in_(list(v1_labels)),
            ForwardSignal.fwd_return_20d.isnot(None),
        )
        .all()
    )
    for fs in fs_rows:
        fs_lookup[(fs.trade_date, fs.stock_id)] = float(fs.fwd_return_20d)

    # ── Run simulation ────────────────────────────────────────────────────────
    v1_rets: List[float] = []
    v2_selection_rets: List[float] = []  # ENTRY_READY, using V1 returns (Comparison A)
    v2_filled_rets: List[float] = []     # simulated returns, filled only (Comparison B)
    v2_fos_rets: List[float] = []        # filled simulated + 0% for no-fill (Comparison C)

    wait_days_list: List[float] = []
    trades: List[SimulatedTrade] = []
    missing_ohlcv: int = 0
    missing_v1_ret: int = 0

    for shadow in shadows:
        v1_ret = fs_lookup.get((shadow.trade_date, shadow.stock_id))
        if v1_ret is None:
            missing_v1_ret += 1
            continue

        v1_rets.append(v1_ret)

        # Comparison A: signal selection
        if shadow.entry_label == _ENTRY_READY:
            v2_selection_rets.append(v1_ret)

        # Get OHLCV for this stock
        stock_ohlcv = ohlcv_df.get(shadow.stock_id, pd.DataFrame())
        if stock_ohlcv.empty:
            missing_ohlcv += 1
            # For FOS: no fill → 0%
            if shadow.entry_label in _FILLABLE:
                v2_fos_rets.append(0.0)
            continue

        # Simulate V2
        if shadow.entry_label in _FILLABLE:
            if shadow.stop_price and shadow.target_price:
                trade = sim.simulate_v2(
                    signal_date=shadow.trade_date,
                    stock_id=shadow.stock_id,
                    entry_label=shadow.entry_label,
                    planned_entry=shadow.entry_price or shadow.prior_20d_high or 100.0,
                    stop_price=float(shadow.stop_price),
                    target_price=float(shadow.target_price),
                    ohlcv=stock_ohlcv,
                    prior_20d_high=(
                        float(shadow.prior_20d_high) if shadow.prior_20d_high else None
                    ),
                    v1_decision_label=shadow.v1_decision_label,
                    expiry_days=expiry_days,
                )
                trades.append(trade)

                if trade.filled and trade.net_return_pct is not None:
                    v2_filled_rets.append(trade.net_return_pct)
                    v2_fos_rets.append(trade.net_return_pct)
                    wait_days_list.append(float(trade.waiting_days))
                else:
                    v2_fos_rets.append(0.0)  # SA-7: no fill → 0%
            else:
                v2_fos_rets.append(0.0)
        # Non-fillable labels (TOO_EXTENDED etc.) → no entry in FOS (not counted)

    # ── Compute opportunity cost ──────────────────────────────────────────────
    # Per-signal: V2_FOS_ret - V1_ret, for signals that appear in both
    # (approximation: compare means)
    opportunity_cost = None
    if v2_fos_rets and v1_rets:
        opp_cost_per_signal = (sum(v2_fos_rets) / len(v2_fos_rets)) - (sum(v1_rets) / len(v1_rets))
        opportunity_cost = round(opp_cost_per_signal, 4)

    return {
        "research_version": research_version,
        "date_range": f"{from_date} to {to_date}",
        "v1_eligible_count": len(v1_rets),
        "v2_fillable_count": sum(1 for s in shadows if s.entry_label in _FILLABLE),
        "v2_filled_count": len(v2_filled_rets),
        "v2_no_fill_count": len(v2_fos_rets) - len(v2_filled_rets),
        "fill_rate_pct": (
            round(len(v2_filled_rets) / max(len(v2_fos_rets), 1) * 100, 2)
            if v2_fos_rets else None
        ),
        "avg_waiting_days": (
            round(sum(wait_days_list) / len(wait_days_list), 1)
            if wait_days_list else None
        ),
        # Comparison A
        "v1_stats": _stats(v1_rets),
        "v2_selection_stats": _stats(v2_selection_rets),
        # Comparison B
        "v2_filled_stats": _stats(v2_filled_rets),
        # Comparison C (main)
        "v2_fos_stats": _stats(v2_fos_rets),
        "opportunity_cost_vs_v1_mean": opportunity_cost,
        # Detail
        "trades": trades,
        "missing_ohlcv_count": missing_ohlcv,
        "missing_v1_ret_count": missing_v1_ret,
        "notes": [
            "RESEARCH ONLY — NOT A LIVE BUY SIGNAL",
            "Comparison C (Full Opportunity Set) is the primary V1 vs V2 metric.",
            "SA-7: V2 no-fill signals assigned 0% return in Comparison C.",
            "SA: V1 returns use ForwardSignal.fwd_return_20d (not OHLC simulation).",
            "SA: open prices use daily close as proxy (open column not stored in DailyPrice).",
        ],
    }


def _empty_result(reason: str) -> Dict:
    return {
        "v1_eligible_count": 0, "v2_fillable_count": 0,
        "v2_filled_count": 0, "v2_no_fill_count": 0,
        "fill_rate_pct": None, "avg_waiting_days": None,
        "v1_stats": _stats([]), "v2_selection_stats": _stats([]),
        "v2_filled_stats": _stats([]), "v2_fos_stats": _stats([]),
        "opportunity_cost_vs_v1_mean": None,
        "trades": [], "missing_ohlcv_count": 0, "missing_v1_ret_count": 0,
        "notes": [
            "RESEARCH ONLY — NOT A LIVE BUY SIGNAL",
            reason,
        ],
    }
