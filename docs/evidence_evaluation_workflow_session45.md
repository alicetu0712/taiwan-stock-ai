# Evidence Evaluation Workflow — Session 45

**Date:** 2026-11-09  
**Session:** S45  
**Module:** `src/research/evidence_policy_s45.py`  
**Mode:** DRY_RUN (Read-only)

---

## Purpose

12-step workflow for evaluating new evidence when it becomes available. Currently operates in dry-run mode. No computation or production writes are performed.

---

## Workflow Steps

| Step | Action | Result (S45 Dry-run) |
|---|---|---|
| W01 | Discover candidate evidence (v8.0 buy/SB fill dates) | 6 fill dates |
| W02 | Verify provenance (all GENUINE_PROSPECTIVE) | 6/6 pass |
| W03 | Verify strategy version (v8.0, hash `be43e8ca977d9fdd`) | 6/6 pass |
| W04 | Verify trading calendar (0 non-TD signals in v8.0 strict pool) | 6/6 pass |
| W05 | Verify execution date (all NEXT_OPEN_SIMULATED) | 6/6 pass |
| W06 | Verify universe (common stocks) | 6/6 pass |
| W07 | Verify 5D outcome maturity (≥5 real TDs after fill) | 3 eligible, 3 deferred |
| W08 | Verify benchmark (0050 available on all exit dates) | 3/3 pass |
| W09 | Check duplicate/overlap (G04: adjacent windows overlap ~80%) | 3 eligible, G04 documented |
| W10 | Apply comparison contract v1.0-s44 | 3 pass |
| W11 | Apply statistical guardrails (G01-G10) | G03 FAIL (need ≥10 clusters) |
| W12 | Generate evidence readiness report | NO_NEW_ELIGIBLE_EVIDENCE |

---

## Dry-run Output

| Metric | Value |
|---|---|
| Candidate count | 6 |
| Eligible (strict 5D) | 3 |
| Ineligible | 0 |
| Deferred (incomplete) | 3 |
| Unique eligible fill dates | 3 |
| Missing evidence | G03: need 7 more strict clusters; 3 deferred pending pipeline |
| Next eligible evaluation date | ~2026-11-10 (after pipeline updates) |
| **Overall status** | **NO_NEW_ELIGIBLE_EVIDENCE** |

---

## Forbidden Automated Actions

The workflow must never automatically trigger:
1. 20D Outcome Computation
2. Production Backfill
3. Cron Installation
4. Scheduled Capture
5. Strategy Activation
6. Trading Recommendation

These require explicit session-level authorisation.

---

## When to Re-run

Re-run this workflow when:
- daily_prices max advances past 2026-11-11 (Oct-22 fill may become eligible)
- daily_prices max advances past 2026-11-13 (Oct-28 fill may become eligible)
- New forward_signals appear from cron (additional fill clusters)

Each re-run generates a new dry-run report. The workflow is idempotent and read-only.
