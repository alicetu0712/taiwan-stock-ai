# Session 71Q — Quality Gate Evidence

**Session**: 71Q  
**Verdict**: `QG_NOT_OBSERVED` (pre-trigger)

---

## QG Status

No cron run has occurred for Nov 11-13. Quality gate evidence is unavailable until after 16:00 CST triggers a natural cron run.

---

## Last Known QG Result (2026-11-10 — Pre-Deploy-A)

From `logs/hybrid_cron.log` (all 4 retries produced the same QG result):

```
• 2026-11-06: TWSE api_date=2026-11-09 != target — API returned wrong date
• 2026-11-06: quality gate FAILED — not writing to DB
• 2026-11-09: quality gate FAILED — not writing to DB
• 2026-11-10: TWSE api_date=2026-11-09 != target — API returned wrong date
• 2026-11-10: quality gate FAILED — not writing to DB
```

Root cause on 2026-11-10: TWSE API still serving the previous session's (Nov 9) data at 16:00 CST — data not yet published for Nov 10. The backfill ran but QG blocked all writes.

---

## QG Gate Reference (from backfill source)

The 7 quality gates (QG-1~QG-7) check:
- QG-1: API date matches target date
- QG-2~QG-7: Price validity, volume, range, company count thresholds

For 2026-11-13 (Friday), QG-1 is the most likely gate to either pass or block:
- If TWSE publishes Nov 13 data before 16:00 CST → QG-1 may PASS
- If TWSE still serving Nov 12 data at 16:00 CST → QG-1 will FAIL (api_date ≠ target)

Historical pattern: TWSE data typically available after ~15:30 CST, but the 2026-11-10 failure shows it can still be late.

---

## Post-16:00 QG Observation Checklist

After cron runs:

1. Check log for `quality gate PASSED` or `quality gate FAILED`
2. Check log for `api_date=` field — should equal `2026-11-13` for QG-1 PASS
3. Check for `BLOCKED_STALE_DATA` in state file — indicates QG blocked all writes
4. If QG passed: check for `written_count` in log
5. If QG failed: H3 verdict is `H3_INCONCLUSIVE` (QG issue, not RC-2 issue)
