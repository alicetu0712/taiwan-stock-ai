# Session 71H — Same-day Run Guard Design

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / IMPLEMENTATION_PLANNING_ONLY

---

## 1. The Problem

The current pipeline has no same-day run guard. A sequential re-run on the same day (e.g., cron fires at 16:00 and completes; launchd then fires a catch-up at 16:30) results in:
1. Backfill: `_find_missing_dates()` returns empty → 0 inserts (safe)
2. Freshness gate: passes (data already fresh from first run)
3. **Shadow runner: runs again, creates new `run_id`, detects decision CONFLICT** ← not ideal

The guard must NOT simply block all re-runs. BLOCKED_STALE_DATA means no data was written and retry is desirable.

---

## 2. Guard State Semantics

### Question: What states should BLOCK same-day re-run?

| State | Data Written? | Shadow Ran? | Block Re-run? | Rationale |
|---|---|---|---|---|
| `SUCCESS` | YES | YES | **YES** | Pipeline complete; re-run pollutes shadow run log |
| `BLOCKED_STALE_DATA` | NO | NO | **NO** | TWSE not ready; retry is the design intent |
| `BLOCKED_PARTIAL_MARKET` | PARTIAL | NO | **NO** | Data partially written; retry valid |
| `BLOCKED_LOCK` | NO | NO | **NO** | Another instance was running; retry valid |
| `SKIPPED_NON_TRADING_DAY` | NO | NO | **NO** | Legitimate skip; re-run should also skip |
| `DATA_NOT_READY` | NO | NO | **NO** | TWSE pre-15:30; retry valid |
| `DRY_RUN_OK` | NO | NO | **NO** | No writes; dry-run only |
| `BACKFILL_FAILED` | UNKNOWN | NO | **CONDITIONAL** | Need to check if any date was partially committed |
| `SHADOW_FAILED` | YES | PARTIAL | **CONDITIONAL** | Backfill succeeded; shadow failed — depends on use case |
| `EXECUTION_WINDOW_EXPIRED` (new) | NO | NO | **NO** | Legitimate skip |

### Critical distinction: `BLOCKED_STALE_DATA` after partial writes

The state can be `BLOCKED_STALE_DATA` even when some dates WERE written. Example:
- Nov 06, Nov 09 data written successfully
- Nov 10 (today) data: QG-5 blocked (api_date = Nov 09 ≠ Nov 10)
- Post-write freshness gate for Nov 10: PROVIDER_NOT_READY
- Status: `BLOCKED_STALE_DATA`

In this case, retrying is CORRECT — the Nov 10 data wasn't written, and next run will skip Nov 06/09 (already covered) and re-attempt Nov 10.

**Conclusion**: Guard key is `status == "SUCCESS"` with correct date matching.

---

## 3. Guard Design Options

### Option 1: File-based Run Ledger

A separate JSON file `data/.daily_run_ledger.json`:

```json
{
  "scheduled_date": "2026-11-12",
  "run_id": "a1b2c3d4",
  "started_at": "2026-11-12T08:00:05Z",
  "status": "SUCCESS",
  "data_written": true,
  "shadow_ran": true,
  "finished_at": "2026-11-12T08:03:21Z"
}
```

| Attribute | Assessment |
|---|---|
| Guard key | `scheduled_date == str(date.today()) AND status == "SUCCESS"` |
| Atomicity | File write is NOT atomic; crash between writes → partial ledger |
| Corrupted ledger | FAIL_CLOSED: treat corrupted ledger as "no prior run" (allow run) |
| Auditability | Good — human readable |
| Implementation effort | LOW — simple JSON |
| Risk | Race condition if two processes write simultaneously |

### Option 2: SQLite Run Ledger

New table `cron_run_ledger` in `data/platform.db`:

```sql
CREATE TABLE IF NOT EXISTS cron_run_ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scheduled_date TEXT NOT NULL,
    run_id       TEXT NOT NULL UNIQUE,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL,
    data_written INTEGER DEFAULT 0,
    shadow_ran   INTEGER DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_crl_success 
  ON cron_run_ledger(scheduled_date) WHERE status = 'SUCCESS';
```

| Attribute | Assessment |
|---|---|
| Guard key | `SELECT 1 FROM cron_run_ledger WHERE scheduled_date = ? AND status = 'SUCCESS'` |
| Atomicity | SQLite transactions (atomic) |
| Corrupted ledger | SQLite detects corruption; FAIL_CLOSED |
| Auditability | Good — queryable |
| Implementation effort | MEDIUM — requires schema migration |
| Risk | Requires DB connection in guard check (adds dependency) |

### Option 3: Existing Log-derived Guard

Parse `logs/hybrid_cron.log` or `data/.cron_state.json`:

```python
state = json.loads(Path("data/.cron_state.json").read_text())
if state.get("today") == str(date.today()) and state.get("status") == "SUCCESS":
    return "ALREADY_RAN_TODAY"
```

| Attribute | Assessment |
|---|---|
| Guard key | `state["today"] == str(today) AND state["status"] == "SUCCESS"` |
| Atomicity | File write not atomic; but state file is already in use |
| Corrupted state | FAIL_OPEN (treat missing state as no prior run) → need FAIL_CLOSED modification |
| Auditability | Reuses existing infrastructure |
| Implementation effort | MINIMAL — 3 lines in `run_cron_pipeline()` |
| Risk | State file can be manually edited; less auditable than SQLite |

### Option 4: State File + RUNNING Marker (Recommended)

Augment the existing state file with a RUNNING marker and SUCCESS marker:

**Write RUNNING at start (before lock check in state):**
```python
# Step 0 (before lock acquire or just after):
# Check prior state
state = _load_state()
prior_today = state.get("today")
prior_status = state.get("status")
if prior_today == str(today) and prior_status == "SUCCESS":
    _log(f"[cron] ALREADY_RAN_TODAY: {today} — prior run completed successfully, skipping")
    result["status"] = "ALREADY_RAN_TODAY"
    return result
```

| Attribute | Assessment |
|---|---|
| Guard key | `state["today"] == str(today) AND state["status"] == "SUCCESS"` |
| Atomicity | None added; relies on state file existing |
| Corrupted state | Load error → `{}` → prior_today = None → allow run (safe) |
| Auditability | Reuses existing `data/.cron_state.json` |
| Implementation effort | **MINIMAL** — 4 lines |
| Risk | Does not cover RUNNING state mid-execution (FileLock handles this) |
| FAIL_CLOSED | YES for SUCCESS state; corrupted → allow run (conservative) |

---

## 4. Recommended Design: Option 4 (State File Guard)

**Recommended approach**: Use existing `.cron_state.json` as the guard source. Add a check AFTER FileLock acquisition (since FileLock handles concurrent runs) but BEFORE the calendar check.

```python
# PROPOSED — not authorized, not implemented
# Location: run_cron_pipeline(), after Stage 1 (FileLock acquired), before Stage 2

# Step 1b: Same-day SUCCESS guard
prior_state = _load_state()
if (
    prior_state.get("today") == str(today)
    and prior_state.get("status") == "SUCCESS"
    and prior_state.get("execute") is True
):
    _log(f"[cron] ALREADY_RAN_TODAY: {today} completed successfully at "
         f"{prior_state.get('taiwan_time', 'unknown')} — skipping")
    result["status"] = "ALREADY_RAN_TODAY"
    result["steps"]["same_day_guard"] = "BLOCKED_ALREADY_SUCCESS"
    return result
result["steps"]["same_day_guard"] = "ALLOWED"
```

**Add "ALREADY_RAN_TODAY" to clean_statuses** (exit 0).

---

## 5. State Machine

```
                   ┌─────────────────────────────────┐
                   │     Same-day Guard Check         │
                   │  today == state["today"]?         │
                   │  AND state["status"] == SUCCESS?  │
                   └─────────────────────────────────┘
                              │                │
                             YES              NO
                              │                │
                     BLOCKED_ALREADY         PROCEED
                     (exit 0, skip)         (continue pipeline)
```

---

## 6. What States Allow Retry

| Prior Status | Allow Same-Day Retry? | Reason |
|---|---|---|
| `SUCCESS` | **NO** | Pipeline complete |
| `BLOCKED_STALE_DATA` | YES | TWSE data not ready; retry expected |
| `BLOCKED_PARTIAL_MARKET` | YES | Partial data; retry valid |
| `BLOCKED_LOCK` | YES | Concurrent block; retry valid |
| `SKIPPED_NON_TRADING_DAY` | YES | (Will re-skip — harmless) |
| `DATA_NOT_READY` | YES | TWSE pre-15:30; retry valid |
| `BACKFILL_FAILED` | YES | Script crashed; retry valid |
| `SHADOW_FAILED` | YES | Shadow failed; backfill OK; retry valid for shadow |
| `DRY_RUN_OK` | YES | No writes |
| `ALREADY_RAN_TODAY` | YES | (Will re-check and re-block) |
| None (first run) | YES | No prior state |

---

## 7. QG FAIL After Partial Write

Scenario: Nov 06 and Nov 09 data written (QG pass); Nov 10 blocked (QG-5: api_date mismatch). Status = `BLOCKED_STALE_DATA`.

Same-day guard behavior:
1. Guard checks: `status == "SUCCESS"`? NO → ALLOW retry
2. Second run: `_find_missing_dates()` returns [Nov 10] only (Nov 06/09 covered by INSERT OR IGNORE)
3. Fetches Nov 10 data again → QG-5 checks → writes if api_date matches
4. If still blocked: status remains `BLOCKED_STALE_DATA` (allow next retry)

**No data loss. No duplicate writes. Guard correctly allows retry.**

---

## 8. Verdict

| Option | Verdict | Recommended |
|---|---|---|
| Option 1 (File Ledger) | `DESIGN_READY` | No |
| Option 2 (SQLite Ledger) | `DESIGN_READY` | No (overkill) |
| Option 3 (Log-derived) | `DESIGN_PARTIAL` | No |
| **Option 4 (State File Guard)** | **`DESIGN_READY`** | **YES** |

**`DESIGN_READY`** — Recommended as minimal, auditable guard. Requires 4 lines added to `hybrid_shadow_cron.py` and 1 new status in `clean_statuses`. Separate authorization required.
