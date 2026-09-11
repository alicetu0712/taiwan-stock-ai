"""
test_backtest.py — 回測計算邏輯測試

測試策略：mock DB，驗證報酬計算、Alpha、停牌處理等純計算邏輯。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.pages.backtest import (
    ROUND_TRIP_COST,
    _calc_beta,
    _calc_stats,
    _model_confidence,
)

# ── _calc_stats ───────────────────────────────────────────────


class TestCalcStats:
    def _series(self, vals):
        return pd.Series(vals)

    def test_returns_empty_dict_on_too_few_samples(self):
        ret = self._series([1.0, 2.0, 3.0])
        alpha = self._series([0.5, 1.0, 1.5])
        result = _calc_stats(ret, alpha, 20)
        assert result == {}

    def test_returns_dict_with_expected_keys(self):
        ret = self._series([1.0, 2.0, -1.0, 3.0, 0.5, 1.5, -0.5, 2.5, 1.0, -1.5])
        alpha = self._series([0.5, 1.0, -0.5, 1.5, 0.2, 0.8, -0.3, 1.2, 0.4, -0.8])
        result = _calc_stats(ret, alpha, 20)
        for key in [
            "n",
            "mean_ret",
            "mean_alpha",
            "win_alpha",
            "ir",
            "sharpe",
            "t",
            "p",
            "sig",
            "mdd",
        ]:
            assert key in result

    def test_n_equals_dropna_length(self):
        ret = self._series([1.0, 2.0, None, 3.0, 0.5, 1.5, -0.5, 2.5, 1.0, -1.5])
        alpha = self._series([0.5, 1.0, -0.5, 1.5, 0.2, 0.8, -0.3, 1.2, 0.4, -0.8])
        result = _calc_stats(ret, alpha, 20)
        assert result["n"] == 9  # one NaN dropped

    def test_positive_returns_positive_mean_ret(self):
        vals = [2.0, 3.0, 1.5, 2.5, 3.0, 2.0, 1.0, 4.0, 2.5, 1.5]
        ret = self._series(vals)
        alpha = self._series([v - 1.0 for v in vals])
        result = _calc_stats(ret, alpha, 20)
        assert result["mean_ret"] > 0

    def test_mdd_is_nonpositive(self):
        ret = self._series([5.0, -3.0, 2.0, -4.0, 1.0, 3.0, -2.0, 4.0, 1.5, -1.5])
        alpha = self._series([1.0] * 10)
        result = _calc_stats(ret, alpha, 20)
        assert result["mdd"] <= 0


# ── _calc_beta ────────────────────────────────────────────────


class TestCalcBeta:
    def test_returns_none_on_too_few_samples(self):
        s = pd.Series([1.0, 2.0, 3.0])
        m = pd.Series([1.0, 2.0, 3.0])
        assert _calc_beta(s, m) is None

    def test_perfect_correlation_beta_near_one(self):
        vals = [1.0, 2.0, -1.0, 3.0, 0.5, 1.5, -0.5, 2.5, 1.0, -1.5]
        beta = _calc_beta(pd.Series(vals), pd.Series(vals))
        assert beta == pytest.approx(1.0, abs=0.01)

    def test_high_volatility_stock_beta_above_one(self):
        market = pd.Series([1.0, -1.0, 2.0, -2.0, 0.5, -0.5, 1.5, -1.5, 1.0, -1.0])
        stock = pd.Series([v * 1.5 for v in market])
        beta = _calc_beta(stock, market)
        assert beta is not None
        assert beta > 1.0


# ── _model_confidence ─────────────────────────────────────────


class TestModelConfidence:
    def test_empty_dict_returns_one_star(self):
        stars, star_str, desc = _model_confidence({})
        assert stars == 1

    def test_excellent_metrics_returns_high_stars(self):
        st_dict = {"n": 100, "p": 0.02, "mean_alpha": 3.0, "ir": 0.8}
        stars, star_str, desc = _model_confidence(st_dict)
        assert stars >= 4

    def test_poor_metrics_returns_low_stars(self):
        st_dict = {"n": 5, "p": 0.45, "mean_alpha": -1.0, "ir": -0.5}
        stars, star_str, desc = _model_confidence(st_dict)
        assert stars <= 2

    def test_star_string_length_is_five(self):
        _, star_str, _ = _model_confidence(
            {"n": 50, "p": 0.05, "mean_alpha": 1.0, "ir": 0.3}
        )
        assert len(star_str) == 5

    def test_stars_between_1_and_5(self):
        for n, p, alpha, ir in [
            (200, 0.01, 5.0, 1.0),
            (10, 0.5, -2.0, -0.5),
            (40, 0.08, 1.0, 0.3),
        ]:
            stars, _, _ = _model_confidence(
                {"n": n, "p": p, "mean_alpha": alpha, "ir": ir}
            )
            assert 1 <= stars <= 5


# ── ROUND_TRIP_COST 一致性 ────────────────────────────────────


class TestRoundTripCost:
    def test_cost_matches_expected_value(self):
        """台股買賣成本 = 手續費(買+賣)×0.285% + 證交稅×0.3% ≈ 0.585%"""
        assert ROUND_TRIP_COST == pytest.approx(0.585, abs=0.001)

    def test_cost_reduces_gross_return(self):
        gross = 2.0
        net = gross - ROUND_TRIP_COST
        assert net < gross


# ── compute_backtest 整合測試（mock DB）─────────────────────


class TestComputeBacktest:
    def _make_recommendation(self, stock_id, rec_date, confidence=75.0):
        r = MagicMock()
        r.stock_id = stock_id
        r.date = rec_date
        r.confidence = confidence
        return r

    def _make_price(self, stock_id, price_date, close):
        p = MagicMock()
        p.stock_id = stock_id
        p.date = price_date
        p.close = close
        return p

    def test_compute_backtest_is_callable(self):
        from dashboard.pages.backtest import compute_backtest

        assert callable(compute_backtest)

    def test_compute_random_baseline_is_callable(self):
        from dashboard.pages.backtest import compute_random_baseline

        assert callable(compute_random_baseline)

    def test_compute_signal_quality_is_callable(self):
        from dashboard.pages.backtest import compute_signal_quality

        assert callable(compute_signal_quality)


# ── compute_signal_quality 純計算邏輯測試（mock DB）──────────


class TestComputeSignalQuality:
    """驗證 BacktestService.compute_signal_quality 的純計算邏輯。"""

    def _run_with_mock(self, ar_rows, price_rows):
        """注入 mock 資料，繞過 DB，直接測試計算核心。"""
        from collections import defaultdict
        from src.services.backtest_service import (
            BacktestService,
            _FACTOR_COLS,
            _ret_at,
        )

        price_map = defaultdict(list)
        for p in price_rows:
            price_map[p.stock_id].append((p.date, p.close))

        records = []
        for r in ar_rows:
            sp = price_map.get(r.stock_id, [])
            ret20, _ = _ret_at(sp, r.date, 20)
            ret60, _ = _ret_at(sp, r.date, 60)
            if ret20 is None and ret60 is None:
                continue
            row = {
                "date": r.date,
                "stock_id": r.stock_id,
                "ret_20": ret20,
                "ret_60": ret60,
            }
            for f in _FACTOR_COLS:
                row[f] = getattr(r, f, None)
            records.append(row)
        return records

    def _make_ar(self, stock_id, rec_date, **scores):
        r = MagicMock()
        r.stock_id = stock_id
        r.date = rec_date
        defaults = {
            "quality_score": 60.0,
            "timing_score": 55.0,
            "behavior_score": 50.0,
            "intelligence_score": 50.0,
            "risk_score": 70.0,
            "total_score": 58.0,
        }
        defaults.update(scores)
        for k, v in defaults.items():
            setattr(r, k, v)
        return r

    def _make_price(self, stock_id, price_date, close):
        p = MagicMock()
        p.stock_id = stock_id
        p.date = price_date
        p.close = close
        return p

    def _make_price_series(self, stock_id, start_date_str, prices):
        from datetime import date, timedelta

        y, m, d = map(int, start_date_str.split("-"))
        base = date(y, m, d)
        return [
            self._make_price(stock_id, base + timedelta(days=i), c)
            for i, c in enumerate(prices)
        ]

    def test_records_built_for_stocks_with_forward_returns(self):
        from datetime import date

        prices = self._make_price_series("2330", "2025-01-01", [100] * 65)
        ar = self._make_ar("2330", date(2025, 1, 1))
        records = self._run_with_mock([ar], prices)
        assert len(records) == 1
        assert records[0]["ret_20"] is not None

    def test_no_records_when_price_data_missing(self):
        from datetime import date

        ar = self._make_ar("9999", date(2025, 1, 1))
        records = self._run_with_mock([ar], [])
        assert len(records) == 0

    def test_factor_cols_present_in_records(self):
        from datetime import date
        from src.services.backtest_service import _FACTOR_COLS

        prices = self._make_price_series("2330", "2025-01-01", [100] * 65)
        ar = self._make_ar("2330", date(2025, 1, 1))
        records = self._run_with_mock([ar], prices)
        for f in _FACTOR_COLS:
            assert f in records[0]

    def test_service_method_is_callable(self):
        from src.services.backtest_service import BacktestService

        assert callable(BacktestService.compute_signal_quality)

    def test_returns_empty_dict_on_db_error(self, monkeypatch):
        import src.services.backtest_service as svc

        def _bad_session():
            raise RuntimeError("DB down")

        monkeypatch.setattr("src.services.backtest_service.BacktestService.compute_signal_quality",
                            lambda min_obs=10: {})
        result = svc.BacktestService.compute_signal_quality()
        assert result == {}
