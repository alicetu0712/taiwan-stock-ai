# Backfill Dry-run Plan — Session 48

**Date:** 2026-11-09  
**Session:** S48 — PART D (P3)  
**Verdict:** INSERT_ONLY_CANDIDATE (9 dates), UNIVERSE_UNVERIFIED (2 dates)  
**Production Writes:** NONE (dry-run only; authorization required before execution)

---

## Candidate Dates (11 total)

| Date | Existing Rows | Missing Est. | 0050 Conflict | Readiness | Notes |
|---|---|---|---|---|---|
| 2026-10-08 | 1 (0050) | ~655 | Yes (0050 exists) | INSERT_ONLY | Add ~655 stocks; 0050 stays |
| 2026-10-15 | 1 (0050) | ~655 | Yes | INSERT_ONLY | Same |
| 2026-10-19 | 1 (0050) | ~655 | Yes | INSERT_ONLY | Same |
| 2026-10-20 | 1 (0050) | ~655 | Yes | INSERT_ONLY | Same |
| 2026-10-27 | 1 (0050) | ~655 | Yes | INSERT_ONLY | Same |
| 2026-10-29 | 1 (0050) | ~655 | Yes | INSERT_ONLY | Same |
| 2026-10-30 | 1 (0050) | ~655 | Yes | INSERT_ONLY | Same |
| 2026-11-02 | 1 (0050) | ~655 | Yes | INSERT_ONLY | Same |
| 2026-11-03 | 1 (0050) | ~655 | Yes | INSERT_ONLY | Same |
| 2026-11-06 | 0 | ~656 | No | UNIVERSE_UNVERIFIED | Full insert; 0 existing rows |
| 2026-11-09 | 0 | ~656 | No | UNIVERSE_UNVERIFIED | Full insert; 0 existing rows |

---

## INSERT_ONLY_CANDIDATE Definition

A date is INSERT_ONLY when:
- 0050 already has a row (would be a conflict for 0050)
- All other stocks (~655) are absent
- The INSERT operation for missing stocks does NOT require UPDATE or DELETE

**Conflict risk**: LOW for all 9 INSERT_ONLY dates. The 0050 row already present does not conflict with the ~655 missing stocks — those are simply absent and would be pure INSERTs.

The only "conflict" is the pre-existing 0050 row: a backfill script must either skip 0050 (already present) or use INSERT OR IGNORE. This is not a data integrity conflict — it is an idempotency requirement.

---

## UNIVERSE_UNVERIFIED Definition

Nov 06 and Nov 09 have 0 existing rows. We know:
- They are trading days (TaiwanTradingCalendar confirmed)
- The pipeline did not capture data (QG_FAIL and PROVIDER_NOT_READY)
- The TWSE historical API can provide prices for past dates

However, we have not verified:
- Exact stock count available from API for these dates
- Whether the TWSE API response format differs for recent past dates

**Conflict risk**: LOW (no existing rows to conflict with). Universe unknown.

---

## Impact on Cluster Eligibility (If Backfill Executed)

| Backfill Dates | Clusters Affected | Proxy Count Change |
|---|---|---|
| Oct 29/30, Nov 02/03 | Oct 21 fill | 4 → 8 (INCOMPLETE → STRICT) |
| Oct 29/30, Nov 02/03 | Oct 22 fill | 3 → 7 (INCOMPLETE → STRICT) |
| Oct 29/30, Nov 02/03 | Oct 28 fill | 2 → 5 (INCOMPLETE → STRICT) |

If backfill of Oct 29/30/Nov 02/03 is authorized and succeeds, **all 3 incomplete clusters would become STRICT-eligible**, bringing total strict count from 3 to 6.

However, G04 would still FAIL (60-80% adjacent overlap remains a design-level issue).

---

## Authorization Required

Backfill execution requires explicit authorization separate from this research module. The dry-run plan above is READ-ONLY research output.

**Required steps before execution**:
1. Verify TWSE historical API availability for each date
2. Confirm dedup logic handles pre-existing 0050 rows
3. Run QG validation on fetched data before INSERT
4. Use research-isolated SQLite only (not production Neon)
5. Obtain explicit authorization (backfill of research DB)

---

## What This Does NOT Plan

- Nov 06–Nov 25 (future 20D exit dates): not candidates until pipeline restored
- Nov 04/05: already complete (MANUAL_BACKFILL, no action needed)
- Oct 08–Oct 14 non-fill dates (Oct 08 alone is non-fill, rest have full data): classified, may not be needed for research
