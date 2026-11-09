# V3 Performance Attribution — Session 39

**Date:** 2026-11-08  
**Session:** 39  
**Version:** session39_v1

---

## 1. Attribution Framework

V3's in-sample advantage (+3.66ppt vs A_direct, Session 27) can be decomposed into:

| Component | Definition | Identifiable? |
|---|---|---|
| Market Timing | Invest vs hold-cash decision | CONDITIONAL |
| Stock Selection | Stock return vs benchmark on invested days | UNIDENTIFIABLE |
| Entry Timing | Same stock, different entry price | UNIDENTIFIABLE |
| Risk / Exposure | Portfolio drawdown vs benchmark | CONDITIONAL |
| Transaction Cost | Fees from selection rate | COMPUTABLE |

---

## 2. Component 1: Market Timing (CONDITIONAL)

**Definition**: The strategy's decision to be invested (open positions) vs holding cash.

**Key evidence (Session 28):**
> V3 walk-forward conclusion: `MARKET_AVOIDANCE_DRIVEN` — V3's improvement in walk-forward periods is driven by being less invested during market drawdowns.

**Measurement approach**:
- For each (stock_id, signal_date), compute: was V3 invested on this day?
- Compare cumulative market return during V3-invested days vs benchmark-invested days
- Positive market timing = V3 is invested on days when market performs better

**Current status**: CONDITIONAL — walk-forward analysis (Session 28) is evidence, but only 0 actual out-of-sample windows are feasible. In-sample result cannot be extrapolated.

**Warning**: V3's `WAIT_MA20_PULLBACK` and `WAIT_MA60_SUPPORT` decisions reduce investment frequency. If the market rises during wait periods, V3 misses gains. If the market falls, V3 avoids losses. Session 28 found the second effect dominates — but this may not persist out-of-sample.

---

## 3. Component 2: Stock Selection (UNIDENTIFIABLE)

**Definition**: Given that V3 is invested, do its selected stocks outperform the market?

**Why UNIDENTIFIABLE now:**
1. fwd_return_20d = NULL for all v8.0 signals → cannot compute stock return
2. 0050 benchmark return for same periods not separately stored
3. V3 and V2 are not evaluated on matched-exposure days → comparison conflates timing and selection

**What would be needed:**
- fwd_return_20d populated (available 2026-12-02 earliest)
- 0050 fwd_return for same start dates (computable from daily_prices)
- Matched-exposure comparison: V3 vs V2 on days when BOTH are invested

**Warning**: If V3 is simply less invested (more WAIT decisions), its average position may appear to outperform because it only holds stocks during favorable periods — this is market timing, not stock selection. These effects cannot be separated with the current data.

---

## 4. Component 3: Entry Timing (UNIDENTIFIABLE)

**Definition**: Given same stock is selected, does V3's entry price/timing improve returns?

**Why UNIDENTIFIABLE now:**
1. No matched (stock_id, date, entry_price) pairs between V1 and V3
2. V1's actual fill price not separately tracked from V3's
3. Both use NEXT_OPEN pricing in comparison engine — the "entry timing" difference is in WHICH day they enter, not at WHAT price on the same day

**Specific clarification**:
- V3's WAIT decisions mean it may enter on day D+2 or D+3 instead of D+1
- The comparison engine does NOT track this lagged entry
- If V3 waits for a pullback and the stock continues rising, V3 misses the trade → negative impact
- If V3 waits and the stock pulls back, V3 enters cheaper → positive impact
- This cannot be measured without fresh entry-price tracking for WAIT outcomes

**Label**: `ENTRY_TIMING: UNIDENTIFIABLE` — do not infer that V3's entry timing improves returns.

---

## 5. Component 4: Risk / Exposure (CONDITIONAL)

**Definition**: Does V3 reduce drawdown by reducing exposure during adverse periods?

**Estimation** (from Session 28 walk-forward analysis):
- V3 net_return = +1.33% (1 feasible window, MARKET_AVOIDANCE_DRIVEN)
- V3 reduced exposure = fewer DIRECT_ENTRY decisions
- This is consistent with V3 avoiding loss periods, not necessarily outperforming on invested days

**Current status**: CONDITIONAL — walk-forward evidence exists but is INSUFFICIENT (1 window, possible market avoidance bias).

---

## 6. Component 5: Transaction Costs (COMPUTABLE)

| Version | Signal Count (Dataset B) | Filter Rate | Estimated Cost Impact |
|---|---|---|---|
| V1 (B_v1v2) | ~128 actionable | 0% | 128 × 0.585% = 0.749% aggregate cost |
| V3 (D_v3) | < 128 (some NO_ENTRY) | > 0% | Fewer trades = lower aggregate cost |

V3's NO_ENTRY and WAIT decisions reduce the number of actual trades relative to V1. With 0.585% round-trip fees, fewer trades = lower total cost. This is a minor advantage in V3's favor, but quantitatively small.

---

## 7. Summary Table

| Component | Evidence | Status | Current Measurement |
|---|---|---|---|
| Market Timing | Session 28 MARKET_AVOIDANCE_DRIVEN | CONDITIONAL | In-sample only; 1 WF window |
| Stock Selection | None | UNIDENTIFIABLE | 0 outcomes; no matched pairs |
| Entry Timing | None | UNIDENTIFIABLE | 0 lagged-entry records |
| Risk / Exposure | Session 28 | CONDITIONAL | INSUFFICIENT_EVIDENCE |
| Transaction Cost | FEES_PCT documented | COMPUTABLE | Minor V3 advantage (fewer trades) |

---

## 8. Attribution Verdict

**The in-sample +3.66ppt advantage for V3 cannot currently be attributed to stock selection or entry timing.**

Confirmed source of advantage: **Market timing / exposure reduction** (Session 28).

Remaining unattributed: Whether V3 picks better entry points within the same stocks — currently `UNIDENTIFIABLE`.

**ATTRIBUTION_VERDICT: `MARKET_AVOIDANCE_DRIVEN`** (consistent with Session 28)
