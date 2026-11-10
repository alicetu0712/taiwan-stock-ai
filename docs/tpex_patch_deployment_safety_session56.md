# TPEx Patch Deployment Safety Audit — Session 56

**Verdict**: PATCH_DEPLOYMENT_READY  
**Execution**: PATCH_NOT_DEPLOYED

## S56 Confirmed Patch State

| Property | Confirmed Value |
|----------|----------------|
| File | scripts/backfill_daily_prices.py |
| TWSE section (L494-498) | ALREADY_HAS_ERROR_PROPAGATION |
| TPEx section (L500-501) | PRINT_ONLY_CONFIRMED |
| Patch needed | YES — 2 lines to add after L501 |

## Exact Diff

```diff
--- scripts/backfill_daily_prices.py
+++ scripts/backfill_daily_prices.py
@@ -500,2 +500,4 @@
         if tpex_api_date and tpex_api_date != target_d:
-            print(f"  [WARN] {target_d}: TPEx api_date={tpex_api_date} != target")
+            msg = f"{target_d}: TPEx api_date={tpex_api_date} != target — API returned wrong date"
+            print(f"  [WARN] {msg}")
+            summary["errors"].append(msg)
```

**Changes**: +2 lines (msg variable + summary append)  
**Zero logic change**: only observability improvement

## 15-Scenario Simulation Results

| # | Scenario | Before Errors | After Errors | Price Rows Equiv | Verdict |
|---|----------|--------------|-------------|-----------------|---------|
| S01 | Correct TPEx date | 0 | 0 | ✓ | PASS |
| S02 | Wrong TPEx date | 0 | 1 | ✓ | PASS |
| S03 | Stale TPEx date | 0 | 1 | ✓ | PASS |
| S04 | Empty response (api_date=None) | 0 | 0 | ✓ | PASS |
| S05 | Timeout | 0 | 0 | ✓ | PASS |
| S06 | Rate limit | 0 | 0 | ✓ | PASS |
| S07 | Retry success (attempt 2) | 0 | 1 | ✓ | PASS |
| S08 | Retry failure (4 retries) | 0 | 4 | ✓ | PASS |
| S09 | TWSE+TPEx both wrong | 1 | 2 | ✓ | PASS |
| S10 | Multiple errors | 0 | 1 | ✓ | PASS |
| S11 | QG failure + TPEx error | 0 | 1 | ✓ | PASS |
| S12 | Completion marker | 0 | 0 | ✓ | PASS |
| S13 | Log parsing | 0 | 1 | ✓ | PASS |
| S14 | No data mutation | 0 | 0 | ✓ | PASS |
| S15 | No scheduler mutation | 0 | 0 | ✓ | PASS |

**All 15 scenarios: PASS**

## Behavioral Equivalence

| Property | Equivalent? |
|----------|-------------|
| Price rows written | ✓ IDENTICAL |
| Provider API requests | ✓ IDENTICAL |
| Security universe | ✓ IDENTICAL |
| QG thresholds | ✓ IDENTICAL |
| Retry count | ✓ IDENTICAL |
| Completion semantics | ✓ IDENTICAL |
| Error reporting | INTENTIONAL DIFFERENCE (TPEx errors now captured) |

No UNEXPECTED differences detected.

## Deployment Risk

| Risk | Level | Mitigation |
|------|-------|-----------|
| Runtime compatibility | LOW | TWSE section already works with same pattern |
| Error schema | NONE | No schema change |
| Cron environment | NONE | Cron invocation unchanged |
| Monitoring alerts | MEDIUM | May trigger new alerts on TPEx mismatches |
| Rollback | LOW | 2-line revert; trivial |
| Failure isolation | NONE | append() cannot throw |

## Authorization Package

**Deployment procedure**:
1. Edit `scripts/backfill_daily_prices.py` L501: replace single `print()` with 3-line block
2. Run `python3 -m pytest tests/ -k 'tpex or patch' --tb=short`
3. Run `python3 -m ruff check scripts/backfill_daily_prices.py`
4. `git add + git commit`

**Rollback**: restore original 2-line form; run tests

**Verification**: confirm `summary["errors"].append(msg)` present in TPEx block after deployment

**Authorization required**: explicit user authorization before deployment

## Module

`src/research/tpex_patch_deployment_s56.py` — PARTS C1–C6
