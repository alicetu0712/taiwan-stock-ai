# Session 71O — Deploy A Artifact Set

**Session**: 71O  
**Verdict**: `DEPLOY_A_ARTIFACT_SET_VERIFIED`

---

## Deploy A = 2 Files

| # | File | Role | Action | Hash |
|---|---|---|---|---|
| 1 | `scripts/backfill_daily_prices_guarded.py` | Guarded backfill | Replace `backfill_daily_prices.py` | `202e2231...` |
| 2 | `scripts/scheduler_safety_guards.py` | Guard module (dependency) | Verify already in place | `f6929a7c...` |

**File 2 (`scheduler_safety_guards.py`) is already deployed** — it was installed in S71J/S71L. Deploy A only requires verifying it has not drifted.

---

## Why 2 Files (not 1)

`backfill_daily_prices_guarded.py` imports `BackfillEntryGuard` from `scripts.scheduler_safety_guards`:

```python
from scripts.scheduler_safety_guards import BackfillEntryGuard
```

If `scheduler_safety_guards.py` were absent or stale (wrong version), the guarded backfill would fail at import time with `ImportError` or use the wrong guard implementation. The dependency must be verified atomically with the deployment.

---

## Hash Verification

Hashes measured at session start (confirmed unchanged throughout S71N and S71O):

```
backfill_daily_prices_guarded.py : 202e2231b6d2b8b865e5a854254c04b4dabff2b408807bac8172bced3a194c42
scheduler_safety_guards.py       : f6929a7c7cf2734ca597dda06bdc1014d67f74990c29dff3f5f825284783765b
```

These are the CANDIDATE (guarded) hashes. The PRODUCTION backfill (target of replacement) is:
```
backfill_daily_prices.py         : 4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb
```

---

## Deployment Procedure (from S71N atomic cutover plan)

```bash
# Step 1: Verify guard module already in place
sha256sum scripts/scheduler_safety_guards.py
# Expected: f6929a7c...

# Step 2: Atomic copy of guarded backfill
cp scripts/backfill_daily_prices_guarded.py /tmp/backfill_daily_prices.py.new
mv /tmp/backfill_daily_prices.py.new scripts/backfill_daily_prices.py
# mv on APFS = kernel-level rename syscall = atomic

# Step 3: Verify
sha256sum scripts/backfill_daily_prices.py
# Expected: 202e2231...
```

---

## Rollback

Replace `backfill_daily_prices.py` with its original content (hash `4eb6eacf...`). The guard module (`scheduler_safety_guards.py`) does not need to be changed during rollback — it is backward-compatible with the original backfill.

---

## What Deploy A Does NOT Change

| Item | Status |
|---|---|
| `hybrid_shadow_cron.py` (original wrapper) | UNCHANGED |
| `scheduler_safety_guards.py` (guard module) | VERIFY ONLY |
| Crontab / launchd plist | UNCHANGED |
| SQLite production data | UNCHANGED |
| Neon production data | UNCHANGED |
| RC-2 filter / QG | UNCHANGED |
| `hybrid_shadow_cron_integrated.py` | NOT deployed |
