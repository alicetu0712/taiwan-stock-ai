# Architecture

AI 台股研究平台 v7.0 系統架構。

## 模組地圖

```
┌─────────────────────────────────────────────────────┐
│                  外部資料來源                         │
│  TWSE OpenAPI  TPEx OpenAPI  FinMind  Goodinfo  RSS  │
└────────────┬──────────────────────────────┬──────────┘
             │                              │
             ▼                              ▼
┌─────────────────────┐       ┌─────────────────────────┐
│   src/collectors/   │       │     src/collectors/      │
│   price_collector   │       │   chip_collector         │
│   financial_coll.   │       │   news_collector         │
│   goodinfo_coll.    │       │   mops_collector         │
└──────────┬──────────┘       └────────────┬────────────┘
           │  BaseCollector.run()           │
           │  → CollectResult              │
           └───────────────┬───────────────┘
                           ▼
                ┌─────────────────┐
                │  src/database   │
                │  SQLAlchemy ORM │
                │  SQLite / Neon  │
                └────────┬────────┘
                         │
            ┌────────────┴──────────────┐
            ▼                           ▼
┌───────────────────┐       ┌───────────────────────┐
│  src/analyzers/   │       │    src/engines/        │
│  technical.py     │       │    hard_filter.py      │
│  fundamental.py   │──────▶│    decision.py         │
│  market_behavior  │       │    monte_carlo.py      │
│  risk.py          │       │    position_manager.py │
└───────────────────┘       └──────────┬────────────┘
                                       │ StockRecommendation
                                       ▼
                            ┌─────────────────────┐
                            │  src/reporters/      │
                            │  report_generator.py │
                            │  src/ai/             │
                            │  claude_analyst.py   │
                            └──────────┬───────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │  dashboard/          │
                            │  app.py (Streamlit)  │
                            │  pages/ loaders.py   │
                            └─────────────────────┘
```

## 目錄結構

```
stock_platform/
├── config.py               # 全域設定、策略參數、API 金鑰
├── main.py                 # 每日批次執行入口
├── src/
│   ├── core/
│   │   └── result.py       # Result[T] / CollectResult 統一回傳型別
│   ├── collectors/
│   │   ├── base.py         # BaseCollector ABC（定義 collect/validate/parse/save/run）
│   │   ├── price_collector.py
│   │   ├── chip_collector.py
│   │   ├── financial_collector.py
│   │   ├── news_collector.py
│   │   ├── goodinfo_collector.py
│   │   └── mops_collector.py
│   ├── analyzers/
│   │   ├── technical.py    # RSI / KD / MA / 支撐壓力
│   │   ├── fundamental.py  # ROE / ROA / EPS / 毛利率 / 估值
│   │   ├── market_behavior.py  # 籌碼分析
│   │   └── risk.py         # 風險評估
│   ├── engines/
│   │   ├── hard_filter.py  # 硬性篩選（第一層淘汰）
│   │   ├── decision.py     # AI 決策引擎（整合所有分析）
│   │   ├── monte_carlo.py  # 蒙地卡羅價格模擬
│   │   └── position_manager.py  # 目標價 / 停損 / 部位
│   ├── ai/
│   │   └── claude_analyst.py   # Claude API 呼叫
│   ├── reporters/
│   │   └── report_generator.py
│   ├── validators/
│   └── database.py         # ORM models + get_session()
├── dashboard/
│   ├── app.py              # Streamlit 入口（9 個 tab）
│   ├── db.py               # dashboard 用的 DB alias
│   ├── loaders.py          # @st.cache_data 快取查詢
│   └── pages/
│       ├── overview.py     # 今日推薦
│       ├── reports.py      # 個股查詢 / 歷史
│       ├── position.py     # 模型持倉追蹤
│       ├── backtest.py     # 回測驗證
│       ├── my_trades.py    # 個人交易記錄
│       ├── data_health.py  # 資料品質監控
│       ├── guide.py        # 說明 / 設定
│       └── backtest.py
├── tests/                  # pytest 測試（97 tests, 81% coverage）
├── docs/                   # 本文件目錄
└── config.py
```

## 資料流

```
每日 15:35 → 收盤後執行
  1. price_collector  → daily_prices (TWSE+TPEx)
  2. chip_collector   → institutional_data
  3. news_collector   → news cache (RSS)
  4. hard_filter      → 篩掉不合格股票
  5. analyzers        → quality/timing/behavior/risk scores
  6. decision.py      → StockRecommendation list
  7. monte_carlo      → 目標價達成率
  8. position_manager → 停損/目標價/部位建議
  9. report_generator → Markdown 報告 + DB 寫入
 10. claude_analyst   → AI 摘要（可選）
```

## 資料庫 Schema（主要表）

| 資料表 | 說明 |
|---|---|
| `daily_prices` | 每日股價（OHLCV）|
| `institutional_data` | 三大法人買賣超 |
| `financial_quarters` | 季度財報（EPS / ROE / ROA / 毛利率）|
| `monthly_revenue` | 月營收 |
| `analysis_results` | 每日分析評分 |
| `recommendations` | 每日推薦名單 |
| `position_monitor` | 持倉追蹤（目標價/停損）|
| `execution_logs` | 每日執行記錄 |
| `user_trades` | 個人交易記錄 |

## 環境

- **本機開發**：SQLite（`data/platform.db`）
- **雲端部署**：PostgreSQL / Neon（`DATABASE_URL` env var）
- 切換邏輯見 `config.py`，程式碼不需修改。
