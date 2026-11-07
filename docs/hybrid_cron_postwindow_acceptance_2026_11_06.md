# Hybrid Cron Post-Window Acceptance Audit — 2026-11-06

**Audit Date:** 2026-11-06  
**Audit Timestamp:** 2026-11-06 23:03 Taiwan (CST, UTC+8)  
**Scheduled Window:** 2026-11-06 16:00–17:30 Taiwan  
**Audit Type:** Post-window evidence-only acceptance (read-only, no production writes)  
**Previous Status:** `AWAITING_FIRST_SCHEDULED_RUN` (from `hybrid_first_scheduled_run_acceptance.md`)  

---

## Executive Summary

**Verdict: `CRON_EXECUTION_FAILURE`**

The 2026-11-06 scheduled cron window (16:00 Taiwan) has passed. Post-window audit confirms:

- The cron daemon was running (started 2026-11-05 18:08 Taiwan)
- The system was continuously awake (244-day uptime since 2026-03-07)
- The crontab was correctly configured (`0 16 * * 1-5`)
- Full Disk Access for `/usr/sbin/cron` was reportedly granted (Session 11)
- The Python script has no syntax errors
- The log directory is writable

**Despite all prerequisites being met, `logs/hybrid_cron.log` was never created.** No DB state changes, no mail spool output, and no production writes occurred. The cron command was not executed by the macOS scheduler.

This is distinct from `DATA_NOT_READY`: the data gate would have been checked if the job had run. We cannot determine what the gate result would have been because the job never started.

---

## P0 — Audit Baseline

| Item | Value |
|---|---|
| Audit time (Taiwan) | 2026-11-06 23:03 CST |
| Audit time (UTC) | 2026-11-06 15:03 UTC |
| Hours after window close | +6h 33m after 16:30 Taiwan window close |
| System uptime | 244 days (boot: 2026-03-07 12:11:27) |
| System timezone | CST (UTC+8) — correct for Taiwan |
| BT_HASH | `be43e8ca977d9fdd` |
| CP_HASH | `1feb7a6b294a063d` |
| AR_VERSION | `v3_activation_readiness_v1` |
| Regression | 1942 passed, 1 skipped, 0 failures |

---

## P1 — Cron Trigger Verification

**Verdict: `NO_TRIGGER_EVIDENCE`**

### Evidence Matrix

| Evidence Source | Expected if Ran | Actual | Interpretation |
|---|---|---|---|
| `logs/hybrid_cron.log` | File exists (created by `>>` redirect) | **ABSENT** | Cron command was never executed |
| `data/.cron_state.json` | Updated for 2026-11-06 | Still 2026-11-05T10:28Z | Python script did not run |
| `hybrid_forward_run_log` latest | id > 9, trade_date = 2026-11-06 | id=9, 2026-11-05T09:20Z | No Nov 6 run log entry |
| `hybrid_forward_decision` count | ≥21 entries | 21 (unchanged, MAX=2026-11-04) | No new decisions |
| `/var/mail/alicetu` | Mail if redirect failed | **ABSENT** | No fallback mail either |
| `daily_prices` for 2026-11-06 | Populated after pipeline | 0 rows | DailyPrice pipeline also silent |

### Trigger Source Limitation

Even if the job had run, `trigger_source` in `cron_state.json` is set by `sys.stdout.isatty()`. A cron-redirected run (`>> logfile 2>&1`) has no TTY → `"cron_scheduled"`. A manual run from terminal → `"manual"`. Without `hybrid_cron.log` existing, this distinction is moot.

---

## P2 — Cron Execution Timeline

```
2026-11-05 18:08 Taiwan  Crontab installed (crontab -e, /var/at/tabs mtime)
2026-11-05 18:00 Taiwan  /usr/sbin/cron daemon started (ps: Ss Thu06PM)
2026-11-05 18:28 Taiwan  Manual run: BLOCKED_PARTIAL_MARKET (cron_state saved)
2026-11-05 10:28 UTC     Last cron_state.json write (= 18:28 Taiwan) — FROZEN HERE

2026-11-06 00:56 Taiwan  run_2026-11-06.log created 0 bytes (main.py logging init, unrelated)
2026-11-06 01:11 Taiwan  scripts/hybrid_shadow_cron.py mtime updated

2026-11-06 16:00 Taiwan  SCHEDULED: hybrid cron should fire
                           ← NO EVIDENCE OF EXECUTION
                           ← logs/hybrid_cron.log NOT CREATED
                           ← cron_state.json NOT UPDATED
                           ← hybrid_forward_run_log NOT UPDATED
                           ← /var/mail/alicetu NOT CREATED

2026-11-06 23:03 Taiwan  AUDIT: post-window evidence collection
                          /usr/sbin/cron still running (confirmed)
```

---

## P3 — Root Cause Analysis

**Root Cause: `CRON_SYSTEM_SILENT_FAILURE`**

All technical prerequisites were confirmed met:

| Prerequisite | Status | Evidence |
|---|---|---|
| Python interpreter | PASS | `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` exists (symlink to 3.13) |
| Script exists | PASS | `scripts/hybrid_shadow_cron.py` exists (mtime Nov 6 01:11) |
| Script syntax | PASS | `python3 -m py_compile` → no errors |
| Log dir writable | PASS | `touch logs/hybrid_cron.log` → LOG_PATH_WRITABLE |
| Cron daemon running | PASS | PID 20488, started Thu 2026-11-05 18:00 |
| System awake | PASS | 244-day uptime, confirmed running |
| Crontab correct | PASS | `0 16 * * 1-5 ... >> logs/hybrid_cron.log 2>&1` |
| FDA granted | REPORTED_PASS | From `hybrid_first_scheduled_run_acceptance.md`: "FDA granted to /usr/sbin/cron; env -i PASS" |

Despite all prerequisites, the shell command was never executed by the cron daemon.

**Most Likely Cause:** macOS Sequoia (Darwin 25.3.0 = macOS 15.x) silently blocks traditional BSD `/usr/sbin/cron` from invoking subprocesses in some configurations. This is a documented macOS 10.15+ behavior:

- FDA granted in System Settings may not persist when cron daemon starts fresh (restarts do not automatically re-inherit grants in some macOS versions)
- The cron daemon started at 18:08 on Nov 5 — a fresh start triggered by `crontab -e`. Even if FDA was granted earlier, the new daemon process may not have FDA in its security token
- The `>> logs/hybrid_cron.log 2>&1` redirect would create the log file even with a Python error; its absence means the shell was never invoked at all — consistent with a process-spawn-level block

**Secondary Possibility:** macOS launchd may have throttled or killed the cron daemon between 16:00 and 17:30 Taiwan. No evidence of this, but `/usr/sbin/cron` shows 0:16 CPU time since Nov 5, suggesting minimal activity.

---

## P4 — Post-close Market Data Gate

**Verdict: `POST_CLOSE_DATA_UNAVAILABLE`**

Since cron did not execute, the DailyPrice pipeline was never triggered. The market data gate cannot be formally evaluated.

| Check | Expected | Actual | Note |
|---|---|---|---|
| 0050 for 2026-11-06 | ≥1 row | **0 rows** | DailyPrice pipeline never ran |
| Non-0050 for 2026-11-06 | ≥5,000 rows | **0 rows** | DailyPrice pipeline never ran |
| All stocks for 2026-11-06 | ≥5,001 rows | **0 rows** | Confirmed: `SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-06'` |

**TWSE last available:** 2026-11-04 (6,956 non-0050 stocks)  
**0050 last available:** 2026-11-05 (slot from manual backfill)  

Had cron run, the freshness gate would have evaluated 2026-11-06 — but we cannot determine what result it would have produced because DailyPrice ingestion is a prerequisite that also did not run.

---

## P5 — Prospective Capture Audit

**Verdict: `NO_PROSPECTIVE_CAPTURE`**

| Metric | Value |
|---|---|
| `hybrid_forward_decision` total | 21 (UNCHANGED from 2026-11-05) |
| `hybrid_forward_decision` latest | trade_date=2026-11-04 |
| Decisions for 2026-11-06 | 0 |
| `v3_prospective_decision` table | ABSENT (pre-activation, expected) |
| `hybrid_forward_run_log` latest | id=9, trade_date=2026-11-05, BLOCKED_MISSING_SIGNALS (from 17:20 Taiwan Nov 5) |

**Classification impact:**  
Any 2026-11-06 decisions captured on 2026-11-07 or later would be classified `LATE_CAPTURE`, not `PROSPECTIVE`. This reduces their OOS validity weight from full to acceptable.

---

## P6 — Append-only Integrity Verification

**Verdict: `APPEND_ONLY_PASS`**

| Table | Before Window | After Window | Delta |
|---|---|---|---|
| `forward_signals` | 2605 total, MAX=2026-10-28 | 2605 total, MAX=2026-10-28 | **0 change** |
| `hybrid_forward_decision` | 21 total, MAX=2026-11-04 | 21 total, MAX=2026-11-04 | **0 change** |
| `hybrid_forward_run_log` | id=9 latest | id=9 latest | **0 change** |

No unauthorized writes were detected. All safety boundaries preserved.

---

## P7 — V3 Parameter Freeze Verification

**Verdict: `FREEZE_PASS`**

| Component | Hash | Status |
|---|---|---|
| Backtest Engine (`PARAMETER_HASH`) | `be43e8ca977d9fdd` | UNCHANGED |
| Comparison Engine (`PARAMETER_HASH`) | `1feb7a6b294a063d` | UNCHANGED |
| `MODEL_VERSION` | v8.0 | NOT MODIFIED |
| ForwardSignals last entry | 2026-10-28 | FROZEN |
| `v3_activation_readiness.py` | AR_VERSION=v3_activation_readiness_v1 | UNCHANGED |

---

## P8 — Regression & Safety

**Verdict: `REGRESSION_PASS`**

| Suite | Result |
|---|---|
| FM11 (post-backfill real DB) | PASS |
| AR-01..AR-40 (activation readiness) | 40/40 PASS |
| Full suite | **1942 passed, 1 skipped, 0 failures** |
| Ruff (v3_activation_readiness.py + tests) | All checks passed |

---

## P9 — Six Activation Blockers: Updated Status

| # | Blocker | Session 30 Status | Session 31 Status | Change |
|---|---|---|---|---|
| R3 | 0050 Gate (2026-11-06) | PENDING | **FAIL** | Market data = 0 rows |
| R4 | TWSE proxy gate (2026-11-06) | PENDING | **FAIL** | Market data = 0 rows |
| R5 | TPEx proxy gate (2026-11-06) | PENDING | **FAIL** | Market data = 0 rows |
| R8 | Append-only (live captures) | PENDING | **FAIL_NO_EVIDENCE** | Cron didn't run; 0 captures |
| R13 | Cron Acceptance | PENDING_SCHEDULED_WINDOW | **CRON_EXECUTION_FAILURE** | Log absent; daemon confirmed running but job didn't fire |
| R16 | Explicit Activation Approval | PENDING | **PENDING** | No change — human authorization required |

**All 6 blockers remain. Net change: R13 upgraded from PENDING to FAIL.**

---

## P10 — Final Questions

**Q01: Was the audit conducted post-window (after 16:30 Taiwan)?**  
Yes. Audit timestamp: 23:03 Taiwan, +6h33m after window close.

**Q02: Was the system continuously running during the scheduled window?**  
Yes. 244-day uptime confirmed; boot 2026-03-07 12:11:27.

**Q03: Was the cron daemon running at 16:00 Taiwan?**  
Yes. `ps aux` shows `PID 20488 /usr/sbin/cron` started Thu 18:00 PM (Nov 5). Daemon running continuously from Nov 5 18:00 to audit time.

**Q04: Was the crontab correctly configured?**  
Yes. `crontab -l` shows `0 16 * * 1-5 ... >> logs/hybrid_cron.log 2>&1`. Entry is correct.

**Q05: Was `logs/hybrid_cron.log` created?**  
No. File is ABSENT. This is the primary evidence of cron execution failure.

**Q06: Was `data/.cron_state.json` updated?**  
No. Still shows `2026-11-05T10:28Z`, `BLOCKED_PARTIAL_MARKET`. Python script did not execute.

**Q07: Was there any cron output in the mail spool?**  
No. `/var/mail/alicetu` does not exist. No fallback output captured anywhere.

**Q08: Is the macOS FDA restriction the confirmed root cause?**  
No, it cannot be confirmed. FDA was reportedly granted (Session 11 doc). But TCC.db is inaccessible from user context. Root cause is `CRON_SYSTEM_SILENT_FAILURE` — exact mechanism unverified.

**Q09: Was market data for 2026-11-06 available at the audit time?**  
No. `SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-06'` = 0. DailyPrice pipeline also did not run.

**Q10: Would the data gate have passed if cron had run?**  
Unknown. Market data for 2026-11-06 was never ingested — both the DailyPrice pipeline and the shadow cron failed to execute. Cannot retroactively evaluate gate status.

**Q11: Were any prospective decisions captured for 2026-11-06?**  
No. `hybrid_forward_decision` count = 21, unchanged, latest = 2026-11-04. No decisions for Nov 6 exist.

**Q12: Can a late capture for 2026-11-06 still be performed?**  
Technically yes, by running `hybrid_shadow_cron.py --execute` after DailyPrice for Nov 6 is ingested. Classification would be `LATE_CAPTURE` (not `PROSPECTIVE`). This requires explicit authorization. Not performed in this audit.

**Q13: Is the ForwardSignals data integrity intact?**  
Yes. 2605 total, MAX=2026-10-28, unchanged from pre-window state.

**Q14: Is the Hybrid shadow decision data integrity intact?**  
Yes. 21 total, MAX=2026-11-04, unchanged.

**Q15: Are the V3 parameter hashes frozen?**  
Yes. BT_HASH=`be43e8ca977d9fdd`, CP_HASH=`1feb7a6b294a063d`. Unchanged from Sessions 26–27.

**Q16: Is the full regression passing?**  
Yes. 1942 passed, 1 skipped, 0 failures.

**Q17: What is the recommended remediation for R13?**  
Two options:  
(a) **Short-term**: Re-verify FDA for `/usr/sbin/cron` in System Settings → Privacy & Security → Full Disk Access. Run a minute-level test (`* * * * *`) to confirm cron fires. See `macos_cron_permission_validation.md`.  
(b) **Long-term**: Migrate from crontab to `launchd` `.plist` (see `hybrid_cron_installation_audit.md` for launchd path). launchd has better macOS 15.x integration and FDA handling.

**Q18: Does the cron failure invalidate the V3 prospective shadow design?**  
No. The design is correct. The scheduler layer is a macOS infrastructure concern orthogonal to the V3 logic. Once the scheduler is fixed, the fail-closed gate, classification logic, and prospective capture design remain valid.

**Q19: Is V3 Shadow activation approved in this session?**  
No. R13 is FAIL (not just PENDING). R16 remains PENDING. Full gate: 6/6 blockers remain.

**Q20: What is the final verdict for this acceptance audit?**  
`CRON_EXECUTION_FAILURE`. The first scheduled run did not occur. This is a macOS infrastructure failure, not a research design failure. Resolution requires explicit scheduler remediation (see Q17) before the next scheduled window.

---

## Recommended Actions (require explicit authorization)

| Priority | Action | Owner | Safety Class |
|---|---|---|---|
| P0 | Re-verify FDA for `/usr/sbin/cron` in System Settings | Manual — requires System Settings access | SAFE |
| P0 | Run `* * * * *` test cron to confirm shell invocation | Manual — temporary test entry | SAFE (read-only test) |
| P1 | If FDA confirmed: run `hybrid_shadow_cron.py --execute` for 2026-11-06 (LATE_CAPTURE) | Requires explicit authorization | Authorized production write |
| P1 | Run DailyPrice backfill for 2026-11-06 | Requires explicit authorization | Authorized data write |
| P2 | Evaluate launchd migration | Manual design decision | Architecture change |

**None of the above actions were performed in this audit session.** This is a read-only evidence-collection audit.

---

## Appendix: Diagnostic Commands

```bash
# Verify cron daemon is running
ps aux | grep cron

# Verify crontab
crontab -l

# Test script syntax
python3 -m py_compile scripts/hybrid_shadow_cron.py

# Test log path writability
touch logs/hybrid_cron.log && echo OK && rm logs/hybrid_cron.log

# Test cron-like environment (non-TTY)
env -i HOME=$HOME PATH=/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/bin:/bin \
  python3 scripts/hybrid_shadow_cron.py --status

# Check market data for 2026-11-06
sqlite3 data/platform.db "SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-06';"

# Check hybrid_forward_decision count
sqlite3 data/platform.db "SELECT COUNT(*), MAX(trade_date) FROM hybrid_forward_decision;"

# Check cron state
cat data/.cron_state.json | python3 -m json.tool
```
