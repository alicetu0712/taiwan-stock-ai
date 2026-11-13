# Session 71L — Direct Entry Protection

**Session**: 71L  
**Verdict**: `DIRECT_ENTRY_HARDENED` (soft block; not fully closeable without backfill modification)

---

## The Gap (Inherited from S71K)

`backfill_daily_prices.py` can be executed directly, bypassing:
- Wrapper's `FileLock`
- Window guard
- Same-day state guard
- All `BackfillEntryGuard` logic

**Risk**: Concurrent wrapper + direct execution during same window = potential duplicate write attempt. However, `INSERT OR IGNORE` prevents duplicate rows, and SQLite WAL serializes writes, so actual data corruption is LOW risk. The main risk is state file inconsistency (wrapper thinks it wrote, but direct script also wrote without updating state).

---

## S71L Implementation

### 1. `BackfillEntryGuard.check_invocation()` — Two-layer authorization

**Layer 1**: `CALLED_FROM_WRAPPER=1` environment variable  
Set by wrapper's `_run_backfill()` subprocess call. Fast, cheap, testable.

**Layer 2**: Parent process name via `ps -p {ppid} -o command=`  
Checks if parent process cmdline contains `'hybrid_shadow_cron'`. Harder to accidentally bypass, but forgeable with intention.

**Maintenance override**: `BACKFILL_ALLOW_DIRECT=1` environment variable  
Explicit bypass for authorized manual operations. Issues a warning.

```python
@classmethod
def check_invocation(cls, is_execute: bool = True) -> tuple[bool, str]:
    if not is_execute:
        return True, "AUTHORIZED: dry-run mode — no write risk"
    if os.environ.get(cls.ALLOW_DIRECT_KEY) == "1":
        return True, "AUTHORIZED_MAINTENANCE: BACKFILL_ALLOW_DIRECT=1 override active..."
    if cls.is_called_from_wrapper():
        return True, "AUTHORIZED: CALLED_FROM_WRAPPER=1"
    is_wrapper, detail = cls._parent_is_wrapper()
    if is_wrapper:
        return True, f"AUTHORIZED: parent is wrapper ({detail})"
    return False, "UNAUTHORIZED_DIRECT_ENTRY: ..."
```

### 2. `backfill_daily_prices_protected.py` — Protected entry point

Thin wrapper that:
- Reuses all logic from `run_backfill()` (no duplication)
- Calls `check_invocation(is_execute=args.execute)` before any execute path
- Returns **exit code 2** on safety block (distinct from backfill failure exit code 1)
- Dry-run always passes (no write risk)

### 3. `hybrid_shadow_cron_integrated.py` update

`_run_backfill()` now prefers `backfill_daily_prices_protected.py` over the base script:

```python
protected = sd / "backfill_daily_prices_protected.py"
base = sd / "backfill_daily_prices.py"
target_script = protected if protected.exists() else base
```

Falls back to base if protected is not found — safe, since `CALLED_FROM_WRAPPER=1` is still set.

---

## What This Covers vs What Remains

| Scenario | Before S71L | After S71L |
|---|---|---|
| Direct `backfill_daily_prices.py --execute` | ALLOWED (silent) | WARNING only (unchanged script) |
| Direct `backfill_daily_prices_protected.py --execute` | N/A | **BLOCKED** (exit 2) |
| `backfill_daily_prices.py` dry-run | ALLOWED | ALLOWED (unchanged) |
| `backfill_daily_prices_protected.py` dry-run | N/A | ALLOWED |
| Wrapper → protected script | N/A | AUTHORIZED (env var) |
| Wrapper → base script (fallback) | ALLOWED | ALLOWED (env var advisory) |

**Remaining gap**: `backfill_daily_prices.py` can still be called directly without any guard.  
**Closure requirement**: Modify `backfill_daily_prices.py` to call `check_invocation()` at its own `main()` — requires separate authorization (production backfill script modification).

---

## Test Coverage

- **L-01**: Direct `--execute` via protected script → exit 2 ✓ PASS
- **L-01b**: Direct dry-run via protected script → allowed ✓ PASS
- **L-02b**: `CALLED_FROM_WRAPPER=1` env → authorized ✓ PASS
- **L-04**: Concurrent wrapper+direct, guard blocks ✓ PASS
- **L-04b**: `BACKFILL_ALLOW_DIRECT=1` override → authorized with warning ✓ PASS
