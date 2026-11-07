# Scheduler Diagnostics Correction — Session 35

**Date:** 2026-11-08  
**Version:** session35_v1  
**Scope:** Corrects two factual errors introduced in Session 32 that propagated into Session 33.  
**Changes:** `src/research/scheduler_diagnostics.py` SD_VERSION v1→v2; `tests/test_scheduler_diagnostics.py` SD-01..SD-70

---

## 1. Executive Summary

**Result: `DIAGNOSTICS_CORRECTED`**

Session 32 introduced two incorrect causal inferences that invalidated the root cause classification. Session 33 preserved both errors (the grep error persisted; forks=0 was still cited). Session 35 corrects both errors systematically in code, tests, and documentation.

**Before (v1):** `forks=0 → NEVER_FORKED → BTM_AUTHORIZATION_MISSING` (HIGH confidence)  
**After (v2):** `ROOT_CAUSE_INCONCLUSIVE` with BTM as secondary INDIRECT hypothesis

The classification change applies when BTM entry is `NOT_REGISTERED` or `PRESENT_NOT_NOTIFIED`. The `BLOCKED` case still correctly produces `BTM_AUTHORIZATION_MISSING` (DIRECT confidence) because that is real direct evidence.

---

## 2. Baseline

| Item | Value |
|---|---|
| Git HEAD | ad6fbb8 |
| Audit timestamp | 2026-11-07 16:16:48 CST |
| Cron script hash | `46209171…` UNCHANGED |
| BT_HASH | `be43e8ca977d9fdd` UNCHANGED |
| CP_HASH | `1feb7a6b294a063d` UNCHANGED |
| ForwardSignals | 2605, max=2026-10-28 UNCHANGED |
| Hybrid decisions | 21, max=2026-11-04 UNCHANGED |
| Cron daemon | PID 20488, forks=0, state=running |
| Session 33 regression | 2017 passed, 1 skipped |

---

## 3. Original Incorrect Inferences

### Error 1: `forks=0 → "daemon has never executed a cron job since start"`

**Location (v1):** `audit_daemon()` lines 296–299

```python
# INCORRECT (v1):
if launchd_forks == 0:
    issues.append("launchd forks=0: daemon has never executed a cron job since start")
```

**Why it is wrong:** macOS uses `posix_spawn()` for all launchd service launches. The `forks` counter in `launchctl print` tracks `fork()` syscalls only — which launchd never issues. ALL launchd services show `forks=0`:

```
com.apple.logd:    forks=0, runs=1, execs=1
com.apple.notifyd: forks=0, runs=1, execs=1
com.vix.cron:      forks=0, runs=1, execs=1
```

`forks=0` is the baseline for every service. It carries zero diagnostic signal for cron job execution.

**v2 correction in `audit_daemon()`:**
```python
# CORRECT (v2):
issues.append(
    f"launchd forks_counter={launchd_forks} "
    "(metadata only — forks=0 is normal for all macOS launchd services using posix_spawn)"
)
# status = DaemonStatus.RUNNING (not RUNNING_IDLE, regardless of forks)
```

---

### Error 2: `forks=0 + BTM_NOT_REGISTERED → BTM_AUTHORIZATION_MISSING (HIGH confidence)`

**Location (v1):** `classify_failure()` lines 508–558

```python
# INCORRECT (v1):
if daemon.status in (RUNNING, RUNNING_IDLE) and daemon.launchd_forks == 0:
    if btm.status == BTMStatus.NOT_REGISTERED:
        primary = FailureClass.BTM_AUTHORIZATION_MISSING
        confidence = "HIGH"
        # ...
```

**Why it is wrong:**
1. `launchd_forks=0` is not evidence of anything (see Error 1 above)
2. `BTM_NOT_REGISTERED` was itself wrong in Sessions 32/33 — the grep error meant the entry was never found even though it existed
3. Even with a genuinely absent BTM entry, the causal link `absent entry → job silently skipped` is undocumented in Apple's public specification

**v2 correction in `classify_failure()`:**
```python
# CORRECT (v2):
# forks count is NOT checked anywhere in this function
if btm.status == BTMStatus.NOT_REGISTERED:
    return FailureClassification(
        primary=FailureClass.ROOT_CAUSE_INCONCLUSIVE,
        secondary=FailureClass.BTM_AUTHORIZATION_MISSING,
        confidence="INDIRECT",
        confidence_level=EvidenceConfidence.INDIRECT,
        ...
    )
```

---

### Session 32 grep error (documented in Sessions 33/34, corrected in audit_btm)

The bash diagnostic command `sfltool dumpbtm | grep -i "cron|hybrid"` without `-E` searched for a literal pipe character, not an OR pattern. The BTM entry was always present — it just wasn't found.

`audit_btm()` in v1 already used Python string parsing, so the grep error was not in the module code. However, the module's `issues` message for `NOT_REGISTERED` included false causal claims:

```python
# INCORRECT (v1) — overstated causality:
"cronBTMCheck will fail and jobs will be silently skipped."

# CORRECT (v2):
"cronBTMCheck behavior with missing entry is undocumented — "
"controlled test required to confirm causality."
```

---

## 4. New: `PRESENT_NOT_NOTIFIED` BTM Status

Session 34 confirmed that the BTM entry has disposition `[enabled, allowed, not notified] (0x3)`. v1 had no status for this case — it would fall through to `AUTHORIZED` (incorrect).

**v2 adds `BTMStatus.PRESENT_NOT_NOTIFIED`:**

```python
class BTMStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"               # 0xb: enabled+allowed+notified
    PRESENT_NOT_NOTIFIED = "PRESENT_NOT_NOTIFIED"  # 0x3: enabled+allowed, NOT notified
    NOT_REGISTERED = "NOT_REGISTERED"       # entry absent
    BLOCKED = "BLOCKED"                     # entry present but blocked
    UNAVAILABLE = "UNAVAILABLE"
```

**`_parse_btm_disposition()` helper added** to correctly parse `"not notified"` before `"notified"`:
```python
# "not notified" must be checked BEFORE "notified" to avoid false positive
if "not notified" in d:
    notified = False
else:
    notified = "notified" in d
```

**Classification for `PRESENT_NOT_NOTIFIED`:**
- `ROOT_CAUSE_INCONCLUSIVE` (INDIRECT)
- Evidence includes "0x8 bit (notified) is clear" and "causality unverified"

---

## 5. New: `SchedulerTriggerStatus` and `EvidenceConfidence`

```python
class SchedulerTriggerStatus(str, Enum):
    CONFIRMED = "SCHEDULER_TRIGGER_CONFIRMED"
    UNVERIFIED = "SCHEDULER_TRIGGER_UNVERIFIED"
    NOT_OBSERVED = "SCHEDULED_EXECUTION_NOT_OBSERVED"
    FAILURE_CONFIRMED = "SCHEDULER_TRIGGER_FAILURE_CONFIRMED"

class EvidenceConfidence(str, Enum):
    DIRECT = "DIRECT"
    CORROBORATED = "CORROBORATED"
    INDIRECT = "INDIRECT"
    INSUFFICIENT = "INSUFFICIENT"
```

**Rule enforcement:**
- `trigger_source="cron_scheduled"` from application self-report → `UNVERIFIED`
- Absent log file → `NOT_OBSERVED` (never `FAILURE_CONFIRMED` from absence alone)
- `CONFIRMED`/`FAILURE_CONFIRMED` require independent direct evidence

---

## 6. New: `CronExecutionEvidenceReport`

```python
@dataclass
class CronExecutionEvidenceReport:
    scheduled_at: Optional[str]
    observed_process_start: bool
    observed_process_exit: Optional[int]
    scheduler_log: Optional[str]
    application_log: Optional[str]
    stdout_stderr: Optional[str]
    trigger_source: Optional[str]
    source_reliability: EvidenceConfidence
    evidence_confidence: EvidenceConfidence
    execution_verdict: SchedulerTriggerStatus
```

`audit_execution_evidence(project_root)` checks for `hybrid_cron.log` and `data/.cron_state.json`.

---

## 7. Backward Compatibility

| Item | Treatment |
|---|---|
| `DaemonStatus.RUNNING_IDLE` | Kept in enum; documented that it must NOT be set by `audit_daemon()` based on forks=0 |
| `FailureClass.BTM_AUTHORIZATION_MISSING` | Kept; now only used with DIRECT evidence (BLOCKED disposition) |
| `FailureClassification.confidence: str` | Kept as string field; `confidence_level: EvidenceConfidence` added as new field |
| `DaemonAudit.launchd_forks` | Kept as metadata field; `scheduler_trigger_status` added with default |
| `BTMAudit.issues` | Kept; message text corrected to avoid overstated causality |
| All SD-01..SD-43 | Mostly preserved; SD-10/SD-14 test helpers (not audit function) so backward compat maintained |

No existing consumers of `SchedulerDiagnosticsReport` are broken by the new optional fields.

---

## 8. Test Results

| Suite | Before | After |
|---|---|---|
| SD-01..SD-45 (original, some updated) | 45 PASS | 45 PASS |
| SD-46..SD-70 (new) | — | 25 PASS |
| **SD total** | **45** | **70 PASS** |
| CP-01..CP-30 (cron probe) | 30 PASS | 30 PASS |
| PF-11 (fixed clock) | 1 PASS | 1 PASS |
| **Full regression** | 2017 PASS, 1 skip | **2042 PASS, 1 skip** |
| Ruff | PASS | **PASS** |

---

## 9. Updated Tests (SD35, SD41, SD43, SD45)

| Test | v1 assertion | v2 assertion | Reason |
|---|---|---|---|
| SD35 | `primary == BTM_AUTHORIZATION_MISSING` | `primary == ROOT_CAUSE_INCONCLUSIVE` | forks=0 no longer drives BTM classification |
| SD41 | `"System Settings" in fix` | `"probe" in fix` | Probe test is now the first step |
| SD43 | `primary == SCHEDULER_NOT_TRIGGERING` | `primary == ROOT_CAUSE_INCONCLUSIVE` | BTM unavailable + forks=0 no longer → SCHEDULER_NOT_TRIGGERING |
| SD45 | `SD_VERSION == "v1"` | `SD_VERSION == "v2"` | Version bumped after semantic correction |

---

## 10. Stage B Approval Plan

See `docs/isolated_cron_stage_b_approval_request.md` for the complete controlled test plan.

**Current status:** `SCHEDULER_TEST_READY_FOR_APPROVAL`

---

## 11. Safety Verification

| Item | Status |
|---|---|
| Production crontab | UNCHANGED |
| hybrid_shadow_cron.py hash | UNCHANGED (`46209171…`) |
| ForwardSignals | UNCHANGED (2605, fp=885afab1c55e9943) |
| Hybrid decisions | UNCHANGED (21, fp=1f61bb126934bb9f) |
| BT_HASH | UNCHANGED (`be43e8ca977d9fdd`) |
| CP_HASH | UNCHANGED (`1feb7a6b294a063d`) |
| Neon | NOT TOUCHED |
| launchd | NOT MODIFIED |
| BTM database | NOT MODIFIED |
| Cron daemon | NOT RESTARTED |

---

## 12. Final Verdict

| Dimension | Verdict |
|---|---|
| **Diagnostic Correction** | `DIAGNOSTICS_CORRECTED` |
| **BTM** | `BTM_ALLOWED_CAUSALITY_UNVERIFIED` |
| **Scheduler Evidence** | `SCHEDULED_EXECUTION_NOT_OBSERVED` |
| **Stage B** | `SCHEDULER_TEST_READY_FOR_APPROVAL` |
| **Regression** | `REGRESSION_PASS` (2042 passed, 1 skipped) |
| **V3 Activation** | `ACTIVATION_BLOCKED` |
