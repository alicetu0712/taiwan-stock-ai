# Historical Data Recovery Readiness — Session 52

**Analysis date**: 2026-11-10  
**Session**: S52  
**AUTH01 overall**: PENDING  
**Verdict**: BACKFILL_PARTIAL

---

## Per-date Readiness

| Date | Source status | Stocks in DB | Coverage | 5TD impact | 20TD impact | AUTH01 |
|------|--------------|--------------|----------|------------|-------------|--------|
| Oct 29 | SOURCE_VERIFIED_PARTIAL | 1 (0050 only) | 0.05% | Oct 28 exit TD1 | Oct 13-28 exits | PENDING |
| Oct 30 | SOURCE_VERIFIED_PARTIAL | 1 (0050 only) | 0.05% | Oct 28 exit TD2 | Oct 13-28 exits | PENDING |
| Nov 02 | SOURCE_VERIFIED_PARTIAL | 1 (0050 only) | 0.05% | Oct 22/28 exit | Oct 13-28 exits | PENDING |
| Nov 03 | SOURCE_VERIFIED_PARTIAL | 1 (0050 only) | 0.05% | Oct 28 exit TD5 | Oct 13-28 exits | PENDING |
| Nov 04 | SOURCE_COMPLETE | 6,957 | 100%+ | Oct 28 exit TD5 | already covered | ALREADY_COVERED |
| Nov 05 | SOURCE_COMPLETE | 6,957 | 100%+ | — | 20TD windows | ALREADY_COVERED |
| Nov 06 | SOURCE_VERIFIED_PARTIAL | 0 | 0% | — | Oct 13-16 20TD | PENDING |
| Nov 09 | SOURCE_VERIFIED_PARTIAL | 0 | 0% | — | Oct 13-16 20TD | PENDING |

---

## Critical: Single-stock Verification ≠ DATA_COMPLETE

S50 verified via TWSE single-stock API:
- Nov 06: TSMC C=2135, MediaTek C=3390 ✓
- Nov 09: TSMC C=2235, MediaTek C=3725 ✓

**This does NOT mean full market data is available**. Single-stock verification proves data exists for a small sample; it does not prove:
- All 1996 common stocks have OHLC data
- Coverage threshold (≥5000) can be met via bulk API
- Data is available via any single API endpoint in complete form

---

## Nov 06 Coverage QG Failure — Key Finding (New in S52)

When Nov 09 backfill tried to fill Nov 06:
- api_date returned = 2026-11-06 (matched target → QG-5 passed)
- Coverage QG still failed: stocks returned < threshold

This reveals Nov 06 bulk API data has insufficient coverage independently of the api_date lag issue. The specific sub-check that failed is not in the compressed log output (HYPOTHESIS_ONLY).

---

## AUTH01 Preconditions

Before any backfill execution:
1. Explicit user authorization for each target date
2. `--execute` flag required (dry-run default)
3. Quality gate must pass for the recovered data
4. No write to `forward_signals` or `hybrid_forward_decision` as part of backfill
5. Research pipeline re-run is a separate AUTH02 step

---

## Nov 12 Note

Nov 12 is the 20TD maturity date for the Oct 13 cluster. If the Oct 13 → Nov 12 price window cannot be filled with verified data, the Oct 13 20D outcome cannot be computed. However, Nov 12 is **not a permanent data expiry** — historical prices can still be recovered later if authentic sources are available. The constraint is data authenticity, not calendar deadline.
