# Historical Research Eligibility — Session 39

**Date:** 2026-11-08  
**Session:** 39  
**Overall Verdict:** `INELIGIBLE`

---

## 12-Check Eligibility Gate

| ID | Check | Verdict | Key Finding |
|---|---|---|---|
| EG-01 | Official security classification | ELIGIBLE | 100% of FS v8.0 classified by official API |
| EG-02 | Point-in-time universe | INELIGIBLE | No listing_date in schema; look-ahead unverifiable |
| EG-03 | Trading date validity | CONDITIONAL | v8.0 dates valid; v6.0 excluded; backtest era OK |
| EG-04 | Market data coverage | CONDITIONAL | Forward 48%, Backtest 87%; below 80% threshold |
| EG-05 | Benchmark availability | CONDITIONAL | 0050 available but also ETF-contaminated in signals |
| EG-06 | Price freshness (source_price_date) | UNVERIFIED | Column exists; population rate not verified |
| EG-07 | Corporate action adjustment | UNVERIFIED | Adjustment status not documented |
| EG-08 | Missing outcomes | INELIGIBLE | 0/2236 fwd_return_20d; no outcomes until Dec 2026 |
| EG-09 | Duplicate signals | ELIGIBLE | 0 duplicates confirmed (Session 37) |
| EG-10 | Overlapping hold-period samples | CONDITIONAL | 7 signal dates × 20D window = overlapping; cluster inference required |
| EG-11 | Look-ahead bias | CONDITIONAL | NEXT_OPEN entry OK; two look-ahead sources UNVERIFIED |
| EG-12 | Survivorship bias | INELIGIBLE | 0 delisted_date records; 99 probable delistings unhandled |

**Score: 2 ELIGIBLE, 4 CONDITIONAL, 3 INELIGIBLE, 2 UNVERIFIED**  
**Overall: INELIGIBLE**

---

## Critical Flag: POINT_IN_TIME_UNIVERSE_UNVERIFIED

> The stocks master has NO `listing_date` column. The platform cannot verify which stocks were listed on each historical signal date. It is FORBIDDEN to use current listing status to infer past eligibility.
>
> Any backtest result that uses all 826 stocks on all historical dates implicitly assumes all stocks were listed from the beginning of the data period. This assumption is unverified.

---

## EG-08 Detail: Missing Outcomes (INELIGIBLE)

| Metric | Value |
|---|---|
| v8.0 valid signals | 2,236 |
| fwd_return_20d non-NULL | 0 |
| Earliest outcome available | 2026-12-02 (Oct 12 + 20D) |
| Outcome window status | PENDING |

Without fwd_return_20d, NO outcome-based performance comparison can be computed. All three datasets (A/B/C) have identical outcome availability: zero.

---

## EG-12 Detail: Survivorship Bias (INELIGIBLE)

| Metric | Value |
|---|---|
| `delisted_date` rows | 0 |
| Probable delistings in master | 99 |
| Confirmed mid-era delistings | 3 (2867: 2026-07-24, 6806: 2026-06-22, 6288: 2025-08-04) |
| Delisted before data start | 96 (zero price data) |

The 3 mid-era delistings participated in backtest signals. If the backtest engine does not handle post-delisting prices correctly, return calculations may be distorted.

---

## Eligibility by Research Phase

| Phase | Eligibility | Primary Blockers |
|---|---|---|
| Backtest era (Jul 2024–May 2026) | CONDITIONAL | EG-02 (point-in-time), EG-07 (adj), EG-12 (survivorship) |
| Walk-forward (Sessions 28) | INELIGIBLE | 0 feasible windows (MARKET_AVOIDANCE_DRIVEN) |
| Forward era Oct 12–28, 2026 | INELIGIBLE | EG-08 (0 outcomes), EG-04 (48% coverage) |
| Prospective (future) | BLOCKED | Cron not running; Stage B not authorized |

---

## Remediation to Reach CONDITIONAL

Minimum changes needed to upgrade from INELIGIBLE to CONDITIONAL:

1. **EG-08**: Wait for 2026-12-02 (first outcomes available)
2. **EG-12**: Add `delisted_date` column; mark 3 confirmed delistings (2867, 6806, 6288)
3. **EG-02**: Extract TWSE listing dates → add to stocks master

After these three changes, the remaining INELIGIBLE checks convert to CONDITIONAL, enabling analysis with explicit caveats.
