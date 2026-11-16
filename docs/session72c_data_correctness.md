# Session 72C — Data Correctness

**Session**: 72C  
**Verdict**: `DATA_CORRECTNESS_PARTIAL` (Neon LIVE_DATA_NOT_VERIFIED)  
**Date**: 2026-11-13

---

## Per-Page Data Audit

| Page | Data Source | Tables | Signal Type | Freshness Check | Empty State Behavior | Availability |
|---|---|---|---|---|---|---|
| `page_today` | SQLite | `recommendations`, `candidate_pool` | Official BUY/WAIT/SELL (v8.0) | Sidebar shows max(DailyPrice.date) | Shows "目前沒有符合條件的買進訊號" if no BUY | `LIVE_DATA_NOT_VERIFIED` |
| `page_live_monitor` | SQLite | `live_decisions` | Live collector signals | Live data timestamp | Shows "盤中監控資料尚未啟用或尚未更新" | `LIVE_DATA_NOT_VERIFIED` |
| `page_market_watch` | SQLite | `daily_prices` | Chart data (no signal) | Date from DailyPrice | Shows "查無資料" for no price data | `LIVE_DATA_NOT_VERIFIED` |
| `page_search` | SQLite | `recommendations`, `daily_prices` | Official BUY/WAIT/SELL (v8.0) | Per-stock date | Decision Center embedded | `LIVE_DATA_NOT_VERIFIED` |
| `page_positions` | SQLite | `positions` | None (portfolio tracking) | — | Shows empty portfolio state | `LIVE_DATA_NOT_VERIFIED` |
| `page_my_trades` | SQLite | `trades` | None (trade log) | — | Shows empty trades table | `LIVE_DATA_NOT_VERIFIED` |
| `page_scorecard` | SQLite | `forward_signals`, `recommendations` | Historical performance | — | Shows "樣本不足" if below threshold | `LIVE_DATA_NOT_VERIFIED` |
| `page_evidence` | SQLite | `forward_signals` | Forward validation (not trading signal) | Outcome date | Shows period/sample counts | `LIVE_DATA_NOT_VERIFIED` |
| `page_research_backtest` | SQLite | `backtest_results` | Research only | — | Shows research-only label | `LIVE_DATA_NOT_VERIFIED` |
| `page_backtest` | SQLite | `backtest_results` (legacy) | Historical only | — | Legacy label present | `LIVE_DATA_NOT_VERIFIED` |
| `page_entry_timing_research` | Neon | `v2_shadow_signals` | Research ONLY (V2 Shadow) | — | "無法連線研究資料庫" if Neon unreachable | `LIVE_DATA_NOT_VERIFIED` (Neon) |
| `page_history` | SQLite | `recommendations` | Historical record | Date range shown | Empty if no historical recs | `LIVE_DATA_NOT_VERIFIED` |
| `page_data_health` | SQLite + Neon | `daily_prices`, coverage tables | None (health metrics) | Multiple freshness gates | Per-gate status displayed | `LIVE_DATA_NOT_VERIFIED` |
| `page_guide` | Static | — | None | — | Static content always available | `DATA_AVAILABLE` |
| `page_settings` | SQLite (read) | `daily_prices` | None | Date picker | Always loads | `DATA_AVAILABLE` (mostly static) |

---

## Empty State Classification

| Situation | Correct Response | Implementation |
|---|---|---|
| No BUY signal today | `no_signal`: "目前沒有符合條件的買進訊號。" | `overview.py` handles this |
| SQLite has no data | `source_unavailable` or specific error msg | Each page handles via try/except |
| Sample too small | `insufficient_sample` message | `scorecard.py` has threshold check |
| Neon not reachable | "無法連線研究資料庫" | `entry_timing_research.py:282` |
| Feature not enabled | `feature_inactive`: "此功能尚未啟用" | Available in `empty_state()` |
| Research-only page | `research_only` banner | `st.info()` before 進場研究 |

---

## Critical Distinctions

The new UI correctly separates:
1. **「沒有推薦」** ≠ **「資料錯誤」** — `page_today` distinguishes these cases
2. **「研究結果」** ≠ **「正式訊號」** — 進場研究有明確 research banner
3. **「資料尚未更新」** ≠ **「資料庫無法連線」** — `page_data_health` shows per-gate status
4. **「樣本不足」** ≠ **「策略失敗」** — scorecard shows sample count with threshold

---

## `v2_shadow_signals` Write Path

Confirmed via code inspection: There is NO automated cron write path for `v2_shadow_signals` in the production scheduler. The table is populated by manual research scripts (`scripts/run_hybrid_forward_shadow.py`). The `entry_timing_research.py` page shows the correct "無資料" state when the table is empty. This is NOT an error — it is `FEATURE_NOT_ACTIVATED` state.

`BACKEND_CHANGE_REQUIRES_SEPARATE_AUTHORIZATION`: Adding an automated write schedule for `v2_shadow_signals` would require a separate backend authorization.

---

**Note**: All "LIVE_DATA_NOT_VERIFIED" means the data correctness was verified via code inspection, not live database queries. The Streamlit process (PID 43585) already shows data from the production SQLite in the live dashboard; the isolated dashboard connects to the same SQLite.
