# Stock Selection & Entry Timing Assessment — Session 41

**Date:** 2026-11-09
**Session:** 41
**Verdict:** STOCK_SELECTION_UNIDENTIFIABLE, ENTRY_TIMING_UNIDENTIFIABLE

---

## 1. Why Stock Selection Is Unidentifiable

### Identical Scoring Engine

V1, V2, V3, and Hybrid V1 ALL use the same scoring engine (`foe_v1`, MODEL_VERSION v8.0).

The comparison V3 vs A_direct is therefore:
- **Same stocks** (same foe_v1 buy/strong_buy signals)
- **Same signal strength** (same scores from same engine)
- **Different: when/whether to enter** (V3 applies entry timing filter)
- **Different: exit rules** (V3 uses V3 stop/target parameters)

There is NO stock selection difference between V3 and A_direct — they receive identical signals. Any performance difference comes from entry/exit rules, not stock selection.

### DIRECT_ENTRY Paired Analysis

For the 82 signals where V3 says DIRECT_ENTRY:
| Metric | Value |
|---|---|
| V3 mean net return | -2.79% |
| A_direct mean net return | -2.23% |
| V3 paired alpha vs A_direct | **-0.56%** |

V3 DIRECT_ENTRY **underperforms** A_direct by 0.56%. This is the opposite of "superior stock selection."

**Interpretation:** The -0.56% gap is likely due to exit rule differences:
- V3 uses its own stop/target parameters (tighter?)
- A_direct uses reconstructed stop/target from V1 rules
- In declining market, V3's exit rules caused slightly earlier stops or different target levels

Since V3 is marginally worse (-0.56%) even for direct fills, the case for "stock selection advantage" is absent.

---

## 2. Why Entry Timing Is Unidentifiable

### Comparison Engine Architecture

The V3ComparisonEngine assigns:
- **DIRECT_ENTRY**: V3 enters at next open (same as A_direct)
- **WAIT_BREAKOUT_CONF**: V3 "waits" → comparison engine returns 0% (no fill credit)
- **WAIT_MA20_PULLBACK**: Same as above
- **AVOID_CHASING**: V3 avoids → 0% return
- **NO_ENTRY**: V3 avoids → 0% return

For WAIT decisions, the comparison engine **cannot track the actual delayed fill**:
- If V3 eventually fills at D+2, D+3... the comparison counts it as 0%
- The actual entry price benefit is UNCREDITED in this analysis
- We cannot distinguish "V3 waited and missed a rising stock" from "V3 waited and entered at a better price"

### WAIT_BREAKOUT_CONF Result

| Metric | Value |
|---|---|
| n signals | 74 (53 eventually filled, 21 no fill) |
| V3 mean net | -1.08% (mix of fills and 0%) |
| A_direct mean net | -2.78% |
| V3 paired alpha vs A_direct | +1.70% |

The +1.70% advantage for WAIT_BREAKOUT_CONF includes:
- Signals where V3 eventually filled at a better (delayed) price
- Signals where A_direct entered and declined; V3 never filled (0% vs negative)
- These two effects cannot be separated

### Conclusion

Entry timing benefit is **structurally unidentifiable** using the current comparison engine. A dedicated analysis tracking actual delayed fill dates and prices would be required (requires accessing future price data for the WAIT cases).

---

## 3. Summary

| Component | Verdict | Evidence | Limitation |
|---|---|---|---|
| Stock Selection | UNIDENTIFIABLE | Same foe_v1 engine | No differentiation possible |
| Entry Timing | UNIDENTIFIABLE | WAIT fills uncredited | Architecture prevents measurement |
| Exit Rule Effect | PARTIAL | DIRECT_ENTRY -0.56% | Confounded by exit rule differences |
| Avoidance Quality | DESCRIPTIVE | AVOID_CHASING +6.38% | Descriptive, not causal |

**None of V3's advantages can be attributed to superior stock selection or entry timing using this dataset and comparison engine.**
