# macOS Cron Permission Validation

**Date:** 2026-11-05  
**Platform:** macOS Sequoia 25.3.0 (Darwin 25.3.0)  
**Status:** MACOS_PERMISSION_NOT_VERIFIED

---

## What Was Verified (from Terminal)

| Check | Method | Result |
|---|---|---|
| Python interpreter exists | `which python3` | PASS — `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` |
| Script paths exist | preflight CG01–CG04 | PASS |
| SQLite DB accessible | backup API test | PASS (integrity_check=ok, 528K rows, 82.4 MB) |
| Cron minimal-env test | `env -i HOME=... PATH=... python3 hybrid_shadow_cron.py` | PASS — DRY_RUN_OK |
| System timezone | `date +%Z` | CST (UTC+8) → correct cron hour = 16 |
| Log directory writable | `ls -la logs/` | PASS |

---

## What Cannot Be Verified from Terminal

### Full Disk Access (FDA) for cron

macOS Sequoia 25.3 requires Full Disk Access for `cron` to read files outside the user's standard home directories. The Terminal process itself has FDA (you can read the DB from Terminal), but `cron` runs under a different security context.

**Why Terminal cannot verify cron's FDA:** `Terminal.app` already has Full Disk Access, so any test run from Terminal inherits those permissions. The only way to verify cron's FDA is to:
1. Install the cron entry
2. Wait for a scheduled run
3. Check the log for access errors

### How to Grant FDA to cron (manual steps required)

1. Open **System Settings** → **Privacy & Security** → **Full Disk Access**
2. Click the `+` button
3. Navigate to `/usr/sbin/cron` (press `Cmd+Shift+G` to type the path)
4. Add `/usr/sbin/cron` and enable the toggle
5. You may be prompted to restart cron: `sudo launchctl kickstart -k system/com.vix.cron`

### Alternative: Use launchd instead of cron

macOS's `launchd` has better integration with the permission system and handles sleep/wake cycles more reliably than cron. However, launchd requires a `.plist` file and separate approval. See `hybrid_cron_installation_audit.md` for the launchd path.

---

## Risk Assessment

| Scenario | Probability | Impact | Mitigation |
|---|---|---|---|
| cron has FDA → runs fine | High (most installs) | None | First run will confirm |
| cron lacks FDA → silent failure | Medium (Sequoia 15+) | Missed run | `--check-missed` will detect; grant FDA |
| cron lacks FDA → explicit error | Low | Error in log | Fix: grant FDA, re-run |

**Recommended action:** Install cron, let it run once, verify log. If log shows permission errors, grant FDA and re-run.

---

## Preflight Check Status

The preflight script (`hybrid_shadow_preflight.py`) reports `MACOS_PERMISSION_NOT_VERIFIED` as a WARNING (not a blocker). The check is:

```python
# PF22 — macOS FDA cannot be verified from Terminal
# macOS cron runs in a separate security context
# Full Disk Access must be granted to /usr/sbin/cron in System Settings
result = "MACOS_PERMISSION_NOT_VERIFIED"
```

This is documented as a known limitation. The cron entry is otherwise CONDITIONAL READY.

---

## Post-Install Verification Steps

After running `crontab -e` to install the entry:

```bash
# 1. Check cron is registered
crontab -l

# 2. Wait for 16:00 Taiwan time (or test manually)
python3 scripts/hybrid_shadow_cron.py --execute  # manual dry-run

# 3. Check log after first run
tail -50 logs/hybrid_cron.log

# 4. Check for permission errors
grep -i "permission\|denied\|error" logs/hybrid_cron.log

# 5. Check state
python3 scripts/hybrid_shadow_cron.py --status
```

If `logs/hybrid_cron.log` is empty after the scheduled time, cron ran but output was suppressed — check `mail` or `MAILTO` configuration.
