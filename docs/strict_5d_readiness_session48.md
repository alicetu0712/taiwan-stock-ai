# Strict 5D Re-evaluation Readiness — Session 48

**Date:** 2026-11-09  
**Session:** S48 — PART F (P5)  
**Verdict:** STRICT_COUNT_UNCHANGED (3/6); WAITING_FOR_PRICE_DATA (3/6)

---

## Eligibility Criterion

A fill cluster is STRICT-ELIGIBLE when:
- TSMC (2330) proxy count ≥ 5
- Proxy count = number of dates after fill_date where TSMC is present in `daily_prices`
- This matches `_count_exit_days(conn, fill_date, "2330")` from `canonical_5d_baseline_s44.py`

The proxy count is NOT limited to the 5-day holding window. It counts all TSMC-present dates after the fill date with no upper bound.

---

## Readiness Matrix

| Fill Date | Proxy Count | Threshold | Strict? | Readiness | Missing Dates |
|---|---|---|---|---|---|
| Oct 13 | 7 | 5 | ✓ | READY_FOR_REEVALUATION | — |
| Oct 14 | 6 | 5 | ✓ | READY_FOR_REEVALUATION | — |
| Oct 16 | 5 | 5 | ✓ | READY_FOR_REEVALUATION | — |
| Oct 21 | 4 | 5 | ✗ | WAITING_FOR_PRICE_DATA | Oct 29/30, Nov 02/03 |
| Oct 22 | 3 | 5 | ✗ | WAITING_FOR_PRICE_DATA | Oct 29/30, Nov 02/03 |
| Oct 28 | 2 | 5 | ✗ | WAITING_FOR_PRICE_DATA | Oct 29/30, Nov 02/03 |

---

## 5D Holding Windows (Window TSMC Presence)

| Fill Date | Window Dates | TSMC Present | Proxy in Window |
|---|---|---|---|
| Oct 13 | Oct 14/15/16/19/20 | ✓ ✗ ✓ ✗ ✗ | 2/5 in window |
| Oct 14 | Oct 15/16/19/20/21 | ✗ ✓ ✗ ✗ ✓ | 2/5 in window |
| Oct 16 | Oct 19/20/21/22/27 | ✗ ✗ ✓ ✓ ✗ | 2/5 in window |
| Oct 21 | Oct 22/27/28/29/30 | ✓ ✗ ✓ ✗ ✗ | 2/5 in window |
| Oct 22 | Oct 27/28/29/30/Nov02 | ✗ ✓ ✗ ✗ ✗ | 1/5 in window |
| Oct 28 | Oct 29/30/Nov02/03/04 | ✗ ✗ ✗ ✗ ✓ | 1/5 in window |

**Key insight**: TSMC presence WITHIN the 5-day window (2/5 for strict fills) differs from the proxy count (5+), because the proxy counts all TSMC dates after fill_date, including later fill dates like Oct 21, Oct 22, Oct 28, Nov 04/05.

This means the frozen baseline deltas were computed using exit prices from dates BEYOND the 5-day calendar window for some clusters.

---

## Why WAITING_FOR_PRICE_DATA (Not PERMANENTLY_INELIGIBLE)

The three incomplete clusters can reach strict eligibility if Oct 29/30/Nov 02/03 are backfilled with full market data (including TSMC). This is a data availability problem, not a structural one:

| Cluster | Additional TSMC Days Needed | From Backfill |
|---|---|---|
| Oct 21 | 1 more (Oct 29 or later) | Oct 29/30/Nov 02/03 backfill |
| Oct 22 | 2 more | Oct 29/30/Nov 02/03 backfill |
| Oct 28 | 3 more | Oct 29/30/Nov 02/03 backfill |

If Oct 29, 30, Nov 02, Nov 03 are all backfilled:
- Oct 21 proxy: 4 → 8 (STRICT)
- Oct 22 proxy: 3 → 7 (STRICT)
- Oct 28 proxy: 2 → 5 (STRICT)

---

## Frozen Baseline Unchanged

Regardless of readiness status of incomplete clusters:
- **Strict cluster count**: 3 (Oct 13/14/16 fills) — UNCHANGED from S44/S45/S46/S47
- **Grand mean delta**: +0.81 pp — UNCHANGED
- **Statistical verdict**: SIGNIFICANCE_INCONCLUSIVE — UNCHANGED

Promoting Oct 21/22/28 to strict would change the baseline — that calculation requires separate authorization.

---

## Recovery Pathway

1. **Backfill authorization** for Oct 29/30/Nov 02/03
2. **QG validation** of fetched data
3. **INSERT into research SQLite** (not production Neon)
4. **Re-run** `build_strict_readiness_matrix_5d()` to confirm proxy counts update
5. **Re-run** `build_canonical_5d_baseline()` to compute expanded baseline

Steps 4–5 require additional session authorization after steps 1–3 complete.
