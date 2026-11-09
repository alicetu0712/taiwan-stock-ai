# Strategy Version Recovery — Session 40

**Date:** 2026-11-09  
**Session:** 40  

---

## Critical Reminder

All four strategy versions (V1, V2, Hybrid V1, V3) use the **same scoring engine** (foe_v1 / MODEL_VERSION v8.0). The comparison tests **entry timing filter quality only** — not scoring model quality.

---

## V1 — Signal Only (RECOVERED)

| Property | Value |
|---|---|
| version_id | `v1_signal_only` |
| Status | **RECOVERED** (hash from current code; historical accuracy PARTIAL) |
| Scoring engine | foe_v1 / MODEL_VERSION v8.0 |
| Entry rule | `trade_signal IN ('buy','strong_buy')` → fill at D+1 OPEN (no filter) |
| Parameter hash | `13113e2933ec3017` (computed Session 40) |
| Frozen commit | None |
| Comparison engine | A_direct |
| Limitations | No frozen commit; `trade_signal='buy'` includes 57 `decision_label='wait_pullback'` signals |

**Missing items**: Frozen commit; confirmation that `trade_signal` (not `decision_label`) was used in Sessions 23-25.

---

## V2 — Entry Timing Filtered (RECOVERED)

| Property | Value |
|---|---|
| version_id | `v2_entry_timing` |
| Status | **RECOVERED** (hash from current code; historical accuracy PARTIAL) |
| Scoring engine | foe_v1 / MODEL_VERSION v8.0 |
| Entry rule | BUY/STRONG_BUY → `EntryTimingAnalyzer` → ENTRY_READY only → D+1 OPEN |
| Filter | MA20 pullback zone: price within [-5%, +3%] of MA20; gap < 15% |
| Parameter hash | `258513077a5ca6a0` (computed Session 40 from current code) |
| Parameters | `ma20_pullback_upper=0.03, ma20_pullback_lower=-0.05, too_extended_ma20_gap=15.0, stop_buffer=0.03` |
| Frozen commit | None |
| Comparison engine | B_v1v2 |
| Limitations | No frozen commit; parameters may have changed since Sessions 23-26 |

**Missing items**: Frozen commit for `src/analyzers/entry_timing.py`.

---

## Hybrid V1 — P1–P4 Regime Rules (VERIFIED)

| Property | Value |
|---|---|
| version_id | `hybrid_v1` |
| Status | **VERIFIED** |
| Scoring engine | foe_v1 / MODEL_VERSION v8.0 |
| Entry rule | V2 label + market_regime + ma20_trend → P1–P4 rules |
| Parameter hash | `ma20_rising=0.3, ma20_falling=-0.3` |
| Frozen commit | **6602c3b** |
| Comparison engine | C_hybrid |

---

## V3 — Advanced Entry Timing (VERIFIED)

| Property | Value |
|---|---|
| version_id | `v3_entry_timing` |
| Status | **VERIFIED** |
| Scoring engine | foe_v1 / MODEL_VERSION v8.0 |
| Entry rule | V3EntryTimingAnalyzer (MA20+MA60+slope+volume+regime) |
| Outputs | DIRECT_ENTRY / WAIT_MA20_PULLBACK / WAIT_MA60_SUPPORT / WAIT_BREAKOUT_CONFIRMATION / AVOID_CHASING / NO_ENTRY |
| Parameter hash | **be43e8ca977d9fdd** |
| Comparison engine hash | **1feb7a6b294a063d** |
| Frozen commit | **6602c3b** |
| Comparison engine | D_v3 |

---

## Pairwise Comparability (Session 40 Update)

| Pair | Comparability | Blocker |
|---|---|---|
| V1 ↔ V2 | CONDITIONAL | Both RECOVERED; historical params unverifiable |
| V1 ↔ Hybrid V1 | CONDITIONAL | V1 RECOVERED |
| V1 ↔ V3 | CONDITIONAL | V1 RECOVERED |
| V2 ↔ Hybrid V1 | CONDITIONAL | V2 RECOVERED |
| V2 ↔ V3 | CONDITIONAL | V2 RECOVERED |
| **Hybrid V1 ↔ V3** | **CONDITIONAL** | Both VERIFIED; blocked by statistical power and regime |

**All pairs CONDITIONAL** (upgraded from NOT_COMPARABLE for V1/V2 pairs due to RECOVERED status).

---

## Overall Status: `VERSIONS_PARTIAL`

2/4 VERIFIED (Hybrid V1, V3). 2/4 RECOVERED (V1, V2). No INCOMPLETE.

Upgrade path: Freeze V1/V2 definitions with git commit → upgrade to VERIFIED.
