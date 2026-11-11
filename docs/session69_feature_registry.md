# Session 69 — Feature Registry

**Audit Date**: 2026-11-11  
**Execution Mode**: READ_ONLY_ARCHITECTURE_AUDIT  
**Production Integrity**: RC-2 hash 4eb6eacf... VERIFIED, MODEL_VERSION v8.0 VERIFIED

---

## 1. Navigation Feature Inventory

| ID | Feature Name | User Goal | Entry Point | Key Files | Data Source | R/W | Mode | Model | Status | Freq | Overlap | Risk | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F01 | 今日分析 Today Overview | 看今日推薦、市場狀態、進場計劃 | Tab 0 | overview.py, loaders.py | SQLite: Recommendation, DailyPrice, ForwardSignal, CandidatePool | R | Live | v8.0 | Production | Daily | F02(盤中), F08(個股) | 核心頁面 | KEEP |
| F02 | 盤中監控 Live Monitor | 盤中確認 BUY 計劃是否仍有效 | Tab 1 | live_monitor.py, live_background_service.py, live_decision.py | SQLite: Recommendation, DailyPrice; LiveExecutionEvent | R+W(state) | Live | v8.0 | Production | Daily | F01(今日), F04(持倉) | Intraday state write | KEEP |
| F03 | 看盤 Market Watch | K 線圖、MA 趨勢、Setup 狀態 | Tab 2 | market_watch.py, loaders.py | SQLite: DailyPrice, AnalysisResult | R | Live | v8.0 | Production | Daily | F02(盤中) | 無計算重疊 | KEEP |
| F04 | 持倉管理 Positions | 追蹤實際持倉+模型持倉+歷史 | Tab 3 (3 sub-tabs) | position.py, position_presenter.py, actual_position_service.py | SQLite(ActualPosition), Neon(PositionMonitor), SQLite(UserTrade) | R+W | Live | v8.0 | Production | Daily | F11(交易記錄) | 寫入 ActualPosition | MERGE_UI (與F11) |
| F05 | 前向執行證據 Evidence | foe_v1 前向執行結果、成效評估 | Tab 4 | evidence.py, evidence_presenter.py, outcome_service.py | SQLite: ForwardOutcomeEvaluation | R | Research | foe_v1 | Production | Occasional | F12(成績單) | DO_NOT_REMOVE (foe_v1 contract) | KEEP |
| F06 | 研究回測 Research Backtest | IS/OOS 研究分析、Alpha 統計 | Tab 5 | research_backtest.py, research_backtest_service.py | SQLite: analysis_results, forward_signals | R | Research | v8.0 research | Production | Occasional | F07(進場時機), F10(Legacy驗證) | 研究重現性 | KEEP |
| F07 | 進場時機研究 Entry Timing | V2 進場時機研究、Shadow 比較 | Tab 6 | entry_timing_research.py, entry_timing_research_service.py | SQLite(raw sqlite3+ORM): ForwardSignal, EntryTimingResult | R | Research/Shadow | v2_research | Research | Occasional | F06(研究回測) | raw sqlite3 access risk | KEEP (fix sqlite3 access) |
| F08 | 個股查詢 Stock Search | 查詢特定股票歷史研究記錄 | Tab 7 | reports.py::page_search, loaders.py | SQLite: Recommendation, DailyPrice | R | Live | v8.0 | Production | Occasional | F01(今日) | 無 | KEEP |
| F09 | 歷史推薦 History | 近期推薦清單 | Tab 8 | reports.py::page_history, loaders.py | SQLite: Recommendation | R | Live | v8.0 | Production | Occasional | F08(個股), F12(成績單) | 無 | MERGE_UI (與F08 合成單頁) |
| F10 | Legacy 驗證 Legacy Backtest | 舊式回測+Monte Carlo+V1vsV2 | Archive | backtest.py, backtest_service.py | SQLite: Recommendation, DailyPrice | R | Archive | v8.0 historical | Archive | Admin | F06(研究回測) | 歷史可重現性 | ARCHIVE |
| F11 | 交易記錄 My Trades | 使用者手動記錄的實際交易 | Archive | my_trades.py | SQLite: UserTrade | R+W | Live | N/A | Production | Occasional | F04(持倉歷史tab) | UserTrade write | MERGE_UI (入 F04) |
| F12 | 成績單 Scorecard | ForwardSignal 決策記錄+績效追蹤 | Archive | scorecard.py | SQLite: ForwardSignal | R | Research | v8.0 | Research | Occasional | F05(證據) | 研究可重現性 | ARCHIVE (or MERGE_UI 入 F05) |
| F13 | 資料健康 Data Health | 資料來源新鮮度+覆蓋率監控 | Archive | data_health.py | SQLite: DailyPrice, Recommendation, Stock | R | Tool | N/A | Tool | Admin | 無 | 無 | KEEP (提升至常駐) |
| F14 | 說明 Guide | 評分說明、模型說明 | Archive | guide.py | 靜態文字 | R | Tool | N/A | Tool | Admin | 無 | 無 | KEEP |
| F15 | 設定 Settings | 日期選擇、Cache 清除 | Archive | guide.py::page_settings | session_state | R+W | Tool | N/A | Tool | Admin | 無 | 無 | KEEP (移至 Sidebar) |

---

## 2. CLI / Script Feature Inventory

| ID | Feature Name | Entry Point | Key Files | Purpose | Status | Risk |
|---|---|---|---|---|---|---|
| S01 | 每日分析 Pipeline | `python main.py` | main.py (1621L) | 完整 EOD 分析流程（收集+分析+決策+報告） | Production | DO_NOT_REMOVE |
| S02 | 自動 Backfill Cron | cron 0 16 * * 1-5 | hybrid_shadow_cron.py → backfill_daily_prices.py | 每日自動更新 DailyPrice | Production (RC-2 deployed) | DO_NOT_REMOVE |
| S03 | Hybrid Forward Shadow | `run_hybrid_forward_shadow.py` | hybrid_forward_db.py | Forward Signal 寫入 | Production | DO_NOT_REMOVE |
| S04 | Overnight Risk | `run_overnight.py` | overnight_service.py, overnight_risk.py | 隔夜風險評估 | Production | DO_NOT_REMOVE |
| S05 | Neon Sync | `sync_to_neon.py` | — | 本機 → Neon 同步 | Production | DO_NOT_REMOVE |
| S06 | Research Backtest | `run_research_backtest.py` | research_backtest_service.py | 研究回測重跑 | Research | DO_NOT_REMOVE |
| S07 | Effectiveness Analysis | `run_effectiveness_analysis.py` | effectiveness_analyzer.py | 效果評估 | Research | DO_NOT_REMOVE |
| S08 | History Backfill | `backfill_history.py` | — | 歷史資料補填 | Tool | REFACTOR_CANDIDATE |
| S09 | DB Init | `init_db.py` | database.py | 建立 Schema | Tool | DO_NOT_REMOVE |
| S10 | Migration Scripts | `migrate_*.py` (3 files) | database.py | Schema migration | Tool | ARCHIVE (已執行完畢) |

---

## 3. Source Module Role Map

| Module | Role | Consumers | Status |
|---|---|---|---|
| `src/analyzers/technical.py` | V1 技術面評分（MA/MACD/RSI/setup_type） | main.py pipeline | Production (V1) |
| `src/analyzers/price_trend.py` | V2 價格趨勢分析（MA structure, breakout, V2 architecture） | main.py pipeline, research_backtest_service | Production (V2 scorer) |
| `src/analyzers/fundamental.py` | 基本面分析（EPS, ROE） | main.py pipeline | Production |
| `src/analyzers/market_behavior.py` | 市場行為分析（籌碼、法人） | main.py pipeline | Production |
| `src/analyzers/risk.py` | 風險評估（ATR, 乖離率） | main.py pipeline | Production |
| `src/analyzers/entry_timing.py` | 進場時機評分 | main.py pipeline | Production |
| `src/engines/decision.py` | 整合決策引擎（BUY/WAIT/STRONG_BUY） | main.py pipeline | Production (v8.0) |
| `src/engines/live_decision.py` | 盤中即時決策 | live_monitor | Production |
| `src/engines/hard_filter.py` | 硬性排除規則 | main.py pipeline | Production |
| `src/engines/outcome_evaluation.py` | foe_v1 Forward Outcome 評估規則 | outcome_service | Production (frozen) |
| `src/engines/overnight_risk.py` | 隔夜風險層 | overnight_service | Production |
| `src/engines/position_manager.py` | PAPER 持倉狀態機 | hybrid_shadow_cron | Production |
| `src/services/backtest_service.py` | Legacy 回測（Recommendation table） | backtest.py (Archive) | Archive |
| `src/services/research_backtest_service.py` | IS/OOS 研究回測 | research_backtest.py | Production/Research |
| `src/services/evidence_service.py` | Historical/Forward Alpha 統計 | overview.py, evidence.py | Production |
| `src/services/candidate_pool_service.py` | 候選追蹤池管理 | hybrid_shadow_cron, overview.py | Production |
| `src/services/outcome_service.py` | foe_v1 outcome 計算+持久化 | run_overnight.py | Production |
| `src/research/` (60+ files) | Session-specific 研究模組 | 各 test files | Research/Archive |
| `src/core/trading_calendar.py` | 正式交易日曆 | 廣泛使用 | Production |
| `src/research/hybrid_trading_calendar.py` | Research 交易日曆包裝 | 研究模組 | Research |

---

## 4. Data Table Summary

| Table | Owner | Consumer Pages | Write Path | SSOT Role |
|---|---|---|---|---|
| `stocks` | backfill_daily_prices | loaders, data_health | Cron backfill | 股票主檔 |
| `daily_prices` | backfill_daily_prices | loaders, backtest, evidence | Cron backfill (RC-2) | 股價 SSOT |
| `analysis_results` | main.py pipeline | research_backtest, loaders | Daily pipeline | In-Sample 研究基礎 |
| `recommendations` | main.py pipeline | overview, search, history, backtest | Daily pipeline | 決策記錄 |
| `forward_signals` | hybrid_shadow_cron | research_backtest, scorecard, evidence | Shadow cron | Forward 訊號 SSOT |
| `forward_outcome_evaluations` | outcome_service | evidence.py | run_overnight | foe_v1 outcome |
| `position_monitor` | position_manager (Neon) | position.py PAPER tab | hybrid_shadow_cron | PAPER 持倉 |
| `actual_positions` | UI (user manual, Neon) | position.py ACTUAL tab | dashboard write | 實際持倉 |
| `user_trades` | UI (old, SQLite) | my_trades.py, position.py 歷史 | dashboard write | 舊式交易記錄 |
| `candidate_pool` | candidate_pool_service | overview.py | hybrid_shadow_cron | 候選池 |
