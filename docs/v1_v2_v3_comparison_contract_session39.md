# V1/V2/V3 Comparison Contract — Session 39

**Date:** 2026-11-08  
**Session:** 39  
**Version:** session39_v1

---

## 1. Shared Framework Contract

All strategy versions MUST use these identical inputs when compared:

| Dimension | Required Value | Status |
|---|---|---|
| Eligible universe | Dataset B (verified TWSE/TPEx common stocks only) | DEFINED |
| Evaluation period | Same trading dates for all versions | DEFINED |
| Benchmark | 0050 gross return (open[fill_date] → close[exit_date]) | DEFINED |
| Trading calendar | Taiwan Stock Exchange (TradingCalendarService) | DEFINED |
| Fees | 0.585% (buy+sell combined, from execution_simulator.py) | READY |
| Capital assumption | Equal weight per signal; no leverage | DEFINED |
| Position sizing | 1 unit per signal | DEFINED |
| Outcome definition | Net return = gross return − 0.585% | DEFINED |
| Dedup policy | 20D dedup by stock_id for inference; raw N reported separately | DEFINED |

---

## 2. Per-Version Entry Rules (Must NOT be changed for comparison)

| Version | Entry Rule | Comparison Engine |
|---|---|---|
| V1 | BUY/STRONG_BUY → NEXT_OPEN (no filter) | B_v1v2 |
| V2 | BUY/STRONG_BUY → ENTRY_READY only → NEXT_OPEN | B_v1v2 (note: shares label) |
| Hybrid V1 | V2_label + P1–P4 rules → DIRECT or WAIT | C_hybrid |
| V3 | V3EntryTimingAnalyzer → DIRECT_ENTRY etc. | D_v3 |

**Rule**: Each version's entry logic is preserved exactly. The contract only standardizes what happens BEFORE and AFTER entry — not the entry decision itself.

---

## 3. Paired Comparison Design

For a valid paired comparison (same stock, same date):

```
For each (stock_id, trade_date) in Dataset B:
    V1_entry = NEXT_OPEN (always fills)
    V2_entry = NEXT_OPEN if ENTRY_READY else SKIP
    Hybrid_entry = NEXT_OPEN or WAIT based on P1-P4
    V3_entry = DIRECT_ENTRY / WAIT / NO_ENTRY based on V3EntryTimingAnalyzer
    
    If V1_entry and V2_entry both have outcome:
        pair_alpha = V2_net_return - V1_net_return
        (positive = V2 improved on V1)
```

**Current status**: Paired comparison NOT POSSIBLE — fwd_return_20d = NULL for all v8.0 signals.

---

## 4. Performance Metrics Design

### Return Metrics
| Metric | Horizon | Status |
|---|---|---|
| Net Return | 5D / 20D / 60D | INSUFFICIENT_DATA (all NULL) |
| Alpha vs 0050 | 5D / 20D / 60D | INSUFFICIENT_DATA |
| Median Return | 20D | INSUFFICIENT_DATA |
| Win Rate | 20D | INSUFFICIENT_DATA |
| Profit Factor | 20D | INSUFFICIENT_DATA |

### Risk Metrics
| Metric | Status |
|---|---|
| Maximum Drawdown | INSUFFICIENT_DATA |
| Volatility | INSUFFICIENT_DATA |
| Downside Risk | INSUFFICIENT_DATA |
| Turnover | COMPUTABLE (from signal counts) |
| Transaction Costs | COMPUTABLE (0.585% per trade) |
| Exposure | COMPUTABLE (from signal dates) |

### Statistical Confidence
| Metric | Status |
|---|---|
| Raw N | 2236 (A) / 2023 (B) |
| 20D Dedup N | ~290–360 estimate (7 dates × ~50/date) |
| Confidence Interval | INSUFFICIENT_DATA |
| Effect Size | INSUFFICIENT_DATA |
| Bootstrap CI | INSUFFICIENT_DATA |

**All return-based metrics output `INSUFFICIENT_DATA` until 2026-12-02.**

---

## 5. Coverage Comparison (Computable Now)

| Version | Signals (Dataset B) | Filter Rate | Stocks |
|---|---|---|---|
| V1 | 128 (buy+strong_buy subset) | 0% (no filter) | ~75 |
| V2 | Subset of V1 where ENTRY_READY | Requires V2ShadowSignal lookup | — |
| Hybrid V1 | Subset of V1 based on P1–P4 | Requires regime data | — |
| V3 | Subset of V1 based on V3EntryTimingAnalyzer | Requires price history | — |

**Note**: Only v8.0 signals with decision_label IN ('buy', 'strong_buy') are actionable for V1/V2/V3 — this is 128 of 2236 total v8.0 valid signals (5.72%).

---

## 6. Missingness Analysis

| Category | Count | Impact |
|---|---|---|
| Missing outcome (fwd_return_20d = NULL) | 2,236 | Blocks all return analysis |
| ETF contamination (Dataset A only) | 213 | Removed in Dataset B |
| Universe mismatch (48% coverage) | ~1,100 (est.) | CONDITIONAL for coverage |
| Overlapping hold periods | All 7 dates | Cluster inference required |
| **Comparable signals today** | **0** | NOT_COMPARABLE |

---

## 7. Comparison Verdict

**`COMPARISON_BLOCKED`** — Zero comparable outcomes available.

The framework is DESIGNED and READY — all contracts defined, Dataset B established, version registry complete. The comparison cannot be EXECUTED until 2026-12-02 (earliest outcomes).
