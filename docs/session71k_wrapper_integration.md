# Session 71K — Wrapper Integration

**Session**: 71K  
**File**: `scripts/hybrid_shadow_cron_integrated.py` (NEW — deployment candidate)  
**Base**: `scripts/hybrid_shadow_cron.py` (SHA: `46209171...`)  
**Status**: INTEGRATION_VERIFIED

---

## 1. Integration Points

The integrated wrapper adds 7 integration points to the existing pipeline. Zero changes to QG, RC-2, provider calls, SQLite write location, or shadow runner logic.

### Pipeline Flow (Integrated)

```
run_cron_pipeline()
  │
  ├── [NEW] Step 0a: Execution Validity Window guard
  │     • check_execution_window(now_taipei=now_taiwan)
  │     • If not allowed: return GUARD_WINDOW_* (no lock taken)
  │
  ├── Step 1: FileLock acquire (UNCHANGED)
  │     • If blocked: return BLOCKED_LOCK
  │
  ├── [NEW] Step 1b: Same-day State Guard
  │     • SameDayStateGuard(state_file).check(scheduled_date)
  │     • If not allowed: release lock, return GUARD_STATE_*
  │
  ├── [NEW] Step 1c: Mark RUNNING
  │     • Write run_id, pid, status=RUNNING, write_committed=False to state
  │
  ├── Step 2: Calendar check (UNCHANGED)
  ├── Step 3: Data readiness check (UNCHANGED)
  ├── Step 4: Backfill subprocess (UNCHANGED, adds CALLED_FROM_WRAPPER=1 to env)
  │
  ├── Step 4b: Freshness check with retry (UNCHANGED logic)
  │     ├── If FULL_MARKET_FRESH:
  │     │     [NEW] Step 4c: Mark WRITE_COMMITTED (write_committed=True)
  │     │     → proceed to Step 5
  │     └── If not: → return BLOCKED_STALE_DATA / BLOCKED_PARTIAL_MARKET
  │
  ├── Step 5: Backup (UNCHANGED)
  ├── Step 6: Shadow runner (UNCHANGED)
  │
  └── [NEW] Step 7: Final state save with SUCCESS/SHADOW_FAILED
        (always happens in finally block via _save_state)
```

### Single change to Step 4 (`_run_backfill`):
```python
# Added env injection for Option B FileLock warning
env = {**os.environ, "CALLED_FROM_WRAPPER": "1"}
subprocess.run(cmd, ..., env=env)
```

---

## 2. Function Signature Changes

```python
# Production (hybrid_shadow_cron.py):
def run_cron_pipeline(execute: bool = False, skip_backup: bool = False) -> dict:

# Integrated (hybrid_shadow_cron_integrated.py):
def run_cron_pipeline(
    execute: bool = False,
    skip_backup: bool = False,
    _now_taipei_override: Optional[datetime] = None,   # clock injection
    _state_file_override: Optional[Path] = None,        # state path injection
    _lock_file_override: Optional[Path] = None,         # lock path injection
    _db_path_override: Optional[str] = None,            # db path injection
    _backfill_runner: Optional[object] = None,          # mock backfill
    _shadow_runner: Optional[object] = None,            # mock shadow
    _freshness_checker: Optional[object] = None,        # mock freshness
) -> dict:
```

All injection parameters default to None → production behavior unchanged when None is passed.

---

## 3. `_save_state()` Change: Atomic Write

```python
# Production (non-atomic):
def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))

# Integrated (atomic write + secret strip):
def _save_state(state: dict, state_file: Optional[Path] = None) -> None:
    path = state_file or STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    safe = {k: v for k, v in state.items()
            if k not in ("database_url", "api_key", "password", "secret")}
    tmp.write_text(json.dumps(safe, indent=2, default=str))
    os.replace(tmp, path)   # atomic rename
```

This prevents partial state reads during concurrent execution.

---

## 4. New Fields in State File

The integrated wrapper adds these fields to the existing state file schema:

| Field | Type | When set | Meaning |
|---|---|---|---|
| `run_id` | str | Step 1c | Unique ID for this run (`cron-YYYY-MM-DD-{hex8}`) |
| `scheduled_date` | str | Step 0a | Date the pipeline was scheduled for |
| `schema_version` | int | Step 1c | Always 1 |
| `pid` | int | Step 1c | Process ID of the wrapper |
| `write_committed` | bool | Step 4c | True after FULL_MARKET_FRESH confirmed |

Existing fields (`today`, `taiwan_time`, `steps`, `status`, `execute`, etc.) are preserved.

---

## 5. Zero-change Guarantees

| Component | Modified? | Evidence |
|---|---|---|
| QG-1 ~ QG-7 | NO | Guards exit before backfill; QG runs in backfill subprocess |
| RC-2 filter (`len(sid) > 4`) | NO | Backfill script untouched |
| Provider calls (TWSE/TPEx) | NO | Backfill script untouched |
| SQLite write location (`DB_PATH`) | NO | Same `config.DB_PATH` used |
| Shadow runner logic | NO | `_run_shadow()` unchanged |
| Trading calendar | NO | Same `TaiwanTradingCalendar()` instance |
| Backup logic | NO | `create_backup()` unchanged |
| Exit code policy | NO | Same `clean_statuses` set (guard rejections added as clean) |
| Neon | NO | Never touched (cron only writes SQLite) |

---

## 6. Deployment Diff Summary

To deploy to production:
1. Verify hash of `hybrid_shadow_cron_integrated.py`
2. Rename `hybrid_shadow_cron.py` → `hybrid_shadow_cron.py.bak`
3. Rename `hybrid_shadow_cron_integrated.py` → `hybrid_shadow_cron.py`
4. Verify new file is loaded by cron on next trigger
5. Monitor state file for `run_id` and `write_committed` fields

Rollback:
```bash
mv scripts/hybrid_shadow_cron.py scripts/hybrid_shadow_cron_integrated_rollback.py
mv scripts/hybrid_shadow_cron.py.bak scripts/hybrid_shadow_cron.py
# Verify: shasum -a 256 scripts/hybrid_shadow_cron.py → 46209171...
```

**NOT authorized in S71K — requires explicit Phase 2 deployment authorization.**
