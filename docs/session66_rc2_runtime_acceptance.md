# Session 66 — RC-2 Runtime Acceptance

## H3 Scheduled Runtime: PENDING_NEXT_SCHEDULED_RUN

## H4 Production Data Quality: H4_NOT_YET_VERIFIED

---

## H3 — What to Observe (Next Cron Run)

After the next scheduled `0 16 * * 1-5` execution, verify in `logs/hybrid_cron.log`:

| Check | Expected After RC-2 |
|---|---|
| Cron execution timestamp | 16:00 Taiwan time, any weekday |
| Runtime script path | `.../scripts/backfill_daily_prices.py --execute` (unchanged) |
| Warrant stock IDs in output | ABSENT — len>4 pure-numeric excluded |
| 5-digit ETF IDs in output | ABSENT — len>4 pure-numeric excluded |
| 4-digit ordinary stocks | PRESENT — unaffected by RC-2 |
| 0050 (benchmark) | PRESENT — unaffected |
| Provider HTTP calls | TWSE + TPEx called (normal) |
| QG result | PASS or PRE_EXISTING_QG_FAILURE (see below) |
| DB rows after (if QG passes) | Increases — new dates inserted without warrant rows |
| DB rows after (if QG fails) | Unchanged |
| Error log | No new errors attributable to RC-2 |

---

## Pre-existing QG Failure Warning

Recent cron logs (Nov 9, Nov 10) show repeated QG failures:
```
quality gate FAILED — not writing to DB
TWSE api_date != target — API returned wrong date
```

These failures pre-date RC-2. If the next cron run also fails QG, classify as:

`PRE_EXISTING_QG_FAILURE`

This does NOT indicate an RC-2 problem. Do NOT roll back RC-2 for a pre-existing QG issue.

Do NOT modify the QG, Provider, or `api_date` logic to "fix" this. That is out of scope.

---

## H4 — Production Data Quality

H4 cannot be evaluated until at least one successful QG-passing cron run has occurred with RC-2 active.

Metrics to check when H4 becomes evaluable:

| Metric | Baseline | Expected Improvement |
|---|---|---|
| Warrant rows in new backfill batches | Previously included (NULL volume) | ZERO — now excluded |
| 5-digit ETF rows in new batches | Previously included (NULL volume) | ZERO — now excluded |
| New NULL volume rows from warrants | 107,590 historical (unrepairable without AUTH01) | Zero for new dates |
| Ordinary stock coverage | 826 stocks | Unchanged |
| 0050 continuity | Last date 2026-11-05 | Continues with new dates |

**RC-2 does NOT repair existing 129,636 NULL volume rows.** It prevents new warrant/5-digit-ETF rows from being created.

---

## Monitoring Plan

### Immediate (already done)
- [x] File hash verified: `4eb6eacf...`
- [x] Exact diff: single-line RC-2 only
- [x] Syntax: OK
- [x] Import: OK
- [x] Offline functional: 8/8 PASS
- [x] Cron: UNCHANGED
- [x] DB integrity: 534,770 rows, unchanged

### Next Scheduled Run
- [ ] Check `logs/hybrid_cron.log` after 16:00 next trading day
- [ ] Confirm script path matches deployed file
- [ ] Confirm warrant/5-digit-ETF IDs absent from eligible list
- [ ] Record QG result (PASS or PRE_EXISTING_QG_FAILURE)
- [ ] Record `SELECT COUNT(*) FROM daily_prices` before/after

### Follow-up
- [ ] After first successful QG-pass run: evaluate H4 metrics
- [ ] If unexpected behavior: preserve log evidence, check if attributable to RC-2
- [ ] If rollback needed: use `scripts/backfill_daily_prices.py.bak-PRE-RC2-20261111`

---

## H3 Declaration

H3 observation window has not yet occurred as of end of Session 66.

```
H3: PENDING_NEXT_SCHEDULED_RUN
H4: H4_NOT_YET_VERIFIED
```

Manual triggering of cron or backfill is NOT authorized. Wait for natural scheduled execution.
