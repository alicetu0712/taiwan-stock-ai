# Session 71K — Deployment Readiness

**Session**: 71K  
**Overall**: `INTEGRATION_READY_FOR_DEPLOYMENT_REVIEW` with acknowledged gap

---

## 1. Deployment Readiness Gate

| Gate | Status | Evidence |
|---|---|---|
| Isolation Verified | ✓ PASS | No production files modified; cron unchanged |
| Guard Integration Verified | ✓ PASS | 38 integration tests pass |
| State Semantics Verified | ✓ PASS | write_committed proxy verified; P0 IT-09/10 |
| Lock Safety Verified | ✓ PASS (gap noted) | IT-15~17; IT-18 no deadlock |
| QG Preserved | ✓ PASS | Layer 0/1/2 separation; QG unchanged |
| RC-2 Unchanged | ✓ PASS | IT-34 hash match |
| No Unexpected DB Writes | ✓ PASS | IT-37 SQLite 534,770 unchanged |
| Offline P0 Tests Pass | ✓ PASS | 38/38 (IT-09, IT-10, IT-25 all PASS) |
| No New Regressions | ✓ PASS | 4400 passed, 37 unchanged pre-existing |
| Direct Entry Risk | ⚠ GAP | `DIRECT_ENTRY_GAP_REMAINS` |
| Rollback Design Ready | ✓ PASS | See Section 2 |

**Overall**: `INTEGRATION_READY_FOR_DEPLOYMENT_REVIEW`

---

## 2. Rollback Plan

### Phase: Deployment (not yet authorized)

```bash
# Step 1: Rename production wrapper to backup
mv scripts/hybrid_shadow_cron.py scripts/hybrid_shadow_cron.py.bak.$(date +%Y%m%d)

# Step 2: Deploy integrated version
cp scripts/hybrid_shadow_cron_integrated.py scripts/hybrid_shadow_cron.py

# Step 3: Verify hash
shasum -a 256 scripts/hybrid_shadow_cron.py
# Expected: matches hash of hybrid_shadow_cron_integrated.py

# Step 4: Smoke test (dry-run)
python3 scripts/hybrid_shadow_cron.py
```

### Rollback procedure:

```bash
# Restore backup
mv scripts/hybrid_shadow_cron.py scripts/hybrid_shadow_cron_integrated_failed.py
mv scripts/hybrid_shadow_cron.py.bak.* scripts/hybrid_shadow_cron.py

# Verify restored
shasum -a 256 scripts/hybrid_shadow_cron.py
# Expected: 46209171e00eb46429d0e36d02c106b87cf3684b13803ccdf53369042ba060d4

# If state file is in RUNNING state after rollback, check if data was written:
sqlite3 data/platform.db "SELECT date, COUNT(*) FROM daily_prices WHERE date >= '2026-11-12'"
# If rows present → reset state to WRITE_COMMITTED manually
# If no rows → reset state to FAILED (safe to retry)
```

---

## 3. Known Gaps / Pre-conditions for Production Deployment

### GAP-1: Direct Backfill Entry (MUST ACKNOWLEDGE)

`backfill_daily_prices.py` can be invoked directly, bypassing all guards.

**Risk level**: LOW (INSERT OR IGNORE prevents duplicates; SQLite WAL serializes)  
**Mitigation in place**: `CALLED_FROM_WRAPPER=1` env variable + `BackfillEntryGuard` soft warning  
**Closure requirement**: Modify `backfill_daily_prices.py` with hard enforcement (separate authorization)  
**Deployment gate**: Explicitly acknowledge this gap OR close it before deploying.

### GAP-2: H3 Still Pending

Production cron has not yet triggered naturally with the RC-2 patch and new guards active. H3 requires the machine to be awake at 16:00 CST on a trading day.

**Risk level**: LOW (guards are layered on top of existing pipeline; RC-2 is verified)  
**Deployment gate**: H3 is NOT required before Phase 2 deployment (guards are defensive additions).

### GAP-3: launchd Not Installed

The root cause of repeated cron misses (machine sleeping at 16:00 CST) is not yet addressed. The validity window guard (16:00–20:00) is designed to bound catch-up once launchd is deployed.

**Deployment gate**: Phase 2 (this session) does not require launchd. Phase 3 (launchd) is a separate authorization.

---

## 4. Deployment Steps (Phase 2 — requires explicit authorization)

1. Confirm `hybrid_shadow_cron_integrated.py` hash pre-deployment
2. Rename `hybrid_shadow_cron.py` → backup
3. Rename integrated → `hybrid_shadow_cron.py`
4. Verify new hash
5. Run dry-run smoke test
6. Monitor state file for `run_id` and `write_committed` on next natural cron execution
7. Confirm H3 acceptance after first natural cron run with integrated wrapper

**NOT authorized in S71K.**

---

## 5. Files for Deployment Review

| File | Purpose | Status |
|---|---|---|
| `scripts/hybrid_shadow_cron_integrated.py` | Deployment candidate | READY |
| `scripts/scheduler_safety_guards.py` | Guard module (already in production dir) | READY |
| `tests/test_wrapper_integration.py` | Acceptance tests | 38/38 PASS |
| `tests/test_scheduler_safety_guards.py` | Unit tests | 53/53 PASS |
| `docs/session71k_wrapper_integration.md` | Deployment diff | READY |
| `docs/session71k_state_outcome_mapping.md` | Outcome semantics | READY |
| `docs/session71k_filelock_acceptance.md` | Lock safety | READY |
| `docs/session71k_deployment_readiness.md` | This document | READY |
