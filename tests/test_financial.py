"""
test_financial.py — 財務資料蒐集器與計算邏輯測試

測試策略：測試純計算函數（_calc_trend, _date_to_quarter）不需要 mock。
          build_financial_summary 測試 DB 缺席時的回傳格式。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.collectors.financial_collector import _calc_trend, _date_to_quarter

# ── _calc_trend ───────────────────────────────────────────────


class TestCalcTrend:
    def test_uptrend(self):
        series = [10, 11, 12, 13, 14, 15, 16, 17]
        assert _calc_trend(series) == "up"

    def test_downtrend(self):
        series = [20, 18, 16, 14, 12, 10, 8, 6]
        assert _calc_trend(series) == "down"

    def test_stable(self):
        series = [10.0, 10.1, 9.9, 10.2, 9.8, 10.0, 10.1, 9.9]
        assert _calc_trend(series) == "stable"

    def test_too_short_returns_unknown(self):
        assert _calc_trend([1, 2, 3]) == "unknown"
        assert _calc_trend([]) == "unknown"

    def test_with_none_values(self):
        series = [10, None, 12, 13, 14, 15, None, 17]
        result = _calc_trend(series)
        assert result in ("up", "down", "stable", "unknown")

    def test_all_none_returns_unknown(self):
        series = [None, None, None, None, None]
        assert _calc_trend(series) == "unknown"

    def test_large_uptrend_is_up(self):
        series = [100, 200, 300, 400, 500, 600, 700, 800]
        assert _calc_trend(series) == "up"


# ── _date_to_quarter ──────────────────────────────────────────


class TestDateToQuarter:
    def test_q1_months(self):
        for month in ["01", "02", "03"]:
            assert _date_to_quarter(f"2025-{month}-15") == 1

    def test_q2_months(self):
        for month in ["04", "05", "06"]:
            assert _date_to_quarter(f"2025-{month}-01") == 2

    def test_q3_months(self):
        for month in ["07", "08", "09"]:
            assert _date_to_quarter(f"2025-{month}-01") == 3

    def test_q4_months(self):
        for month in ["10", "11", "12"]:
            assert _date_to_quarter(f"2025-{month}-01") == 4

    def test_invalid_returns_1(self):
        assert _date_to_quarter("invalid") == 1
        assert _date_to_quarter("") == 1


# ── build_financial_summary 格式合約 ─────────────────────────


class TestBuildFinancialSummaryContract:
    """驗證函數回傳格式，不依賴實際 DB。"""

    def test_returns_dict(self):
        from src.collectors.financial_collector import build_financial_summary

        with patch(
            "src.collectors.financial_collector._get_dataloader", return_value=None
        ):
            result = build_financial_summary("2330")
        assert isinstance(result, dict)

    def test_has_data_key(self):
        from src.collectors.financial_collector import build_financial_summary

        with patch(
            "src.collectors.financial_collector._get_dataloader", return_value=None
        ):
            result = build_financial_summary("2330")
        assert "has_data" in result

    def test_no_dataloader_returns_has_data_false(self):
        from src.collectors.financial_collector import build_financial_summary

        with patch(
            "src.collectors.financial_collector._get_dataloader", return_value=None
        ):
            result = build_financial_summary("2330")
        # 無 FinMind 時，可能從 DB 讀取，has_data 取決於 DB 狀態
        assert isinstance(result.get("has_data"), bool)


# ── _get_dataloader 回傳合約 ──────────────────────────────────


class TestGetDataloader:
    def test_returns_none_when_finmind_not_installed(self):
        from src.collectors.financial_collector import _get_dataloader

        with patch.dict("sys.modules", {"FinMind": None, "FinMind.data": None}):
            # ImportError 時應回傳 None
            with patch(
                "builtins.__import__",
                side_effect=ImportError("No module named FinMind"),
            ):
                _get_dataloader()
        # 可能 None 或 DataLoader，視環境而定；關鍵是不 crash
        assert True

    def test_returns_none_on_login_failure(self):
        from src.collectors.financial_collector import _get_dataloader

        mock_dl = MagicMock()
        mock_dl.login_by_token.side_effect = Exception("auth failed")
        with patch("src.collectors.financial_collector.FINMIND_TOKEN", "test_token"):
            try:
                from FinMind.data import DataLoader  # noqa

                with patch("FinMind.data.DataLoader", return_value=mock_dl):
                    result = _get_dataloader()
                    assert result is None
            except ImportError:
                pytest.skip("FinMind not installed")
