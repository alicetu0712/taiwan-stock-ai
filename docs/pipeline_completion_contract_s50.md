# Pipeline Completion Contract — Session 50

**Date:** 2026-11-10  
**Session:** S50 — PART D  
**Pipeline Status:** BLOCKED (last DATA_COMPLETE date: 2026-11-05)

---

## Overview

The PipelineCompletionContract defines the 10 explicit stages that must pass for a trading day's data to be classified as DATA_COMPLETE. It establishes the BENCHMARK_ONLY rejection rule: a date with only 1 stock (0050 proxy) is explicitly NOT DATA_COMPLETE.

This contract is used to reason about pipeline failures and backfill requirements without modifying any production systems.

---

## 10 Pipeline Stages

| Stage | Name | DATA_COMPLETE Criterion | Failure Verdict |
|---|---|---|---|
| S01 | SCHEDULER_TRIGGER | N/A — prerequisite | SCHEDULER_NOT_TRIGGERED |
| S02 | PROVIDER_READY_CHECK | api_date == expected trading date | PROVIDER_NOT_READY |
| S03 | BULK_FETCH | ≥ 1000 records from at least 1 provider | BULK_FETCH_FAILED |
| S04 | UNIVERSE_FILTER | filtered count ≥ 300 (not benchmark only) | UNIVERSE_FILTER_FAILED |
| S05 | QUALITY_GATE | pass_rate ≥ 95% AND stock_count ≥ 300 | QUALITY_GATE_FAIL |
| S06 | CONFLICT_DETECTION | conflict_count == 0 OR conflicts resolved | CONFLICT_DETECTED |
| S07 | TRANSACTION_PREPARE | n_prepared == n_qg_passed | TRANSACTION_PREPARE_FAILED |
| S08 | TRANSACTION_COMMIT | rows_inserted == n_prepared | TRANSACTION_COMMIT_FAILED |
| S09 | COVERAGE_VERIFY | stock_count ≥ 300 (not 1 benchmark proxy) | COVERAGE_VERIFY_FAILED |
| S10 | PIPELINE_COMPLETE | all prior stages PASS AND audit_log written | PIPELINE_INCOMPLETE |

---

## DATA_COMPLETE Definition

**DATA_COMPLETE** requires ALL of:
1. S04 ≥ 300 distinct stocks after universe filter
2. S05 Quality Gate PASS (pass_rate ≥ 95% AND stock_count ≥ 300)
3. S08 Transaction committed successfully
4. S09 Post-write verification shows ≥ 300 stocks in DB

**DATA_COMPLETE is binary.** A date that partially succeeded (e.g., 100 stocks committed) is NOT DATA_COMPLETE.

---

## BENCHMARK_ONLY Rejection Rule

If `daily_prices` for a given date contains only 1 stock (stock_id = '0050', the ETF benchmark proxy):

- Classification: **TIER_1_PROXY** (not DATA_COMPLETE)
- Verdict: **BENCHMARK_ONLY_REJECTED**
- Reason: A single benchmark stock cannot serve as an exit-price source for multi-stock portfolio evaluation
- Use case: TIER_1_PROXY data is used **only** as a proxy for counting TSMC-present trading days (strict cluster eligibility), not for exit price calculations

---

## Why These Dates Are TIER_1_PROXY (not DATA_COMPLETE)

| Date | DB Stock Count | Classification | Root Cause |
|---|---|---|---|
| 2026-10-29 | 1 (0050) | TIER_1_PROXY | Pipeline ran but only 0050 inserted |
| 2026-10-30 | 1 (0050) | TIER_1_PROXY | Same |
| 2026-11-02 | 1 (0050) | TIER_1_PROXY | Same |
| 2026-11-03 | 1 (0050) | TIER_1_PROXY | Same |
| 2026-11-06 | 0 | DATA_MISSING | QUALITY_GATE_FAIL — 0 stocks |
| 2026-11-09 | 0 | DATA_MISSING | PROVIDER_NOT_READY — api_date returned Nov 06 |

---

## Pipeline Failure Analysis

### Nov 06 (QUALITY_GATE_FAIL)
- Scheduler triggered ✓
- Provider connected ✓  
- Bulk fetch returned data ✓
- Quality Gate: **FAIL** — unknown reason (stock count or OHLC validation below threshold)
- Result: 0 rows written to daily_prices

### Nov 09 (PROVIDER_NOT_READY)
- Scheduler triggered ✓
- Provider check: **FAIL** — api_date returned `1151106` (Nov 06), not `1151109` (Nov 09)
- Pipeline exited at S02 — no data fetched
- Result: 0 rows written to daily_prices

### Root Cause Assessment
**SCHEDULER_NOT_TRIGGERED** or delayed execution is the upstream hypothesis. When the scheduler runs at an unexpected time, the TWSE API may still serve the previous day's cached bulk data. This manifests as:
- S02 FAIL (api_date mismatch) on Nov 09
- S05 FAIL (empty/incomplete universe) on Nov 06

**Root cause is INCONCLUSIVE** — requires pipeline log inspection (not authorized in S50).

---

## References

- Module: `src/research/calendar_contract_s50.py`
- Function: `build_pipeline_completion_contract()`
- Tests: `tests/test_session50_market_sources.py` TC25–TC28
- Prior: `docs/pipeline_recovery_validation_s49.md`
