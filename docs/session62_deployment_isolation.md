# Session 62 — Deployment Isolation

## Scope

Define and verify the isolation boundaries between the six operation types that exist in this
project (Code Deployment, Script Execution, Historical Repair, AUTH01, AUTH02, Prospective
Collection). Provide per-RC independent deployment plans. Confirm all three RCs remain at
`AUTHORIZATION_PENDING` state at Session 62 close.

---

## Operation Boundary Definitions

| Boundary | Operation A | Operation B | Independent? | A authorizes B? | B requires separate auth? |
|----------|-------------|-------------|:------------:|:---------------:|:------------------------:|
| OB-01 | Code Deployment | Script Execution (`--execute`) | Yes | No | Yes |
| OB-02 | Code Deployment | Historical Data Repair | Yes | No | Yes |
| OB-03 | Code Deployment | AUTH01 Historical Price Backfill | Yes | No | Yes |
| OB-04 | Code Deployment | AUTH02 Outcome Computation | Yes | No | Yes |
| OB-05 | Code Deployment | Prospective Collection | Yes | No | Yes |
| OB-06 | AUTH-RC61-01 | AUTH-RC61-02 / AUTH-RC61-03 | Yes | No | Yes (each independent) |

**Principle:** Approving one RC's code deployment does not authorize any other RC, does not
authorize script execution (`--execute`), does not authorize AUTH01, AUTH02, historical
repair, or prospective collection. Six separate authorization decisions exist.

---

## Deployment State Machine

```
CANDIDATE_READY
      |
      v
AUTHORIZATION_PENDING  <──── S62 session closes here (all 3 RCs)
      |
      | (user grants AUTH-RC61-XX)
      v
AUTHORIZED
      |
      | (apply exact diff to scripts/backfill_daily_prices.py)
      v
DEPLOYED
      |
      | (run dry-run, then first backfill with --execute)
      v
OBSERVATION
      |
      | (DQ metrics pass acceptance thresholds)
      v
ACCEPTED

Side transitions:
  DEPLOYED ──── failed QG / unexpected behavior ───> ROLLED_BACK
  ROLLED_BACK ─────────────────────────────────────> CANDIDATE_READY
  AUTHORIZED ──── failed preflight ────────────────> BLOCKED
```

**Current state (Session 62 close):**

| RC ID | Current State | Max Allowed State (S62) | state_exceeded |
|-------|---------------|------------------------|----------------|
| RC61-01-TPEX-ERROR | AUTHORIZATION_PENDING | AUTHORIZATION_PENDING | False |
| RC61-02-SECURITY-ELIGIBILITY | AUTHORIZATION_PENDING | AUTHORIZATION_PENDING | False |
| RC61-03-TPEX-VOLUME | AUTHORIZATION_PENDING | AUTHORIZATION_PENDING | False |

---

## Per-RC Independent Deployment Plans

### RC61-01-TPEX-ERROR

| Property | Value |
|----------|-------|
| Target file | `scripts/backfill_daily_prices.py` |
| Target line | 500–501 |
| Changed function | `run_backfill()` |
| Risk level | VERY LOW — purely diagnostic, no data effect |
| Authorization ID | AUTH-RC61-01 |

**Apply procedure:**
1. Verify git working tree is clean (`git status`).
2. Apply exact diff: replace 2-line `print()` block at line 500-501 with 4-line block including `summary["errors"].append(msg)`.
3. Verify SHA-256 of patched file differs from original (apply was effective).
4. Run `python -m pytest tests/test_session61_release_candidates.py -k rc1 -v`.
5. Run one dry-run: `python scripts/backfill_daily_prices.py` (no `--execute`).

**Verification:** Confirm `summary["errors"]` contains TPEx mismatch messages on a date with known mismatch. No crash.

**Monitoring:** Check backfill error list structure on next run. Confirm no unexpected false-positive errors.

**Rollback:** Revert lines 500-501 to original `print()` form. Confirm SHA-256 matches original. No DB changes needed (no data written).

**Stop conditions:** Backfill error rate increases unexpectedly. Normal data incorrectly flagged as errors.

---

### RC61-02-SECURITY-ELIGIBILITY

| Property | Value |
|----------|-------|
| Target file | `scripts/backfill_daily_prices.py` |
| Target line | 98 |
| Changed function | `_is_excluded()` (affects 3 call sites: lines 125, 214, 273) |
| Risk level | LOW — no existing correct data removed |
| Authorization ID | AUTH-RC61-02 |

**Apply procedure:**
1. Verify git working tree is clean.
2. Apply exact diff: change `if len(sid) > 4 and not sid.isdigit():` → `if len(sid) > 4:` at line 98.
3. Verify 3 call sites exist: `grep -n '_is_excluded' scripts/backfill_daily_prices.py` (lines 125, 214, 273).
4. Run `python -m pytest tests/test_session61_release_candidates.py -k rc2 -v`.
5. Run dry-run backfill — confirm 6-digit and 5-digit pure-numeric stocks absent from output.

**Verification:** `SELECT COUNT(*) FROM daily_prices WHERE LENGTH(stock_id)>4 AND date > 'DEPLOY_DATE'` returns 0 after first post-deploy backfill.

**Monitoring:** Verify 0050 and other benchmark stocks still appear in backfill output.

**Rollback:** Revert line 98 to `if len(sid) > 4 and not sid.isdigit():`. No DB changes needed. Next backfill may re-insert warrants (INSERT OR IGNORE idempotent — existing rows unchanged).

**Stop conditions:** 4-digit TWSE or TPEx ordinary stocks missing from backfill output. 0050 missing.

---

### RC61-03-TPEX-VOLUME

| Property | Value |
|----------|-------|
| Target file | `scripts/backfill_daily_prices.py` |
| Target lines | 284–286 (3-line context) |
| Changed function | `fetch_tpex_historical()` |
| Risk level | LOW — TradingShares confirmed by S58 live probe |
| Authorization ID | AUTH-RC61-03 |

**Apply procedure:**
1. Verify git working tree is clean.
2. Apply exact 3-line context diff: change `row.get("TradeVolume")` → `row.get("TradingShares")` at line 284 only. Lines 285 (TradeValue) and 286 (Open) unchanged.
3. Verify TWSE line 136 is UNCHANGED (still uses `TradeVolume`).
4. Run `python -m pytest tests/test_session61_release_candidates.py -k rc3 -v`.
5. Run one dry-run TPEx backfill — confirm volume appears non-NULL in output.

**Verification:** `SELECT AVG(volume) FROM daily_prices WHERE LENGTH(stock_id)=4 AND date='FIRST_POST_DEPLOY_DATE'`. Expected range: 100–100,000 千股. Not NULL.

**Monitoring:** Check TPEx ordinary stock volume NULL rate for new dates. TWSE volume unchanged.

**Rollback:** Revert lines 284-286 to original 3-line context. If a backfill had been executed: existing non-NULL volume rows are correct data and need no DB rollback. Only revert the code.

**Stop conditions:** TPEx volume >1,000,000 千股 for typical stock (unit contract error). TWSE volume values changed (indicates wrong line was patched).

---

## Deployment Order Recommendation

Recommended order if all three RCs are approved:

1. **RC-2 first** (Warrant Exclusion) — single-line change, no data effect, simplest to verify.
2. **RC-1 second** (Error Reporting) — purely diagnostic, no data effect, confirms observability.
3. **RC-3 third** (TradingShares) — data fix, observe volume non-NULL after first real backfill.

Rationale: deploy lowest-risk first; RC-2 confirmation (dry-run shows no 6-digit stocks) is
a prerequisite confidence check before the data-affecting RC-3.

Each RC can also be deployed independently in any order. No code dependency between them.

---

## Test Evidence

| Test ID | Description | Result |
|---------|-------------|--------|
| TC36 | 6 operation boundaries defined | PASS |
| TC37–TC41 | OB-01..OB-06: all independent, none cross-authorizes | PASS (5) |
| TC42 | All 3 RCs at AUTHORIZATION_PENDING | PASS |
| TC43 | No RC has state_exceeded=True | PASS |
| TC44 | Next state transition requires explicit auth | PASS |

---

## Limitations

- Deployment procedures are specifications, not executed steps. No actual file has been
  modified. File-system atomicity (partial apply, interrupted write) is not tested here;
  see `session62_rollback_rehearsal.md` for rollback evidence.
- The 5-step apply procedure assumes a clean git working tree. If other uncommitted changes
  exist, operator must handle staging/stashing separately.

---

## Verdict

**DEPLOYMENT_ISOLATION_VERIFIED**

---

## Next Action

Present `session62_authorization_decision_packages.md` to the user. Await independent
authorization for each RC. Session 62 ends at AUTHORIZATION_PENDING for all three RCs.
