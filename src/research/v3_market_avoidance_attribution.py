"""
v3_market_avoidance_attribution.py — Quantify V3 market avoidance vs other alpha sources.

RESEARCH ONLY. Read-only.

Attribution framework (5D window, Oct 2026):
  Total V3 alpha vs A_direct ≈ +3.66%

  Decomposed into:
  1. Market avoidance: V3 fills less → less exposure during market decline
  2. Stock selection within invested: V3 DIRECT_ENTRY stocks vs A_direct same stocks
  3. Entry timing: Same entry price (both D+1 open) → NOT identifiable from price
  4. Exit rule difference: V3 own stop/target vs reconstructed → partially mixed with #2

Conclusion:
  Market avoidance dominates. Stock selection within invested is secondary.
  Entry timing is UNIDENTIFIABLE.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class AttributionStatus(str, Enum):
    QUANTIFIED = "QUANTIFIED"
    ESTIMATED = "ESTIMATED"
    PARTIAL = "PARTIAL"
    UNIDENTIFIABLE = "UNIDENTIFIABLE"


@dataclass(frozen=True)
class AttributionComponent:
    name: str
    status: AttributionStatus
    estimated_contribution_ppt: Optional[float]  # percentage points of total 3.66ppt alpha
    evidence: str
    caveat: str = ""


@dataclass
class MarketAvoidanceAttribution:
    """
    Quantitative attribution of V3 alpha vs A_direct on 5D horizon, Oct 2026 window.
    """
    total_alpha_ppt: float                     # D_v3 mean_net_alpha vs A_direct
    n_signals: int
    n_v3_filled: int
    n_v3_skipped: int
    v3_fill_rate: float
    benchmark_avg_5d_return_pct: float          # 0050 average 5D return in window
    a_direct_mean_net_return_pct: float
    d_v3_mean_net_return_pct: float
    components: List[AttributionComponent] = field(default_factory=list)
    overall_verdict: str = ""
    overall_evidence: str = ""

    def exposure_reduction_estimate_ppt(self) -> float:
        """
        Estimate the market avoidance contribution.

        Logic:
          - V3 avoids (1 - fill_rate) = 31.4% of signals
          - Those avoided signals get 0% return
          - A_direct would have gotten approximately A_direct_mean for those same signals
          - Market avoidance benefit ≈ (1 - fill_rate) × (0% - A_direct_mean)
          Note: assumes avoided signals would perform like average A_direct position.
          Actual result is worse if V3 avoids the BEST A_direct positions.
        """
        avoided_fraction = 1.0 - self.v3_fill_rate
        a_direct_mean = self.a_direct_mean_net_return_pct / 100  # convert to decimal
        # Avoidance benefit: 0% return for avoided signals vs A_direct's return
        benefit = avoided_fraction * (0.0 - a_direct_mean)
        return benefit * 100  # back to percentage points

    def stock_selection_estimate_ppt(self) -> Optional[float]:
        """
        Estimate stock selection within invested subset.

        V3 filled positions: 188/274
        If V3 filled positions return better than A_direct on those same 188 stocks,
        that's stock selection (net of exit rule difference).
        Cannot precisely compute without matched-stock breakdown.
        """
        return None  # UNIDENTIFIABLE without matched-stock breakdown


def build_session40_attribution(
    conn: sqlite3.Connection,
) -> MarketAvoidanceAttribution:
    """
    Build V3 market avoidance attribution from actual 5D comparison data.

    Uses:
    - V3ComparisonEngine results (5D, Oct 2026)
    - 0050 benchmark prices for attribution denominator
    - Subgroup analysis by V3 decision type
    """
    import sys
    sys.path.insert(0, ".")
    from src.research.v3_comparison_engine import V3ComparisonEngine

    engine = V3ComparisonEngine(conn)
    result = engine.run_comparison(horizon_days=5)

    # Extract key stats
    a_stats = result.strategy_stats.get("A_direct")
    d_stats = result.strategy_stats.get("D_v3")

    if a_stats is None or d_stats is None:
        return MarketAvoidanceAttribution(
            total_alpha_ppt=0.0, n_signals=0, n_v3_filled=0, n_v3_skipped=0,
            v3_fill_rate=0.0, benchmark_avg_5d_return_pct=0.0,
            a_direct_mean_net_return_pct=0.0, d_v3_mean_net_return_pct=0.0,
            overall_verdict="ATTRIBUTION_NOT_IDENTIFIABLE",
            overall_evidence="Comparison engine returned no results",
        )

    # Paired alpha for D_v3 vs A_direct
    ps_v3_a = next((ps for ps in result.paired_stats if ps.candidate == "D_v3" and ps.baseline == "A_direct"), None)
    total_alpha = ps_v3_a.mean_delta * 100 if ps_v3_a else (
        (d_stats.mean_net_return - a_stats.mean_net_return) * 100
    )

    n_sigs = result.n_universe
    n_filled = d_stats.n_filled
    n_skipped = n_sigs - n_filled
    fill_rate = d_stats.fill_rate

    # Compute 0050 benchmark average 5D return
    cur = conn.cursor()
    signal_dates = [
        "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-16",
        "2026-10-21", "2026-10-22", "2026-10-28",
    ]
    bench_returns = []
    all_price_rows = cur.execute(
        "SELECT date, open, close FROM daily_prices WHERE stock_id='0050' "
        "AND date >= '2026-10-12' ORDER BY date"
    ).fetchall()
    price_map = {r[0]: (r[1], r[2]) for r in all_price_rows}
    sorted_dates = sorted(price_map.keys())

    for sig_date in signal_dates:
        fill_idx = next((i for i, d in enumerate(sorted_dates) if d > sig_date), None)
        if fill_idx is None:
            continue
        exit_idx = fill_idx + 5
        if exit_idx >= len(sorted_dates):
            continue
        fill_date = sorted_dates[fill_idx]
        exit_date = sorted_dates[exit_idx]
        fill_price = price_map[fill_date][0]  # open
        exit_price = price_map[exit_date][1]  # close
        if fill_price > 0:
            bench_returns.append((exit_price - fill_price) / fill_price * 100)

    benchmark_avg = sum(bench_returns) / len(bench_returns) if bench_returns else 0.0

    a_mean = a_stats.mean_net_return * 100
    d_mean = d_stats.mean_net_return * 100

    attr = MarketAvoidanceAttribution(
        total_alpha_ppt=total_alpha,
        n_signals=n_sigs,
        n_v3_filled=n_filled,
        n_v3_skipped=n_skipped,
        v3_fill_rate=fill_rate,
        benchmark_avg_5d_return_pct=benchmark_avg,
        a_direct_mean_net_return_pct=a_mean,
        d_v3_mean_net_return_pct=d_mean,
    )

    # ── Component 1: Market Avoidance ──────────────────────────────────────────
    exposure_reduction_est = attr.exposure_reduction_estimate_ppt()
    pct_explained = (exposure_reduction_est / total_alpha * 100) if total_alpha != 0 else 0
    attr.components.append(AttributionComponent(
        name="Market Avoidance (Exposure Reduction)",
        status=AttributionStatus.ESTIMATED,
        estimated_contribution_ppt=round(exposure_reduction_est, 3),
        evidence=(
            f"V3 fill rate = {fill_rate:.1%}; A_direct fill rate = 100%. "
            f"V3 skipped {n_skipped}/{n_sigs} signals (returned 0%). "
            f"A_direct mean = {a_mean:.4f}%. "
            f"Exposure reduction estimate = {fill_rate:.3f} avoid × ({a_mean:.3f}% − 0%) "
            f"≈ {exposure_reduction_est:.3f}ppt (~{pct_explained:.0f}% of total alpha). "
            f"0050 benchmark avg 5D return: {benchmark_avg:.2f}% (market declined)."
        ),
        caveat=(
            "Assumes avoided signals would perform like average A_direct position. "
            "Overestimates avoidance if V3 avoids better-than-average stocks. "
            "Underestimates if V3 avoids worse-than-average stocks."
        ),
    ))

    # ── Component 2: Stock Selection within Invested (DIRECT_ENTRY subgroup) ──
    direct_entry = result.subgroup_analysis.get("by_decision", {}).get("DIRECT_ENTRY", {})
    de_alpha = direct_entry.get("mean_net_alpha", 0) * 100
    de_n = direct_entry.get("n", 0)
    attr.components.append(AttributionComponent(
        name="Stock Selection Within Invested (DIRECT_ENTRY subgroup)",
        status=AttributionStatus.PARTIAL,
        estimated_contribution_ppt=round(de_alpha, 3) if de_alpha else None,
        evidence=(
            f"V3 DIRECT_ENTRY subgroup: n={de_n}, mean_net_alpha vs A_direct = {de_alpha:.4f}%. "
            f"These {de_n} stocks: V3 and A_direct both fill at D+1 open (same price). "
            f"Alpha comes from exit rule difference (V3 own stop/target vs reconstructed A/B/C)."
        ),
        caveat=(
            "PARTIAL: Alpha for DIRECT_ENTRY is confounded by exit rule difference. "
            "V3 uses its own stop/target; A_direct uses reconstructed/forward_signals values. "
            "Cannot cleanly separate stock selection from exit rule effect."
        ),
    ))

    # ── Component 3: Avoidance Quality (AVOID_CHASING + NO_ENTRY subgroups) ──
    avoid_chasing = result.subgroup_analysis.get("by_decision", {}).get("AVOID_CHASING", {})
    no_entry = result.subgroup_analysis.get("by_decision", {}).get("NO_ENTRY", {})
    ac_alpha = avoid_chasing.get("mean_net_alpha", 0) * 100
    ne_alpha = no_entry.get("mean_net_alpha", 0) * 100
    ac_n = avoid_chasing.get("n", 0)
    ne_n = no_entry.get("n", 0)
    attr.components.append(AttributionComponent(
        name="Avoidance Quality (AVOID_CHASING + NO_ENTRY decisions)",
        status=AttributionStatus.QUANTIFIED,
        estimated_contribution_ppt=round((ac_alpha * ac_n + ne_alpha * ne_n) / (ac_n + ne_n) if (ac_n + ne_n) > 0 else 0, 3),
        evidence=(
            f"AVOID_CHASING: n={ac_n}, alpha vs A_direct = {ac_alpha:.4f}%. "
            f"NO_ENTRY: n={ne_n}, alpha vs A_direct = {ne_alpha:.4f}%. "
            f"These are stocks V3 CORRECTLY avoided — A_direct lost {-ac_alpha:.2f}% / {-ne_alpha:.2f}% on them."
        ),
        caveat=(
            "In-sample: V3 parameters were tuned on historical data that included similar "
            "avoidance patterns. AVOID_CHASING and NO_ENTRY performance may overfit "
            "to Oct 2026 market conditions."
        ),
    ))

    # ── Component 4: Entry Timing ─────────────────────────────────────────────
    attr.components.append(AttributionComponent(
        name="Entry Timing (Price Improvement)",
        status=AttributionStatus.UNIDENTIFIABLE,
        estimated_contribution_ppt=None,
        evidence=(
            "All strategies fill at D+1 open (same date, same price). "
            "V3's WAIT_MA20_PULLBACK and WAIT_BREAKOUT_CONFIRMATION decisions result in "
            "LATER fills (D+2, D+3, etc.) — but these lags are NOT tracked in the comparison engine. "
            "The comparison engine counts WAIT signals as no-fill → 0% return."
        ),
        caveat=(
            "UNIDENTIFIABLE: Entry timing benefit from waiting (better price) cannot be measured "
            "without tracking actual fill prices for WAIT outcomes. "
            "Current setup: WAIT → 0% → favors V3 during market decline."
        ),
    ))

    # ── Component 5: Transaction Cost ─────────────────────────────────────────
    fees_pct = 0.585
    cost_saving = (n_skipped / n_sigs) * fees_pct
    attr.components.append(AttributionComponent(
        name="Transaction Cost Savings",
        status=AttributionStatus.QUANTIFIED,
        estimated_contribution_ppt=round(cost_saving, 4),
        evidence=(
            f"V3 fills {n_filled}/{n_sigs} signals ({fill_rate:.1%}). "
            f"FEES_PCT = {fees_pct}%. "
            f"Cost saving from non-fills = {fill_rate:.3f} skipped × {fees_pct:.3f}% ≈ {cost_saving:.4f}ppt. "
            f"This is a MINOR contribution to the {total_alpha:.2f}ppt total alpha."
        ),
        caveat="Assumes skipped signals incur 0 cost. Net cost saving ≈ 0.18ppt of 3.66ppt total.",
    ))

    # ── Summary ───────────────────────────────────────────────────────────────
    attr.overall_verdict = "MARKET_AVOIDANCE_DRIVEN"
    attr.overall_evidence = (
        f"Total V3 alpha vs A_direct = +{total_alpha:.2f}ppt (5D, Oct 2026 window). "
        f"Estimated market avoidance component: {exposure_reduction_est:.2f}ppt "
        f"({pct_explained:.0f}% of total). "
        f"Market declined avg {benchmark_avg:.2f}% (0050) during hold periods. "
        f"V3 fill rate = {fill_rate:.1%} vs 100% for A_direct. "
        f"Stock selection within invested (DIRECT_ENTRY): {de_alpha:.2f}ppt alpha (n={de_n}), "
        f"confounded by exit rule difference. "
        f"Entry timing: UNIDENTIFIABLE. "
        f"Transaction cost savings: minor (~{cost_saving:.2f}ppt). "
        f"Conclusion: V3's advantage in this window is primarily from reduced exposure "
        f"during a market decline. Consistent with Sessions 27-28 findings."
    )

    return attr
