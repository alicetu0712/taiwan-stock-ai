# Universe Integrity & Warrant Contamination — Session 57

**Session ID**: S57  
**Date**: 2026-11-10

---

## Nov04 Universe Composition

| Category | Count | % of Total | In Research Universe? |
|----------|-------|-----------|----------------------|
| Ordinary 4-digit (1000-9999) | 1969 | 28.3% | YES |
| ETF (00x prefix) | 159 | 2.3% | NO |
| Warrants 7xx prefix | 4816 | 69.2% | NO |
| Other 02x prefix | 13 | 0.2% | NO |
| **Total** | **6957** | **100%** | — |

**Contamination rate**: 71.7% of rows are non-ordinary securities.

---

## Warrant Classification

Warrants in `daily_prices` as of Nov04:
- **4816 rows with 7xx prefix**: Covered warrants (認購/認售權證) issued by brokerages
- **13 rows with 02x prefix**: Preferred shares or similar instruments

These are NOT ordinary common stocks. Including them in coverage calculations or
universe counts produces severely misleading results.

---

## Correct Research Denominator

| Session | Denominator Used | Correct? | Note |
|---------|-----------------|----------|------|
| S38 (official) | 1996 | YES (official TWSE+TPEx count) | Official common stock universe |
| S55 "~700 universe" | ~700 | NO | Underestimate |
| S56 | 1969 | YES | Actual Nov04 ordinary stock count |
| S57 | 1969 | YES | Verified Nov04 ordinary stock count |

**Working denominator**: 1969 (actual Nov04 ordinary stock count)  
**Official denominator**: 1996 (S38 official TWSE+TPEx common stock count)  
**Discrepancy**: 27 stocks — likely newly listed, recently delisted, or ETF reclassification

---

## Coverage Implications

For research coverage calculations (e.g., how many ordinary stocks have price data for a given date):

**WRONG**: `covered_stocks / 6957` → produces artificially low coverage (28.3% max)  
**CORRECT**: `covered_stocks / 1969` → produces meaningful coverage percentage

For the BENCHMARK_ONLY dates (Oct29/30/Nov02/03):
- 0 ordinary stocks → 0/1969 = 0% coverage (not 1/6957 = 0.014%)

---

## ETF Tracking

159 ETF rows on Nov04 (00x prefix). These include:
- 0050 (元大台灣50 — the benchmark)
- Other TWSE-listed ETFs (00632, 00636, etc.)
- TPEx-listed ETFs

ETFs are excluded from ordinary stock universe but should NOT be deleted —
they are valid securities for backtesting ETF strategies.

---

## Deduplication Status (Nov04)

- Duplicate stock IDs: 0 (no duplicates found)
- OHLC invalid rows: 0 (high ≥ low, close in range for all rows)
- Volume null rows: 5715 (structural TPEx NULL — expected, not a data error)

---

## PIT Universe Stability

Point-in-time ordinary stock count across dates:

| Date | Ordinary 4-digit Count |
|------|----------------------|
| Nov04 | 1969 |
| Nov05 | 1967 |
| Difference | -2 (delisting or classification change between Nov04/05) |

For Oct29–Nov03 (BENCHMARK_ONLY dates), PIT universe estimated at 1969
based on Nov04 reference. This is an estimate — actual PIT count unverified.

---

## S38 Official Universe Reference

From S38 security classification work:
- Official TWSE common stocks: ~1600-1650 (estimated; exact count requires TWSE API)
- Official TPEx common stocks: ~350-400 (estimated)
- Combined official ordinary: **1996** (S38 official count)
- ETF fraction: 9.52% (official)

The S57 research denominator of 1969 is 1.4% lower than the official 1996,
consistent with normal market delisting/listing turnover.
