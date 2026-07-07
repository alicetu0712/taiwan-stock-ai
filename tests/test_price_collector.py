"""
test_price_collector.py — 股價蒐集器單元測試

測試策略：mock 外部 HTTP，只測試解析邏輯與資料轉換。
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.collectors.price_collector import (
    _fetch_yahoo_one,
    _parse_roc_date,
)

# ── _parse_roc_date ───────────────────────────────────────────


class TestParseRocDate:
    def test_standard_format(self):
        # 民國日期格式為 7 位數字 "YYYMMDD"，民國 114 年 = 西元 2025 年
        assert _parse_roc_date("1140701") == date(2025, 7, 1)

    def test_year_adds_1911(self):
        d = _parse_roc_date("1100115")
        assert d == date(2021, 1, 15)

    def test_invalid_returns_none(self):
        assert _parse_roc_date("invalid") is None
        assert _parse_roc_date("") is None
        assert _parse_roc_date(None) is None

    def test_slash_format_returns_none(self):
        # "114/07/01" 不是預期格式，應回傳 None
        assert _parse_roc_date("114/07/01") is None

    def test_two_digit_month_day(self):
        d = _parse_roc_date("1131231")
        assert d == date(2024, 12, 31)


# ── _fetch_yahoo_one ──────────────────────────────────────────


class TestFetchYahooOne:
    def _make_yahoo_response(self, close=100.0, volume=10000):
        return {
            "chart": {
                "result": [
                    {
                        "meta": {"regularMarketPrice": close},
                        "timestamp": [1700000000],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [close * 0.99],
                                    "high": [close * 1.01],
                                    "low": [close * 0.98],
                                    "close": [close],
                                    "volume": [volume],
                                }
                            ],
                            "adjclose": [{"adjclose": [close]}],
                        },
                    }
                ],
                "error": None,
            }
        }

    @patch("src.collectors.price_collector.requests.get")
    def test_returns_dict_with_close(self, mock_get):
        # _fetch_yahoo_one 判斷 status_code != 200，需設定 status_code
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: self._make_yahoo_response(close=500.0),
        )
        result = _fetch_yahoo_one("2330.TW", date(2025, 7, 1))
        assert result is not None
        assert "close" in result
        assert result["close"] == pytest.approx(500.0)

    @patch("src.collectors.price_collector.requests.get")
    def test_returns_none_on_http_error(self, mock_get):
        mock_get.return_value = MagicMock(status_code=503)
        result = _fetch_yahoo_one("9999.TW", date(2025, 7, 1))
        assert result is None

    @patch("src.collectors.price_collector.requests.get")
    def test_returns_none_on_empty_result(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"chart": {"result": None, "error": "Not found"}},
        )
        result = _fetch_yahoo_one("0000.TW", date(2025, 7, 1))
        assert result is None

    @patch("src.collectors.price_collector.requests.get")
    def test_network_exception_returns_none(self, mock_get):
        mock_get.side_effect = Exception("connection refused")
        result = _fetch_yahoo_one("2330.TW", date(2025, 7, 1))
        assert result is None


# ── fetch_twse_daily 基本合約 ─────────────────────────────────


class TestFetchTwseDaily:
    """測試 TWSE 解析邏輯（mock HTTP response）"""

    def _make_twse_row(
        self, code="2330", name="台積電", close="800.00", volume="50000"
    ):
        return {
            "Code": code,
            "Name": name,
            "ClosingPrice": close,
            "TradeVolume": volume,
            "OpeningPrice": "795.00",
            "HighestPrice": "805.00",
            "LowestPrice": "790.00",
        }

    @patch("src.collectors.price_collector.requests.get")
    def test_returns_dataframe(self, mock_get):
        from src.collectors.price_collector import fetch_twse_daily

        mock_get.return_value = MagicMock(
            ok=True,
            json=lambda: [self._make_twse_row()],
        )
        df = fetch_twse_daily(date(2025, 7, 1))
        assert isinstance(df, pd.DataFrame)

    @patch("src.collectors.price_collector.requests.get")
    def test_empty_on_api_fail(self, mock_get):
        from src.collectors.price_collector import fetch_twse_daily

        mock_get.return_value = MagicMock(ok=False)
        df = fetch_twse_daily(date(2025, 7, 1))
        assert df.empty

    @patch("src.collectors.price_collector.requests.get")
    def test_skips_non_numeric_close(self, mock_get):
        from src.collectors.price_collector import fetch_twse_daily

        rows = [
            self._make_twse_row(code="2330", close="800.00"),
            self._make_twse_row(code="9999", close="---"),  # 停牌
        ]
        mock_get.return_value = MagicMock(ok=True, json=lambda: rows)
        df = fetch_twse_daily(date(2025, 7, 1))
        if not df.empty:
            assert (
                "9999" not in df["stock_id"].values
                or df[df["stock_id"] == "9999"]["close"].isna().all()
            )
