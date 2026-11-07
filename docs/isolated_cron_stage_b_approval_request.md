# Isolated Cron Stage B — Approval Request

**Date:** 2026-11-08  
**Status:** `SCHEDULER_TEST_READY_FOR_APPROVAL`  
**Version:** session35_v1  
**Precondition:** Stage A complete (cron_probe.py built, tested, manual PASS)

---

## 1. Purpose

This document is the formal approval request for Stage B: installing a temporary, isolated, minute-level cron entry to determine whether the macOS scheduler can fire jobs under current system conditions.

**This is the only currently available path to direct evidence for the cron root cause.**

Stage B does NOT modify the production Hybrid Shadow entry. It uses only `cron_probe.py`, which has zero trading code, zero database connections, and zero network access.

---

## 2. Current Situation

| Item | State |
|---|---|
| Crontab | Installed, valid (`0 16 * * 1-5`) |
| Cron daemon | Running, PID 20488 |
| BTM entry | `[enabled, allowed, not notified] (0x3)`, Generation=0 |
| Root cause | `ROOT_CAUSE_INCONCLUSIVE` |
| hybrid_cron.log | ABSENT (Nov 6 job never ran) |
| DailyPrice Nov 6 | 0 rows |

The only way to distinguish:
- BTM `not notified` is blocking `cronBTMCheck` → probe will FAIL
- BTM is NOT the blocker → probe will PASS

...is a controlled before/after test.

---

## 3. Stage B — Exact Proposed Test Entry

```
* * * * *  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/diagnostics/cron_probe.py --execute --output-dir /tmp/cron_probe_output >> /tmp/cron_probe_redirect.log 2>&1
```

| Field | Value | Meaning |
|---|---|---|
| Minute | `*` | Every minute |
| Hour | `*` | Every hour |
| Day | `*` | Every day |
| Month | `*` | Every month |
| DOW | `*` | Every day of week |
| Python | Absolute path (`/Library/Frameworks/…/python3`) | Same interpreter as production |
| Script | `cron_probe.py` | Isolated probe only |
| Output | `/tmp/cron_probe_output/` | Outside project directory |
| Redirect | `/tmp/cron_probe_redirect.log` | Stderr capture |

---

## 4. Stage A — What Is Already Complete

| Item | Status |
|---|---|
| `scripts/diagnostics/cron_probe.py` v1 | COMPLETE |
| 30 tests CP01–CP30 | ALL PASS |
| Manual `--dry-run` | PASS (uid=501, +08:00) |
| Manual `--execute` | PASS (file written to /tmp) |
| No trading imports (AST-verified) | PASS |
| No network imports (AST-verified) | PASS |
| No crontab modification (AST-verified) | PASS |

---

## 5. Current Crontab Backup Strategy

Before any Stage B installation, the following backup must be completed:

```bash
# Step 1: Backup
crontab -l > /tmp/crontab_backup_$(date +%Y%m%d_%H%M%S).txt

# Step 2: Verify backup
cat /tmp/crontab_backup_*.txt
# Expected output: the single production 0 16 * * 1-5 line

# Step 3: Only proceed if backup verified
```

Production entry that must remain intact:
```
0 16 * * 1-5  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py --execute >> /Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log 2>&1
```

---

## 6. Expected Trigger Times

After installation: within 60 seconds (fires on next full minute).

Minimum observation period: **3 minutes** (at least 3 independent trigger attempts).  
Maximum test duration: **10 minutes** (must remove before leaving).

---

## 7. Success Criteria

All of the following must be true for Stage B PASS:

1. `/tmp/cron_probe_output/cron_probe_*.json` created within 60 seconds of installation
2. File contains valid JSON with `pid > 0` and `uid == 501`
3. `/tmp/cron_probe_redirect.log` created (even if empty = OK)
4. At least 2 output files within 3 minutes (confirms repeated triggering)

---

## 8. Failure Criteria

Stage B FAIL (cron still NOT triggering) if:

1. No output file after 120 seconds
2. `/tmp/cron_probe_redirect.log` does not exist after 120 seconds
3. `forks=0` (but note: this is NOT diagnostic — see SD46)

**A Stage B FAIL does NOT mean cron is permanently broken.** It means BTM authorization is still pending.

---

## 9. Interpretation Table

| forks | Output file | Interpretation |
|---|---|---|
| metadata only | EXISTS, uid=501 | Cron IS triggering. BTM `not notified` is NOT the blocker. Seek other root cause. |
| metadata only | ABSENT after 120s | Cron NOT triggering. BTM `not notified` is probable blocker → System Settings action. |
| metadata only | EXISTS but uid≠501 | Execution context wrong. Investigate environment. |
| metadata only | EXISTS, stderr errors | Python environment issue in cron context. |

**Note:** `forks` counter is not used in interpretation. Only the output file existence determines PASS/FAIL.

---

## 10. Rollback Procedure

### After observation (required, with or without authorization to proceed further):

```bash
# Step 1: Show current crontab (verify no unexpected changes)
crontab -l

# Step 2: Edit to remove test entry, keep production entry
# (crontab -e, delete the * * * * * line, save)

# Step 3: Verify only production entry remains
crontab -l
# Expected: only the 0 16 * * 1-5 line

# Step 4: Check no stale probe output
ls -la /tmp/cron_probe_output/
```

### Emergency rollback (full restore):

```bash
# Full crontab restore from backup
crontab /tmp/crontab_backup_YYYYMMDD_HHMMSS.txt

# Verify
crontab -l
```

### Cleanup verification:

```bash
# Confirm only the production entry remains
crontab -l | wc -l  # should be 1
crontab -l | grep "hybrid_shadow_cron"  # should match
crontab -l | grep "cron_probe"  # should be empty
```

---

## 11. Production Isolation Verification

Stage B is fully isolated from production:

| Protection | Mechanism |
|---|---|
| No production SQLite writes | AST-verified: no sqlite3 import in cron_probe.py |
| No Neon writes | AST-verified: no network imports |
| No ForwardSignals modification | No connection to any database |
| No Hybrid decision capture | No connection to any database |
| No V3 activation | No research module imports |
| No production credential access | No imports from src.research |
| Output to /tmp only | `--output-dir /tmp/cron_probe_output` |
| Does not overwrite production log | Output dir is `/tmp/`, not `logs/` |
| Production entry preserved | Backup + verification before install |
| Test entry has unique script path | Different from `hybrid_shadow_cron.py` |

---

## 12. What Stage B Does NOT Prove

- **A PASS does not mean Hybrid Shadow cron is now working.** The probe uses a different script (`cron_probe.py`) and fires every minute, not at 16:00 trading-day logic.
- **A PASS does not advance V3 Activation.** V3 activation requires the FORMAL `hybrid_shadow_cron.py` to execute successfully on a trading day 16:00 and produce PROSPECTIVE decisions.
- **A FAIL does not mean the production entry is permanently broken.** It confirms authorization is still needed.

---

## 13. After Stage B: Next Steps

### If Stage B PASSES (cron triggers probe):
1. Remove test entry
2. Verify production entry intact
3. Check BTM entry state: `sfltool dumpbtm | grep -i -A 10 cron`
4. If BTM entry now shows `notified=True (0xb)`: cron is authorized and working
5. Wait for next trading day 16:00 for formal Hybrid Shadow execution
6. DailyPrice backfill for Nov 6 is a separate authorization (see Phase 3)

### If Stage B FAILS (cron does NOT trigger probe):
1. Remove test entry
2. Go to System Settings → General → Login Items & Extensions
3. Locate cron/Python entry in "Allow in Background" section
4. Toggle to Allow
5. Re-run Stage B to confirm fix
6. If still failing after System Settings action → escalate to launchd migration

---

## 14. Safety Boundaries

The following actions require explicit authorization BEYOND this document:

| Action | Authorization Required |
|---|---|
| Install Stage B crontab entry | **This document is the request** |
| Remove Stage B crontab entry | Implicit with Stage B authorization |
| System Settings BTM action | Separate user GUI action |
| DailyPrice Nov 6 backfill | Separate explicit write authorization |
| launchd plist installation | Not planned; escalation path only |

The following actions are **forbidden** regardless of authorization:

- `crontab -r` (delete entire crontab)
- Modify production `0 16 * * 1-5` entry
- Write to production SQLite or Neon
- Run `hybrid_shadow_cron.py` via any test mechanism
- Activate V3 shadow

---

## 15. Authorization Statement Required

To proceed with Stage B, the user must authorize:

> **"I authorize installation of the test crontab entry described in Stage B of this document. I understand this is a temporary entry (`* * * * * …cron_probe.py`) to be removed within 10 minutes, and does not modify or replace the production Hybrid Shadow entry (`0 16 * * 1-5 …hybrid_shadow_cron.py`)."**

**Current status: `SCHEDULER_TEST_PENDING_APPROVAL`**

This document is the formal request. No installation will occur until the authorization statement is provided in the conversation.
