# Pipeline Forensics — Session 52

**Analysis date**: 2026-11-10  
**Session**: S52  
**Module**: `src/research/pipeline_forensics_s52.py`  
**Overall Verdict**: ROOT_CAUSE_PARTIAL

---

## Executive Summary

Three pipeline failure dates investigated (Nov 06, Nov 09, Nov 10).

| Date | Failure Mode | Root Cause | Confidence |
|------|-------------|------------|------------|
| Nov 06 | CRON_NO_TRIGGER | macOS scheduler did not execute cron | DIRECTLY_CONFIRMED |
| Nov 09 | PROVIDER_WRONG_DATE | TWSE bulk api_date=2026-11-06 for Nov 09 target | DIRECTLY_CONFIRMED |
| Nov 10 | PROVIDER_WRONG_DATE | TWSE bulk api_date=2026-11-09 for Nov 10 target | STRONGLY_SUPPORTED |

**ROOT_CAUSE_PARTIAL**: Individual failure modes confirmed, but underlying macOS cron non-execution root cause remains inconclusive (Stage B Cron Probe NOT AUTHORIZED since S36).

---

## Nov 06 — CRON_NO_TRIGGER (DIRECTLY_CONFIRMED)

**Primary evidence**: `hybrid_cron.log` was absent at 23:03 CST post-window audit. The cron command uses `>>` redirect — this operator creates the file even if the script produces empty output. File absence is definitive proof of non-execution.

**Secondary evidence**: `.cron_state.json` still showed 2026-11-05 state; `hybrid_forward_run_log` unchanged at id=9.

**S52 addition**: Nov 09/10 cron log entries reveal Nov 06 backfill behavior:
- Nov 09 attempt for Nov 06: api_date=2026-11-06 matched target, but coverage QG failed (<5000 stocks)
- Nov 10 attempt for Nov 06: api_date=2026-11-09 (mismatch); QG-5 blocked

**Conclusion**: Even if cron had run on Nov 06, the TWSE bulk API data for that date had insufficient coverage. Two independent failure modes for Nov 06.

**Important**: The coverage QG failure reason (sub-check: S38 reclassification? API partial response?) is HYPOTHESIS_ONLY — not extractable from compressed log output.

---

## Nov 09 — PROVIDER_WRONG_DATE (DIRECTLY_CONFIRMED)

**Evidence**: `hybrid_cron.log` lines 12, 24, 36, 48:
```
2026-11-09: TWSE api_date=2026-11-06 != target — API returned wrong date
```
Cron fired at 08:00:17Z (16:00:17 CST), retried 3×30min, all returning same wrong date.
Final state: BLOCKED_STALE_DATA at 09:35:14Z.

**Pattern**: TWSE bulk STOCK_DAY_ALL endpoint returns most-recently-available trading day data, not the requested historical date.

---

## Nov 10 — PROVIDER_WRONG_DATE (STRONGLY_SUPPORTED, in-progress at audit)

**Evidence**: `hybrid_cron.log` lines 62-65 (cron at 08:00:39Z, audit at 08:02Z):
```
2026-11-06: TWSE api_date=2026-11-09 != target
2026-11-10: TWSE api_date=2026-11-09 != target
```
**Status at audit time**: PROVIDER_NOT_READY after retry 1/3. Retries 2 and 3 pending.

**Pattern confirmed**: TWSE bulk consistently returns (today - 1 trading day), not requested date.

---

## Failure Reproduction (Mock-based, all production-safe)

7 scenarios in `build_failure_reproduction_scenarios()`:
- FR-01: PROVIDER_WRONG_DATE (api_date mismatch)
- FR-02: QG_FAIL (coverage < 5000)
- FR-03: CRON_NO_TRIGGER (log absent)
- FR-04: STALE_DATA (0050 last_date < today after 3 retries)
- FR-05: PARTIAL_MARKET_COVERAGE (TPEx empty)
- FR-06: BENCHMARK_ONLY (non-benchmark count = 1)
- FR-07: INTERRUPTED_WRITE (rollback simulation)

---

## Recovery Architecture (Design-only, all require authorization)

| Component | Current | Proposed | Complexity |
|-----------|---------|----------|------------|
| Provider Fallback | Bulk only | Single-stock fallback on api_date mismatch | MEDIUM |
| Coverage Gate | Hard fail <5000 | Tiered: FULL/PARTIAL/FAIL with write flag | LOW |
| Retry Policy | Fixed 30min | Exponential for WRONG_DATE | LOW |
| Completion Marker | .cron_state.json | Add completion_hash | LOW |
| macOS Cron | crontab | Launchd plist or heartbeat monitor | MEDIUM |

---

## ROOT_CAUSE_PARTIAL Rationale

- Nov 06 primary cause (macOS non-execution) DIRECTLY_CONFIRMED ✓
- Nov 09/10 cause (TWSE api lag) DIRECTLY_CONFIRMED ✓
- Nov 06 coverage QG sub-check: HYPOTHESIS_ONLY
- macOS underlying cron failure mechanism: ROOT_CAUSE_INCONCLUSIVE (Stage B NOT AUTHORIZED)
