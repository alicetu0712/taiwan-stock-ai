# Session 71N — Commit / Lock / State Safety Review

**Session**: 71N  
**Verdict**: `COMMIT_SAFETY_DOCUMENTED` / `LOCK_SAFETY_VERIFIED_OFFLINE` / `STATE_COMPATIBILITY_PARTIAL`

---

## Commit Order Analysis

From `backfill_daily_prices_guarded.py` (matches original semantics):

```
for target_d in missing_dates:
    # Fetch (no write)
    twse_df, _ = fetch_twse_historical(target_d)
    tpex_df, _ = fetch_tpex_historical(target_d)
    # QG check (no write)
    qg_result = run_quality_gate(combined_df, target_d, conn)
    if qg_result["status"] != "PASS":
        # QG fail → skip date, no write
        continue
    # Only write if QG passes
    _write_df_to_sqlite(conn, combined_df, target_d, execute)
    conn.commit()   ← per-date commit
    # State update happens after all dates processed
```

**Exact ordering**: `QG pass → write → conn.commit()` — per date, inside loop.

---

## Crash Window Analysis

| Phase | Crash Effect | Recovery |
|---|---|---|
| Before guard check | No data touched | Safe — retry authorized if lock held |
| After guard authorize, before connect | No data touched | Safe |
| After connect, before write | No data touched | Safe |
| After write, before conn.commit() | Write NOT committed (SQLite WAL) | Safe — retry will re-write same data (INSERT OR IGNORE) |
| After conn.commit(), before state update | Data committed; state = RUNNING | WRITE_OUTCOME_UNKNOWN on next run → FAIL_CLOSED |
| After state update (WRITE_COMMITTED) | Data committed; state reflects it | WRITE_COMMITTED_TODAY on next run → blocked (correct) |

**Key**: `conn.commit()` is per-date. A crash between dates leaves some dates committed and others not. The backfill uses `INSERT OR IGNORE` — idempotent — so a retry will commit the remaining dates without duplicating written ones.

**But**: State file is only updated by the integrated wrapper, not by the backfill itself. The original wrapper reads backfill `exit_code` only. If the guarded backfill crashes after writing, the original wrapper may still record `exit_code=0` (or non-zero) but won't have `write_committed=True` in state.

---

## `write_committed` Semantics

The `write_committed=True` field in the state file is written by `hybrid_shadow_cron_integrated.py`:
```python
# After backfill returns exit_code=0:
_save_guard_state(WRITE_COMMITTED, state_path, run_state)
```

The **original wrapper** (`hybrid_shadow_cron.py`) does NOT write `write_committed` to its state file. Its state file format is:
```json
{"run_at": "...", "today": "...", "status": "SUCCESS", "steps": {"backfill": {"exit_code": 0}}}
```

**Implication for Deploy A**: After Deploy A (original wrapper + guarded backfill), the state file will NOT contain `write_committed=True`. The `SameDayStateGuard`'s `WRITE_COMMITTED_TODAY` protection is only active if `hybrid_shadow_cron_integrated.py` is the wrapper. This guard is Deploy B (Integrated Wrapper) functionality.

---

## Lock Ownership

| Component | Lock Role | Timing |
|---|---|---|
| `hybrid_shadow_cron.py` | Acquires and holds for entire run | Before backfill, after pipeline completion |
| `backfill_daily_prices_guarded.py` | Checks only (LOCK_NB) — does NOT hold | Before write, releases immediately if acquired |
| `SameDayStateGuard` | No lock interaction | State file only |

**No parent/child deadlock possible**: The backfill uses `LOCK_EX | LOCK_NB` with immediate release on success. `BlockingIOError` is the authorized path. The check takes <1ms.

---

## State File Compatibility Matrix

| State Written By | Read By | Key Used | Behavior |
|---|---|---|---|
| Original wrapper | `SameDayStateGuard.check()` | `today` field | ALLOWED (different date format incompatibility noted below) |
| Integrated wrapper | `SameDayStateGuard.check()` | `scheduled_date` → WRITE_COMMITTED_TODAY | CORRECT |
| Original wrapper | Original wrapper (next run) | `today` + `status` | CORRECT (same format) |
| Integrated wrapper | Integrated wrapper (next run) | `scheduled_date` + `write_committed` | CORRECT |

### NEW FINDING: State Incompatibility After Calendar Advance (N-STATE-01)

**Root cause**: `SameDayStateGuard.check()` reads `state.get("today") or state.get("scheduled_date", "")`. Original wrapper writes `today=YYYY-MM-DD`.

**After cutover to integrated wrapper**: State from previous original-wrapper run has `today=2026-11-10`. New run with integrated wrapper has `scheduled_date=2026-11-13`. Guard reads `today=2026-11-10 ≠ scheduled_date=2026-11-13` → ALLOWED. **This is correct** — different day should be allowed.

**After rollback from integrated → original**: State has `scheduled_date=YYYY-MM-DD` (guard format). Original wrapper reads `today` from state → not present in guard-format state. `today=None` → outer wrapper logic does not block (uses its own date logic). **Rollback is safe.**

---

## Duplicate Write Risk Assessment

| Scenario | Risk | Mitigation |
|---|---|---|
| Retry of same day's backfill | LOW — `INSERT OR IGNORE` | Idempotent by design |
| Duplicate cron trigger same day | GUARDED by `SameDayStateGuard` (Deploy B) | Deploy A: no state guard, but wrapper still checks exit_code |
| Direct call + wrapper running same time | PREVENTED by wrapper holding lock | Guarded backfill gets AUTHORIZED, but lock acquired by wrapper prevents concurrent second backfill subprocess |

**Note**: Deploy A has no `SameDayStateGuard` protection (that's integrated wrapper only). However, the original wrapper already has its own state check (`today` field) and the cron schedule is once per day.

**Cannot claim Exactly-once Execution** for Deploy A: If cron fires multiple times (e.g., system time jump), the original wrapper has weak duplicate protection. This was true before S71M and remains true after Deploy A.
