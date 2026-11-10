# 20D Readiness Matrix — Session 50

**Date:** 2026-11-10  
**Session:** S50 — PART H  
**Overall Verdict:** BLOCKED_PIPELINE  
**AUTH01:** PENDING | **AUTH02:** PENDING

---

## Overview

The 20D Readiness Matrix assesses per-cluster readiness for 20-trading-day outcome calculation. This does NOT compute outcomes — it only assesses what prerequisites are met and what is missing.

---

## Per-Cluster Readiness (Analysis Date: 2026-11-02)

| Fill Date | Corrected 20TD Exit | S46 (Wrong) Exit | Days to Maturity | Is Mature? | Pipeline Data? | Verdict |
|---|---|---|---|---|---|---|
| 2026-10-13 | **2026-11-12** | 2026-11-14 | 10 | No | No | BLOCKED_PIPELINE |
| 2026-10-14 | **2026-11-13** | 2026-11-17 | 11 | No | No | BLOCKED_PIPELINE |
| 2026-10-16 | **2026-11-17** | 2026-11-19 | 15 | No | No | BLOCKED_PIPELINE |
| 2026-10-21 | **2026-11-20** | 2026-11-24 | 18 | No | No | BLOCKED_PIPELINE |
| 2026-10-22 | **2026-11-23** | 2026-11-25 | 21 | No | No | BLOCKED_PIPELINE |
| 2026-10-28 | **2026-11-25** | 2026-12-02 | 23 | No | No | BLOCKED_PIPELINE |

**All 6 clusters: BLOCKED_PIPELINE**

---

## Verdict Precedence Logic

```
if not pipeline_restored:
    → BLOCKED_PIPELINE (overrides all other conditions)
elif not auth01_granted and not strict_now:
    → BLOCKED_AUTH01
elif not is_mature:
    → NOT_YET_MATURE
elif not pipeline_data_available:
    → MATURE_PENDING_DATA
elif auth02_granted:
    → AUTHORIZED_READY
else:
    → DATA_AVAILABLE
```

Pipeline is the most foundational blocker: even if AUTH01 is granted and data is mature, without pipeline restoration there's no exit-price data in the DB.

---

## Nov 12 Hard Deadline

**Oct 13 fill → 20TD exit date: 2026-11-12 (corrected)**

This is the most critical deadline in the entire research program.

| Scenario | Outcome |
|---|---|
| Pipeline restored AND Nov 12 data written to DB by Nov 12 | Oct 13 20D outcome computable after AUTH02 |
| Pipeline NOT restored by Nov 12 | Oct 13 20D exit price NOT in platform.db — permanently unrecoverable from local DB |
| Recovery via Neon DB | Possible in theory, but requires separate authorization |

**Current status (Nov 02):** 10 calendar days until Nov 12. Pipeline has been down since Nov 05.

---

## Critical Path

```
AUTH01 (backfill Oct 29/30/Nov 02/03)
  ↓
Pipeline restoration (Nov 06+ data)
  ↓
Wait for maturity (Oct 13 → Nov 12 earliest, Oct 28 → Nov 25 latest)
  ↓
Confirm exit data in DB (stock_count ≥ 300 for each exit date)
  ↓
AUTH02 (20D computation authorization)
  ↓
Compute 20D outcomes (6 clusters if all pass)
```

---

## 20D vs 5D Guardrail Status

| Guardrail | 5D Status | 20D Status | Notes |
|---|---|---|---|
| G03 (N≥10 clusters) | FAIL (3/10 now, 6/10 after P1) | Same (20D doesn't add clusters) | Need 4+ more weeks |
| G04 (overlap < 30%) | FAIL (5 adjacent pairs) | Worse (longer windows = more overlap) | Structural failure |

20D data does NOT resolve G03 or G04. Even with all 6 clusters' 20D outcomes:
- Statistical verdict: **SIGNIFICANCE_INCONCLUSIVE (unchanged)**
- Activation: **ACTIVATION_BLOCKED (unchanged)**

---

## What 20D Data Would Tell Us

Even though it won't change the activation verdict, 20D data would provide:
1. **Longer holding period characterization**: Does the edge persist beyond 5 days?
2. **Comparison with 5D**: Is the +0.81 pp from 5D consistent or reverting over 20 days?
3. **Additional evidence for future sessions**: 6 data points with ~20D returns

This is research evidence, not a path to activation.

---

## References

- Module: `src/research/calendar_contract_s50.py`
- Function: `build_20d_readiness_matrix()`
- Tests: `tests/test_session50_market_sources.py` TC38–TC39
- Prior: `docs/authorization_20d_readiness_s49.md`
