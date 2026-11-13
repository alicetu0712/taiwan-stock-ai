# Session 71N — Entry Guard Review

**Session**: 71N  
**Verdict**: `ENTRY_COVERAGE_GAP_REMAINS` (documented, not a deployment blocker)

---

## Entry Point Coverage Matrix

| Entry Path | Execute Risk | Guard Present | Method | Authorization |
|---|---|---|---|---|
| CLI `--execute` | HIGH | ✓ YES | `check_original_entry()` (lock) | Blocked if no lock |
| CLI (dry-run, no --execute) | NONE | ✓ YES | `is_execute=False` | Always authorized |
| `run_backfill(execute=True)` | HIGH | ✓ YES | `check_original_entry()` (lock) | Blocked if no lock |
| `run_backfill(execute=False)` | NONE | ✓ YES | `is_execute=False` | Always authorized |
| `_write_df_to_sqlite()` direct | HIGH | ✗ NO | None | `WRITE_PATH_GAP_REMAINS` |
| `_process_trading_day()` direct | HIGH | ✗ NO | None | `WRITE_PATH_GAP_REMAINS` |
| Protected adapter `--execute` | HIGH | ✓ YES | `check_invocation()` (env) | Env var based |
| Maintenance override | CONDITIONAL | ✓ YES | Two-key check | BACKFILL_ALLOW_DIRECT+REASON |

---

## `WRITE_PATH_GAP_REMAINS` — Detailed Assessment

The two internal write functions are not independently guarded:

```python
def _write_df_to_sqlite(conn: sqlite3.Connection, df: pd.DataFrame, ...) -> int:
def _process_trading_day(conn, target_d, execute, ...) -> dict:
```

**To exploit these directly, an attacker must**:
1. Import the module in a Python REPL/script
2. Manually construct a `sqlite3.Connection` to the production DB
3. Call the function directly with valid arguments

**Risk**: LOW. This requires deliberate action with knowledge of internal API. It is not accessible from CLI or normal workflow.

**Not a deployment blocker** per S71M documented consensus.

---

## Guard Enforcement Order Verification

```
CLI main() → guard check (check_original_entry) → exit 2 if blocked
                ↓ if authorized
run_backfill() → guard check (check_original_entry) → guard_blocked=True if blocked
                ↓ if authorized
_verify_sqlite()       ← SQLite check (no write)
sqlite3.connect()      ← Connection open (no write yet)
_find_missing_dates()  ← SELECT only (no write)
fetch_twse_historical() ← HTTP (no write)
fetch_tpex_historical() ← HTTP (no write)
run_quality_gate()     ← Analysis (no write)
_write_df_to_sqlite()  ← ACTUAL WRITE ← guard fires before this ✓
conn.commit()          ← ACTUAL COMMIT ← guard fires before this ✓
```

**Confirmed**: Guard fires at both `main()` and `run_backfill()` entry points, BEFORE any provider calls, BEFORE any SQLite write.

---

## Guard Failure Mode Analysis

| Scenario | Behavior | Evidence |
|---|---|---|
| Lock file not found | `_check_lock_state` creates parent dir, tries acquire → not held → UNAUTHORIZED | `_check_lock_state` line 554 |
| Lock check OSError | Treat as not held → UNAUTHORIZED (fail closed) | `_check_lock_state` line 562 |
| Lock held but OSError | `BlockingIOError` path → AUTHORIZED | `_check_lock_state` line 560 |
| Lock file on different filesystem | Same behavior — flock works on same file regardless | macOS flock semantics |
| `BACKFILL_ALLOW_DIRECT=1` alone | `MAINTENANCE_AUTHORIZATION_INCOMPLETE` → UNAUTHORIZED | M-06 test |
| `BACKFILL_MAINTENANCE_REASON` alone | Passes `allow_direct=False` → lock check path → UNAUTHORIZED (unless lock held) | M-07 logic |
| Both maintenance keys set | `AUTHORIZED_MAINTENANCE` | M-07 test |
| Dry-run (`is_execute=False`) | Always `AUTHORIZED: dry-run mode` | M-01b, M-16b |

---

## Maintenance Override Security Analysis

The two-key requirement prevents accidental maintenance mode:
- `BACKFILL_ALLOW_DIRECT=1` alone → rejected
- `BACKFILL_MAINTENANCE_REASON` alone → lock path applies (may authorize if wrapper is running)
- Both set → authorized with reason logged

**Limitation**: Same OS user can set both env vars, so this is not cryptographic authorization. However:
1. It requires deliberate two-key action
2. The reason is logged for auditability
3. This is best achievable on single-user macOS (documented in `_check_lock_state()` docstring)

**Can maintenance override be accidentally used by normal cron?**  
No. The cron entry uses `python3 hybrid_shadow_cron.py --execute` without any env var injection. `BACKFILL_ALLOW_DIRECT=1` would need to be manually set in the shell environment.

---

## Parent PID Not Sole Authorization

Confirmed: `check_original_entry()` does NOT use parent PID as authorization. Parent PID is diagnostic only:
```python
is_wrapper_parent, parent_detail = cls._parent_is_wrapper()
return True, f"AUTHORIZED: {lock_detail}. env_var=..., parent={'wrapper' if is_wrapper_parent else ...}"
```
The `return True` at this point is based on `lock_held=True`, not on parent PID check.
