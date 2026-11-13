# Session 71O — Deploy A Residual Risks

**Session**: 71O  
**Verdict**: `RESIDUAL_RISKS_DOCUMENTED`

---

## Risk Register

### R-01 — Lock-based Authorization Only Covers Execute Path

**Severity**: MEDIUM  
**Category**: Guard Coverage Gap

**Description**: `BackfillEntryGuard.check_original_entry()` is only inserted at the `--execute` branch of `run_backfill()` and `main()`. The `--dry-run` path (execute=False) bypasses the guard entirely.

**Mitigated by**: The lock is only held by the cron wrapper when it calls backfill with `--execute`. Dry-run calls are not safety-critical (no writes to production).

**Residual**: An operator running `python backfill_daily_prices.py --execute` from a shell without the wrapper's lock held will be BLOCKED (guard returns BLOCKED). This is expected behavior.

---

### R-02 — `write_committed=True` Protection Absent (Deploy A)

**Severity**: LOW  
**Category**: Duplicate-run Protection Gap

**Description**: Under Deploy A, the original wrapper (`hybrid_shadow_cron.py`) does **not** write `write_committed=True` to the state file after a successful backfill. This means a rare crash-after-commit scenario could allow a re-run before the state file is updated.

**Mitigated by**: The `SameDayStateGuard` still blocks via `scheduled_date` / `today` field match — covers the common case. The `write_committed` layer is Deploy B only.

**Residual**: Window between commit and state-file write is seconds. Operational risk is minimal.

---

### R-03 — Single-Node Lock (No Distributed Lock)

**Severity**: LOW  
**Category**: Architecture Assumption

**Description**: `fcntl.flock` is POSIX file locking — it is per-host. If the cron were ever run on multiple machines, the lock would not prevent cross-machine duplicate runs.

**Mitigated by**: This is a single-machine personal research platform. No distributed deployment is planned.

**Residual**: If infrastructure changes, this assumption must be re-evaluated.

---

### R-04 — Guard Module Hash Drift

**Severity**: LOW  
**Category**: Deployment Integrity

**Description**: `scheduler_safety_guards.py` is verified by hash at session-start and deploy-time. If the file is modified after Deploy A verification but before cutover, the guard behavior could change.

**Mitigated by**: The deploy procedure verifies the hash immediately before the `cp/mv` sequence. The window is seconds.

**Residual**: Recommend pinning `f6929a7c...` hash in deployment checklist and re-verifying after cutover.

---

### R-05 — `OSError` → Lock Treated as Not Held

**Severity**: LOW  
**Category**: Fail-safe Direction

**Description**: `_check_lock_state()` catches `OSError` and returns `(False, "lock check failed")`. On a filesystem permission error or quota issue, the lock is treated as NOT HELD → guard BLOCKS the backfill.

**Mitigated by**: This is fail-closed behavior — an OSError causes the backfill to be blocked rather than allowed. This is the safer direction.

**Residual**: If the lock file directory has persistent permissions issues, every execution attempt will be BLOCKED. Monitor for `[BACKFILL_GUARD] BLOCKED: lock check failed` in stderr.

---

### R-06 — Maintenance Override Both-Key Requirement

**Severity**: LOW  
**Category**: Operational Complexity

**Description**: The two-key maintenance override (`BACKFILL_ALLOW_DIRECT=1` AND `BACKFILL_MAINTENANCE_REASON=<non-empty>`) is easy to forget. If only one key is set, the override is `MAINTENANCE_AUTHORIZATION_INCOMPLETE` and the backfill is BLOCKED.

**Mitigated by**: The error message is explicit: `MAINTENANCE_AUTHORIZATION_INCOMPLETE`. The operator receives a clear diagnostic.

**Residual**: Document the two-key requirement in the operations runbook.

---

## Not-a-Risk Clarifications

| Item | Assessment |
|---|---|
| Calendar-stale failures (N-FINDING-01) | FIXED in S71O — not a production risk |
| RC-2 filter drift | AST-verified identical (S71N rc2_qg_semantic_diff.md) |
| Quality Gate preservation | Verified unchanged (S71N) |
| Original wrapper compatibility | N-lock-01 cross-process lock proof (S71N compatibility_matrix.md) |
| Atomic replacement | APFS rename syscall — no partial-state window |
