# Research Clean Universe Comparison — Session 38

**Date:** 2026-11-08  
**Session:** 38  
**Version:** session38_v1

---

## 1. Purpose

Establish three canonical signal datasets (A, B, C) for future performance comparisons.
Quantify the size impact of ETF filtering. Provide sensitivity boundary.

---

## 2. Dataset Definitions

### Dataset A — Original v8.0 Signals

| Property | Value |
|---|---|
| Total signals | 2,236 |
| Unique stocks | 410 |
| ETF signals included | 213 (9.52%) |
| TWSE common signals | 2,023 (90.47%) |
| TPEx common signals | 0 |
| Label | `A_original` |
| Use case | Baseline; replication of all prior session analyses |

### Dataset B — Clean (Verified Common Stocks Only)

| Property | Value |
|---|---|
| Total signals | **2,023** |
| Unique stocks | **368** |
| ETF signals removed | 213 (9.52% reduction) |
| TWSE common signals | 2,023 (100%) |
| TPEx common signals | 0 |
| Label | `B_clean` |
| Use case | Official common-stock-only research; preferred for future analyses |
| Filtering method | SecurityClassificationService — official TWSE/TPEx API cross-reference |

### Dataset C — Sensitivity Boundary

| Property | Value |
|---|---|
| Total signals | **2,023** |
| ETF signals removed | 213 |
| Other non-common types removed | 0 |
| Label | `C_sensitivity` |
| Note | In this case B = C because there are no non-ETF, non-common stocks in FS v8.0 |

**B = C for Session 38**: All 42 non-common stock_ids in FS v8.0 are confirmed ETFs (0-prefix). There are no "borderline" cases (UNKNOWN or PROBABLE_DELISTED in signals), so the sensitivity boundary coincides with the clean set.

---

## 3. Impact Analysis: A vs B

### Signal count impact

| | Dataset A | Dataset B | Δ |
|---|---|---|---|
| Signals | 2,236 | 2,023 | −213 (−9.52%) |
| Unique stocks | 410 | 368 | −42 (−10.2%) |

### Forward return impact (current status)

| | Status |
|---|---|
| fwd_return_20d for v8.0 | **NULL** — 20d window expires 2026-12-02 |
| Mean signal return A vs B | **UNCOMPUTABLE** until returns available |
| Sharpe ratio A vs B | **UNCOMPUTABLE** |

**The quantitative performance impact of ETF removal cannot be measured until Dec 2026.**

### Qualitative impact estimate

The 42 ETF stock_ids include:
- **0050** (元大台灣50): tracks TWSE market-cap index → returns approximate TWSE market returns
- **0056** (元大高股息): high-dividend ETF → returns skewed toward dividend-paying stocks
- **5/6-digit ETFs**: sector and leveraged ETFs → highly varied return profiles

If ETFs generated signals during a period when ETFs outperformed the common stocks selected:
- Dataset A return > Dataset B return (ETF inflation)

If ETFs underperformed common stocks:
- Dataset A return < Dataset B return (ETF drag)

**Direction is unknown without outcome data.**

---

## 4. Historical Backtest Impact

For the historical in-sample backtest (Jul 2024–May 2026):

| Era | ETF contamination | Dataset |
|---|---|---|
| Backtest era | 0% (ETFs not in signal pool) | Implicitly Dataset B |
| Forward era (Oct 2026) | 9.52% | Dataset A (current) |

This confirms that the **historical backtest was implicitly ETF-clean** (Dataset B equivalent). The contamination is a NEW issue that appeared in the forward era. The +3.66ppt in-sample advantage was therefore measured WITHOUT ETF contamination.

**Implication**: The in-sample comparison (V3 vs V2) is internally consistent and unaffected by ETF contamination. The contamination affects ONLY the forward era signals.

---

## 5. Recommendation

| Use Case | Recommended Dataset |
|---|---|
| Replicating Session 27–28 backtest results | A (matches what was computed) |
| Future research on V3 effectiveness | **B** (clean, official-verified) |
| Sensitivity check | C (= B in Session 38) |
| Any forward era analysis (Oct 2026+) | **B** — mandatory ETF filter required |

**CLEAN_UNIVERSE_VERDICT: `B_RECOMMENDED`** — Dataset B is the canonical reference for all future common-stock research.
