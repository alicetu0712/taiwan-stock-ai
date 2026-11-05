"""
v3_entry_strategy.py — V3 Entry Timing Strategy (Research-only Prototype)

RESEARCH ONLY — NOT A LIVE TRADING SYSTEM.

V3 is structurally different from V1/V2 (entry_timing.py) in six ways:
  1. MA60 as an explicit secondary support level (V1/V2 ignores MA60 entirely)
  2. MA20 and MA60 slope as entry QUALIFIERS — not just levels
  3. Volume signature classification (3-class: contracting/neutral/expanding)
     vs V1/V2's binary vol_ratio >= 1.0 for breakout only
  4. Market regime adaptation — thresholds shift in bull/bear/sideways
  5. Multi-setup confidence scoring — 0-100 alignment score
  6. Near-breakout vs failed-breakout distinction as first-class setups

Comparison to existing systems:
  V1/V2 (entry_timing.py):
    - Inputs: close, high, volume
    - MA used: MA20 only (level, no slope)
    - Outputs: 7 labels (ENTRY_READY / WAIT_FOR_PULLBACK / WAIT_FOR_BREAKOUT /
               TOO_EXTENDED / RISK_REWARD_UNFAVORABLE / NO_VALID_SETUP / INSUFFICIENT_DATA)
    - Market regime: ignored
    - MA60: ignored
    - Volume: only binary breakout qualifier

  V3 (this module):
    - Inputs: close, high, low, volume, market_regime
    - MA used: MA20 + MA60 (both level AND slope)
    - Outputs: 6 decisions (DIRECT_ENTRY / WAIT_MA20_PULLBACK / WAIT_MA60_SUPPORT /
               WAIT_BREAKOUT_CONFIRMATION / AVOID_CHASING / NO_ENTRY)
    - Market regime: explicitly adjusts thresholds
    - MA60: used as second support level and trend filter
    - Volume: 3-class signature + contracting-pullback bonus

  Hybrid V1 (hybrid_entry_strategy.py — FROZEN):
    - Input: v2_entry_label + market_regime + ma20_trend
    - Rules: P1-P4 (Bear+WAIT→WAIT_PULLBACK, Flat+WAIT→WAIT_PULLBACK, default DIRECT)
    - V3 is NOT a replacement; it is a parallel research track

FORBIDDEN:
  - Do NOT modify MODEL_VERSION v8.0
  - Do NOT modify foe_v1
  - Do NOT modify BUY/STRONG BUY thresholds
  - Do NOT modify Frozen ForwardSignals
  - Do NOT modify ACTUAL/PAPER accounting
  - Do NOT modify Hybrid P1–P4
  - Do NOT deploy V3 to production
  - Do NOT write to Neon
  - Do NOT modify hybrid_forward_decision table
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Version ────────────────────────────────────────────────────────────────────

RESEARCH_VERSION = "v3_research_v1"

# ── Entry Decision Labels ──────────────────────────────────────────────────────

DIRECT_ENTRY = "DIRECT_ENTRY"                       # enter now (next open)
WAIT_MA20_PULLBACK = "WAIT_MA20_PULLBACK"           # trend OK; wait for MA20 touch
WAIT_MA60_SUPPORT = "WAIT_MA60_SUPPORT"             # extended above MA20; wait for MA60 test
WAIT_BREAKOUT_CONFIRMATION = "WAIT_BREAKOUT_CONF"   # near resistance; wait for volume breakout
AVOID_CHASING = "AVOID_CHASING"                     # too extended or failed setup
NO_ENTRY = "NO_ENTRY"                               # no valid setup
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

ALL_V3_DECISIONS = [
    DIRECT_ENTRY,
    WAIT_MA20_PULLBACK,
    WAIT_MA60_SUPPORT,
    WAIT_BREAKOUT_CONFIRMATION,
    AVOID_CHASING,
    NO_ENTRY,
    INSUFFICIENT_DATA,
]

# ── Minimum bars ──────────────────────────────────────────────────────────────

MIN_BARS_MA20 = 21     # MA20 + prior_20d_high without look-ahead
MIN_BARS_MA60 = 61     # MA60 required
MIN_BARS_SLOPE = 31    # MA20 slope window (20 + 10 slope_bars + 1)
MIN_BARS_FULL = 71     # MA60 slope window (60 + 10 + 1)

# ── Thresholds by Market Regime ────────────────────────────────────────────────
# V3 distinguishes from V1/V2 by adapting these per regime.
# V1/V2 uses a single fixed zone regardless of regime.

_REGIME_PARAMS = {
    "bull": {
        # MA20 pullback zone: price within [lower, upper] % of MA20
        "ma20_zone_lower": -3.0,    # price can be up to 3% below MA20
        "ma20_zone_upper": +2.0,    # price must be within 2% above MA20
        # MA60 support zone
        "ma60_zone": 3.0,           # within ±3% of MA60
        # Too extended (AVOID_CHASING)
        "too_extended_pct": 18.0,
        # Breakout: how far above 20D high (avoid late entry)
        "breakout_max_premium": 5.0,
        # Volume: minimum vol_ratio for breakout confirmation
        "breakout_min_vol": 1.2,
        # Volume: contraction qualifier for pullback (vol_ratio below this = healthy)
        "pullback_vol_contraction": 0.8,
    },
    "bear": {
        "ma20_zone_lower": -1.0,    # tighter — less tolerance below MA20 in bear
        "ma20_zone_upper": +1.5,    # very close to MA20 required
        "ma60_zone": 2.0,           # tighter MA60 zone
        "too_extended_pct": 12.0,   # lower threshold — extended faster in bear
        "breakout_max_premium": 3.0,
        "breakout_min_vol": 1.5,    # requires more volume confirmation in bear
        "pullback_vol_contraction": 0.7,
    },
    "neutral": {
        "ma20_zone_lower": -2.0,
        "ma20_zone_upper": +2.5,
        "ma60_zone": 3.0,
        "too_extended_pct": 15.0,
        "breakout_max_premium": 4.0,
        "breakout_min_vol": 1.3,
        "pullback_vol_contraction": 0.75,
    },
}
_REGIME_PARAMS["sideways"] = _REGIME_PARAMS["neutral"]
_REGIME_PARAMS["unknown"] = _REGIME_PARAMS["neutral"]

# ── MA Slope thresholds ────────────────────────────────────────────────────────
# Same definition as effectiveness_analyzer / hybrid_entry_strategy
MA20_SLOPE_BARS = 10        # compute slope over last 10 bars
MA60_SLOPE_BARS = 10        # compute slope over last 10 bars for MA60
MA20_RISING_THRESHOLD = 0.3  # slope % above this → rising
MA20_FALLING_THRESHOLD = -0.3

# ── Volume Signature ───────────────────────────────────────────────────────────
VOL_CONTRACTING_RATIO = 0.8    # 3D avg / 10D avg < 0.8 → contracting
VOL_EXPANDING_RATIO = 1.3      # 3D avg / 10D avg > 1.3 → expanding

# ── R/R Parameters ────────────────────────────────────────────────────────────
# Mirrors V1/V2 for comparability
STOP_BUFFER = 0.03
MIN_RR_RATIO = 2.0

# ── Reason Code Registry ──────────────────────────────────────────────────────
RC_MA60_NOT_RISING = "MA60_SLOPE_NOT_RISING"
RC_MA20_FALLING = "MA20_SLOPE_FALLING"
RC_BELOW_BOTH_MAS = "PRICE_BELOW_MA20_AND_MA60"
RC_TOO_EXTENDED = "MA20_GAP_TOO_EXTENDED"
RC_FAILED_BREAKOUT = "FAILED_BREAKOUT_DETECTED"
RC_MA20_PULLBACK_ZONE = "MA20_PULLBACK_ZONE_ACTIVE"
RC_MA60_SUPPORT_ZONE = "MA60_SUPPORT_ZONE_ACTIVE"
RC_VOL_CONTRACTING = "VOLUME_CONTRACTING_PULLBACK"
RC_VOL_EXPANDING = "VOLUME_EXPANDING_BREAKOUT"
RC_VOL_SPIKE_RISK = "VOLUME_SPIKE_EXHAUSTION_RISK"
RC_BREAKOUT_CONFIRMED = "BREAKOUT_VOL_CONFIRMED"
RC_NEAR_RESISTANCE = "NEAR_RESISTANCE_NO_BREAKOUT"
RC_RR_FAVORABLE = "RR_RATIO_FAVORABLE"
RC_RR_UNFAVORABLE = "RR_RATIO_UNFAVORABLE"
RC_MARKET_REGIME_ADAPTED = "THRESHOLD_ADAPTED_FOR_REGIME"
RC_BULL_REGIME_ENTRY = "BULL_REGIME_DIRECT_ENTRY"
RC_BEAR_REGIME_CAUTION = "BEAR_REGIME_CAUTION"
RC_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
RC_CONFLICT_MA20_WINS = "CONFLICT_MA20_ZONE_WINS_OVER_MA60"
RC_NO_VALID_SETUP = "NO_VALID_SETUP"


# ── Output dataclass ───────────────────────────────────────────────────────────

@dataclass
class V3EntryDecision:
    """
    Full record of a V3 entry timing decision.

    All inputs derive from data available on or before signal_date (no look-ahead).
    """

    stock_id: str

    # ── Primary output ────────────────────────────────────────────────────────
    entry_decision: str = INSUFFICIENT_DATA
    confidence: float = 0.0        # 0-100; higher = more confirming signals
    research_version: str = RESEARCH_VERSION

    # ── Setup classification ──────────────────────────────────────────────────
    setup_type: str = "none"       # S1-S6 label for the dominant setup
    market_regime: str = "unknown"

    # ── MA indicators ─────────────────────────────────────────────────────────
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    ma20_gap_pct: Optional[float] = None   # (close-MA20)/MA20 * 100
    ma60_gap_pct: Optional[float] = None   # (close-MA60)/MA60 * 100
    ma20_slope_pct: Optional[float] = None # 10-bar MA20 % change
    ma60_slope_pct: Optional[float] = None # 10-bar MA60 % change
    ma20_trend: str = "flat"              # rising / flat / falling
    ma60_trend: str = "flat"

    # ── Resistance & breakout ─────────────────────────────────────────────────
    prior_20d_high: Optional[float] = None
    dist_to_resistance_pct: Optional[float] = None
    resistance_broken: bool = False
    near_resistance: bool = False      # within 3% of prior_20d_high
    failed_breakout: bool = False      # recent bar peaked above resistance, now below

    # ── Volume signature ──────────────────────────────────────────────────────
    vol_ratio: Optional[float] = None             # today / 20D avg
    volume_signature: str = "neutral"             # contracting / neutral / expanding
    vol_contraction_in_pullback: bool = False     # healthy pullback flag

    # ── Entry parameters ──────────────────────────────────────────────────────
    entry_price: Optional[float] = None           # today's close (proxy for next open)
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    risk: Optional[float] = None
    reward: Optional[float] = None
    rr_ratio: Optional[float] = None

    # Proposed limit/trigger levels for WAIT_* decisions
    proposed_limit_price: Optional[float] = None  # trigger level to watch
    invalidation_price: Optional[float] = None    # if hit, setup is invalid

    # ── Execution model ───────────────────────────────────────────────────────
    # Mirrors execution_simulator.py constants for consistency
    entry_order_type: str = "DIRECT_NEXT_OPEN"    # or CONFIRMED_NEXT_OPEN
    data_quality_status: str = "OK"               # OK / PARTIAL (missing MA60)
    research_capture_type: str = "RESEARCH_ONLY"  # always RESEARCH_ONLY in V3 prototype

    # ── Diagnostics ───────────────────────────────────────────────────────────
    reason_codes: List[str] = field(default_factory=list)
    data_bars: int = 0


# ── Core Analyzer ─────────────────────────────────────────────────────────────

class V3EntryTimingAnalyzer:
    """
    Pure-compute entry timing analyzer for V3.

    Requires: close, high, low, volume columns.
    Optional: market_regime (default "unknown").

    Design invariants:
      - No DB access
      - No side effects
      - Deterministic (same input → same output)
      - No look-ahead: all indicators use data strictly before or on signal_date
      - prior_20d_high uses high[-21:-1] (excludes today, same as V1/V2)
      - MA60 slope uses only past data

    Key differences from V1/V2 EntryTimingAnalyzer (entry_timing.py):
      - Uses MA60 for support detection and trend filtering
      - Uses MA20 and MA60 slope as entry qualifiers
      - Adapts thresholds to market_regime
      - Classifies volume into 3 signatures
      - Produces confidence score
    """

    def analyze(
        self,
        stock_id: str,
        history: pd.DataFrame,
        market_regime: str = "unknown",
    ) -> V3EntryDecision:
        result = V3EntryDecision(stock_id=stock_id, market_regime=market_regime)

        if history is None or len(history) < MIN_BARS_MA20:
            result.entry_decision = INSUFFICIENT_DATA
            result.reason_codes.append(RC_INSUFFICIENT_DATA)
            return result

        hist = history.sort_values("date").reset_index(drop=True)
        close = hist["close"].values.astype(float)
        high = hist["high"].values.astype(float) if "high" in hist.columns else close
        low = hist["low"].values.astype(float) if "low" in hist.columns else close
        volume = (
            hist["volume"].values.astype(float)
            if "volume" in hist.columns
            else np.ones(len(hist))
        )

        n = len(close)
        result.data_bars = n
        cur = float(close[-1])
        result.entry_price = cur

        params = _REGIME_PARAMS.get(market_regime, _REGIME_PARAMS["unknown"])

        # ── Step 1: Compute all MA indicators ─────────────────────────────────
        ma20 = float(np.mean(close[-20:])) if n >= 20 else None
        ma60 = float(np.mean(close[-60:])) if n >= 60 else None
        result.ma20 = round(ma20, 2) if ma20 else None
        result.ma60 = round(ma60, 2) if ma60 else None

        ma20_gap = (cur - ma20) / ma20 * 100.0 if ma20 and ma20 > 0 else None
        ma60_gap = (cur - ma60) / ma60 * 100.0 if ma60 and ma60 > 0 else None
        result.ma20_gap_pct = round(ma20_gap, 2) if ma20_gap is not None else None
        result.ma60_gap_pct = round(ma60_gap, 2) if ma60_gap is not None else None

        # MA20 slope — 10-bar % change
        ma20_slope = _compute_ma_slope(close, 20, MA20_SLOPE_BARS) if n >= MIN_BARS_SLOPE else None
        # MA60 slope — 10-bar % change
        ma60_slope = _compute_ma_slope(close, 60, MA60_SLOPE_BARS) if n >= MIN_BARS_FULL else None
        result.ma20_slope_pct = round(ma20_slope, 4) if ma20_slope is not None else None
        result.ma60_slope_pct = round(ma60_slope, 4) if ma60_slope is not None else None

        result.ma20_trend = _classify_slope(ma20_slope) if ma20_slope is not None else "flat"
        result.ma60_trend = _classify_slope(ma60_slope) if ma60_slope is not None else "flat"

        if ma60 is None:
            result.data_quality_status = "PARTIAL"

        # ── Step 2: Resistance state (same look-ahead prevention as V1/V2) ────
        prior_20d_high = float(np.max(high[-21:-1]))
        result.prior_20d_high = prior_20d_high
        dist_pct = (prior_20d_high - cur) / cur * 100.0
        result.dist_to_resistance_pct = round(dist_pct, 2)
        result.resistance_broken = cur > prior_20d_high
        result.near_resistance = (not result.resistance_broken) and (dist_pct <= 3.0)

        # Failed breakout: recent bar (last 3 excl today) peaked above resistance
        # but today is well below it
        if n >= 4:
            recent_peak = float(np.max(high[-4:-1]))
            result.failed_breakout = (
                not result.resistance_broken
                and recent_peak >= prior_20d_high * 0.999
                and cur < prior_20d_high * 0.97
            )

        # ── Step 3: Volume signature ──────────────────────────────────────────
        vol_ma20 = float(np.mean(volume[-20:])) if n >= 20 else None
        vol_ratio = round(float(volume[-1]) / vol_ma20, 2) if vol_ma20 and vol_ma20 > 0 else None
        result.vol_ratio = vol_ratio

        # Volume trend: compare 3D average vs 10D average (excluding today)
        volume_signature = "neutral"
        if n >= 11:
            vol_3d = float(np.mean(volume[-4:-1]))   # last 3 bars excluding today
            vol_10d = float(np.mean(volume[-11:-1]))  # last 10 bars excluding today
            if vol_10d > 0:
                vol_trend_ratio = vol_3d / vol_10d
                if vol_trend_ratio < VOL_CONTRACTING_RATIO:
                    volume_signature = "contracting"
                elif vol_trend_ratio > VOL_EXPANDING_RATIO:
                    volume_signature = "expanding"
        result.volume_signature = volume_signature

        # Healthy pullback: price declining from above MA20 zone, volume contracting
        result.vol_contraction_in_pullback = (
            volume_signature == "contracting"
            and ma20_gap is not None
            and ma20_gap < params["ma20_zone_upper"] + 2.0
            and ma20_gap > params["ma20_zone_lower"] - 5.0
        )

        # ── Step 4: R/R Computation (same stop formula as V1/V2) ─────────────
        # stop = MA20 * (1 - STOP_BUFFER); secondary: MA60 * (1 - STOP_BUFFER)
        stop_anchor = ma60 if (ma60 and ma60 < cur) else ma20
        if stop_anchor and stop_anchor > 0:
            stop = stop_anchor * (1.0 - STOP_BUFFER)
            result.stop_price = round(stop, 2)
            risk = cur - stop
            if risk > 0 and prior_20d_high > stop:
                target = prior_20d_high + (prior_20d_high - stop)
                result.target_price = round(target, 2)
                result.risk = round(risk, 4)
                result.reward = round(target - cur, 4)
                result.rr_ratio = round(result.reward / result.risk, 2)
            elif risk > 0 and not result.resistance_broken:
                target = prior_20d_high
                result.target_price = round(target, 2)
                result.risk = round(risk, 4)
                result.reward = round(target - cur, 4)
                result.rr_ratio = round(result.reward / result.risk, 2)

        # ── Step 5: Decision logic ─────────────────────────────────────────────
        result.entry_decision, result.setup_type, result.confidence = self._decide(
            result, params, market_regime
        )
        return result

    def _decide(
        self,
        r: V3EntryDecision,
        params: dict,
        market_regime: str,
    ) -> Tuple[str, str, float]:
        """
        Return (entry_decision, setup_type, confidence).

        Priority order:
          1. Hard stops (failed breakout, below both MAs, MA60 falling)
          2. Too extended (AVOID_CHASING)
          3. Breakout confirmation (DIRECT_ENTRY or WAIT_BREAKOUT_CONF)
          4. MA20 pullback zone (DIRECT_ENTRY with confirmation, or WAIT_MA20_PULLBACK)
          5. MA60 support zone (DIRECT_ENTRY or WAIT_MA60_SUPPORT)
          6. Default (NO_ENTRY or WAIT_MA20_PULLBACK)

        V3 differs from V1/V2 by checking MA60 slope, MA20 slope, volume signature,
        and adapting thresholds to market_regime.
        """
        rcs: List[str] = r.reason_codes
        confidence = 0.0

        # ── Hard stop: failed breakout ─────────────────────────────────────────
        if r.failed_breakout:
            rcs.append(RC_FAILED_BREAKOUT)
            return AVOID_CHASING, "failed_breakout", 20.0

        # ── Hard stop: price below both MAs ────────────────────────────────────
        if (
            r.ma20 is not None
            and r.ma60 is not None
            and r.entry_price is not None
            and r.entry_price < r.ma20
            and r.entry_price < r.ma60
        ):
            rcs.append(RC_BELOW_BOTH_MAS)
            return NO_ENTRY, "below_both_mas", 10.0

        # ── Hard stop: MA60 clearly falling (trend deteriorating) ──────────────
        # V3 key differentiator: requires MA60 non-falling for MA20 pullback setups
        # V1/V2 does NOT check MA60 at all
        if r.ma60 is not None and r.ma60_trend == "falling":
            rcs.append(RC_MA60_NOT_RISING)
            # Can still enter on breakout, but MA20 pullback is blocked
            # Fall through — breakout check handles it

        # ── Too extended ───────────────────────────────────────────────────────
        if r.ma20_gap_pct is not None and r.ma20_gap_pct >= params["too_extended_pct"]:
            rcs.append(RC_TOO_EXTENDED)
            # Volume spike during extension = exhaustion risk
            if r.vol_ratio is not None and r.vol_ratio >= 2.0:
                rcs.append(RC_VOL_SPIKE_RISK)
            return AVOID_CHASING, "overextended", 15.0

        # ── Breakout path ──────────────────────────────────────────────────────
        if r.resistance_broken:
            premium_pct = abs(r.dist_to_resistance_pct or 0.0)
            if premium_pct > params["breakout_max_premium"]:
                # Broke out too long ago — chasing
                rcs.append(RC_TOO_EXTENDED)
                return AVOID_CHASING, "breakout_stale", 10.0

            vol_ok = r.vol_ratio is not None and r.vol_ratio >= params["breakout_min_vol"]
            confidence = 50.0
            if vol_ok:
                confidence += 25.0
                rcs.append(RC_BREAKOUT_CONFIRMED)
                rcs.append(RC_VOL_EXPANDING)
            else:
                # Breakout without volume — wait for retest or volume confirmation
                rcs.append(RC_NEAR_RESISTANCE)
                return WAIT_BREAKOUT_CONFIRMATION, "near_breakout", 40.0

            if r.ma20_trend == "rising":
                confidence += 10.0
            if r.ma60_trend in ("rising", "flat"):
                confidence += 10.0
            if market_regime == "bull":
                confidence += 5.0
                rcs.append(RC_BULL_REGIME_ENTRY)
            rcs.append(RC_MARKET_REGIME_ADAPTED)
            if r.rr_ratio is not None:
                if r.rr_ratio >= MIN_RR_RATIO:
                    rcs.append(RC_RR_FAVORABLE)
                    confidence += 5.0
                else:
                    rcs.append(RC_RR_UNFAVORABLE)

            entry_type = "DIRECT_NEXT_OPEN"
            r.entry_order_type = entry_type
            return DIRECT_ENTRY, "breakout", round(min(confidence, 100.0), 1)

        # ── Near resistance (but not yet broken) ───────────────────────────────
        if r.near_resistance:
            rcs.append(RC_NEAR_RESISTANCE)
            # Wait for breakout + volume
            return WAIT_BREAKOUT_CONFIRMATION, "near_breakout", 35.0

        # ── MA20 pullback zone ─────────────────────────────────────────────────
        if r.ma20_gap_pct is not None:
            in_ma20_zone = (
                params["ma20_zone_lower"] <= r.ma20_gap_pct <= params["ma20_zone_upper"]
            )
        else:
            in_ma20_zone = False

        # ── MA60 support zone ──────────────────────────────────────────────────
        # V3 key differentiator: separate MA60 support setup
        in_ma60_zone = (
            r.ma60_gap_pct is not None
            and abs(r.ma60_gap_pct) <= params["ma60_zone"]
            and r.ma20 is not None
            and r.ma60 is not None
            and r.ma20 > r.ma60  # structural integrity: MA20 > MA60
        )

        # ── MA20 pullback entry ────────────────────────────────────────────────
        if in_ma20_zone:
            # Require MA60 not falling (V3 key differentiator vs V1/V2)
            if r.ma60_trend == "falling":
                rcs.append(RC_MA60_NOT_RISING)
                # Downgrade: wait for MA60 stabilisation
                return NO_ENTRY, "ma20_pullback_ma60_falling", 20.0

            rcs.append(RC_MA20_PULLBACK_ZONE)
            confidence = 40.0

            # MA20 slope boosts confidence
            if r.ma20_trend == "rising":
                confidence += 20.0
            elif r.ma20_trend == "flat":
                confidence += 10.0
            else:
                rcs.append(RC_MA20_FALLING)
                confidence -= 10.0

            # Volume contraction during pullback = healthy setup
            if r.vol_contraction_in_pullback:
                rcs.append(RC_VOL_CONTRACTING)
                confidence += 15.0
            elif r.volume_signature == "expanding":
                # Volume expanding while pulling back = distribution risk
                rcs.append(RC_VOL_EXPANDING)
                confidence -= 10.0

            # MA60 alignment
            if r.ma60_trend == "rising":
                confidence += 10.0
            if r.ma60 is not None and r.entry_price is not None and r.entry_price > r.ma60:
                confidence += 5.0

            # Market regime
            if market_regime == "bear":
                rcs.append(RC_BEAR_REGIME_CAUTION)
                confidence -= 10.0
            elif market_regime == "bull":
                rcs.append(RC_BULL_REGIME_ENTRY)
                confidence += 5.0

            rcs.append(RC_MARKET_REGIME_ADAPTED)

            if r.rr_ratio is not None:
                if r.rr_ratio >= MIN_RR_RATIO:
                    rcs.append(RC_RR_FAVORABLE)
                    confidence += 10.0
                else:
                    rcs.append(RC_RR_UNFAVORABLE)
                    confidence -= 15.0

            confidence = round(min(max(confidence, 0.0), 100.0), 1)

            if confidence >= 55.0:
                r.entry_order_type = "DIRECT_NEXT_OPEN"
                r.proposed_limit_price = r.ma20  # watch MA20 as trigger
                return DIRECT_ENTRY, "ma20_pullback", confidence
            else:
                # Still worth watching but not confident enough for immediate entry
                r.entry_order_type = "CONFIRMED_NEXT_OPEN"
                r.proposed_limit_price = r.ma20
                r.invalidation_price = (r.ma60 * (1.0 - STOP_BUFFER)) if r.ma60 else r.stop_price
                return WAIT_MA20_PULLBACK, "ma20_pullback_wait", confidence

        # ── MA60 support entry ─────────────────────────────────────────────────
        if in_ma60_zone:
            rcs.append(RC_MA60_SUPPORT_ZONE)
            confidence = 35.0

            # Require MA60 not falling
            if r.ma60_trend == "falling":
                rcs.append(RC_MA60_NOT_RISING)
                return NO_ENTRY, "ma60_support_ma60_falling", 10.0

            if r.ma60_trend == "rising":
                confidence += 20.0
            elif r.ma60_trend == "flat":
                confidence += 10.0

            # Volume contraction near MA60 = healthy test
            if r.vol_contraction_in_pullback:
                rcs.append(RC_VOL_CONTRACTING)
                confidence += 15.0

            if market_regime == "bull":
                confidence += 10.0
                rcs.append(RC_BULL_REGIME_ENTRY)
            elif market_regime == "bear":
                confidence -= 15.0
                rcs.append(RC_BEAR_REGIME_CAUTION)

            rcs.append(RC_MARKET_REGIME_ADAPTED)

            if r.rr_ratio is not None:
                if r.rr_ratio >= MIN_RR_RATIO:
                    rcs.append(RC_RR_FAVORABLE)
                    confidence += 10.0
                else:
                    rcs.append(RC_RR_UNFAVORABLE)
                    confidence -= 10.0

            confidence = round(min(max(confidence, 0.0), 100.0), 1)

            r.proposed_limit_price = r.ma60
            r.invalidation_price = (
                r.ma60 * (1.0 - STOP_BUFFER * 2) if r.ma60 else r.stop_price
            )
            if confidence >= 50.0:
                r.entry_order_type = "DIRECT_NEXT_OPEN"
                return DIRECT_ENTRY, "ma60_support", confidence
            else:
                r.entry_order_type = "CONFIRMED_NEXT_OPEN"
                return WAIT_MA60_SUPPORT, "ma60_support_wait", confidence

        # ── Price above MA20 zone but not at resistance: wait for pullback ──────
        if r.ma20_gap_pct is not None and r.ma20_gap_pct > params["ma20_zone_upper"]:
            rcs.append(RC_NO_VALID_SETUP)
            r.proposed_limit_price = (
                r.ma20 * (1.0 + params["ma20_zone_upper"] / 100.0) if r.ma20 else None
            )
            return WAIT_MA20_PULLBACK, "wait_pullback_above_zone", 25.0

        # ── Default ────────────────────────────────────────────────────────────
        rcs.append(RC_NO_VALID_SETUP)
        return NO_ENTRY, "no_setup", 10.0


# ── Utility functions ─────────────────────────────────────────────────────────

def _compute_ma_slope(close: np.ndarray, ma_period: int, slope_bars: int) -> float:
    """
    Compute percentage change in moving average over the last slope_bars bars.

    Uses (MA_now - MA_n_bars_ago) / MA_n_bars_ago × 100.

    No look-ahead: MA_now = mean(close[-ma_period:]), MA_prev uses bars
    entirely before the current MA window.
    """
    n = len(close)
    if n < ma_period + slope_bars:
        return 0.0
    ma_now = float(np.mean(close[-ma_period:]))
    # Slide window back by slope_bars
    prev_start = n - ma_period - slope_bars
    prev_end = n - slope_bars
    ma_prev = float(np.mean(close[prev_start:prev_end]))
    if ma_prev <= 0:
        return 0.0
    return round((ma_now - ma_prev) / ma_prev * 100.0, 4)


def _classify_slope(slope_pct: float) -> str:
    """Classify slope into trend label (consistent with effectiveness_analyzer)."""
    if slope_pct > MA20_RISING_THRESHOLD:
        return "rising"
    if slope_pct < MA20_FALLING_THRESHOLD:
        return "falling"
    return "flat"
