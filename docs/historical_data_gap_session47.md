# Historical Data Gap Analysis — Session 47

**Date:** 2026-11-09  
**Session:** S47 — PART B (P1)  
**Verdict:** DATA_GAP_CONFIRMED

---

## Summary

The data gap affecting incomplete fill clusters is broader than S46 documented. It is not limited to Nov 02/03 — gaps exist across 11 trading days from Oct 08 through Nov 09.

---

## Full Data Gap Matrix (Oct 08 – Nov 09)

| Date | Day | TD? | DB Stocks | Status | Root Cause | Affected Clusters |
|------|-----|-----|-----------|--------|------------|-------------------|
| 2026-10-08 | Thu | ✓ | 1 | PARTIAL | PIPELINE_SELECTIVE | (pre-v8.0) |
| 2026-10-12 | Mon | ✓ | 655 | COMPLETE | NO_GAP | v6.0 fill |
| 2026-10-13 | Tue | ✓ | 656 | COMPLETE | NO_GAP | Oct 13 fill |
| 2026-10-14 | Wed | ✓ | 656 | COMPLETE | NO_GAP | Oct 14 fill |
| **2026-10-15** | **Thu** | **✓** | **1** | **PARTIAL** | **PIPELINE_SELECTIVE** | Oct 13/14 hold window |
| 2026-10-16 | Fri | ✓ | 655 | COMPLETE | NO_GAP | Oct 16 fill |
| **2026-10-19** | **Mon** | **✓** | **1** | **PARTIAL** | **PIPELINE_SELECTIVE** | Oct 13/14/16 hold window |
| **2026-10-20** | **Tue** | **✓** | **1** | **PARTIAL** | **PIPELINE_SELECTIVE** | Oct 13/14/16 hold window |
| 2026-10-21 | Wed | ✓ | 655 | COMPLETE | NO_GAP | Oct 21 fill |
| 2026-10-22 | Thu | ✓ | 655 | COMPLETE | NO_GAP | Oct 22 fill |
| **2026-10-27** | **Tue** | **✓** | **1** | **PARTIAL** | **PIPELINE_SELECTIVE** | Oct 16/21/22 hold window |
| 2026-10-28 | Wed | ✓ | 656 | COMPLETE | NO_GAP | Oct 28 fill |
| **2026-10-29** | **Thu** | **✓** | **1** | **PARTIAL** | **PIPELINE_SELECTIVE** | Oct 21/22/28 hold window |
| **2026-10-30** | **Fri** | **✓** | **1** | **PARTIAL** | **SCHEDULER_NOT_TRIGGERED** | Oct 21/22 hold window |
| **2026-11-02** | **Mon** | **✓** | **1** | **PARTIAL** | **SCHEDULER_NOT_TRIGGERED** | Oct 22/28 hold window |
| **2026-11-03** | **Tue** | **✓** | **1** | **PARTIAL** | **SCHEDULER_NOT_TRIGGERED** | Oct 28 hold window |
| 2026-11-04 | Wed | ✓ | 6,957 | COMPLETE | MANUAL_BACKFILL | Oct 28 exit |
| 2026-11-05 | Thu | ✓ | 6,589 | COMPLETE | MANUAL_BACKFILL | — |
| **2026-11-06** | **Fri** | **✓** | **0** | **MISSING** | **QUALITY_GATE_FAIL** | — |
| **2026-11-09** | **Mon** | **✓** | **0** | **MISSING** | **PROVIDER_NOT_READY** | — |

**Oct 23–26, Oct 31, Nov 01:** NOT trading days (holiday cluster / weekend). Confirmed by TaiwanTradingCalendar.

---

## Gap Categories

| Category | Count | Dates |
|---|---|---|
| COMPLETE (normal pipeline) | 7 | Oct 12/13/14/16/21/22/28 |
| COMPLETE (manual backfill) | 2 | Nov 04/05 |
| PARTIAL_COVERAGE (1 stock, 0050 only) | 9 | Oct 08/15/19/20/27/29/30, Nov 02/03 |
| DATE_MISSING (0 stocks) | 2 | Nov 06/09 |
| NOT_TRADING | 12+ | Weekends + holidays |

---

## Root Cause Analysis

### PIPELINE_SELECTIVE (Oct 08, 15, 19, 20, 27, 29)

**Finding (NEW vs S46):** The pipeline only captured daily prices on dates that are execution_dates (fill dates) of forward signals. Intermediate trading days between fills were never captured.

Evidence:
- Complete dates (655-656 stocks) = exactly the fill dates: Oct 12, 13, 14, 16, 21, 22, 28
- Intermediate dates (1 stock = 0050 only) = all trading days between fills
- This is a pre-existing structural gap, not caused by any recent scheduler failure
- These dates cannot be recovered without an external historical data source

### SCHEDULER_NOT_TRIGGERED (Oct 30, Nov 02, Nov 03)

The cron was not running Nov 02–08. First confirmed cron entry: `2026-11-09T08:00:17Z`. Oct 30 is also affected because the cron was not yet installed/running at that point.

### QUALITY_GATE_FAIL (Nov 06)

Cron ran on Nov 09 and attempted to backfill Nov 06. Quality gate rejected the data. Specific QG check that failed not definitively identified from logs.

### PROVIDER_NOT_READY (Nov 09)

TWSE API returned `api_date=2026-11-06` for all 4 Nov 09 attempts. Status: BLOCKED_STALE_DATA.

---

## Impact on Cluster Eligibility

The `_count_exit_days` proxy (TSMC presence after fill date) determines "COMPLETE" status:

| Fill Date | TSMC-present dates counted | Proxy count | Required | Status |
|---|---|---|---|---|
| Oct 13 | Oct 14, 16, 21, 22, 28, Nov 04, Nov 05 | 7 | 5 | COMPLETE ✓ |
| Oct 14 | Oct 16, 21, 22, 28, Nov 04, Nov 05 | 6 | 5 | COMPLETE ✓ |
| Oct 16 | Oct 21, 22, 28, Nov 04, Nov 05 | 5 | 5 | COMPLETE ✓ |
| Oct 21 | Oct 22, 28, Nov 04, Nov 05 | 4 | 5 | INCOMPLETE ✗ |
| Oct 22 | Oct 28, Nov 04, Nov 05 | 3 | 5 | INCOMPLETE ✗ |
| Oct 28 | Nov 04, Nov 05 | 2 | 5 | INCOMPLETE ✗ |

**Key limitation:** The proxy doesn't count Oct 15, 19, 20, 27 because TSMC is not in the DB for those dates. So the strict baseline clusters' "COMPLETE" status is based on TSMC-proxy-available dates, not consecutive calendar trading days. The actual 5th calendar TD for Oct 13/14/16 fills is Oct 20/21/27 (see PART E for details).

---

## Recovery Verdict

**RECOVERY_BLOCKED** for all 11 gap dates.

- **Older gaps (Oct 15, 19, 20, 27, 29):** No local data cache; never captured. Recovery requires authorized production backfill with TWSE historical data API.
- **Oct 30, Nov 02, Nov 03:** Cron was not running; data not captured. Recovery requires authorized manual backfill.
- **Nov 06:** Quality gate blocked. Root cause unknown; recovery requires investigation.
- **Nov 09:** Provider not ready; recovery expected once TWSE publishes.

**Next action:** Pipeline restoration plan (see `extended_workflow_session46.md` AI-1 and AI-2).
