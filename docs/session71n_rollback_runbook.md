# Session 71N — Rollback Runbook

**Session**: 71N  
**Verdict**: `ROLLBACK_PLAN_READY`

---

## Rollback Triggers

Initiate rollback if any of the following:

1. `backfill_daily_prices.py --help` fails after Deploy A
2. Import of `run_backfill` raises ImportError or AttributeError
3. Guard dry-run produces unexpected error (not exit 2)
4. Guard rejection test does NOT exit 2 (guard not firing)
5. Cron run after Deploy A produces exit code != 0 AND unexplained
6. SQLite row count changes unexpectedly
7. Any write to production DB at unexpected time

---

## Rollback Procedure

### Pre-rollback: Confirm quiescence

```bash
# Check no active cron run
lsof data/.cron.lock 2>/dev/null | grep -v COMMAND
# If output shows a process: wait for it to complete before rollback
```

### Step 1: Verify backup exists

```bash
ls -la scripts/backfill_daily_prices.py.bak.*
sha256sum scripts/backfill_daily_prices.py.bak.*
# Must see: 4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb
```

### Step 2: Restore original backfill

```bash
# Near-atomic restore
cp scripts/backfill_daily_prices.py.bak.<TIMESTAMP> \
   scripts/backfill_daily_prices.restore.new

sha256sum scripts/backfill_daily_prices.restore.new
# Must verify: 4eb6eacf...

mv scripts/backfill_daily_prices.restore.new \
   scripts/backfill_daily_prices.py
```

### Step 3: Verify rollback

```bash
sha256sum scripts/backfill_daily_prices.py
# Expected: 4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb

python3 scripts/backfill_daily_prices.py --help
# Must succeed

python3 scripts/backfill_daily_prices.py \
    --start 2026-11-13 --end 2026-11-13
# Dry-run must succeed
```

### Step 4: scheduler_safety_guards.py rollback (only if needed)

`scheduler_safety_guards.py` is additive — the original `backfill_daily_prices.py` does NOT import it. Rolling back `backfill_daily_prices.py` automatically removes the dependency.

If needed separately:
```bash
cp scripts/scheduler_safety_guards.py.bak.<TIMESTAMP> \
   scripts/scheduler_safety_guards.py
sha256sum scripts/scheduler_safety_guards.py
# Verify expected hash
```

### Step 5: Post-rollback confirmation

```bash
# Confirm original wrapper still uses backfill by name (unchanged)
sha256sum scripts/hybrid_shadow_cron.py
# Expected: 46209171... (UNCHANGED — no rollback needed for this)

# Confirm SQLite unchanged
python3 -c "
import sqlite3
conn = sqlite3.connect('data/platform.db')
print(conn.execute('SELECT COUNT(*), MAX(date) FROM daily_prices').fetchone())
"
```

---

## State File After Rollback

The state file (`data/.cron_state.json`) does NOT need to be restored or deleted during rollback.

- Original wrapper reads `today` and `status` fields — these are present regardless of which backfill version ran
- If the guarded backfill wrote `guard_blocked=True` to stderr (not to state file), the state file is unaffected
- Rollback does NOT require deleting state file

**DB Safety Boundary**: Rollback does NOT require clearing any DB rows. The guarded backfill, if it ran successfully, wrote the same data the original backfill would have written (same QG, same providers, same schema). `INSERT OR IGNORE` means any rows written are valid.

---

## Rollback Compatibility Summary

| Item | Pre-deploy | Post-rollback | Requires action? |
|---|---|---|---|
| `backfill_daily_prices.py` | `4eb6eacf...` | `4eb6eacf...` | Restore from backup |
| `scheduler_safety_guards.py` | `f6929a7c...` | `f6929a7c...` or old | Optional (backward compat) |
| `hybrid_shadow_cron.py` | `46209171...` | `46209171...` | No action (unchanged) |
| `data/platform.db` | unchanged | unchanged | No action |
| `data/.cron_state.json` | original format | original format | No action |
| Crontab | unchanged | unchanged | No action |
