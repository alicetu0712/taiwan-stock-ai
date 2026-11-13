# Session 71M — Entry Coverage Matrix

**Session**: 71M  
**Verdict**: `WRITE_PATH_COVERAGE_PARTIAL` (CLI + run_backfill() covered; internal functions not)

---

## Invocation Matrix

| Invocation | Guard Applied | Authorization | Test |
|---|---|---|---|
| `guarded.py --execute` (direct, no lock) | `main()` guard | BLOCKED (exit 2) | M-01 ✓ |
| `guarded.py --execute` (via wrapper, lock held) | `main()` guard | AUTHORIZED | M-10 ✓ |
| `guarded.py` (dry-run) | `main()` guard | AUTHORIZED (dry-run) | M-16 ✓ |
| `guarded.py --help` | `main()` guard | AUTHORIZED (read-only) | M-17 ✓ |
| Integrated wrapper → guarded | wrapper holds lock + sets env | AUTHORIZED (lock check) | M-02 ✓ |
| Protected adapter → original | env var check only | AUTHORIZED (env var) | M-03 ✓ |
| `run_backfill(execute=True)` on guarded (no auth) | `run_backfill()` guard | BLOCKED (guard_blocked=True) | M-08 ✓ |
| `run_backfill(execute=True)` on guarded (lock+env) | `run_backfill()` guard | AUTHORIZED | M-08b ✓ |
| Maintenance override (two-key) | `check_original_entry()` | AUTHORIZED_MAINTENANCE | M-07 ✓ |
| Maintenance override (single key) | `check_original_entry()` | BLOCKED | M-06 ✓ |
| Fake env var only (CALLED_FROM_WRAPPER=1, no lock) | lock check | BLOCKED | M-04 ✓ |
| No env, no lock | lock check | BLOCKED | M-05 ✓ |

---

## Write Path Analysis

### Protected

1. **`main()` in `guarded.py`** → `check_original_entry()` called → lock check primary gate ✓
2. **`run_backfill()` in `guarded.py`** → `check_original_entry()` called (defense-in-depth) ✓

### Not Protected (documented gap)

3. **`_process_trading_day()`** → internal function; requires `sqlite3.Connection` to call directly
4. **`_write_df_to_sqlite(conn, df)`** → internal function; requires `sqlite3.Connection`

**Rationale for gap acceptance**: These are private/internal functions (prefixed `_`). Direct callers must construct a `sqlite3.Connection` to production DB themselves — requires deliberate code and system access beyond CLI misuse. This is below the accidental misuse threshold.

**Original `backfill_daily_prices.py`**: The production file remains unguarded at `run_backfill()`. Direct calls to it bypass all S71M guards. Future deployment of `guarded.py` → `backfill_daily_prices.py` closes this.

---

## Authorization Hierarchy Summary

```
Priority 1: Dry-run (is_execute=False) → ALWAYS AUTHORIZED
Priority 2: Two-key maintenance (BACKFILL_ALLOW_DIRECT=1 + BACKFILL_MAINTENANCE_REASON) → AUTHORIZED
Priority 3: Lock check → lock IS held by another process → AUTHORIZED
  └── Env var and parent PID logged as diagnostic info
Priority 4: Lock NOT held → UNAUTHORIZED (env var alone insufficient)
```

**Key property**: Env var (`CALLED_FROM_WRAPPER=1`) alone is NOT sufficient to authorize `--execute` when `lock_path` is provided. This satisfies the M-04/M-05 requirements.

---

## Security Limitation (Acknowledged)

Same OS user can forge lock check by holding `data/.cron.lock` before calling backfill, preventing the legitimate scheduler from running. This is documented per spec: "不得宣稱同一 OS 使用者無法偽造其自行控制的程序資訊."

The guard prevents **accidental** direct invocation, not **deliberate** misuse by the same user.
