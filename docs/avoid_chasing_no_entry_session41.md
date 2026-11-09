# AVOID_CHASING / NO_ENTRY Analysis — Session 41

**Date:** 2026-11-09
**Session:** 41
**Causal Verdict:** DESCRIPTIVE_ASSOCIATION_ONLY

---

## 1. What AVOID_CHASING and NO_ENTRY Mean

V3 rejects signals based on entry rule conditions:
- **AVOID_CHASING**: Stock's MA20 gap % exceeds threshold → entry would chase an overextended move
- **NO_ENTRY**: V3 evaluates signal as not meeting minimum entry quality threshold

Both result in **0% return** for V3 (no position opened). A_direct always enters these signals.

---

## 2. Descriptive Statistics

### AVOID_CHASING (n=41)

| Metric | Value |
|---|---|
| V3 return (no fill) | 0.00% |
| A_direct mean net return | **-6.38%** |
| V3 paired alpha vs A_direct | **+6.38%** |
| V3 alpha vs 0050 benchmark | +0.91% |
| A_direct returns negative | 76% (31/41) |
| A_direct std | 10.14% (high variance) |

**Interpretation**: 76% of AVOID_CHASING stocks declined in A_direct. The mean decline was -6.38%. V3's avoidance resulted in +6.38% paired advantage for these 41 signals. However, 24% of avoided stocks were actually POSITIVE for A_direct — V3 missed gains on those.

### NO_ENTRY (n=13)

| Metric | Value |
|---|---|
| V3 return (no fill) | 0.00% |
| A_direct mean net return | **-0.67%** |
| V3 paired alpha vs A_direct | **+0.67%** |
| V3 alpha vs 0050 benchmark | +1.41% |
| A_direct returns negative | 54% (7/13) |

**Interpretation**: NO_ENTRY stocks were mixed — only slight negative (-0.67%) for A_direct. V3's avoidance of these was not strongly justified by outcome. These stocks actually outperformed 0050 (1.41% alpha vs benchmark).

---

## 3. Counterfactual Analysis

The key question: *Did V3 avoid these signals BECAUSE they would decline, or BECAUSE they triggered certain entry rules?*

**We cannot answer this.** This is the fundamental confound:

V3's AVOID_CHASING rule is:
```
ma20_gap_pct > MA20_PULLBACK_UPPER (3%)
```
Stocks with MA20 gap > 3% also tend to be more extended/overvalued in declining markets.

**Correlation ≠ Causation:**
- In a declining market, overextended stocks (high MA20 gap) tend to fall more
- V3's rule that avoids them correlates with avoiding worse performers
- This correlation may be spurious — in a rising market, overextended stocks might continue higher
- We have ZERO data on V3's avoidance quality in a rising market

---

## 4. Confounding Factors

1. **Market decline confounds**: The Oct 09-16 window was a declining market (0050 -2.16% avg). Overextended stocks decline more in falling markets → AVOID_CHASING looks good precisely because the market was falling.

2. **No randomized control**: V3 avoids based on entry rules, not expected return prediction. We cannot know the counterfactual return.

3. **Same scoring engine**: Both V3 and A_direct use foe_v1. Any "selection skill" is identical between them.

4. **7 dates, single regime**: 41 AVOID_CHASING signals across 7 dates = effective N ≈ 7 (same cluster issue as main analysis).

5. **Selection bias**: V3 avoids MA20-extended stocks. In declining markets, these tend to be laggards. But in bull markets, they tend to be leaders. The "quality" of avoidance is regime-dependent.

---

## 5. What AVOID_CHASING Does and Does NOT Tell Us

| Claim | Valid? | Reason |
|---|---|---|
| "V3 avoided 41 stocks that declined -6.38% on avg" | Yes | Direct observation |
| "V3's avoidance was skillful" | No | Descriptive association, not causal |
| "AVOID_CHASING protects against losses in declining markets" | Conditional | Only when MA20-extended stocks underperform more than average |
| "AVOID_CHASING adds value in bull markets" | No evidence | Zero data points from bull-market hold periods |
| "V3 would have similar avoidance quality over 100+ dates" | Unknown | Single-regime, 7-date observation |

---

## 6. Combined Avoidance (AVOID_CHASING + NO_ENTRY): 54 signals

| Metric | Value |
|---|---|
| Combined paired alpha vs A_direct | +4.37% |
| A_direct mean for avoided signals | -4.37% |
| Avoidance rate | 19.7% (54/274) |

---

## 7. Verdict

**DESCRIPTIVE_ASSOCIATION_ONLY**

The avoidance data shows a strong descriptive association between V3's rejection decisions and poor A_direct outcomes in Oct 2026. This is consistent with MARKET_AVOIDANCE_DRIVEN verdict.

It does NOT constitute evidence of a generalisable avoidance skill. Specifically:
- AVOID_CHASING performs well because declining markets punish overextended stocks
- NO_ENTRY performance is weak (+0.67% vs A_direct)
- Both effects are measured in a single declining-market regime with 7 effective dates
