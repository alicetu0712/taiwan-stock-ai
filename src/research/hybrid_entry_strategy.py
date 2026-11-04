"""
hybrid_entry_strategy.py — Hybrid Entry Strategy V1 (Shadow Research)

RESEARCH ONLY — NOT A LIVE TRADING SYSTEM.

Implements Hybrid Entry Strategy V1: a rules-based conditional entry method
that selects between DIRECT_NEXT_OPEN (V1 behaviour) and WAIT_PULLBACK (V2
behaviour) based on market regime and MA20 trend state at signal time.

Rule derivation background:
  Exploration of the 2024-10 to 2026-09 research cohort found:
    - WAIT_FOR_PULLBACK + Bear regime:    delta +0.36pp (95% CI spans zero in
                                          the full dataset, [+0.02, +0.69] in
                                          the bear subgroup — pre-Bonferroni)
    - WAIT_FOR_PULLBACK + Flat MA20:      delta +0.41pp ([+0.09, +0.70])

  These findings are HYPOTHESIS-GENERATING and are pre-registered here for
  prospective forward validation.  The same dataset CANNOT be used as OOS.

Rule freeze:
  Version:    hybrid_v1
  Frozen at:  2026-11-05T00:00:00
  Frozen SHA: 6602c3b

FORBIDDEN: Do not modify MODEL_VERSION, BUY/STRONG_BUY thresholds,
           ForwardSignals, ACTUAL/PAPER positions, or Phase 1B migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

RULE_VERSION = "hybrid_v1"
RULE_FROZEN_AT = "2026-11-05T00:00:00"
RULE_FROZEN_COMMIT = "6602c3b"

# Entry labels (mirrors execution_simulator)
_ENTRY_READY = "ENTRY_READY"
_WAIT_PULLBACK = "WAIT_FOR_PULLBACK"
_WAIT_BREAKOUT = "WAIT_FOR_BREAKOUT"

# MA20 trend thresholds (mirrors effectiveness_analyzer)
MA20_RISING_THRESHOLD = 0.3
MA20_FALLING_THRESHOLD = -0.3


# ── Enums ─────────────────────────────────────────────────────────────────────

class HybridAction(str, Enum):
    """The entry action Hybrid strategy assigns to a signal."""
    DIRECT_NEXT_OPEN = "DIRECT_NEXT_OPEN"
    WAIT_PULLBACK    = "WAIT_PULLBACK"
    WAIT_BREAKOUT    = "WAIT_BREAKOUT"
    SKIP             = "SKIP"


class RulePriority(int, Enum):
    """Priority levels in the Hybrid decision tree (lower = higher priority)."""
    P1_BEAR_PULLBACK  = 1   # Bear regime + WAIT_FOR_PULLBACK
    P2_FLAT_PULLBACK  = 2   # Flat MA20 + WAIT_FOR_PULLBACK
    P3_BULL_RISING    = 3   # Bull regime + MA20 Rising
    P4_DEFAULT        = 4   # All other cases


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class HybridStrategyConfig:
    """
    Immutable configuration for one rule version.

    Thresholds must NOT be changed after freeze_commit is set.
    To change rules, create a new version with a new freeze_commit.
    """
    version_id: str = RULE_VERSION
    frozen_at: str = RULE_FROZEN_AT
    frozen_commit: str = RULE_FROZEN_COMMIT
    description: str = (
        "V1 rules: Bear or Flat MA20 → WAIT_PULLBACK for WAIT_FOR_PULLBACK "
        "signals; all others → DIRECT_NEXT_OPEN.  "
        "WAIT_FOR_BREAKOUT always → DIRECT_NEXT_OPEN."
    )
    # Rule thresholds — do not modify
    ma20_rising_threshold: float = MA20_RISING_THRESHOLD
    ma20_falling_threshold: float = MA20_FALLING_THRESHOLD


@dataclass
class HybridDecision:
    """
    Full record of one Hybrid entry decision.

    All input features must come from data available on or before
    feature_cutoff_date (= signal_date).  No future data is used.
    """
    stock_id: str
    signal_date: date

    # ── Input features (all known at signal_date) ─────────────────────────────
    v2_entry_label: str         # from EntryTimingAnalyzer (ENTRY_READY, WAIT_FOR_PULLBACK, ...)
    market_regime: str          # bull / neutral / bear / unknown (from 0050 MA20)
    ma20_trend: str             # rising / flat / falling (from stock's own MA20 slope)
    ma20_slope_pct: float       # raw slope % for audit

    # ── Decision ──────────────────────────────────────────────────────────────
    hybrid_action: HybridAction
    rule_reason: str
    rule_priority: int          # RulePriority value

    # ── Traceability ──────────────────────────────────────────────────────────
    rule_version: str = RULE_VERSION
    feature_cutoff_date: date = field(default_factory=date.today)
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Optional context ──────────────────────────────────────────────────────
    ma20_gap_pct: Optional[float] = None


@dataclass
class HybridForwardShadow:
    """
    Persistent record of a Hybrid decision for prospective forward validation.

    outcome_* fields are filled in AFTER the hold period matures.
    Idempotency key: (stock_id, signal_date, rule_version).
    """
    stock_id: str
    signal_date: date
    rule_version: str

    # Decision snapshot
    v2_entry_label: str
    market_regime: str
    ma20_trend: str
    ma20_slope_pct: float
    hybrid_action: str
    rule_reason: str
    rule_priority: int
    feature_cutoff_date: date
    calculated_at: datetime

    # Prospective outcomes (None until matured)
    outcome_5d: Optional[float] = None
    outcome_10d: Optional[float] = None
    outcome_20d: Optional[float] = None
    outcome_recorded_at: Optional[datetime] = None


# ── Core decision engine ──────────────────────────────────────────────────────

class HybridDecisionService:
    """
    Apply Hybrid V1 rules to produce a HybridDecision per signal.

    Design invariant: all inputs must be computable from data on or before
    signal_date.  The service itself performs no data loading.

    Rule priority (highest first):
      P1  Bear regime + WAIT_FOR_PULLBACK label → WAIT_PULLBACK
      P2  Flat MA20 + WAIT_FOR_PULLBACK label   → WAIT_PULLBACK
      P3  Bull regime + Rising MA20              → DIRECT_NEXT_OPEN
      P4  Default                                → DIRECT_NEXT_OPEN
    """

    def __init__(self, config: Optional[HybridStrategyConfig] = None) -> None:
        self.config = config or HybridStrategyConfig()

    def decide(
        self,
        stock_id: str,
        signal_date: date,
        v2_entry_label: str,
        market_regime: str,
        ma20_trend: str,
        ma20_slope_pct: float = 0.0,
        ma20_gap_pct: Optional[float] = None,
    ) -> HybridDecision:
        """
        Apply rule tree and return HybridDecision.

        market_regime and ma20_trend must be derived from data strictly
        available on signal_date — no look-ahead.
        """
        action, reason, priority = self._apply_rules(
            v2_entry_label, market_regime, ma20_trend
        )

        return HybridDecision(
            stock_id=stock_id,
            signal_date=signal_date,
            v2_entry_label=v2_entry_label,
            market_regime=market_regime,
            ma20_trend=ma20_trend,
            ma20_slope_pct=ma20_slope_pct,
            hybrid_action=action,
            rule_reason=reason,
            rule_priority=priority,
            rule_version=self.config.version_id,
            feature_cutoff_date=signal_date,
            calculated_at=datetime.now(timezone.utc),
            ma20_gap_pct=ma20_gap_pct,
        )

    def _apply_rules(
        self,
        entry_label: str,
        market_regime: str,
        ma20_trend: str,
    ) -> tuple[HybridAction, str, int]:
        """
        Rule tree.  Returns (action, reason, priority).

        Critically: rules only fire for WAIT_FOR_PULLBACK signals because
        only that label was shown to benefit from waiting in specific regimes.
        WAIT_FOR_BREAKOUT and ENTRY_READY always → DIRECT_NEXT_OPEN.
        """
        # P1: Bear + WAIT_FOR_PULLBACK → patience reduces buying into weakness
        if market_regime == "bear" and entry_label == _WAIT_PULLBACK:
            return (
                HybridAction.WAIT_PULLBACK,
                "P1: Bear regime + WAIT_FOR_PULLBACK — waiting reduces downtrend exposure",
                RulePriority.P1_BEAR_PULLBACK,
            )

        # P2: Flat MA20 + WAIT_FOR_PULLBACK → trend ambiguity; pullback improves entry
        if ma20_trend == "flat" and entry_label == _WAIT_PULLBACK:
            return (
                HybridAction.WAIT_PULLBACK,
                "P2: Flat MA20 trend + WAIT_FOR_PULLBACK — ambiguous trend; pullback entry preferred",
                RulePriority.P2_FLAT_PULLBACK,
            )

        # P3: Bull + Rising MA20 → momentum is clear; direct entry captures it
        if market_regime == "bull" and ma20_trend == "rising":
            return (
                HybridAction.DIRECT_NEXT_OPEN,
                "P3: Bull regime + Rising MA20 — momentum entry; no waiting",
                RulePriority.P3_BULL_RISING,
            )

        # P4: Default → direct entry
        return (
            HybridAction.DIRECT_NEXT_OPEN,
            f"P4: Default entry ({entry_label}, regime={market_regime}, trend={ma20_trend})",
            RulePriority.P4_DEFAULT,
        )

    def classify_ma20_trend(self, slope_pct: float) -> str:
        """Classify slope into trend label (mirrors effectiveness_analyzer)."""
        if slope_pct > self.config.ma20_rising_threshold:
            return "rising"
        if slope_pct < self.config.ma20_falling_threshold:
            return "falling"
        return "flat"


# ── Simulation adapter ────────────────────────────────────────────────────────

def hybrid_action_to_simulation_params(
    hybrid_action: HybridAction,
    v2_entry_label: str,
    prior_20d_high: Optional[float],
) -> tuple[str, Optional[float]]:
    """
    Map a HybridAction to the simulation entry_label and prior_20d_high to
    pass into EntryTimingExecutionSimulator.simulate_v2().

    Returns (sim_entry_label, prior_20d_high_to_use).

    Mapping:
      WAIT_PULLBACK    → WAIT_FOR_PULLBACK  (use simulator's pullback logic)
      WAIT_BREAKOUT    → WAIT_FOR_BREAKOUT  (use simulator's breakout logic)
      DIRECT_NEXT_OPEN → ENTRY_READY        (bypass wait; immediate entry)
      SKIP             → original label     (no simulation; label excludes entry)
    """
    if hybrid_action == HybridAction.WAIT_PULLBACK:
        return "WAIT_FOR_PULLBACK", prior_20d_high
    if hybrid_action == HybridAction.WAIT_BREAKOUT:
        return "WAIT_FOR_BREAKOUT", prior_20d_high
    if hybrid_action == HybridAction.DIRECT_NEXT_OPEN:
        return "ENTRY_READY", prior_20d_high
    # SKIP
    return v2_entry_label, prior_20d_high
