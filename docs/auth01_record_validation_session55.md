# AUTH01 Record-level Source Validation — Session 55

**Verdict**: AUTH01_PARTIAL

## Priority Classification

| Date | Priority | Action | TWSE Verified Stocks | Coverage | Auth Status |
|------|----------|--------|---------------------|----------|-------------|
| 2026-10-29 | P1 | INSERT_CANDIDATE | 2330, 2454, 2317 (3 stocks) | 0.43% | PENDING |
| 2026-10-30 | P1 | INSERT_CANDIDATE | 2330, 2454 (2 stocks) | 0.29% | PENDING |
| 2026-11-02 | P1 | INSERT_CANDIDATE | 2330 (1 stock) | 0.14% | PENDING |
| 2026-11-03 | P1 | INSERT_CANDIDATE | 2317 (1 stock) | 0.14% | PENDING |
| 2026-11-04 | P1 | SKIP_EXISTING | (6956 rows present) | ~99% | READY |
| 2026-11-05 | P1 | SKIP_EXISTING | (6588 rows present) | ~94% | READY |
| 2026-11-06 | P2 | INSERT_CANDIDATE | 2330, 2454 (2 stocks) | 0.29% | PENDING |
| 2026-11-09 | P2 | INSERT_CANDIDATE | 2330, 2454 (2 stocks) | 0.29% | PENDING |

## Record-level Detail (Verified Records Only)

| Date | Stock | Exchange | Type | Close | Source | Action |
|------|-------|----------|------|-------|--------|--------|
| Oct29 | 2330 | TWSE | ordinary_stock | 2415.0 | TWSE_SINGLE_STOCK_S50 | INSERT_CANDIDATE |
| Oct29 | 2454 | TWSE | ordinary_stock | 4045.0 | TWSE_SINGLE_STOCK_S50 | INSERT_CANDIDATE |
| Oct29 | 2317 | TWSE | ordinary_stock | 248.0 | TWSE_SINGLE_STOCK_S50 | INSERT_CANDIDATE |
| Oct30 | 2330 | TWSE | ordinary_stock | 2370.0 | TWSE_SINGLE_STOCK_S50 | INSERT_CANDIDATE |
| Oct30 | 2454 | TWSE | ordinary_stock | 3915.0 | TWSE_SINGLE_STOCK_S50 | INSERT_CANDIDATE |
| Nov02 | 2330 | TWSE | ordinary_stock | 2330.0 | TWSE_SINGLE_STOCK_S50 | INSERT_CANDIDATE |
| Nov03 | 2317 | TWSE | ordinary_stock | 245.0 | TWSE_SINGLE_STOCK_S50 | INSERT_CANDIDATE |
| Nov06 | 2330 | TWSE | ordinary_stock | 2135.0 | TWSE_SINGLE_STOCK_S50 | INSERT_CANDIDATE |
| Nov06 | 2454 | TWSE | ordinary_stock | 3390.0 | TWSE_SINGLE_STOCK_S50 | INSERT_CANDIDATE |
| Nov09 | 2330 | TWSE | ordinary_stock | 2200.0 | TWSE_SINGLE_STOCK_S50 | INSERT_CANDIDATE |
| Nov09 | 2454 | TWSE | ordinary_stock | 3450.0 | TWSE_SINGLE_STOCK_S50 | INSERT_CANDIDATE |

## Universe Coverage Analysis

**Important**: These 11 records represent 3 stocks across 8 dates. Full universe coverage is ~700 stocks/date.

| Property | Status |
|----------|--------|
| ETFs excluded | ✓ (all verified records are ordinary_stock) |
| TPEx coverage | SOURCE_UNVERIFIED (all dates) |
| Corporate action check | NOT COMPLETED |
| Single-stock ≠ full coverage | Explicitly noted |

## Idempotency Dry-run (Temp SQLite)

| Test | Result |
|------|--------|
| Insert-only | PASS |
| Idempotent re-insert | PASS (0 rows changed) |
| Conflict (different values) | PASS (INSERT OR IGNORE) |
| Transaction rollback | PASS |
| Read-back | PASS |
| Coverage recalculation | PASS |
| Production modified | False ✓ |

## Blockers for Full Coverage

1. **TPEx UNVERIFIED**: No TPEx single-stock endpoint tested (SOURCE_UNVERIFIED for all dates)
2. **Sample coverage only**: 3 stocks / ~700 universe = 0.43% per date maximum
3. **AUTH01 pending**: User authorization required before production INSERT
4. **Corporate actions**: Not checked for any candidate record
5. **P2 dates**: Nov06/09 also need TWSE_HIST_URL replacement (RC-02 fix)

## Module

`src/research/tpex_patch_verification_s55.py` — PART E
