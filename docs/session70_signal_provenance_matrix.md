# Session 70 — Signal Provenance Matrix

**Audit Date**: 2026-11-11  
**Scope**: Every user-visible signal/price/score → trace to source table, date column, TTL, and display surface

---

## 1. Signal Type Taxonomy

| Signal Class | Definition | Example |
|---|---|---|
| `TRADE_SIGNAL` | AI-generated BUY/WAIT/STRONG_BUY recommendation | "BUY 台積電 at 850–870" |
| `EOD_PRICE` | Historical end-of-day OHLCV from daily_prices | K-chart closing price |
| `ANALYSIS_SCORE` | Computed technical score (PriceTrend, timing, etc.) | "breakout 🚀 MA20乖離 +3.5%" |
| `LIVE_QUOTE` | Real-time intraday price from TWSE MIS API | "現價 851.0" in 盤中 |
| `FORWARD_SIGNAL` | Pre-registered forward observation for research | ForwardSignal table |
| `OUTCOME_EVAL` | foe_v1 evaluated outcome (WINNER/LOSER/ACTIVE) | 證據 page stats |
| `OVERNIGHT_RISK` | US market risk context | GreenYellowRed in 盤中 |
| `CANDIDATE_POOL` | Active watchlist entry | Candidate pool card |

---

## 2. Full Provenance Matrix

### TRADE_SIGNAL

| Attribute | Value |
|---|---|
| **Source table** | `recommendations` |
| **Date column** | `date` (analysis date, NOT execution date) |
| **Price source** | `daily_prices.close` (via `load_db_recommendations` → `load_stock_prices`) |
| **Price date column** | `daily_prices.date` (separately tracked as `price_date`) |
| **Generation time** | Cron 16:00 CST → `main.py::run_pipeline()` |
| **Display surfaces** | T0 今日 (primary), T1 盤中 (validity check), T8 歷史 (historical) |
| **Loader** | `load_db_recommendations(date)` TTL=1800s |
| **Freshness shown** | Partial — "前收盤"/"收盤" label per price; `freshness_html` if `days_old > 1` |
| **Provenance gap** | No header label "訊號日期: {date}" on main card |

---

### EOD_PRICE

| Attribute | Value |
|---|---|
| **Source table** | `daily_prices` |
| **Date column** | `date` |
| **Max date** | 2026-11-05 (as of audit) |
| **Source origin** | TWSE/TPEx via `backfill_daily_prices.py` → cron |
| **Fetched time** | Cron 16:00 CST; backfill post-market |
| **Display surfaces** | T2 看盤 (chart), T3 持倉 (P&L), T7 個股 (chart) |
| **Loader** | `load_price_chart_data(stock_id)` TTL=600s; `load_stock_prices()` TTL=300s |
| **Freshness shown** | Sidebar: `st.caption("最新：{newest}")` only |
| **Provenance gap** | No "as-of YYYY-MM-DD" label on chart axis or header |

---

### ANALYSIS_SCORE

| Attribute | Value |
|---|---|
| **Source table** | `analysis_results` |
| **Date column** | `date` (trading day of analysis) |
| **Generation time** | Same cron run as TRADE_SIGNAL (main.py pipeline) |
| **Display surfaces** | T2 看盤 (PriceTrend banner, MA row), T6 進場時機 (V2 research) |
| **Loader** | `load_latest_pt_analysis(stock_id)` TTL=600s |
| **Score fields** | `price_trend_score`, `timing_score`, `quality_score`, `setup_type`, `ma20_gap`, `volume_ratio` |
| **Date returned** | Yes — `row.date` returned in dict |
| **Freshness shown** | None — `analysis["date"]` available but NOT rendered in market_watch.py |
| **Provenance gap** | PriceTrend score shown without "分析日: {date}" label |

---

### LIVE_QUOTE

| Attribute | Value |
|---|---|
| **Source** | TWSE MIS API (`api.mis.twse.com.tw`) |
| **Data structure** | `IntradayQuote` dataclass |
| **Freshness fields** | `update_time: str` (HH:MM:SS TW), `trade_date: str` (YYYYMMDD), `fetched_at: str` |
| **Stale detection** | `quote_date_status()` → "valid" if `trade_date == today`, "stale" otherwise |
| **Display surfaces** | T1 盤中 (live price cards, entry evaluation) |
| **Cache** | In-memory `_cache_ts`, TTL = 60s (live refresh) |
| **Freshness shown** | Yes — session label "盤中"/"收盤後"; valid/stale per quote |
| **Provenance gap** | `fetched_at` shown per card? Unclear — not in examined code |

---

### FORWARD_SIGNAL

| Attribute | Value |
|---|---|
| **Source table** | `forward_signals` (SQLite) + `neon_forward_signals` (Neon) |
| **Date column** | `trade_date` (signal execution date), `signal_date` (analysis date) |
| **Generation** | `main.py::run_pipeline()` creates ForwardSignal from Recommendation |
| **Display surfaces** | T4 證據 (outcome evaluation), T5 研究回測 (OOS set), T6 進場時機 |
| **IS/OOS split** | `RESEARCH_CUTOFF_DATE = 2026-10-09` |
| **Model version** | `model_version = "v8.0"` |
| **Freshness shown** | T5: shows cutoff date; T4/T6: no max ForwardSignal date |
| **Provenance gap** | No "最新訊號日期: {max_trade_date}" on T4/T5/T6 |

---

### OUTCOME_EVAL

| Attribute | Value |
|---|---|
| **Source table** | `forward_outcome_evaluations` |
| **Protocol** | `foe_v1` — pre-registered, immutable |
| **Date columns** | Derived from ForwardSignal `trade_date` + hold period |
| **Display surfaces** | T4 證據 |
| **Last evaluated** | Unknown (no explicit `evaluated_at` column in schema) |
| **Freshness shown** | No — only sample counts and performance stats |
| **Provenance gap** | No "最後評估日期" shown; user cannot tell if outcomes are up-to-date |

---

### OVERNIGHT_RISK

| Attribute | Value |
|---|---|
| **Source table** | `overnight_market_contexts` |
| **Date columns** | `execution_date` (TW date), `us_market_date` (US date), `fetched_at` (UTC), `available_at` (UTC) |
| **Generation** | `live_background_service.run_once()` pre-market |
| **Display surfaces** | T1 盤中 (risk level badge) |
| **Freshness shown** | `data_quality` shown (COMPLETE/PARTIAL/STALE/UNKNOWN); `fetched_at` NOT shown |
| **Provenance gap** | User sees "YELLOW" risk without knowing context was fetched 8 hours ago |

---

### CANDIDATE_POOL

| Attribute | Value |
|---|---|
| **Source table** | `candidate_pool_entries` |
| **Date columns** | `first_seen_date`, `last_checked_date`, `exit_date` |
| **Display surfaces** | T0 今日 (candidate cards) |
| **Freshness shown** | Yes — `as_of_label = "{as_of_date} 分析日資料"` shown as caption |
| **Provenance gap** | Minor — label format is acceptable |

---

## 3. Provenance Chain Diagram

```
TWSE/TPEx
    ↓ backfill_daily_prices.py (cron 16:00 CST)
    ↓
daily_prices (SQLite)
    ├── → EOD_PRICE  → T2 看盤 (chart) [NO freshness label]
    ├── → load_stock_prices() → TRADE_SIGNAL price field → T0 今日 [partial label]
    └── → analysis pipeline (main.py run_pipeline)
              ↓
         analysis_results (SQLite)
              ├── → ANALYSIS_SCORE → T2 看盤 (PriceTrend) [NO date label]
              └── → recommendations (SQLite)
                        ├── → TRADE_SIGNAL → T0 今日 [partial freshness]
                        └── → forward_signals (SQLite)
                                  ├── → FORWARD_SIGNAL → T5 研究 [cutoff shown]
                                  └── → forward_outcome_evaluations
                                              → OUTCOME_EVAL → T4 證據 [NO date]

TWSE MIS API (live)
    ↓ intraday_collector.fetch_intraday()
    → LIVE_QUOTE → T1 盤中 [GOOD freshness]

Yahoo Finance API (overnight)
    ↓ live_background_service.run_once()
    → overnight_market_contexts
    → OVERNIGHT_RISK → T1 盤中 [partial freshness]
```

---

## 4. Single Source of Truth per Signal Type

| Signal | SSOT Table | SSOT Date Column | Notes |
|---|---|---|---|
| EOD prices | `daily_prices` | `date` | DO NOT use `analysis_results.date` for price freshness |
| AI trade signal | `recommendations` | `date` | signal date ≠ price date |
| Technical scores | `analysis_results` | `date` | same date as recommendations |
| Live quotes | TWSE MIS API | `trade_date` (IntradayQuote) | ephemeral, in-memory only |
| Forward signals | `forward_signals` | `trade_date` | model_version must match |
| Outcomes | `forward_outcome_evaluations` | derived from ForwardSignal | foe_v1 frozen |
| Overnight risk | `overnight_market_contexts` | `execution_date` | `fetched_at` for provenance |

---

## 5. Cross-Surface Consistency Risk

| Risk | Scenario | Severity |
|---|---|---|
| Price divergence | T0 shows "BUY at 870" (from 2026-11-05 analysis) but T2 chart shows same 870 price with no date indicator | HIGH — user may think 870 is today's price |
| Score divergence | T2 shows "breakout" PriceTrend from 2026-11-05 but stock may have broken down since | HIGH |
| Live vs EOD confusion | User checks T2 during market hours, sees static K-chart from 5 days ago | HIGH |
| Signal vs execution date | NEXT_OPEN architecture: signal_date = Nov 5, execution_date = Nov 6. T0 shows Nov 5 signal, T1 tracks Nov 6 execution | MEDIUM (by design but not explained in UI) |

---

## 6. Verdict

| Category | Status |
|---|---|
| Provenance completeness | PARTIAL — 4/8 signal types have adequate freshness labels |
| Highest risk gap | EOD_PRICE on T2 看盤 (no chart date indicator) |
| Best existing pattern | LIVE_QUOTE in T1 (fully labeled: session + valid/stale) |
| Reference for contract | `IntradayQuote.trade_date` + `quote_date_status()` = good model |
| Implementation complexity | LOW — all fixes are display-only |
