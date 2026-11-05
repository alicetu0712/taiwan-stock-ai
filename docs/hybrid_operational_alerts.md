# Hybrid Forward Shadow — Operational Alerts

**Status:** ACTIVE  
**Date:** 2026-11-05

---

## Design

Local-only alert state. No email, no Slack, no external services.

Alerts are written to `data/.alert_state.json` during pipeline execution.  
The dashboard reads this file and shows a warning banner for unresolved today-alerts.

## Alert Types

| Alert Type | Trigger | Pipeline Status |
|---|---|---|
| `STALE_DATA` | Backfill failed; or freshness STALE/PROVIDER_NOT_READY after retries | BACKFILL_FAILED / BLOCKED_STALE_DATA |
| `PARTIAL_MARKET` | BENCHMARK_ONLY_UPDATED or PARTIAL_MARKET_UPDATE after all retries | BLOCKED_PARTIAL_MARKET |
| `BACKUP_FAILURE` | `create_backup()` returned None | — (pipeline continues) |
| `SHADOW_FAILED` | Shadow runner exited non-zero | SHADOW_FAILED |
| `MISSED_RUN` | Reserved for future missed-run detector | — |
| `PROVIDER_FAILURE` | Reserved | — |
| `DECISION_HASH_CONFLICT` | Reserved | — |

## Deduplication

Each alert is keyed by `(trade_date, alert_type)`.

- First occurrence: `record()` returns `True`, alert written to file
- Subsequent same-day same-type: `record()` returns `False`, `count` incremented
- After fix: call `resolve(trade_date, alert_type)` to mark resolved

## State File Format

`data/.alert_state.json`:
```json
{
  "alerts": [
    {
      "trade_date": "2026-11-06",
      "alert_type": "PARTIAL_MARKET",
      "message": "BENCHMARK_ONLY_UPDATED after 3 retries: 0 stocks on 2026-11-06",
      "first_seen": "2026-11-06T08:30:00+00:00",
      "last_seen": "2026-11-06T09:30:00+00:00",
      "count": 3,
      "resolved": false
    }
  ]
}
```

## Dashboard Integration

G0 panel in `dashboard/_pages/entry_timing_research.py`:
- Shows **今日未解警報** count in metrics row
- Shows warning banner listing each active alert with type, message, and count

## AlertStateManager API

```python
from src.research.alert_state import AlertStateManager

mgr = AlertStateManager()                     # loads from data/.alert_state.json
is_new = mgr.record(trade_date, alert_type, message)  # True=new, False=dup
mgr.resolve(trade_date, alert_type)           # mark resolved
active = mgr.active_alerts(trade_date=date.today())   # unresolved today
all_a  = mgr.all_alerts(limit=20)            # all, most-recent first
```

## Tests

AL01–AL08 in `tests/test_hybrid_cron.py`:
- AL01: new alert → True
- AL02: duplicate → False
- AL03: duplicate increments count
- AL04: resolve → not in active_alerts
- AL05: active_alerts excludes resolved
- AL06: active_alerts filters by date
- AL07: all_alerts includes resolved
- AL08: different alert_types on same date are independent
