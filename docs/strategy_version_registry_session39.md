# Strategy Version Registry — Session 39

**Date:** 2026-11-08  
**Session:** 39 — Clean Research Universe & V1/V2/V3 Comparison Foundation  
**Version:** session39_v1

---

## Critical Finding: "V1/V2/V3" Are Entry Timing Variants, Not Scoring Models

> All four strategy variants (V1, V2, Hybrid V1, V3) use the **identical underlying scoring engine**  
> (foe_v1 / MODEL_VERSION v8.0). They differ **only in entry timing rules** applied after  
> the scoring engine generates BUY/STRONG_BUY signals.
>
> The user's question "is V3 better than V1/V2?" is therefore asking:  
> **"Does a more sophisticated entry timing filter improve trading performance?"**  
> NOT: "Is the scoring model improving over time?"

---

## Version Registry

### V1 — Signal Only (Original)

| Property | Value |
|---|---|
| `version_id` | `v1_signal_only` |
| **Status** | **PARTIAL** |
| Scoring engine | foe_v1 / MODEL_VERSION v8.0 |
| Entry rule | BUY/STRONG_BUY → NEXT_OPEN (no additional filter) |
| Exit rule | stop_price or target1 or 20D horizon |
| Parameter hash | None (thresholds unversioned) |
| Frozen commit | None |
| Code file | `src/research/v3_comparison_engine.py` (STRATEGY_B) |
| Comparison engine | `B_v1v2` |

**Unverified items (3):**
1. No parameter hash for BUY/STRONG_BUY thresholds
2. Historical threshold values not recorded
3. Transaction cost assumptions not explicitly documented

---

### V2 — Entry Timing Filtered

| Property | Value |
|---|---|
| `version_id` | `v2_entry_timing` |
| **Status** | **PARTIAL** |
| Scoring engine | foe_v1 / MODEL_VERSION v8.0 |
| Entry rule | BUY/STRONG_BUY → EntryTimingAnalyzer → ENTRY_READY only → NEXT_OPEN |
| Filter | MA20 level (no MA60, no slope) |
| Exit rule | stop_price or target1 or 20D horizon |
| Parameter hash | None (embedded in entry_timing.py) |
| Frozen commit | None |
| Code file | `src/analyzers/entry_timing.py` |
| Comparison engine | `B_v1v2` (shares label with V1 in comparison engine) |

**Unverified items (3):**
1. EntryTimingAnalyzer MA20 thresholds embedded without hash
2. No frozen commit documented for EntryTimingAnalyzer
3. Exact V2 rules used in Sessions 23–26 not reconstructable if code changed

---

### Hybrid V1 — P1–P4 Rules (Frozen)

| Property | Value |
|---|---|
| `version_id` | `hybrid_v1` |
| **Status** | **VERIFIED** |
| Scoring engine | foe_v1 / MODEL_VERSION v8.0 |
| Entry rule | V2 label + market_regime + ma20_trend → P1–P4 rules |
| P1 | Bear + WAIT_FOR_PULLBACK → WAIT_PULLBACK |
| P2 | Flat MA20 + WAIT_FOR_PULLBACK → WAIT_PULLBACK |
| P3 | (default) all others → DIRECT_NEXT_OPEN |
| P4 | WAIT_FOR_BREAKOUT → DIRECT_NEXT_OPEN |
| Parameter hash | `ma20_rising=0.3, ma20_falling=-0.3` |
| Frozen at | 2026-11-05T00:00:00 |
| Frozen commit | **6602c3b** |
| Code file | `src/research/hybrid_entry_strategy.py` |
| Comparison engine | `C_hybrid` |

---

### V3 — Advanced Entry Timing (Research)

| Property | Value |
|---|---|
| `version_id` | `v3_entry_timing` |
| **Status** | **VERIFIED** |
| Scoring engine | foe_v1 / MODEL_VERSION v8.0 |
| Entry rule | V3EntryTimingAnalyzer (MA20+MA60+slope+volume+regime) |
| Outputs | DIRECT_ENTRY / WAIT_MA20_PULLBACK / WAIT_MA60_SUPPORT / WAIT_BREAKOUT_CONFIRMATION / AVOID_CHASING / NO_ENTRY |
| MA features | MA20 + MA60 (level AND slope) vs V1/V2's MA20 level only |
| Volume | 3-class signature vs V1/V2 binary |
| Market regime | Explicit threshold adaptation |
| Parameter hash | **be43e8ca977d9fdd** |
| Frozen at | 2026-11-05 |
| Frozen commit | **6602c3b** |
| Code file | `src/research/v3_entry_strategy.py` |
| Comparison engine | `D_v3` |

---

## Pairwise Comparability

| Pair | Shared Scoring Engine | Comparability | Blockers |
|---|---|---|---|
| V1 ↔ V2 | Yes | NOT_COMPARABLE | Both PARTIAL; unverified parameters on both sides |
| V1 ↔ Hybrid V1 | Yes | NOT_COMPARABLE | V1 is PARTIAL; unverified thresholds |
| V1 ↔ V3 | Yes | NOT_COMPARABLE | V1 is PARTIAL; unverified thresholds |
| V2 ↔ Hybrid V1 | Yes | NOT_COMPARABLE | V2 is PARTIAL |
| V2 ↔ V3 | Yes | NOT_COMPARABLE | V2 is PARTIAL |
| **Hybrid V1 ↔ V3** | **Yes** | **CONDITIONAL** | Both VERIFIED; but outcome data = 0 |

**Only Hybrid V1 vs V3 can be compared once outcome data arrives.** V1 and V2 require parameter versioning before they can participate in a strict comparison.

---

## VERSION_DEFINITION Verdict

| Version | Verdict |
|---|---|
| V1 | `VERSION_DEFINITION_PARTIAL` |
| V2 | `VERSION_DEFINITION_PARTIAL` |
| Hybrid V1 | `VERSION_DEFINITION_VERIFIED` |
| V3 | `VERSION_DEFINITION_VERIFIED` |

**Overall: `VERSIONS_PARTIAL`** — 2 of 4 versions have unresolved parameter documentation.

---

## What This Means

The scoring engine (`foe_v1`) produces the same set of BUY/STRONG_BUY signals regardless of which version is chosen. The versions are tested on the SAME signals with DIFFERENT entry rules.

This means:
- Comparing V1 vs V3 performance = "does entry timing add value?"
- NOT "does the new model pick better stocks?"
- The stock selection ability of foe_v1 is constant across all versions
