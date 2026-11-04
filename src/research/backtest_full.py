"""
backtest_full.py — V1 vs V2 three-way fair backtest (Part D).

RESEARCH ONLY — NOT A LIVE TRADING SYSTEM.

Comparison definitions:
  A) Signal Selection: V2 ENTRY_READY vs V1 all BUY/STRONG_BUY using
     the SAME fwd_return_20d data.  Shows signal quality only.
  B) Filled Trades: V2 filled simulated trades vs V1 OHLC-simulated.
     WARNING: selection bias — only V2 trades that filled are included.
  C) Full Opportunity Set (main):
     Both V1 and V2 use OHLC simulation.
     V2 filled → simulated net return.
     V2 no-fill → 0% (SA-7).
     V1 → simulated net return (DIRECT_NEXT_OPEN, same stop/target as V2).

V1 Baseline notes:
  - V1 uses stop_price / target_price from V2ShadowSignal (same MA20-based
    parameters available on signal_date).  Disclosed in result notes.
  - Sensitivity analysis: V1_hold variant uses no stop/target (hold-only).
  - V1 and V2 share the same OHLC data source, fees, hold horizon, exit rules.
  - The ONLY difference is entry timing:
      V1 → D+1 OPEN unconditionally (DIRECT_NEXT_OPEN)
      V2 → waits for entry condition (CONFIRMED_NEXT_OPEN) or skips entirely

Performance metrics:
  performance_delta      = mean(v2_ret - v1_ret) per paired signal
                           (V2_FOS_mean - V1_FOS_mean as independent-sample check)
  missed_opportunity     = breakdown of no-fill V2 signals:
    signed_missed_return   = mean(v1_ret for no-fill signals)  [+/-]
    positive_missed_upside = mean(v1_ret for no-fill where v1_ret > 0)
    avoided_loss           = mean(v1_ret for no-fill where v1_ret < 0)

Dedup rule: for the same stock_id, only the FIRST signal within any
28-calendar-day window is kept (approximates 20-trading-day overlap).
"""

from __future__ import annotations

import logging
import random
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.research.execution_simulator import (
    STOP_BUFFER,
    EntryTimingExecutionSimulator,
    SimulatedTrade,
    _WAIT_PULLBACK_LABEL,
)

logger = logging.getLogger(__name__)

_ACTIONABLE_V1 = ("BUY", "STRONG_BUY")
_ENTRY_READY = "ENTRY_READY"
_FILLABLE = ("ENTRY_READY", "WAIT_FOR_PULLBACK", "WAIT_FOR_BREAKOUT")

# Dedup window in calendar days (≈ 20 trading days)
_DEDUP_WINDOW_DAYS = 28


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


def _planned_pullback_entry(shadow) -> float:
    """
    For WAIT_FOR_PULLBACK: return MA20_estimate (the actual pullback target),
    not the signal-day close (which is above MA20 and thus incorrect).

    For all other labels: return entry_price (signal-day close proxy).

    MA20_estimate = stop_price / (1 - STOP_BUFFER)
    """
    if shadow.entry_label == _WAIT_PULLBACK_LABEL and shadow.stop_price:
        return float(shadow.stop_price) / (1.0 - STOP_BUFFER)
    return float(shadow.entry_price) if shadow.entry_price else 100.0


def _dedup_signals(shadows: list, window_days: int = _DEDUP_WINDOW_DAYS) -> list:
    """
    Keep only the first V2 signal per stock within any window_days window.
    Prevents sample inflation from overlapping hold periods on the same stock.
    Sorts by trade_date ascending before filtering.
    """
    seen: Dict[str, date] = {}
    result = []
    for s in sorted(shadows, key=lambda x: x.trade_date):
        last = seen.get(s.stock_id)
        if last is None or (s.trade_date - last).days > window_days:
            result.append(s)
            seen[s.stock_id] = s.trade_date
    return result


def run_full_backtest(
    research_session,
    prod_session,
    from_date: date,
    to_date: date,
    research_version: str = "v2_research_v2",
    v1_labels: Tuple[str, ...] = _ACTIONABLE_V1,
    expiry_days: int = 10,
    dedup: bool = True,
) -> Dict:
    """
    Run three-way V1 vs V2 comparison.

    Parameters
    ----------
    research_session : SQLAlchemy Session on research DB (V2ShadowSignal)
    prod_session     : SQLAlchemy Session on production DB (DailyPrice, ForwardSignal)
    dedup            : Apply 28-calendar-day dedup per stock (recommended True)

    Returns dict with keys documented at module top.
    """
    from src.database import DailyPrice, ForwardSignal
    from src.research.models import V2ShadowSignal

    sim = EntryTimingExecutionSimulator()

    # ── Load V2 shadow signals ────────────────────────────────────────────────
    shadows_raw = (
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

    if not shadows_raw:
        return _empty_result(
            f"No v2 signals ({research_version}) found in [{from_date}, {to_date}]"
        )

    shadows = _dedup_signals(shadows_raw, _DEDUP_WINDOW_DAYS) if dedup else shadows_raw
    dedup_removed = len(shadows_raw) - len(shadows)

    stock_ids = list({s.stock_id for s in shadows})

    # ── Load post-signal OHLCV in bulk ────────────────────────────────────────
    ohlcv_cutoff = to_date + timedelta(days=35)
    ohlcv_rows = (
        prod_session.query(DailyPrice)
        .filter(
            DailyPrice.stock_id.in_(stock_ids),
            DailyPrice.date >= from_date - timedelta(days=1),
            DailyPrice.date <= ohlcv_cutoff,
        )
        .order_by(DailyPrice.stock_id, DailyPrice.date)
        .all()
    )
    ohlcv_by_stock: Dict[str, list] = {}
    for row in ohlcv_rows:
        sid = row.stock_id
        if sid not in ohlcv_by_stock:
            ohlcv_by_stock[sid] = []
        ohlcv_by_stock[sid].append({
            "date": row.date,
            # DailyPrice has no separate open column → use close as OPEN proxy
            # SA note: open prices are approximated by daily close
            "open": float(row.close),
            "high": float(row.high) if row.high else float(row.close),
            "low": float(row.low) if row.low else float(row.close),
            "close": float(row.close),
            "volume": int(row.volume) if row.volume else 1,
        })
    ohlcv_df: Dict[str, pd.DataFrame] = {
        sid: pd.DataFrame(rows) for sid, rows in ohlcv_by_stock.items()
    }

    # ── Load V1 ForwardSignal fwd_return_20d (Comparison A reference only) ───
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

    # ── Main simulation loop ──────────────────────────────────────────────────
    # V1 FOS: each signal → OHLC simulated (DIRECT_NEXT_OPEN, same stop/target)
    # V2 FOS: filled → simulated net return; no-fill → 0% (SA-7)

    v1_fos_rets: List[float] = []        # V1 OHLC returns (Comparison C primary)
    v1_fwd_rets: List[float] = []        # V1 ForwardSignal.fwd_return_20d (reference)
    v2_selection_rets: List[float] = []  # V2 ENTRY_READY using V1 fwd (Comparison A)
    v2_filled_rets: List[float] = []     # V2 filled simulated (Comparison B)
    v2_fos_rets: List[float] = []        # V2 FOS: filled + 0% no-fill (Comparison C)
    paired_deltas: List[float] = []      # per-signal: v2_fos_ret - v1_fos_ret

    # Missed opportunity tracking: signals where V2 did NOT fill
    no_fill_v1_rets: List[float] = []

    wait_days_list: List[float] = []
    v1_trades: List[SimulatedTrade] = []
    v2_trades: List[SimulatedTrade] = []
    missing_ohlcv = 0
    missing_v1_ohlcv = 0

    for shadow in shadows:
        if not shadow.stop_price or not shadow.target_price:
            # Cannot simulate without stop/target — skip entirely
            continue

        stop_price = float(shadow.stop_price)
        target_price = float(shadow.target_price)
        stock_ohlcv = ohlcv_df.get(shadow.stock_id, pd.DataFrame())

        # ── V1 OHLC simulation ────────────────────────────────────────────
        if stock_ohlcv.empty:
            missing_ohlcv += 1
            missing_v1_ohlcv += 1
            # Cannot compute V1 → skip paired comparison for this signal
            # Still count in V2 FOS if applicable
            if shadow.entry_label in _FILLABLE:
                v2_fos_rets.append(0.0)
            continue

        v1_trade = sim.simulate_v1(
            signal_date=shadow.trade_date,
            stock_id=shadow.stock_id,
            stop_price=stop_price,
            target_price=target_price,
            ohlcv=stock_ohlcv,
        )
        v1_trades.append(v1_trade)

        v1_ret = v1_trade.net_return_pct if v1_trade.net_return_pct is not None else 0.0
        v1_fos_rets.append(v1_ret)

        # Keep ForwardSignal fwd_return_20d for Comparison A reference
        fwd_ret = fs_lookup.get((shadow.trade_date, shadow.stock_id))
        if fwd_ret is not None:
            v1_fwd_rets.append(fwd_ret)

        # Comparison A: signal selection (ENTRY_READY subset vs V1 using fwd_return_20d)
        if shadow.entry_label == _ENTRY_READY and fwd_ret is not None:
            v2_selection_rets.append(fwd_ret)

        # ── V2 simulation ─────────────────────────────────────────────────
        if shadow.entry_label in _FILLABLE:
            # SA-1 fix: for WAIT_FOR_PULLBACK, use MA20_estimate as planned_entry
            planned_entry = _planned_pullback_entry(shadow)

            v2_trade = sim.simulate_v2(
                signal_date=shadow.trade_date,
                stock_id=shadow.stock_id,
                entry_label=shadow.entry_label,
                planned_entry=planned_entry,
                stop_price=stop_price,
                target_price=target_price,
                ohlcv=stock_ohlcv,
                prior_20d_high=(
                    float(shadow.prior_20d_high) if shadow.prior_20d_high else None
                ),
                v1_decision_label=shadow.v1_decision_label,
                expiry_days=expiry_days,
            )
            v2_trades.append(v2_trade)

            if v2_trade.filled and v2_trade.net_return_pct is not None:
                v2_ret = v2_trade.net_return_pct
                v2_filled_rets.append(v2_ret)
                v2_fos_rets.append(v2_ret)
                wait_days_list.append(float(v2_trade.waiting_days))
            else:
                v2_ret = 0.0  # SA-7
                v2_fos_rets.append(0.0)
                no_fill_v1_rets.append(v1_ret)

            paired_deltas.append(v2_ret - v1_ret)

        # Non-fillable labels (TOO_EXTENDED etc.) → not counted in FOS

    # ── Compute Performance Delta & Missed Opportunity ────────────────────────
    performance_delta: Optional[float] = None
    if paired_deltas:
        performance_delta = round(sum(paired_deltas) / len(paired_deltas), 4)

    # V2_FOS_mean - V1_FOS_mean (independent-sample check; use paired_delta as primary)
    v2_fos_mean = (sum(v2_fos_rets) / len(v2_fos_rets)) if v2_fos_rets else None
    v1_fos_mean = (sum(v1_fos_rets) / len(v1_fos_rets)) if v1_fos_rets else None
    independent_delta = (
        round(v2_fos_mean - v1_fos_mean, 4)
        if v2_fos_mean is not None and v1_fos_mean is not None
        else None
    )

    # Missed Opportunity breakdown (for V2 no-fill signals only)
    pos_missed = [r for r in no_fill_v1_rets if r > 0]
    neg_missed = [r for r in no_fill_v1_rets if r < 0]
    missed_opportunity = {
        "n_no_fill": len(no_fill_v1_rets),
        "signed_missed_return": (
            round(sum(no_fill_v1_rets) / len(no_fill_v1_rets), 4)
            if no_fill_v1_rets else None
        ),
        "positive_missed_upside": (
            round(sum(pos_missed) / len(pos_missed), 4) if pos_missed else None
        ),
        "avoided_loss": (
            round(sum(neg_missed) / len(neg_missed), 4) if neg_missed else None
        ),
        "n_positive_missed": len(pos_missed),
        "n_avoided_negative": len(neg_missed),
        "note": (
            "signed_missed_return: mean V1 return for V2 no-fill signals (+/-);"
            " positive_missed_upside: mean V1 return where V1>0 (upside missed);"
            " avoided_loss: mean V1 return where V1<0 (loss avoided by not filling)"
        ),
    }

    return {
        "research_version": research_version,
        "date_range": f"{from_date} to {to_date}",
        "dedup_rule": f"first signal per stock within {_DEDUP_WINDOW_DAYS}d window",
        "dedup_removed": dedup_removed,
        # Counts
        "v1_eligible_count": len(v1_fos_rets),
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
        # Comparison A: signal selection (ENTRY_READY vs V1 using fwd_return_20d)
        "v1_fwd_stats": _stats(v1_fwd_rets),   # V1 ForwardSignal reference
        "v2_selection_stats": _stats(v2_selection_rets),
        # Comparison B: filled trades only (selection bias)
        "v2_filled_stats": _stats(v2_filled_rets),
        # Comparison C: Full Opportunity Set (primary)
        "v1_fos_stats": _stats(v1_fos_rets),   # V1 OHLC simulated (all)
        "v2_fos_stats": _stats(v2_fos_rets),   # V2 filled + 0% no-fill
        # Performance metrics
        "performance_delta": performance_delta,       # paired mean(v2-v1)
        "independent_delta": independent_delta,       # V2_FOS_mean - V1_FOS_mean
        "missed_opportunity": missed_opportunity,
        "paired_delta_stats": _stats(paired_deltas),
        # Trades detail
        "v1_trades": v1_trades,
        "v2_trades": v2_trades,
        "missing_ohlcv_count": missing_ohlcv,
        "notes": [
            "RESEARCH ONLY — NOT A LIVE BUY SIGNAL",
            "Comparison C (Full Opportunity Set) is the primary V1 vs V2 metric.",
            "V1 and V2 use the same OHLC data, stop/target, fees (SA-6), and hold period (SA-5).",
            "V1 stop/target sourced from V2ShadowSignal (MA20-based, same signal_date info).",
            "SA-1 fix: WAIT_FOR_PULLBACK planned_entry = MA20_est = stop/(1-0.03).",
            "SA-7: V2 no-fill → 0% in FOS; same V1 return counted in missed_opportunity.",
            "SA: open prices approximated by daily close (DailyPrice has no separate open).",
            f"Dedup: removed {dedup_removed} duplicate signals within {_DEDUP_WINDOW_DAYS}d windows.",
        ],
    }


def _empty_result(reason: str) -> Dict:
    empty = _stats([])
    return {
        "v1_eligible_count": 0, "v2_fillable_count": 0,
        "v2_filled_count": 0, "v2_no_fill_count": 0,
        "fill_rate_pct": None, "avg_waiting_days": None,
        "dedup_rule": "", "dedup_removed": 0,
        "v1_fwd_stats": empty,
        "v2_selection_stats": empty,
        "v2_filled_stats": empty,
        "v1_fos_stats": empty,
        "v2_fos_stats": empty,
        "performance_delta": None,
        "independent_delta": None,
        "missed_opportunity": {
            "n_no_fill": 0, "signed_missed_return": None,
            "positive_missed_upside": None, "avoided_loss": None,
            "n_positive_missed": 0, "n_avoided_negative": 0, "note": "",
        },
        "paired_delta_stats": empty,
        "v1_trades": [], "v2_trades": [],
        "missing_ohlcv_count": 0,
        "notes": [
            "RESEARCH ONLY — NOT A LIVE BUY SIGNAL",
            reason,
        ],
    }
