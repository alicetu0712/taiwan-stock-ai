# 20D Research Execution Plan — Session 44

**Date:** 2026-11-09  
**Session:** S44  
**Module:** `src/research/execution_plan_20d_s44.py`  
**Status:** DESIGN_ONLY_NOT_AUTHORIZED

---

## Overview

This document records the step-by-step procedure for conducting the 20D outcome analysis when authorized in a future session. It is a design plan only — no computation is performed.

---

## Precondition Status

| ID | Precondition | Status | Blocking Until |
|---|---|---|---|
| P01 | 20D outcome maturity (all target clusters have 20 TDs) | **FAIL** | ~2026-11-24 |
| P02 | Price completeness through outcome_end_date | **FAIL** | ~2026-11-24 |
| P03 | 0050 benchmark price through outcome_end_date | **FAIL** | ~2026-11-24 |
| P04 | Universe verified (v8.0 common stocks) | PASS | Already done |
| P05 | Execution provenance (NEXT_OPEN_SIMULATED) | PASS | Already done |
| P06 | V3 parameter hash = be43e8ca977d9fdd | PASS | Already verified |
| P07 | Research authorization granted for 20D computation | **FAIL** | Future session |

**3/7 PASS. 4/7 FAIL. Earliest eligible execution: ~2026-11-24.**

---

## 12 Execution Steps

| Step | Action |
|---|---|
| E01 | Create read-only DB snapshot; compute dataset fingerprint |
| E02 | Build canonical 5D/20D signal pool (strict fill_date_contract criteria) |
| E03 | Compute per-signal 20D gross return: (exit_close − fill_open) / fill_open |
| E04 | Apply FEES_PCT=0.00585 → net_return |
| E05 | Compute 0050 benchmark return for same fill/exit dates |
| E06 | Aggregate to fill-date cluster means |
| E07 | Compute paired delta per cluster: D_v3[i] − A_direct[i] |
| E08 | Cluster-level t-test on delta vector; 95% CI |
| E09 | Apply statistical guardrails G01–G10 |
| E10 | Generate reproducibility manifest |
| E11 | Write results to stock_research.db ONLY (never platform.db) |
| E12 | Generate evidence quality report and final verdict |

---

## Abort Conditions

| ID | Trigger | Action |
|---|---|---|
| A01 | Any signal's outcome_end_date > MAX(daily_prices.date) | ABORT: Immature outcome |
| A02 | Missing price for any stock on fill_date or outcome_end_date | EXCLUDE signal; if >10% → ABORT |
| A03 | V3 parameter hash ≠ be43e8ca977d9fdd | ABORT: Parameters changed |
| A04 | Any code attempts to write to platform.db | ABORT: Production write detected |
| A05 | Dataset fingerprint at execution ≠ manifest fingerprint | ABORT: Dataset changed |
| A06 | v6.0 contamination in strict pool | EXCLUDE; verify fill_date_contract |

---

## Authorization Items

| ID | Required Action | Current Status |
|---|---|---|
| AUTH01 | Execute 20D outcome return computation | **BLOCKED** — not authorized by S44 |
| AUTH02 | Write 20D outcome returns to any database | **BLOCKED** — not authorized by S44 |
| AUTH03 | Use 20D results to update V3 activation status | **BLOCKED** — G03/G04 still FAIL |
| AUTH04 | Activate V3 in production | **BLOCKED** — multiple preconditions unmet |
| AUTH05 | Modify cron / Stage B probe | **BLOCKED** — Stage B declined in S36 |

**AUTH01 and AUTH02 must be explicitly granted in the future session prompt.**
