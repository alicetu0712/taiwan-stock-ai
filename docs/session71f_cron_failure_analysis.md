# Session 71F — Cron Failure Analysis

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / SCHEDULER_FORENSICS

---

## 1. Failure Summary

| Item | Value |
|---|---|
| Scheduled fire | 2026-11-11 16:00 CST |
| Actual execution | NONE |
| Classification | `MISSED_DUE_TO_SLEEP` |
| Root cause | Machine in deep sleep (hibernate mode 3) at scheduled fire time |
| Evidence quality | `SLEEP_CONFIRMED` |

---

## 2. Failure Mechanism

```
Cron daemon flow:
  crontab line: 0 16 * * 1-5 → evaluates at 16:00:00 CST
  
  At 16:00:00 CST:
    - CPU was in deep sleep (hibernate mode 3)
    - /usr/sbin/cron (vixie-cron) DID NOT receive the wake signal
    - Scheduled job was SILENTLY DROPPED
    - No log entry written (stdout/stderr redirect never reached)
    
  At 16:01:09 CST:
    - DarkWake from SleepService (2 seconds)
    - User space NOT activated
    - Cron daemon evaluated: 16:00 minute already passed → NOT fired
    - Machine returned to sleep
```

**Key behavior**: Vixie-cron on macOS evaluates the schedule table every minute when awake. If the machine wakes after the scheduled minute, cron does **not** retroactively fire missed jobs.

---

## 3. Root Cause Ladder

| Level | Cause | Classification |
|---|---|---|
| Immediate | Machine asleep at 16:00:00 CST | `SLEEP_AT_FIRE_TIME` |
| Underlying | Running on battery with hibmode=3; standbydelay=0 | `AGGRESSIVE_SLEEP_POLICY` |
| Structural | macOS cron cannot wake from sleep; no catch-up | `SCHEDULER_LIMITATION` |
| Contributing | No `caffeinate` / `pmset schedule` for 16:00 window | `NO_WAKE_GUARD` |

---

## 4. Elimination of Other Hypotheses

| Hypothesis | Status | Evidence |
|---|---|---|
| Cron daemon not running | **RULED OUT** | PID 20488 confirmed running |
| Crontab misconfiguration | **RULED OUT** | `0 16 * * 1-5` verified correct; path verified |
| Stale lock file | **RULED OUT** | PID 91460 dead; flock advisory = freed at process death |
| Non-trading day | **RULED OUT** | 2026-11-11 is_trading_day=True; Remembrance Day is not in TWSE calendar |
| Script import error | **RULED OUT** | Would appear via `2>&1` redirect; log unchanged → no stderr |
| Quality Gate pre-emption | **RULED OUT** | QG only runs after cron fires; cron never fired |
| Calendar check pre-emption | **RULED OUT** | Calendar check runs after cron fires |
| Machine not waking in time window | **CONFIRMED** | SLEEP_CONFIRMED; all wakes were DarkWake |

---

## 5. Historical Pattern

| Date | Outcome | Failure Cause |
|---|---|---|
| 2026-11-10 16:00 | BLOCKED_STALE_DATA | Cron fired; QG FAIL (api_date lag) |
| 2026-11-11 16:00 | CRON_TRIGGER_NOT_OBSERVED | Machine sleeping → MISSED_DUE_TO_SLEEP |

This is the **first confirmed sleep-caused miss** in the RC-2 era. Prior failures (Nov 10 and earlier) involved the cron firing but failing at Quality Gate stage.

---

## 6. Impact Assessment

| Item | Impact |
|---|---|
| SQLite data freshness | Still at 2026-11-05 (5 trading days behind as of Nov 11) |
| RC-2 runtime validation | FILTER_EFFECT_UNVERIFIED — no runtime execution occurred |
| H3 acceptance | H3_PENDING — requires natural execution |
| Data quality | No corruption risk — zero writes occurred |
| Neon / production | ZERO IMPACT — cron never touches Neon |

---

## 7. Recurrence Risk

Without remediation, this failure pattern will repeat whenever:
1. The machine is on battery power
2. The user has not interacted with the machine for >15 minutes before 16:00 CST
3. No external alarm/caffeinate guard is in place

Given that `standbydelaylow=0` and `hibmode=3`, aggressive sleep is the default behavior on this machine.

**Estimated recurrence frequency**: HIGH — any afternoon session where machine is left unattended before 16:00 CST.

---

## 8. Verdict

| Classification | Value |
|---|---|
| **Failure type** | `MISSED_DUE_TO_SLEEP` |
| **Scheduler behavior** | `SCHEDULER_LIMITATION_CONFIRMED` |
| **Data safety** | `NO_CORRUPTION_RISK` |
| **Remediation required** | YES — sleep guard OR scheduler migration |
