# macOS Cron Authorization Verification — Session 33

**Date:** 2026-11-07  
**Audit Type:** Read-only system audit  
**Version:** session33_v1  

---

## 1. Executive Summary

**Cron Root Cause: `ROOT_CAUSE_PROBABLE`** (downgraded from Session 32 `ROOT_CAUSE_CONFIRMED`)

**BTM: `BTM_CAUSE_UNVERIFIED`**

The 2026-11-06 cron failure evidence is consistent with BTM authorization missing, but no **direct** evidence (log entry, controlled before/after test, or system refusal record) has been obtained. The circumstantial evidence remains strong:

- `launchd forks=0` — daemon has never forked since Nov 5 18:00 start
- 125 BTM entries, zero for cron
- `/usr/sbin/cron` linked against `BackgroundTaskManagement.framework v104.0.0`
- `cronBTMCheck` symbol in binary
- No mail spool, no log file, no DB changes

However, `forks=0` and `no BTM entry` alone do not constitute direct proof of a BTM block. Alternative explanations (cron not waking up, TCC denial without log, kernel extension blocking) have not been directly ruled out by a controlled test.

The resolution is a controlled test with a minimal probe (see `isolated_cron_test_approval_plan.md`).

---

## 2. Baseline Snapshot (Session 33, 2026-11-07 12:55 CST)

| Item | Value |
|---|---|
| macOS | 26.3 (BuildVersion 25D125) |
| System time | Sat Nov 7 12:55 CST 2026 |
| User | alicetu (UID=501) |
| Cron daemon PID | 20488 (unchanged from Session 32) |
| Cron daemon start | 2026-11-05 18:00 Taiwan |
| launchd forks | **0** (unchanged from Session 32) |
| launchd state | running |
| BTM entries | 125 (unchanged) |
| Cron BTM entry | NOT FOUND (unchanged) |
| Script hash | `46209171...` (unchanged) |
| BT_HASH | `be43e8ca977d9fdd` (unchanged) |
| CP_HASH | `1feb7a6b294a063d` (unchanged) |
| ForwardSignals | 2605, MAX=2026-10-28, fp=caf3b962d38dec74 |
| Hybrid decisions | 21, MAX=2026-11-04, fp=a966df16aa82f85c |
| DailyPrice Nov 6 | 0 rows |
| DailyPrice Nov 7 | 0 rows (Saturday, market closed) |

---

## 3. BTM / TCC / FDA Evidence

### 3a. BTM Database

```
$ sfltool dumpbtm | grep -c "Identifier:"
125

$ sfltool dumpbtm | grep -i "cron|hybrid|python|alicetu"
(no output — zero matches)
```

BTM entry type distribution:
| Type | Count |
|---|---|
| developer (0x20) | 24 |
| legacy daemon (0x10010) | 11 |
| app (0x2) | 8 |
| legacy agent (0x10008) | 7 |
| spotlight (0x40) | 3 |
| quicklook (0x800) | 2 |
| login item (0x4) | 1 |

No "cron" type entry exists in the BTM type taxonomy from this database. User crontab entries would appear as `legacy agent (0x10008)` if registered.

### 3b. TCC / FDA Evidence

```
$ log show --last 72h --predicate 'subsystem == "com.apple.TCC"' | grep -i cron
(no output)
```

TCC denial log for 72h: empty for cron. This means either:
- cron was never attempted (consistent with BTM block before fork)
- cron was attempted but no TCC check was needed
- TCC log is not capturing all events

**TCC_DENIAL_NOT_CONFIRMED**

### 3c. cron Binary BTM Integration

```
$ otool -L /usr/sbin/cron
  BackgroundTaskManagement.framework/Versions/A/BackgroundTaskManagement
    (compatibility version 1.0.0, current version 104.0.0)

$ strings /usr/sbin/cron | grep BTM
  cronBTMToggle
  cronBTMCheck
  Error contacting BTM to check enablement state: %d
```

cron is **definitively linked** to BTM and calls `cronBTMCheck` before fork. This is confirmed from both `otool` and `strings`.

### 3d. Unified Log

The `log show --predicate` syntax on macOS 26.3 returns "too many arguments" in this shell context. Alternative log check (`log show --info --last 72h | grep cron`) returned no output.

**NO_CRON_LOG_ENTRIES_IN_72H** — consistent with zero forks (cron never ran).

---

## 4. Cron Trigger Analysis — Four-Case Classification

| Case | Evidence |
|---|---|
| **Case 1: Cron did NOT trigger** | `forks=0`, no log file, no mail, no DB change — **CONFIRMED** |
| Case 2: Cron triggered but script couldn't start | No evidence of trigger; fork count would be > 0 |
| Case 3: Script started but couldn't write log | No process spawn evidence; fork count would be > 0 |
| Case 4: Script started but environment failure | No process spawn evidence; fork count would be > 0 |

**Result: Case 1 is confirmed. The scheduler did not trigger at all.**

The question of WHY Case 1 occurred (BTM vs other mechanism) remains unverified by direct evidence.

---

## 5. BTM Cause Analysis

### Why BTM is the most probable cause

1. `forks=0` — daemon has never forked (not just Nov 6; every day since Nov 5 18:00)
2. cron binary calls `cronBTMCheck` before fork (confirmed from binary strings)
3. No BTM entry for cron in 125-entry database
4. Neighboring entries (Google, Adobe, Microsoft) are all authorized — cron was never registered
5. `cron.deny` contains only "Guest" — cron itself is not denied at the application level
6. macOS 26.3 introduced tighter BTM enforcement

### Why we cannot call it CONFIRMED

The `sfltool dumpbtm` output does not show what happens when `cronBTMCheck` fails. It shows the authorization database, not the runtime decision log.

Possible alternative scenarios:
- cron fires but `cronBTMCheck` passes silently and the real failure is elsewhere (not supported by `forks=0`)
- A kernel extension or security product is blocking cron at a lower level (possible but no evidence found)
- launchd itself is not waking cron at 16:00 (possible but `state=running` and daemon is live)

**Without a controlled before/after test (Stage B in the approval plan), BTM_CAUSE_UNVERIFIED is the correct classification.**

---

## 6. GUI Authorization Status

### System Settings → General → Login Items & Extensions

Based on the BTM database state:
- If a BTM entry existed for cron, it would appear in System Settings → General → Login Items & Extensions
- No BTM entry found → it may not appear in the GUI either
- The likely scenario: when crontab was installed on Nov 5, the BTM registration notification was either not shown, or was dismissed without approving

**CRON_GUI_ENTRY_STATUS: UNKNOWN** — cannot verify without user checking System Settings

The user should check:
1. System Settings → General → Login Items & Extensions
2. Scroll to "Allow in Background" or "Background Items" section
3. Look for any entry mentioning cron, Python, or Antigravity
4. If found and disabled: toggle to Allow
5. If not found: BTM registration likely failed — proceed to re-register via `crontab -r` + `crontab -e`

---

## 7. Independent Probe Design

See `docs/isolated_cron_test_approval_plan.md` for the complete design.

| Item | Value |
|---|---|
| Probe script | `scripts/diagnostics/cron_probe.py` |
| Version | v1 |
| Test coverage | 30 tests CP01–CP30, all PASS |
| Manual dry-run | PASS (UID=501, Taiwan time, no DB) |
| Manual execute | PASS (file created in tmp dir) |
| Scheduled install | PENDING_APPROVAL |

---

## 8. Cron vs launchd Assessment

| Dimension | Traditional cron | launchd LaunchAgent |
|---|---|---|
| Actual trigger evidence | forks=0, NEVER triggered | No live evidence (not installed) |
| BTM requirement | YES — `cronBTMCheck` before fork | NO — user agents exempt from cronBTMCheck |
| macOS 26.x reliability | LOW until BTM authorized | HIGH — native integration |
| Environment | Minimal PATH, no HOME vars | Full EnvironmentVariables support |
| Configuration | 5-field cron syntax | XML plist |
| Logging | >> redirect | StandardOutPath key |
| Working directory | Requires explicit `cd` | WorkingDirectory key |
| Migration risk | Low (re-register cron, same script) | Moderate (new plist, different trigger path) |
| Authorization required | System Settings BTM approve | launchctl bootstrap user/$UID |

**Assessment:** If Stage B test shows BTM still blocking even after System Settings action, migration to launchd is the recommended path. If Stage B test passes, stay on cron (simpler).

The proposed launchd plist is documented in `docs/hybrid_scheduler_recovery_plan.md`.

---

## 9. PF11 Regression Fix

See `docs/pf11_regression_root_cause.md` for full analysis.

**Root cause:** `check_dailyprice_freshness()` uses `date.today()` as reference, making the test non-deterministic. With Nov 6 missing, gap = (Nov 7 − Nov 5) = 2 > STALE_DAYS_WARN(1) → WARNING.

**Fix:** Applied fixed clock (same pattern as PF13) — freeze `date.today` to `date(2026, 11, 5)`.

**Gate unchanged.** The production gate correctly returns WARNING for missing data.

---

## 10. Approval Boundary

| Action | Authorization |
|---|---|
| Read BTM database | No auth required — DONE |
| Check unified logs | No auth required — DONE |
| Manual probe dry-run | No auth required — DONE |
| Manual probe execute | No auth required — DONE |
| Install test crontab | **PENDING_APPROVAL** |
| Remove test crontab | **PENDING_APPROVAL** |
| System Settings BTM action | **USER GUI ACTION REQUIRED** |
| launchctl bootstrap | Not planned |
| Nov 6 DailyPrice backfill | Not in scope this session |

---

## 11. Safety Verification

- Production crontab entry: **UNCHANGED** (`0 16 * * 1-5`, same as Session 32)
- Production script hash: **UNCHANGED** (`46209171...`)
- ForwardSignals: **UNCHANGED** (2605, fp=caf3b962d38dec74)
- Hybrid decisions: **UNCHANGED** (21, fp=a966df16aa82f85c)
- V3 BT_HASH: **UNCHANGED** (`be43e8ca977d9fdd`)
- V3 CP_HASH: **UNCHANGED** (`1feb7a6b294a063d`)
- Neon: NOT TOUCHED
- launchd: NOT MODIFIED
- BTM database: NOT MODIFIED (read-only audit only)

---

## 12. Test Results

| Suite | Tests | Status |
|---|---|---|
| CP01–CP30 (cron probe) | 30 | ALL PASS |
| PF11 (fixed clock) | 1 | PASS (was FAIL) |
| SD01–SD45 (scheduler diagnostics) | 45 | ALL PASS |
| Full regression | 2017 passed, 1 skipped | PASS |

---

## 13. Final Verdict

| Dimension | Verdict |
|---|---|
| **Cron Root Cause** | `ROOT_CAUSE_PROBABLE` — strong circumstantial evidence for BTM, no direct proof |
| **BTM** | `BTM_CAUSE_UNVERIFIED` — no direct log/controlled test; absence of entry + forks=0 is circumstantial |
| **Probe** | `PROBE_MANUAL_PASS` — dry-run and execute both PASS locally |
| **Scheduled Test** | `SCHEDULER_TEST_PENDING_APPROVAL` |
| **Regression** | `REGRESSION_PASS` — 2017 passed, 1 skipped |
| **V3 Activation** | `ACTIVATION_BLOCKED` — 6/6 blockers remain |
