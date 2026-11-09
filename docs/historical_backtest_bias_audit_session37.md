# Historical Backtest Bias Audit — Session 37

**Date:** 2026-11-08  
**Audit Type:** Read-only bias analysis  
**Version:** session37_v1

---

## 1. Executive Summary

**Verdict: `BACKTEST_CONDITIONAL`**

The historical backtest period (Jul 2024 – Oct 2026) used a consistent TWSE-only universe (713–724 stocks/day). This internal consistency is good. However, multiple biases exist that limit interpretability: survivorship bias from excluding delisted stocks, ETF contamination in signal generation, train-test universe mismatch, and lack of corporate action adjustments. The backtest results are CONDITIONALLY reliable for relative comparisons (V3 vs V2 vs Baseline) but NOT reliable as absolute performance estimates.

---

## 2. Bias Assessment Table

| # | Bias Type | Evidence | Affected Modules | Severity | Est. Impact | Remediation |
|---|---|---|---|---|---|---|
| 1 | Survivorship Bias | 0 delisted stocks in master | All backtests | HIGH | Unknown (overestimates returns) | Load historical delistings |
| 2 | ETF Contamination | 192/2236 v8.0 signals are ETFs | ForwardSignals, V3 backtest | HIGH | Distorts signal distribution | Filter by security_type |
| 3 | Universe Mismatch | Backtest: ~720 stocks; ForwardSignals: ~394 master + non-master | V3 comparison (Session 27) | HIGH | +3.66ppt comparison on mismatched universe | Align universes |
| 4 | Missing Data Bias | Oct 12–28: 394 of 826 master stocks (48%) | ForwardSignals generation | HIGH | Signals from incomplete universe | Ensure full coverage |
| 5 | Stale Price Signals | V6.0 Oct 9–11 signals with 0 price data for those dates | V6.0 ForwardSignals | MEDIUM | V6.0 signals likely unreliable | Record source_price_date |
| 6 | Look-ahead Bias | source_price_date = NULL (unverifiable) | V8.0 ForwardSignals | MEDIUM | Cannot confirm no look-ahead | Mandatory source_price_date logging |
| 7 | Sparse Universe | Only ~10% of full market on ForwardSignals dates | V3 signal generation | HIGH | Selection restricted to subset | Full market coverage |
| 8 | Benchmark Mismatch | V3 comparison uses internal baseline, not 0050 | V3 performance claims | MEDIUM | Unclear alpha vs market | Add 0050 as baseline |
| 9 | Corporate Action | No adjustment for splits/dividends | All backtests | MEDIUM | Unknown (affects long-horizon returns) | Add adjustment factor |
| 10 | Trading Suspension | No suspension flag | All backtests | LOW | Small impact on 1-20d horizon | Load suspension data |

---

## 3. Detailed Analysis

### 3.1 Survivorship Bias

**Definition:** Only currently-listed stocks are included in the analysis. Stocks that were delisted (due to merger, acquisition, bankruptcy, or regulation) are absent.

**Evidence:**
- stocks table: 826 records, ALL have `security_status='listed'`, ALL have `delisted_date=NULL`
- Over a 28-month period (Jul 2024 – Nov 2026), it is statistically unlikely that ZERO stocks were delisted from an 826-stock universe
- Typical Taiwan market annual delisting rate: ~10–20 stocks/year → expected ~25–50 delistings in 28 months

**Affected modules:** All backtests (hybrid_backtest, v3_backtest_engine, backtest_comparison)

**Estimated impact:** Survivorship bias typically inflates backtested returns by 1–5% per annum by excluding negative-return terminations. For 28 months, this could bias returns by +3–12%.

**Verification method:** Cross-reference against TWSE historical listing database. If delistings occurred among our 826 stocks, they would have last price data before their delisting date.

**Remediation:** Load delisted stocks with `delisted_date` populated; exclude them from future signals after their delisting date; keep them in historical simulation as of their last trading day.

---

### 3.2 ETF Contamination

**Definition:** ETFs are included in the signal generation universe, mixed with common stocks.

**Evidence:**
- V8.0 forward_signals: 192 signals for ETF-like stock_ids (5-digit and 6-digit codes)
- Sample ETF signals: 006208 (富邦台50), 00646 (元大S&P500), 00662 (富邦NASDAQ), 00878 (國泰永續高股息)
- V6.0 forward_signals also includes 0050 (benchmark ETF)
- These ETFs have price patterns (momentum, MA20 slopes) that differ fundamentally from common stocks

**Affected modules:** ForwardSignals, V3 backtest where signals are used as input

**Estimated impact:** ETFs represent 8.6% of v8.0 signals. ETFs tracking overseas indices (00646=S&P500, 00662=NASDAQ) will have momentum/timing patterns driven by US markets, not Taiwan market microstructure. Including them creates signal contamination.

**Verification method:** Remove ETF signals and re-run backtest comparison; if relative performance changes materially, ETF contamination was significant.

**Remediation:** Add `security_type` to stocks master; filter signal universe to `security_type='common_stock'` before computation.

---

### 3.3 Train-Test Universe Mismatch

**Definition:** The backtest was trained on a different stock universe than the one used for ForwardSignals generation.

**Evidence:**
- Backtest era (Jul 2024 – May 2026): ~720 TWSE-master stocks/day, 100% in-master
- ForwardSignals dates (Oct 12–28, 2026): 394–395 master stocks + 203 orphan 4-digit + 57 ETF
- Key gap: 826 - 394 = 432 master stocks have NO price data on ForwardSignals dates

**Implications:**
1. The backtest learned patterns from 720 TWSE stocks; the signal applies those patterns to only 394 of those stocks (plus non-master stocks and ETFs)
2. The 432 "missing" master stocks (those without Oct 2026 prices) systematically differ from the 394 that have prices — possibly different sectors or sizes
3. The 203 orphan 4-digit stocks are applying a model trained on master stocks to stocks that were never in the training universe

**Severity:** HIGH — this affects the generalizability of V3 findings

**Verification method:** Identify which 432 master stocks are absent from Oct 2026 prices; check if they form a non-random sample (e.g., all small caps, specific sectors)

**Remediation:** Ensure consistent daily_prices loading across all trading dates before computing ForwardSignals.

---

### 3.4 Missing Data Bias (Sparse Universe)

**Definition:** Only 48% of the master universe has prices on ForwardSignals dates.

**Evidence:**
- Oct 12–28 average: 394 of 826 master stocks present
- This means 432 stocks (52%) are excluded from signal generation
- The included 394 stocks may systematically outperform or underperform the excluded 432

**Price availability selection:** Stocks with prices available on Oct 12–28 may be:
- More actively traded (higher liquidity)
- More prominent in the data source batch being loaded
- Different sector/size characteristics

If the 394 stocks with prices tend to be higher-quality or higher-liquidity, the backtest effectively filtered for these characteristics, inflating returns.

---

### 3.5 Stale Price / Look-ahead Bias

**Definition:** Signals computed using price data from a date different from the declared signal date.

**Evidence — V6.0 (CONFIRMED stale):**
- V6.0 trade_date = 2026-10-09: no daily_prices for Oct 9 in DB
- Signal likely computed from Oct 7 prices (last available)
- This is not look-ahead (using FUTURE prices) but STALE data (using OLD prices)
- Trading on Oct 9 based on Oct 7 prices is realistic (prices from prior close), so this may be intentional
- However, it is undocumented (`source_price_date = NULL`)

**Evidence — V8.0 (UNVERIFIED):**
- V8.0 `source_price_date = NULL` for all 2236 signals
- Cannot confirm whether signals used Oct 12 prices for Oct 12 signals
- Absence of source_price_date logging is a documentation gap

**Verification method:** Check the signal generation code to confirm it uses `date = signal_date` as price data filter.

---

### 3.6 Benchmark Mismatch

**Definition:** V3 performance is compared against an internal baseline strategy, not against a market benchmark.

**Evidence:**
- Session 27: V3 vs V2 comparison (+3.66ppt in-sample)
- V3 vs Baseline (original strategy) comparison
- No comparison against 0050 return or market-exposure-matched portfolio
- Market timing component: V3 avoids market during downturns — this is positive alpha if market goes down but would appear as "stock selection" if not decomposed

**Impact:** Cannot determine whether V3's advantage comes from market timing (avoiding market), stock selection (picking better stocks), or entry timing (better price).

---

### 3.7 Corporate Action Adjustment

**Definition:** No adjustment for stock splits, dividends, or rights offerings.

**Evidence:** `change_pct` column is computed directly from raw close prices. No `adjusted_close` column exists in daily_prices schema.

**Impact:** Forward return calculations (fwd_return_20d, fwd_return_60d) may be distorted by ex-dividend gaps. For a 20-day horizon, one large dividend can create apparent negative returns that are not actual losses.

**Severity:** MEDIUM for 20d horizon; lower for 1-5d horizon.

---

## 4. `PRICE_AVAILABLE` vs `UNIVERSE_COMPLETE`

| Concept | Definition | Current State |
|---|---|---|
| `PRICE_AVAILABLE` | Stock has at least one price record on the target date | Verified per date/stock via daily_prices query |
| `UNIVERSE_COMPLETE` | All eligible tradeable common stocks have prices on the date | **CANNOT BE VERIFIED** — no authoritative universe denominator |

**Key implication:** The fact that 655 stocks have prices on Oct 12 does NOT mean "the universe for Oct 12 is complete." Without knowing how many common stocks were listed on Oct 12, we cannot compute a true coverage ratio.

A signal generated on Oct 12 saying "stock X is a buy" implicitly assumes the signal engine examined ALL eligible stocks and X ranked highest. If the engine only examined 655 of ~1700 eligible stocks, then X may rank 1st among 655 examined but rank 50th if all 1700 were included.

---

## 5. Backtest Reliability Assessment

| Research Finding | Reliability | Limitation |
|---|---|---|
| V3 vs V2 comparison (+3.66ppt in-sample, Session 27) | CONDITIONAL | Same universe for both but: ETF contamination, sparse dates, non-representative universe |
| Walk-forward: 0 feasible windows (Session 28) | HIGH | Market avoidance finding is robust — not sensitive to universe issues |
| V3 market avoidance dominance | HIGH | Structural finding; holds across universe sizes |
| V3 absolute return estimates | LOW | Survivorship bias + sparse universe distort absolute values |
| Signal score distributions | CONDITIONAL | ETF contamination affects score statistics |

---

## 6. Remediation Priority

| Priority | Action | Blockers |
|---|---|---|
| P0 | Filter ETFs from signal generation (code change) | Production code change authorization |
| P0 | Record source_price_date in ForwardSignals (code change) | Production code change authorization |
| P1 | Load historical delisted stocks with delist_date | Write authorization |
| P1 | Ensure consistent daily_prices loading (fix Oct 2026 sparse dates) | Cron resolution + authorization |
| P2 | Add TPEx stocks to master | Schema migration + ETL work |
| P2 | Add adjusted_close column | Schema migration |
| P3 | Validate corporate action adjustments | External data source |

**None executed in this session.**
