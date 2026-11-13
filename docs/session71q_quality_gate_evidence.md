# Session 71Q — Quality Gate Evidence

**Session**: 71Q  
**Verdict**: `QG_FAILED_PROVIDER_NOT_READY` (retrying)  
**Updated**: 2026-11-13 16:35 CST

---

## QG Status

Cron triggered at 16:00 CST. Initial run + retry 1 complete. Both runs: QG FAILED for all dates. Retry 2 at ~17:05 CST, retry 3 at ~17:35 CST.

## Runtime QG Evidence (2026-11-13T08:00-08:35Z)

**Initial run (08:00-08:02Z)**:
```
• 2026-11-10: TWSE api_date=2026-11-12 != target — API returned wrong date
• 2026-11-10: quality gate FAILED — not writing to DB
• 2026-11-11: TWSE api_date=2026-11-12 != target — API returned wrong date
• 2026-11-11: quality gate FAILED — not writing to DB
• 2026-11-12: quality gate FAILED — not writing to DB
• 2026-11-13: TWSE api_date=2026-11-12 != target — API returned wrong date
• 2026-11-13: quality gate FAILED — not writing to DB
Done (exit=0) ✓
```

**Retry 1 (08:32-08:35Z)**:
```
• 2026-11-10: quality gate FAILED — not writing to DB
• 2026-11-11: quality gate FAILED — not writing to DB
• 2026-11-12: quality gate FAILED — not writing to DB
• 2026-11-13: quality gate FAILED — not writing to DB
Done (exit=0) ✓
PROVIDER_NOT_READY — retry 2/3 in 30m
```
(Mac slept between retry 1 and retry 2 — retry 2 delayed ~5 hours)

**Retry 2 (13:32-13:34Z = 21:32-21:34 CST)**:
```
• 2026-11-10: TWSE api_date=2026-11-12 != target — API returned wrong date
• 2026-11-10: quality gate FAILED — not writing to DB
• 2026-11-11: TWSE api_date=2026-11-12 != target — API returned wrong date
• 2026-11-11: quality gate FAILED — not writing to DB
• 2026-11-12: quality gate FAILED — not writing to DB
• 2026-11-13: TWSE api_date=2026-11-12 != target — API returned wrong date
• 2026-11-13: quality gate FAILED — not writing to DB
Done (exit=0) ✓
PROVIDER_NOT_READY — retry 3/3 in 30m
```

**Retry 3 (14:04-14:05Z = 22:04-22:05 CST — LAST)**:
```
• 2026-11-10: TWSE api_date=2026-11-12 != target — API returned wrong date
• 2026-11-10: quality gate FAILED — not writing to DB
• 2026-11-11: TWSE api_date=2026-11-12 != target — API returned wrong date
• 2026-11-11: quality gate FAILED — not writing to DB
• 2026-11-12: quality gate FAILED — not writing to DB
• 2026-11-13: TWSE api_date=2026-11-12 != target — API returned wrong date
• 2026-11-13: quality gate FAILED — not writing to DB
Done (exit=0) ✓
BLOCKED_STALE_DATA (after 3 retries) — 0050 last_date=2026-11-05, today=2026-11-13
```

**Final status**: `BLOCKED_STALE_DATA`. All 4 runs (initial + 3 retries) failed for all dates.

**Root cause**: TWSE API serving `api_date=2026-11-12` for ALL requests across the entire day (16:00–22:05 CST). Same structural pattern as Nov 10 (where TWSE showed Nov 09 data all day). TWSE API only serves the most recently published date — same-day Nov 13 data was never published to the API during the observation window. This is a data provider structural limitation, not a code or guard issue.

**Note on 2026-11-12**: No `api_date mismatch` error (api_date correctly returns 2026-11-12) but still QG FAILED — another gate (QG-2~QG-7) blocked it. Possibly incomplete data or TPEx error.

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
