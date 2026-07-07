# Collector

資料蒐集層設計。每個 Collector 繼承 `BaseCollector`，透過統一管道完成抓取→驗證→解析→儲存。

## BaseCollector 介面

定義於 `src/collectors/base.py`：

```python
class BaseCollector(ABC):
    name: str = "base"

    def collect(self, trade_date=None, **kwargs) -> Any: ...   # 抓取原始資料
    def validate(self, data) -> Tuple[bool, str]: ...          # 驗證資料品質
    def parse(self, data) -> pd.DataFrame: ...                 # 清理 / 標準化
    def save(self, df, session) -> int: ...                    # 寫入 DB

    def run(self, trade_date=None, session=None, **kwargs) -> CollectResult:
        # collect → validate → parse → save 標準流程
        # 任何步驟拋出 exception 均自動 wrap 成 CollectResult.error
```

## CollectResult

定義於 `src/core/result.py`：

```python
result = PriceCollector().run(trade_date, session)

result.is_success   # True → 正常完成
result.is_warning   # True → 完成但資料品質有疑慮
result.is_error     # True → collect / parse / save 拋出 exception
result.n_rows       # 儲存筆數
result.message      # 人類可讀說明
result.source       # "price" / "chip" / "financial" / "news"
bool(result)        # False = error，True = success / warning
```

## 各 Collector

### PriceCollector（`price_collector.py`）

- **來源**：TWSE OpenAPI + TPEx OpenAPI + Yahoo Finance（補缺）
- **輸出**：`daily_prices` table（stock_id, date, open/high/low/close/volume/amount）
- **特殊邏輯**：
  - `_parse_roc_date(s)` 解析民國日期格式 `YYYMMDD`（7 位數字）
  - `_fetch_yahoo_one(sid)` 以 `status_code != 200` 判斷失敗（不用 `resp.ok`）
  - TWSE 和 TPEx 分別抓取後合併

### ChipCollector（`chip_collector.py`）

- **來源**：TWSE OpenAPI（外資 / 投信 / 自營商）+ TPEx OpenAPI
- **輸出**：`institutional_data` table（foreign_net / trust_net / dealer_net / total_net）
- **繼承**：`run()` 由 `BaseCollector` 提供

### FinancialCollector（`financial_collector.py`）

- **來源**：FinMind API（需要 Token）
- **輸出**：`financial_quarters` table（EPS / ROE / ROA / 毛利率等）
- **特殊**：`run()` 接受 `stock_id=` kwarg，以個股為單位蒐集

### NewsCollector（`news_collector.py`）

- **來源**：RSS feeds
- **輸出**：in-memory（不寫 DB；供 decision engine 使用）
- **run()** 回傳 `CollectResult`（n_rows = 新聞篇數）

### GoodinfoCollector / MopsCollector

- 補充財務資料（Goodinfo 本益比 / MOPS 公開資訊觀測站）
- 同樣實作 `BaseCollector` 介面

## 新增 Collector

詳見 `docs/DeveloperGuide.md`。簡短步驟：

1. 在 `src/collectors/` 新建 `xxx_collector.py`
2. `class XxxCollector(BaseCollector)`，實作 4 個抽象方法
3. 在 `src/collectors/__init__.py` export
4. 在 `main.py` 加入執行步驟

## 錯誤處理

`BaseCollector.run()` 會 catch 每個步驟的 exception 並回傳 `CollectResult.error`，不會讓單一 Collector 的失敗影響其他 Collector 的執行。

```python
result = PriceCollector().run(trade_date, session)
if result.is_error:
    logger.error(f"[{result.source}] {result.message}")
    # 繼續執行下一個 Collector
```
