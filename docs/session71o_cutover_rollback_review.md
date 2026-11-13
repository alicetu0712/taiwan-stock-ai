# Session 71O — Cutover & Rollback Review

**Session**: 71O  
**Verdict**: `CUTOVER_ROLLBACK_VERIFIED`

---

## Cutover Design Review

This document re-verifies the atomic cutover plan from S71N against S71O findings (calendar-stale fix, regression results).

### Did S71O change the cutover plan?

**No.** S71O modified only test files (`test_session71l_safety.py`, `test_wrapper_integration.py`, new `test_session71o_date_boundary.py`). No production scripts were touched. The Deploy A artifact set, hashes, and atomic cutover procedure are unchanged from S71N.

---

## Cutover Checklist (S71N plan, S71O confirmed)

| Step | Action | Prerequisite |
|---|---|---|
| C-01 | Verify cron is not running | No `.cron.lock` held |
| C-02 | Hash-verify `scheduler_safety_guards.py` = `f6929a7c...` | File exists |
| C-03 | Hash-verify `backfill_daily_prices_guarded.py` = `202e2231...` | File exists |
| C-04 | `cp backfill_daily_prices_guarded.py /tmp/backfill_daily_prices.py.new` | /tmp writable |
| C-05 | `mv /tmp/backfill_daily_prices.py.new scripts/backfill_daily_prices.py` | APFS atomic rename |
| C-06 | Hash-verify `backfill_daily_prices.py` = `202e2231...` | Same hash as guarded |
| C-07 | Test dry-run: `python scripts/backfill_daily_prices.py --dry-run` | Exit 0 expected |
| C-08 | Monitor first cron run after 16:00 CST | H3 acceptance |

### Why atomic?

`mv` on APFS executes a kernel `rename(2)` syscall. The file descriptor swap is atomic — there is no window where the file is partially written or absent. Any reader sees either the old or the new version, never an intermediate state.

---

## H3 Acceptance Definition (unchanged from S71N)

**H3**: First cron execution after Deploy A completes without error, guard fires as expected, and backfill writes data to SQLite.

| Condition | Evidence |
|---|---|
| `[BACKFILL_GUARD] BLOCKED` absent from cron log | Guard authorized (lock held by wrapper) |
| Backfill exit code 0 | Normal completion |
| `max(date)` in SQLite advances | Write committed |
| No `GUARD_WINDOW` or `GUARD_STATE` in cron log | No unexpected block |

---

## Rollback Procedure

| Step | Action |
|---|---|
| R-01 | `cp scripts/backfill_daily_prices.py /tmp/backfill_daily_prices.py.bak` (save current) |
| R-02 | Restore from backup: original hash `4eb6eacf...` |
| R-03 | Hash-verify restored file |
| R-04 | Monitor next cron run |

**`scheduler_safety_guards.py` does not need rollback** — it is backward-compatible with the original backfill (which does not import it). The guard module being present does not affect original backfill behavior.

---

## S71O-Specific Confidence

After S71O:
- 157/157 guard tests PASS
- 37 pre-existing failures UNCHANGED (no regression)
- 4 calendar-stale failures FIXED
- Cutover procedure not modified
- Rollback procedure not modified

**Conclusion**: The cutover and rollback plan from S71N remains valid and is not affected by S71O findings.
