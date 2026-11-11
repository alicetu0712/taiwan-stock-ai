# Session 71 — No-Drift Verification

**Date**: 2026-11-11  
**Authorization**: AUTH-S71-BUNDLE-A

---

## 1. Signal & Model Integrity

| Check | Evidence | Status |
|---|---|---|
| `MODEL_VERSION = "v8.0"` unchanged | `src/database.py:39` text verified | ✓ NO DRIFT |
| `build_chart(price_df, analysis or {}, stock_name)` call unchanged | Verified in market_watch.py source | ✓ NO DRIFT |
| `st.plotly_chart` config unchanged | `scrollZoom: True, displayModeBar: False` verified | ✓ NO DRIFT |
| `_render_ma_row(price_df)` call unchanged | price_df passed unmodified | ✓ NO DRIFT |
| No OHLCV mutation | components.py has no access to price data | ✓ NO DRIFT |
| Recommendation entries unchanged | `_render_trading_reference()` logic unchanged | ✓ NO DRIFT |
| Entry/Stop/Target unchanged | No computation in components.py | ✓ NO DRIFT |
| Candidate pool unchanged | `_render_candidate_pool()` not modified | ✓ NO DRIFT |
| `freshness_html` conditional logic preserved | Added BEFORE existing logic, not replacing | ✓ NO DRIFT |
| IS/OOS split preserved | `_CUTOFF_LABEL = "2026-10-09"` preserved | ✓ NO DRIFT |
| research_backtest tabs preserved | `tab_r, tab_f = st.tabs(...)` unchanged | ✓ NO DRIFT |
| V2 isolation note preserved | `V2 標籤不影響正式買賣決策` text verified | ✓ NO DRIFT |

---

## 2. Database Integrity

| Check | Before | After | Status |
|---|---|---|---|
| `daily_prices` row count | 534,770 | 534,770 | ✓ UNCHANGED |
| `daily_prices` max_date | 2026-11-05 | 2026-11-05 | ✓ UNCHANGED |
| DB write operations | 0 | 0 | ✓ ZERO WRITES |
| `components.py` DB calls | n/a | NONE (verified by test) | ✓ VERIFIED |

---

## 3. Cron Integrity

| Check | Evidence | Status |
|---|---|---|
| Cron schedule | `0 16 * * 1-5` unchanged | ✓ UNCHANGED |
| `hybrid_shadow_cron.py` not modified | `git diff` verified | ✓ UNCHANGED |
| `backfill_daily_prices.py` not modified | Hash `4eb6eacf...` verified | ✓ UNCHANGED |
| Cron import isolation | No `import dashboard` in cron | ✓ ISOLATED |

---

## 4. RC-2 Integrity

| Check | Expected | Actual | Status |
|---|---|---|---|
| SHA-256 of backfill_daily_prices.py | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | ✓ MATCH |

---

## 5. Provider HTTP Integrity

| Check | Evidence | Status |
|---|---|---|
| No HTTP in `components.py` | Grep for `requests`, `urllib`, `httpx`, `fetch_intraday` → 0 results | ✓ NO HTTP |
| No new Provider calls added to pages | Only `from dashboard.components import ...` added | ✓ NO HTTP |

---

## 6. Known Gaps (Not Regressions)

| Gap | Description | Impact |
|---|---|---|
| Calendar days vs trading days | `_staleness_days()` returns calendar days (not trading days). Label shows "落後 N 天" not "N 個交易日". | Display only — overstates by ~25% (6 calendar vs 4 trading days). Acceptable for a "stale" indicator. Future: use `TaiwanTradingCalendar` |
| T0 Price As-of proxy | `latest_date` = `MAX(ExecutionLog WHERE success)` ≠ per-stock price date. Used as proxy only. | PART F documented limitation. No new DB query added. The label "股價資料" with `latest_date` is accurate as a global proxy. |
| Streamlit render not visually verified | Tests mock `st.markdown`. Actual browser render not confirmed. | Must be confirmed by user in browser before accepting as fully compliant. |
| V3 not labeled as activated | V3 remains ACTIVATION_BLOCKED. No V3 banner added. | Correct — V3 is not activated. |

---

## 7. Verdict

| Category | Status |
|---|---|
| Signal drift | `NO_SIGNAL_DRIFT_VERIFIED` |
| Score drift | `NO_SCORE_DRIFT_VERIFIED` |
| Entry/Stop/Target drift | `NO_ENTRY_STOP_TARGET_DRIFT_VERIFIED` |
| K-line data drift | `NO_KLINE_DATA_DRIFT_VERIFIED` |
| DB write | `NO_DB_WRITE_VERIFIED` |
| Provider HTTP | `NO_PROVIDER_HTTP_VERIFIED` |
| Cron modification | `CRON_UNCHANGED_VERIFIED` |
| RC-2 modification | `RC2_HASH_UNCHANGED` |
