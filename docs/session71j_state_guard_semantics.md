# Session 71J — State Guard Semantics

**Session**: 71J  
**Component**: `SameDayStateGuard` in `scripts/scheduler_safety_guards.py`

---

## 1. Purpose

The same-day state guard prevents the cron pipeline from running more than once
per trading day by consulting an atomic state file.

It does NOT replace the existing `.cron_state.json` logic — it extends it. The
guard reads the existing state file schema (`"today"` key) for compatibility and
writes a new schema (`"scheduled_date"` key) on first use.

---

## 2. Status Machine

```
                    ┌──────────────┐
                    │   RUNNING    │──(PID alive)──► CONCURRENT_RUN (block)
                    │              │──(PID dead)───► WRITE_OUTCOME_UNKNOWN (block)
                    └──────────────┘
                           │
              ┌────────────┼─────────────────────────┐
              │            │                         │
              ▼            ▼                         ▼
        QG_BLOCKED   PROVIDER_FAILED           WRITE_STARTED
            │              │                         │
            └──────────────┴──────────────────────── │
                       ALLOWED (retry)               │
                                                     ▼
                                             WRITE_COMMITTED ──► WRITE_COMMITTED_TODAY (block)
                                             write_committed=True
                                                     │
                                                     ▼
                                          POST_WRITE_CHECK_FAILED ──► WRITE_COMMITTED_TODAY (block)
                                          (write_committed=True)
                                                     │
                                                     ▼
                                                  SUCCESS ──────────► ALREADY_RAN_TODAY (block)
                                                  
                                                  FAILED ──────────► ALLOWED (retry)
```

---

## 3. Guard Decision Table

| State file `scheduled_date` | State file `status` | PID liveness | `write_committed` | Guard Decision |
|---|---|---|---|---|
| (absent / empty) | — | — | — | `ALLOWED` (first run) |
| ≠ today | any | — | — | `ALLOWED` (prior day) |
| = today | SUCCESS | — | — | `ALREADY_RAN_TODAY` |
| = today | WRITE_COMMITTED | — | — | `WRITE_COMMITTED_TODAY` |
| = today | any | — | True | `WRITE_COMMITTED_TODAY` |
| = today | RUNNING | alive | — | `CONCURRENT_RUN` |
| = today | RUNNING | dead / 0 | — | `WRITE_OUTCOME_UNKNOWN` |
| = today | QG_BLOCKED | — | False | `ALLOWED` |
| = today | PROVIDER_FAILED | — | False | `ALLOWED` |
| = today | POST_WRITE_CHECK_FAILED | — | False | `ALLOWED` |
| = today | FAILED | — | False | `ALLOWED` |
| (corrupt JSON) | — | — | — | `FAIL_CLOSED_CORRUPT` |

---

## 4. Atomic Write Protocol

```
write_state(state):
  1. serialize state to JSON
  2. strip secrets (database_url, api_key, password, secret)
  3. write to path + ".tmp"   (write-then-replace pattern)
  4. os.replace(".tmp", target)   ← atomic on POSIX
  5. return True

on failure at any step:
  return False (non-fatal — caller logs and continues)
```

The temp file is written to the same filesystem as the target, so `os.replace`
is an atomic rename (no cross-filesystem rename). On macOS (APFS/HFS+), `os.replace`
calls `rename(2)` which is guaranteed atomic.

---

## 5. State File Schema

```json
{
  "schema_version": 1,
  "run_id": "cron-2026-11-12-a1b2c3d4",
  "scheduled_date": "2026-11-12",
  "actual_start_utc": "2026-11-12T08:00:01Z",
  "pid": 12345,
  "status": "RUNNING",
  "guard_decision": "ALLOWED",
  "write_committed": false,
  "post_write_check": ""
}
```

**Backward compatibility**: The guard reads `"today"` as a fallback key when
`"scheduled_date"` is absent. This matches the existing `.cron_state.json` format.

**No secrets**: `database_url`, `api_key`, `password`, `secret` are stripped before write.

---

## 6. WRITE_OUTCOME_UNKNOWN Handling

When a run crashed with `status=RUNNING` and the PID is no longer alive,
the guard cannot determine whether SQLite was written (the crash may have
occurred before or after the INSERT commit).

**Decision**: Block and require manual intervention.

**Rationale**: SQLite `INSERT OR IGNORE` protects against duplicate rows, but
re-running without investigation risks:
- Logging duplicate `run_id` entries
- Triggering duplicate shadow runner execution
- Masking the crash root cause

**Manual recovery**:
```bash
# Check if rows were written
sqlite3 data/platform.db \
  "SELECT date, COUNT(*) FROM daily_prices WHERE date = '2026-11-12' GROUP BY date;"

# If 0 rows: safe to reset state to FAILED for retry
# If N rows: data was written; reset state to WRITE_COMMITTED

# Reset state (manual)
echo '{"scheduled_date":"2026-11-12","status":"WRITE_COMMITTED","write_committed":true}' \
  > data/.cron_state.json
```

---

## 7. Stale RUNNING Detection

A RUNNING state from a prior calendar day does NOT trigger `WRITE_OUTCOME_UNKNOWN`.
If `scheduled_date != today`, the guard returns ALLOWED regardless of status.

This prevents a Nov 11 crash from blocking Nov 12's run.

---

## 8. Relationship to Existing `.cron_state.json`

The existing state file will be used as the guard's state file once Phase 2
integration is authorized. Until then, the guard uses whichever path is passed
by the caller.

The guard adds these new fields to the existing schema:
- `schema_version`
- `run_id`
- `scheduled_date` (alias for existing `"today"`)
- `guard_decision`
- `write_committed`
- `post_write_check`

Existing fields (`run_at`, `steps`, `trigger_source`, `exit_code`) are preserved.
