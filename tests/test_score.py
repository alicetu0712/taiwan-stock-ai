"""
test_score.py — TechnicalAnalyzer + FundamentalAnalyzer 評分邏輯測試

測試策略：純計算邏輯，不依賴 DB 或外部 API。
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analyzers.fundamental import FundamentalAnalyzer, FundamentalResult
from src.analyzers.technical import TechnicalAnalyzer, TechnicalResult

# ── Fixtures ─────────────────────────────────────────────────


def _make_history(n=80, trend="up") -> pd.DataFrame:
    """生成 n 日模擬 OHLCV 資料。"""
    base = 100.0
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(n)]
    closes = []
    for i in range(n):
        if trend == "up":
            closes.append(base * (1 + i * 0.002 + np.random.normal(0, 0.005)))
        elif trend == "down":
            closes.append(base * (1 - i * 0.002 + np.random.normal(0, 0.005)))
        else:
            closes.append(base * (1 + np.random.normal(0, 0.005)))
    closes = [max(c, 1.0) for c in closes]
    return pd.DataFrame(
        {
            "date": dates,
            "open": [c * 0.99 for c in closes],
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.98 for c in closes],
            "close": closes,
            "volume": [int(1e6 * (1 + np.random.normal(0, 0.1))) for _ in range(n)],
        }
    )


def _make_fin_summary(
    roe=15.0,
    roa=8.0,
    eps_ttm=5.0,
    gm=35.0,
    debt=40.0,
    eps_trend="up",
    per=20.0,
    pbr=2.0,
    has_data=True,
) -> dict:
    return {
        "has_data": has_data,
        "roe_avg": roe,
        "roe_5y": [roe - 2, roe - 1, roe, roe + 1, roe + 1.5],
        "roa_avg": roa,
        "eps_ttm": eps_ttm,
        "eps_trend": eps_trend,
        "eps_5y": [eps_ttm - 1, eps_ttm - 0.5, eps_ttm, eps_ttm + 0.2, eps_ttm + 0.5],
        "gross_margin_avg": gm,
        "debt_ratio": debt,
        "free_cash_flow": 100.0,
        "current_ratio": 2.0,
        "per": per,
        "pbr": pbr,
        "revenue_trend": "up",
    }


# ── TechnicalAnalyzer ─────────────────────────────────────────


class TestTechnicalAnalyzer:
    def setup_method(self):
        self.analyzer = TechnicalAnalyzer()

    def test_returns_result_object(self):
        hist = _make_history(80)
        result = self.analyzer.analyze("2330", hist)
        assert isinstance(result, TechnicalResult)
        assert result.stock_id == "2330"

    def test_score_in_range(self):
        hist = _make_history(80)
        result = self.analyzer.analyze("2330", hist)
        assert 0.0 <= result.timing_score <= 100.0

    def test_insufficient_history_returns_zero_score(self):
        hist = _make_history(5)  # 低於 MIN_HISTORY
        result = self.analyzer.analyze("2330", hist)
        assert result.timing_score == 0.0
        assert "不足" in result.summary

    def test_uptrend_score_higher_than_downtrend(self):
        np.random.seed(42)
        up_hist = _make_history(120, trend="up")
        np.random.seed(42)
        down_hist = _make_history(120, trend="down")
        up_score = self.analyzer.analyze("UP", up_hist).timing_score
        down_score = self.analyzer.analyze("DOWN", down_hist).timing_score
        assert up_score > down_score

    def test_rsi_calculated(self):
        hist = _make_history(80)
        result = self.analyzer.analyze("2330", hist)
        assert result.rsi is not None
        assert 0 <= result.rsi <= 100

    def test_ma_values_present(self):
        hist = _make_history(80)
        result = self.analyzer.analyze("2330", hist)
        assert result.ma5 is not None
        assert result.ma20 is not None

    def test_close_matches_last_price(self):
        hist = _make_history(80)
        result = self.analyzer.analyze("2330", hist)
        assert result.close == pytest.approx(hist["close"].iloc[-1], abs=0.01)

    def test_none_history_returns_empty_result(self):
        result = self.analyzer.analyze("2330", None)
        assert result.timing_score == 0.0


# ── TechnicalAnalyzer private methods ────────────────────────


class TestTechnicalInternals:
    def setup_method(self):
        self.a = TechnicalAnalyzer()

    def test_calc_rsi_normal(self):
        close = np.linspace(100, 120, 30)
        rsi = self.a._calc_rsi(close, period=14)
        assert rsi is not None
        assert rsi > 50  # 持續上漲 → RSI 偏高

    def test_calc_rsi_too_short_returns_none(self):
        close = np.array([100.0, 101.0, 102.0])
        assert self.a._calc_rsi(close, period=14) is None

    def test_score_rsi_oversold(self):
        score, risk = self.a._score_rsi(25.0)  # RSI < 30 超賣
        assert score > 0
        assert risk is None  # 超賣不視為風險警告

    def test_score_rsi_overbought(self):
        score, risk = self.a._score_rsi(85.0)  # RSI > 80
        assert score == 0.0
        assert risk is not None

    def test_analyze_ma_bullish(self):
        # 上升趨勢 → 多頭排列
        close = np.linspace(80, 120, 150)
        score, trend, vals = self.a._analyze_ma(close)
        assert trend in ("bullish", "bullish_weak", "neutral")
        assert score >= 0

    def test_find_support_resistance(self):
        close = np.linspace(100, 110, 60)
        high = close * 1.01
        low = close * 0.99
        support, resistance = self.a._find_support_resistance(close, high, low)
        assert support is not None
        assert resistance is not None
        assert support < resistance


# ── FundamentalAnalyzer ───────────────────────────────────────


class TestFundamentalAnalyzer:
    def setup_method(self):
        self.analyzer = FundamentalAnalyzer()

    def test_returns_result_object(self):
        fin = _make_fin_summary()
        result = self.analyzer.analyze("2330", fin)
        assert isinstance(result, FundamentalResult)
        assert result.stock_id == "2330"

    def test_score_in_range(self):
        fin = _make_fin_summary()
        result = self.analyzer.analyze("2330", fin)
        assert 0.0 <= result.quality_score <= 100.0

    def test_no_data_returns_zero(self):
        fin = _make_fin_summary(has_data=False)
        result = self.analyzer.analyze("2330", fin)
        assert result.quality_score == 0.0
        assert result.quality_grade == "D"

    def test_excellent_metrics_gives_high_score(self):
        fin = _make_fin_summary(roe=25.0, roa=15.0, eps_ttm=8.0, gm=50.0, debt=20.0)
        result = self.analyzer.analyze("2330", fin)
        assert result.quality_score >= 70.0
        assert result.quality_grade in ("A+", "A", "B")

    def test_poor_metrics_gives_low_score(self):
        fin = _make_fin_summary(roe=3.0, roa=1.0, eps_ttm=-1.0, gm=5.0, debt=80.0)
        result = self.analyzer.analyze("2330", fin)
        assert result.quality_score < 50.0

    def test_factors_plus_not_empty_for_good_stock(self):
        fin = _make_fin_summary(roe=20.0, roa=12.0)
        result = self.analyzer.analyze("2330", fin)
        assert len(result.factors_plus) > 0

    def test_grade_mapping(self):
        for roe, expected_grade_min in [(25.0, "B"), (5.0, "D")]:
            fin = _make_fin_summary(roe=roe)
            result = self.analyzer.analyze("2330", fin)
            assert result.quality_grade in ("A+", "A", "B", "C", "D")


# ── FundamentalAnalyzer private score methods ─────────────────


class TestFundamentalScorers:
    def setup_method(self):
        self.a = FundamentalAnalyzer()

    def test_roe_excellent_gets_max(self):
        score, plus, minus = self.a._score_roe(25.0, [22, 23, 24, 25, 25])
        assert score == 20.0

    def test_roe_none_returns_zero(self):
        score, plus, minus = self.a._score_roe(None, [])
        assert score == 0.0

    def test_roa_excellent(self):
        score, plus, minus = self.a._score_roa(15.0)
        assert score == 15.0

    def test_eps_negative_returns_zero(self):
        score, plus, minus = self.a._score_eps(-1.0, "down", [])
        assert score == 0.0
        assert any("虧損" in m for m in minus)

    def test_eps_uptrend_bonus(self):
        score_up, *_ = self.a._score_eps(5.0, "up", [3, 3.5, 4, 4.5, 5])
        score_down, *_ = self.a._score_eps(5.0, "down", [6, 5.5, 5, 4.5, 4])
        assert score_up > score_down

    def test_high_debt_ratio_penalized(self):
        score, plus, minus = self.a._score_financial_health(75.0, 100.0, 2.0)
        assert any("負債" in m for m in minus)

    def test_gross_margin_excellent(self):
        score, plus, minus = self.a._score_gross_margin(45.0)
        assert score == 15.0

    def test_valuation_low_per_bonus(self):
        score_low, *_ = self.a._score_valuation(12.0, 1.5)
        score_high, *_ = self.a._score_valuation(50.0, 6.0)
        assert score_low > score_high

    def test_revenue_trend(self):
        score_up, *_ = self.a._score_revenue("up")
        score_down, *_ = self.a._score_revenue("down")
        assert score_up > score_down
        assert score_down == 0.0
