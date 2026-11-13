# Session 71G — Catch-up Safety Policy

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / MIGRATION_DESIGN_ONLY  
**Note**: Policy design only — user must choose between Option A (Strict) and Option B (Controlled Catch-up)

---

## 1. The Catch-up Problem

Traditional cron: fires exactly at scheduled time or is silently dropped. No catch-up.

launchd `StartCalendarInterval`: when machine was asleep, fires within a grace window after the machine wakes (full user session required for LaunchAgent).

This introduces new scenarios that require explicit policy:

| Scenario | Cron | LaunchD (no policy) | Risk |
|---|---|---|---|
| Machine awake at 16:00 | Fires ✓ | Fires ✓ | None |
| Machine sleeps at 16:00, wakes 16:30 | MISSED | Fires ~16:30 | LOW — data still fresh |
| Machine sleeps at 16:00, wakes 22:00 | MISSED | Fires ~22:00 | MEDIUM — late execution |
| Machine sleeps, wakes next day 09:00 | MISSED | Fires ~09:00 (next day!) | HIGH — wrong `date.today()` |
| Machine never wakes that day | MISSED | MISSED (no catch-up) | Same as cron |

---

## 2. Script-Level Time Guards (Already Present)

The script already has the following built-in guards:

```python
# Step 2: Calendar check
if not CALENDAR.is_trading_day(today): return SKIPPED_NON_TRADING_DAY

# Step 3: Data readiness (time >= 15:30 CST)
data_ready = _is_data_ready(now_taiwan)  # True if >= 15:30
# → if execute=True and not ready: logs WARNING but continues
# → backfill QG-5 blocks wrong-date writes (api_date != target)
```

These guards handle:
- Non-trading day: safe skip ✓
- Data not yet published (< 15:30): QG-5 blocks wrong-date writes ✓

What they do NOT handle:
- Catch-up runs at 22:00 CST (data still for today, OK)
- Catch-up runs next day (data for NEXT day, not yesterday) ← NEW RISK

---

## 3. Execution Validity Window Analysis

### Current Date Behavior

The script uses `date.today()` (line 296 of `hybrid_shadow_cron.py`). This date is determined at **run time**, not schedule time.

| Catch-up Fire Time | `date.today()` | TWSE target date | Risk |
|---|---|---|---|
| Nov 11 16:30 CST | Nov 11 | Nov 11 ✓ | None |
| Nov 11 22:00 CST | Nov 11 | Nov 11 ✓ | None — TWSE data available since 15:30 |
| Nov 11 23:59 CST | Nov 11 | Nov 11 ✓ | None |
| Nov 12 00:00 CST | **Nov 12** | Nov 12 (not yet closed!) | Medium — Nov 11 data permanently missed |
| Nov 12 09:00 CST | Nov 12 | Nov 12 (not yet closed!) | Medium — Nov 11 data permanently missed |
| Nov 12 16:30 CST | Nov 12 | Nov 12 ✓ | Correct for Nov 12 |

**Key insight**: Any catch-up that fires before midnight CST is safe (uses `date.today() = Nov 11`). A catch-up that fires after midnight CST will target Nov 12 (not Nov 11), permanently losing Nov 11 data.

---

## 4. Option A — Strict Window

**Definition**: Accept catch-up execution only within a defined window on the same calendar day.

```
Execution Validity Window: 15:30 CST – 23:59 CST (same day)
```

**Implementation**: Add a validity check in `hybrid_shadow_cron.py`:

```python
# PROPOSED GUARD (not authorized — design only)
EXECUTION_DEADLINE_HOUR = 23
EXECUTION_DEADLINE_MINUTE = 59

def _within_validity_window(now_taipei: datetime) -> bool:
    """True if current time is within the same-day execution window."""
    t = now_taipei.time()
    if not _is_data_ready(now_taipei):  # before 15:30
        return False
    if (t.hour, t.minute) > (EXECUTION_DEADLINE_HOUR, EXECUTION_DEADLINE_MINUTE):
        return False
    return True
```

| Attribute | Value |
|---|---|
| Window | 15:30 CST – 23:59 CST |
| Catch-up allowed | YES, same day |
| Cross-day catch-up | BLOCKED |
| Implementation change required | YES — add `_within_validity_window()` check |
| Data loss scenario | Machine never wakes same day → day permanently missed |
| False negative risk | Very low (machine waking at 16:30 on correct day works) |

---

## 5. Option B — Controlled Catch-up Window

**Definition**: Accept catch-up execution within a defined window (e.g., up to 4 hours past schedule), rejecting later runs.

```
Execution Validity Window: 15:30 CST – 20:00 CST (4-hour post-schedule window)
```

**Rationale**: TWSE data is published around 15:30, available through end of day. 4 hours provides generous recovery time while preventing very-late runs.

```python
# PROPOSED GUARD (not authorized — design only)
EXECUTION_DEADLINE_HOUR = 20   # 4 hours after 16:00 schedule
EXECUTION_DEADLINE_MINUTE = 0

def _within_validity_window(now_taipei: datetime) -> bool:
    t = now_taipei.time()
    if not _is_data_ready(now_taipei):
        return False
    if (t.hour, t.minute) > (EXECUTION_DEADLINE_HOUR, EXECUTION_DEADLINE_MINUTE):
        _log(f"[cron] EXPIRED — {t.strftime('%H:%M')} CST past execution deadline {EXECUTION_DEADLINE_HOUR:02d}:{EXECUTION_DEADLINE_MINUTE:02d} — skipping")
        return False
    return True
```

| Attribute | Value |
|---|---|
| Window | 15:30 CST – 20:00 CST |
| Catch-up allowed | YES (up to 4h post-schedule) |
| Cross-day catch-up | BLOCKED (window ends at 20:00) |
| Implementation change required | YES — add deadline check |
| Data loss scenario | Machine wakes after 20:00 → day missed |
| False negative risk | Low — most human-use patterns wake before 20:00 |

---

## 6. Scenario Verification Table

| Scenario | Option A (strict) | Option B (controlled) | Current (no guard) |
|---|---|---|---|
| **15:55 awake** → 16:00 cron | ✓ Fires | ✓ Fires | ✓ Fires |
| **16:00 asleep, 16:30 wake** | ✓ Catch-up at 16:30 | ✓ Catch-up at 16:30 | ✓ Catch-up |
| **16:00 asleep, 22:00 wake** | ✓ Catch-up at 22:00 (same day data) | ✗ BLOCKED (past 20:00) | ✓ Catch-up at 22:00 |
| **16:00 asleep, next day 09:00 wake** | ✗ BLOCKED (next day) | ✗ BLOCKED (next day + past window) | ⚠ Runs with today=next day (wrong target) |
| **Provider api_date stale** | QG-5 blocks write | QG-5 blocks write | QG-5 blocks write |
| **Provider HTTP failure** | backfill exits 0, QG blocks | Same | Same |
| **Duplicate trigger** | FileLock blocks second | FileLock blocks second | FileLock blocks second |
| **Previous job running** | FileLock blocks | FileLock blocks | FileLock blocks |
| **Non-trading day** | Calendar check skips | Calendar check skips | Calendar check skips |
| **Network unavailable** | backfill exits 0, 0 rows inserted | Same | Same |

---

## 7. Without Policy Guard: Current Behavior

The existing script has **no explicit execution validity window**. If launchd fires a catch-up:
- Same day at any time after 15:30: SAFE (data for today)
- Same day before 15:30: `_is_data_ready()` returns False; execute mode warns but QG-5 blocks wrong-date writes → safe
- Next day: runs with `date.today()` = next day → targets next-day data, NOT missed day → data loss for missed day

**Conclusion**: Without a policy guard, same-day catch-up is safe; next-day catch-up permanently loses the missed day.

---

## 8. Policy Recommendation

**Recommended: Option B (Controlled Catch-up Window: 15:30–20:00 CST)**

Rationale:
- Covers the most common catch-up scenarios (machine wakes within 4 hours)
- Prevents the edge case of very late runs where data quality may be uncertain
- Prevents next-day mis-targeting
- More conservative than Option A's 23:59 deadline

**Preconditions for implementation**:
1. User authorization for code change to `hybrid_shadow_cron.py`
2. Add `_within_validity_window()` function and check at Step 3.5
3. Test with time mock before deployment

**Current behavior without guard**:
- Safe for same-day wakes (all times after 15:30)
- Risk for next-day wakes (data loss, no crash)

---

## 9. Catch-up Policy Verdict

| Policy | Verdict | Recommended |
|---|---|---|
| Option A (Strict 23:59) | `SUITABLE_CONSERVATIVE` | No |
| **Option B (Controlled 20:00)** | **`CONTROLLED_CATCHUP_RECOMMENDED`** | **YES** |
| No policy guard | `SUITABLE_WITH_CAVEAT` (same-day safe, next-day risk) | Only as interim |
