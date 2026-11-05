# TWSE Provider Root Cause Diagnosis

**Analysis Date:** 2026-11-05  
**Taiwan Time:** 2026-11-05 ~19:30 CST  
**Session:** 12  
**Git HEAD:** 1c42cb3  
**Trigger:** BLOCKED_PARTIAL_MARKET on manual test run at 18:28 CST Nov 5

---

## Observation

During the Session 9 manual test run (18:28 CST Nov 5) and Session 11 preflight (19:16 CST Nov 5), `backfill_daily_prices.py` attempted to fetch 2026-11-05 market data from TWSE. The API returned `api_date=2026-11-04` both times. The quality gate (QG-5) blocked the write. The freshness gate reported `BENCHMARK_ONLY_UPDATED`, resulting in `BLOCKED_PARTIAL_MARKET`.

Meanwhile, `0050` was present in `daily_prices` for 2026-11-05 (1 row, close=97.15), while all other stocks were still at 2026-11-04 (6,957 rows).

---

## Root Cause

### 1. Origin of the solitary 0050 Nov 5 row

`recover_ohlc_0050.py --execute` was run during the OHLC Continuity Gate session (commit `1c42cb3`). Its `RECOVERY_TARGETS` list includes `date(2026, 11, 5)`:

```python
(date(2026, 11, 5),  "2026-11-05 (confirmed TWSE trading, index=41,574.72)"),
```

This script uses a **per-stock** TWSE endpoint:
```
https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?stockNo=0050&date=YYYYMMDD
```

This endpoint returns individual-stock monthly history and **publishes faster** than the batch endpoint. It successfully returned 0050 Nov 5 data at the time of the OHLC recovery run.

### 2. Why TWSE batch returned Nov 4 at 19:16 CST Nov 5

`backfill_daily_prices.py` uses the batch endpoint, not the per-stock endpoint:

| Attempt | URL | Behavior |
|---|---|---|
| Primary | `twse.com.tw/exchangeReport/STOCK_DAY_ALL?date=YYYYMMDD` | Returns stat="no data" or previous day if not ready |
| Fallback | `openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL` | Always returns "most recent published day" |

At 18:28–19:16 CST Nov 5, the TWSE OpenAPI fallback returned `api_date=2026-11-04` — the most recently published day. The full-market batch for 2026-11-05 had not yet been published.

**This is expected behavior.** TWSE publishes the full-market batch after post-market processing, which can extend to 19:00–20:00+ CST on some days.

### 3. QG-5 correctly blocked the write

```python
if twse_api_date and twse_api_date != target_d:
    msg = f"{target_d}: TWSE api_date={twse_api_date} != target — API returned wrong date"
    summary["errors"].append(msg)
    # Don't abort — still run quality gate so it fails on QG-5
```

QG-5 compares every row's date to `target_date`. Since all rows had `date=2026-11-04` and `target=2026-11-05`, all rows failed QG-5. The write was correctly blocked.

---

## State Resulting from Recovery

| Stock | Nov 5 | Nov 4 | Source |
|---|---|---|---|
| 0050 | ✅ 1 row (close=97.15) | ✅ 1 row | `recover_ohlc_0050.py` → `TWSE_STOCK_DAY_API` |
| All others (6,957) | ❌ 0 rows | ✅ 6,957 rows | `backfill_daily_prices.py` → `STOCK_DAY_ALL` |

This is the documented "0050 manually recovered" scenario. The backfill script's `_default_start()` correctly identifies this via `_MIN_COVERED_STOCKS = 1,000`:

```
last_covered_date = 2026-11-04 (last date with >= 1,000 non-0050 stocks)
default_start for Nov 6 cron = 2026-11-05
missing_dates_to_fetch = [2026-11-05, 2026-11-06]
```

---

## Impact on Nov 6 First Scheduled Run

### Expected timeline

| Time (CST) | Action | Expected Outcome |
|---|---|---|
| 16:00 | Cron fires; backfill tries Nov 5 + Nov 6 | Nov 5 may succeed; Nov 6 not ready → PROVIDER_NOT_READY |
| 16:30 | Retry 1; backfill re-runs | Nov 6 may still not be ready |
| 17:00 | Retry 2 | TWSE may start publishing |
| 17:30 | Retry 3 (final) | If FULL_MARKET_FRESH → SUCCESS; else BLOCKED |

### Risk

Based on the Nov 5 observation (TWSE batch not published at 19:16 CST), the TWSE OpenAPI may publish the Nov 6 batch **after the retry window ends (17:30)**. If that occurs:

- Pipeline status: `BLOCKED_STALE_DATA` or `BLOCKED_PARTIAL_MARKET`
- Alert: `STALE_DATA` or `PARTIAL_MARKET` recorded in `data/.alert_state.json`
- Exit code: 0 (normal fail-closed, not a crash)
- No PROSPECTIVE decisions written (shadow not invoked)
- **Manual recovery option:** Run `python scripts/backfill_daily_prices.py --execute` and `python scripts/hybrid_shadow_cron.py --execute` after TWSE publishes

### Mitigation options (for future consideration, not implementing now)

| Option | Trade-off |
|---|---|
| Extend retry window (RETRY_MAX=6, 60-min intervals, up to 23:30) | Longer lock hold; less urgent for research system |
| Poll TWSE at shorter intervals (15 min) | More API calls; risk of rate limiting |
| Run cron at 20:00 instead of 16:00 | Misses early-evening publishing; loses market-close-fresh decisions |
| Use per-stock batch approach (like `recover_ohlc_0050.py`) for all stocks | Much higher API load (826 individual calls); TWSE rate limiting risk |

**Current recommendation:** Accept the risk for now. If Nov 6 blocks, run manual backfill+shadow after TWSE publishes. Gather empirical data on TWSE publishing times across 5 trading days before adjusting retry policy.

---

## Verdict

| Finding | Conclusion |
|---|---|
| 0050 Nov 5 isolated row | **Expected** — written by `recover_ohlc_0050.py` using per-stock endpoint |
| TWSE batch returning Nov 4 at 19:16 | **Expected** — TWSE publishes full-market batch late; QG-5 correctly blocked write |
| Backfill logic | **Correct** — QG-5 guard, `_default_start()` with `_MIN_COVERED_STOCKS` both working |
| Nov 6 cron risk | **Present** — retry window (16:00–17:30) may end before TWSE publishes |
| System health | **No defects found** — all gates working as designed |

---

## Appendix — TWSE Endpoint Comparison

| Endpoint | Type | Updates | Used By |
|---|---|---|---|
| `twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?stockNo=0050` | Per-stock monthly history | Relatively fast | `recover_ohlc_0050.py` |
| `twse.com.tw/exchangeReport/STOCK_DAY_ALL?date=YYYYMMDD` | Full-market historical | Day-specific; slow | `backfill_daily_prices.py` (primary) |
| `openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL` | Full-market "today" | Published late (19:00+?) | `backfill_daily_prices.py` (fallback) |
