"""
test_market_sentiment.py — analyze_market_sentiment() 與市場情緒卡片解析測試

覆蓋：
  - 正常行情（漲家多 / 跌家多 / 中性）
  - 空資料 / API 失敗
  - change_pct 欄缺失
  - change_pct 全為 NaN（資料庫未填寫）
  - 低覆蓋率 NaN（< 10%）
  - index_change_pct fallback
  - 非交易日（data_available=False）
  - parse_market_summary：N/A 漲跌家數 → 無 key，UI 顯示 "—"
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analyzers.market_behavior import analyze_market_sentiment

TRADE_DATE = date(2026, 11, 1)


# ── 工具函數 ──────────────────────────────────────────────────


def _make_prices(n: int, up_pct: float, trade_date=TRADE_DATE) -> pd.DataFrame:
    """建立 n 筆測試股價，up_pct 為上漲比例（0.0–1.0）。"""
    n_up = int(n * up_pct)
    n_down = n - n_up
    rows = []
    for i in range(n_up):
        rows.append(
            {
                "stock_id": f"UP{i:04d}",
                "date": trade_date,
                "close": 100.0,
                "change_pct": 2.0,
            }
        )
    for i in range(n_down):
        rows.append(
            {
                "stock_id": f"DN{i:04d}",
                "date": trade_date,
                "close": 100.0,
                "change_pct": -1.5,
            }
        )
    return pd.DataFrame(rows)


def _make_prices_with_nan(
    n: int, nan_pct: float, trade_date=TRADE_DATE
) -> pd.DataFrame:
    """n 筆股價，nan_pct 比例的 change_pct 為 NaN（剩餘全為上漲）。"""
    rows = []
    for i in range(n):
        cp = None if (i / n) < nan_pct else 1.5
        rows.append(
            {
                "stock_id": f"S{i:04d}",
                "date": trade_date,
                "close": 100.0,
                "change_pct": cp,
            }
        )
    return pd.DataFrame(rows)


# ── 正常行情 ──────────────────────────────────────────────────


class TestNormalBreadthData:
    def test_bullish_majority(self):
        df = _make_prices(1000, up_pct=0.65)
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert result["sentiment"] == "Bullish"
        assert result["data_available"] is True
        assert result["up_count"] == 650
        assert result["down_count"] == 350
        assert result["sentiment_basis"] == "breadth"

    def test_bearish_minority(self):
        df = _make_prices(1000, up_pct=0.35)
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert result["sentiment"] == "Bearish"
        assert result["data_available"] is True
        assert result["up_count"] == 350
        assert result["down_count"] == 650

    def test_neutral_middle(self):
        df = _make_prices(1000, up_pct=0.50)
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert result["sentiment"] == "Neutral"
        assert result["data_available"] is True

    def test_exact_60pct_boundary_bullish(self):
        df = _make_prices(1000, up_pct=0.60)
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert result["sentiment"] == "Bullish"

    def test_exact_40pct_boundary_bearish(self):
        df = _make_prices(1000, up_pct=0.40)
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert result["sentiment"] == "Bearish"

    def test_up_ratio_field(self):
        df = _make_prices(1000, up_pct=0.70)
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert abs(result["up_ratio"] - 0.70) < 0.01

    def test_data_coverage_100pct(self):
        df = _make_prices(1000, up_pct=0.60)
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert result["data_coverage_pct"] == pytest.approx(100.0, abs=0.1)


# ── 空資料 / 資料缺失 ─────────────────────────────────────────


class TestMissingData:
    def test_empty_dataframe_returns_neutral(self):
        result = analyze_market_sentiment(pd.DataFrame(), TRADE_DATE)
        assert result["sentiment"] == "Neutral"
        assert result["data_available"] is False
        assert result["up_count"] is None
        assert result["down_count"] is None

    def test_none_dataframe_returns_neutral(self):
        result = analyze_market_sentiment(None, TRADE_DATE)
        assert result["sentiment"] == "Neutral"
        assert result["data_available"] is False

    def test_no_change_pct_column(self):
        df = pd.DataFrame(
            [
                {"stock_id": "0001", "date": TRADE_DATE, "close": 100.0}
                for _ in range(500)
            ]
        )
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert result["data_available"] is False
        assert result["up_count"] is None
        assert result["down_count"] is None
        # 缺少資料時不得回傳 Bearish
        assert result["sentiment"] != "Bearish"

    def test_all_nan_change_pct_not_bearish(self):
        """Bug regression：所有 change_pct 為 NaN 時不得回傳 Bearish。"""
        df = pd.DataFrame(
            [
                {
                    "stock_id": f"S{i:04d}",
                    "date": TRADE_DATE,
                    "close": 100.0,
                    "change_pct": None,
                }
                for i in range(1000)
            ]
        )
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert result["data_available"] is False
        assert result["up_count"] is None
        assert result["down_count"] is None
        assert result["sentiment"] != "Bearish", "全 NaN change_pct 不應判定 Bearish"

    def test_low_coverage_nan_not_bearish(self):
        """只有 5% 有效 change_pct（< 10% 門檻）→ data_available=False。"""
        df = _make_prices_with_nan(1000, nan_pct=0.95)
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert result["data_available"] is False
        assert result["sentiment"] != "Bearish"

    def test_sufficient_coverage_computes_normally(self):
        """10%+ 有效 change_pct → 正常計算。"""
        df = _make_prices_with_nan(1000, nan_pct=0.80)
        # 20% valid，全為上漲 → Bullish
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert result["data_available"] is True
        assert result["sentiment"] == "Bullish"

    def test_data_coverage_pct_field(self):
        df = _make_prices_with_nan(1000, nan_pct=0.70)  # 30% valid
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert result["data_coverage_pct"] == pytest.approx(30.0, abs=1.0)

    def test_zero_up_zero_down_not_returned_when_all_nan(self):
        """迴歸：所有 NaN 時 up_count 應為 None，不是 0。"""
        df = pd.DataFrame(
            [
                {
                    "stock_id": f"S{i}",
                    "date": TRADE_DATE,
                    "close": 100.0,
                    "change_pct": float("nan"),
                }
                for i in range(500)
            ]
        )
        result = analyze_market_sentiment(df, TRADE_DATE)
        assert result["up_count"] is None
        assert result["down_count"] is None


# ── index_change_pct fallback ─────────────────────────────────


class TestIndexFallback:
    def _no_breadth_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "stock_id": f"S{i}",
                    "date": TRADE_DATE,
                    "close": 100.0,
                    "change_pct": None,
                }
                for i in range(500)
            ]
        )

    def test_index_up_gives_bullish(self):
        result = analyze_market_sentiment(
            self._no_breadth_df(), TRADE_DATE, index_change_pct=1.5
        )
        assert result["sentiment"] == "Bullish"
        assert result["sentiment_basis"] == "index"
        assert result["data_available"] is False

    def test_index_down_gives_bearish(self):
        result = analyze_market_sentiment(
            self._no_breadth_df(), TRADE_DATE, index_change_pct=-1.2
        )
        assert result["sentiment"] == "Bearish"
        assert result["sentiment_basis"] == "index"

    def test_index_flat_gives_neutral(self):
        result = analyze_market_sentiment(
            self._no_breadth_df(), TRADE_DATE, index_change_pct=0.3
        )
        assert result["sentiment"] == "Neutral"
        assert result["sentiment_basis"] == "index"

    def test_index_exactly_1pct_bullish_boundary(self):
        result = analyze_market_sentiment(
            self._no_breadth_df(), TRADE_DATE, index_change_pct=1.0
        )
        assert result["sentiment"] == "Bullish"

    def test_index_exactly_neg1pct_bearish_boundary(self):
        result = analyze_market_sentiment(
            self._no_breadth_df(), TRADE_DATE, index_change_pct=-1.0
        )
        assert result["sentiment"] == "Bearish"

    def test_no_breadth_no_index_gives_neutral(self):
        result = analyze_market_sentiment(self._no_breadth_df(), TRADE_DATE)
        assert result["sentiment"] == "Neutral"
        assert result["sentiment_basis"] == "none"

    def test_breadth_takes_priority_over_index(self):
        """有完整 breadth 資料時，index fallback 不影響結果。"""
        df = _make_prices(1000, up_pct=0.65)
        result = analyze_market_sentiment(df, TRADE_DATE, index_change_pct=-5.0)
        # 有 breadth → 用 breadth（Bullish），不用 index
        assert result["sentiment"] == "Bullish"
        assert result["sentiment_basis"] == "breadth"

    def test_summary_mentions_index_fallback(self):
        result = analyze_market_sentiment(
            self._no_breadth_df(), TRADE_DATE, index_change_pct=2.0
        )
        assert "加權指數" in result["summary"] or "index" in result["summary"].lower()

    def test_invalid_index_pct_handled_gracefully(self):
        result = analyze_market_sentiment(
            self._no_breadth_df(), TRADE_DATE, index_change_pct="bad_value"
        )
        # 無效值 → 無 fallback，應回傳 Neutral
        assert result["sentiment"] == "Neutral"
        assert result["data_available"] is False


# ── parse_market_summary: N/A 與 0 的區分 ─────────────────────


class TestParseMarketSummaryBreadth:
    def test_na_up_count_no_key_in_result(self):
        """report 有 N/A → 無 'up' key → UI 顯示 '—'（迴歸修正驗證）。"""
        from dashboard.loaders import parse_market_summary

        report = "| 上漲家數 | N/A |\n| 下跌家數 | N/A |"
        result = parse_market_summary(report)
        assert "up" not in result, "N/A 不應被解析為數字 key"
        assert "down" not in result

    def test_zero_up_count_still_matches_regex(self):
        """真正的 0 仍可被 regex 解析（向下相容）。"""
        from dashboard.loaders import parse_market_summary

        report = "| 上漲家數 | 0 |\n| 下跌家數 | 100 |"
        result = parse_market_summary(report)
        assert result.get("up") == "0"
        assert result.get("down") == "100"

    def test_valid_counts_parsed(self):
        from dashboard.loaders import parse_market_summary

        report = "| 上漲家數 | 750 |\n| 下跌家數 | 420 |"
        result = parse_market_summary(report)
        assert result["up"] == "750"
        assert result["down"] == "420"

    def test_sentiment_note_in_report_still_parsed(self):
        """情緒行有備注文字時仍可解析 Bullish/Neutral/Bearish。"""
        from dashboard.loaders import parse_market_summary

        report = "| 市場情緒 | ➡️ Neutral（漲跌家數不可用，情緒無法判斷，顯示中性） |"
        result = parse_market_summary(report)
        assert result.get("sentiment") == "Neutral"

    def test_index_fallback_sentiment_parsed(self):
        from dashboard.loaders import parse_market_summary

        report = "| 市場情緒 | 📈 Bullish（以加權指數漲跌幅推估） |"
        result = parse_market_summary(report)
        assert result.get("sentiment") == "Bullish"


# ── 非交易日（資料過期）─────────────────────────────────────


class TestStaleData:
    def test_stale_date_still_computes(self):
        """即使 trade_date 與 df 日期不同，仍嘗試使用全部資料。"""
        df = _make_prices(500, up_pct=0.65, trade_date=date(2026, 10, 30))
        # 傳入不同的 trade_date → 無 date filter 匹配，fallback 用全資料
        result = analyze_market_sentiment(df, date(2026, 11, 1))
        # 無匹配 date 時 fallback 至全部資料
        assert result["data_available"] is True
        assert result["sentiment"] == "Bullish"

    def test_all_data_for_different_date_used_as_fallback(self):
        """所有行的 date 都是另一天 → day_data 為空 → fallback 到全部資料。"""
        df = pd.DataFrame(
            [
                {
                    "stock_id": f"S{i}",
                    "date": date(2026, 10, 30),
                    "close": 100.0,
                    "change_pct": 1.5,
                }
                for i in range(500)
            ]
        )
        result = analyze_market_sentiment(df, date(2026, 11, 3))
        # fallback to all data
        assert result["total_count"] == 500
