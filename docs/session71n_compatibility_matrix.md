# Session 71N — Wrapper/Guard/Backfill Compatibility Matrix

**Session**: 71N  
**Verdict**: `RUNTIME_COMPATIBILITY_VERIFIED_OFFLINE`

---

## Compatibility Matrix

| Wrapper | Backfill | Authorization Path | Result | Evidence |
|---|---|---|---|---|
| Original (`46209171`) | Original (`4eb6eacf`) | None (unguarded) | ✓ WORKS (baseline) | Existing production |
| Original (`46209171`) | Guarded (`202e2231`) | Lock-based (primary) | ✓ WORKS | N-lock-01 (see below) |
| Integrated (`dc474aa2`) | Original (`4eb6eacf`) | Env var advisory only | ✓ WORKS (advisory) | N-lock-02 |
| Integrated (`dc474aa2`) | Guarded (`202e2231`) | Lock + env var | ✓ WORKS | N-lock-03 |
| Integrated (`dc474aa2`) | Protected (`7aa3a602`) | Env var (check_invocation) | ✓ WORKS | Existing IT tests |
| Direct CLI | Guarded (`202e2231`) | None → lock absent | ✗ BLOCKED (exit 2) | M-01 |

---

## Critical Path: Original Wrapper → Guarded Backfill

**This is the DEPLOYMENT A runtime path.**

### Evidence Chain

**Step 1**: Original wrapper acquires exclusive lock on `data/.cron.lock`:
```python
# hybrid_shadow_cron.py line 157–167
def acquire(self) -> bool:
    self._fd = os.open(str(self._path), os.O_CREAT | os.O_WRONLY)
    try:
        fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.write(self._fd, f"{os.getpid()}\n".encode())
        return True
    except BlockingIOError:
        ...
```

**Step 2**: Original wrapper calls guarded backfill via subprocess:
```python
# hybrid_shadow_cron.py line 239
cmd = [PYTHON, str(SCRIPTS_DIR / "backfill_daily_prices.py")]
```
(After Deploy A, `backfill_daily_prices.py` IS the guarded version.)

**Step 3**: Guarded backfill calls `_check_lock_state()`:
```python
# backfill_daily_prices_guarded.py line 466
lock_path = _get_cron_lock_path(db_path, _lock_path)
authorized, reason = BackfillEntryGuard.check_original_entry(
    is_execute=True, lock_path=lock_path
)
```

**Step 4**: `_check_lock_state()` tries `LOCK_EX | LOCK_NB` on same file. Parent holds it → `BlockingIOError` → `AUTHORIZED`.

**Lock path resolution** (both sides resolve to same file):
- Wrapper: `Path(__file__).parent.parent / "data" / ".cron.lock"` = `data/.cron.lock`
- Guarded: `Path(DB_PATH).parent / ".cron.lock"` = `data/.cron.lock`
- **Verified**: `wrapper_lock.resolve() == default_lock.resolve()` ✓

### N-lock-01: Cross-process Lock Visibility Test
```
SUBPROCESS TEST RESULT:
  Parent holds LOCK_EX → subprocess tries LOCK_EX|LOCK_NB → "HELD" (AUTHORIZED)
  Parent releases → subprocess tries LOCK_EX|LOCK_NB → "NOT_HELD" (unauthorized)
  STATUS: PASS ✓
```
Verified via `subprocess.run()` with actual `fcntl.flock` — not a mock.

---

## Note: Original Wrapper Does NOT Set `CALLED_FROM_WRAPPER=1`

The original `hybrid_shadow_cron.py` does NOT inject `CALLED_FROM_WRAPPER` env var:
```python
result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SCRIPTS_DIR.parent))
# No env= override → no CALLED_FROM_WRAPPER=1
```

The integrated wrapper DOES:
```python
env = {**os.environ, "CALLED_FROM_WRAPPER": "1"}
result = subprocess.run(cmd, ..., env=env)
```

**Impact**: For `Original → Guarded` path, `check_original_entry()` will log `env_var=NOT_SET` in the authorized reason, but authorization is granted based on lock (not env var). Lock is the primary gate. **This is correct behavior.**

---

## CLI Argument Compatibility

| Argument | Original | Guarded | Match |
|---|---|---|---|
| `--start` | ✓ | ✓ | IDENTICAL |
| `--end` | ✓ | ✓ | IDENTICAL |
| `--execute` | ✓ | ✓ | IDENTICAL |
| `--db` | ✓ | ✓ | IDENTICAL |

## Exit Code Compatibility

| Scenario | Original | Guarded | Match |
|---|---|---|---|
| Success | 0 | 0 | ✓ |
| Guard block | N/A | 2 | Additive only |
| Dry-run complete | 0 | 0 | ✓ |
| Error | non-zero | non-zero | ✓ |

Exit code 2 is new (guard block). Original wrapper checks `returncode != 0` — this is treated as BACKFILL_FAILED in wrapper's pipeline. **This is correct fail-closed behavior.**

---

## State File Compatibility Finding (NEW)

The `SameDayStateGuard.check()` reads `state.get("today") or state.get("scheduled_date", "")`.

The original wrapper writes `today=YYYY-MM-DD` to state. The integrated wrapper writes both `today` (outer dict) and `scheduled_date` (guard state).

**Risk**: After Deploy A (keeping original wrapper), the state file will continue using original format (`today=...`). The `SameDayStateGuard` (if used) correctly reads `today` field. **Compatible.**

**Risk on first run after Deploy A**: If old state file with `today=2026-11-10` is present, the guard reads it and allows the run (different day). This is **correct behavior** — the run is for a new day.
