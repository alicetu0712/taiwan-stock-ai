# AUTH01 Backfill Impact Simulation — Session 56

**Verdict**: AUTH01_PARTIAL  
**Execution**: AUTH01_NOT_EXECUTED

## S56 New Findings (Critical)

| Finding | Detail |
|---------|--------|
| Expected ordinary universe | ~1969 (4-digit 1000-9999 stocks, Nov04 reference) |
| Total daily_prices on Nov04 | 6957 (includes ETFs, warrants, preferred shares) |
| S50 verified prices | CLOSE ONLY — OPEN/HIGH/LOW/VOLUME not available |
| Fabricated OHLCV | S55 module estimated OHLV from close (×0.99/×1.01/×0.98) |
| OHLCV completeness | CLOSE_ONLY for all candidates → DB schema requires full OHLCV |
| Stocks table | 826 entries, all TWSE — NOT a complete universe reference |

## Record-level Manifest

| Date | Priority | Action | Verified Stocks | Close Source | OHLCV State |
|------|----------|--------|----------------|-------------|-------------|
| Oct29 | P1 | INSERT_CANDIDATE | 2330, 2454, 2317 | TWSE_S50 | CLOSE_ONLY |
| Oct30 | P1 | INSERT_CANDIDATE | 2330, 2454 | TWSE_S50 | CLOSE_ONLY |
| Nov02 | P1 | INSERT_CANDIDATE | 2330 | TWSE_S50 | CLOSE_ONLY |
| Nov03 | P1 | INSERT_CANDIDATE | 2317 | TWSE_S50 | CLOSE_ONLY |
| Nov04 | P1 | SKIP_EXISTING | (6956 rows) | — | FULL_OHLCV |
| Nov05 | P1 | SKIP_EXISTING | (6588 rows) | — | FULL_OHLCV |
| Nov06 | P2 | INSERT_CANDIDATE | 2330, 2454 | TWSE_S50 | CLOSE_ONLY |
| Nov09 | P2 | INSERT_CANDIDATE | 2330, 2454 | TWSE_S50 | CLOSE_ONLY |

## Coverage Before/After (Ordinary Stocks, 4-digit 1000-9999)

| Date | Existing | Candidates | Simulated Total | Universe | Before % | After % | QG |
|------|----------|------------|-----------------|----------|----------|---------|-----|
| Oct29 | 0 | 3 | 3 | 1969 | 0.00% | 0.15% | FAIL |
| Oct30 | 0 | 2 | 2 | 1969 | 0.00% | 0.10% | FAIL |
| Nov02 | 0 | 1 | 1 | 1969 | 0.00% | 0.05% | FAIL |
| Nov03 | 0 | 1 | 1 | 1969 | 0.00% | 0.05% | FAIL |
| Nov04 | 6956 | 0 | 6956 | 1969 | ~354% | ~354% | PASS |
| Nov05 | 6588 | 0 | 6588 | 1969 | ~335% | ~335% | PASS |
| Nov06 | 0 | 2 | 2 | 1969 | 0.00% | 0.10% | FAIL |
| Nov09 | 0 | 2 | 2 | 1969 | 0.00% | 0.10% | FAIL |

**Note**: Nov04/05 coverage >100% because daily_prices includes non-ordinary stocks. Universe reference (1969) is ordinary stocks only.

**TWSE coverage**: as above (all S50 records are TWSE ordinary stocks)  
**TPEx coverage**: UNVERIFIED (0% verified for all dates)

## Source Integrity Checks

| Check | Status |
|-------|--------|
| TWSE_OFFICIAL_SOURCE | PASS |
| TPEX_OFFICIAL_SOURCE | **UNVERIFIED** |
| Provider Date Semantics | PASS |
| Trading Calendar | PASS |
| Corporate Actions | **UNVERIFIED** |
| Suspensions | **UNVERIFIED** |
| ETF Contamination | PASS (2330/2454/2317 are ordinary_stock) |
| Duplicate Detection | PASS (0 existing rows for candidates) |
| OHLCV Consistency | **FAIL** (CLOSE only) |
| Volume Validity | **FAIL** (not available) |
| Security Mapping | PASS |

## QG Counterfactual Summary

| Scenario | Oct29 QG | Note |
|----------|---------|------|
| Current | FAIL | 0 non-0050 rows |
| Backfill only (S50) | FAIL | 3/1969 = 0.15% |
| Backfill + Patch | FAIL | Patch adds no rows |
| TPEx stale (no patch) | FAIL | Silent wrong date risk |

## Research Impact

| Category | Before | After S50 Backfill | After Full Backfill |
|----------|--------|-------------------|---------------------|
| Historical Coverage | 0% (Oct29–Nov03) | 0.05–0.15% | ~100% |
| Historical Outcomes | BLOCKED | PARTIAL (3 stocks) | READY |
| Genuine Prospective N | 0 | 0 (unchanged) | 0 (unchanged) |
| G03 Clusters | 0/10 | 0/10 | 0/10 |
| G04 | STRUCTURAL_FAIL | STRUCTURAL_FAIL | STRUCTURAL_FAIL |

## AUTH01 Decision Package

| Item | Value |
|------|-------|
| Target DB | data/platform.db |
| Target Table | daily_prices |
| Target Dates (P1) | Oct29, Oct30, Nov02, Nov03 |
| Verified INSERT count | 7 (3+2+1+1) |
| Missing | ~1962/1969 per date |
| OHLCV limitation | CRITICAL: OPEN/HIGH/LOW/VOLUME not verified |
| Rollback | DELETE 7 rows (trivial) |
| Corporate actions | UNCHECKED |

## Dry-run Results

| Test | Result |
|------|--------|
| Initial insert (7 rows) | PASS |
| Idempotent re-insert | PASS (0 new rows) |
| Conflict detection | PASS (IntegrityError raised) |
| Transaction rollback | PASS |
| Read-back close=2415.0 | PASS |
| Coverage after: Oct29=3 | PASS |
| Production not modified | PASS |

## Verdict

**AUTH01_PARTIAL** — 7 close-price records verified (TWSE only). Full universe not achievable from S50 data.  
**AUTH01_NOT_EXECUTED** — Production DB unchanged.

## Limitations

1. OPEN/HIGH/LOW estimates are mathematically derived, not market-verified
2. TPEx entirely unverified
3. Corporate actions unchecked
4. Volume not available
5. 7 rows out of ~15,752 missing ordinary stock-days (Oct29/30/Nov02/03)
