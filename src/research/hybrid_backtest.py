"""
hybrid_backtest.py — Three-Strategy Comparison (V1 / V2 / Hybrid)

RESEARCH ONLY — NOT A LIVE TRADING SYSTEM.
RETROSPECTIVE / EXPLORATORY ONLY — IN-SAMPLE FOR HYBRID RULES.

The Hybrid V1 rules were DERIVED from the same 2024-10 to 2026-09 research
cohort used here.  Therefore all Hybrid results in this module are:

  ⚠️  IN-SAMPLE / RETROSPECTIVE — not an independent validation.

True OOS for Hybrid = forward shadow only, starting from rule freeze
date 2026-11-05.  Results here cannot be used to claim Hybrid outperforms.

Pure-function module: accepts pre-enriched EnrichedSignal lists (from
run_effectiveness_analysis.py), applies HybridDecisionService, and returns
structured comparison dicts.  No I/O.

FORBIDDEN: Do NOT modify MODEL_VERSION, BUY/STRONG_BUY thresholds,
           ForwardSignals, ACTUAL/PAPER positions, or Phase 1B migration.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from src.research.effectiveness_analyzer import EnrichedSignal
from src.research.hybrid_entry_strategy import (
    HybridAction,
    HybridDecisionService,
    HybridStrategyConfig,
    RULE_VERSION,
)

# ── Constants ─────────────────────────────────────────────────────────────────

BOOTSTRAP_N = 1000
BOOTSTRAP_SEED = 42
MIN_GROUP_N = 10
IN_SAMPLE_WARNING = (
    "⚠️  RETROSPECTIVE/EXPLORATORY ONLY — IN-SAMPLE FOR HYBRID RULES. "
    "Hybrid V1 rules were derived from this same dataset. "
    "True OOS = forward shadow only (starting 2026-11-05)."
)


# ── Per-signal result ─────────────────────────────────────────────────────────

@dataclass
class HybridSignalResult:
    """
    One signal annotated with Hybrid decision and three-way returns.

    hybrid_ret = v1_ret if action is DIRECT_NEXT_OPEN (immediate entry like V1)
               = v2_ret if action is WAIT_PULLBACK     (wait like V2, SA-7 applies)
    """
    signal_date: date
    stock_id: str
    entry_label: str
    market_regime: str
    ma20_trend: str
    ma20_slope_pct: float
    ma20_gap_pct: float

    v1_ret: float
    v2_ret: float               # SA-7: 0.0 if V2 no-fill

    hybrid_action: HybridAction
    rule_reason: str
    rule_priority: int

    hybrid_ret: float           # resolved from hybrid_action
    v2_v1_delta: float          # v2_ret - v1_ret
    hybrid_v1_delta: float      # hybrid_ret - v1_ret


# ── Core annotation ───────────────────────────────────────────────────────────

def annotate_hybrid(
    signals: List[EnrichedSignal],
    config: Optional[HybridStrategyConfig] = None,
) -> List[HybridSignalResult]:
    """
    Apply HybridDecisionService to each EnrichedSignal and compute hybrid_ret.

    hybrid_ret mapping:
      DIRECT_NEXT_OPEN → v1_ret   (bypass wait; immediate entry = V1 outcome)
      WAIT_PULLBACK    → v2_ret   (keep the wait; V2 outcome, SA-7 for no-fills)
    """
    svc = HybridDecisionService(config)
    results: List[HybridSignalResult] = []

    for s in signals:
        if s.v1_ret is None or s.v2_ret is None:
            continue
        if not s.is_dedup_kept or not s.is_matured:
            continue

        decision = svc.decide(
            stock_id=s.stock_id,
            signal_date=s.signal_date,
            v2_entry_label=s.entry_label,
            market_regime=s.market_regime,
            ma20_trend=s.ma20_trend,
            ma20_slope_pct=s.ma20_slope_pct,
            ma20_gap_pct=s.ma20_gap_pct,
        )

        v1_ret = s.v1_ret
        v2_ret = s.v2_ret

        if decision.hybrid_action == HybridAction.WAIT_PULLBACK:
            hybrid_ret = v2_ret
        else:
            # DIRECT_NEXT_OPEN (P3 or P4 default) → take V1 outcome
            hybrid_ret = v1_ret

        results.append(HybridSignalResult(
            signal_date=s.signal_date,
            stock_id=s.stock_id,
            entry_label=s.entry_label,
            market_regime=s.market_regime,
            ma20_trend=s.ma20_trend,
            ma20_slope_pct=s.ma20_slope_pct,
            ma20_gap_pct=s.ma20_gap_pct,
            v1_ret=v1_ret,
            v2_ret=v2_ret,
            hybrid_action=decision.hybrid_action,
            rule_reason=decision.rule_reason,
            rule_priority=decision.rule_priority,
            hybrid_ret=hybrid_ret,
            v2_v1_delta=round(v2_ret - v1_ret, 6),
            hybrid_v1_delta=round(hybrid_ret - v1_ret, 6),
        ))

    return results


# ── Bootstrap CI ──────────────────────────────────────────────────────────────

def _bootstrap_ci(
    deltas: List[float],
    n_iter: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
) -> Optional[Dict[str, float]]:
    """Return 95% bootstrap CI on the mean of deltas."""
    n = len(deltas)
    if n < MIN_GROUP_N:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_iter):
        sample = [rng.choice(deltas) for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(0.025 * n_iter)]
    hi = means[int(0.975 * n_iter)]
    return {"lo": round(lo, 4), "hi": round(hi, 4)}


def _ci_verdict(ci: Optional[Dict]) -> str:
    if ci is None:
        return "INSUFFICIENT_SAMPLE"
    if ci["lo"] > 0:
        return "POSITIVE_CI"
    if ci["hi"] < 0:
        return "NEGATIVE_CI"
    return "CI_SPANS_ZERO"


# ── Three-strategy summary stats ──────────────────────────────────────────────

def _strategy_stats(
    returns: List[float],
    name: str,
) -> Dict:
    n = len(returns)
    if n == 0:
        return {"strategy": name, "n": 0}
    mean = round(sum(returns) / n, 4)
    wins = sum(1 for r in returns if r > 0)
    return {
        "strategy": name,
        "n": n,
        "mean_net_ret": mean,
        "win_rate": round(wins / n * 100, 2),
    }


def compute_three_strategy_comparison(
    results: List[HybridSignalResult],
) -> Dict:
    """
    V1 / V2 (FOS) / Hybrid three-way comparison.

    Returns structured dict with per-strategy summary + paired delta stats.
    All labeled IN-SAMPLE for Hybrid.
    """
    if not results:
        return {"error": "empty", "in_sample_warning": IN_SAMPLE_WARNING}

    v1_rets = [r.v1_ret for r in results]
    v2_rets = [r.v2_ret for r in results]
    hybrid_rets = [r.hybrid_ret for r in results]

    v2_v1_deltas = [r.v2_v1_delta for r in results]
    hybrid_v1_deltas = [r.hybrid_v1_delta for r in results]
    hybrid_v2_deltas = [round(r.hybrid_ret - r.v2_ret, 6) for r in results]

    n = len(results)

    # Paired delta stats
    v2_v1_mean = round(sum(v2_v1_deltas) / n, 4)
    hyb_v1_mean = round(sum(hybrid_v1_deltas) / n, 4)
    hyb_v2_mean = round(sum(hybrid_v2_deltas) / n, 4)

    return {
        "in_sample_warning": IN_SAMPLE_WARNING,
        "rule_version": RULE_VERSION,
        "n_signals": n,
        "strategies": {
            "v1": _strategy_stats(v1_rets, "V1"),
            "v2_fos": _strategy_stats(v2_rets, "V2_FOS"),
            "hybrid": _strategy_stats(hybrid_rets, "Hybrid"),
        },
        "paired_deltas": {
            "v2_vs_v1": {
                "mean": v2_v1_mean,
                "ci_95": _bootstrap_ci(v2_v1_deltas),
                "ci_verdict": _ci_verdict(_bootstrap_ci(v2_v1_deltas)),
            },
            "hybrid_vs_v1": {
                "mean": hyb_v1_mean,
                "ci_95": _bootstrap_ci(hybrid_v1_deltas),
                "ci_verdict": _ci_verdict(_bootstrap_ci(hybrid_v1_deltas)),
            },
            "hybrid_vs_v2": {
                "mean": hyb_v2_mean,
                "ci_95": _bootstrap_ci(hybrid_v2_deltas),
                "ci_verdict": _ci_verdict(_bootstrap_ci(hybrid_v2_deltas)),
            },
        },
    }


# ── Action distribution ───────────────────────────────────────────────────────

def compute_action_distribution(results: List[HybridSignalResult]) -> Dict:
    """Break down Hybrid action counts by label × action."""
    if not results:
        return {}

    action_counts: Dict[str, int] = {}
    label_action: Dict[str, Dict[str, int]] = {}
    regime_action: Dict[str, Dict[str, int]] = {}

    for r in results:
        a = r.hybrid_action.value
        action_counts[a] = action_counts.get(a, 0) + 1

        if r.entry_label not in label_action:
            label_action[r.entry_label] = {}
        label_action[r.entry_label][a] = label_action[r.entry_label].get(a, 0) + 1

        if r.market_regime not in regime_action:
            regime_action[r.market_regime] = {}
        regime_action[r.market_regime][a] = regime_action[r.market_regime].get(a, 0) + 1

    return {
        "total": len(results),
        "action_counts": action_counts,
        "by_entry_label": label_action,
        "by_market_regime": regime_action,
    }


# ── Subgroup analysis ─────────────────────────────────────────────────────────

def _group_delta_stats(
    group_results: List[HybridSignalResult],
    delta_key: str,
) -> Dict:
    """Stats for one group, one delta type."""
    if delta_key == "hybrid_v1":
        deltas = [r.hybrid_v1_delta for r in group_results]
    elif delta_key == "v2_v1":
        deltas = [r.v2_v1_delta for r in group_results]
    else:
        return {}

    n = len(deltas)
    if n == 0:
        return {"n": 0}

    mean = round(sum(deltas) / n, 4)
    ci = _bootstrap_ci(deltas)
    return {
        "n": n,
        "mean_delta": mean,
        "ci_95": ci,
        "ci_verdict": _ci_verdict(ci),
    }


def compute_hybrid_subgroup_analysis(results: List[HybridSignalResult]) -> Dict:
    """
    Subgroup performance: Hybrid vs V1 delta broken out by:
      - hybrid_action (WAIT_PULLBACK vs DIRECT_NEXT_OPEN)
      - rule_priority (P1–P4)
      - market_regime
      - ma20_trend
      - entry_label
    """
    if not results:
        return {}

    def group_by(attr: str) -> Dict[str, List[HybridSignalResult]]:
        d: Dict[str, List[HybridSignalResult]] = {}
        for r in results:
            key = str(getattr(r, attr))
            if isinstance(key, str) and hasattr(getattr(r, attr), "value"):
                key = getattr(r, attr).value
            d.setdefault(key, []).append(r)
        return d

    def stats_for_groups(grouped: Dict[str, List[HybridSignalResult]]) -> Dict:
        return {
            k: _group_delta_stats(v, "hybrid_v1")
            for k, v in sorted(grouped.items())
        }

    return {
        "by_hybrid_action": stats_for_groups(group_by("hybrid_action")),
        "by_rule_priority": stats_for_groups(group_by("rule_priority")),
        "by_market_regime": stats_for_groups(group_by("market_regime")),
        "by_ma20_trend": stats_for_groups(group_by("ma20_trend")),
        "by_entry_label": stats_for_groups(group_by("entry_label")),
    }


# ── Top-level analysis runner ─────────────────────────────────────────────────

def run_hybrid_analysis(
    signals: List[EnrichedSignal],
    config: Optional[HybridStrategyConfig] = None,
) -> Dict:
    """
    Full in-sample Hybrid analysis.

    Parameters
    ----------
    signals : list of EnrichedSignal (must have v1_ret, v2_ret set)
    config  : HybridStrategyConfig (defaults to frozen V1 config)

    Returns structured dict suitable for JSON serialisation.

    ⚠️  All results are RETROSPECTIVE/EXPLORATORY ONLY — IN-SAMPLE.
    """
    hybrid_results = annotate_hybrid(signals, config)

    comparison = compute_three_strategy_comparison(hybrid_results)
    action_dist = compute_action_distribution(hybrid_results)
    subgroup = compute_hybrid_subgroup_analysis(hybrid_results)

    # Signals where Hybrid changed the action vs V2
    switched_to_direct = [
        r for r in hybrid_results
        if r.entry_label == "WAIT_FOR_PULLBACK"
        and r.hybrid_action == HybridAction.DIRECT_NEXT_OPEN
    ]
    kept_waiting = [
        r for r in hybrid_results
        if r.entry_label == "WAIT_FOR_PULLBACK"
        and r.hybrid_action == HybridAction.WAIT_PULLBACK
    ]

    switch_summary = {
        "total_wait_for_pullback": len(switched_to_direct) + len(kept_waiting),
        "switched_to_direct": len(switched_to_direct),
        "kept_waiting": len(kept_waiting),
        "switched_to_direct_mean_delta": (
            round(
                sum(r.hybrid_v1_delta for r in switched_to_direct)
                / len(switched_to_direct),
                4,
            )
            if switched_to_direct else None
        ),
        "kept_waiting_mean_delta": (
            round(
                sum(r.hybrid_v1_delta for r in kept_waiting)
                / len(kept_waiting),
                4,
            )
            if kept_waiting else None
        ),
    }

    return {
        "in_sample_warning": IN_SAMPLE_WARNING,
        "rule_version": RULE_VERSION,
        "comparison": comparison,
        "action_distribution": action_dist,
        "subgroup_analysis": subgroup,
        "switch_summary": switch_summary,
    }
