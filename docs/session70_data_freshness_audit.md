# Session 70 — Data Freshness Audit

**Audit Date**: 2026-11-11  
**Execution Mode**: READ_ONLY_DESIGN_AND_VALIDATION — no production code changes  
**Baseline**: DB max_date = 2026-11-05 (5 trading days behind as of audit date)

---

## 1. Current Freshness State (Verified)

| Data Source | Table | Max Date | Lag (Trading Days) | Status |
|---|---|---|---|---|
| EOD Prices | `daily_prices` | 2026-11-05 | 5 | STALE |
| Analysis Results | `analysis_results` | 2026-11-05 (inferred) | 5 | STALE |
| Forward Signals | `forward_signals` | Unknown (see S46+) | Unknown | STALE |
| Execution Log | `execution_log` | 2026-11-10 (last failed) | — | QG_FAIL |
| Overnight Context | `overnight_market_contexts` | 2026-11-10 | 1 | QG_FAIL |
| Intraday Quotes | TWSE MIS API (live) | Real-time during 盤中 | Live | LIVE / STALE |
| Recommendations | `recommendations` | 2026-11-05 (inferred) | 5 | STALE |
| Candidate Pool | `candidate_pool_entries` | 2026-11-05 (inferred) | 5 | STALE |

**Root cause of STALE status**: RC-2 H3 pending; PRE_EXISTING QG failure (api_date mismatch Nov 9/10).  
**Warrant count contamination**: 0 rows post-2026-11-05 (RC-2 clean).

---

## 2. Per-Page Freshness Coverage Audit

### T0 — 今日 (overview.py)

| Data Element | Source | Freshness Label Shown? | Quality |
|---|---|---|---|
| BUY signal cards | `recommendations` | Partial — `freshness_html` only if `days_old > 1` | INSUFFICIENT |
| Candidate pool | `candidate_pool_entries` | Yes — `as_of_label` = "YYYY-MM-DD 分析日資料" | ACCEPTABLE |
| Pipeline funnel | `execution_log` | No | MISSING |
| Market health | `analysis_results` derived | No explicit data-as-of | MISSING |
| Price in signal card | `daily_prices` | "前收盤" / "收盤" label (relative to selected_date) | PARTIAL |
| Auto-redirect notice | `execution_log` | Yes — "資料庫最新完成日期：{latest_data_date}" | ACCEPTABLE |

**Gap**: No persistent "資料截至 {max_daily_price_date}" banner on the main card header. The `freshness_html` only appears when `selected_date < latest_date`, which means when looking at the current latest date, there is NO indicator that data is 5 trading days behind.

**Code location**: `overview.py:99–115` (_render_trading_reference), `overview.py:1256–1273` (auto-redirect)

---

### T1 — 盤中 (live_monitor.py)

| Data Element | Source | Freshness Label Shown? | Quality |
|---|---|---|---|
| Intraday price | TWSE MIS API | Yes — `quote_date_status()` → "valid" / "stale" | GOOD |
| Session label | Computed | Yes — "盤中" vs "收盤後" | GOOD |
| Signal source date | `recommendations` | Partial — signal_date shown in card | ACCEPTABLE |
| Overnight risk | `overnight_market_contexts` | No explicit data-age label | PARTIAL |
| Refresh interval | UI selectbox | Yes — shows countdown | GOOD |

**Gap**: Overnight context `fetched_at` not surfaced. If overnight data is STALE, only `risk_level=UNKNOWN` is shown without timestamp.

---

### T2 — 看盤 (market_watch.py)

| Data Element | Source | Freshness Label Shown? | Quality |
|---|---|---|---|
| K-line chart | `daily_prices` | **None** — chart ends at max_date silently | MISSING |
| PriceTrend score | `analysis_results` | No date label shown in banner | MISSING |
| MA values | `daily_prices` derived | No data-as-of | MISSING |
| Setup badge | `analysis_results` | No analysis-date label | MISSING |

**Gap**: This is the most severe gap. A user viewing 看盤 on 2026-11-11 sees a K-chart that ends at 2026-11-05 with no indication the data is 5 days old. The PriceTrend score shows "breakout" without any "calculated on 2026-11-05" label.

**Loader TTLs**: `load_price_chart_data()` TTL=600s; `load_latest_pt_analysis()` TTL=600s. Neither surfaces `as_of_date` to the UI.

---

### T3 — 持倉 (position.py)

| Data Element | Source | Freshness Label Shown? | Quality |
|---|---|---|---|
| Position prices | `daily_prices` / API | No explicit freshness | PARTIAL |
| P&L calculations | `daily_prices` | No | MISSING |
| Entry date | `actual_positions` | Yes (absolute dates) | ACCEPTABLE |

---

### T4 — 證據 (evidence.py)

| Data Element | Source | Freshness Label Shown? | Quality |
|---|---|---|---|
| ForwardOutcome stats | `forward_outcome_evaluations` | No data-age label | MISSING |
| Overnight data quality | `overnight_market_contexts` | Yes — ODQ_COMPLETE/PARTIAL | ACCEPTABLE |
| Protocol version | `foe_v1` | Yes — banner | GOOD |
| Last evaluation date | `forward_outcome_evaluations` | No | MISSING |

---

### T5 — 研究回測 (research_backtest.py)

| Data Element | Source | Freshness Label Shown? | Quality |
|---|---|---|---|
| IS results | `analysis_results` | Shows cutoff 2026-10-09 | ACCEPTABLE |
| OOS results | `forward_signals` | Shows cutoff 2026-10-09 | ACCEPTABLE |
| Most recent signal | `forward_signals` | No max_date label | PARTIAL |
| RESEARCH banner | — | Partial (docstring only, not UI) | MISSING |

---

### T6 — 進場時機 (entry_timing_research.py)

| Data Element | Source | Freshness Label Shown? | Quality |
|---|---|---|---|
| DailyPrice freshness | `daily_prices` | Yes — `_render_dailyprice_freshness_panel()` exists! | GOOD |
| V2 shadow signals | `v2_shadow_signals` Neon | No max_date | PARTIAL |
| RESEARCH banner | — | Inline text, not prominent | PARTIAL |

**Notable**: `_render_dailyprice_freshness_panel()` at line 1110 is the ONLY dedicated freshness panel in the entire platform. It shows last_date, gap_days, and stale warning. This should serve as the reference implementation.

---

### Sidebar (app.py)

| Data Element | Source | Freshness Label Shown? | Quality |
|---|---|---|---|
| DB row count | `daily_prices` | `st.metric("股價資料", f"{cnt:,} 筆")` | PARTIAL |
| Max date | `daily_prices` | `st.caption(f"最新：{newest}")` | PARTIAL |

**Exists but low-visibility**: `app.py:276–278`. The caption "最新：2026-11-05" is shown but only as a small caption under the metric. No staleness color or warning.

---

## 3. TTL Inventory (Freshness-Affecting)

| Function | TTL | Returns Date? | Freshness Gap |
|---|---|---|---|
| `load_stock_prices()` | 300s | No (only prices dict) | Missing: no max_date returned |
| `load_latest_completed_date()` | 300s | Yes (`ExecutionLog.date`) | ExecutionLog ≠ DailyPrice date |
| `load_price_chart_data()` | 600s | Yes (df["date"]) | Not surfaced to UI |
| `load_latest_pt_analysis()` | 600s | Yes (`row.date`) | Not surfaced to UI |
| `load_watchable_stocks()` | 600s | No | — |
| `load_stock_names()` | 86400s | No | 24h cache = OK |
| `load_db_stats()` | 1800s | Yes (`newest`) | Only in Sidebar |
| `load_analysis_results()` | 1800s | Yes (embedded in results) | Not surfaced as freshness label |

**Key issue**: `load_latest_completed_date()` returns the last SUCCESSFUL execution_log date — this represents the last time the pipeline ran successfully, NOT necessarily the last DailyPrice date. After QG failures (Nov 9/10), `execution_log.status` = failed, so `load_latest_completed_date()` still returns 2026-11-05 (the last success). This is correct behavior but should be clearly labeled.

---

## 4. Live vs EOD Distinction

| Surface | Data Type | Distinction Shown? |
|---|---|---|
| T0 今日 | EOD only | No "EOD" label |
| T1 盤中 | Live (intraday) + EOD signal | Yes — "盤中" / "收盤後" label |
| T2 看盤 | EOD only | No "EOD" label |
| T3 持倉 | EOD + stale check | Partial |
| T4–T6 Research | Historical | No |

**Risk**: User accessing T2 看盤 during market hours may expect live prices. No "EOD data only" warning exists.

---

## 5. Priority Gaps

Ranked by user impact:

| Rank | Gap | Pages Affected | Severity |
|---|---|---|---|
| 1 | No "資料截至 {date}" on T2 看盤 K-chart | T2 | HIGH |
| 2 | No "EOD data" label on T2 during market hours | T2 | HIGH |
| 3 | Sidebar `st.caption("最新：{newest}")` has no staleness color | Sidebar | MEDIUM |
| 4 | PriceTrend score has no analysis-date label in market_watch.py | T2 | MEDIUM |
| 5 | No persistent freshness banner on T0 main header | T0 | MEDIUM |
| 6 | T4 证據: no last-evaluation-date label | T4 | MEDIUM |
| 7 | T5/T6: no max ForwardSignal date shown | T5, T6 | LOW |
| 8 | Overnight context `fetched_at` not shown in T1 | T1 | LOW |

---

## 6. What Exists (Do Not Duplicate)

The following freshness patterns already exist and are ACCEPTABLE — new components must be consistent with these:

1. `overview.py:99–115` — `freshness_html` conditional staleness warning (selected_date vs latest)
2. `overview.py:321–326` — `as_of_label` on candidate pool
3. `overview.py:149–155` — "前收盤" / "收盤" label per price (relative date)
4. `live_monitor.py` — "盤中" / "收盤後" session label + refresh countdown
5. `entry_timing_research.py:1110–1165` — `_render_dailyprice_freshness_panel()` ← reference implementation
6. `app.py:276–278` — sidebar `st.caption("最新：{newest}")` ← extend, not replace

---

## 7. Verdict

| Category | Status |
|---|---|
| EOD Price Freshness (T2) | GAP_CRITICAL |
| Signal Freshness (T0) | GAP_MEDIUM |
| Live vs EOD Distinction | GAP_MEDIUM |
| Research Freshness (T5/T6) | GAP_LOW |
| Reference Implementation Exists | YES (T6 _render_dailyprice_freshness_panel) |
| Implementation Risk | ZERO (display-only changes) |
