# Session 61 — Rollback Rehearsal

**Verdict: ROLLBACK_VERIFIED**

## Methodology

Each rollback test follows this sequence:
1. Read production script into memory (file is NOT modified).
2. Compute SHA-256 of original content (`base_hash`).
3. Apply patch(es) via string substitution → `patched_content`.
4. Compute SHA-256 of patched content (`after_apply_hash`).
5. Revert patch(es) in reverse order via string substitution → `reverted_content`.
6. Compute SHA-256 of reverted content (`after_rollback_hash`).
7. Assert `after_rollback_hash == base_hash`.
8. Assert no residual patched text remains in `reverted_content`.

The production script file is never written to. All operations are in-memory.

## Rollback Test Results (R01–R07)

| Test ID | Description | Hashes Match | Residual Patched Text | Verdict |
|---------|-------------|-------------|----------------------|---------|
| R01 | RC-1 only rollback | Yes | No | ROLLBACK_VERIFIED |
| R02 | RC-2 only rollback | Yes | No | ROLLBACK_VERIFIED |
| R03 | RC-3 only rollback | Yes | No | ROLLBACK_VERIFIED |
| R04 | RC-1 + RC-2 combined rollback | Yes | No | ROLLBACK_VERIFIED |
| R05 | RC-1 + RC-3 combined rollback | Yes | No | ROLLBACK_VERIFIED |
| R06 | RC-2 + RC-3 combined rollback | Yes | No | ROLLBACK_VERIFIED |
| R07 | All 3 combined rollback | Yes | No | ROLLBACK_VERIFIED |

Base script SHA-256 (first 16 chars): `4bb88de209df6b82`

## Rollback Order for Combined Patches

When multiple RCs are applied and rollback is needed, revert in reverse deployment order:

1. If all 3 were deployed: revert RC-3 first, then RC-1, then RC-2.
2. If only RC-2 + RC-3: revert RC-3 first, then RC-2.
3. Any single-RC rollback is order-independent.

Reverting in reverse order ensures that each revert finds its patched text intact (no double-substitution risk since all patches modify different lines).

## Rollback Limitations

| Concern | Assessment |
|---------|------------|
| Code rollback reversible | Yes — single-line text substitution, exact round-trip |
| Historical data reversible | Yes — no production writes in Session 61 |
| Downstream data reversible | Yes — no signals, outcomes, or forward_signals modified |
| DB rollback needed | No — no production DB writes executed |
| Post-deployment data rollback | Conditional — if RC-3 were deployed and a backfill run executed, new non-NULL volume rows would exist. Those rows are correct data. Reverting the code does not undo written rows. If deletion is desired, a separate `DELETE WHERE date > deploy_date` query requires its own authorization. |

## Production Safety Note

Session 61 does not execute any production backfill. The rollback scenarios above apply to a hypothetical future deployment. As of this session, the base hash is verified unchanged (`PRODUCTION_UNCHANGED_VERIFIED`).
