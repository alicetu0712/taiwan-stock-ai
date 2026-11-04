"""
backtest_comparison.py — Compare V1 (v8.0 decision) vs V2 (Entry Timing) on
historical ForwardSignal outcomes.

V1 baseline: BUY / STRONG_BUY ForwardSignals that also have a V2ShadowSignal.
V2 filtered : V1 candidates where entry_label == ENTRY_READY.

Methodology notes (read before interpreting results):
  1. RETURN SOURCE LIMITATION: Both V1 and V2 rows use `ForwardSignal.fwd_return_20d`
     (the return at V1 execution price / NEXT_OPEN timing). V2 may trade at a
     different intraday entry — simulated V2 entry returns are NOT AVAILABLE.
     This means V2 improvement estimates are conservative lower bounds.
  2. UNIVERSE BIAS: Only stocks with a matching V2ShadowSignal are included.
     V1 BUY signals without shadow coverage are excluded from both groups.
  3. OPPORTUNITY COST: `v2_missed` captures V1 BUY signals that V2 rejected
     (ENTRY_READY = 0).  Their returns estimate the cost of V2's selectivity.

This module reads ONLY — never writes to ForwardSignal or any production table.
"""

from __future__ import annotations

import logging
import random
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_V1_ACTIONABLE = ("BUY", "STRONG_BUY")
_N_BOOTSTRAP = 1000


def compare_v1_v2(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_outcome_bars: int = 20,
) -> Dict[str, Any]:
    """
    Pull V2ShadowSignals whose matching ForwardSignal has a 20-day outcome,
    then compare V1-only vs V2-filtered return distributions.

    Returns a dict with keys:
      v1_count, v2_count, v2_missed_count,
      v1_mean_return_20d, v2_mean_return_20d, v2_missed_mean_return_20d,
      v1_win_rate_20d, v2_win_rate_20d,
      v1_median_return_20d, v2_median_return_20d,
      v1_ci_95, v2_ci_95,
      fill_rate_pct,
      return_source_note,
      rows (list of dicts for tabular display)
    """
    from src.database import ForwardSignal, get_session
    from src.research.models import V2ShadowSignal

    session = get_session()
    try:
        q = (
            session.query(V2ShadowSignal, ForwardSignal)
            .join(
                ForwardSignal,
                (ForwardSignal.trade_date == V2ShadowSignal.trade_date)
                & (ForwardSignal.stock_id == V2ShadowSignal.stock_id),
            )
            .filter(
                # V1 baseline = actionable BUY / STRONG_BUY only
                V2ShadowSignal.v1_decision_label.in_(_V1_ACTIONABLE)
            )
        )
        if start_date:
            q = q.filter(V2ShadowSignal.trade_date >= start_date)
        if end_date:
            q = q.filter(V2ShadowSignal.trade_date <= end_date)

        pairs = q.all()
    finally:
        session.close()

    v1_rows: List[float] = []       # all V1 BUY+STRONG_BUY with outcome
    v2_rows: List[float] = []       # V2 ENTRY_READY subset
    v2_missed_rows: List[float] = []  # V1 signals V2 rejected
    all_rows: List[Dict[str, Any]] = []

    for shadow, fs in pairs:
        if fs.fwd_return_20d is None:
            continue

        is_entry_ready = shadow.entry_label == "ENTRY_READY"
        row: Dict[str, Any] = {
            "trade_date": shadow.trade_date,
            "stock_id": shadow.stock_id,
            "v1_label": shadow.v1_decision_label,
            "v2_label": shadow.entry_label,
            "v1_pt_score": shadow.v1_pt_score,
            "rr_ratio": shadow.rr_ratio,
            "fwd_return_20d": fs.fwd_return_20d,
            "fwd_return_60d": fs.fwd_return_60d,
            "v2_selected": is_entry_ready,
        }
        all_rows.append(row)
        v1_rows.append(fs.fwd_return_20d)
        if is_entry_ready:
            v2_rows.append(fs.fwd_return_20d)
        else:
            v2_missed_rows.append(fs.fwd_return_20d)

    v1_stats = _stats(v1_rows)
    v2_stats = _stats(v2_rows)
    v2_missed_stats = _stats(v2_missed_rows)

    fill_rate = (
        round(len(v2_rows) / len(v1_rows) * 100, 1) if v1_rows else None
    )

    return {
        "v1_count": v1_stats["count"],
        "v2_count": v2_stats["count"],
        "v2_missed_count": v2_missed_stats["count"],
        "v1_mean_return_20d": v1_stats["mean"],
        "v2_mean_return_20d": v2_stats["mean"],
        "v2_missed_mean_return_20d": v2_missed_stats["mean"],
        "v1_win_rate_20d": v1_stats["win_rate"],
        "v2_win_rate_20d": v2_stats["win_rate"],
        "v1_median_return_20d": v1_stats["median"],
        "v2_median_return_20d": v2_stats["median"],
        "v1_ci_95": v1_stats["ci_95"],
        "v2_ci_95": v2_stats["ci_95"],
        "fill_rate_pct": fill_rate,
        "return_source_note": (
            "V2 returns use V1 execution price (NEXT_OPEN). "
            "Simulated V2 entry-price returns are NOT AVAILABLE."
        ),
        "rows": all_rows,
    }


def _stats(returns: List[float]) -> Dict[str, Any]:
    if not returns:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "win_rate": None,
            "ci_95": None,
        }
    import statistics

    n = len(returns)
    wins = sum(1 for r in returns if r > 0)
    ci_95 = _bootstrap_ci(returns, n_boot=_N_BOOTSTRAP) if n >= 10 else None
    return {
        "count": n,
        "mean": round(statistics.mean(returns), 4),
        "median": round(statistics.median(returns), 4),
        "win_rate": round(wins / n * 100, 1),
        "ci_95": ci_95,
    }


def _bootstrap_ci(
    returns: List[float], n_boot: int = 1000, confidence: float = 0.95
) -> Dict[str, float]:
    """Percentile bootstrap CI on mean return."""
    rng = random.Random(42)
    n = len(returns)
    boot_means = []
    for _ in range(n_boot):
        sample = [returns[rng.randrange(n)] for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    lo = boot_means[int(n_boot * (1 - confidence) / 2)]
    hi = boot_means[int(n_boot * (1 - (1 - confidence) / 2)) - 1]
    return {"lo": round(lo, 4), "hi": round(hi, 4)}
