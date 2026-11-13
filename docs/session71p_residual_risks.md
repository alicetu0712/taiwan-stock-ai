# Session 71P — Residual Risks

**Session**: 71P  
**Verdict**: `RESIDUAL_RISKS_DOCUMENTED`

---

## Deploy A Safety Limitations (per PART I)

### L1 — Same-day State

Deploy A does not activate the full Integrated Wrapper (`hybrid_shadow_cron_integrated.py`). The `write_committed=True` field is NOT written to the state file by the original wrapper. The `WRITE_COMMITTED_TODAY` duplicate protection is **Deploy B only**.

**Remaining protection under Deploy A**: FileLock + SQLite `INSERT OR IGNORE` constraints.

---

### L2 — Duplicate Execution

Deploy A's main protections are:
- `fcntl.flock(LOCK_EX)` on `.cron.lock` (held by wrapper for entire run)
- SQLite `INSERT OR IGNORE` constraints

This is **not** exactly-once execution. If the lock is released by the wrapper and cron fires again on the same day (unusual), a second backfill attempt is possible. The SQLite constraint will prevent duplicate rows but the network call will still occur.

---

### L3 — Internal Entry Coverage Gap

As documented in S71N (`GAP_REMAINS`): the guard only covers the `--execute` path. `--dry-run` calls are intentionally unguarded (no writes possible). No change from S71N finding.

---

### L4 — Crash Recovery

Deploy A does not add crash recovery beyond existing behavior. If the backfill crashes after starting a write transaction, SQLite's journal mode handles rollback. No application-level crash guard until Deploy B.

---

### L5 — H3 Runtime Acceptance

H3 (`RC-2 H3`) remains `H3_PENDING`. H3 requires the first natural cron execution after Deploy A to complete successfully with the guarded backfill. This cannot be verified by hash, import, or mock tests — only by actual cron runtime evidence.

**Next H3 opportunity**: 2026-11-13 16:00 CST (today, if a trading day).

---

## Deployment-Specific Residual Risks

### R-01 — Single Natural Cron Run as H3 Evidence

The first post-Deploy-A cron run will be the H3 acceptance test. If the machine is asleep at 16:00 CST, H3 is missed again. This risk is not new — it was present from S66 onwards.

### R-02 — Guard Module Version Pinning Not Enforced

`scheduler_safety_guards.py` is not pinned to a specific hash at runtime. If the file were modified between Deploy A and the next cron run, the guard behavior could change without notice. No such modification is authorized, but the system does not enforce this automatically.

### R-03 — No Rollback Test Executed

The rollback procedure was documented and verified as executable (backup readable, hash match confirmed) but was not actually executed (not needed). This is by design.
