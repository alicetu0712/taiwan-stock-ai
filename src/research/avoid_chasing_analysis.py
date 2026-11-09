"""
PART E: AVOID_CHASING / NO_ENTRY subgroup analysis.

Descriptive stats for V3-rejected signals and counterfactual analysis.
Causal inference is IMPOSSIBLE without randomized assignment; we document
the limitation explicitly.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum


class CausalVerdict(str, Enum):
    CAUSAL_EFFECT_UNIDENTIFIABLE = "CAUSAL_EFFECT_UNIDENTIFIABLE"
    DESCRIPTIVE_ASSOCIATION_ONLY = "DESCRIPTIVE_ASSOCIATION_ONLY"
    QUANTIFIED_ASSOCIATION = "QUANTIFIED_ASSOCIATION"


@dataclass(frozen=True)
class SubgroupStats:
    v3_decision: str
    n_signals: int
    mean_net_alpha_vs_a_direct: float   # D_v3 net - A_direct net (paired, correct metric)
    mean_net_alpha_vs_benchmark: float  # D_v3 net - 0050 net (what S40 doc reported)
    median_net_alpha: float
    mean_a_direct_return: float         # what A_direct got for these signals
    mean_v3_return: float               # 0.0 for AVOID_CHASING / NO_ENTRY (no fill)
    std_a_direct_return: float
    n_a_direct_negative: int            # how many had negative A_direct return
    pct_a_direct_negative: float
    s40_doc_note: str                   # clarify S40 mislabel if applicable


@dataclass(frozen=True)
class AvoidChasingReport:
    session: int
    subgroups: tuple[SubgroupStats, ...]
    total_avoided: int                  # AVOID_CHASING + NO_ENTRY combined
    total_signals: int
    avoidance_rate: float
    combined_mean_alpha: float
    causal_verdict: CausalVerdict
    confounding_factors: tuple[str, ...]
    counterfactual_note: str


def build_avoid_chasing_report(conn: sqlite3.Connection) -> AvoidChasingReport:
    from research.v3_comparison_engine import V3ComparisonEngine
    import numpy as np

    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=5)


    # Build lookup for A_direct and D_v3 returns per signal
    a_direct: dict[tuple, float] = {}
    a_direct_bench: dict[tuple, float] = {}  # benchmark (0050) return
    d_v3_rows: dict[tuple, object] = {}

    for row in result.rows:
        key = (row.stock_id, row.signal_date)
        if row.strategy == "A_direct":
            a_direct[key] = row.net_return
            a_direct_bench[key] = row.benchmark_return
        elif row.strategy == "D_v3":
            d_v3_rows[key] = row

    # Group by V3 decision
    # Each entry: (d_v3_net, a_direct_net, benchmark_return)
    by_decision: dict[str, list[tuple[float, float, float]]] = defaultdict(list)

    for key, v3row in d_v3_rows.items():
        if key not in a_direct:
            continue
        a_ret = a_direct[key]
        bench_ret = a_direct_bench.get(key, 0.0)
        v3_ret = v3row.net_return
        decision = v3row.v3_decision or "UNKNOWN"
        by_decision[decision].append((v3_ret, a_ret, bench_ret))

    # S40 doc mislabeled DIRECT_ENTRY alpha as "vs A_direct" when it was "vs 0050"
    s40_mislabel_note = {
        "DIRECT_ENTRY": (
            "S40 doc claimed +2.86% 'vs A_direct' — INCORRECT. "
            "Engine's mean_net_alpha=+2.86% is vs 0050 benchmark. "
            "Correct paired alpha vs A_direct = -0.56%."
        ),
    }

    subgroups = []
    for decision in sorted(by_decision.keys()):
        pairs = by_decision[decision]
        v3_rets = [p[0] for p in pairs]
        a_rets = [p[1] for p in pairs]
        bench_rets = [p[2] for p in pairs]
        alphas_vs_adirect = [v - a for v, a in zip(v3_rets, a_rets)]
        alphas_vs_bench = [v - b for v, b in zip(v3_rets, bench_rets)]

        n = len(pairs)
        n_neg = sum(1 for a in a_rets if a < 0)
        subgroups.append(SubgroupStats(
            v3_decision=decision,
            n_signals=n,
            mean_net_alpha_vs_a_direct=float(np.mean(alphas_vs_adirect)),
            mean_net_alpha_vs_benchmark=float(np.mean(alphas_vs_bench)),
            median_net_alpha=float(np.median(alphas_vs_adirect)),
            mean_a_direct_return=float(np.mean(a_rets)),
            mean_v3_return=float(np.mean(v3_rets)),
            std_a_direct_return=float(np.std(a_rets, ddof=1)) if n > 1 else 0.0,
            n_a_direct_negative=n_neg,
            pct_a_direct_negative=n_neg / n if n > 0 else 0.0,
            s40_doc_note=s40_mislabel_note.get(decision, ""),
        ))

    # Combined stats for avoided signals (AVOID_CHASING + NO_ENTRY)
    avoided_decisions = {"AVOID_CHASING", "NO_ENTRY"}
    avoided_pairs = [
        p for decision, pairs in by_decision.items()
        if decision in avoided_decisions
        for p in pairs
    ]
    total_avoided = len(avoided_pairs)
    total_signals = sum(len(p) for p in by_decision.values())
    avoidance_rate = total_avoided / total_signals if total_signals > 0 else 0.0

    if avoided_pairs:
        avoided_alphas = [v - a for v, a, _b in avoided_pairs]
        combined_mean = float(np.mean(avoided_alphas))
    else:
        combined_mean = 0.0

    confounding = (
        "Market decline confounds avoidance quality: avoided stocks decline during market fall",
        "No randomized control: we cannot know if V3 would have avoided same stocks in a bull market",
        "Same foe_v1 scoring engine: V3 and A_direct use identical signal scores",
        "7 dates, single regime: avoidance quality may not generalise outside declining markets",
        "Selection bias: V3 avoids based on entry rules, not expected return prediction",
    )

    counterfactual_note = (
        "The counterfactual 'what if V3 had entered these avoided signals' is NOT observable. "
        "A_direct returns for AVOID_CHASING and NO_ENTRY signals show what DID happen when "
        "entering unconditionally. These are descriptive, not causal estimates of V3's avoidance skill."
    )

    return AvoidChasingReport(
        session=41,
        subgroups=tuple(subgroups),
        total_avoided=total_avoided,
        total_signals=total_signals,
        avoidance_rate=avoidance_rate,
        combined_mean_alpha=combined_mean,
        causal_verdict=CausalVerdict.DESCRIPTIVE_ASSOCIATION_ONLY,
        confounding_factors=confounding,
        counterfactual_note=counterfactual_note,
    )
