# TPEx Source Contract — Session 57

**Session ID**: S57  
**Date**: 2026-11-10  
**Status**: TPEX_SOURCE_NOT_FEASIBLE

---

## Critical Finding

The TPEx bulk endpoint **ignores the `?d=` date parameter entirely**.
Requesting historical data returns today's data with today's api_date.
This is a design constraint of the endpoint, not a bug.

---

## Source Contract

| Attribute | Value |
|-----------|-------|
| URL | `https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes?d={RRRMMDD}` |
| Date Format | RRRMMDD (ROC year, e.g. 1151029 for 2026-10-29) |
| Date Semantics | **DATE_PARAM_IGNORED** |
| Historical Availability | **LATEST_ONLY** |
| OHLCV Availability | **FULL_OHLCV_NO_VOLUME** (open/high/low/close present; volume=NULL all records) |
| Typical Stock Count | 5737 (includes warrants, ETFs, preferred shares) |
| Exchange Coverage | TPEx only |

---

## S57 Live Probe Evidence

**Test 1 — Requested Oct29 (ROC: 1151029)**:
```
GET tpex_mainboard_daily_close_quotes?d=1151029
→ rows=5737, api_date=2026-11-10
→ Sample: 006201 (元大富櫃50): open=33.91, high=35.5, low=33.91, close=35.44, volume=None
Date match: api_date=2026-11-10 ≠ requested 2026-10-29 → FALSE
```

**Test 2 — Requested Nov04 (ROC: 1151104)**:
```
GET tpex_mainboard_daily_close_quotes?d=1151104
→ rows=5737, api_date=2026-11-10
Date match: api_date=2026-11-10 ≠ requested 2026-11-04 → FALSE
```

Both tests requested different historical dates and both returned `api_date=2026-11-10`.
The endpoint is named `daily_close_quotes` (not `historical_quotes`), confirming by design it returns
only the latest market day.

---

## Root Cause Confirmation

**RC-03** (TPEX_HIST_URL): **DIRECTLY_CONFIRMED**

The TPEx api_date mismatch error first observed in Session 50/51 is confirmed to be
a structural design constraint: the endpoint cannot return historical data.
The S55 TPEx patch (L500-503) correctly captures this in `summary["errors"]` after deployment,
but it cannot fix the underlying missing historical data.

---

## Volume Availability

TPEx volume is **NULL for ALL 5737 records** regardless of which date is requested.
This is a known limitation of the `tpex_mainboard_daily_close_quotes` endpoint:
it returns close price data only (despite having open/high/low fields).

This explains Nov04/05 `volume_null_rows=5715` in `daily_prices`:
those are TPEx records with structural NULL volume.

---

## Impact on Data Recovery

| Scenario | Feasibility |
|----------|-------------|
| TPEx bulk historical backfill | NOT_FEASIBLE |
| TPEx latest (cron, same-day) | FEASIBLE (but volume=NULL always) |
| TPEx per-stock historical API | UNVERIFIED (not tested in S57) |

For historical recovery: TPEx ordinary stocks that are cross-listed on TWSE
may be retrievable via TWSE_SINGLE_STOCK. Pure TPEx stocks require
alternative per-stock endpoint or TPEx OpenAPI historical endpoint (if one exists).

---

## TPEx Patch Authorization

The 2-line patch (L500-503 of `scripts/backfill_daily_prices.py`) remains
**DEPLOYMENT_READY** per S56 analysis:
- 15/15 scenarios pass
- Behavioral equivalence verified
- Adds `msg` variable + `summary["errors"].append(msg)` for api_date mismatch
- Rollback: trivial (remove 2 lines)

**This patch improves observability but does not fix the missing TPEx historical data.**

---

## Verdict

| Component | Status |
|-----------|--------|
| TPEx bulk historical | NOT_FEASIBLE (date param ignored) |
| TPEx volume | ALWAYS_NULL (endpoint design) |
| TPEx per-stock historical | UNVERIFIED |
| **Overall TPEx** | **TPEX_SOURCE_NOT_FEASIBLE** (for historical recovery) |
| TPEx patch deployment | DEPLOYMENT_READY (observability only) |
