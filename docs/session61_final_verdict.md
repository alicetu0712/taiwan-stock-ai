# Session 61 — Final Verdict

**Session: S61 — Production Release Candidates**
**Date: 2026-11-10**
**Regression: 4198 passed / 4 skipped**

---

## 16-Dimension Final Verdict

| # | Dimension | Verdict |
|---|-----------|---------|
| 1 | RC-1 (TPEx Error Reporting) | RC1_RELEASE_READY |
| 2 | RC-2 (Security Eligibility) | RC2_RELEASE_READY |
| 3 | RC-3 (TradingShares Volume) | RC3_RELEASE_READY |
| 4 | Patch Independence | PATCH_INDEPENDENCE_VERIFIED |
| 5 | Integration (7-combination matrix) | INTEGRATION_PASS (7/7) |
| 6 | Rollback Rehearsal (7 cases) | ROLLBACK_VERIFIED (7/7) |
| 7 | DQ Acceptance Metrics | DQ_ACCEPTANCE_READY |
| 8 | Authorization Packages | THREE_INDEPENDENT_PACKAGES_READY |
| 9 | Deployment Status | NO_DEPLOYMENT_EXECUTED |
| 10 | AUTH01 (Historical Backfill) | NOT_AUTHORIZED |
| 11 | AUTH02 (Historical Volume Repair) | NOT_AUTHORIZED |
| 12 | Prospective Evidence | GENUINE_PROSPECTIVE_N_0 |
| 13 | G03 (Signal coverage) | G03_FAIL |
| 14 | G04 (Weekly spacing) | G04_STRUCTURAL_FAIL |
| 15 | V3 Activation | ACTIVATION_BLOCKED |
| 16 | Production Integrity | PRODUCTION_UNCHANGED_VERIFIED |

---

## RC Readiness Summary

### RC61-01-TPEX-ERROR — RELEASE_READY
- **What:** Add TPEx api_date mismatch to `summary["errors"]` (symmetric with TWSE).
- **Risk:** LOW — observability only, no data written.
- **Reversible:** Yes, hash round-trip verified.
- **Auth required:** AUTH-RC61-01 (independent).

### RC61-02-SECURITY-ELIGIBILITY — RELEASE_READY
- **What:** Remove `and not sid.isdigit()` from `_is_excluded`. All len>4 stock IDs are excluded.
- **Risk:** LOW — 0 false exclusions of ordinary stocks (14 test cases audited).
- **Reversible:** Yes, hash round-trip verified.
- **Auth required:** AUTH-RC61-02 (independent).

### RC61-03-TPEX-VOLUME — RELEASE_READY
- **What:** Change TPEx volume field from `TradeVolume` → `TradingShares` at line 284.
- **Risk:** LOW–MEDIUM — corrects future inserts; existing 21,846 NULL rows unchanged.
- **Reversible:** Yes, hash round-trip verified.
- **Auth required:** AUTH-RC61-03 (independent).

---

## What Was Not Done (By Design)

| Item | Reason |
|------|--------|
| Production deployment | NOT_AUTHORIZED — requires explicit independent auth per RC |
| AUTH01 (TWSE Historical Backfill) | NOT_AUTHORIZED — separate from RC deployment |
| AUTH02 (TPEx Historical Repair) | BLOCKED — no feasible per-stock historical endpoint confirmed |
| PP-03 (TransactionAmount) | Excluded — HYPOTHESIS, MEDIUM confidence only |
| G03 / G04 improvement | Structural — not addressable by these RCs |
| V3 Activation | ACTIVATION_BLOCKED — preconditions not met |
| Deletion of 107,765 warrant/ETF rows | Not authorized by RC-2 |
| Deletion of 21,846 NULL volume rows | Not authorized by RC-3 |

---

## Frozen Parameters (Unchanged)

| Parameter | Value |
|-----------|-------|
| MODEL_VERSION | v8.0 |
| foe_v1 | FROZEN |
| Hybrid P1–P4 | FROZEN |
| V3 Parameter Hash | `be43e8ca977d9fdd` |
| Canonical V2 SHA-256 | `6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f` |
| Production script SHA-256 | `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` |
| Cron | `0 16 * * 1-5` Asia/Taipei |

---

## Session Deliverables

| Deliverable | Status |
|-------------|--------|
| `src/research/release_candidate_harness_s61.py` | COMPLETE, Ruff clean |
| `tests/test_session61_release_candidates.py` | 68 passed / 1 skipped, Ruff clean |
| `docs/session61_release_candidate_inventory.md` | COMPLETE |
| `docs/session61_rc1_error_acceptance.md` | COMPLETE |
| `docs/session61_rc2_eligibility_acceptance.md` | COMPLETE |
| `docs/session61_rc3_volume_acceptance.md` | COMPLETE |
| `docs/session61_integration_matrix.md` | COMPLETE |
| `docs/session61_rollback_rehearsal.md` | COMPLETE |
| `docs/session61_authorization_packages.md` | COMPLETE |
| `docs/session61_final_verdict.md` | COMPLETE (this file) |
| Full regression | 4198 passed / 4 skipped |
