# Hybrid Forward Shadow — Post Go-Live Stabilization

**Status:** COMPLETE  
**Date:** 2026-11-05  
**Session:** 9 (Post Go-Live Stabilization & Operational Reliability)

---

## Overview

Cron was installed on 2026-11-05 (Session 7, authorized). This document records the post-go-live stabilization work completed before the first scheduled run (2026-11-06 16:00 Taiwan).

The goal: system can continuously, safely, and traceably accumulate genuine prospective data.

---

## Work Completed

### PART A — First Scheduled Run Status

| Item | Status |
|---|---|
| Cron installed | ✅ 2026-11-05 18:09 Taiwan |
| First scheduled run | ⏳ AWAITING — 2026-11-06 (五) 16:00 Taiwan |
| Manual pipeline run | ✅ BLOCKED_PARTIAL_MARKET (correct fail-closed) |
| trigger_source recorded | ✅ state file contains trigger_source field |
| exit_code recorded | ✅ state file contains exit_code field |

### PART B — Full-Market Freshness Gate (P1)

- Gate: `src/research/full_market_freshness_gate.py`
- Returns `FULL_MARKET_FRESH` only when both TWSE and TPEx non-0050 count ≥ MIN_REQUIRED (1,000 stocks)
- Shadow runner only proceeds on `FULL_MARKET_FRESH`
- 2026-11-05 status: `BENCHMARK_ONLY_UPDATED` (0050 updated, non-0050 count=0 at 18:28 Taiwan)

### PART C — Retry Policy (P2)

Implemented in `scripts/hybrid_shadow_cron.py`:

| Parameter | Value | Rationale |
|---|---|---|
| RETRY_MAX | 3 | Max 3 retries per session |
| RETRY_INTERVAL_MINUTES | 30 | Wait 30 min between attempts |
| Retryable statuses | BENCHMARK_ONLY_UPDATED, PARTIAL_MARKET_UPDATE, PROVIDER_NOT_READY | TWSE data can be late |
| Non-retryable statuses | STALE, UNKNOWN | Data genuinely missing |
| Max total wait | 90 minutes | Cron process holds lock |
| Cron entries | 1 (single) | Internal retry, NOT multiple cron entries |

Each retry re-runs `backfill_daily_prices.py` before re-checking freshness.  
State file updated during each wait interval so progress is visible.

### PART D — Operational Alerts (P3)

Implemented in `src/research/alert_state.py`:

| Alert Type | Trigger |
|---|---|
| STALE_DATA | Backfill failed, or 0050 data stale after retries |
| PARTIAL_MARKET | TWSE/TPEx partial after all retries exhausted |
| BACKUP_FAILURE | `create_backup()` returns None |
| SHADOW_FAILED | Shadow runner exits non-zero |

**Deduplication:** keyed by `(trade_date, alert_type)`. Duplicate events increment `count` rather than creating new alerts. `record()` returns `True` for new, `False` for duplicate.  
**No external services.** All state in `data/.alert_state.json`.  
**Dashboard G0** reads active alerts and shows banner.

### PART E — Dashboard G0 (P4)

Enhanced G0 panel now shows:
- Cron installed status
- Last run time / status (human-readable Chinese description)
- trigger_source: 排程觸發 / 手動
- exit_code
- Freshness retry attempt counter
- Today's active alert count + alert banner

---

## Tests Added

| Range | Description | Count |
|---|---|---|
| HC34–HC38 | Retry policy: once-then-pass, max-exhausted, stale-no-retry, state-saved, provider-not-ready | 5 |
| AL01–AL08 | AlertStateManager: new/dup/count/resolve/active/filter-date/all/multi-type | 8 |

Total new tests: **13**

---

## Safety Constraints Maintained

- MODEL_VERSION v8.0 — unchanged
- No production Neon writes
- No ACTUAL/PAPER trade accounting changes
- Cron entry count: 1 (no duplicates added)
- No retrospective data claimed as prospective
