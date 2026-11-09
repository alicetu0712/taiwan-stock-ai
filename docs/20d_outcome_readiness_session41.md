# 20D Outcome Readiness Report — Session 41

**Date:** 2026-11-09
**Session:** 41
**Verdict:** NO_SIGNALS_MATURE (as of evaluation)

---

## 1. Status Summary

| Metric | Value |
|---|---|
| Oct 2026 signals checked (buy/strong_buy) | 344 |
| Signals with ≥20 trading days available | 0 |
| Earliest estimated maturity | ~2026-11-06 (Oct 09 signals) |
| Latest estimated maturity | ~2026-12-02 (Oct 28 signals) |
| Horizon required | 20 trading days |
| `fwd_return_20d` populated | 0 / 344 (all NULL) |

---

## 2. Per-Date Maturity Estimate

| Signal Date | n Signals | 20D Maturity Date (est.) | Status as of 2026-11-09 |
|---|---|---|---|
| 2026-10-09 | 99 | ~2026-11-06 | Borderline (barely mature) |
| 2026-10-10 | 4 | ~2026-11-07 | Not yet mature |
| 2026-10-11 | 4 | ~2026-11-07 | Not yet mature |
| 2026-10-12 | 46 | ~2026-11-10 | Not yet mature |
| 2026-10-13 | 27 | ~2026-11-11 | Not yet mature |
| 2026-10-14 | 55 | ~2026-11-12 | Not yet mature |
| 2026-10-16 | 39 | ~2026-11-14 | Not yet mature |
| 2026-10-21 | 23 | ~2026-11-20 | Not yet mature |
| 2026-10-22 | 19 | ~2026-11-21 | Not yet mature |
| 2026-10-28 | 28 | ~2026-12-02 | Not yet mature |

Maturity dates are approximate: signal_date + 28 calendar days ≈ 20 trading days (Taiwan trading calendar). Exact dates depend on holidays.

---

## 3. Data Availability Check

As of 2026-11-09, `daily_prices` contains data through approximately 2026-11-09. For Oct 09 signals:
- Fill date: 2026-10-12
- 20D exit date: approximately 2026-11-10 (20th trading day after Oct 12)
- Today: 2026-11-09 → data for the 20th day is NOT YET available

For Oct 28 signals, the 20th trading day is approximately 2026-12-02.

---

## 4. Safety Constraint

**DO NOT compute 20D returns prematurely.** Per safety constraints:
- `forward_signals.fwd_return_20d` must remain NULL (read-only constraint)
- Backfill not authorized
- Research-only 20D computation (writing to research cache) requires explicit authorization

The current production pipeline has not filled `fwd_return_20d`. This is intentional.

---

## 5. Next Steps

**When authorization is granted for research-only 20D computation:**
1. Wait until ~2026-12-02 (Oct 28 signals fully mature)
2. Run research script to compute 20D returns from `daily_prices` → write to research SQLite cache (NOT `forward_signals`)
3. This unblocks Blocker EG-08a and enables 20D horizon comparison
4. Expected: upgrade from 5D CONDITIONAL to 20D comparison

**Current status of Blocker EG-08a:** OPEN (blocked on maturity and authorization)
