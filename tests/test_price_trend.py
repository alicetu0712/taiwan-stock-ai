"""
test_price_trend.py — MA Structure 判斷優先順序與 MA60 Support Zone

驗證「specific conditions before general conditions」原則：
MA60 Support Zone 必須在一般 neutral (cur > ma20 or cur > ma60) 之前被捕捉到。
"""

import pytest
from src.analyzers.price_trend import PriceTrendAnalyzer


def _mas(ma5=None, ma10=None, ma20=None, ma60=None):
    d = {}
    if ma5  is not None: d["ma5"]  = float(ma5)
    if ma10 is not None: d["ma10"] = float(ma10)
    if ma20 is not None: d["ma20"] = float(ma20)
    if ma60 is not None: d["ma60"] = float(ma60)
    return d


class TestMA60StructureOrdering:

    def setup_method(self):
        self.az = PriceTrendAnalyzer()

    # ── Case 1 ────────────────────────────────────────────────────

    def test_case1_ma60_support_zone_identified(self):
        """
        MA20=105, Price=100, MA60=98, MA60 slope up
        → Price < MA20, MA20 > MA60, near MA60 (2.04%), MA60 rising
        → MA60 Support Zone (score=5.0), NOT generic neutral (4.0)
        """
        mas = _mas(ma5=101, ma10=102, ma20=105, ma60=98)
        score, trend = self.az._score_ma_structure(100.0, mas, ma60_slope="up")
        assert score == 5.0, f"Expected 5.0 (MA60 zone), got {score}"
        assert trend == "neutral"
        # Explicitly verify it's NOT the generic neutral score
        assert score > 4.0, "MA60 zone must score higher than generic neutral (4.0)"

    # ── Case 2 ────────────────────────────────────────────────────

    def test_case2_not_ma60_support_when_slope_down(self):
        """
        Same price position but MA60 slope down → not MA60 Support Zone.
        Falls through to generic neutral because cur > ma60.
        """
        mas = _mas(ma5=101, ma10=102, ma20=105, ma60=98)
        score, trend = self.az._score_ma_structure(100.0, mas, ma60_slope="down")
        assert score == 4.0, f"Expected 4.0 (generic neutral, slope down), got {score}"
        assert trend == "neutral"

    def test_case2_not_ma60_support_when_slope_flat(self):
        """MA60 slope flat → also not MA60 Support Zone."""
        mas = _mas(ma5=101, ma10=102, ma20=105, ma60=98)
        score, _ = self.az._score_ma_structure(100.0, mas, ma60_slope="flat")
        assert score == 4.0

    # ── Case 3 ────────────────────────────────────────────────────

    def test_case3_not_ma60_support_when_ma20_below_ma60(self):
        """
        MA20=95 < MA60=98: medium-term structure broken.
        MA60 zone condition (ma20 > ma60) fails → not MA60 Support Zone.
        cur > ma20 and cur > ma60 → bullish_weak (6.0).
        """
        mas = _mas(ma5=101, ma10=102, ma20=95, ma60=98)
        score, trend = self.az._score_ma_structure(100.0, mas, ma60_slope="up")
        assert score == 6.0, f"Expected 6.0 (bullish_weak), got {score}"
        assert trend == "bullish_weak"
        assert score != 5.0, "MA20 < MA60 must not trigger MA60 zone"

    # ── Case 4 ────────────────────────────────────────────────────

    def test_case4_not_ma60_support_when_price_far_from_ma60(self):
        """
        MA60=96, Price=100 → gap = 4.17% > 3% threshold.
        → not MA60 Support Zone, falls to generic neutral.
        """
        mas = _mas(ma5=101, ma10=102, ma20=105, ma60=96)
        score, trend = self.az._score_ma_structure(100.0, mas, ma60_slope="up")
        assert score == 4.0, f"Expected 4.0 (gap > 3%, generic neutral), got {score}"

    def test_case4_boundary_within_3pct_qualifies(self):
        """Price 2.99% above MA60 qualifies for MA60 zone."""
        # MA60=97.09 → gap=(100-97.09)/97.09*100=2.997% < 3% → should qualify
        mas = _mas(ma5=101, ma10=102, ma20=105, ma60=97.09)
        score, _ = self.az._score_ma_structure(100.0, mas, ma60_slope="up")
        assert score == 5.0, "Price within 3% of MA60 should qualify for MA60 zone"

    def test_case4_just_over_3pct_falls_to_neutral(self):
        """Price 3.1% above MA60 → falls to generic neutral."""
        ma60 = 100.0 / 1.031
        mas = _mas(ma5=101, ma10=102, ma20=105, ma60=ma60)
        score, _ = self.az._score_ma_structure(100.0, mas, ma60_slope="up")
        assert score == 4.0

    # ── Case 5 ────────────────────────────────────────────────────

    def test_case5_structure_and_setup_separation(self):
        """
        MA Structure identifies MA60 zone regardless of volume.
        _detect_setup() adds volume condition: vol_ratio > 1.0 blocks ma60_support.
        """
        mas = _mas(ma5=101, ma10=102, ma20=105, ma60=98)

        # MA Structure: MA60 zone even with high volume
        score, trend = self.az._score_ma_structure(100.0, mas, ma60_slope="up")
        assert score == 5.0, "MA Structure should be MA60 zone regardless of volume"

        # Setup: vol_ratio=1.5 violates the <= 1.0 condition in _detect_setup
        setup = self.az._detect_setup(
            cur=100.0, mas=mas,
            ma_trend="neutral", ma20_slope="down", ma60_slope="up",
            breakout_20d=False, near_20d=False,
            vol_ratio=1.5,
        )
        assert setup != "ma60_support", (
            f"vol_ratio=1.5 should block ma60_support setup, got '{setup}'"
        )

    def test_case5_low_volume_does_trigger_setup(self):
        """With vol_ratio <= 1.0, same position should become ma60_support setup."""
        mas = _mas(ma5=101, ma10=102, ma20=105, ma60=98)
        setup = self.az._detect_setup(
            cur=100.0, mas=mas,
            ma_trend="neutral", ma20_slope="down", ma60_slope="up",
            breakout_20d=False, near_20d=False,
            vol_ratio=0.7,
        )
        assert setup == "ma60_support", f"Low vol_ratio should yield ma60_support, got '{setup}'"

    # ── 一般回歸測試：確保既有路徑不受影響 ─────────────────────────

    def test_perfect_bull_unaffected(self):
        """Perfect bullish alignment still returns 12.0."""
        mas = _mas(ma5=110, ma10=108, ma20=105, ma60=100)
        score, trend = self.az._score_ma_structure(112.0, mas, ma60_slope="up")
        assert score == 12.0
        assert trend == "bullish"

    def test_breakdown_unaffected(self):
        """Perfect bearish alignment still returns 0.0."""
        mas = _mas(ma5=90, ma10=92, ma20=95, ma60=100)
        score, trend = self.az._score_ma_structure(88.0, mas, ma60_slope="down")
        assert score == 0.0
        assert trend == "bearish"

    def test_generic_neutral_when_only_above_ma60(self):
        """cur above MA60 but not near it, MA20 falling → generic neutral 4.0."""
        # cur=97, MA20=105, MA60=94 → gap=(97-94)/94*100=3.19% > 3%
        mas = _mas(ma5=98, ma10=99, ma20=105, ma60=94)
        score, trend = self.az._score_ma_structure(97.0, mas, ma60_slope="up")
        assert score == 4.0
        assert trend == "neutral"
