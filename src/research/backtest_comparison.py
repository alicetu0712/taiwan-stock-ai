"""
backtest_comparison.py — Compare V1 (v8.0 decision) vs V2 (Entry Timing) on
historical ForwardSignal outcomes.

V1: selects stocks based on BUY / STRONG_BUY decision_label.
V2: filters V1 candidates by ENTRY_READY label.

This module reads ONLY — never writes to ForwardSignal.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def compare_v1_v2(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_outcome_bars: int = 20,
) -> Dict[str, Any]:
    """
    Pull V2ShadowSignals that have matching ForwardSignal outcomes,
    then compare V1-only vs V2-filtered return distributions.

    Returns a dict with keys:
      v1_count, v2_count,
      v1_mean_return_20d, v2_mean_return_20d,
      v1_win_rate_20d, v2_win_rate_20d,
      v1_median_return_20d, v2_median_return_20d,
      rows (list of dicts for tabular display)
    """
    from src.database import ForwardSignal, get_session
    from src.research.models import V2ShadowSignal

    session = get_session()
    try:
        q = session.query(V2ShadowSignal, ForwardSignal).join(
            ForwardSignal,
            (ForwardSignal.trade_date == V2ShadowSignal.trade_date)
            & (ForwardSignal.stock_id == V2ShadowSignal.stock_id),
        )
        if start_date:
            q = q.filter(V2ShadowSignal.trade_date >= start_date)
        if end_date:
            q = q.filter(V2ShadowSignal.trade_date <= end_date)

        pairs = q.all()
    finally:
        session.close()

    v1_rows = []
    v2_rows = []
    all_rows = []

    for shadow, fs in pairs:
        # Only include rows with 20d outcome available
        if fs.fwd_return_20d is None:
            continue

        row = {
            "trade_date": shadow.trade_date,
            "stock_id": shadow.stock_id,
            "v1_label": shadow.v1_decision_label,
            "v2_label": shadow.entry_label,
            "v1_pt_score": shadow.v1_pt_score,
            "rr_ratio": shadow.rr_ratio,
            "fwd_return_20d": fs.fwd_return_20d,
            "fwd_return_60d": fs.fwd_return_60d,
        }
        all_rows.append(row)
        v1_rows.append(fs.fwd_return_20d)
        if shadow.entry_label == "ENTRY_READY":
            v2_rows.append(fs.fwd_return_20d)

    def _stats(returns: List[float]) -> Dict[str, Any]:
        if not returns:
            return {"count": 0, "mean": None, "median": None, "win_rate": None}
        import statistics

        wins = sum(1 for r in returns if r > 0)
        return {
            "count": len(returns),
            "mean": round(statistics.mean(returns), 2),
            "median": round(statistics.median(returns), 2),
            "win_rate": round(wins / len(returns) * 100, 1),
        }

    v1_stats = _stats(v1_rows)
    v2_stats = _stats(v2_rows)

    return {
        "v1_count": v1_stats["count"],
        "v2_count": v2_stats["count"],
        "v1_mean_return_20d": v1_stats["mean"],
        "v2_mean_return_20d": v2_stats["mean"],
        "v1_win_rate_20d": v1_stats["win_rate"],
        "v2_win_rate_20d": v2_stats["win_rate"],
        "v1_median_return_20d": v1_stats["median"],
        "v2_median_return_20d": v2_stats["median"],
        "rows": all_rows,
    }
