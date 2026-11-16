# Session 72C — Functional Parity

**Session**: 72C  
**Verdict**: `FUNCTIONAL_PARITY_PASS`  
**Date**: 2026-11-13

---

## Old → New Entry Matrix

| Feature | Old Entry | New Entry | Original Function | Original Service | Data Source | Test | Status |
|---|---|---|---|---|---|---|---|
| 今日推薦 | Tab: 📊今日 | 今日決策 → 📊今日推薦 | `page_today` | `load_db_recommendations` | SQLite `recommendations` | test_all_core_pages_reachable | ✓ PASS |
| Candidate Pool | Tab: 📊今日 (sub-section) | 今日決策 → 📊今日推薦 | `page_today` (includes pool) | `CandidatePoolService` | SQLite `candidate_pool` | test_all_core_pages_reachable | ✓ PASS |
| Live Monitor | Tab: 📡盤中 | 今日決策 → 📡盤中監控 | `page_live_monitor` | LiveDecisionMonitor | SQLite `live_decisions` | test_all_core_pages_reachable | ✓ PASS |
| 股票搜尋 | Tab: 🔍個股 | 個股分析 → 🔍個股搜尋 | `page_search` | `load_db_recommendations` | SQLite | test_all_core_pages_reachable | ✓ PASS |
| K 線 | Tab: 📈看盤 | 個股分析 → 📈看盤K線 | `page_market_watch` | `DailyPriceService` | SQLite `daily_prices` | test_all_core_pages_reachable | ✓ PASS |
| MA20/MA60 | Tab: 📈看盤 | 個股分析 → 📈看盤K線 | `page_market_watch` | `DailyPriceService` | SQLite `daily_prices` | test_all_core_pages_reachable | ✓ PASS |
| 成交量 | Tab: 📈看盤 | 個股分析 → 📈看盤K線 | `page_market_watch` | `DailyPriceService` | SQLite `daily_prices` | test_all_core_pages_reachable | ✓ PASS |
| Decision Center | Tab: 🔍個股 | 個股分析 → 🔍個股搜尋 | `page_search` (embedded) | `DecisionPresenter` | SQLite | test_all_core_pages_reachable | ✓ PASS |
| 進場條件 | Tab: 🔍個股 | 個股分析 → 🔍個股搜尋 | `page_search` | `DecisionPresenter` | SQLite | test_all_core_pages_reachable | ✓ PASS |
| 停損 | Tab: 🔍個股 | 個股分析 → 🔍個股搜尋 | `page_search` | `DecisionPresenter` | SQLite | test_all_core_pages_reachable | ✓ PASS |
| 目標價 | Tab: 🔍個股 | 個股分析 → 🔍個股搜尋 | `page_search` | `DecisionPresenter` | SQLite | test_all_core_pages_reachable | ✓ PASS |
| 真實持倉 | Tab: 💼持倉 | 我的持倉 → 💼持倉狀況 | `page_positions` | `PositionService` | SQLite `positions` | test_all_core_pages_reachable | ✓ PASS |
| 模擬持倉 | Tab: 💼持倉 | 我的持倉 → 💼持倉狀況 | `page_positions` | `PositionService` | SQLite `positions` | test_all_core_pages_reachable | ✓ PASS |
| 交易紀錄 | Archive: 🗂交易記錄 | 我的持倉 → 🗂交易記錄 | `page_my_trades` | `TradeService` | SQLite `trades` | test_all_core_pages_reachable | ✓ PASS |
| 歷史回測 | Archive: 🔬Legacy驗證 | 策略績效 → 🧪歷史回測 → radio Legacy | `page_backtest` | `BacktestEngine` | SQLite | test_legacy_reachable_via_system_management | ✓ PASS |
| 研究回測 | Tab: 🧪研究回測 | 策略績效 → 🧪歷史回測 → radio 研究回測 | `page_research_backtest` | `ResearchBacktestService` | SQLite | test_all_core_pages_reachable | ✓ PASS |
| Forward Evidence | Tab: 🔒證據 | 策略績效 → 🔒前向驗證 | `page_evidence` | `ForwardSignalService` | SQLite `forward_signals` | test_all_core_pages_reachable | ✓ PASS |
| Shadow Research | Tab: ⏱️進場時機 | 策略績效 → ⏱️進場研究 → radio進場時機 | `page_entry_timing_research` | `EntryTimingResearchService` | Neon `v2_shadow_signals` | test_all_core_pages_reachable | ✓ PASS |
| 資料健康 | Archive: 🩺資料健康 | 系統管理 → 🩺資料健康 | `page_data_health` | DataHealthService | SQLite + Neon | test_all_core_pages_reachable | ✓ PASS |
| 設定 | Archive: ⚙️設定 | 系統管理 → ⚙️設定 | `page_settings` | — | — | test_all_core_pages_reachable | ✓ PASS |
| Legacy Access | Archive: 📦Archive | 系統管理 (all) + 策略績效 radio | multiple | multiple | multiple | test_legacy_reachable_via_system_management | ✓ PASS |

---

## Parity Summary

- **21 features checked**: 21 PASS, 0 GAP
- All original page functions called unchanged
- No service logic modified
- No data source changed
- Trading signals, scoring, backtest formulas: ALL UNCHANGED

**Note**: `page_history` (推薦歷史) is now accessible via 策略績效 → 進場研究 → radio「推薦歷史」. This is a slight position change from the old Tab 9 (📋歷史) but all the same data and function.
