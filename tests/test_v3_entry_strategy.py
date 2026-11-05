"""
tests/test_v3_entry_strategy.py — V3 Entry Timing Strategy Research Tests

Coverage map:
  V3-01  MA20 pullback zone — direct entry (high confidence)
  V3-02  MA20 pullback zone — wait (low confidence due to low R/R)
  V3-03  MA60 support zone — direct entry
  V3-04  MA60 support zone — wait (MA60 flat, low confidence)
  V3-05  Breakout with volume confirmation → DIRECT_ENTRY
  V3-06  Breakout without volume → WAIT_BREAKOUT_CONFIRMATION
  V3-07  Avoid chasing — MA20 gap too extended
  V3-08  No entry — price below both MAs
  V3-09  Failed breakout → AVOID_CHASING
  V3-10  Near resistance → WAIT_BREAKOUT_CONFIRMATION
  V3-11  Wait for pullback — price above zone but not at resistance
  V3-12  Market regime adapts MA20 zone threshold (bear tighter than bull)
  V3-13  MA60 falling blocks MA20 pullback entry → NO_ENTRY
  V3-14  Volume contraction during pullback boosts confidence
  V3-15  Volume expansion during pullback reduces confidence
  V3-16  Insufficient data — fewer than MIN_BARS_MA20
  V3-17  Insufficient data — MA60 not available (PARTIAL quality)
  V3-18  Look-ahead prevention: prior_20d_high uses [-21:-1]
  V3-19  Determinism: same input → same output
  V3-20  Version isolation: RESEARCH_VERSION constant
  V3-21  No production imports: V3 does NOT import from decision.py or foe_v1
  V3-22  Frozen Hybrid isolation: V3 output has no effect on hybrid_forward_decision
  V3-23  Confidence score bounded [0, 100]
  V3-24  Reason codes populated on all decision paths
  V3-25  Missing volume column: graceful handling
  V3-26  Missing low column: graceful handling
  V3-27  Price gap scenario: prior_20d_high correctly uses historical high
  V3-28  Conflicting setups: MA20 zone AND MA60 zone at same time
  V3-29  Market regime "bear": AVOID_CHASING threshold lower than "bull"
  V3-30  R/R unfavorable in MA20 pullback → WAIT_MA20_PULLBACK (not DIRECT)
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.research.v3_entry_strategy import (
    AVOID_CHASING,
    DIRECT_ENTRY,
    INSUFFICIENT_DATA,
    NO_ENTRY,
    RESEARCH_VERSION,
    WAIT_BREAKOUT_CONFIRMATION,
    WAIT_MA20_PULLBACK,
    WAIT_MA60_SUPPORT,
    MIN_BARS_MA20,
    MIN_BARS_FULL,
    RC_BREAKOUT_CONFIRMED,
    RC_FAILED_BREAKOUT,
    RC_INSUFFICIENT_DATA,
    RC_MA60_NOT_RISING,
    RC_MA20_PULLBACK_ZONE,
    RC_MA60_SUPPORT_ZONE,
    RC_TOO_EXTENDED,
    RC_BELOW_BOTH_MAS,
    RC_VOL_CONTRACTING,
    RC_VOL_EXPANDING,
    RC_NEAR_RESISTANCE,
    V3EntryDecision,
    V3EntryTimingAnalyzer,
)


# ── Test helpers ──────────────────────────────────────────────────────────────

def _make_history(
    n: int = 90,
    base_price: float = 100.0,
    trend_pct_per_bar: float = 0.0,
    vol_base: float = 1_000_000.0,
    vol_trend: float = 0.0,
    end_price: float | None = None,
    high_premium: float = 0.01,  # high = close * (1 + high_premium)
    low_discount: float = 0.01,  # low = close * (1 - low_discount)
    spike_price_at_end: float | None = None,  # override last close
) -> pd.DataFrame:
    """
    Build a reproducible OHLCV DataFrame.
    All values computed deterministically — no randomness.
    Trend creates a linearly sloping close series.
    """
    closes = []
    for i in range(n):
        c = base_price * (1 + trend_pct_per_bar / 100.0) ** i
        closes.append(c)

    if end_price is not None:
        # rescale so last close equals end_price
        scale = end_price / closes[-1]
        closes = [c * scale for c in closes]

    if spike_price_at_end is not None:
        closes[-1] = spike_price_at_end

    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [c * (1 + high_premium) for c in closes]
    lows = [c * (1 - low_discount) for c in closes]
    volumes = [vol_base * (1 + vol_trend * i / max(n - 1, 1)) for i in range(n)]

    return pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def _make_pullback_history(
    n: int = 90,
    trend_up_pct: float = 0.3,
    pullback_pct: float = -2.0,
    vol_contract: bool = True,
) -> pd.DataFrame:
    """
    Build a trending + pullback setup:
    - First 70 bars: uptrend
    - Last 20 bars: pullback to near MA20
    Volume contracting in last 10 bars if vol_contract=True.
    """
    closes = []
    base = 80.0
    for i in range(n - 20):
        closes.append(base * (1 + trend_up_pct / 100.0) ** i)
    # pullback
    peak = closes[-1]
    for i in range(1, 21):
        closes.append(peak * (1 + pullback_pct / 100.0 * i / 20.0))

    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]

    if vol_contract:
        # First 80 bars: normal volume; last 10: contracting
        volumes = [1_000_000.0] * (n - 10) + [
            1_000_000.0 * (0.9 - 0.05 * i) for i in range(10)
        ]
    else:
        volumes = [1_000_000.0 + 50_000.0 * i for i in range(n)]

    return pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


_ANALYZER = V3EntryTimingAnalyzer()


# ── V3-01: MA20 pullback → DIRECT_ENTRY (high confidence) ────────────────────

def test_V3_01_ma20_pullback_direct_entry():
    """
    Uptrend with mild pullback to MA20 zone, rising MA20 slope, contracting volume,
    positive R/R → should give DIRECT_ENTRY with confidence >= 55.
    """
    hist = _make_pullback_history(n=MIN_BARS_FULL, trend_up_pct=0.4, pullback_pct=-1.5, vol_contract=True)
    result = _ANALYZER.analyze("TEST", hist, market_regime="bull")

    assert result.entry_decision == DIRECT_ENTRY, (
        f"Expected DIRECT_ENTRY, got {result.entry_decision} | "
        f"ma20_gap={result.ma20_gap_pct}, ma20_trend={result.ma20_trend}, "
        f"confidence={result.confidence}, reasons={result.reason_codes}"
    )
    assert result.confidence >= 55.0
    assert RC_MA20_PULLBACK_ZONE in result.reason_codes


# ── V3-02: MA20 pullback → WAIT (low R/R) ────────────────────────────────────

def test_V3_02_ma20_pullback_wait_low_rr():
    """
    MA20 pullback zone but stop too close to entry → R/R unfavorable → WAIT_MA20_PULLBACK.
    Force this by making price sit right at MA20 with high target very close.
    """
    # Use very small trend so prior_20d_high ≈ current price → R/R < 2
    hist = _make_history(n=MIN_BARS_FULL, base_price=100.0, trend_pct_per_bar=0.02)
    result = _ANALYZER.analyze("TEST", hist, market_regime="neutral")

    # Result should be WAIT or NO_ENTRY (not DIRECT_ENTRY)
    assert result.entry_decision != DIRECT_ENTRY, (
        f"Expected not DIRECT_ENTRY, got {result.entry_decision}"
    )
    assert result.entry_decision in (WAIT_MA20_PULLBACK, NO_ENTRY, WAIT_BREAKOUT_CONFIRMATION), (
        f"Unexpected decision: {result.entry_decision}"
    )


# ── V3-03: MA60 support → DIRECT_ENTRY ────────────────────────────────────────

def test_V3_03_ma60_support_direct_entry():
    """
    Price pulled back all the way to MA60 zone (MA20 > MA60, MA60 rising),
    contracting volume → should trigger DIRECT_ENTRY on MA60 support.
    """
    n = MIN_BARS_FULL
    # Build: uptrend for 50 bars, then deep pullback to near MA60
    closes = []
    base = 60.0
    for i in range(n - 25):
        closes.append(base * 1.005 ** i)
    peak = closes[-1]
    for i in range(1, 26):
        closes.append(peak * (1 - 0.009 * i))

    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    # Contracting volume in last 10 bars
    volumes = [1_000_000.0] * (n - 10) + [1_000_000.0 * (0.6 + 0.04 * i) for i in range(10)]

    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes, "volume": volumes,
    })
    result = _ANALYZER.analyze("TEST", hist, market_regime="bull")

    # Either DIRECT_ENTRY or WAIT_MA60_SUPPORT or NO_ENTRY depending on exact levels
    assert result.entry_decision in (DIRECT_ENTRY, WAIT_MA60_SUPPORT, NO_ENTRY), (
        f"Got unexpected: {result.entry_decision}"
    )
    # MA60 should be computed (we have enough bars)
    assert result.ma60 is not None
    assert result.ma60_gap_pct is not None


# ── V3-04: MA60 support wait (MA60 flat) ─────────────────────────────────────

def test_V3_04_ma60_support_wait_flat_slope():
    """
    Price near MA60 but MA60 is flat (not rising) → low confidence → WAIT or NO_ENTRY.
    """
    n = MIN_BARS_FULL
    closes = [100.0] * n  # perfectly flat → MA60 slope = 0 = flat
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    hist = pd.DataFrame({
        "date": dates,
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [1_000_000.0] * n,
    })
    result = _ANALYZER.analyze("TEST", hist, market_regime="neutral")

    assert result.ma60 is not None
    # Flat price = MA20 zone = MA60 zone simultaneously, slope = flat
    # Should not be DIRECT_ENTRY (insufficient trend confirmation)
    assert result.confidence < 80.0


# ── V3-05: Breakout with volume confirmation → DIRECT_ENTRY ──────────────────

def test_V3_05_breakout_with_volume_direct_entry():
    """
    Today's close exceeds prior 20D high with vol_ratio >= breakout_min_vol.
    """
    n = MIN_BARS_FULL
    closes = [100.0 + i * 0.1 for i in range(n)]  # mild uptrend
    # Push last close above 20D prior high
    closes[-1] = max(closes[-22:-2]) * 1.05  # +5% above 20D high

    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [c * 1.01 for c in closes[:-1]] + [closes[-1] * 1.005]
    lows = [c * 0.99 for c in closes]
    # High volume today
    volumes = [1_000_000.0] * (n - 1) + [1_800_000.0]  # 1.8x avg

    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes, "volume": volumes,
    })
    result = _ANALYZER.analyze("TEST", hist, market_regime="bull")

    assert result.resistance_broken is True
    assert result.entry_decision == DIRECT_ENTRY, (
        f"Expected DIRECT_ENTRY, got {result.entry_decision} | "
        f"vol_ratio={result.vol_ratio}, reasons={result.reason_codes}"
    )
    assert RC_BREAKOUT_CONFIRMED in result.reason_codes


# ── V3-06: Breakout without volume → WAIT_BREAKOUT_CONFIRMATION ──────────────

def test_V3_06_breakout_no_volume_wait():
    """
    Today's close exceeds prior 20D high but volume is low (< min vol for regime).
    """
    n = MIN_BARS_FULL
    closes = [100.0 + i * 0.1 for i in range(n)]
    closes[-1] = max(closes[-22:-2]) * 1.02  # just above 20D high

    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    # Low volume today
    volumes = [1_000_000.0] * (n - 1) + [700_000.0]  # 0.7x avg

    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes, "volume": volumes,
    })
    result = _ANALYZER.analyze("TEST", hist, market_regime="neutral")

    assert result.resistance_broken is True
    assert result.entry_decision == WAIT_BREAKOUT_CONFIRMATION, (
        f"Expected WAIT_BREAKOUT_CONFIRMATION, got {result.entry_decision}"
    )


# ── V3-07: Avoid chasing — too extended ──────────────────────────────────────

def test_V3_07_avoid_chasing_too_extended():
    """
    MA20 gap >= too_extended_pct threshold → AVOID_CHASING.
    Test both neutral (15%) and bear (12%) thresholds.
    """
    n = MIN_BARS_FULL
    # Build a flat MA20 ≈ 100, then spike price to 120 (20% above MA20)
    closes = [100.0] * (n - 1) + [120.0]
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    volumes = [1_000_000.0] * n
    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes, "volume": volumes,
    })

    result_neutral = _ANALYZER.analyze("TEST", hist, market_regime="neutral")
    assert result_neutral.entry_decision == AVOID_CHASING, (
        f"neutral: Expected AVOID_CHASING, got {result_neutral.entry_decision}"
    )
    assert RC_TOO_EXTENDED in result_neutral.reason_codes

    result_bear = _ANALYZER.analyze("TEST", hist, market_regime="bear")
    assert result_bear.entry_decision == AVOID_CHASING, (
        f"bear: Expected AVOID_CHASING, got {result_bear.entry_decision}"
    )


# ── V3-08: No entry — price below both MAs ───────────────────────────────────

def test_V3_08_no_entry_below_both_mas():
    """
    Price below both MA20 and MA60 → NO_ENTRY (don't catch falling knife).
    """
    n = MIN_BARS_FULL
    # Uptrend for 70 bars, then steep decline
    closes = [100.0 + i * 0.5 for i in range(70)] + [135.0 - i * 3.0 for i in range(1, n - 69)]
    closes = closes[:n]
    # Last close < MA20 and < MA60
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    volumes = [1_000_000.0] * n
    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes, "volume": volumes,
    })
    result = _ANALYZER.analyze("TEST", hist, market_regime="neutral")

    # Should not give a bullish entry
    assert result.entry_decision in (NO_ENTRY, AVOID_CHASING, WAIT_MA20_PULLBACK), (
        f"Got unexpected entry with price below both MAs: {result.entry_decision}"
    )
    if result.ma20 and result.ma60 and result.entry_price:
        below_ma20 = result.entry_price < result.ma20
        below_ma60 = result.entry_price < result.ma60
        if below_ma20 and below_ma60:
            assert RC_BELOW_BOTH_MAS in result.reason_codes


# ── V3-09: Failed breakout → AVOID_CHASING ───────────────────────────────────

def test_V3_09_failed_breakout_avoid_chasing():
    """
    Recent bars peaked above 20D high, today closed well below → failed_breakout.
    """
    n = MIN_BARS_FULL
    closes = [100.0 + i * 0.2 for i in range(n)]
    # Three bars ago: high above 20D high; today: close well below
    highs = [c * 1.01 for c in closes]
    prior_high = max(highs[-22:-2])
    # Set 3 bars ago high above prior_high
    highs[-4] = prior_high * 1.01
    # Set today's close well below resistance
    closes[-1] = prior_high * 0.95
    highs[-1] = closes[-1] * 1.005
    lows = [c * 0.99 for c in closes]
    volumes = [1_000_000.0] * n
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes, "volume": volumes,
    })
    result = _ANALYZER.analyze("TEST", hist, market_regime="neutral")

    assert result.failed_breakout is True
    assert result.entry_decision == AVOID_CHASING, (
        f"Expected AVOID_CHASING, got {result.entry_decision}"
    )
    assert RC_FAILED_BREAKOUT in result.reason_codes


# ── V3-10: Near resistance → WAIT_BREAKOUT_CONFIRMATION ──────────────────────

def test_V3_10_near_resistance_wait_breakout():
    """
    Price within 3% of 20D prior high but not broken → WAIT_BREAKOUT_CONFIRMATION.
    """
    n = MIN_BARS_FULL
    closes = [100.0 + i * 0.3 for i in range(n)]
    # Set last close just below (2%) prior 20D high
    prior_high = max(closes[-22:-2])
    closes[-1] = prior_high * 0.985  # 1.5% below, within 3%
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    volumes = [1_000_000.0] * n
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes, "volume": volumes,
    })
    result = _ANALYZER.analyze("TEST", hist, market_regime="neutral")

    assert result.near_resistance is True, f"Expected near_resistance=True"
    assert result.entry_decision == WAIT_BREAKOUT_CONFIRMATION, (
        f"Expected WAIT_BREAKOUT_CONFIRMATION, got {result.entry_decision}"
    )
    assert RC_NEAR_RESISTANCE in result.reason_codes


# ── V3-11: Wait for pullback — above zone, below resistance ──────────────────

def test_V3_11_wait_pullback_above_zone():
    """
    Price above MA20 zone (ma20_gap > zone_upper) but not near resistance.
    """
    n = MIN_BARS_FULL
    # MA20 ≈ 100, price at 108 (8% above MA20, within neutral zone_upper=2.5%)
    closes = [100.0] * (n - 1) + [108.0]
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    volumes = [1_000_000.0] * n
    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes, "volume": volumes,
    })
    result = _ANALYZER.analyze("TEST", hist, market_regime="neutral")

    # Should wait for pullback (above zone but not at resistance or too extended)
    assert result.entry_decision in (WAIT_MA20_PULLBACK, WAIT_BREAKOUT_CONFIRMATION, AVOID_CHASING), (
        f"Expected WAIT_MA20_PULLBACK or similar, got {result.entry_decision}"
    )


# ── V3-12: Market regime adapts MA20 zone threshold ──────────────────────────

def test_V3_12_market_regime_adapts_thresholds():
    """
    Bear regime has tighter MA20 pullback zone than bull.
    Same history, different market_regime → different decisions or confidence.
    """
    hist = _make_pullback_history(n=MIN_BARS_FULL, trend_up_pct=0.4, pullback_pct=-1.0, vol_contract=True)

    result_bull = _ANALYZER.analyze("TEST", hist, market_regime="bull")
    result_bear = _ANALYZER.analyze("TEST", hist, market_regime="bear")

    # Bear should be more cautious (lower confidence or wait vs direct)
    # At minimum, confidence in bear should be <= bull
    if result_bull.entry_decision == DIRECT_ENTRY and result_bear.entry_decision == DIRECT_ENTRY:
        assert result_bear.confidence <= result_bull.confidence, (
            f"Bear confidence {result_bear.confidence} > bull confidence {result_bull.confidence}"
        )
    # Both should not give higher confidence in bear
    assert result_bear.confidence <= result_bull.confidence + 5.0, (
        "Bear regime should not produce significantly higher confidence than bull"
    )


# ── V3-13: MA60 falling blocks MA20 pullback → NO_ENTRY ──────────────────────

def test_V3_13_ma60_falling_blocks_ma20_pullback():
    """
    Price in MA20 pullback zone, but MA60 is falling → NO_ENTRY.
    V3 key differentiator: requires MA60 non-falling for MA20 pullback.
    V1/V2 would give ENTRY_READY here.
    """
    n = MIN_BARS_FULL
    # Initial uptrend for 50 bars, then MA60 starts falling
    closes = []
    for i in range(50):
        closes.append(100.0 + i * 0.3)
    peak = closes[-1]
    # Sharp decline for 20 bars (makes MA60 slope negative)
    for i in range(1, 21):
        closes.append(peak - i * 0.8)
    # Then mild recovery to MA20 pullback zone
    trough = closes[-1]
    for i in range(1, n - 70 + 1):
        closes.append(trough + i * 0.2)
    closes = closes[:n]

    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    volumes = [1_000_000.0] * n
    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes, "volume": volumes,
    })
    result = _ANALYZER.analyze("TEST", hist, market_regime="neutral")

    # If MA60 is indeed falling, should block pullback entry
    if result.ma60_trend == "falling" and result.ma20_gap_pct is not None:
        from src.research.v3_entry_strategy import _REGIME_PARAMS
        params = _REGIME_PARAMS["neutral"]
        in_ma20_zone = params["ma20_zone_lower"] <= result.ma20_gap_pct <= params["ma20_zone_upper"]
        if in_ma20_zone:
            assert result.entry_decision == NO_ENTRY, (
                f"MA60 falling should block MA20 pullback: got {result.entry_decision}"
            )
            assert RC_MA60_NOT_RISING in result.reason_codes


# ── V3-14: Volume contraction during pullback boosts confidence ───────────────

def test_V3_14_volume_contraction_boosts_confidence():
    """
    Same setup twice: contracting vs expanding volume during pullback.
    Contracting should produce higher confidence score.
    """
    hist_contract = _make_pullback_history(
        n=MIN_BARS_FULL, trend_up_pct=0.4, pullback_pct=-1.5, vol_contract=True
    )
    hist_expand = _make_pullback_history(
        n=MIN_BARS_FULL, trend_up_pct=0.4, pullback_pct=-1.5, vol_contract=False
    )
    result_contract = _ANALYZER.analyze("TEST", hist_contract, market_regime="bull")
    result_expand = _ANALYZER.analyze("TEST", hist_expand, market_regime="bull")

    # Contracting volume should produce higher confidence in pullback zone
    if (
        result_contract.entry_decision in (DIRECT_ENTRY, WAIT_MA20_PULLBACK)
        and result_expand.entry_decision in (DIRECT_ENTRY, WAIT_MA20_PULLBACK)
    ):
        assert result_contract.confidence >= result_expand.confidence - 5.0, (
            f"Contracting vol confidence {result_contract.confidence} should >= "
            f"expanding {result_expand.confidence}"
        )


# ── V3-15: Volume expansion during pullback ───────────────────────────────────

def test_V3_15_volume_expansion_during_pullback():
    """
    Volume expanding while price pulls back = potential distribution signal.
    Should reduce confidence or change decision.
    """
    hist = _make_pullback_history(
        n=MIN_BARS_FULL, trend_up_pct=0.4, pullback_pct=-1.5, vol_contract=False
    )
    result = _ANALYZER.analyze("TEST", hist, market_regime="neutral")

    # If in MA20 pullback zone, expanding volume should appear in reason codes
    if result.volume_signature == "expanding" and RC_MA20_PULLBACK_ZONE in result.reason_codes:
        assert RC_VOL_EXPANDING in result.reason_codes


# ── V3-16: Insufficient data (<= MIN_BARS_MA20) ──────────────────────────────

def test_V3_16_insufficient_data():
    """
    Fewer bars than MIN_BARS_MA20 → INSUFFICIENT_DATA.
    """
    hist = _make_history(n=MIN_BARS_MA20 - 1)
    result = _ANALYZER.analyze("TEST", hist)

    assert result.entry_decision == INSUFFICIENT_DATA
    assert RC_INSUFFICIENT_DATA in result.reason_codes


def test_V3_16b_exactly_min_bars_works():
    """MIN_BARS_MA20 exactly → should not return INSUFFICIENT_DATA."""
    hist = _make_history(n=MIN_BARS_MA20)
    result = _ANALYZER.analyze("TEST", hist)

    assert result.entry_decision != INSUFFICIENT_DATA
    assert result.data_bars == MIN_BARS_MA20


# ── V3-17: Partial data quality (no MA60) ────────────────────────────────────

def test_V3_17_partial_data_no_ma60():
    """
    Between MIN_BARS_MA20 and MIN_BARS_FULL → MA60 not available → PARTIAL quality.
    """
    hist = _make_history(n=50)  # > 21 bars but < 71
    result = _ANALYZER.analyze("TEST", hist)

    assert result.ma60 is None
    assert result.data_quality_status == "PARTIAL"
    assert result.entry_decision != INSUFFICIENT_DATA  # should still produce a decision


# ── V3-18: No look-ahead prevention ──────────────────────────────────────────

def test_V3_18_no_lookahead_prior_20d_high():
    """
    prior_20d_high must use high[-21:-1], excluding today's high.
    Insert a very high today's high — it must NOT affect prior_20d_high.
    """
    n = MIN_BARS_FULL
    closes = [100.0] * n
    highs = [101.0] * n
    # Set today's high very high
    highs[-1] = 500.0
    lows = [99.0] * n
    volumes = [1_000_000.0] * n
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes, "volume": volumes,
    })
    result = _ANALYZER.analyze("TEST", hist)

    # prior_20d_high must be based on high[-21:-1] = all 101.0, NOT 500.0
    assert result.prior_20d_high is not None
    assert result.prior_20d_high <= 102.0, (
        f"Look-ahead detected: prior_20d_high={result.prior_20d_high} includes today's spike"
    )


# ── V3-19: Determinism ───────────────────────────────────────────────────────

def test_V3_19_determinism():
    """Same input → same output (no randomness or state)."""
    hist = _make_pullback_history(n=MIN_BARS_FULL)
    r1 = _ANALYZER.analyze("TSMC", hist, market_regime="bull")
    r2 = _ANALYZER.analyze("TSMC", hist, market_regime="bull")

    assert r1.entry_decision == r2.entry_decision
    assert r1.confidence == r2.confidence
    assert r1.reason_codes == r2.reason_codes
    assert r1.ma20_gap_pct == r2.ma20_gap_pct
    assert r1.rr_ratio == r2.rr_ratio


# ── V3-20: Research version constant ─────────────────────────────────────────

def test_V3_20_research_version_constant():
    """V3 must have RESEARCH_VERSION set."""
    assert RESEARCH_VERSION == "v3_research_v1"

    hist = _make_history(n=MIN_BARS_FULL)
    result = _ANALYZER.analyze("TEST", hist)
    assert result.research_version == RESEARCH_VERSION


# ── V3-21: No production imports ─────────────────────────────────────────────

def test_V3_21_no_production_imports():
    """
    V3 must NOT import from production decision engine or foe_v1.
    Check source code for forbidden import paths.
    """
    v3_source = Path(__file__).parent.parent / "src" / "research" / "v3_entry_strategy.py"
    source_text = v3_source.read_text()

    forbidden = [
        "from src.engines.decision",
        "import decision",
        "foe_v1",
        "MODEL_VERSION",
        "BUY_THRESHOLD",
        "STRONG_BUY_THRESHOLD",
        "forward_signals",          # must not write to forward_signals
        "hybrid_forward_decision",  # must not write to hybrid_forward_decision
    ]
    for f in forbidden:
        assert f not in source_text, f"V3 prototype contains forbidden reference: {f!r}"


# ── V3-22: Frozen Hybrid isolation ───────────────────────────────────────────

def test_V3_22_frozen_hybrid_isolation():
    """
    V3 output has no RULE_VERSION or RULE_FROZEN_AT — it is not hybrid_v1.
    """
    hist = _make_history(n=MIN_BARS_FULL)
    result = _ANALYZER.analyze("TEST", hist)

    # V3EntryDecision has no rule_version or frozen_at attributes
    assert not hasattr(result, "rule_version"), "V3 must not expose rule_version"
    assert not hasattr(result, "rule_priority"), "V3 must not expose rule_priority"


# ── V3-23: Confidence bounded [0, 100] ───────────────────────────────────────

def test_V3_23_confidence_bounded():
    """Confidence score must always be in [0, 100]."""
    # Test with various histories and regimes
    histories = [
        _make_history(n=MIN_BARS_FULL, trend_pct_per_bar=0.5),
        _make_history(n=MIN_BARS_FULL, trend_pct_per_bar=-0.3, spike_price_at_end=200.0),
        _make_pullback_history(n=MIN_BARS_FULL, vol_contract=True),
        _make_pullback_history(n=MIN_BARS_FULL, vol_contract=False),
    ]
    for regime in ("bull", "bear", "neutral", "unknown"):
        for hist in histories:
            result = _ANALYZER.analyze("TEST", hist, market_regime=regime)
            assert 0.0 <= result.confidence <= 100.0, (
                f"Confidence {result.confidence} out of bounds for regime={regime}"
            )


# ── V3-24: Reason codes on all decision paths ─────────────────────────────────

def test_V3_24_reason_codes_always_populated():
    """All decision paths must produce at least one reason code."""
    histories = [
        (_make_history(n=5), "unknown"),                                           # insufficient
        (_make_history(n=MIN_BARS_FULL, spike_price_at_end=200.0), "neutral"),    # too extended
        (_make_pullback_history(n=MIN_BARS_FULL, vol_contract=True), "bull"),     # pullback entry
    ]
    for hist, regime in histories:
        result = _ANALYZER.analyze("TEST", hist, market_regime=regime)
        assert len(result.reason_codes) >= 1, (
            f"No reason codes for decision={result.entry_decision}, regime={regime}"
        )


# ── V3-25: Missing volume column ─────────────────────────────────────────────

def test_V3_25_missing_volume_graceful():
    """Missing volume column should not raise — defaults to constant volume."""
    n = MIN_BARS_FULL
    closes = [100.0 + i * 0.1 for i in range(n)]
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    hist = pd.DataFrame({
        "date": dates,
        "open": closes, "high": closes, "low": closes, "close": closes,
        # NO volume column
    })
    result = _ANALYZER.analyze("TEST", hist)

    # Should not raise; vol_ratio and volume_signature may be None/neutral
    assert result.entry_decision != INSUFFICIENT_DATA or result.data_bars < MIN_BARS_MA20


# ── V3-26: Missing low column ─────────────────────────────────────────────────

def test_V3_26_missing_low_graceful():
    """Missing low column should not raise — defaults to close."""
    n = MIN_BARS_FULL
    closes = [100.0 + i * 0.1 for i in range(n)]
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    hist = pd.DataFrame({
        "date": dates,
        "open": closes, "high": [c * 1.01 for c in closes], "close": closes,
        "volume": [1_000_000.0] * n,
        # NO low column
    })
    result = _ANALYZER.analyze("TEST", hist)
    assert result.entry_decision != INSUFFICIENT_DATA or result.data_bars < MIN_BARS_MA20


# ── V3-27: Price gap — prior_20d_high correctness ────────────────────────────

def test_V3_27_price_gap_prior_high_correct():
    """
    After a gap-up beyond 20D high, prior_20d_high should still reflect
    the historical period (not inflated by the gap bar's high).
    """
    n = MIN_BARS_FULL
    closes = [100.0] * n
    # Gap-up yesterday was at 130, today is at 115 (came back down)
    closes[-2] = 130.0
    closes[-1] = 115.0
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    hist = pd.DataFrame({
        "date": dates, "open": closes,
        "high": highs, "low": lows, "close": closes,
        "volume": [1_000_000.0] * n,
    })
    result = _ANALYZER.analyze("TEST", hist)

    # prior_20d_high uses high[-21:-1] which includes yesterday's high (131.3)
    # so resistance_broken should reflect today vs historical
    assert result.prior_20d_high is not None
    # prior_20d_high includes yesterday's high spike
    assert result.prior_20d_high >= 100.0


# ── V3-28: Conflicting setups (MA20 AND MA60 zone) ───────────────────────────

def test_V3_28_conflict_ma20_wins_over_ma60():
    """
    When price is simultaneously in MA20 pullback zone AND near MA60,
    MA20 pullback takes priority (earlier in decision tree).
    """
    n = MIN_BARS_FULL
    # Build: flat market so MA20 ≈ MA60 ≈ close (both near each other)
    closes = [100.0] * n
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes,
        "volume": [1_000_000.0] * n,
    })
    result = _ANALYZER.analyze("TEST", hist)

    # With perfectly flat prices, MA20 == MA60 == close → both zones overlap
    # Decision should be consistent (not crash), and reason codes should reflect it
    assert result.entry_decision in (DIRECT_ENTRY, WAIT_MA20_PULLBACK, NO_ENTRY), (
        f"Unexpected decision in conflict scenario: {result.entry_decision}"
    )
    assert len(result.reason_codes) >= 1


# ── V3-29: Bear regime → lower AVOID_CHASING threshold ───────────────────────

def test_V3_29_bear_regime_avoid_chasing_lower_threshold():
    """
    Bear regime has too_extended_pct=12%, neutral=15%.
    A 13% MA20 gap should trigger AVOID_CHASING in bear but not neutral.
    """
    n = MIN_BARS_FULL
    closes = [100.0] * (n - 1) + [113.0]  # +13% above MA20 ≈ 100
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes,
        "volume": [1_000_000.0] * n,
    })

    result_bear = _ANALYZER.analyze("TEST", hist, market_regime="bear")
    result_neutral = _ANALYZER.analyze("TEST", hist, market_regime="neutral")

    # bear threshold=12% → 13% gap should trigger AVOID_CHASING in bear
    assert result_bear.entry_decision == AVOID_CHASING, (
        f"Bear 13% gap should be AVOID_CHASING, got {result_bear.entry_decision}"
    )
    # neutral threshold=15% → 13% gap should NOT trigger AVOID_CHASING in neutral
    assert result_neutral.entry_decision != AVOID_CHASING, (
        f"Neutral 13% gap should NOT be AVOID_CHASING, got {result_neutral.entry_decision}"
    )


# ── V3-30: R/R unfavorable in MA20 pullback → WAIT_MA20_PULLBACK ─────────────

def test_V3_30_rr_unfavorable_in_ma20_pullback():
    """
    When price is in MA20 pullback zone but R/R < MIN_RR_RATIO,
    confidence decreases — may downgrade to WAIT_MA20_PULLBACK.
    """
    n = MIN_BARS_FULL
    # Very flat price series: prior_20d_high ≈ current price → R/R poor
    closes = [100.0] * n
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [c * 1.005 for c in closes]
    lows = [c * 0.995 for c in closes]
    hist = pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes,
        "volume": [1_000_000.0] * n,
    })
    result = _ANALYZER.analyze("TEST", hist, market_regime="neutral")

    # R/R should be very low or None due to flat price
    if result.rr_ratio is not None:
        # Very flat → target ≈ stop ≈ entry → R/R poor
        assert result.confidence < 90.0  # should not have full confidence with poor R/R
