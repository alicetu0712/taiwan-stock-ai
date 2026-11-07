# Universe Definition Audit — Session 37

**Date:** 2026-11-08  
**Audit Type:** Read-only universe classification  
**Version:** session37_v1

---

## 1. Executive Summary

**Verdict: `UNIVERSE_PARTIAL`**

The stocks table contains 826 TWSE common stocks only. TPEx common stocks are absent from the master table. ETFs (5-digit and 6-digit codes) appear in daily_prices but should be excluded from any common stock trading strategy. The current ForwardSignals engine did NOT filter by stocks master — it computed signals for ETFs and non-master stocks, creating a methodology error.

---

## 2. Taiwan Market Security Classification

| Security Type | Exchange | Typical Code Format | Expected Count | In stocks table | Coverage |
|---|---|---|---|---|---|
| 上市普通股 (TWSE Common) | TWSE | 4-digit 1xxx–9xxx | ~900–1000 | **826** | **~85–92%** |
| 上櫃普通股 (TPEx Common) | TPEx | 4-digit (overlapping ranges) | ~700–900 | **0** | **0%** |
| 上市 ETF | TWSE | 4-digit 0xxx, 5-digit 00xxx, 6-digit 006xxx | ~200+ | 11 (ETFs in TWSE master) | Partial |
| 槓桿/反向 ETF | Both | 6-digit 006xxx, 009xxx | ~300+ | 0 | 0% |
| ETN | Both | Various | ~50 | 0 | Unknown |
| TDR | TWSE | Various | ~30 | 0 | Unknown |
| 權證 (Warrants) | TWSE | 6-7 digit | ~10,000+ | 0 | 0% |
| 興櫃 (OTC-emerging) | GTSM | Various | ~200+ | 0 | 0% |
| 特別股 (Preferred) | Both | Various | ~20 | 0 | 0% |

**Note:** Counts are approximate based on observed daily_prices data as of Nov 2026. Official TWSE/TPEx published counts would be authoritative.

---

## 3. Observed Data — stocks Table

| Field | Value |
|---|---|
| Total records | 826 |
| Market | TWSE (all 826) |
| TPEx records | **0** |
| ID format | All 4-digit (4 characters) |
| security_status | 'listed' (all 826) |
| delisted_date | NULL (all 826) |
| is_excluded | 0 (all 826, none excluded) |
| ETF-like codes (starting '0') | 11 (includes 0050 benchmark) |

**Observed fact:** stocks table has NO delisted stocks. Either this is by design (only current listed) or delisted stocks were never loaded. This creates potential survivorship bias (see `historical_backtest_bias_audit_session37.md`).

---

## 4. Observed Data — daily_prices Universe

On full-market dates (Nov 4, 2026 — 6957 total stock_ids):

| Security Type (inferred) | ID Pattern | Count | In stocks master |
|---|---|---|---|
| TWSE/TPEx common stocks (inferred) | 4-digit, non-0-prefix | ~1969 | 720 |
| ETFs / benchmark | 4-digit, 0-prefix | ~8 | 8 |
| ETFs (5-digit 00xxx) | 5-digit | 112 | 0 |
| ETFs / leverage / bond ETFs (6-digit) | 6-digit | 4868 | 0 |
| **Total** | — | 6957 | 720 |

**Inference (not direct observation):** The ~1969 four-digit non-0-prefix stocks are assumed to be common stocks (TWSE + TPEx). This cannot be confirmed without a reference master from TWSE/TPEx. The ~4980 non-4-digit stocks are assumed to be ETFs, leverage funds, and special instruments.

---

## 5. TRADEABLE_COMMON_STOCK_UNIVERSE Definition (Proposal)

For short-term trading strategy research:

```
TRADEABLE_COMMON_STOCK_UNIVERSE = {
  Exchange: TWSE ∪ TPEx,
  Security Type: 普通股 (ordinary share only),
  Listing Status: 上市 OR 上櫃 (not 興櫃, not delisted at signal_date),
  Code Format: 4-digit (1000–9999 range),
  Exclusions: {
    0050 (and all benchmark ETFs starting with '0'),
    5-digit (00xxx) ETFs,
    6-digit (006xxx, 009xxx) ETFs/leverage funds,
    ETNs, TDRs, warrants, preferred shares
  },
  Minimum Liquidity: undefined (not currently enforced),
  Minimum Price: undefined,
  Suspension: exclude on suspension date
}
```

**0050 Treatment:** 0050 (元大台灣50) is designated **Benchmark / Proxy** only. It is NOT part of the common stock tradeable universe. It MUST NOT be included in signal generation, scoring, or strategy comparisons as a candidate stock.

**Current implementation gap:** The signal generation pipeline does NOT enforce this universe definition. It computes signals for all stocks in daily_prices, including ETFs (see Part 3 of `stock_master_integrity_session37.md`).

---

## 6. Universe Size Estimates

| Universe | Estimated Count | Confidence | Source |
|---|---|---|---|
| TWSE common stocks (current) | ~900–1000 | MEDIUM | Inferred from daily_prices 4-digit + stocks master |
| TPEx common stocks (current) | ~700–900 | LOW | Inferred from orphan 4-digit counts; unverified |
| Total common stock universe | ~1700–1900 | LOW | Sum of above estimates |
| Stocks in current master | 826 (TWSE only) | HIGH | Direct observation |
| TPEx in stocks master | 0 | HIGH | Direct observation |
| ForwardSignals actual universe | ~655 securities | HIGH | Direct observation (Oct 12–28) |
| ForwardSignals eligible (common stocks only) | ~394–410 | MEDIUM | In-master + orphan 4-digit estimate |
| ForwardSignals ineligible (ETFs) | ~57 | HIGH | Direct observation (5+6 digit codes) |

---

## 7. 6957 — What Does This Number Actually Represent?

**Observed:** On 2026-11-04, daily_prices contains 6957 distinct stock_ids.

**Breakdown (inferred):**
- ~1969 four-digit non-0-prefix → common stocks (TWSE + TPEx estimated)
- ~8 four-digit 0-prefix → ETF/benchmark codes  
- ~112 five-digit → ETFs (00xxx series)
- ~4868 six-digit → Leverage ETFs, inverse ETFs, bond ETFs, warrants (006xxx, 009xxx)

**Conclusion:** 6957 is NOT "total tradeable common stocks." It includes ~5000 ETF/special instruments. The actual common stock count on that day is estimated at ~1977 (but cannot be confirmed without authoritative TWSE/TPEx reference data).

**Key concern:** Prior sessions used 6957 as the "full market" threshold marker, which is correct as a *data completeness indicator* (Nov 4 = full batch loaded) but should NOT be interpreted as "6957 common stocks available for selection."

---

## 8. Recommended Actions (Approval Required)

| Action | Priority | Authorization Needed |
|---|---|---|
| Load TPEx common stocks into stocks master (ETL) | HIGH | Schema migration + write authorization |
| Add `security_type` column to stocks (common/ETF/etc.) | HIGH | Schema migration |
| Add `exchange` column distinguishing TWSE vs TPEx | HIGH | Schema migration |
| Add delisted stocks with delist_date to master | HIGH | Write authorization |
| Filter signal generation to common stocks only | HIGH | Production code change |
| Exclude ETFs from forward_signals explicitly | HIGH | Production code change |
| Load historical delisting data to fix survivorship | MEDIUM | Write authorization |

None of the above are executed in this session.
