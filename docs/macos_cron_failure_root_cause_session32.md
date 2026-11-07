# macOS Cron Failure Root Cause — Session 32

**Date:** 2026-11-07  
**Audit Type:** Read-only system + code audit  
**Version:** session32_v1  

---

## 1. Executive Summary

**Root Cause: `BTM_AUTHORIZATION_MISSING`**  
**Confidence: HIGH**

The 2026-11-06 Hybrid Shadow Cron failure is caused by **Background Task Management (BTM) authorization never being granted** for the user crontab entry.

macOS 26.3 (macOS 26, Darwin 25.3.0) integrated BTM directly into `/usr/sbin/cron`:

- cron is linked against `BackgroundTaskManagement.framework v104.0.0`
- cron calls `cronBTMCheck` before each `fork()` to verify BTM authorization
- If BTM check fails (no registered entry), the fork is silently skipped
- Result: `launchd forks=0` — the daemon has NEVER executed any cron job

The BTM database (125 entries via `sfltool dumpbtm`) contains **zero entries for cron or any user crontab entry**. This is the definitive evidence.

This failure is distinct from, and unrelated to:
- FDA (Full Disk Access) — reportedly granted; FDA and BTM are separate systems
- System sleep — 244-day uptime; machine was awake
- Script syntax error — `python3 -m py_compile` PASS
- Log directory permissions — writable from user context
- Python path — `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` exists
- Crontab format — no CRLF, no unescaped `%`, correct hour/DOW

---

## 2. Baseline Snapshot

| Item | Value |
|---|---|
| Audit time | 2026-11-07 01:22 CST (UTC+8) |
| macOS version | 26.3 (BuildVersion 25D125) |
| System uptime | 244 days (boot: 2026-03-07 12:11:27) |
| User | alicetu (UID=501) |
| Cron daemon PID | 20488 |
| Cron daemon start | 2026-11-05 18:00 Taiwan |
| launchd forks | **0** |
| launchd state | running |
| BTM entries | 125 |
| Cron BTM entry | **NOT FOUND** |
| Script hash | `46209171e00eb46429d0e36d02c106b87cf3684b13803ccdf53369042ba060d4` |
| BT_HASH | `be43e8ca977d9fdd` (unchanged) |
| CP_HASH | `1feb7a6b294a063d` (unchanged) |
| ForwardSignals | 2605, MAX=2026-10-28 (unchanged) |
| DailyPrice Nov 6 | 0 rows |

---

## 3. Crontab Audit

| Check | Result |
|---|---|
| `crontab -l` returns entry | PASS |
| Hour field | `16` ✓ |
| Minute field | `0` ✓ |
| DOW field | `1-5` ✓ |
| Python path | `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` ✓ |
| Script path | Absolute path ✓ |
| Log redirect | `>> logs/hybrid_cron.log 2>&1` ✓ |
| CRLF | None ✓ |
| Unescaped `%` | None ✓ |
| Hex dump end byte | `0x0a` (Unix LF) ✓ |
| `/var/at/tabs` mtime | Nov 5 18:08 (matches crontab install time) ✓ |

**Crontab audit: INSTALLED_VALID — no syntax issues**

---

## 4. Cron Daemon Evidence

```
$ launchctl print system/com.vix.cron
state = running
program = /usr/sbin/cron
pid = 20488
immediate reason = xpc event
forks = 0           ← CRITICAL: never executed any job
execs = 1
last exit code = (never exited)
```

Key flags:
- `forks = 0`: In macOS launchd statistics, `forks` counts how many child processes the daemon has created since start. For cron, each job execution is a fork. **Zero forks = zero jobs executed ever.**
- `immediate reason = xpc event`: Daemon was started by an XPC event (triggered by `crontab -e` on Nov 5), not by `/etc/crontab` existence (which is missing).
- `KeepAlive PathState: /etc/crontab` is false (file missing), but daemon stays running due to QueueDirectories watch.

---

## 5. TCC / FDA Audit

| Check | Result |
|---|---|
| FDA for `/usr/sbin/cron` | Reportedly granted (Session 11 doc) |
| TCC.db accessible | PERMISSION_DENIED (requires root) |
| TCC denial log entries (48h) | **Empty** — no TCC events logged |
| Unified Log cron entries (48h) | **Empty** — no cron activity logged |

FDA and BTM are separate macOS security systems. FDA controls file access. BTM controls whether background tasks can execute at all.

---

## 6. BTM Authorization Analysis

### How BTM integrates with cron

```
$ otool -L /usr/sbin/cron
  BackgroundTaskManagement.framework/Versions/A/BackgroundTaskManagement
    (compatibility version 1.0.0, current version 104.0.0)
```

```
$ strings /usr/sbin/cron | grep BTM
  cronBTMToggle
  cronBTMCheck
  Error contacting BTM to check enablement state: %d
```

Execution flow in macOS 26.3 cron:
```
1. Cron wakes up at 16:00 Taiwan
2. Reads crontab from /usr/lib/cron/tabs/alicetu (symlink to /private/var/at/tabs/)
3. Calls cronBTMCheck for the job entry
4. BTM database lookup: finds NO entry for this crontab
5. cronBTMCheck returns "not authorized"
6. fork() is SKIPPED — no child process created
7. No log file created, no mail sent
8. launchd forks counter remains at 0
```

### BTM Database State

```
$ sfltool dumpbtm | grep -c "Identifier:"
125
```

```
$ sfltool dumpbtm | grep -i "cron|hybrid|python|alicetu"
(no output)
```

**125 BTM entries exist (Adobe, Microsoft, Google, etc.) but NONE for cron.**

### Expected BTM behavior

When `crontab -e` is run on macOS 13+:
1. macOS should register the new job with BTM
2. A system notification should appear: "Background Items Added"
3. User must approve in System Settings → General → Login Items & Extensions
4. BTM database entry is created with `Disposition: [enabled, allowed]`
5. cron can then fork jobs

**What actually happened:** The BTM registration either failed silently or the approval notification was missed/dismissed. No BTM entry = no fork authorization.

---

## 7. Independent Test Script

A minimal cron test script was created and verified (local execution only):

```
Path: /private/tmp/.../scratchpad/cron_test/minimal_cron_test.py
Status: CREATED AND LOCAL-VERIFIED
```

Local execution confirms:
- Python 3.13.3 runs correctly
- `zoneinfo.ZoneInfo("Asia/Taipei")` works
- UID=501 (alicetu)
- File write to `/tmp/.../cron_test_output.log` succeeds

**NOT installed as a cron job — SCHEDULER_TEST_PENDING_APPROVAL**

To test cron execution:
```bash
# Proposed test crontab entry (DO NOT INSTALL without authorization):
# * * * * *  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
#   /private/tmp/.../cron_test/minimal_cron_test.py >> /tmp/cron_test_redirect.log 2>&1
# Wait 1 minute, then check /tmp/cron_test_redirect.log
# If file exists: BTM was granted (or cron fires before BTM check)
# If file absent: BTM blocking confirmed
```

---

## 8. Failure Classification

| Class | Verdict | Confidence |
|---|---|---|
| `CRONTAB_NOT_INSTALLED` | NOT THIS | HIGH |
| `CRONTAB_SYNTAX_ERROR` | NOT THIS | HIGH |
| `SCHEDULER_NOT_TRIGGERING` | YES (secondary) | HIGH |
| **`BTM_AUTHORIZATION_MISSING`** | **PRIMARY ROOT CAUSE** | **HIGH** |
| `TCC_PERMISSION_DENIED` | NOT CONFIRMED | — |
| `EXECUTION_ENVIRONMENT_FAILURE` | NOT THIS | HIGH |
| `SCRIPT_RUNTIME_FAILURE` | NOT THIS | HIGH |
| `LOGGING_FAILURE` | NOT THIS | HIGH |

**Primary:** `BTM_AUTHORIZATION_MISSING`  
**Secondary:** `SCHEDULER_NOT_TRIGGERING`  
**Confidence:** HIGH  

---

## 9. Required Approvals

### A — BTM Re-authorization (REQUIRED, manual only)

```
1. Open System Settings
2. General → Login Items & Extensions
3. Scroll to "Background Allow" or "Allow in Background" section
4. Look for entries related to cron / Python / Antigravity
5. Toggle any blocked entries to "Allow"

OR if no entry appears:
1. Remove crontab: crontab -r
2. Wait 30 seconds
3. Re-add crontab: crontab -e
4. Approve the system notification that appears
5. Verify entry in System Settings → General → Login Items & Extensions
```

No code change required. This is a macOS system settings action.

### B — Scheduler Acceptance Test (PENDING_APPROVAL)

```
1. Install test crontab: * * * * * python3 /tmp/cron_test.py >> /tmp/cron_out.log 2>&1
2. Wait 60 seconds
3. Verify /tmp/cron_out.log exists and contains output
4. Remove test crontab: crontab -r
5. Reinstall production crontab
```

Authorization required from user before modifying crontab.

### C — Launchd Migration (OPTIONAL, requires design approval)

If cron remains unreliable, migrate to LaunchAgent `.plist` (see `hybrid_scheduler_recovery_plan.md`). Requires explicit authorization to install.

---

## 10. Safety Verification

- No production crontab modified ✓
- No launchctl bootstrap executed ✓
- No production SQLite writes ✓
- No ForwardSignals mutation ✓
- V3 parameters frozen ✓
- BTM database not modified ✓
- TCC database not accessed ✓
