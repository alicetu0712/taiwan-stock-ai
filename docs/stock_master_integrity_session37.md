# Stock Master Integrity Report — Session 37

**Date:** 2026-11-08  
**Audit Type:** Read-only stocks/daily_prices integrity analysis  
**Version:** session37_v1

---

## 1. StockMasterIntegrityReport Summary

**Verdict: `STOCK_MASTER_PARTIAL`**

The stocks table covers only TWSE common stocks (826 records). TPEx common stocks are absent. The daily_prices table contains 15,046 distinct stock_ids including ~14,319 "orphan" records (not in stocks master). The ForwardSignals engine computed signals for ETFs and non-master stocks, creating a **universe contamination** issue.

---

## 2. Schema Analysis

### stocks table

| Column | Type | Key | Notes |
|---|---|---|---|
| stock_id | VARCHAR(10) | PRIMARY KEY | 4-char codes only (826 records) |
| name | VARCHAR(50) | — | Chinese company name |
| market | VARCHAR(10) | — | 'TWSE' for all 826 |
| industry | VARCHAR(50) | — | Sector classification |
| listing_date | DATE | — | IPO date |
| capital | FLOAT | — | Paid-in capital |
| outstanding_shares | FLOAT | — | Shares outstanding |
| is_excluded | BOOLEAN | — | All 0 (none excluded) |
| updated_at | DATETIME | — | Last update timestamp |
| delisted_date | DATE | — | NULL for all 826 |
| security_status | VARCHAR(20) | — | 'listed' for all 826 |

**Missing columns (proposal only, not implemented):**
- `security_type` (common/ETF/preferred/TDR)
- `exchange` (TWSE/TPEx/GTSM)
- `tpex_flag` or similar

### daily_prices table

| Column | Type | Key | Notes |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY | Auto-increment |
| stock_id | VARCHAR(10) | — | **No FK constraint to stocks** |
| date | DATE | — | Trading date |
| open/high/low/close | FLOAT | — | OHLC |
| volume | FLOAT | — | Volume |
| amount | FLOAT | — | Turnover amount |
| change_pct | FLOAT | — | Daily return |

**Critical: No foreign key constraint.** daily_prices accepts any stock_id. This is by design (allows loading full market data before stocks master is populated) but creates master-less orphan records.

---

## 3. Primary Key / Foreign Key Analysis

| Check | Result |
|---|---|
| stocks PK | stock_id (VARCHAR 10), 826 unique values |
| daily_prices FK to stocks | **NONE** — no FK constraint defined |
| daily_prices unique constraint | None stated (deduplicated by backfill script) |
| forward_signals FK to stocks | **NONE** — no FK constraint |
| forward_signals distinct stock_ids (v8.0) | 410 |
| forward_signals orphan stock_ids (not in stocks) | **186** (45.4%) |

---

## 4. Stock ID Normalization

| ID Length | Count in daily_prices | Count in stocks | Interpretation |
|---|---|---|---|
| 4-digit | 2002 | 826 | TWSE/TPEx common stocks + some ETFs |
| 5-digit | 113 | 0 | ETFs (00xxx series, e.g. 00646, 00878) |
| 6-digit | 12931 | 0 | Leverage/inverse ETFs, bond ETFs (006xxx, 009xxx) |
| **Total** | **15046** | **826** | — |

**4-digit orphans by first digit (not in stocks master):**

| First Digit | Count | Likely Type |
|---|---|---|
| 1 | 28 | TWSE traditional industry (some not in master) |
| 2 | 42 | TWSE electronics (some not in master) |
| 3 | 169 | TWSE/TPEx electronics |
| 4 | 203 | Likely TPEx stocks |
| 5 | 147 | Likely TPEx stocks |
| 6 | 422 | Likely TPEx stocks (large count vs 36 in master) |
| 7 | 79 | Mixed TWSE/TPEx |
| 8 | 154 | Likely TPEx stocks |
| 9 | 31 | Mixed |
| **Total** | **1275** | — |

**Key inference:** The 1275 four-digit orphans are likely a mix of TPEx common stocks and TWSE stocks not loaded into the master. The 6xxx range is particularly suspicious: stocks master has only 36 six-hundred-series stocks but daily_prices has 422 orphan 6xxx stocks.

---

## 5. Missing Master Records

**Question: Why don't TPEx stocks appear in the stocks table?**

**Observed facts:**
1. The stocks table has `market='TWSE'` for all 826 records
2. Zero records have `market='TPEx'` or any TPEx indicator
3. The ETL pipeline appears to have been designed or executed with TWSE-only data sources
4. TWSE OpenAPI (`STOCK_DAY_ALL` endpoint) returns TWSE stocks only
5. TPEx stocks require a separate data source (TPEx API or twstock library)

**Conclusion (INFERENCE, not confirmed by code review):** The ETL pipeline was designed around TWSE data sources only. TPEx data was never loaded into the stocks master. This is an ETL scope gap, not a data model limitation.

**Question: Does daily_prices allow stocks without master records?**

**Yes.** There is no FK constraint. The full-market backfill (Nov 4–5, 2026) loaded all securities from the full market batch, including TPEx stocks, ETFs, and leverage funds, directly into daily_prices without corresponding stocks master records.

---

## 6. Orphan Price Records

| Category | Count (stock_ids) | Count (price rows) | Notes |
|---|---|---|---|
| Orphan stock_ids in daily_prices | 14,319 | ~108,579 (est.) | Not in stocks master |
| 5-digit ETFs (00xxx) | 113 | 3,131 | ETFs, definitively not common stocks |
| 6-digit instruments (006xxx, 009xxx) | 12,931 | ~108,000 | Leverage ETFs, bond ETFs, warrants |
| 4-digit non-master | 1,275 | ~32,462 | Mixed TPEx/TWSE not in master |

**On ForwardSignals dates specifically:**
- Orphan stock_ids with price data: 203–204 (4-digit) + 57 (5/6-digit ETF)
- Signal generation included 787 (4-digit orphan) + 192 (ETF-like) = 979 signals from non-master stocks

---

## 7. ETF / Stock Mixing

**Critical finding:** The ForwardSignals v8.0 and v6.0 include signals for ETFs:

| ETF | Name | Signals in v8.0 | Should be included? |
|---|---|---|---|
| 006208 | 富邦台50 | 7 | **NO** — ETF tracking TWSE 50 |
| 00646 | 元大S&P500 | 5 | **NO** — overseas ETF |
| 00662 | 富邦NASDAQ | 7 | **NO** — overseas ETF |
| 00712 | 復華中小精選 | 6 | **NO** — mixed ETF |
| 00713 | 元大台灣高息低波 | 7 | **NO** — ETF |
| 00878 | 國泰永續高股息 | 7 | **NO** — dividend ETF |
| 0050 | 元大台灣50 (in V6) | Multiple | **NO** — benchmark |

**Root cause:** The signal computation pipeline uses `daily_prices` as its stock universe source without filtering by `stocks` master or by security type. Any security in daily_prices on the signal date gets a score computed.

**Impact:** 192 of 2236 v8.0 signals (8.6%) are for ETFs. These inflate signal counts but should not be part of a common stock strategy. The backtests may not specifically filter ETFs either.

---

## 8. Delisted Securities

| Check | Result |
|---|---|
| Stocks with delisted_date in stocks master | **0** |
| Stocks with security_status ≠ 'listed' | **0** |

**Concern:** A healthy market dataset of 826 stocks accumulated since Jul 2024 should include some stocks that were delisted during this period. The fact that zero delisted stocks appear in the master suggests either:
1. The ETL only loaded currently-listed stocks (survivorship bias), OR
2. The dataset was loaded at a point in time where all 826 were still listed

**Verdict:** PROBABLE SURVIVORSHIP BIAS in stocks master (see `historical_backtest_bias_audit_session37.md`).

---

## 9. Historical Universe Changes

**Observed coverage over time:**

| Period | Daily_prices stocks/day | In master | Note |
|---|---|---|---|
| Jul 2024 – May 2026 | 713–724 | ALL | TWSE-only, clean consistent universe |
| Jun 2026 onwards (full market days) | 6393–6957 | 718–725 | Full market batch loaded (ETFs included) |
| Oct 12–28, 2026 (ForwardSignals dates) | 655–656 | 394–395 | SPARSE: subset of TWSE + ETFs |

**Key pattern:** The historical backtest period (pre-Jun 2026) has a CLEAN TWSE-only universe (713–724 stocks/day, all in master). The ForwardSignals period (Oct 2026) has a DIFFERENT, SMALLER universe (394–395 master stocks — only ~48% of the master universe).

This creates a **train-test universe mismatch**: backtest was trained on ~720 stocks but ForwardSignals were computed on ~394 master stocks.

---

## 10. Duplicate Stock IDs

| Check | Result |
|---|---|
| Duplicate stock_ids in stocks table | 0 |
| Duplicate (stock_id, date) in daily_prices | 0 (from Session 36 audit) |
| Duplicate (stock_id, trade_date, model_version) in forward_signals | 0 |

---

## 11. Verdict Table

| Dimension | Verdict | Severity |
|---|---|---|
| TPEx in stocks master | MISSING | HIGH |
| FK constraint: daily_prices→stocks | ABSENT | MEDIUM |
| ETF filtering in signal generation | ABSENT | HIGH |
| Delisted stocks in master | NOT PRESENT | HIGH (survivorship bias) |
| Orphan price records | PRESENT (14,319 stock_ids) | MEDIUM |
| ID normalization | CONSISTENT (4-digit = master) | — |
| Duplicate IDs | NONE | PASS |
| **Overall** | **`STOCK_MASTER_PARTIAL`** | — |
