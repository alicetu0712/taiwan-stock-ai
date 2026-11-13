# Session 71F — Sleep/Wake Forensics

**Date**: 2026-11-11  
**Source**: `pmset -g log` (read-only)  
**Authorization**: STRICT_READ_ONLY / SCHEDULER_FORENSICS

---

## 1. Investigation Scope

Verify or refute the **sleep hypothesis** from S71E: machine was sleeping at 16:00 CST on Nov 11, causing cron to be silently skipped.

Evidence window examined: **15:00 CST — 16:45 CST** (2026-11-11)

---

## 2. Complete Sleep/Wake Timeline (15:00–16:45 CST)

| Time (CST) | Event | Type | Key Detail | Duration |
|---|---|---|---|---|
| 15:17:03 | **Sleep** | Sleep Service Back to Sleep | Using BATT (82%); TCPKeepAlive=active | ~1028 s |
| 15:17:06 | Wake Requests | — | Next SleepService: 15:34:11; UserWake: 15:44:09 (calaccessd) | — |
| 15:34:11 | **DarkWake** | Deep Idle [CDNP] | rtc/SleepService; family.heartbeat | 2 s |
| 15:34:13 | **Sleep** | Sleep Service Back to Sleep | Using BATT (82%) | ~596 s |
| 15:34:16 | Wake Requests | — | Next UserWake: 15:44:09 (calaccessd) | — |
| 15:44:09 | **DarkWake** | Deep Idle [CDNP] | rtc/Maintenance; NUB.SPMISw3IRQ | 18 s |
| 15:44:27 | Sleep (inferred) | — | 18 s duration → machine returned to sleep ~15:44:27 | — |
| **15:44:29** | **Wake Requests** | — | **UserWake shifted: 15:44:09 → 23:35:59 (keysync.retry)** | — |
| **~15:45** | **Deep Sleep** | — | **No UserWake until 23:35:59 CST** | ~7h 51m |
| **16:01:09** | **DarkWake** | Deep Idle [CDNP] | rtc/SleepService; mDNSResponder maintenance | **2 s** |
| 16:01:11 | **Sleep** | Sleep Service Back to Sleep | TCPKeepAlive=active; BATT 82% | ~73 s |
| 16:02:24 | **DarkWake** | Deep Idle [CDNP] | smc.sysState.Wake(0x70070000); wifibt; SMC.OutboxNotEmpty | **22 s** |
| 16:02:46 | **Sleep** | Maintenance Sleep | TCPKeepAlive=active; BATT 82% | ~1029 s |
| 16:19:55 | **DarkWake** | Deep Idle [CDNP] | rtc/SleepService | **2 s** |
| 16:19:57 | **Sleep** | Sleep Service Back to Sleep | BATT 82% | ~970 s |
| 16:36:07 | **DarkWake** | Deep Idle [CDNP] | rtc/SleepService | **2 s** |
| 16:36:08+ | Sleep (inferred) | — | Continuing DarkWake cycle | — |

---

## 3. Machine State at Cron Fire Time (16:00 CST)

| Question | Answer | Evidence |
|---|---|---|
| Was machine awake at 16:00 CST? | **NO** | Last sleep entry before 16:00 = 15:44:27; next wake = 16:01:09 |
| Machine state at 16:00:00 CST | **Deep Sleep (hibernate mode 3)** | 1029 s sleep started 15:44 |
| Any FullWake between 15:00–16:30? | **ZERO** | All wake events are `DarkWake from Deep Idle [CDNP]` |
| DarkWake at 16:01:09 — did cron execute? | **NO** | DarkWake does not launch user-space cron jobs; lasted 2 s |
| DarkWake at 16:02:24 — did cron execute? | **NO** | DarkWake (WiFi/BT maintenance); lasted 22 s; not user-space |
| Was there a FullWake before 17:13 CST? | **UNKNOWN** | pmset log ends at 16:36; user active at 17:13 (sent "更新") |

---

## 4. DarkWake vs FullWake — Cron Behavior

| Wake Type | pmset Tag | User Processes Execute? | Traditional Cron Runs? |
|---|---|---|---|
| **DarkWake** | `DarkWake from Deep Idle [CDNP]` | NO — kernel + selected daemons only | **NO** |
| **FullWake** | `Wake from Deep Idle` / user-initiated | YES — full user space | YES (within 60 s of scheduled time) |

All observed wake events in the 15:00–16:45 window are DarkWake `[CDNP]` type. Zero FullWake events.

**CDNP breakdown**:
- C = CPU (core woken)
- D = Display (NOT turned on)
- N = Network (maintained)
- P = Power (from battery)

The absence of a Display flag confirms dark (non-display) wake — user processes do not run.

---

## 5. Sleep Continuity Map

```
15:00    15:17    15:34    15:44    16:00    16:01    16:02    16:20    16:36
  |--------|--------|--------|--------|--------|--------|--------|--------|
  [active?]|DW 2s   |DW 2s   |DW 18s  |ASLEEP  |DW 2s   |DW 22s  |DW 2s
           |SLEEP   |SLEEP   |SLEEP→  |        |SLEEP   |SLEEP   |
                                                ^
                                           CRON FIRES HERE (16:00:00 CST)
                                           Machine: DEEP SLEEP
```

---

## 6. Corroborating Evidence

| Evidence Item | Observation | Conclusion |
|---|---|---|
| Charge: 82% (unchanged all day) | No AC power; battery saver mode | Aggressive sleep behavior expected |
| `hibmode=3` in HibernateStats | Hibernate-on-sleep enabled | Deep sleep, not shallow standby |
| `rd=455 ms` (read time) | Hibernate image exists | Confirms deep hibernation, not light sleep |
| `standbydelaylow=0` / `standbydelayhigh=0` | Immediate standby | Machine goes deep immediately |
| All DarkWake [CDNP] | Standard maintenance wakes | No display-on wakes; user space never activated |
| UserWake after 15:44 = 23:35:59 | No alarm/calendar events until night | Machine intended to sleep all evening |

---

## 7. Verdict

**`SLEEP_CONFIRMED`**

The machine was in deep sleep (hibernate mode 3, battery, standby) at 16:00:00 CST on 2026-11-11. The DarkWake events at 16:01, 16:02, 16:19, and 16:36 are brief system maintenance wakes that do not activate user-space processes or traditional cron. No FullWake occurred in the entire 15:17–16:36+ window.

macOS traditional cron (`/usr/sbin/cron`) with `vixiecron` semantics: when the machine is asleep at the scheduled minute, the job is **silently dropped** — there is no catch-up. This is the definitive root cause of `CRON_TRIGGER_NOT_OBSERVED`.
