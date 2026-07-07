# Developer Guide

如何在平台上新增 Collector / Analyzer / Dashboard 頁面。所有範例以真實程式碼為基準。

---

## 1. 新增 Collector

**目標**：從新資料來源抓取資料並存入 DB。

### Step 1 — 建立 Collector 類別

參考 `PriceCollector`（`src/collectors/price_collector.py`）。

```python
# src/collectors/my_collector.py
import logging
from datetime import date
from typing import Optional
import pandas as pd
import requests

from src.collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class MyCollector(BaseCollector):
    name = "my_source"          # CollectResult.source 顯示的名稱

    def collect(self, trade_date: Optional[date] = None, **kwargs):
        resp = requests.get("https://api.example.com/data", timeout=10)
        if resp.status_code != 200:     # 注意：用 status_code，不用 resp.ok
            return []
        return resp.json()

    def validate(self, data) -> tuple:
        if not data:
            return False, "empty response"
        return True, "ok"

    def parse(self, data) -> pd.DataFrame:
        df = pd.DataFrame(data)
        df["stock_id"] = df["Code"].astype(str).str.strip()
        df["date"] = trade_date or date.today()
        return df[["stock_id", "date", "value"]]

    def save(self, df: pd.DataFrame, session) -> int:
        from src.database import MyData
        n = 0
        for _, row in df.iterrows():
            exists = session.query(MyData).filter_by(
                stock_id=row["stock_id"], date=row["date"]
            ).first()
            if not exists:
                session.add(MyData(
                    stock_id=row["stock_id"],
                    date=row["date"],
                    value=row.get("value"),
                ))
                n += 1
        session.commit()
        return n

    # run() 繼承自 BaseCollector，自動 wrap 成 CollectResult
```

### Step 2 — 新增 ORM Model（需要新表時）

```python
# src/database.py — 在現有 class 之後新增
class MyData(Base):
    __tablename__ = "my_data"
    __table_args__ = (UniqueConstraint("stock_id", "date"),)

    id       = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), nullable=False)
    date     = Column(Date, nullable=False)
    value    = Column(Float)
```

### Step 3 — Export

```python
# src/collectors/__init__.py
from src.collectors.my_collector import MyCollector

__all__ = [..., "MyCollector"]
```

### Step 4 — 加入 main.py

```python
# main.py — 在 run_daily() 的收集步驟加入
result = MyCollector().run(trade_date, session)
if result.is_error:
    logger.error(f"[{result.source}] {result.message}")
elif result.is_warning:
    logger.warning(result.message)
else:
    logger.info(f"my_source: {result.n_rows} rows saved")
```

---

## 2. 新增 Analyzer

**目標**：為股票計算新的評分維度。

參考 `TechnicalAnalyzer`（`src/analyzers/technical.py`）和 `FundamentalAnalyzer`（`src/analyzers/fundamental.py`）。

### Step 1 — 建立 Analyzer 類別

```python
# src/analyzers/my_analyzer.py
import logging
logger = logging.getLogger(__name__)


class MyAnalyzer:
    def analyze(self, stock_id: str, data: dict) -> dict:
        """
        回傳 score（0–100）和細節 dict。
        若資料不足，回傳 score=0，不要 raise。
        """
        if not data:
            return {"my_score": 0, "my_detail": {}}
        score = self._calc_score(data)
        return {
            "my_score": min(100, max(0, score)),
            "my_detail": {"input": data, "computed": score},
        }

    def _calc_score(self, data: dict) -> float:
        # 計算邏輯，回傳 0–100
        value = data.get("value", 0) or 0
        if value >= 20:
            return 100
        elif value >= 10:
            return 70
        return 40
```

### Step 2 — 整合到 decision.py

```python
# src/engines/decision.py
from src.analyzers.my_analyzer import MyAnalyzer

_my_analyzer = MyAnalyzer()

# 在 _analyze_single() 函數內新增：
my_result = _my_analyzer.analyze(stock_id, my_data)
my_score = my_result.get("my_score", 0)
```

### Step 3 — 調整 SCORE_WEIGHTS（如需改變權重分配）

```python
# config.py
SCORE_WEIGHTS = {
    "quality":       0.35,   # 原 0.40，騰出空間
    "timing":        0.25,
    "behavior":      0.20,
    "my_dimension":  0.10,   # 新增
    "intelligence":  0.05,
    "risk":          0.05,
}
```

---

## 3. 新增 Dashboard 頁面

**目標**：在 Streamlit 加入新的功能頁。

參考 `dashboard/pages/data_health.py`（最近新增，結構最整潔）。

### Step 1 — 建立頁面模組

```python
# dashboard/pages/my_page.py
import logging
import streamlit as st
from dashboard.loaders import load_my_data

logger = logging.getLogger(__name__)


def page_my_feature() -> None:
    st.subheader("我的功能")
    st.caption("說明文字")

    df = load_my_data()
    if df.empty:
        st.info("尚無資料")
        return

    st.dataframe(df, use_container_width=True)
```

### Step 2 — 加入快取 Loader

所有 DB 查詢都放在 `dashboard/loaders.py`，套 `@st.cache_data`。TTL 參考：
- 日資料（分析結果、推薦）→ `ttl=1800`（30 分鐘）
- 即時價格 → `ttl=300`（5 分鐘）
- 靜態對照表（股票名稱）→ `ttl=86400`（24 小時）

```python
# dashboard/loaders.py
@st.cache_data(ttl=1800)
def load_my_data() -> pd.DataFrame:
    try:
        from src.database import MyData, get_session
        s = get_session()
        rows = s.query(MyData).order_by(MyData.date.desc()).limit(100).all()
        s.close()
        return pd.DataFrame([{"stock_id": r.stock_id, "value": r.value} for r in rows])
    except Exception as e:
        logger.warning(f"load_my_data failed: {e}")
        return pd.DataFrame()
```

### Step 3 — 掛載到 app.py

```python
# dashboard/app.py
from dashboard.pages.my_page import page_my_feature

tabs = st.tabs([
    "📊今日", "🔍個股", "📋歷史", "📈模型持倉",
    "🔬模型驗證", "💼我的交易", "🩺資料健康",
    "🆕我的功能",   # ← 新增
    "📖說明", "⚙️設定",
])

with tabs[7]:       # ← index 對應上面的位置
    page_my_feature()
```

---

## 4. 撰寫測試

測試檔放在 `tests/`，命名規則 `test_<模組名>.py`。

### Collector 測試模板

參考 `tests/test_price_collector.py`。

```python
# tests/test_my_collector.py
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.collectors.my_collector import MyCollector


class TestMyCollectorValidate:
    def test_empty_list_fails(self):
        ok, msg = MyCollector().validate([])
        assert not ok
        assert "empty" in msg.lower()

    def test_valid_data_passes(self):
        ok, _ = MyCollector().validate([{"Code": "2330", "value": 10}])
        assert ok


class TestMyCollectorParse:
    def test_returns_dataframe(self):
        df = MyCollector().parse([{"Code": "2330", "value": 10}])
        assert isinstance(df, pd.DataFrame)
        assert "stock_id" in df.columns
        assert "value" in df.columns

    def test_strips_stock_id(self):
        df = MyCollector().parse([{"Code": " 2330 ", "value": 10}])
        assert df["stock_id"].iloc[0] == "2330"


class TestMyCollectorRun:
    def test_collect_error_returns_error_result(self):
        c = MyCollector()
        with patch.object(c, "collect", side_effect=ConnectionError("timeout")):
            result = c.run()
        assert result.is_error
        assert "collect failed" in result.message
        assert result.source == "my_source"
```

### Analyzer 測試模板

參考 `tests/test_score.py`，重點是**純計算邏輯，不依賴 DB 或 API**。

```python
# tests/test_my_analyzer.py
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.analyzers.my_analyzer import MyAnalyzer


class TestMyAnalyzer:
    def setup_method(self):
        self.analyzer = MyAnalyzer()

    def test_returns_score_key(self):
        result = self.analyzer.analyze("2330", {"value": 15})
        assert "my_score" in result

    def test_score_in_range(self):
        result = self.analyzer.analyze("2330", {"value": 15})
        assert 0 <= result["my_score"] <= 100

    def test_empty_data_returns_zero(self):
        result = self.analyzer.analyze("2330", {})
        assert result["my_score"] == 0

    def test_high_value_gets_full_score(self):
        result = self.analyzer.analyze("2330", {"value": 25})
        assert result["my_score"] == 100
```

### 執行測試

```bash
pytest tests/ -q                        # 全套快跑
pytest tests/test_my_collector.py -v   # 只跑新增的
pytest --cov=src/collectors --cov-report=term-missing  # 覆蓋率
```

---

## 提交前 Checklist

```
□ 語法：python3 -c "import ast; ast.parse(open('src/collectors/my_collector.py').read())"
□ 格式：black src/ dashboard/ tests/ config.py
□ Import 排序：isort src/ dashboard/ tests/ config.py
□ Lint：ruff check src/ dashboard/ tests/ config.py
□ 全套測試通過：pytest tests/ -q
□ 覆蓋率不低於 75%：pytest --cov=src/analyzers --cov=src/collectors --cov-fail-under=75
□ __init__.py 已 export 新類別
□ DeveloperGuide.md 已更新（如有新 pattern）
```

---

## 完整鏈路速查

```
新資料來源（API / 爬蟲）
  │
  ▼  src/collectors/my_collector.py
  │  MyCollector(BaseCollector)
  │  collect / validate / parse / save
  │  run() → CollectResult（error 自動 wrap，不影響其他 collector）
  ▼
src/database.py — MyData ORM model → DB table
  │
  ▼  src/analyzers/my_analyzer.py
  │  MyAnalyzer.analyze() → {my_score: 0–100, my_detail: {...}}
  ▼
src/engines/decision.py — 整合進 StockRecommendation
  │
  ▼  DB：analysis_results / recommendations
  │
  ▼  dashboard/loaders.py
  │  load_my_data()（@st.cache_data ttl=1800）
  ▼
dashboard/pages/my_page.py → page_my_feature()
dashboard/app.py → 新 tab
```

## 常見錯誤

| 症狀 | 原因 | 解法 |
|---|---|---|
| `ruff F401` import unused | 新增 import 後沒用到 | 刪掉，或確認使用 |
| `black` 改了你的格式 | 行太長或引號 | 讓 black 自動修正，不要手動 |
| Coverage 掉到 75% 以下 | 新程式碼沒有測試 | 補 validate / parse 的 test |
| `CollectResult` 工廠參數錯 | `.success()` 需要 `n_rows: int` | 參考 `src/core/result.py` 定義 |
| Streamlit `st.cache_data` 緩存舊資料 | TTL 未到期 | 點「重新整理」或 `st.cache_data.clear()` |
