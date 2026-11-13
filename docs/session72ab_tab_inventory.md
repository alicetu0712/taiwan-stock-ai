# Session 72AB — Tab Inventory

**Session**: 72AB  
**Verdict**: `COMPLETE`  
**Source**: Static scan of `dashboard/_pages/` + `dashboard/app.py`

---

## Original Navigation Structure (10 Tabs)

### Level 1 — 每日使用 (Tabs 0–4)

| Tab | Display Name | Source File | Entry Function | Service Dependency | Data Source | Visibility | User Value | Duplication | Proposed Destination |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 📊 今日 | `overview.py` | `page_today(date)` | DecisionPresenter, loaders, trading_calendar | SQLite DailyPrice + Recommendation | Always visible | HIGH — 核心入口：今日推薦 | Partial dup with 🔍個股 | → 今日決策 (主) |
| 1 | 📡 盤中 | `live_monitor.py` | `page_live_monitor(date)` | Recommendation, DailyPrice, get_session | SQLite + 即時 | Always visible | MEDIUM — 盤中價格追蹤 | Dup with 今日推薦入口 | → 今日決策 (子) |
| 2 | 📈 看盤 | `market_watch.py` | `page_market_watch(date)` | loaders, components | SQLite DailyPrice | Always visible | HIGH — K線/均線/趨勢 | Dup with 🔍個股 | → 個股分析 (主) |
| 3 | 💼 持倉 | `position.py` | `page_positions()` | PositionPresenter, PositionMonitor | SQLite/Neon PositionMonitor | Always visible | HIGH — 持倉損益追蹤 | None | → 我的持倉 (主) |
| 4 | 🔒 證據 | `evidence.py` | `page_evidence()` | EvidencePresenter, ForwardOutcomeEvaluation | SQLite ForwardOutcomeEvaluation | Always visible | MEDIUM — 前向驗證結果 | Partial dup with 研究回測 | → 策略績效/前向驗證 |

### Level 2 — Research (Tabs 5–8)

| Tab | Display Name | Source File | Entry Function | Service Dependency | Data Source | Visibility | User Value | Duplication | Proposed Destination |
|---|---|---|---|---|---|---|---|---|---|
| 5 | 🧪 研究回測 | `research_backtest.py` | `page_research_backtest()` | ResearchBacktestService, ForwardSignal | SQLite ForwardSignal | Always visible | MEDIUM — 策略回測 | Dup with 🔬Legacy | → 策略績效/歷史回測 |
| 6 | ⏱️ 進場時機 | `entry_timing_research.py` | `page_entry_timing_research()` | V2ShadowSignal, research.backtest_full | Neon v2_shadow_signals | Always visible | LOW — Shadow研究，常無資料 | None | → 策略績效/進場研究 |
| 7 | 🔍 個股 | `reports.py` | `page_search()` | loaders | SQLite DailyPrice + Recommendation | Always visible | HIGH — 個股搜尋 | Dup with 📈看盤 | → 個股分析 (子) |
| 8 | 📋 歷史 | `reports.py` | `page_history()` | loaders | SQLite Recommendation | Always visible | MEDIUM — 推薦歷史查詢 | None | → 策略績效/進場研究 (子) |

### Level 3 — Archive (Tab 9)

| Sub-page | Display Name | Source File | Entry Function | Proposed Destination |
|---|---|---|---|---|
| Archive/0 | 🔬 Legacy 驗證 | `backtest.py` | `page_backtest()` | → 策略績效/歷史回測 (Legacy子) |
| Archive/1 | 📋 成績單 | `scorecard.py` | `page_scorecard()` | → 策略績效/績效總覽 |
| Archive/2 | 🗂 交易記錄 | `my_trades.py` | `page_my_trades()` | → 我的持倉/交易記錄 |
| Archive/3 | 🩺 資料健康 | `data_health.py` | `page_data_health()` | → 系統管理/資料健康 |
| Archive/4 | 📖 說明 | `guide.py` | `page_guide()` | → 系統管理/說明 |
| Archive/5 | ⚙️ 設定 | `guide.py` | `page_settings(date)` | → 系統管理/設定 |

---

## Duplication Map

| Duplicate Pair | Type | Resolution |
|---|---|---|
| 📊今日 + 📡盤中 | Same entry point for today's view | Merge: 今日決策/今日推薦 + 盤中監控 sub-tabs |
| 📈看盤 + 🔍個股 | Both show individual stock data | Merge: 個股分析 with K線 + 搜尋 sub-tabs |
| 🧪研究回測 + 🔬Legacy驗證 | Both are backtests | Merge under 策略績效/歷史回測 |
| 🔒證據 + 🧪研究回測 | Both are strategy performance evidence | Separate sub-tabs under 策略績效 |
| 交易記錄 (Archive) | Separate from 持倉 | Merge: 我的持倉/交易記錄 |
| 📋成績單 (Archive) | Separated from performance pages | Merge: 策略績效/績效總覽 |
