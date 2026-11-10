# Research Trading Calendar Contract (SSOT) — Session 50

**Date:** 2026-11-10  
**Session:** S50 — PART E  
**Module:** `src/research/calendar_contract_s50.py`  
**Version:** S50 SSOT (supersedes S48/S49 duplicates)

---

## Overview

This document records the consolidation of the Research Trading Calendar Contract into a single source of truth (SSOT). Previously, `_CORRECT_5TD` and `_CORRECT_20TD` were duplicated across two frozen modules. The S50 SSOT module is now the authoritative reference.

---

## Consolidation History

| Session | Module | Role |
|---|---|---|
| S46 | `prospective_comparison_s46.py` | Original dates — **ERRONEOUS** (3/6 5TD wrong, 6/6 20TD wrong) |
| S48 | `calendar_contract_s48.py` | First corrections introduced — **FROZEN** |
| S49 | `pipeline_recovery_s49.py` | Duplicate overlay — **FROZEN** |
| **S50** | `calendar_contract_s50.py` | **SINGLE SSOT** — this module |

**Rule:** Neither S48 nor S49 modules are modified. S50 is the SSOT. New callers MUST use `get_corrected_exit()` from S50.

---

## Authoritative Exit Dates

### 5TD Exit Dates

| Fill Date | S46 (ERRONEOUS) | Corrected (S50 SSOT) | Error? | Calendar Δ |
|---|---|---|---|---|
| 2026-10-13 | 2026-10-21 | **2026-10-20** | ✓ WRONG | -1 TD |
| 2026-10-14 | 2026-10-28 | **2026-10-21** | ✓ WRONG | -5 TD |
| 2026-10-16 | 2026-11-05 | **2026-10-27** | ✓ WRONG | -7 TD |
| 2026-10-21 | 2026-10-30 | 2026-10-30 | correct | 0 |
| 2026-10-22 | 2026-11-02 | 2026-11-02 | correct | 0 |
| 2026-10-28 | 2026-11-04 | 2026-11-04 | correct | 0 |

**S46 5TD error rate: 3/6 (50%)**

### 20TD Exit Dates

| Fill Date | S46 (ERRONEOUS) | Corrected (S50 SSOT) | Calendar Δ |
|---|---|---|---|
| 2026-10-13 | 2026-11-14 | **2026-11-12** | -2d |
| 2026-10-14 | 2026-11-17 | **2026-11-13** | -4d |
| 2026-10-16 | 2026-11-19 | **2026-11-17** | -2d |
| 2026-10-21 | 2026-11-24 | **2026-11-20** | -4d |
| 2026-10-22 | 2026-11-25 | **2026-11-23** | -2d |
| 2026-10-28 | 2026-12-02 | **2026-11-25** | -7d |

**S46 20TD error rate: 6/6 (100%) — all S46 dates were too late**

---

## Impact of S46 Errors

Using S46's erroneous 20TD dates would:
- Classify Oct 13 outcome as "not mature" until Nov 14 (instead of Nov 12)
- Effectively push the entire evaluation window 2–7 days later than the actual market exit
- If researchers waited until S46's Nov 14 date to look at Oct 13's outcome, they might be looking at the wrong price point

This is why all analysis must use `get_corrected_exit()` from this module.

---

## Why prospective_comparison_s46.py Was Not Modified

The S46 module contains the original research lineage. Modifying it would:
1. Break research reproducibility for the S46 analysis record
2. Change the behavior of any tests that explicitly test for the erroneous S46 values (as historical documentation)
3. Require re-running the entire S46 comparison with corrected dates (which requires a separate authorization)

The overlay approach (S50 SSOT) is the correct path forward.

---

## 5TD Window Map

| Fill | TD1 | TD2 | TD3 | TD4 | TD5 (exit) |
|---|---|---|---|---|---|
| Oct 13 | Oct 14 | Oct 15 | Oct 16 | Oct 19 | **Oct 20** |
| Oct 14 | Oct 15 | Oct 16 | Oct 19 | Oct 20 | **Oct 21** |
| Oct 16 | Oct 19 | Oct 20 | Oct 21 | Oct 22 | **Oct 27** |
| Oct 21 | Oct 22 | Oct 23 | Oct 26 | Oct 27 | **Oct 28** |
| Oct 22 | Oct 23 | Oct 26 | Oct 27 | Oct 28 | **Nov 02** |
| Oct 28 | Oct 29 | Oct 30 | Nov 02 | Nov 03 | **Nov 04** |

Note: The apparent jump from Oct 22→Oct 27 for Oct 16, and from Oct 28→Nov 02 for Oct 22, reflects Taiwan trading calendar holidays (Oct 23/26 are non-trading days per TradingCalendarService).

---

## Usage

```python
from src.research.calendar_contract_s50 import get_corrected_exit

exit_5td = get_corrected_exit("2026-10-13", "5TD")   # → "2026-10-20"
exit_20td = get_corrected_exit("2026-10-13", "20TD")  # → "2026-11-12"
```

---

## References

- Module: `src/research/calendar_contract_s50.py`
- Function: `build_research_trading_calendar_contract()`, `get_corrected_exit()`
- Tests: `tests/test_session50_market_sources.py` TC16–TC24
- Prior: `docs/calendar_contract_integration_s49.md`
