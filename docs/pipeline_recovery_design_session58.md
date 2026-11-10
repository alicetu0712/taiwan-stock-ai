# Pipeline Recovery Design — Session 58

**Status**: DESIGN_COMPLETE_PENDING_AUTHORIZATION  
**Date**: 2026-11-10

---

## Recovery Phases

### Phase 1: TPEx Patch (Minimal Risk, No New Auth Needed)

Apply the already-designed 2-line fix to `scripts/backfill_daily_prices.py`:

**L500-501 change**: Replace `print()` with `summary["errors"].append(msg)` for api_date mismatch.

**Additional fix** (discovered in S58): TPEx volume field mapping from `"TradeVolume"` to `"TradingShares"`.

This fixes error observability and NULL volume for future TPEx scrapes. Does not recover historical data.  
**Current state**: PRINT_ONLY_CONFIRMED. PATCH_DEPLOYMENT_READY. AUTH01 not required.

### Phase 2: TWSE Single-Stock Recovery (AUTH01 Required)

**Preconditions**:
1. TWSE rate limit policy confirmed
2. AUTH01 explicit authorization granted
3. Compliance terms confirmed

**Script design** (not implemented):
```
for month in ["202610", "202611"]:
    for stock_id in research_universe_599:
        fetch TWSE STOCK_DAY for stock_id/month
        parse OHLCV for gap dates: Oct29/Oct30 (Oct), Nov02/03/06/09 (Nov)
        insert into daily_prices (AUTH01 required before this step)
        sleep 2.0 seconds
```

**Runtime estimate**: ~1,198 calls × 2s = ~40 minutes  
**Rate limit risk**: UNVERIFIED — stop on HTTP 429 or 5+ consecutive failures

### Phase 3: Pipeline Continuity Recovery (AUTH01 Extended)

Populate `daily_prices` from Nov06 through Nov12 (required for Oct13 cluster 20D outcomes).

Same TWSE single-stock mechanism, additional months as needed.

### Phase 4: 20D Outcome Computation (AUTH02 Required)

After Phase 2-3 complete:
- Query `forward_signals` for Oct13 cluster (execution_date in Oct13-16)
- Look up `daily_prices` for execution_price (entry) and Nov12 price (exit)
- Compute 20D return and alpha per signal
- Store in designated output table (not `forward_signals`)

**AUTH02 not authorized. Phase 4 cannot begin.**

---

## Health Checks (From S57 HC-01 to HC-06)

| Check | Purpose | Priority |
|-------|---------|----------|
| HC-01: Minimum row count | Alert if daily_prices for today has < threshold rows | HIGH — would catch Nov06/09 gaps immediately |
| HC-02: Date coverage gate | Alert if any expected trading day is missing | HIGH |
| HC-03: TPEx api_date validation | Error propagation for date mismatch (Phase 1 patch) | MEDIUM |
| HC-04: Volume NULL rate | Alert if >50% of rows have NULL volume | MEDIUM |
| HC-05: OHLC sanity check | H≥O≥L, H≥C≥L for all new rows | MEDIUM |
| HC-06: Dedup check | Alert if any (stock_id, date) duplicate | LOW |

**None implemented. All pending authorization.**

---

## Recovery Estimate vs S57

| Item | S57 | S58 (Corrected) |
|------|-----|----------------|
| Calls per gap date | 1969 | N/A — monthly |
| Total calls | ~11,814 | ~1,198 |
| Runtime | ~6.6 hours | ~40 minutes |
| Denominator | 1969 | 599 |
| Data quality after | FEASIBLE | FULL OHLCV confirmed (5 stocks) |
