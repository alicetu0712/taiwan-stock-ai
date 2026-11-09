# Historical Universe Bias Report — Session 38

**Date:** 2026-11-08  
**Session:** 38  
**Verdict:** `POINT_IN_TIME_UNIVERSE_UNVERIFIED` + `SELECTION_BIAS_PRESENT`

---

## 1. Overview

This report extends the Session 37 bias audit with official-source-verified classification.
Four historical bias types are assessed using official TWSE/TPEx data.

---

## 2. Bias 1: Survivorship Bias (CONFIRMED, HIGH)

### Evidence

| Metric | Value |
|---|---|
| Stocks in master | 826 |
| `security_status = 'delisted'` | 0 |
| Stocks NOT in current TWSE API | 99 |
| Of these: with price data (delisted mid-era) | 3 (2867, 6806, 6288) |
| Of these: with zero price data (delisted before era) | 96 |
| Official TWSE listing date range for 826 stocks | Unknown (not stored) |

### Interpretation

The platform's stocks master loads stocks that SURVIVE to the present day. Stocks delisted before the data extraction date are simply absent. This creates classic survivorship bias:

- 96 stocks are in master but have no price data → they were loaded in a historical snapshot but delisted before Jul 2024
- These 96 stocks did NOT participate in the backtest (zero prices = no signals)
- However, their presence in the master means the model trained on a universe that implicitly excluded non-surviving stocks

**The 826-stock master approximates a survivor-biased universe**: it represents stocks currently active on TWSE, plus historical entries that survived long enough to be included in the data feed.

### Delistings during backtest era (Jul 2024 – Nov 2026)

| Stock | Last Price Date | Status |
|---|---|---|
| 2867 | 2026-07-24 | Delisted mid-era |
| 6806 | 2026-06-22 | Delisted mid-era |
| 6288 | 2025-08-04 | Delisted mid-era |

These 3 stocks DID participate in backtest signals during their active period. After their delisting date, they disappear from the price feed. The backtest engine must handle this correctly (no lookahead on delisting status).

**Survivorship bias severity**: MODERATE — 3 actual delistings in 28-month period is low by absolute count, but the 96 pre-era delistings indicate systematic exclusion of previously delisted stocks from the training universe.

---

## 3. Bias 2: Selection Universe Incompleteness (CONFIRMED, HIGH)

### Evidence from official classification

| Universe | Official Count | In Master | Coverage |
|---|---|---|---|
| TWSE common stocks | 1,099 | 715 | 65.1% |
| TPEx common stocks | 897 | 1 (6423) | 0.1% |
| **Total official common** | **1,996** | **716** | **35.9%** |

**The backtest trained on 35.9% of the full Taiwan common stock market.**

### Breakdown of missing TWSE stocks (384 missing)

| Category | Count | Impact on backtest |
|---|---|---|
| New IPOs (after Jul 2024) | 70 | LOW — unavailable during most of backtest era |
| Pre-existing (before Jul 2024) | 314 | HIGH — should have been in backtest universe |
| Present as orphans in daily_prices | 377 | — |

314 TWSE common stocks existed before the backtest started, have price data as orphans, but were never loaded into the stocks master. The model was not trained on these stocks.

### Impact

The 314 missing pre-existing TWSE stocks represent approximately:
- 314 / (715 + 314) = 30.5% of TWSE stocks that the model never saw
- If these stocks have different sector distributions or return characteristics, the model's learned patterns reflect only the 715-stock subset

---

## 4. Bias 3: Point-in-Time Universe (UNVERIFIED)

The stocks master does not store listing_date for each stock. This creates a potential look-ahead bias:

**Scenario**: Stock X listed in January 2025. Without listing_date filtering, the backtest could generate signals for Stock X on July 2024 dates (before it existed). The model's training distribution includes post-IPO stocks in pre-IPO periods.

### Status
- **UNVERIFIED**: Cannot confirm or deny without listing dates
- The 70 new IPOs (listed after Jul 2024) are explicitly in the master but not distinguished from stocks that existed throughout the backtest period
- TWSE API provides listing dates (上市日期) but these are NOT stored in the platform's stocks master

**Remediation**: Extract listing dates from TWSE API and add to stocks master. Filter backtest signals to stock_id.listing_date < signal_date.

---

## 5. Bias 4: Sector/Market-Cap Distribution Bias (PROBABLE, MEDIUM)

The 715-stock TWSE subset vs full 1,099 is not a random sample. Without detailed analysis:
- The 384 missing TWSE stocks likely include smaller-cap and newer companies
- If the platform loaded stocks based on liquidity or trading volume thresholds, it systematically excludes illiquid stocks
- The model's learned scoring patterns may favor characteristics common in the 715 loaded stocks

**Status**: PROBABLE but unquantified — requires sector and market-cap data for full analysis.

---

## 6. Bias Summary Table

| Bias | Evidence | Severity | Verifiable Now? |
|---|---|---|---|
| Survivorship | 0 delisted in master, 99 probable delistings, 3 mid-era confirmed | HIGH | PARTIAL (3 confirmed) |
| Selection universe | 35.9% coverage of official common stock universe | HIGH | CONFIRMED (official) |
| Point-in-time universe | No listing_date in master | MEDIUM | UNVERIFIED |
| Sector/market-cap distribution | 715 non-random subset | MEDIUM | UNQUANTIFIED |
| ETF contamination (forward era) | 9.52% official | HIGH (forward) | CONFIRMED (official) |

---

## 7. What This Means for the +3.66ppt Result

| Dimension | Bias Impact |
|---|---|
| Relative comparison V3 vs V2 | UNAFFECTED — both trained on same biased universe |
| Absolute return estimate | UNRELIABLE — survivorship + selection bias inflate estimates |
| Generalizability to full Taiwan market | LOW — model trained on 36% of universe |
| Out-of-sample validity | CONDITIONAL — forward era universe mismatch makes OOS test invalid |

**HISTORICAL_BIAS_VERDICT: `POINT_IN_TIME_UNIVERSE_UNVERIFIED` + `SELECTION_BIAS_PRESENT`**

The relative in-sample comparison (V3 vs V2) remains internally consistent despite these biases. Absolute performance claims are unreliable until biases are addressed.
