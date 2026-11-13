# Session 71H — FileLock Coverage Analysis

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / IMPLEMENTATION_PLANNING_ONLY

---

## 1. Current Lock Inventory

| Lock | File | Mechanism | Scope | Owned by |
|---|---|---|---|---|
| Wrapper process lock | `data/.cron.lock` | `fcntl.flock(LOCK_EX|LOCK_NB)` | `hybrid_shadow_cron.py` pipeline | Wrapper |
| No lock | — | — | `backfill_daily_prices.py` direct run | None |
| No lock | — | — | `run_hybrid_forward_shadow.py` direct run | None |
| No lock | — | — | `sync_to_neon.py` | None |

**Lock file**: `data/.cron.lock`  
**Lock type**: Advisory exclusive, non-blocking (`LOCK_EX|LOCK_NB`)  
**Lock PID**: Written to file on acquisition  
**Release**: `finally:` block in wrapper → `lock.release()` → `fcntl.flock(LOCK_UN)` + `os.close(fd)`  
**Stale lock**: Advisory lock released automatically when process dies (file descriptor closed)

---

## 2. Lock Coverage Map

```
                     data/.cron.lock (advisory flock)
                              │
                    ┌─────────┴──────────┐
                    │  LOCKED             │  NOT LOCKED
                    │                     │
         hybrid_shadow_cron.py      backfill_daily_prices.py
         (wrapper + all stages)      (standalone --execute)
              FileLock: YES          FileLock: NO
                    │                     │
         ┌──────────┴──────┐              └── direct SQLite write
         │                  │                 (INSERT OR IGNORE protects rows)
     backfill         shadow runner
     (subprocess)     (subprocess)
     No own lock,     No own lock,
     wrapper lock     wrapper lock
     holds during     holds during
     wrapper run      wrapper run
```

---

## 3. Lock Gap Analysis

### Gap 1: Backfill Standalone Direct Entry

If a user runs `python3 scripts/backfill_daily_prices.py --execute` while cron is running:
- Wrapper holds `data/.cron.lock` via flock
- Backfill subprocess is called BY wrapper (different PID) → cannot acquire same flock during wrapper execution
- Independent backfill process (user-initiated) → different PID → tries flock → **succeeds** (advisory locks don't block same-file different-FD for different processes if one is a subprocess)

Wait — clarification needed. With `fcntl.flock`:
- If wrapper (PID A) holds LOCK_EX on `data/.cron.lock`
- Backfill subprocess called by wrapper (PID B, child of A) also tries flock on same file
- With `flock`, the lock is per-open-file-description: subprocess has a NEW file descriptor → it will BLOCK waiting for wrapper to release (or fail with LOCK_NB)
- With LOCK_NB: subprocess gets `BlockingIOError` → backfill returns `BLOCKED_LOCK` (exit 0)
- Wrapper sees exit 0 → "Done" → continues to freshness check → 0 data written → freshness FAIL

**DEADLOCK RISK**: If backfill in Option C is given its OWN lock acquire on the SAME lock file:
- Wrapper acquires lock (PID A)
- Wrapper calls backfill subprocess (PID B)
- PID B tries to acquire same lock → `BLOCKED_LOCK` (with LOCK_NB) → exits 0
- Wrapper sees exit 0 → continues with 0 data written → pipeline fails

This is NOT a traditional deadlock (PID B doesn't block waiting for PID A), but it is a functional failure where backfill always fails when called by wrapper. This is the Option C design risk.

**Current behavior (no lock in backfill)**: backfill subprocess called by wrapper does NOT try to acquire the lock → runs normally → writes data → wrapper sees exit 0 → continues. This is the CORRECT behavior.

### Gap 2: Backfill Direct User Invocation

If user runs `backfill_daily_prices.py --execute` independently (not via wrapper):
- No lock check
- Writes SQLite directly
- May write same dates as an in-progress cron run
- `INSERT OR IGNORE` prevents duplicate rows
- SQLite WAL serializes actual writes
- Risk: duplicate work, but no data corruption

---

## 4. Option Analysis

### Option A: Enforce All Production Runs Through Wrapper

**Description**: Document and enforce that `backfill_daily_prices.py --execute` should NEVER be called directly in production. Add a comment/warning in the script.

Optionally, add a soft warning (not a hard block):
```python
# PROPOSED (not authorized):
import sys
if sys.stdin.isatty() and os.environ.get("CALLED_FROM_WRAPPER") != "1":
    print("[WARNING] Direct execution of backfill_daily_prices.py --execute "
          "bypasses the FileLock in hybrid_shadow_cron.py. "
          "Use hybrid_shadow_cron.py --execute for production runs.", 
          file=sys.stderr)
```

| Attribute | Value |
|---|---|
| Implementation effort | LOW — warning message only |
| Deadlock risk | NONE |
| Protection | Documentation + warning, not technical enforcement |
| Verdict | `SUITABLE_MINIMAL` |

### Option B: Backfill Gets Own Lock (Separate Lock File)

**Description**: Add a DIFFERENT lock file `data/.backfill.lock` to `backfill_daily_prices.py`. Both wrapper and backfill use their own separate locks.

```python
# PROPOSED for backfill (not authorized):
BACKFILL_LOCK_FILE = Path(__file__).parent.parent / "data" / ".backfill.lock"
```

| Attribute | Value |
|---|---|
| Implementation effort | MEDIUM — add FileLock class to backfill |
| Deadlock risk | LOW (different lock files, no nesting) |
| Protection | Prevents concurrent standalone backfill runs |
| Covers wrapper+standalone overlap? | PARTIAL — wrapper doesn't acquire backfill lock |
| Verdict | `SUITABLE_MODERATE` |

### Option C: Wrapper + Backfill Share Same Lock — DEADLOCK RISK

**Description**: Backfill acquires SAME lock (`data/.cron.lock`) as wrapper.

**Problem**: Wrapper holds lock (PID A) → calls backfill subprocess (PID B) → PID B tries to acquire same lock → `BLOCKED_LOCK` (LOCK_NB) → backfill returns exit 0 → wrapper proceeds with 0 data written → freshness gate FAILS.

**Result**: Wrapper+backfill pipeline ALWAYS fails if Option C is implemented without re-entrant lock support.

**macOS `flock` re-entrancy**: `fcntl.flock` is NOT re-entrant by default between parent and child processes for LOCK_EX. The child (subprocess) gets a new file descriptor, so the parent's lock blocks the child.

| Attribute | Value |
|---|---|
| Implementation effort | MEDIUM |
| Deadlock risk | **HIGH — functional failure when called from wrapper** |
| Verdict | `NOT_RECOMMENDED` |

---

## 5. Recommended Approach

**Recommended: Option A (Wrapper Enforcement) + Optional Option B (Standalone Lock)**

For Phase 1 (minimum safe):
- Option A: Add warning to `backfill_daily_prices.py` for direct execution
- Document: "Production backfill always via `hybrid_shadow_cron.py --execute`"

For Phase 2 (complete protection):
- Option B: Add `data/.backfill.lock` to prevent concurrent standalone runs
- Do NOT use same lock file as wrapper (avoids child-process BLOCKED_LOCK)

**NOT Recommended**: Option C (shared lock file between wrapper and backfill subprocess) due to functional failure risk.

---

## 6. Lock Release Safety

| Scenario | Lock Released? | Evidence |
|---|---|---|
| Normal pipeline completion | YES | `finally:` at line 473 |
| Exception in any stage | YES | `finally:` catches all |
| `sys.exit()` called | YES | `finally:` runs before exit |
| `kill -9` (SIGKILL) | YES | Advisory lock released by OS when process dies |
| `kill -15` (SIGTERM) | YES | Python handles SIGTERM gracefully; finally runs |
| Machine crash | YES (after reboot) | Advisory lock file exists but OS releases on next open |
| Stale PID in lock file | YES | `flock` advisory — PID content is cosmetic; lock released by OS |

---

## 7. Verdict

| Item | Status |
|---|---|
| **Wrapper FileLock** | `VERIFIED` — covers all wrapper stages |
| **Backfill standalone lock** | `MISSING` — no lock |
| **Option A (warning)** | `LOCK_DESIGN_READY` — minimal safe |
| **Option B (separate lock)** | `LOCK_DESIGN_READY` — complete protection |
| **Option C (shared lock)** | `NOT_RECOMMENDED` — deadlock risk |
| **Overall** | `LOCK_DESIGN_READY` |
