# 20D Outcome Readiness — Session 42

**Date:** 2026-11-09
**Session:** 42
**Verdict:** PARTIAL_MATURITY (Oct 09-16 signals may now be mature; Oct 21-28 signals NOT yet mature)

---

## 1. Maturity Status Update (vs S41)

As of 2026-11-09, `daily_prices` data is available through 2026-11-09.

**20D maturity timeline** (using fill_date + ~20 trading days):

| Signal Trade_Date | Fill Date | 20D Maturity Date (est.) | Status as of 2026-11-09 |
|---|---|---|---|
| 2026-10-09, 10, 11 | 2026-10-12 | ~2026-11-10 | **Borderline / 1 day away** |
| 2026-10-12 | 2026-10-13 | ~2026-11-11 | Not yet mature |
| 2026-10-13 | 2026-10-14 | ~2026-11-12 | Not yet mature |
| 2026-10-14 | 2026-10-16 | ~2026-11-14 | Not yet mature |
| 2026-10-16 | 2026-10-21 | ~2026-11-20 | Not yet mature |
| 2026-10-21 | 2026-10-22 | ~2026-11-21 | Not yet mature |
| 2026-10-22 | 2026-10-27 | ~2026-11-27 | Not yet mature |
| 2026-10-28 | 2026-10-29 | ~2026-12-02 | Not yet mature |

---

## 2. fwd_return_20d Status

```sql
SELECT COUNT(*) FROM forward_signals
WHERE trade_date BETWEEN '2026-10-01' AND '2026-11-01'
  AND fwd_return_20d IS NOT NULL;
-- Result: 0 (all NULL)
```

**All 344 Oct 2026 signals still have NULL `fwd_return_20d`.**

Production pipeline has not yet written 20D outcomes. This is expected — the production backfill job would need to run after maturity.

---

## 3. Research-Only 20D Computation

Authorized path: compute from `daily_prices` into the SQLite research cache (NOT writing to `forward_signals`). This path is not yet authorized.

**When to authorize:**
1. Wait until ~2026-12-02 (Oct 28 signals mature)
2. OR run partial analysis on only Oct 09-16 signals (~2026-11-14 for all to mature)
3. Research script writes to `SQLiteResearchStorage`, not production tables

---

## 4. Blocker Status

| Blocker | Status | Required For |
|---|---|---|
| EG-08a: 20D outcomes | OPEN (maturity pending) | 20D horizon comparison |
| EG-08b: Research authorization | OPEN (not yet authorized) | Writing to research cache |

---

## 5. Verdict

```
TWENTY_D_OUTCOME = "PARTIAL_MATURITY"
# Oct 09-16 signals: borderline/nearly mature (~Nov 10-14)
# Oct 21-28 signals: not mature until Nov 20-Dec 02
# fwd_return_20d: 0/344 populated (all NULL)
# EG-08a + EG-08b: OPEN
# Action: authorize research-only computation after 2026-11-14
```
