# Hybrid Cron — Missed Run Recovery

**Date:** 2026-11-05  
**Scope:** Mac sleep, shutdown, or other missed cron sessions

---

## Why Mac Cron Misses Runs

macOS `cron` does **not** run missed jobs after the Mac wakes up. If the Mac is asleep or shut down at the scheduled time (16:00 Taiwan), the job is silently skipped — no log entry, no alert.

This is a known limitation of macOS cron (vs. `launchd` with `StartCalendarInterval`). See [Alternative: launchd](#alternative-launchd) below.

---

## Detecting Missed Runs

```bash
python3 scripts/hybrid_shadow_cron.py --check-missed
```

This command:
1. Reads `hybrid_forward_run_log` from SQLite for the last recorded session
2. Compares against today's date using `TaiwanTradingCalendar`
3. Reports any trading days with no run logged between last run and today

Output if no missed sessions:
```
Last recorded session date: 2026-11-05
Today:                      2026-11-05
Missed sessions:            0  ✓
```

Output if sessions missed:
```
⚠ MISSED_RUN detected: 2 session(s) skipped:
  - 2026-11-06
  - 2026-11-07

Recovery options (do NOT auto-mark as PROSPECTIVE):
  1. Manually backfill DailyPrice for missed dates: ...
  2. Re-run shadow for each missed date: ...
```

---

## Recovery Procedure

### Step 1: Detect missed sessions

```bash
python3 scripts/hybrid_shadow_cron.py --check-missed
```

### Step 2: Backfill DailyPrice for missed dates

```bash
python3 scripts/backfill_daily_prices.py --execute
```
This automatically detects and fills any missing dates (coverage-aware: checks >= 1,000 non-0050 stocks).

### Step 3: Re-run shadow for each missed date

```bash
python3 scripts/run_hybrid_forward_shadow.py --date YYYY-MM-DD
```
Repeat for each missed trading day.

### Step 4: Verify decision classification

```sql
SELECT trade_date, capture_classification, COUNT(*)
FROM hybrid_forward_decision
WHERE trade_date >= '2026-11-05'
GROUP BY trade_date, capture_classification
ORDER BY trade_date;
```

---

## Decision Classification After Missed Run

| Scenario | Decision Classification | Research Value |
|----------|------------------------|----------------|
| Captured same day as trade_date | `PROSPECTIVE` | ✅ Full OOS value |
| Captured 1 trading day after trade_date | `PROSPECTIVE` | ✅ Full OOS value (within MAX_PROSPECTIVE_CAPTURE_DAYS=1) |
| Captured 2+ trading days after trade_date | `LATE_CAPTURE` | ⚠️ Acceptable — minor timing delay |
| trade_date < 2026-11-05 | `RETROSPECTIVE_RECONSTRUCTION` | ℹ️ Historical only |
| input_data_as_of < trade_date | `INVALID_DATA` | 🛑 BUG |

**Missed run captured the next day = still PROSPECTIVE** (if 1 trading day gap).  
**Missed run captured 2+ days later = LATE_CAPTURE** (not ideal but transparent).

---

## Rules That Cannot Be Broken

1. **Never retroactively mark decisions as PROSPECTIVE** to inflate the OOS evidence pool.
2. **Never modify existing decisions** — the table is append-only.
3. **DailyPrice backfill for missed dates is safe** — it only adds data, never modifies existing rows.
4. **Classification is computed automatically** by `classify_capture()` from the actual `captured_at` timestamp — no manual override.

---

## Alternative: launchd (More Reliable Than cron)

macOS `launchd` with `RunAtLoad + StartCalendarInterval` will run a missed job on wakeup. This is more reliable than cron for laptops.

**This requires separate approval before implementation.** Do not switch without explicit authorization.

Example `launchd` plist (for reference only — do NOT deploy without approval):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.antigravity.hybrid-shadow-cron</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Library/Frameworks/Python.framework/Versions/3.13/bin/python3</string>
        <string>/Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py</string>
        <string>--execute</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>16</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform</string>
</dict>
</plist>
```

**Advantages over cron:**
- Runs missed jobs after Mac wakeup (within same calendar day)
- Native macOS integration
- No Full Disk Access issues

**Disadvantages:**
- Different management interface (`launchctl` vs `crontab`)
- Requires separate approval

---

## Current Mitigation (cron)

Until launchd is approved, mitigate missed runs by:

1. Keep Mac awake at 16:00 Taiwan time (Mon–Fri)
2. Run `--check-missed` on Monday mornings to catch Friday/weekend gaps
3. Manual recovery as described above when gaps detected
4. All late captures are transparently labeled (`LATE_CAPTURE`) — no data integrity risk

---

## Monitoring Schedule

| When | Command |
|------|---------|
| Every Monday | `python3 scripts/hybrid_shadow_cron.py --check-missed` |
| After Mac sleep/restart | `python3 scripts/hybrid_shadow_cron.py --check-missed` |
| Weekly | `python3 scripts/hybrid_shadow_cron.py --status` |
