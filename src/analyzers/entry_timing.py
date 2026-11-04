"""
entry_timing.py — V2 Entry Timing Research Analyzer (Shadow Mode)

Separates *selecting stocks* (Trend Quality, handled by PriceTrendAnalyzer / v8.0)
from *timing the entry* (this module).

Four-step logic:
  1. Resistance State  — how far below the 20-day high?
  2. MA20 Pullback     — has price pulled back to MA20 support zone?
  3. Breakout Confirm  — has price actually broken the resistance?
  4. R/R Filter        — is the risk/reward acceptable?

FORBIDDEN: This module must NOT modify MODEL_VERSION, BUY/STRONG BUY thresholds,
ForwardSignals, ACTUAL/PAPER trade logic, or any v8.0 decisions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Entry Timing Labels ────────────────────────────────────────────────────

ENTRY_READY = "ENTRY_READY"
WAIT_FOR_PULLBACK = "WAIT_FOR_PULLBACK"
WAIT_FOR_BREAKOUT = "WAIT_FOR_BREAKOUT"
TOO_EXTENDED = "TOO_EXTENDED"
RISK_REWARD_UNFAVORABLE = "RISK_REWARD_UNFAVORABLE"
NO_VALID_SETUP = "NO_VALID_SETUP"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

ALL_LABELS = [
    ENTRY_READY,
    WAIT_FOR_PULLBACK,
    WAIT_FOR_BREAKOUT,
    TOO_EXTENDED,
    RISK_REWARD_UNFAVORABLE,
    NO_VALID_SETUP,
    INSUFFICIENT_DATA,
]

# Minimum R/R to consider a pullback entry acceptable
MIN_RR_RATIO = 2.0
# MA20 pullback zone: price within X% above MA20
MA20_PULLBACK_UPPER = 0.03   # +3% above MA20
MA20_PULLBACK_LOWER = -0.05  # -5% below MA20 (still viable if holding)
# Stop is placed 3% below MA20 (buffer)
STOP_BUFFER = 0.03
# "Too extended" threshold: MA20 gap %
TOO_EXTENDED_MA20_GAP = 15.0


@dataclass
class EntryTimingResult:
    stock_id: str

    # ── Entry label (primary output) ──────────────────────────────────────
    entry_label: str = INSUFFICIENT_DATA

    # ── Resistance state ──────────────────────────────────────────────────
    prior_20d_high: Optional[float] = None        # max(high[-21:-1]) — no look-ahead
    dist_to_resistance_pct: Optional[float] = None  # (prior_20d_high - close) / close * 100 (positive = below)
    resistance_broken: bool = False               # close > prior_20d_high

    # ── MA20 pullback state ───────────────────────────────────────────────
    ma20: Optional[float] = None
    ma20_gap_pct: Optional[float] = None          # (close - ma20) / ma20 * 100
    in_ma20_pullback_zone: bool = False

    # ── Breakout confirmation ─────────────────────────────────────────────
    breakout_volume_confirmed: bool = False       # resistance broken AND vol_ratio >= 1.0
    vol_ratio: Optional[float] = None

    # ── R/R computation ───────────────────────────────────────────────────
    entry_price: Optional[float] = None           # today's close (proxy for next-open entry)
    stop_price: Optional[float] = None            # MA20 (or MA60 fallback)
    target_price: Optional[float] = None          # prior_20d_high + (prior_20d_high - stop)
    risk: Optional[float] = None                  # entry - stop
    reward: Optional[float] = None                # target - entry
    rr_ratio: Optional[float] = None              # reward / risk

    # ── Diagnostics ───────────────────────────────────────────────────────
    reasons: List[str] = field(default_factory=list)
    data_bars: int = 0


class EntryTimingAnalyzer:
    """
    Pure-compute: takes OHLCV history, returns EntryTimingResult.
    No DB access. No side effects. Deterministic.
    """

    MIN_BARS = 21  # need prior_20d_high without look-ahead

    def analyze(self, stock_id: str, history: pd.DataFrame) -> EntryTimingResult:
        result = EntryTimingResult(stock_id=stock_id)

        if history is None or len(history) < self.MIN_BARS:
            result.entry_label = INSUFFICIENT_DATA
            result.reasons.append(
                f"歷史資料不足（{len(history) if history is not None else 0} 根，需 {self.MIN_BARS}）"
            )
            return result

        hist = history.sort_values("date").reset_index(drop=True)
        close = hist["close"].values.astype(float)
        high = hist["high"].values.astype(float) if "high" in hist.columns else close
        volume = (
            hist["volume"].values.astype(float)
            if "volume" in hist.columns
            else np.ones(len(hist))
        )

        result.data_bars = len(close)
        cur = float(close[-1])
        result.entry_price = cur

        # ── Step 1: Resistance State ──────────────────────────────────────
        # CRITICAL: [-21:-1] excludes today — no look-ahead bias
        prior_20d_high = float(np.max(high[-21:-1]))
        result.prior_20d_high = prior_20d_high
        dist_pct = (prior_20d_high - cur) / cur * 100.0
        result.dist_to_resistance_pct = round(dist_pct, 2)
        result.resistance_broken = cur > prior_20d_high

        # ── Step 2: MA20 Pullback State ───────────────────────────────────
        n = len(close)
        ma20 = float(np.mean(close[-20:])) if n >= 20 else None
        result.ma20 = ma20
        if ma20 and ma20 > 0:
            ma20_gap = (cur - ma20) / ma20 * 100.0
            result.ma20_gap_pct = round(ma20_gap, 2)
            result.in_ma20_pullback_zone = (
                MA20_PULLBACK_LOWER * 100 <= ma20_gap <= MA20_PULLBACK_UPPER * 100
            )
        else:
            result.in_ma20_pullback_zone = False

        # Too extended check (before anything else)
        if result.ma20_gap_pct is not None and result.ma20_gap_pct >= TOO_EXTENDED_MA20_GAP:
            result.entry_label = TOO_EXTENDED
            result.reasons.append(
                f"MA20 乖離 {result.ma20_gap_pct:.1f}% ≥ {TOO_EXTENDED_MA20_GAP}%，追高風險"
            )
            return result

        # ── Step 3: Breakout Confirmation ─────────────────────────────────
        vol_ma = float(np.mean(volume[-20:])) if n >= 20 else None
        vol_ratio = round(float(volume[-1]) / vol_ma, 2) if (vol_ma and vol_ma > 0) else None
        result.vol_ratio = vol_ratio
        result.breakout_volume_confirmed = (
            result.resistance_broken
            and (vol_ratio is not None and vol_ratio >= 1.0)
        )

        # ── Step 4: R/R Computation ───────────────────────────────────────
        # stop = MA20 * (1 - STOP_BUFFER) — 3% buffer below MA20
        rr_ratio = None
        if ma20 and ma20 > 0:
            stop = ma20 * (1 - STOP_BUFFER)
            result.stop_price = round(stop, 2)
            risk = cur - stop
            if risk > 0:
                if result.resistance_broken and prior_20d_high > stop:
                    # project beyond resistance by the stop→resistance distance
                    target = prior_20d_high + (prior_20d_high - stop)
                elif not result.resistance_broken:
                    # target = resistance (prior 20d high)
                    target = prior_20d_high
                else:
                    target = None
                if target is not None:
                    reward = target - cur
                    result.target_price = round(target, 2)
                    result.risk = round(risk, 4)
                    result.reward = round(reward, 4)
                    rr_ratio = round(reward / risk, 2)
                    result.rr_ratio = rr_ratio

        # ── Label Decision ────────────────────────────────────────────────
        result.entry_label = self._decide_label(result)
        return result

    def _decide_label(self, r: EntryTimingResult) -> str:
        # 1. Breakout confirmed with volume → ENTRY_READY unconditionally
        #    (R/R computed for reference but does not gate the label — breakout entries
        #     always have narrow stop/reward ratios relative to the entry premium)
        if r.resistance_broken and r.breakout_volume_confirmed:
            rr_str = f"，R/R={r.rr_ratio:.1f}" if r.rr_ratio is not None else ""
            r.reasons.append(f"放量突破前20日高點（{r.prior_20d_high}）{rr_str}")
            return ENTRY_READY

        # 2. Resistance broken but no volume confirmation → wait
        if r.resistance_broken and not r.breakout_volume_confirmed:
            r.reasons.append(
                f"突破前20日高點但量比={r.vol_ratio}（< 1.0），等放量確認"
            )
            return WAIT_FOR_BREAKOUT

        # 3. Near resistance (within 3%) without breakout — check before pullback zone
        #    so that stocks approaching resistance are correctly labelled WAIT_FOR_BREAKOUT
        if r.dist_to_resistance_pct is not None and 0 < r.dist_to_resistance_pct <= 3.0:
            r.reasons.append(
                f"距前20日高點僅 {r.dist_to_resistance_pct:.1f}%，等突破確認"
            )
            return WAIT_FOR_BREAKOUT

        # 4. In MA20 pullback zone → ENTRY_READY if R/R ≥ MIN_RR_RATIO
        if r.in_ma20_pullback_zone:
            if r.rr_ratio is not None and r.rr_ratio >= MIN_RR_RATIO:
                r.reasons.append(
                    f"MA20 拉回支撐（乖離 {r.ma20_gap_pct:.1f}%），R/R={r.rr_ratio:.1f}"
                )
                return ENTRY_READY
            elif r.rr_ratio is not None:
                r.reasons.append(
                    f"MA20 拉回帶但 R/R={r.rr_ratio:.1f} < {MIN_RR_RATIO}"
                )
                return RISK_REWARD_UNFAVORABLE
            else:
                r.reasons.append("MA20 拉回帶，但 R/R 無法計算")
                return NO_VALID_SETUP

        # 5. Price above pullback zone (3-15% above MA20), below resistance → wait for pullback
        if r.ma20_gap_pct is not None and r.ma20_gap_pct > MA20_PULLBACK_UPPER * 100:
            r.reasons.append(
                f"MA20 乖離 {r.ma20_gap_pct:.1f}%，尚未拉回（> +{MA20_PULLBACK_UPPER*100:.0f}%），等回踩"
            )
            return WAIT_FOR_PULLBACK

        # 6. Default
        r.reasons.append("無明確進場型態")
        return NO_VALID_SETUP
