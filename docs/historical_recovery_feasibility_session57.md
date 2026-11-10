# Historical Recovery Feasibility — Session 57

**Session ID**: S57  
**Date**: 2026-11-10  
**Status**: RECOVERY_FEASIBLE_WITH_CAUTION (TWSE single-stock only; TPEx NOT_FEASIBLE)

---

## Recovery Approach Decision Tree

```
Can TWSE_BULK_HIST provide historical data?
  → NO (endpoint returns non-JSON for recent dates)

Can TWSE_LATEST_URL provide historical data?
  → NO (always returns latest trading day)

Can TWSE_SINGLE_STOCK provide historical data?
  → YES (S50 confirmed for Oct29/30/Nov02/03)
  → FEASIBLE_WITH_CAUTION (~1969 calls/date, rate limit unverified)

Can TPEx_BULK provide historical data?
  → NO (endpoint ignores date parameter, always returns today)

Can TPEx_SINGLE_STOCK provide historical data?
  → UNVERIFIED (not tested in S57)
```

---

## Recovery Feasibility Matrix

| Date | Tier | Feasibility | Requests | Time (min) | OHLCV Quality | Auth |
|------|------|-------------|----------|------------|---------------|------|
| Oct29 | T2 TWSE single | FEASIBLE_VERIFIED | 1969 | 65.6 | FULL OHLCV+V | AUTH01 PENDING |
| Oct30 | T2 TWSE single | FEASIBLE_VERIFIED | 1969 | 65.6 | FULL OHLCV+V | AUTH01 PENDING |
| Nov02 | T2 TWSE single | FEASIBLE_VERIFIED | 1969 | 65.6 | FULL OHLCV+V | AUTH01 PENDING |
| Nov03 | T2 TWSE single | FEASIBLE_VERIFIED | 1969 | 65.6 | FULL OHLCV+V | AUTH01 PENDING |
| Nov06 | T2 TWSE single | FEASIBLE_WITH_CAUTION | 1969 | 65.6 | FULL OHLCV+V expected | AUTH01 PENDING |
| Nov09 | T2 TWSE single | FEASIBLE_WITH_CAUTION | 1969 | 65.6 | FULL OHLCV+V expected | AUTH01 PENDING |

**Total**: 6 dates × 1969 requests = 11,814 requests  
**Total time**: 6 × 65.6 min = ~6.6 hours  
**Risk level**: MEDIUM_HIGH (IP throttle possible; TWSE terms unverified)

---

## FEASIBLE_VERIFIED vs FEASIBLE_WITH_CAUTION

**FEASIBLE_VERIFIED** (Oct29/30/Nov02/03):
- S50 Session 50 manually verified TWSE single-stock returns correct date OHLCV
- Confirmed: 2330/2454/2317/2891/6505/3008 on Oct29; 2330/2454 on Oct30; 2330 on Nov02; 2317 on Nov03
- Full OHLCV+volume confirmed for 2330/2454/2317

**FEASIBLE_WITH_CAUTION** (Nov06/09):
- S50 only has CLOSE_ONLY data for Nov06/09 (2330/2454)
- TWSE single-stock should work for OHLCV (same API, same date range)
- Not explicitly verified with full OHLCV call in research scope

---

## Prerequisites for Full Recovery

Before executing T2 single-stock recovery, the following must be confirmed:

1. **AUTH01 authorized** — explicit authorization to write to production `daily_prices`
2. **TWSE rate limit policy** — official TWSE API terms of use verified
3. **Script modification** — `scripts/backfill_daily_prices.py` updated to use single-stock pattern
4. **TPEx handling decision** — accept NULL volume for TPEx-listed stocks OR find alternative
5. **Dedup strategy** — confirm INSERT OR IGNORE behavior for existing rows

---

## Expected Coverage After Full Recovery (TWSE Only)

| Date | Before | After T2 Recovery | TWSE Universe | Coverage | Notes |
|------|--------|-------------------|---------------|----------|-------|
| Oct29 | 1 (0050) | ~1969 | 1969 ordinary | ~100% TWSE | TPEx-exclusive stocks = unrecovered |
| Oct30 | 1 (0050) | ~1969 | 1969 | ~100% TWSE | Same |
| Nov02 | 1 (0050) | ~1969 | 1969 | ~100% TWSE | Same |
| Nov03 | 1 (0050) | ~1969 | 1969 | ~100% TWSE | Same |
| Nov06 | 0 | ~1969 | 1969 | ~100% TWSE | DATE_MISSING → recovered |
| Nov09 | 0 | ~1969 | 1969 | ~100% TWSE | DATE_MISSING → recovered |

TPEx-exclusive stocks (not cross-listed on TWSE): TPEx per-stock API UNVERIFIED.
Estimated TPEx-exclusive ordinary stocks: unknown (requires separate analysis).

---

## Partial Recovery Option (S50 Snapshots Only, No T2)

Using only existing S50 research snapshots:
- 6 stocks on Oct29 insertable immediately (after AUTH01)
- 2 stocks on Oct30, 1 on Nov02, 1 on Nov03
- Maximum coverage: 0.30% (Oct29)
- QG impact: NONE — far below any QG threshold

**This option has research value as a proof-of-insert test,
but does NOT meaningfully recover coverage.**

---

## Impact on Research Quality Gates

| Gate | Before Recovery | After Full T2 Recovery | Change |
|------|----------------|----------------------|--------|
| G01 Data Coverage | FAIL (Oct29–Nov09 dates missing/benchmark-only) | PASS expected | +6 dates |
| G02 Signal Coverage | FAIL (no price data for most signals) | CONDITIONAL | Depends on signal dates |
| G03 Genuine Prospective | FAIL (0/10) | FAIL (0/10) | NO CHANGE |
| G04 Weekly Spacing | STRUCTURAL_FAIL | STRUCTURAL_FAIL | NO CHANGE |

**Note**: G03 and G04 are unaffected by any data recovery. They require V3 activation and
algorithmic changes respectively.

---

## Verdict

| Dimension | Status |
|-----------|--------|
| TWSE historical recovery | FEASIBLE_VERIFIED (Oct29–Nov03), FEASIBLE_WITH_CAUTION (Nov06/09) |
| TPEx historical recovery | NOT_FEASIBLE (endpoint ignores date param) |
| Total time estimate | ~6.6 hours for 6 dates |
| Prerequisites met | NO (AUTH01 not authorized, TWSE terms unverified) |
| Blockers resolved | NONE without authorization |
| **Overall** | **RECOVERY_FEASIBLE_PENDING_AUTHORIZATION** |
