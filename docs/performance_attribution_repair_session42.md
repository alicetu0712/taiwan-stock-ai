# Performance Attribution Repair — Session 42

**Date:** 2026-11-09
**Session:** 42
**Verdict:** MARKET_AVOIDANCE_DRIVEN (confirmed, attribution numbers corrected)

---

## 1. What Was Wrong in S40 Attribution

| Claim (S40) | Was Wrong Because | Corrected Value |
|---|---|---|
| AVOID_CHASING alpha = +3.87% "vs A_direct" | Actually vs 0050 benchmark | +6.38% vs A_direct (larger) |
| DIRECT_ENTRY alpha = +2.86% "vs A_direct" | Actually vs 0050 benchmark | **-0.56% vs A_direct (sign flip)** |
| NO_ENTRY alpha = +4.30% "vs A_direct" | Actually vs 0050 benchmark | +0.67% vs A_direct |
| Market context: 0050 avg = -4.65% | Used wrong signal dates | -2.16% (Oct 09-16 actual) |

---

## 2. Corrected Attribution (S41 / S42)

V3's advantage in October 2026 comes entirely from **not entering** when V1/V2 would.

| V3 Decision | n Signals | Paired Alpha vs A_direct | Interpretation |
|---|---|---|---|
| AVOID_CHASING | 41 | **+6.38%** | V3 avoided stocks that fell -6.38% in A_direct |
| NO_ENTRY (threshold) | 13 | +0.67% | V3 avoided stocks that fell minimally |
| DIRECT_ENTRY | ~167 | **-0.56%** | V3 direct fills slightly worse than A_direct |

**AVOID_CHASING is the dominant driver.** V3 decision to skip 41 "chasing" signals saved the most: those stocks dropped -6.38% on average in A_direct.

The October 2026 market context (Taiwan market decline, 0050 at -2.16%) amplifies market-avoidance strategies.

---

## 3. What DIRECT_ENTRY Being Negative Means

DIRECT_ENTRY (-0.56% vs A_direct) means:
- V3 and A_direct enter the same stocks (same foe_v1 engine, same universe)
- V3 direct fills slightly underperform A_direct direct fills
- This suggests minor differences in exit rule or timing, not superior stock selection
- **Stock selection advantage: UNIDENTIFIABLE** (same engine)
- **Entry timing advantage: UNIDENTIFIABLE** (WAIT fills not tracked)

---

## 4. Market Context Dependence

The AVOID_CHASING advantage is **regime-dependent**. In a rising market:
- AVOID_CHASING would skip stocks that rally → V3 performance drag
- The October 2026 single-regime result is insufficient to claim general superiority

This is consistent with MARKET_AVOIDANCE_DRIVEN: the strategy avoids entry at market extremes, which helps in bear markets and hurts in bull markets.

---

## 5. Attribution Verdict

```
ATTRIBUTION = "MARKET_AVOIDANCE_DRIVEN_CONFIRMED"
AVOID_CHASING: +6.38% paired alpha (n=41, dominant driver)
DIRECT_ENTRY:  -0.56% paired alpha (slight underperformance)
NO_ENTRY:      +0.67% paired alpha (minimal contribution)
Market regime: declining (0050 -2.16% over comparison window)
Stock selection: UNIDENTIFIABLE
Entry timing:   UNIDENTIFIABLE
```
