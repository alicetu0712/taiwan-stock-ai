# Session 71H — Logging & Observability Design

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / IMPLEMENTATION_PLANNING_ONLY

---

## 1. Current Logging Inventory

### Primary Log: `logs/hybrid_cron.log`
- **Mechanism** (cron): `>> logs/hybrid_cron.log 2>&1` — **APPEND**
- **Mechanism** (launchd): `StandardOutPath = logs/hybrid_cron.log` — **TRUNCATES** (overwrites)
- **Last modified**: Nov 10 17:37 CST (106 lines)
- **Format**: Freetext with prefixes like `[cron]`, `[backfill]`, `[shadow]`
- **Retention**: Unbounded; grows indefinitely under cron

### Primary State: `data/.cron_state.json`
- **Purpose**: One-file audit trail of last run result
- **Format**: JSON (human-readable)
- **Updated**: Every run via `_save_state()` in `finally:` block
- **Last state** (confirmed):
  ```json
  {
    "run_at": "2026-11-10T08:00:39.243757+00:00",
    "today": "2026-11-10",
    "taiwan_time": "2026-11-10T16:00:39 CST",
    "execute": true,
    "steps": {
      "lock": "released",
      "calendar": "trading_day",
      "data_ready": true,
      "backfill": {"exit_code": 0, "executed": true},
      "data_freshness": "PROVIDER_NOT_READY",
      "data_freshness_detail": "0050 last_date=2026-11-05, today=2026-11-10",
      "freshness_retry_attempt": 3
    },
    "status": "BLOCKED_STALE_DATA",
    "exit_code": 0,
    "trigger_source": "cron_scheduled"
  }
  ```

### Lock File: `data/.cron.lock`
- **Content**: PID of wrapper process
- **Diagnostic value**: Stale PID indicates crashed previous run
- **State**: 6 bytes, PID 91460 (dead), Nov 10 16:00 — stale lock (safe, advisory)

### Shadow Run Log: `hybrid_forward_run_log` (SQLite table)
- **Key**: `run_id TEXT UNIQUE`
- **Contains**: trade_date, signal counts, decision counts, duration

---

## 2. LaunchD Log Truncation Problem

Under cron, `>>` appends: each run adds lines to the existing log.  
Under launchd, `StandardOutPath` truncates: each invocation **overwrites** the log file.

**Consequence**: Under launchd, only the MOST RECENT run is visible in `logs/hybrid_cron.log`.

**Mitigation options**:

### Option L-1: Wrapper Shell Script for Append

Replace direct plist invocation with a shell script wrapper:
```bash
#!/bin/bash
# /path/to/run_cron.sh (PROPOSED — not authorized)
cd /path/to/stock_platform
python3 scripts/hybrid_shadow_cron.py --execute >> logs/hybrid_cron.log 2>&1
```

Plist runs `run_cron.sh` instead of Python directly. Shell script handles append.

| Attribute | Value |
|---|---|
| Preserves full log history | YES |
| Complexity | LOW (1 extra shell script) |
| Recommended | YES |

### Option L-2: Accept Truncation + Rely on State File

Accept launchd truncation; use `data/.cron_state.json` as the single-run audit trail.

| Attribute | Value |
|---|---|
| Preserves full log history | NO (only last run in log) |
| State file covers essentials | YES (all step outcomes) |
| Implementation effort | ZERO |
| Recommended | ACCEPTABLE if log history not required |

### Option L-3: Explicit Append in Python (Mode 'a')

Modify `hybrid_shadow_cron.py` to open log file with `mode='a'` explicitly:
```python
# PROPOSED (not authorized):
with open("logs/hybrid_cron.log", "a") as f:
    sys.stdout = f
    sys.stderr = f
```

| Attribute | Value |
|---|---|
| Requires Python code change | YES |
| Authorized under S71H | NO |
| Recommended | No (requires code change, deferred) |

**Recommendation**: Option L-1 (wrapper shell script) for launchd migration; Option L-2 as fallback if shell script adds complexity.

---

## 3. Proposed Run Record Format

The state file should be augmented with new fields when guards are added. Proposed schema (DESIGN ONLY, not authorized):

```json
{
  "schema_version": 2,
  "run_id": "cron-20261112-160001-a1b2c3d4",
  "run_at": "<UTC ISO8601>",
  "today": "2026-11-12",
  "taiwan_time": "2026-11-12T16:00:01 CST",
  "execute": true,
  "trigger_source": "cron_scheduled",
  "steps": {
    "lock": "acquired",
    "same_day_guard": "ALLOWED",
    "calendar": "trading_day",
    "data_ready": true,
    "execution_window": "WITHIN_WINDOW",
    "backfill": {
      "exit_code": 0,
      "executed": true,
      "dates_written": ["2026-11-11", "2026-11-12"],
      "dates_skipped": [],
      "dates_error": []
    },
    "data_freshness": "FULL_MARKET_FRESH",
    "data_freshness_detail": "5247 stocks, 0050 2026-11-12",
    "freshness_retry_attempt": 0,
    "backup": "data/backups/platform_20261112_160045.db.bak",
    "shadow": {
      "exit_code": 0,
      "decisions_new": 7,
      "decisions_conflict": 0,
      "run_id": "shadow-20261112-160102-b2c3d4e5"
    },
    "lock": "released"
  },
  "status": "SUCCESS",
  "exit_code": 0,
  "rc_version": "2",
  "script_hash_backfill": "4eb6eacf..."
}
```

**Key additions**:
- `schema_version`: Allows future parsing to handle old vs new format
- `run_id`: Unique per run (useful for correlating log lines to state)
- `same_day_guard`: New step visibility
- `execution_window`: New step visibility
- `dates_written` / `dates_skipped` / `dates_error`: Backfill granularity
- `shadow.decisions_conflict`: Dedup visibility
- `rc_version`: Which RC is running
- `script_hash_backfill`: SHA-256 confirmation (RC-2 integrity)

---

## 4. Structured Events (Log Line Format)

Proposed structured prefix for each log line:
```
[cron][<stage>][<status>] <timestamp> <message>
```

Examples:
```
[cron][startup][INFO] 2026-11-12T08:00:01Z run_id=cron-20261112-160001-a1b2c3d4 trigger=cron_scheduled
[cron][lock][INFO] 2026-11-12T08:00:01Z FileLock acquired pid=91560
[cron][guard][INFO] 2026-11-12T08:00:01Z same_day_guard=ALLOWED prior_status=BLOCKED_STALE_DATA
[cron][calendar][INFO] 2026-11-12T08:00:01Z is_trading_day=True today=2026-11-12
[cron][window][INFO] 2026-11-12T08:00:01Z execution_window=WITHIN_WINDOW 16:00–20:00
[cron][backfill][INFO] 2026-11-12T08:00:02Z subprocess started
[cron][backfill][INFO] 2026-11-12T08:03:21Z exit_code=0 dates_written=2 dates_error=0
[cron][freshness][INFO] 2026-11-12T08:03:22Z FULL_MARKET_FRESH stocks=5247 attempt=0
[cron][shadow][INFO] 2026-11-12T08:03:45Z exit_code=0 decisions=7 conflicts=0
[cron][complete][INFO] 2026-11-12T08:03:46Z status=SUCCESS exit_code=0 duration=225s
```

---

## 5. What to Monitor for H3 Acceptance

H3 requires confirming that the pipeline ran naturally post-RC2 deployment. Monitoring checklist:

| Signal | Source | Expected Value |
|---|---|---|
| `hybrid_cron.log` last line | `logs/hybrid_cron.log` | `status=SUCCESS` or `BLOCKED_STALE_DATA` |
| `.cron_state.json` today | `data/.cron_state.json` | `today == "2026-11-12"` and `trigger_source == "cron_scheduled"` |
| `.cron.lock` PID | `data/.cron.lock` | Dead PID (run complete) |
| SQLite max(date) for 0050 | `data/platform.db` | `>= 2026-11-11` |
| `hybrid_forward_run_log` latest | SQLite | `trade_date == "2026-11-12"` |

**Monitoring window**: 2026-11-12 16:00–17:00 CST (allow 1 hour for freshness retry). Machine must be awake at 16:00 CST.

---

## 6. LaunchD Observability Gaps vs Cron

| Feature | Cron | LaunchD | Gap |
|---|---|---|---|
| Log history | APPEND (all runs) | TRUNCATE (last run only) | Option L-1 mitigates |
| Trigger confirmation | `trigger_source="cron_scheduled"` | Same (if isatty check works) | Minor — verify `sys.stdout.isatty()` returns False under launchd |
| Exit code capture | Captured by shell | Captured by launchd (see `launchctl list`) | CHECK |
| Missed run detection | Manual (check state file) | Same | No gap |
| Last invocation time | `logs/hybrid_cron.log` mtime | Same (or `launchctl list`) | No gap |

**Verification needed pre-deployment**: Confirm `sys.stdout.isatty()` returns `False` when launched by launchd. Expected: False (launchd pipes stdout, not a tty). If True, `trigger_source` would be "manual" — wrong for auditing.

---

## 7. `launchctl list` Observability

After launchd deployment (not yet authorized), the following command shows job state:
```bash
launchctl list | grep com.antigravity.stockplatform.dailybackfill
```
Output columns: PID | LastExitStatus | Label
- PID = `-` when not running
- LastExitStatus = 0 on success; non-zero on failure
- Stale exit status visible until next run

This is a supplement to log file, not a replacement.

---

## 8. Verdict

| Item | Status |
|---|---|
| **Log append vs truncate** | `RISK_IDENTIFIED` — Option L-1 (shell wrapper) mitigates |
| **State file as audit trail** | `VERIFIED` — sufficient for essential run data |
| **New guard observability** | `DESIGN_READY` — same_day_guard + execution_window in state |
| **Structured log format** | `DESIGN_READY` — proposed but not authorized |
| **H3 monitoring checklist** | `READY` — 5 signals defined |
| **Overall** | `LOGGING_DESIGN_READY` |
