# Session 71F — Next Cron Acceptance Plan (Nov 12)

**Date**: 2026-11-11  
**Next Opportunity**: 2026-11-12 16:00 CST  
**Authorization**: STRICT_READ_ONLY / DESIGN_ONLY

---

## 1. Objective

Execute H3 Scheduled Runtime Acceptance on the first available natural cron fire after RC-2 deployment. This is the minimum required to close H3.

---

## 2. Pre-Conditions

| Check | Requirement | How to Verify |
|---|---|---|
| Trading day | 2026-11-12 must be a Taiwan trading day | `python3 -c "from src.research.taiwan_trading_calendar import TaiwanTradingCalendar; c=TaiwanTradingCalendar(); print(c.is_trading_day('2026-11-12'))"` |
| Machine awake | Must be awake at 16:00:00 CST | Active use or external alarm |
| No lock file from prior run | `data/.cron.lock` PID must be dead or absent | `cat data/.cron.lock && kill -0 <PID>` |
| RC-2 script unchanged | Hash must still be `4eb6eacf...` | `shasum -a 256 scripts/backfill_daily_prices.py` |
| Log baseline captured | Know log size before run | `wc -l logs/hybrid_cron.log && ls -la logs/hybrid_cron.log` |

---

## 3. Machine Awake Strategy (Option A — cron)

**Required**: The machine must be in full user-space (awake, display on, or active process) at **16:00:00 CST** on 2026-11-12.

Options to prevent sleep:
1. **Active use**: Simply be using the machine at 16:00 CST
2. **Keep screen active**: Any keyboard/mouse activity before 16:00 resets sleep timer
3. **Terminal session**: Running a terminal command (e.g., `watch date`) keeps user session active

The user should NOT rely on:
- DarkWake events (they don't fire cron)
- Setting an alarm that plays sound (audio doesn't prevent sleep)

The simplest approach: **be at the machine at 15:55 CST and keep active until 16:05 CST**.

---

## 4. Monitoring Procedure

```bash
# Step 1: Before 16:00 CST — capture baseline
wc -l logs/hybrid_cron.log
# → Record this number (e.g. 106)

ls -la logs/hybrid_cron.log
# → Record timestamp (should be "Nov 10 17:37" from last run)

# Step 2: At 16:00:00 CST — cron fires
# Wait 30 seconds for the script to start

# Step 3: After 16:00:30 CST — check for trigger
grep "\[2026-11-12" logs/hybrid_cron.log
# → Should show first log entry if cron fired

# Step 4: Wait for completion (script takes 1-20 minutes depending on QG retries)
# Monitor new log entries:
tail -f logs/hybrid_cron.log
# Press Ctrl-C once you see "COMPLETED" or "BLOCKED_STALE_DATA"
```

---

## 5. Post-Execution Verification Checklist

### 5A. Cron Trigger Verification

```bash
# All Nov 12 entries
grep "\[2026-11-12" logs/hybrid_cron.log

# First entry timestamp (cron fire time)
grep "\[2026-11-12" logs/hybrid_cron.log | head -1
# Expected: within seconds of 16:00:00 CST (UTC 08:00)

# Final status
grep "\[2026-11-12" logs/hybrid_cron.log | grep -E "COMPLETED|BLOCKED|ERROR"
```

### 5B. RC-2 Filter Verification

```bash
# If SQLite was written, check filter compliance:
python3 << 'EOF'
import sqlite3
con = sqlite3.connect("file:data/platform.db?mode=ro", uri=True)
c = con.cursor()

# New rows after Nov 05 baseline
c.execute("SELECT COUNT(*), MAX(date) FROM daily_prices WHERE date > '2026-11-05'")
new_total, new_max = c.fetchone()
print(f"New rows: {new_total}, Max date: {new_max}")

# RC-2 filter check: no len>4 IDs in new rows
c.execute("""
  SELECT stock_id, COUNT(*) 
  FROM daily_prices 
  WHERE date > '2026-11-05' AND LENGTH(stock_id) > 4
  GROUP BY stock_id
  LIMIT 10
""")
suspicious = c.fetchall()
print(f"RC-2 contamination: {suspicious}")

# Total row count
c.execute("SELECT COUNT(*) FROM daily_prices")
print(f"Total rows: {c.fetchone()[0]}")
con.close()
EOF
```

### 5C. Quality Gate Outcome

```bash
# QG result
grep "\[2026-11-12" logs/hybrid_cron.log | grep -E "api_date|quality_gate|QG|PASS|FAIL|BLOCKED"
```

Expected outcomes:
- **QG PASS**: SQLite updated with new rows; `COMPLETED` in final log line
- **QG FAIL**: SQLite unchanged; `BLOCKED_STALE_DATA` in final log line (acceptable — data lag from TWSE)

Both outcomes are **acceptable for H3** — what matters is that cron fired naturally with RC-2.

---

## 6. H3 Acceptance Decision Matrix

| Condition | H3 Decision |
|---|---|
| Cron fired at 16:00 CST ± 1 min | H3 passes trigger check ✓ |
| Script completed (any outcome) | H3 passes execution check ✓ |
| RC-2 hash unchanged (`4eb6eacf...`) | H3 passes version check ✓ |
| No `len(stock_id) > 4` in new rows (or 0 new rows) | H3 passes filter check ✓ |
| Neon unchanged | H3 passes production isolation ✓ |
| **All above** | **H3 = `ACCEPTED`** |
| Cron fires but runtime crashes | H3 = `H3_PARTIAL` — diagnose crash |
| Cron still doesn't fire | H3 = `H3_PENDING` — escalate to launchd migration |

---

## 7. Escalation Path

| Scenario | Action |
|---|---|
| Nov 12 cron fires naturally | Execute Section 5 checklist → close H3 |
| Nov 12 cron fires BUT H3 PARTIAL | Root cause crash → new session |
| Nov 12 cron misses again | Escalate to launchd migration (Option B authorization required) |
| launchd migration authorized | Execute `session71f_migration_design.md` Phases 1–4 |

---

## 8. Post-H3 Path

Once H3 is accepted:
1. **Consider launchd migration** — to prevent future sleep-miss failures (requires separate authorization)
2. **Pre-RC2 warrant data cleanup** — 111,710 rows with `len(stock_id) > 4` in SQLite (requires separate authorization)
3. **Session 72 planning** — user must explicitly authorize

---

## 9. Nov 12 Trading Day Confirmation

```bash
# Verify before 16:00 on Nov 12
python3 -c "
from src.research.taiwan_trading_calendar import TaiwanTradingCalendar
c = TaiwanTradingCalendar()
print('Nov 12 trading day:', c.is_trading_day('2026-11-12'))
"
# Expected: True (Wednesday is a standard trading day; no holiday on Nov 12)
```

---

## 10. Plan Summary

| Item | Value |
|---|---|
| Next H3 opportunity | 2026-11-12 16:00:00 CST |
| Machine requirement | Full user-space wake (not DarkWake) |
| Monitoring window | 15:55–16:30 CST |
| Expected duration | 2–20 min (depends on QG retries) |
| Success definition | Cron fires + script runs + RC-2 filter compliant |
| Failure escalation | launchd migration (requires authorization) |
