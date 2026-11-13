# Session 71N — Atomic Cutover Plan (Design Only)

**Session**: 71N  
**Mode**: DESIGN ONLY — NOT AUTHORIZED FOR EXECUTION  
**Verdict**: `ATOMIC_CUTOVER_PLAN_READY`

---

## Overview

Deploy A installs the guarded backfill (lock-based authorization) while keeping the original wrapper unchanged. It requires replacing 1 file on disk and confirming 1 file is already in place.

---

## Stage 0 — Pre-deployment Approval Gate

Required before ANY file changes:

```
□ Explicit written authorization for Deploy A
□ Confirm current date is a non-trading day OR timing is outside 15:30–20:00 CST
□ Confirm no active cron run in progress (check lock file: data/.cron.lock not held)
□ Confirm production hashes match expected values:
    hybrid_shadow_cron.py:    46209171...
    backfill_daily_prices.py: 4eb6eacf...
□ Record deployment start timestamp
```

**Quiescence condition**: Deploy ONLY when cron is NOT running.
- Safe windows: before 15:30 CST or after 16:30 CST on trading days
- Weekend / holiday: any time is safe
- Quick check: `flock -n data/.cron.lock echo "lock free"` or `lsof data/.cron.lock`

---

## Stage 1 — Backup (3 files)

```bash
# DESIGN ONLY — not to be executed without Stage 0 authorization

BKUP_TS=$(date +%Y%m%dT%H%M%S)

# Backup target files
cp -p scripts/backfill_daily_prices.py \
      scripts/backfill_daily_prices.py.bak.${BKUP_TS}
cp -p scripts/scheduler_safety_guards.py \
      scripts/scheduler_safety_guards.py.bak.${BKUP_TS}

# Verify backup SHA256 matches pre-deploy
sha256sum scripts/backfill_daily_prices.py.bak.*
# Expected: 4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb

sha256sum scripts/scheduler_safety_guards.py.bak.*
# Record (this is the new guard module — ensure it matches f6929a7c...)
```

---

## Stage 2 — Artifact Verification

```bash
# Verify candidate file before deployment
sha256sum scripts/backfill_daily_prices_guarded.py
# Expected: 202e2231b6d2b8b865e5a854254c04b4dabff2b408807bac8172bced3a194c42

sha256sum scripts/scheduler_safety_guards.py
# Expected: f6929a7c7cf2734ca597dda06bdc1014d67f74990c29dff3f5f825284783765b

# Verify production wrapper is unchanged
sha256sum scripts/hybrid_shadow_cron.py
# Expected: 46209171e00eb46429d0e36d02c106b87cf3684b13803ccdf53369042ba060d4
```

---

## Stage 3 — Atomic Replacement

**Note on "atomic" for a single-file replace**: On macOS HFS+/APFS, `cp` is NOT atomic. However, since we're on the same filesystem, we can use `cp` to a `.new` file then `mv` for near-atomic behavior:

```bash
# Step A: scheduler_safety_guards.py is ALREADY deployed (hash verified in Stage 2)
# No action needed for this file.

# Step B: Deploy guarded backfill (near-atomic via mv)
cp scripts/backfill_daily_prices_guarded.py \
   scripts/backfill_daily_prices.new

sha256sum scripts/backfill_daily_prices.new
# Verify: 202e2231...

mv scripts/backfill_daily_prices.new \
   scripts/backfill_daily_prices.py
# mv on same filesystem is atomic at kernel level (rename syscall)
```

**Why not simultaneous multi-file atomic replacement?**  
Deploy A only replaces `backfill_daily_prices.py`. `scheduler_safety_guards.py` is already in place. Single-file `mv` is atomic on APFS/HFS+.

**Quiescence risk**: The cron wrapper may read `backfill_daily_prices.py` by name at the time of `subprocess.run()`. If `mv` happens between wrapper's lock acquisition and subprocess launch, the new guarded version is called — this is correct and desired behavior.

---

## Stage 4 — Post-deployment Verification (Non-destructive)

```bash
# 1. Hash verification
sha256sum scripts/backfill_daily_prices.py
# Expected: 202e2231...

sha256sum scripts/hybrid_shadow_cron.py
# Expected: 46209171... (UNCHANGED)

# 2. Import check
python3 -c "from scripts.backfill_daily_prices import run_backfill; print('OK')"

# 3. CLI help (no write)
python3 scripts/backfill_daily_prices.py --help

# 4. Dry-run (no execute flag — no write)
python3 scripts/backfill_daily_prices.py \
    --start 2026-11-13 --end 2026-11-13

# 5. Guard rejection test (should exit 2)
python3 scripts/backfill_daily_prices.py \
    --start 2026-11-13 --end 2026-11-13 --execute
# Expected: exit code 2, prints GUARD_BLOCKED

# 6. Confirm lock path resolves correctly
python3 -c "
import sys; sys.path.insert(0,'.')
from scripts.backfill_daily_prices import _get_cron_lock_path
print(_get_cron_lock_path(None))
# Expected: data/.cron.lock
"

# 7. SQLite row count (should not have changed)
python3 -c "
import sqlite3
conn = sqlite3.connect('data/platform.db')
print(conn.execute('SELECT COUNT(*), MAX(date) FROM daily_prices').fetchone())
"
# Expected: (534770, '2026-11-05')
```

---

## Stage 5 — Multi-file Consistency Note

Deploy A touches only `backfill_daily_prices.py` (via `mv`). `scheduler_safety_guards.py` was already deployed. There is no window where:
- New `backfill_daily_prices.py` exists but `scheduler_safety_guards.py` doesn't have `check_original_entry()` → both are present before `mv`
- Old `backfill_daily_prices.py` exists with new `scheduler_safety_guards.py` → backward compatible (old file doesn't import guard)

**Multi-file consistency**: SAFE for Deploy A.

---

## Timing Safety

Do NOT execute during active cron window:
```
Trading day 15:30–16:00 CST: data loading time — risky
Trading day 16:00–16:30 CST: cron may be actively running — BLOCKED
Trading day 16:30–20:00 CST: safe if cron completed
Non-trading day: safe any time
Weekend: safe any time
```
