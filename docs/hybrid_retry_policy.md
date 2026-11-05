# Hybrid Forward Shadow — Retry Policy

**Status:** ACTIVE  
**Date:** 2026-11-05

---

## Problem

Taiwan exchange (TWSE/TPEx) data can arrive late. Cron fires at 16:00 Taiwan, but the full market dataset (non-0050 stocks) may not publish until 16:30+. Without a retry, the pipeline fails closed on `BLOCKED_PARTIAL_MARKET` every day that TWSE is slow.

## Design Principles

1. **Single cron entry.** One `0 16 * * 1-5` entry. Retry is an internal loop in the pipeline, NOT multiple cron lines.
2. **Process holds the lock** throughout the entire retry window (up to 90 minutes).
3. **Re-run backfill before each re-check.** New data may have arrived since the last attempt.
4. **Fail-closed on non-retryable conditions.** STALE and UNKNOWN do not retry.

## Parameters

```python
RETRY_MAX = 3                    # max retries per session
RETRY_INTERVAL_MINUTES = 30      # sleep between attempts
# Max total wait = 3 × 30 = 90 min (pipeline exits ~17:30 at latest)

_RETRYABLE_STATUSES = frozenset({
    FreshnessStatus.BENCHMARK_ONLY_UPDATED,   # 0050 updated, non-0050 not yet
    FreshnessStatus.PARTIAL_MARKET_UPDATE,    # partial count below threshold
    FreshnessStatus.PROVIDER_NOT_READY,       # API not yet serving today's data
})
```

## Flow

```
16:00 Cron fires
  │
  ├─ Backfill
  ├─ Check freshness (attempt 0)
  │    FULL_MARKET_FRESH → proceed to backup + shadow
  │    RETRYABLE + attempt < 3 → save state, sleep 30m, re-backfill, loop
  │    STALE / UNKNOWN → BLOCKED_STALE_DATA (no retry)
  │    RETRYABLE + attempt == 3 → BLOCKED_PARTIAL_MARKET (retries exhausted)
  │
  └─ [optional retry at 16:30, 17:00, 17:30]
```

## Outcome mapping

| Freshness after retries exhausted | Pipeline status | exit_code | Alert |
|---|---|---|---|
| BENCHMARK_ONLY_UPDATED | BLOCKED_PARTIAL_MARKET | 0 | PARTIAL_MARKET |
| PARTIAL_MARKET_UPDATE | BLOCKED_PARTIAL_MARKET | 0 | PARTIAL_MARKET |
| PROVIDER_NOT_READY | BLOCKED_STALE_DATA | 0 | STALE_DATA |
| STALE | BLOCKED_STALE_DATA | 0 | STALE_DATA |

All BLOCKED statuses exit with code 0 (expected/safe condition, not a crash).

## State during retry

Each retry saves intermediate state to `data/.cron_state.json`:
```json
{
  "steps": {
    "data_freshness": "BENCHMARK_ONLY_UPDATED",
    "freshness_retry_attempt": 2
  },
  "status": "UNKNOWN"
}
```

Final state reflects the terminal outcome.

## Tests

HC34–HC38 in `tests/test_hybrid_cron.py` cover:
- HC34: retry once then pass → SUCCESS
- HC35: all retries exhausted → BLOCKED_PARTIAL_MARKET  
- HC36: STALE → no retry, immediate block
- HC37: state saved during retry interval
- HC38: PROVIDER_NOT_READY retries → BLOCKED_STALE_DATA
