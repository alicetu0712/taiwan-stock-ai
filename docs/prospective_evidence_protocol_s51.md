# Prospective Evidence Protocol — Session 51

**Analysis date**: 2026-11-10  
**Session**: S51  
**RULE_FREEZE_DATE**: 2026-11-05  
**V3 Parameter Hash**: `be43e8ca977d9fdd`

---

## Classification Hierarchy

```
V3_DECISION_PROSPECTIVE       ← full V3 pipeline ran; decision locked BEFORE execution_date
  └─ BASE_SIGNAL_PROSPECTIVE  ← v8.0 signal locked before execution_date; V3 not yet activated
       └─ RETROSPECTIVE_RECONSTRUCTION ← signal/decision recorded AFTER execution (or pre-freeze)
            └─ PROVENANCE_UNVERIFIED   ← locked_at NULL or unreliable
```

The core principle: **真正的 Prospective Evidence，必須證明完整 V3 決策在結果發生前已經固定，而不只是基礎訊號的時間戳記早於交易日。**

---

## Classification Rules (`classify_fill_cluster()`)

1. **V3_DECISION_PROSPECTIVE**: `v3_decision_frozen=True` AND `locked_before_execution=True`
2. **BASE_SIGNAL_PROSPECTIVE**: `locked_before_execution=True` AND `first_locked_at` is not None AND `NOT v3_decision_frozen`
3. **RETROSPECTIVE_RECONSTRUCTION**: execution_date ≤ RULE_FREEZE_DATE (2026-11-05) OR `locked_before_execution=False`
4. **PROVENANCE_UNVERIFIED**: `first_locked_at` is None

---

## Current Fill Cluster Classifications (as of S51)

| Fill date (execution_date) | Signal count (v8.0) | Classification | Reason |
|---------------------------|---------------------|----------------|--------|
| 2026-10-13 | ~237 | BASE_SIGNAL_PROSPECTIVE | v8.0 locked pre-execution; V3 not activated |
| 2026-10-14 | ~237 | BASE_SIGNAL_PROSPECTIVE | same |
| 2026-10-21 | ~237 | BASE_SIGNAL_PROSPECTIVE | same |
| 2026-10-22 | ~237 | BASE_SIGNAL_PROSPECTIVE | same |
| 2026-10-27 | ~237 | BASE_SIGNAL_PROSPECTIVE | same |
| 2026-10-28 | ~237 | BASE_SIGNAL_PROSPECTIVE | same |
| 2026-11-04 | ~237 | RETROSPECTIVE_RECONSTRUCTION | execution_date ≤ RULE_FREEZE_DATE |

**V3_DECISION_PROSPECTIVE count = 0** (V3 not activated; no eligible window since freeze)

---

## Why V3_DECISION_PROSPECTIVE is Currently Unachievable

V3 activation requires:
1. Pipeline fully operational (Nov 06 / Nov 09 both BLOCKED)
2. V3 formally enabled (blocked by ACTIVATION_BLOCKED)
3. Decision recorded with complete V3 snapshot before execution_date

Until the pipeline is restored and V3 activated, all new clusters will be BASE_SIGNAL_PROSPECTIVE at best.

---

## ImmutableDecisionPayload Fingerprint

Fields included in SHA-256[:16] fingerprint:
- `fill_date`, `signal_id`, `stock_id`, `model_version`, `locked_at`, `trade_signal`, `classification`

The fingerprint is computed at `__post_init__` and stored with the record. `verify()` recomputes and compares. Any mutation of these fields will cause verification failure.

---

## Retrospective Reconstruction Note

Records classified RETROSPECTIVE_RECONSTRUCTION **must not** be relabelled as prospective in any downstream analysis. The `ProspectiveRecorderPrototype` enforces this by storing `classification` in every record and exposing `verify_all()`.
