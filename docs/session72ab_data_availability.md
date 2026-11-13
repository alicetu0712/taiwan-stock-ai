# Session 72AB — Data Availability Audit

**Session**: 72AB  
**Verdict**: `PARTIAL` — Runtime data not verified for Neon-backed pages  
**Method**: Static code analysis + schema inspection. No live Neon queries executed.

> **RUNTIME_DATA_NOT_VERIFIED** for all Neon PostgreSQL-backed pages (live Neon read requires restarting Streamlit with correct env — see S71Q context).

---

## Page-Level Availability

| Page | Data Source | Table(s) | Availability | Notes |
|---|---|---|---|---|
| 📊 今日 (overview) | SQLite | `daily_prices`, `recommendations` | `DATA_AVAILABLE` | 534,770 rows / MAX=2026-11-05 (pre-Nov-13 cron gap) |
| 📡 盤中 (live_monitor) | SQLite | `recommendations`, `daily_prices` | `STALE_DATA` | Last write 2026-11-05; no live ticker |
| 📈 看盤 (market_watch) | SQLite | `daily_prices` | `STALE_DATA` | Same 2026-11-05 ceiling; Nov 6–13 gap |
| 💼 持倉 (position) | SQLite + Neon | `position_monitor` | `RUNTIME_DATA_NOT_VERIFIED` | PositionPresenter reads Neon when USE_NEON=true |
| 🔒 證據 (evidence) | SQLite | `forward_outcome_evaluations` | `DATA_AVAILABLE` | EvidencePresenter confirmed working in prior sessions |
| 🧪 研究回測 (research_backtest) | SQLite | `forward_signals` | `DATA_AVAILABLE` | ForwardSignal with MODEL_VERSION v8.0 confirmed |
| ⏱️ 進場時機 (entry_timing_research) | Neon | `v2_shadow_signals` | `RUNTIME_DATA_NOT_VERIFIED` | Returns `__connection_error__` sentinel when Streamlit process lacks USE_NEON env (see S71Q Streamlit PID 43585 root cause) |
| 🔍 個股 (reports:page_search) | SQLite | `daily_prices`, `recommendations` | `DATA_AVAILABLE` | Dependent on stock in DB |
| 📋 歷史 (reports:page_history) | SQLite | `recommendations` | `DATA_AVAILABLE` | Historical recommendations queryable |
| 📋 成績單 (scorecard) | SQLite | `forward_signals` | `DATA_AVAILABLE` | ForwardSignal with decision_label confirmed |
| 🔬 Legacy 驗證 (backtest) | SQLite | `recommendations`, `forward_signals` | `DATA_AVAILABLE` | Standard backtest runs |
| 🗂 交易記錄 (my_trades) | SQLite | `user_trades`, `daily_prices` | `DATA_AVAILABLE` | UserTrade via dashboard.db.get_session() |
| 🩺 資料健康 (data_health) | SQLite | `daily_prices`, `recommendations` | `DATA_AVAILABLE` | Query confirmed in prior sessions |
| 📖 說明 (guide) | SQLite | stats only | `DATA_AVAILABLE` | Guide + loaders.load_db_stats() |
| ⚙️ 設定 (guide:page_settings) | SQLite | date selection | `DATA_AVAILABLE` | Stateless UI |

---

## v2_shadow_signals Write Path Audit

**Question**: Does `v2_shadow_signals` have an automatic write path?

Static analysis finds:
- `src/research/models.py` — defines `V2ShadowSignal` ORM model
- `src/services/shadow_recalculation_service.py` — `ShadowRecalculationService.recalculate()` writes V2ShadowSignal rows
- `src/services/entry_timing_research_service.py` — `run_for_date()` writes v2_research_v1 rows
- **No scheduled cron entry** found calling these services

**Conclusion**: `v2_shadow_signals` requires MANUAL invocation of research scripts. It is NOT auto-populated by the production cron (`hybrid_shadow_cron.py`). Data absence is expected unless scripts have been run manually.

**Status**: `FEATURE_NOT_ACTIVATED` (not `EMPTY_TABLE` — table may exist but has no automatic pipeline)

---

## Data Freshness Summary

| Layer | Max Date | Gap |
|---|---|---|
| SQLite `daily_prices` | 2026-11-05 | 6 trading days missing (Nov 06–13) |
| SQLite `recommendations` | 2026-10-28 | 12 trading days |
| Neon `v2_shadow_signals` | RUNTIME_DATA_NOT_VERIFIED | — |
| Neon `position_monitor` | RUNTIME_DATA_NOT_VERIFIED | — |

The Nov 06–13 gap in `daily_prices` is due to TWSE returning `api_date=prev_day` during all retry windows (confirmed in S71Q cron observation). This is a provider-side delay, not a schema or code issue.
