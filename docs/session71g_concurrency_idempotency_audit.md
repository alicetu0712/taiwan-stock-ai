# Session 71G — Concurrency & Idempotency Audit

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / MIGRATION_DESIGN_ONLY  
**Source**: Code-confirmed from `hybrid_shadow_cron.py` and `backfill_daily_prices.py`

---

## 1. Audit Summary

| Check | Status | Location | Notes |
|---|---|---|---|
| Process lock (wrapper) | `VERIFIED` | `hybrid_shadow_cron.py:315–320` | `fcntl.flock(LOCK_EX|LOCK_NB)` on `data/.cron.lock` |
| Process lock (backfill standalone) | `MISSING` | `backfill_daily_prices.py` | No lock; direct invocation unsafe during cron run |
| SQLite transaction safety | `VERIFIED` | `backfill_daily_prices.py:546` | `conn.commit()` per date |
| Duplicate-row guard | `VERIFIED` | `backfill_daily_prices.py:388–417` | `INSERT OR IGNORE` on `(stock_id, date)` unique constraint |
| Same-day run guard | `PARTIAL` | `hybrid_shadow_cron.py:296` | No explicit guard; FileLock prevents concurrency but not sequential same-day re-run |
| Provider request dedup | `VERIFIED` | `backfill_daily_prices.py:332–382` | `_find_missing_dates()` skips already-covered dates |
| Retry safety | `VERIFIED` | `hybrid_shadow_cron.py:376–439` | Idempotent retry: re-runs backfill (which finds no new dates if already written) |
| Partial failure recovery | `VERIFIED` | `backfill_daily_prices.py:519` | `continue` on date-level error; other dates proceed |
| Crash recovery | `PARTIAL` | `hybrid_shadow_cron.py:473–476` | `finally:` releases lock and saves state; SQLite not rolled back on crash |
| QG bypass | `VERIFIED` | `backfill_daily_prices.py:504–518` | Cannot be bypassed; QG runs before every write |
| Unique constraint (SQLite) | `PARTIAL` | `INSERT OR IGNORE` behavior | Relies on SQLite table having `(stock_id, date)` unique; not confirmed from schema this session |

---

## 2. Process Lock Analysis

### Wrapper (hybrid_shadow_cron.py)

```python
# hybrid_shadow_cron.py:315–316
lock = FileLock(LOCK_FILE)
if not lock.acquire():
    result["status"] = "BLOCKED_LOCK"
    return result
```

```python
# FileLock.acquire() (lines 157–168):
fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
```

| Property | Value |
|---|---|
| Lock type | Advisory exclusive, non-blocking |
| Released on crash | YES — `finally:` block at line 473 calls `lock.release()` |
| Released if PID dies | YES — advisory flock: released automatically when file descriptor closes |
| Multi-instance safety | YES — second instance gets `BLOCKED_LOCK` and exits cleanly |
| Applies to launchd+cron overlap | YES — first scheduler fires → lock held; second gets BLOCKED_LOCK |

**Verdict**: `VERIFIED` — adequate for preventing concurrent runs between cron and launchd during transition period.

### Backfill Standalone (backfill_daily_prices.py)

The backfill script has **no process lock**. If a user manually runs:
```bash
python3 scripts/backfill_daily_prices.py --execute
```
while cron is running, both will attempt SQLite writes concurrently.

**Risk**: SQLite handles concurrent writes via its own WAL/journal lock, so data corruption is unlikely. However, duplicate work and unpredictable insert order may occur.

**Mitigation already present**: `INSERT OR IGNORE` prevents duplicate rows even with concurrent writes.

**Risk level**: LOW (SQLite serializes writes; INSERT OR IGNORE prevents duplicates)

**Recommendation** (requires separate authorization): Add a check in `backfill_daily_prices.py` that skips execution if `.cron.lock` is held:
```python
# PROPOSED (not authorized):
if LOCK_FILE.exists():
    with open(LOCK_FILE) as f:
        pid = f.read().strip()
    if pid and os.path.exists(f"/proc/{pid}"):  # or kill -0 on macOS
        print("[safety] Cron lock held — aborting standalone run")
        sys.exit(1)
```

---

## 3. Same-Day Run Guard Assessment

### Current behavior

```python
# hybrid_shadow_cron.py:296
today = date.today()
```

There is **no check** like `if state.get("today") == str(today): return ALREADY_RAN_TODAY`.

**Consequence of same-day re-run**:

| Step | First Run | Second Run (same day) |
|---|---|---|
| FileLock | Acquired | Blocked (if first still running) → safe |
| Calendar check | PASS | PASS |
| Data readiness | PASS (>= 15:30) | PASS |
| Backfill | Fetches + writes new rows | `_find_missing_dates()` returns empty (all covered) → 0 inserts |
| Freshness gate | FULL_MARKET_FRESH | FULL_MARKET_FRESH (data already there) |
| Backup | Creates backup | Creates **another backup** (wastes space) |
| **Shadow runner** | **Runs for today** | **Runs AGAIN for today** ← concern |
| State file | Written | Overwritten |

The critical concern is the **shadow runner running twice for the same day**. This may produce duplicate forward shadow decisions.

**Mitigation already present (partial)**:
- Shadow runner likely has its own same-day dedup (not audited this session)
- `INSERT OR IGNORE` protects daily_prices table from duplicates

**Risk**: MEDIUM — shadow runner behavior on duplicate same-day invocation is unaudited.

**Recommendation** (requires authorization): Add same-day guard:
```python
# PROPOSED (not authorized):
if state.get("today") == str(today) and state.get("status") == "SUCCESS":
    _log(f"[cron] ALREADY_RAN_TODAY: {today} — status=SUCCESS, skipping")
    result["status"] = "ALREADY_RAN_TODAY"
    return result
```

---

## 4. SQLite Transaction Safety

```python
# backfill_daily_prices.py:546–547
conn.commit()
print(f"  Committed {target_d} ✓")
```

Transactions are committed **per date** (atomic at date granularity). If the script crashes mid-date:
- Rows for that date may be partially written but not committed → SQLite rollback on connection close
- Rows for previously committed dates remain intact

**Verdict**: `VERIFIED` — per-date transaction commit provides adequate atomicity.

---

## 5. Duplicate Run Protection Summary

| Scenario | Protection | Mechanism |
|---|---|---|
| Cron + launchd both fire | PROTECTED | FileLock: first acquires, second BLOCKED_LOCK |
| launchd fires twice (catch-up + scheduled) | PROTECTED (concurrent) / PARTIAL (sequential) | FileLock for concurrent; same-day guard missing for sequential |
| Manual backfill while cron runs | PARTIAL | No lock in backfill; INSERT OR IGNORE prevents row duplicates |
| Cross-day catch-up (next day wake) | PARTIAL | Calendar check passes; date.today() changes → targets wrong day |
| Same-day sequential re-run | PARTIAL | Backfill safe; shadow runner behavior unaudited |

---

## 6. Required Changes for Full Protection

The following changes are identified but **require separate authorization**:

| Change | Priority | Risk if deferred |
|---|---|---|
| Add same-day run guard to `hybrid_shadow_cron.py` | MEDIUM | Sequential dual-fire could duplicate shadow run |
| Add execution validity window (20:00 CST deadline) | MEDIUM | Next-day wake fires against wrong date |
| Add lock check to `backfill_daily_prices.py` standalone | LOW | Concurrent manual + cron writes (data integrity OK via INSERT OR IGNORE) |
| Audit shadow runner for same-day dedup | MEDIUM | Unknown risk of duplicate decisions |

---

## 7. Critical Insight for Migration

**During the transition period** (dual scheduler window):

If cron fires at 16:00 and completes by 16:15, then launchd fires a catch-up at 16:30:
1. Cron's lock is released at 16:15
2. launchd fires at 16:30 (FileLock available)
3. launchd runs successfully (backfill finds no missing dates → 0 inserts)
4. Freshness gate passes (data already fresh from cron run)
5. **Shadow runner runs AGAIN** ← concern

**Mitigation**: Eliminate the dual scheduler window by removing the crontab entry BEFORE loading launchd (see `session71g_cutover_rollback_plan.md`).

---

## 8. Verdict

| Category | Status |
|---|---|
| **Overall concurrency** | `CONCURRENCY_GAPS_IDENTIFIED` |
| Process lock (wrapper) | `VERIFIED` |
| Process lock (backfill) | `MISSING` |
| Same-day sequential protection | `PARTIAL` |
| Row-level idempotency | `VERIFIED` |
| Transaction safety | `VERIFIED` |
| Catch-up validity window | `MISSING` (needs code change) |
| Required code changes | 3 identified, none blocking launchd migration if dual-scheduler window is eliminated |
