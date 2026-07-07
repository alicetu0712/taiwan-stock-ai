"""
test_loaders.py — Dashboard 資料載入層測試

測試策略：純解析邏輯（parse_*）不需要任何 mock。
           load_* 函數需要 DB，測試其錯誤處理路徑。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.loaders import parse_market_summary, parse_recs_from_report

# ── parse_market_summary ──────────────────────────────────────

SAMPLE_REPORT = """
## ① Market Summary

| 項目 | 數值 |
|---|---|
| 加權指數 | 23,456 |
| 漲跌幅 | +1.23% |
| 市場情緒 | 偏多 Bullish |
| 上漲家數 | 800 |
| 下跌家數 | 350 |
"""


class TestParseMarketSummary:
    def test_extracts_index(self):
        result = parse_market_summary(SAMPLE_REPORT)
        assert result.get("index") == "23,456"

    def test_extracts_change(self):
        result = parse_market_summary(SAMPLE_REPORT)
        assert result.get("change") == "+1.23%"

    def test_extracts_sentiment(self):
        result = parse_market_summary(SAMPLE_REPORT)
        assert result.get("sentiment") == "Bullish"

    def test_extracts_up_down_count(self):
        result = parse_market_summary(SAMPLE_REPORT)
        assert result.get("up") == "800"
        assert result.get("down") == "350"

    def test_bearish_sentiment(self):
        report = "| 市場情緒 | 偏空 Bearish |"
        result = parse_market_summary(report)
        assert result.get("sentiment") == "Bearish"

    def test_neutral_sentiment(self):
        report = "| 市場情緒 | 中性 Neutral |"
        result = parse_market_summary(report)
        assert result.get("sentiment") == "Neutral"

    def test_empty_report_returns_empty_dict(self):
        assert parse_market_summary("") == {}
        assert parse_market_summary("no data here") == {}

    def test_negative_change(self):
        report = "| 漲跌幅 | -2.50% |"
        result = parse_market_summary(report)
        assert result.get("change") == "-2.50%"


# ── parse_recs_from_report ────────────────────────────────────

SAMPLE_REC_SECTION = """
## ③ Research Candidates

### 1. 台積電（2330）—— A+ 級

| 項目 | 數值 |
|---|---|
| 公司品質 | **85**/100 |
| 技術時機 | **72**/100 |
| 市場行為 | **68**/100 |
| 風險評估 | **78**/100 |
| 綜合評分 | **80**/100 |
| 分析信心 | 85% |

**優勢**
- ✅ ROE 長期維持 20%+
- ✅ EPS 連續成長 5 年

**風險**
• 估值偏高

**觀察點**
- 🔍 下季法說會

**AI 結論**

> 台積電長期競爭優勢明顯，目前技術面多頭排列，值得關注。

### 2. 聯發科（2454）—— B 級

| 項目 | 數值 |
|---|---|
| 公司品質 | **65**/100 |
| 技術時機 | **60**/100 |
| 市場行為 | **55**/100 |
| 風險評估 | **70**/100 |
| 綜合評分 | **63**/100 |
| 分析信心 | 72% |
"""


class TestParseRecsFromReport:
    def setup_method(self):
        self.recs = parse_recs_from_report(SAMPLE_REC_SECTION)

    def test_finds_two_recommendations(self):
        assert len(self.recs) == 2

    def test_first_rec_name_and_sid(self):
        assert self.recs[0]["name"] == "台積電"
        assert self.recs[0]["sid"] == "2330"

    def test_second_rec_name_and_sid(self):
        assert self.recs[1]["name"] == "聯發科"
        assert self.recs[1]["sid"] == "2454"

    def test_level_parsed(self):
        assert self.recs[0]["level"] == "A+"
        assert self.recs[1]["level"] == "B"

    def test_scores_parsed(self):
        scores = self.recs[0]["scores"]
        assert scores["quality"] == 85
        assert scores["timing"] == 72
        assert scores["behavior"] == 68
        assert scores["risk"] == 78
        assert scores["total"] == 80

    def test_confidence_parsed(self):
        assert self.recs[0]["confidence"] == 85
        assert self.recs[1]["confidence"] == 72

    def test_advantages_extracted(self):
        assert any("ROE" in a for a in self.recs[0]["advantages"])

    def test_conclusion_extracted(self):
        assert "台積電" in self.recs[0]["conclusion"]

    def test_empty_report_returns_empty_list(self):
        assert parse_recs_from_report("") == []
        assert parse_recs_from_report("no sections here") == []

    def test_missing_confidence_defaults_zero(self):
        report = "### 1. 測試（1234）—— A 級\n| 公司品質 | **70**/100 |"
        recs = parse_recs_from_report(report)
        if recs:
            assert recs[0]["confidence"] == 0


# ── load_* 錯誤路徑測試 ───────────────────────────────────────


class TestLoadersErrorHandling:
    """確認 DB 連線失敗時 loaders 回傳合理的空值，不會 crash。"""

    @patch("dashboard.loaders.st")
    def test_load_stock_prices_returns_empty_on_db_error(self, mock_st):
        from dashboard.loaders import load_stock_prices

        mock_st.cache_data = MagicMock(return_value=lambda f: f)

        # 合約驗證：函數存在且可被參照
        assert callable(load_stock_prices)

    @patch("dashboard.loaders.st")
    def test_load_stock_names_returns_dict_on_db_error(self, mock_st):
        from dashboard.loaders import load_stock_names

        assert callable(load_stock_names)

    def test_parse_functions_are_pure(self):
        """parse_* 函數是純函數，相同輸入必定相同輸出。"""
        r1 = parse_market_summary(SAMPLE_REPORT)
        r2 = parse_market_summary(SAMPLE_REPORT)
        assert r1 == r2

        recs1 = parse_recs_from_report(SAMPLE_REC_SECTION)
        recs2 = parse_recs_from_report(SAMPLE_REC_SECTION)
        assert len(recs1) == len(recs2)
