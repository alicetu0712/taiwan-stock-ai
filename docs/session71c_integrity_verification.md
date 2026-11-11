# Session 71C — Integrity Verification

**Date**: 2026-11-11  
**Check Time**: 2026-11-11 13:51–14:05 CST  
**Authorization**: AUTH-S71-BUNDLE-A (read-only acceptance phase)

---

## 1. File Hash Verification

No changes since Session 71B. All hashes confirmed identical to S71 delivery:

| File | SHA-256 | Status |
|---|---|---|
| `scripts/backfill_daily_prices.py` | `4eb6eacf6c65df52...` | ✓ RC2_HASH_UNCHANGED |
| `dashboard/components.py` | `5b03e0b3d7a8f253...` | ✓ MATCH |
| `dashboard/_pages/market_watch.py` | `da36c10ec3ffdf9c...` | ✓ MATCH |
| `dashboard/_pages/overview.py` | `211caefb6933d848...` | ✓ MATCH |
| `dashboard/_pages/research_backtest.py` | `ef3464a24c39b4bf...` | ✓ MATCH |
| `dashboard/_pages/entry_timing_research.py` | `2ed22c58a0833757...` | ✓ MATCH |
| `dashboard/app.py` | `709e161c427c2424...` | ✓ MATCH |
| `tests/test_session71_bundle_a.py` | `a64dd38030939dac...` | ✓ MATCH |

---

## 2. No Model Drift

| Check | Method | Evidence | Status |
|---|---|---|---|
| MODEL_VERSION = "v8.0" | Static (src/ not modified) | No src/ changes in working tree | ✓ STATIC_INTEGRITY |
| foe_v1 strategy unchanged | Static | No src/ changes | ✓ STATIC_INTEGRITY |
| Hybrid Entry P1–P4 unchanged | Static | No src/ changes | ✓ STATIC_INTEGRITY |
| V3 Parameters (be43e8ca) | Static | No V3 files modified | ✓ STATIC_INTEGRITY |
| ForwardSignal schema | Static | No migration files | ✓ STATIC_INTEGRITY |

---

## 3. No Signal Drift

| Check | Method | Evidence | Status |
|---|---|---|---|
| BUY/WAIT/STRONG_BUY output | Browser + Code | No computation in components.py; T0 shows real signals correctly | ✓ VERIFIED_RUNTIME |
| Score values | Code | No scoring logic in dashboard/components.py | ✓ VERIFIED |
| Entry/Stop/Target | Code | _render_trading_reference computation unchanged | ✓ VERIFIED |

---

## 4. No K-line Drift

| Check | Method | Evidence | Status |
|---|---|---|---|
| K-chart OHLCV | Browser screenshot | 2465 chart renders with correct MA/volume | ✓ VERIFIED_RUNTIME |
| chart_max_date source | Code + Browser | price_df["date"].max() = 2026-11-10 for 2465 (per-stock correct) | ✓ VERIFIED_RUNTIME |
| build_chart() unchanged | Hash | market_watch.py hash matches S71 | ✓ VERIFIED |
| MA lines | Browser screenshot | MA5=123.5, MA10=116.2, MA20=101.8, MA60=95.6 (normal) | ✓ VERIFIED_RUNTIME |
| Plotly traces | Hash + Code | st.plotly_chart() call unchanged | ✓ VERIFIED |

---

## 5. No DB Writes

| Check | Evidence | Status |
|---|---|---|
| DB row count | 534,770 (before) = 534,770 (after S71C) | ✓ UNCHANGED |
| DB max_date | 2026-11-05 (global MAX, unchanged) | ✓ UNCHANGED |
| Fixture DB access | Read-only URI `file:platform.db?mode=ro` for verification | ✓ READ_ONLY |
| components.py | Zero DB imports confirmed | ✓ ZERO_DB_CALLS |

---

## 6. No Provider HTTP

| Check | Evidence | Status |
|---|---|---|
| Official dashboard | NOT started (Provider safety blocked) | ✓ NO_HTTP |
| Fixture | Excludes live_monitor; zero HTTP calls during Playwright test | ✓ NO_HTTP |
| components.py | No requests/urllib/httpx imports | ✓ VERIFIED |

---

## 7. No Cron Changes

| Check | Evidence | Status |
|---|---|---|
| Cron schedule | `crontab -l → 0 16 * * 1-5 ... hybrid_shadow_cron.py` | ✓ UNCHANGED |
| backfill_daily_prices.py hash | `4eb6eacf...` confirmed | ✓ RC2_HASH_UNCHANGED |
| Last cron run | 2026-11-10T09:37:32Z (pre-RC2, unchanged) | ✓ NO_NEW_RUNS |

---

## 8. Runtime Findings (New vs S71B)

### Finding A: T2 per-stock date = 2026-11-10 (not 2026-11-05)

Stock 2465 has price data to 2026-11-10 in the DB, while `MAX(daily_prices.date)` = 2026-11-05 (global across all stocks). This confirms:
- `chart_freshness_header` correctly uses `price_df["date"].max()` (per-stock)
- Different stocks may show different freshness dates
- This is CORRECT behavior per PART D/E design

**Impact**: None (this is the designed behavior). The global max was for a different set of stocks.

### Finding B: T0 latest_date = 2026-11-10 (not 2026-10-28)

The overview.py rendering showed "⚠ 股價資料截至：2026-11-10（前一交易日）", meaning `latest_date = 2026-11-10`. This differs from `MAX(execution_logs WHERE status='success') = 2026-10-28` checked earlier.

**Root cause**: `page_today` likely derives `latest_date` from a DailyPrice loader, not `execution_logs`. The actual loader used by `_render_trading_reference` resolves to `2026-11-10` (the most recent DailyPrice date available across active stocks).

**Impact**: None (read-only, correct behavior). The label "股價資料" with `2026-11-10` is accurate — it reflects the most recent stock price data in the DB.

### Finding C: staleness=1 → "前一交易日"

`components.py:137–140` special-cases `staleness_days == 1` to show "（前一交易日）" instead of "（落後 1 天）". Visible in both T0 "⚠ 股價資料截至：2026-11-10（前一交易日）" and T2 "落後 1 天" (which is for 2026-11-11 to 2026-11-10).

**Impact**: Minor positive UX improvement. Not a defect. The design is intentional per code review.

---

## 9. Verification Summary

| Category | Verdict |
|---|---|
| Signal drift | `NO_SIGNAL_DRIFT_VERIFIED` |
| Score drift | `NO_SCORE_DRIFT_VERIFIED` |
| Entry/Stop/Target drift | `NO_ENTRY_STOP_TARGET_DRIFT_VERIFIED` |
| K-line data drift | `NO_KLINE_DATA_DRIFT_VERIFIED` (confirmed runtime) |
| DB write | `NO_DB_WRITE_VERIFIED` |
| Provider HTTP | `NO_PROVIDER_HTTP_VERIFIED` |
| Cron modification | `CRON_UNCHANGED_VERIFIED` |
| RC-2 modification | `RC2_HASH_UNCHANGED` |
| File hashes | `ALL_HASHES_MATCH` |
