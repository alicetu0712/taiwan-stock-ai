# Session 71N — Scheduler Migration Dependencies

**Session**: 71N  
**Verdict**: `DEPLOYMENT_A_INDEPENDENT_FROM_DEPLOYMENT_B`

---

## Two Deployments Defined

### Deployment A — Safety Guard Runtime
**Goal**: Replace `backfill_daily_prices.py` with guarded version.  
**Scheduler**: macOS cron (UNCHANGED)  
**Files changed**: `backfill_daily_prices.py` (+ `scheduler_safety_guards.py` already in place)  
**Wrapper**: `hybrid_shadow_cron.py` (UNCHANGED)  

### Deployment B — Scheduler Migration
**Goal**: Replace cron with launchd (sleeping-machine safety).  
**Files changed**: Remove cron entry, install launchd plist, update wrapper integration.  
**Prerequisite**: Deploy A complete + H3 root cause addressed.

---

## Can Deployment A proceed independently of Deployment B?

**YES.** Explicit justification:

1. Deploy A does not modify `crontab` — existing cron entry still runs `hybrid_shadow_cron.py --execute`
2. Deploy A does not install or reference any launchd components
3. After Deploy A: `cron → hybrid_shadow_cron.py → backfill_daily_prices.py (guarded)` — works correctly
4. The lock-based guard works with any caller that acquires `data/.cron.lock` before subprocess — cron does this via the wrapper's `FileLock.acquire()`

---

## Minimum Artifact Set for Deploy A

| File | Action | Required? |
|---|---|---|
| `scripts/backfill_daily_prices.py` | Replace with guarded version | YES |
| `scripts/scheduler_safety_guards.py` | Already in place, verify hash | YES (verify only) |
| `scripts/hybrid_shadow_cron.py` | No change | NO |
| `scripts/hybrid_shadow_cron_integrated.py` | Deploy B only | NO for Deploy A |
| launchd plist | Deploy B only | NO for Deploy A |

---

## Risks of Deploy A (independent)

| Risk | Severity | Mitigation |
|---|---|---|
| Guard blocks cron run if lock not held | MEDIUM | Lock is held by wrapper — verified via N-lock-01 |
| New `exit_code=2` confuses original wrapper | LOW | Wrapper treats non-zero as BACKFILL_FAILED — correct fail-closed behavior |
| `scheduler_safety_guards.py` import error | LOW | File already in place with correct hash `f6929a7c...` |
| No `SameDayStateGuard` in Deploy A | INFO | Original wrapper has weak same-day protection; backfill is idempotent |

---

## Prerequisites for Deploy B

Deploy B (launchd migration) requires:

1. ✅ Deploy A complete (guarded backfill in place)
2. ✅ H3 acceptance confirmed (cron runs detected successfully)
3. ✅ `hybrid_shadow_cron_integrated.py` deployment authorized
4. ✅ Cron entry deactivated (not deleted — disable first)
5. ✅ launchd plist tested in isolated environment
6. ✅ Overlap prevention: cannot have both cron AND launchd running simultaneously

---

## Acceptance Gates Between A and B

| Gate | Criterion |
|---|---|
| Deploy A acceptance | 1+ successful cron run with guarded backfill (H3 observation) |
| Deploy A data correctness | SQLite row count increases as expected after trading day |
| Deploy A guard behavior | No unexpected guard blocks in cron log |
| Pre-B gate | At least 2 weeks stable operation under Deploy A |

---

## Two-Scheduler Risk

If both cron AND launchd are active simultaneously:
- Both fire at ~16:00 CST
- Both call `hybrid_shadow_cron.py --execute`
- Wrapper's `FileLock.acquire()` prevents the second one from proceeding
- Winner runs; loser exits early with "LOCKED" status

**This is correct behavior**, but running two schedulers is unnecessary. Deploy B should DEACTIVATE cron before activating launchd.

**NOT safe to test both simultaneously in production.**
