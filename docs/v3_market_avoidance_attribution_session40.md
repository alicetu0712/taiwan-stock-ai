# V3 Market Avoidance Attribution — Session 40

**Date:** 2026-11-09  
**Session:** 40  
**Window:** Oct 2026, 5D horizon  
**Total V3 Alpha vs A_direct:** +3.66ppt

---

## 1. Attribution Framework

| Component | Method | Status |
|---|---|---|
| Market Avoidance (Exposure Reduction) | Estimated from fill rate × A_direct mean | ESTIMATED |
| Stock Selection within Invested (DIRECT_ENTRY) | Subgroup analysis | PARTIAL |
| Avoidance Quality (AVOID_CHASING + NO_ENTRY) | Subgroup analysis | QUANTIFIED |
| Entry Timing (Price Improvement from Waiting) | Not trackable | UNIDENTIFIABLE |
| Transaction Cost Savings | Computed from fill rate × FEES_PCT | QUANTIFIED |

---

## 2. Market Context

| Metric | Value |
|---|---|
| Signal dates | 2026-10-12 to 2026-10-28 (7 dates) |
| Market regime at signal_date | ALL 'bull' (237/237 v8.0 signals) |
| 0050 average 5D return | **-4.65%** (market declined during hold) |
| 0050 by date | -6.09%, -4.42%, -1.82%, +0.74%, -4.32%, -6.07%, -10.58% |

**Key context**: The market DECLINED significantly during the 5D hold periods. V3's lower fill rate means fewer positions during this decline — this is the primary driver of V3's alpha.

---

## 3. Component Analysis

### Component 1: Market Avoidance (Exposure Reduction) — ESTIMATED

| Metric | Value |
|---|---|
| V3 fill rate | 68.6% (188/274) |
| A_direct fill rate | 100% (274/274) |
| V3 skipped signals | 86 (31.4%) |
| A_direct mean net return | -3.1959% |
| Exposure reduction estimate | +1.00ppt (≈27% of total alpha) |

**Formula**: `(1 - 0.686) × (0% - (-3.1959%)) = 0.314 × 3.1959% ≈ 1.00%`

**Caveat**: This assumes avoided signals would perform like average A_direct. Actual result depends on which stocks V3 avoided.

---

### Component 2: Stock Selection within Invested (PARTIAL)

| V3 Decision | N | Mean Net Alpha vs A_direct |
|---|---|---|
| DIRECT_ENTRY | 82 | +2.86% |

**Interpretation**: For the 82 stocks where V3 says DIRECT_ENTRY, it outperforms A_direct by +2.86%. BUT this is confounded by **exit rule difference** — V3 uses its own stop/target while A_direct uses reconstructed values. Cannot isolate stock selection from exit rule effect.

**Status**: PARTIAL — cannot cleanly attribute to stock selection alone.

---

### Component 3: Avoidance Quality — QUANTIFIED

| Decision | N | Mean Net Alpha | Meaning |
|---|---|---|---|
| AVOID_CHASING | 41 | +3.87% | Those stocks fell -3.87% under A_direct; V3 correctly avoided |
| NO_ENTRY | 13 | +4.30% | Largest declines; V3 completely avoided |
| Combined | 54 | ~+3.98% | V3 correctly screened out the worst performers |

**Interpretation**: V3 correctly identified 54 stocks that would significantly decline and avoided them. This IS a form of stock selection / market avoidance.

---

### Component 4: Entry Timing — UNIDENTIFIABLE

**Why unidentifiable**:
- WAIT_MA20_PULLBACK and WAIT_BREAKOUT_CONFIRMATION decisions result in LATER fills (D+2, D+3)
- The comparison engine counts all WAIT decisions as 0% return (no fill)
- If V3 actually fills later at a better price, that benefit is CREDITED as 0% here but would be positive in reality
- Cannot distinguish "V3 waited and missed a rising stock" from "V3 waited and entered at a better price"

**Status**: UNIDENTIFIABLE — do not infer from current data.

---

### Component 5: Transaction Cost Savings — QUANTIFIED

| Metric | Value |
|---|---|
| Skipped signals | 86/274 (31.4%) |
| FEES_PCT | 0.585% per round-trip |
| Cost saving | 0.314 × 0.585% ≈ **0.18ppt** |

**Minor**: Transaction cost saving = 0.18ppt of 3.66ppt total alpha (4.9%).

---

## 4. Attribution Summary

| Component | Estimated Contribution | Status | Note |
|---|---|---|---|
| Market Avoidance | ~1.00ppt (27%) | ESTIMATED | Lower bound; actual may be higher if avoided stocks were worse than avg |
| Avoidance Quality | Captured in fill rate benefit | QUANTIFIED | AVOID_CHASING + NO_ENTRY correctly identified declining stocks |
| Stock Selection (DIRECT_ENTRY) | Partially in +2.86% DIRECT alpha | PARTIAL | Confounded by exit rule difference |
| Entry Timing | None | UNIDENTIFIABLE | WAIT fills not tracked; counted as 0% |
| Transaction Costs | ~0.18ppt (5%) | QUANTIFIED | Minor |

---

## 5. Attribution Verdict

**`MARKET_AVOIDANCE_DRIVEN`** (consistent with Sessions 27-28)

The Oct 2026 window provides the first QUANTITATIVE confirmation:
- Market declined (0050 avg -4.65%)
- V3 filled only 68.6% of signals → 31.4% at 0% return during decline
- Avoidance correctly targeted the worst-performing stocks
- This matches the MARKET_AVOIDANCE_DRIVEN verdict from Session 28 walk-forward analysis

**Stock selection within invested subset (DIRECT_ENTRY, +2.86%)** is a secondary contributor but cannot be cleanly separated from exit rule differences.

**Entry timing benefit** is UNIDENTIFIABLE and should NOT be claimed.

---

## 6. What This Does NOT Prove

| Claim | Valid? |
|---|---|
| "V3 picks better stocks than V1" | No — same scoring engine (foe_v1); stock selection is entry timing filter only |
| "V3's entry timing improves fill price" | No — UNIDENTIFIABLE |
| "V3 will outperform in bull markets" | No — advantage depends on market declining during hold period |
| "V3 is definitively better than V1/V2" | No — RANKING_CONDITIONAL, single regime, 7 dates |
