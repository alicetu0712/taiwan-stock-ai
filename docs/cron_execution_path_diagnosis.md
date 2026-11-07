# Cron Execution Path Diagnosis — Session 34

**Date:** 2026-11-07  
**Scope:** 2026-11-06 Hybrid Shadow cron failure — Stage-by-stage failure analysis  
**Version:** session34_v1

---

## 1. Executive Summary

**First Failed Stage: Stage 1 (Scheduler Trigger)**

The cron daemon was running. The system was awake. The crontab was valid. Despite all prerequisites being satisfied, **the scheduler did not fork any child process** at 16:00 CST on Nov 6. Stages 2–8 were never reached.

**Root Cause:** `ROOT_CAUSE_INCONCLUSIVE` — Stage 1 failure confirmed; mechanism undetermined.

---

## 2. Execution Path Model

```
Stage 1: Scheduler Trigger
  └─ cron daemon wakes at 16:00
  └─ reads /private/var/at/tabs/alicetu
  └─ calls cronBTMCheck()
  └─ if check passes: fork() or posix_spawn()

Stage 2: Shell Launch
  └─ /bin/sh -c "python3 script.py >> log 2>&1"
  └─ stderr/stdout redirect to hybrid_cron.log

Stage 3: Python Interpreter Start
  └─ /Library/Frameworks/.../python3
  └─ sys.path setup, import resolution

Stage 4: Script Import
  └─ from scripts.hybrid_shadow_cron import ...
  └─ src.research.* imports

Stage 5: Preflight Gate
  └─ run_hybrid_shadow_preflight()
  └─ DailyPrice freshness, fullness, schema checks

Stage 6: Business Logic
  └─ signal computation, decision capture
  └─ SQLite writes

Stage 7: Log Write
  └─ hybrid_cron.log line written (cron state)
  └─ cron_state.json updated

Stage 8: Completion
  └─ exit_code 0 or non-zero
  └─ cron mail on failure (if /var/mail exists)
```

---

## 3. Stage-by-stage Evidence

### Stage 1: Scheduler Trigger — `TRIGGER_FAILURE_CONFIRMED`

**Evidence of failure:**

| Evidence Item | Observation |
|---|---|
| `hybrid_cron.log` | DOES NOT EXIST |
| cron process log at 16:00 CST Nov 6 | Zero entries (3 entries total in 72h, all CoreAnalytics) |
| sh process log at 15:50–16:10 CST Nov 6 | Zero entries |
| python3 process log at 15:50–16:10 CST Nov 6 | Zero entries |
| launchd log at 15:59–16:01 CST Nov 6 | Zero entries |

No child process (sh, python3, or any cron-spawned process) was observed at or near 16:00 CST on Nov 6.

**Evidence of normal preconditions:**
- Cron daemon: running PID 20488
- System: 180+ launchd entries in the 15:50-16:09 window (awake)
- Crontab: valid, correct DOW, correct paths
- Python: exists, executable
- Script: exists, readable, modified 01:11 CST (before 16:00)

**Classification:** The scheduler itself did not issue a fork/spawn for the 16:00 job. This is an internal scheduler decision, not a downstream failure.

---

### Stage 2: Shell Launch — `NOT_REACHED`

No `/bin/sh` process was spawned. The shell redirect `>> …/hybrid_cron.log 2>&1` was never processed. The absence of `hybrid_cron.log` is consistent with the shell never being invoked, not with the shell failing to write.

---

### Stages 3–8: `NOT_REACHED`

All subsequent stages depend on Stage 1 producing a child process. Because no process was spawned, none of these stages were reached.

---

## 4. Why Stage 1 Failed — Hypothesis Analysis

### 4a. BTM Check Failure (Highest Probability)

```
/usr/sbin/cron links:
  BackgroundTaskManagement.framework v104.0.0

Binary contains:
  cronBTMToggle
  cronBTMCheck
  "Error contacting BTM to check enablement state: %d"
```

cron calls `cronBTMCheck` before each job fork. If the check fails or returns "not authorized," cron silently skips the job — no log, no mail, no error.

**BTM entry state (Session 34):**
```
Disposition: [enabled, allowed, not notified] (0x3)
Generation: 0
Type: user item (0x1)
```

The entry is `allowed=1` but `not notified=1` (0x8 bit clear). Whether `cronBTMCheck` requires the `0x8` bit is unconfirmed.

**Strength: HIGH circumstantial; UNVERIFIED direct.**

### 4b. macOS 26.3 Cron Job Dispatch Regression

macOS 26.3 (Darwin 25.3.0) has not been widely documented for cron job dispatch behavior. The cron daemon starts correctly via launchd/xpcproxy, receives CoreAnalytics events, but zero job executions are logged in 72h (since Nov 5 18:08).

**Strength: Plausible; no supporting evidence beyond absence.**

### 4c. TCC / Full Disk Access Restriction

```
$ log show --last 72h --predicate 'subsystem == "com.apple.TCC"' | grep -i cron
(no output)
```

No TCC denial was logged for cron in the 72h window.

**Note:** TCC denial logs are only generated when a process attempts a protected resource access. If cron never reaches Stage 2, it never accesses any protected resource. The absence of TCC denial log is consistent with both:
- BTM blocking at Stage 1 (before TCC is relevant)
- FDA restriction preventing script execution (would be TCC, but only if script reached Stage 2)

**Strength: Not ruled out; evidence is consistent with Stage 1 blocking preventing TCC involvement.**

### 4d. xpcproxy / Trampoline Restriction

```
launchctl print system/com.vix.cron:
  trampolined = 1
```

Cron was started via `xpcproxy` ("Successfully spawned cron[20488] because xpc event"). `trampolined = 1` is normal for XPC-bootstrapped services and does not prevent job forking by the daemon itself.

**Strength: LOW — no evidence of trampoline restriction on job forking.**

---

## 5. Failure Tree

```
2026-11-06 16:00 CST — cron schedule fires
│
├─ Stage 1: cronBTMCheck()
│    ├─ [H1] BTM: not notified → check fails → SILENT SKIP ◄ most probable
│    ├─ [H2] macOS 26.3 dispatch bug → job not queued
│    └─ [H3] other internal failure
│
└─ All paths lead to: no child process spawned
       ↓
   hybrid_cron.log: ABSENT
   sh process: ABSENT at 16:00
   python3 process: ABSENT at 16:00
   DailyPrice Nov 6: 0 rows
   V3 shadow capture: NONE
```

---

## 6. What Evidence Was Missing

To confirm Stage 1's exact failure mechanism, we would need any of:

1. A BTM denial entry in the unified log (not found in 72h)
2. A `cron[20488]` error message in the unified log at 16:00 (not present)
3. A controlled before/after test: install test crontab, observe whether probe output file appears (see `docs/isolated_cron_test_approval_plan.md`)
4. macOS kernel extension or Endpoint Security audit log showing cron's fork() being blocked

None of these are available from read-only audit. The first item that can be directly tested is #3.

---

## 7. Downstream Cascade

The Stage 1 failure caused a complete cascade:

| Item | Expected | Actual | Cause |
|---|---|---|---|
| `hybrid_cron.log` | Created | **ABSENT** | Stage 1 failure |
| `cron_state.json` | Updated with Nov 6 state | Frozen at Nov 5 10:28 UTC | Stage 1 failure |
| DailyPrice Nov 6 | 6,957+ rows | **0 rows** | hybrid_shadow_cron.py never ran backfill |
| DailyPrice Nov 7 | N/A (Saturday) | 0 rows | Market closed |
| Hybrid decisions Nov 6 | PROSPECTIVE captures | **0 new rows** | Stage 1 failure |
| R3/R4/R5 (activation gates) | PASS | **FAIL** | No Nov 6 market data |
| R8 (shadow capture) | PASS | **FAIL_NO_EVIDENCE** | No Nov 6 cron execution |
| R13 (cron execution) | PASS | **CRON_EXECUTION_FAILURE** | Stage 1 failure |

---

## 8. Recovery Path

### Phase 1: Verify / Fix Stage 1

**Option A — BTM notification approval (if BTM is the cause):**
- System Settings → General → Login Items & Extensions
- Locate cron entry in "Allow in Background"
- Toggle to Allow
- Verify: `sfltool dumpbtm | grep -i -A 10 cron` should show `0xb` (notified bit set)

**Option B — Controlled probe test (concurrent with Option A):**
- Authorize `docs/isolated_cron_test_approval_plan.md` Stage B
- Install `* * * * * …cron_probe.py --execute` temporarily
- Observe whether output file appears within 60s
- This determines whether Stage 1 is now working

**Option C — Migration to launchd LaunchAgent (if Options A+B fail):**
- LaunchAgent plist bypasses `cronBTMCheck` entirely
- Design is documented in `docs/hybrid_scheduler_recovery_plan.md`
- Moderate implementation risk (new trigger path, needs validation)

### Phase 2: DailyPrice Backfill

After Stage 1 is confirmed working:
```bash
python3 scripts/backfill_daily_prices.py --start 2026-11-06 --execute
```
Requires explicit authorization.

### Phase 3: Scheduled Acceptance

Wait for next trading day 16:00 → verify `hybrid_cron.log` is created → V3 activation gates R3/R4/R5/R8 may clear.

---

## 9. Final Classification

| Dimension | Verdict |
|---|---|
| **First failed stage** | Stage 1: Scheduler Trigger |
| **Failure type** | SILENT_SKIP (no error log, no process spawn) |
| **Root cause** | `ROOT_CAUSE_INCONCLUSIVE` |
| **BTM** | `BTM_ALLOWED_CAUSALITY_UNVERIFIED` (entry present, `not notified` causality unproven) |
| **Next action** | `ISOLATED_PROBE_APPROVAL_REQUIRED` |
| **V3 Activation** | `ACTIVATION_BLOCKED` |
| **Regression (Session 33)** | 2017 passed, 1 skipped — no code changes in Session 34 |
