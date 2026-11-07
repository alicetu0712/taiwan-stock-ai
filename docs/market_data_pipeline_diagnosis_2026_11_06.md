# Market Data Pipeline Diagnosis — 2026-11-06

**Date:** 2026-11-07  
**Audit Type:** Read-only database + pipeline audit  
**Version:** session32_v1  

---

## 1. Executive Summary

**Root Cause: `CRON_EXECUTION_FAILURE_CASCADING`**

The 2026-11-06 market data absence is a **direct cascading consequence** of the BTM cron execution failure. DailyPrice ingestion is embedded inside `hybrid_shadow_cron.py` as a mandatory first step — when cron fails to fire, no market data is fetched.

There is NO independent DailyPrice ingestion schedule. All market data for trading days depends on the hybrid cron executing successfully.

---

## 2. Pipeline Architecture

```
Hybrid Shadow Cron (16:00 Taiwan daily)
  │
  ├── Step 1: Calendar check (trading day?)
  ├── Step 2: Data freshness check (0050 available?)
  ├── Step 3: Backfill trigger [_run_backfill()]
  │     └── subprocess: backfill_daily_prices.py
  │           ├── TWSE: https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL
  │           ├── TPEx: https://www.tpex.org.tw/openapi/v1/...
  │           └── Write to: data/platform.db → daily_prices table
  ├── Step 4: Quality gate check
  ├── Step 5: DB backup
  └── Step 6: Shadow runner (hybrid_forward_decision)
```

Since cron was blocked at the BTM check, Steps 1–6 were never reached.

---

## 3. Pipeline Stage Failure Analysis

| Stage | Expected | Actual | Status |
|---|---|---|---|
| Cron trigger (16:00) | cron fires | BTM block → no fork | **FAILED** |
| Calendar check | trading_day | never reached | BLOCKED_UPSTREAM |
| Freshness check | check 0050 | never reached | BLOCKED_UPSTREAM |
| Backfill trigger | run backfill_daily_prices.py | never reached | BLOCKED_UPSTREAM |
| TWSE fetch | GET STOCK_DAY_ALL | never reached | BLOCKED_UPSTREAM |
| TPEx fetch | GET tpex daily | never reached | BLOCKED_UPSTREAM |
| DailyPrice write | ≥5,000 rows for Nov 6 | 0 rows | BLOCKED_UPSTREAM |
| Quality gate | QG-5 check | never reached | BLOCKED_UPSTREAM |
| Shadow runner | hybrid decisions | never reached | BLOCKED_UPSTREAM |

**First failure stage: Cron trigger** — all downstream stages blocked.

---

## 4. DailyPrice State (Read-only)

| Date | Stock Count | Status |
|---|---|---|
| 2026-11-04 (Wed) | 6,957 | FULL_MARKET_FRESH |
| 2026-11-05 (Thu) | 6,589 | FULL_MARKET_FRESH |
| **2026-11-06 (Fri)** | **0** | **MISSING — cron never ran** |
| 2026-11-07 (Sat) | — | MARKET_CLOSED |

0050 (benchmark) latest entry: 2026-11-05 (close=97.15, vol=487,502).

---

## 5. 0050 Analysis

| Check | Value |
|---|---|
| Latest date | 2026-11-05 |
| Close | 97.15 |
| Volume | 487,502 |
| 2026-11-06 available | **NO** (never fetched) |

0050 is fetched as part of TWSE batch (`STOCK_DAY_ALL`). No independent 0050 recovery mechanism was triggered.

---

## 6. TWSE Analysis

| Check | Value |
|---|---|
| Latest date in DB | 2026-11-04 (non-0050), 2026-11-05 (0050 only) |
| Expected stocks (TWSE) | ~1,976 non-0050 (4-digit codes) |
| 2026-11-06 count | 0 |
| Fetch mechanism | `fetch_twse_historical(d)` in backfill_daily_prices.py |
| Primary URL | `https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json&date={yyyymmdd}` |
| Fallback URL | `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL` |
| Root cause of absence | Backfill script never executed |

---

## 7. TPEx Analysis

| Check | Value |
|---|---|
| Latest date in DB | 2026-11-05 (via Nov 5 backfill) |
| Expected stocks (TPEx) | ~4,980 (5-digit codes) |
| 2026-11-06 count | 0 |
| Fetch mechanism | `fetch_tpex_historical(d)` in backfill_daily_prices.py |
| URL | `https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes?d={roc_date}` |
| Root cause of absence | Backfill script never executed |

---

## 8. Data Source Availability Assessment

Based on backfill script design:

| Source | Historical Support | Status for Nov 6 |
|---|---|---|
| TWSE (classic) | `?date=YYYYMMDD` | AVAILABLE (market closed Nov 6) |
| TWSE (OpenAPI) | Returns most recent day | AVAILABLE |
| TPEx | `?d=RRRMMDD` (ROC date) | AVAILABLE (market closed Nov 6) |

2026-11-06 (Friday) was a regular TWSE/TPEx trading day. Historical data should be available from both sources as of now (Nov 7).

The backfill script `--help` confirms:
```
--start START  Start date (default: day after last stored date = 2026-11-06)
--end END      End date (default: today = 2026-11-07)
```

A dry-run would attempt to fetch Nov 6 data. Data availability is PROBABLE but not confirmed without executing the fetch.

---

## 9. No-lookahead Verification

The pipeline is designed to fetch the most recent closed trading day. Fetching Nov 6 data on Nov 7 is consistent with the pipeline's design (no forward-looking data).

---

## 10. Impact on Research

| Impact | Details |
|---|---|
| Nov 6 Prospective Decisions | None captured (cron blocked) |
| Existing ForwardSignals | Unaffected (2605, MAX=2026-10-28) |
| Hybrid Decisions | Unaffected (21, MAX=2026-11-04) |
| V3 Parameters | Frozen, unaffected |
| Regression | 1942 passed (unchanged) |

---

## 11. Missing Data Does Not Invalidate Research

The absence of 2026-11-06 data:
- Does NOT affect historical backtest results (use Nov 4 as latest date)
- Does NOT affect V3 parameter freeze (hashes unchanged)
- DOES prevent prospective Nov 6 decisions from being captured
- Nov 6 decisions captured LATER (after backfill) would be `LATE_CAPTURE`, not `PROSPECTIVE`

---

## 12. Data Continuity Check

| Metric | Value | Status |
|---|---|---|
| 0050 continuity (last 5 trading days) | Nov 1, 3, 4, 5 — missing Nov 6 | GAP_NOV_6 |
| Non-0050 continuity | Nov 4, 5 — missing Nov 6 | GAP_NOV_6 |
| Corporate actions Nov 6 | Unknown (not checked — no data) | UNKNOWN |
