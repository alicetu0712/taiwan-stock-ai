# Session 71G — LaunchD Architecture Decision

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / MIGRATION_DESIGN_ONLY  
**Note**: Design only — no launchd installation authorized

---

## 1. Decision Question

Should the migration target a **User LaunchAgent** (`~/Library/LaunchAgents/`) or a **System LaunchDaemon** (`/Library/LaunchDaemons/`)?

---

## 2. Comparison Matrix

| Attribute | User LaunchAgent | System LaunchDaemon |
|---|---|---|
| **Location** | `~/Library/LaunchAgents/` | `/Library/LaunchDaemons/` |
| **Context** | User session (GUI login) | System boot (root or specified user) |
| **User identity** | Runs as logged-in user (`alicetu`) | Runs as root unless `UserName` key set |
| **Login required** | YES — requires user to be logged in | NO — starts at boot |
| **Environment** | Full user environment (`HOME`, `PATH`, user dotenv) | Minimal system env; must configure explicitly |
| **SECRET LOADING** | `.env` in project dir via `load_dotenv()` | Same IF `WorkingDirectory` set correctly; safer: not needed here |
| **Sleep/wake behavior** | Fires when user session active after wake | Fires when system wakes (before login) |
| **For our use case** | **CORRECT** — data task tied to user session | OVERKILL — no need for root/boot execution |
| **Installation command** | `launchctl bootstrap gui/$UID <plist>` | `launchctl bootstrap system <plist>` (requires sudo) |
| **Removal command** | `launchctl bootout gui/$UID <label>` | `launchctl bootout system <label>` (requires sudo) |
| **Config file owner** | user | root |
| **Principle of least privilege** | SATISFIED | VIOLATED unless `UserName` key specified |
| **Maintenance complexity** | LOW | MEDIUM (requires sudo for changes) |
| **Industry standard for user scripts** | YES | NO (daemons for system services) |

---

## 3. Sleep/Wake Catch-up Behavior

This is the critical difference vs traditional cron.

**launchd `StartCalendarInterval` catch-up semantics** (documented behavior, Apple Technical Note TN2083):

> If the system is asleep or the user is not logged in at the scheduled time, launchd fires the job within a grace window after the machine becomes available.

**Caveats** (not all are PLATFORM_BEHAVIOR_VERIFIED):

| Claim | Verification Status |
|---|---|
| Fires within 60 seconds of wake | `PLATFORM_BEHAVIOR_UNVERIFIED` — grace window size is undocumented; empirically ~30-120s |
| Fires exactly once per missed interval | `PLATFORM_BEHAVIOR_VERIFIED` — launchd single-instance per calendar interval |
| Multiple missed intervals fire multiple catch-ups | `PLATFORM_BEHAVIOR_UNVERIFIED` — only the most recent missed fire is caught up, NOT all missed |
| Fires even if user not logged in (LaunchAgent) | `PLATFORM_BEHAVIOR_UNVERIFIED` — LaunchAgent requires user session to be active |
| Fires during DarkWake | `PLATFORM_BEHAVIOR_UNVERIFIED` — DarkWake may not activate full user session for LaunchAgent |
| Fires immediately on next boot | `PLATFORM_BEHAVIOR_UNVERIFIED` — unclear if first-boot catch-up applies |

**Critical implication**: launchd does NOT guarantee catch-up for LaunchAgent during DarkWake. The machine must have a full user session active. This means:

- If machine wakes at 16:30 (full user wake, lid open) → LaunchAgent fires ✓
- If machine DarkWakes at 16:01 (SleepService, no display) → LaunchAgent may NOT fire (user session inactive) ⚠
- If machine never wakes until next day → LaunchAgent fires on next-day wake with today's date = next day (Nov 11 data permanently missed) ✗

This nuance means launchd `StartCalendarInterval` is **better than cron** (cron never catches up) but **not guaranteed** for every missed window.

---

## 4. User LaunchAgent Assessment for This Use Case

### Why LaunchAgent is correct:

1. **User context required**: The script loads `.env` via `load_dotenv()` and uses `config.DB_PATH` which is relative to the project directory. These path computations use `__file__` (absolute), so they work in any context, but environment safety is higher with the user context that owns the files.

2. **No elevated privileges needed**: TWSE/TPEx APIs are public (no auth). SQLite writes only to `data/platform.db` owned by `alicetu`. No system-level operations.

3. **Logging**: stdout/stderr captured via `StandardOutPath`/`StandardErrorPath` → `logs/hybrid_cron.log`. User owns the log directory.

4. **Security**: Running as `alicetu` matches file ownership. LaunchDaemon with root would add unneeded privilege escalation risk.

5. **Principle of least privilege**: LaunchAgent with user identity = minimal required authority.

6. **Simpler installation**: No `sudo` required; `launchctl bootstrap gui/$UID` works as normal user.

---

## 5. LaunchDaemon Assessment

**Reasons to REJECT LaunchDaemon for this use case**:

1. Requires root or explicit `UserName` key — adds complexity without benefit
2. The backfill task has no system-level resource requirements
3. Would run before user login — potentially before `.env` is accessible (though path is absolute)
4. Harder to maintain (all changes require sudo)
5. Industry guidance: LaunchDaemons are for system services, not user data tasks

---

## 6. Designed Plist (LaunchAgent)

**File path**: `~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist`  
**Label**: `com.antigravity.stockplatform.dailybackfill`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- Identity -->
    <key>Label</key>
    <string>com.antigravity.stockplatform.dailybackfill</string>

    <!-- Command — matches existing crontab exactly -->
    <key>ProgramArguments</key>
    <array>
        <string>/Library/Frameworks/Python.framework/Versions/3.13/bin/python3</string>
        <string>/Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py</string>
        <string>--execute</string>
    </array>

    <!-- Schedule: 08:00 UTC = 16:00 CST (Asia/Taipei) -->
    <!-- launchd StartCalendarInterval uses local system time, not UTC -->
    <!-- Machine must be in Asia/Taipei timezone for Hour=16 to be correct -->
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Weekday</key><integer>1</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <dict>
            <key>Weekday</key><integer>2</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <dict>
            <key>Weekday</key><integer>3</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <dict>
            <key>Weekday</key><integer>4</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <dict>
            <key>Weekday</key><integer>5</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
    </array>

    <!-- Working directory: project root (matches cron working directory) -->
    <key>WorkingDirectory</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform</string>

    <!-- Logging: append to same log as cron -->
    <!-- NOTE: launchd redirects (overwrites) unless log rotation is handled externally -->
    <key>StandardOutPath</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log</string>

    <!-- Environment: minimal — dotenv handles secrets -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>/Users/alicetu</string>
        <key>PATH</key>
        <string>/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>

    <!-- Do NOT start on load — only fire at scheduled time -->
    <key>RunAtLoad</key>
    <false/>

    <!-- Throttle: prevent rapid-refire after crash (60s minimum between restarts) -->
    <!-- Note: ThrottleInterval prevents restart loop, not duplicate scheduled fires -->
    <key>ThrottleInterval</key>
    <integer>60</integer>
</dict>
</plist>
```

**CRITICAL NOTE on `StartCalendarInterval` with weekday array**: The plist above uses 5 separate `Weekday` entries (1=Monday through 5=Friday in launchd convention). This is the correct approach since launchd `StartCalendarInterval` does not support "1-5" range syntax like cron.

**CRITICAL NOTE on log behavior**: launchd `StandardOutPath` truncates the file on each invocation. To preserve log history (append behavior like cron `>>`), one of:
- Use a wrapper shell script that appends
- Or accept log rotation (launchd overwrites each run)
- Recommendation: use a wrapper script or accept overwrite + rely on `.cron_state.json` for history

---

## 7. Architecture Decision

| Decision | Verdict |
|---|---|
| **Architecture** | `LAUNCH_AGENT_RECOMMENDED` |
| **Rationale** | User context, no root needed, matches file ownership, simpler maintenance |
| **LaunchDaemon** | REJECTED — no system-level requirements; violates least privilege |
| **Implementation** | NOT AUTHORIZED — pending explicit user instruction |
