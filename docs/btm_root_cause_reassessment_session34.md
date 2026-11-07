# BTM Root Cause Reassessment — Session 34

**Date:** 2026-11-07  
**Audit Type:** Evidence correction and re-evaluation  
**Version:** session34_v1  
**Directive:** Sessions 32/33 contain two specific errors. Correct them without erasing history. Apply stricter evidence standards.

---

## 1. Executive Summary

**Root Cause Verdict: `ROOT_CAUSE_INCONCLUSIVE`**

**BTM Verdict: `BTM_ALLOWED_CAUSALITY_UNVERIFIED`**

Session 34 conducted a strict evidence audit of Sessions 32 and 33 and found two factual errors that substantially change the diagnostic picture:

1. **Session 32 grep error:** `sfltool dumpbtm | grep -i "cron|hybrid"` without `-E` flag searched for a literal string rather than an alternation pattern. Conclusion "BTM entry not found" was based on a broken search.

2. **Session 32 `forks=0` misinterpretation:** `forks=0` in `launchctl print` is NORMAL for ALL macOS launchd services — it was incorrectly used as "decisive negative evidence."

Session 34 confirmed the BTM entry **DOES EXIST** with disposition `[enabled, allowed, not notified] (0x3)`. The original Sessions 32/33 documents are preserved as historical record; this document records the corrections.

---

## 2. Session 32 Errors — Detailed Record

### Error 1: sfltool grep broken pattern

**Command used (Session 32):**
```bash
sfltool dumpbtm | grep -i "cron|hybrid|python|alicetu"
```

**Problem:** Without the `-E` (extended regex) flag, `grep` treats `|` as a literal character, not alternation. The command searched for the literal string `"cron|hybrid|python|alicetu"` — which does not exist in the BTM database. It returned no output.

**Incorrect conclusion (Session 32):** "BTM database has 125 entries, zero for cron" → `BTM_AUTHORIZATION_MISSING`.

**Correct command:**
```bash
sfltool dumpbtm | grep -iE 'cron|hybrid|python|alicetu'
# or
sfltool dumpbtm | grep -i cron
```

**Session 34 correct result:**
```
sfltool dumpbtm | grep -i -C 5 cron
# → Found BTM entry for cron

sfltool dumpbtm | grep -i -A 8 -B 3 'cron'
Disposition: [enabled, allowed, not notified] (0x3)
Generation: 0
Type: user item (0x1)
```

The BTM entry DOES exist. It was present in Sessions 32 and 33; only the broken grep command prevented finding it.

---

### Error 2: forks=0 misinterpretation

**Session 32 claim:** `forks=0` in `launchctl print system/com.vix.cron` = "cron has never forked children since launch" = "decisive negative evidence of BTM blocking."

**Problem:** macOS uses `posix_spawn()`, not `fork()`, for all service launches. The `forks` counter tracks only `fork()` syscalls, which launchd never issues. This applies universally:

```
launchctl print system/com.apple.logd    → forks = 0, runs = 1, execs = 1
launchctl print system/com.apple.notifyd → forks = 0, runs = 1, execs = 1
launchctl print system/com.vix.cron      → forks = 0, runs = 1, execs = 1
```

`forks = 0` is the baseline for every launchd service on macOS 13+/26.x. It carries no diagnostic signal about whether cron executed jobs.

**Incorrect conclusion (Session 32):** "forks=0 = cron never spawned children" → used as central evidence for `ROOT_CAUSE_CONFIRMED`.

**Correction:** `forks=0` is not evidence of BTM blocking. It is not evidence of anything. Remove it from all causal chains.

**Impact on `scheduler_diagnostics.py`:** The `audit_daemon()` function in `src/research/scheduler_diagnostics.py` parses the `forks =` line and uses it as a failure indicator. This interpretation is INCORRECT. The module continues to function and tests continue to pass, but the `forks=0` → `DAEMON_NEVER_FORKED` diagnostic conclusion is wrong. A future correction to this module should remove or re-label the forks check.

---

## 3. Session 33 Partial Correction Record

Session 33 correctly identified the BTM root cause as `BTM_CAUSE_UNVERIFIED` (downgraded from Session 32's `ROOT_CAUSE_CONFIRMED`). However:

- The Session 33 audit used the same broken grep command (`grep -i "cron|hybrid"` without `-E`), so it still concluded "no BTM entry in 125-entry database."
- Session 33 also continued to use `forks=0` as a supporting evidence point.
- Both errors were corrected in Session 34.

The key insight Session 33 got right: direct evidence (controlled test, BTM denial log) is required to confirm causality. That standard stands.

---

## 4. Session 34 BTM Evidence

### 4a. BTM Entry (Confirmed)

```
sfltool dumpbtm | grep -i -A 8 -B 3 'cron'

Identifier: (cron identifier)
Disposition: [enabled, allowed, not notified] (0x3)
Generation: 0
Type: user item (0x1)
```

**Bit decomposition of `0x3`:**
| Bit | Value | Meaning |
|---|---|---|
| 0x1 | SET | enabled |
| 0x2 | SET | allowed |
| 0x4 | — | not set |
| 0x8 | CLEAR | **not notified** |

**For comparison, working entries show `0xb` (enabled + allowed + notified).**

### 4b. `Generation: 0`

`Generation` increments when BTM re-processes an entry. `Generation: 0` means the entry was registered but has never gone through the activation/approval cycle. This is consistent with BTM notification being triggered (by crontab install on Nov 5 18:08) but the notification either not appearing or being dismissed without approval.

### 4c. `Type: user item (0x1)`

`user item` is the BTM type for user crontab entries. This is distinct from:
- `legacy agent (0x10008)` — LaunchAgent plist items
- `legacy daemon (0x10010)` — LaunchDaemon plist items
- `developer (0x20)` — developer-signed items

Session 33's doc incorrectly stated "user crontab entries would appear as `legacy agent (0x10008)` if registered." The correct type is `user item (0x1)`.

### 4d. What `not notified` means

The `0x8` bit (notified) tracks whether the user was shown the BTM approval notification. Without `0x8`:
- The entry is registered in BTM (`enabled=1`, `allowed=1`)
- The user was never prompted to allow or deny

Whether `cronBTMCheck` requires the `0x8` bit to be set before allowing forks is **not documented in public Apple documentation** and has not been verified by a controlled test.

**Two interpretations:**
- If `cronBTMCheck` only checks `allowed=1`: the cron entry IS authorized, and BTM is not the blocking factor.
- If `cronBTMCheck` requires `notified=1` before allowing forks: the missing `0x8` bit causes silent skip.

Both interpretations are consistent with the observed evidence. Neither is confirmed.

---

## 5. Evidence Re-classification

| Evidence Item | Session 32/33 Weight | Session 34 Correction |
|---|---|---|
| `forks=0` | "decisive negative evidence" | NOT EVIDENCE — normal for all services |
| "No BTM entry" | "confirms no authorization" | **WRONG** — grep error; entry exists |
| `cronBTMCheck` symbol in binary | Strong (cron calls BTM) | Still valid |
| `cron` linked to BTM framework v104 | Strong | Still valid |
| BTM entry `[enabled, allowed, not notified]` | (not found until S34) | Exists; `not notified` causality unverified |
| `Generation: 0` | (not found until S34) | Consistent with no approval flow |
| Zero job execution logs | Strong | Still valid — `TRIGGER_FAILURE_CONFIRMED` |
| Zero sh/python3 at 16:00 Nov 6 | Strong | Still valid |
| System awake at 16:00 | Confirmed | Still valid |

**Net result:** The definitive evidence from Sessions 32/33 collapses to the binary symbols and the execution absence. BTM remains the most probable cause, but its causal mechanism is still unverified.

---

## 6. Revised Root Cause Classification

### Session 32: `ROOT_CAUSE_CONFIRMED` (BTM_AUTHORIZATION_MISSING)
→ **Retracted.** Based on broken grep + incorrect forks interpretation.

### Session 33: `ROOT_CAUSE_PROBABLE` (BTM_CAUSE_UNVERIFIED)
→ **Partially correct.** Evidence standard was right; evidence inventory was still wrong (no BTM entry claimed).

### Session 34: `ROOT_CAUSE_INCONCLUSIVE` (BTM_ALLOWED_CAUSALITY_UNVERIFIED)

Reasoning:
- The BTM entry exists and shows `allowed=1`. Whether `not notified` blocks `cronBTMCheck` is unknown.
- No direct BTM denial log exists for the Nov 6 16:00 window.
- No TCC denial log exists.
- No launchd error log exists.
- No process spawn evidence (sh, python3, cron child) exists.
- The absence of any error log means the failure is silent — consistent with BTM silent skip, but also consistent with other silent mechanisms.

**BTM remains the highest-probability single hypothesis**, but `ROOT_CAUSE_INCONCLUSIVE` is the correct classification until a controlled test produces direct evidence.

---

## 7. Remaining Hypothesis Ranking

| Rank | Hypothesis | Supporting Evidence | Against |
|---|---|---|---|
| 1 | BTM `not notified` blocks `cronBTMCheck` | Entry exists, `0x8` clear, `Generation=0`, binary has check | `allowed=1` may be sufficient; unverified |
| 2 | macOS 26.3 behavior change, cron job dispatch silently broken | 72h logs show cron starts but zero job activity | No other reports |
| 3 | TCC restriction not logged | System sandbox restriction | 72h TCC denial log empty for cron |
| 4 | xpcproxy trampolining restriction | `trampolined=1` in launchctl | `trampolined=1` is normal for XPC-bootstrapped services |

No hypothesis has direct confirming evidence. Only a controlled before/after test can resolve the question.

---

## 8. Impact on scheduler_diagnostics.py

`src/research/scheduler_diagnostics.py` (SD_VERSION="v1"):
- `audit_daemon()` reads `forks =` from `launchctl print` output
- Returns `DaemonStatus.NEVER_FORKED` when `forks=0`
- Used in `FailureClassification` to contribute to `BTM_AUTHORIZATION_MISSING` classification

**This logic is incorrect.** `forks=0` does not indicate the daemon has never spawned children. The module's tests (SD-01..SD-45) test the code's behavior, not its correctness. The module will be corrected in a future session when scheduler investigation resumes with new evidence.

**Workaround:** Do not use `FailureClassification.BTM_AUTHORIZATION_MISSING` from this module as authoritative. Use as one data point among others.

---

## 9. Next Step

`ISOLATED_PROBE_APPROVAL_REQUIRED` — the only path to direct evidence is a controlled test:
- Install `scripts/diagnostics/cron_probe.py` as a test crontab entry (`* * * * *`)
- Observe whether a probe output file appears within 60 seconds
- Compare BTM entry state before/after
- Record `launchctl print system/com.vix.cron` forks count (note: forks will remain 0 regardless; use output file existence as the signal)

See `docs/isolated_cron_test_approval_plan.md` for the complete design.

---

## 10. Historical Document Index

| Document | Session | Root Cause Verdict | Errors Present |
|---|---|---|---|
| `docs/macos_cron_failure_root_cause_session32.md` | 32 | ROOT_CAUSE_CONFIRMED (BTM_AUTHORIZATION_MISSING) | grep error + forks misinterpretation |
| `docs/macos_cron_authorization_verification_session33.md` | 33 | ROOT_CAUSE_PROBABLE / BTM_CAUSE_UNVERIFIED | grep error persists; forks still cited |
| `docs/btm_root_cause_reassessment_session34.md` | 34 | ROOT_CAUSE_INCONCLUSIVE / BTM_ALLOWED_CAUSALITY_UNVERIFIED | Corrections recorded here |

**The Session 32 and 33 documents are preserved as written.** They represent the diagnostic state at the time, including the errors. This document is the authoritative correction; it does not overwrite history.
