# 20D Calendar Contract Integration — Session 49

**Date:** 2026-11-09  
**Session:** S49 — PART E (P4)  
**Verdict:** 6/6 20TD corrected; 3/6 5TD corrected; S46 NOT modified

---

## Overview

`prospective_comparison_s46.py` contains hardcoded `_CALENDAR_5TD` and `_CALENDAR_20TD` values that have errors. This module (`pipeline_recovery_s49.py`) provides corrected values as an overlay without modifying the original S46 file.

**Rule:** Any caller needing calendar exit dates should use `get_corrected_calendar_exit()` from `pipeline_recovery_s49.py` or `build_calendar_contract_integration()` instead of `_CALENDAR_5TD`/`_CALENDAR_20TD` from `prospective_comparison_s46.py`.

---

## Correction Summary

### 5D Corrections (3/6 corrected)

| Fill Date | S46 Value | Correct Value | Status | Δ (days) |
|---|---|---|---|---|
| 2026-10-13 | 2026-10-21 | **2026-10-20** | CORRECTED | -1 |
| 2026-10-14 | 2026-10-28 | **2026-10-21** | CORRECTED | -7 |
| 2026-10-16 | 2026-11-05 | **2026-10-27** | CORRECTED | -9 |
| 2026-10-21 | 2026-10-30 | 2026-10-30 | UNCHANGED | 0 |
| 2026-10-22 | 2026-11-02 | 2026-11-02 | UNCHANGED | 0 |
| 2026-10-28 | 2026-11-04 | 2026-11-04 | UNCHANGED | 0 |

### 20D Corrections (6/6 corrected)

| Fill Date | S46 Value | Correct Value | Status | Δ (days) |
|---|---|---|---|---|
| 2026-10-13 | 2026-11-14 | **2026-11-12** | CORRECTED | -2 |
| 2026-10-14 | 2026-11-17 | **2026-11-13** | CORRECTED | -4 |
| 2026-10-16 | 2026-11-19 | **2026-11-17** | CORRECTED | -2 |
| 2026-10-21 | 2026-11-24 | **2026-11-20** | CORRECTED | -4 |
| 2026-10-22 | 2026-11-25 | **2026-11-23** | CORRECTED | -2 |
| 2026-10-28 | 2026-12-02 | **2026-11-25** | CORRECTED | -7 |

**Key observation:** All corrections are negative (S46 dates were 2–7 days too late). Root cause: S46 used TSMC-proxy date counting instead of real `TaiwanTradingCalendar.next_trading_day()` iteration.

---

## Impact on Research

### On 5D Baseline (Frozen at +0.81%)
- **NO IMPACT.** The frozen baseline deltas were computed from actual historical prices, not from the erroneous calendar dates.
- The 5D corrections affect future computations only.

### On 20D Maturity Timeline
- S46 said earliest exit: Nov 14 → Correct: **Nov 12** (2 days earlier)
- S46 said latest exit: Dec 02 → Correct: **Nov 25** (7 days earlier)
- If pipeline is restored, Oct 13 fill's 20D outcome could be computable as early as **Nov 12** (3 trading days from today)

---

## Usage

```python
from src.research.pipeline_recovery_s49 import (
    get_corrected_calendar_exit,
    build_calendar_contract_integration,
)

# Get corrected 5D exit for Oct 13 fill
exit_5d = get_corrected_calendar_exit("2026-10-13", 5)   # → "2026-10-20"

# Get corrected 20D exit for Oct 13 fill
exit_20d = get_corrected_calendar_exit("2026-10-13", 20)  # → "2026-11-12"

# Full correction records
integration = build_calendar_contract_integration()
print(f"S46 had {integration.s46_20td_error_count}/6 20TD errors")
```

---

## S46 Original Module (Unchanged)

`src/research/prospective_comparison_s46.py` was **NOT modified** in S49.

The erroneous values remain in the original file:
- `_CALENDAR_5TD` (line 146): has 3 incorrect values (Oct 13/14/16)
- `_CALENDAR_20TD` (line 336): has 6 incorrect values (all fills)

**Reason not modified:** Modifying S46 changes the file hash and would require re-verifying the full S46 research lineage. The calendar contract integration overlay is the safer approach for now. A future session may formally authorize the S46 correction.
