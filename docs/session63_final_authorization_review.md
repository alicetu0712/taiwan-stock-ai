# Session 63 — RC-2 Final Authorization Review

## AUTH-RC61-02: Security Eligibility / Warrant Exclusion Patch

**Decision**: `GO_FOR_AUTHORIZATION`
**Current Status**: `AUTHORIZATION_PENDING` (awaiting explicit user authorization)

---

## 1. Patch Summary

| Property | Value |
|---|---|
| Authorization ID | AUTH-RC61-02 |
| Target file | `scripts/backfill_daily_prices.py` |
| Target function | `_is_excluded()` |
| Risk level | LOW |
| Changed lines | 1 |
| Changed files | 1 |
| Bug fixed | `len>4 AND isdigit()` passed through (warrants, 5-digit ETFs were backfilled) |
| Fix | Remove `and not sid.isdigit()` → all len>4 excluded regardless of digit/alpha content |

---

## 2. Pre-Authorization Checklist

| # | Condition | Status | Evidence |
|---|---|---|---|
| C01 | Patch identity verified (SHA-256) | ✓ VERIFIED | TC01, TC03 |
| C02 | Original text unique (not already applied) | ✓ VERIFIED | TC02 |
| C03 | Round-trip hash match (apply → revert = original) | ✓ VERIFIED | TC23–TC25 |
| C04 | Research Universe (826 stocks) zero false exclusion | ✓ VERIFIED | TC06–TC07, TC39 |
| C05 | Benchmark 0050 preserved | ✓ VERIFIED | TC08–TC09 |
| C06 | Innovation Board 6423 preserved | ✓ VERIFIED | TC10 |
| C07 | All ordinary stocks unaffected | ✓ VERIFIED | TC11 |
| C08 | 5-digit ETFs correctly excluded after RC-2 | ✓ VERIFIED | TC12 |
| C09 | 6-digit warrants correctly excluded after RC-2 | ✓ VERIFIED | TC13 |
| C10 | Name-keyword exclusion unaffected | ✓ VERIFIED | TC14 |
| C11 | Alphanumeric len>4 still excluded | ✓ VERIFIED | TC15 |
| C12 | Zero network calls during `_is_excluded()` | ✓ VERIFIED | TC16–TC22 |
| C13 | Zero DB opens during `_is_excluded()` | ✓ VERIFIED | TC22 |
| C14 | Production file unchanged throughout S63 | ✓ VERIFIED | TC26, TC36, TC37 |
| C15 | No deployment executed during S63 | ✓ VERIFIED | TC37 |
| C16 | AUTH01/AUTH02 not covered by this authorization | ✓ VERIFIED | TC31–TC32 |

**16/16 conditions: VERIFIED**

---

## 3. Five-Universe Impact Summary

| Universe | Before RC-2 | After RC-2 | Net Impact |
|---|---|---|---|
| Backfill Eligible (U1) | Includes len>4 pure-numeric (bug) | Excludes len>4 pure-numeric (fixed) | Bug fixed |
| Daily Prices Storage (U2) | 534,770 rows, 129,636 NULL vol | Unchanged (read-only) | Zero |
| Research Universe (U3: stocks) | 826 × 4-digit | Unchanged | Zero |
| Strategy Signal Universe (U4) | foe_v1 / Hybrid P1–P4 unchanged | Unchanged | Zero |
| Benchmark Universe (U5: 0050) | 4-digit, eligible | Unchanged | Zero |

---

## 4. Offline Verification

```
OFFLINE_ZERO_NETWORK_VERIFIED
  _is_excluded() path : pure string/arithmetic
  network block tests : 7/7 PASS (TC16–TC22)
  subprocess block    : PASS
  DB open block       : PASS
  import side effects : ZERO new from RC-2
```

---

## 5. What This Authorization Covers

- Applying the single-line diff to `scripts/backfill_daily_prices.py`
- Verifying the production script hash changes from `4bb88de2...` to `4eb6eacf...`
- Running one dry-run backfill to confirm 6-digit/5-digit stocks absent from output

## 6. What This Authorization Does NOT Cover

| Excluded Scope | Reason |
|---|---|
| AUTH01 (1,440 TWSE calls) | Separate authorization, not bundled |
| AUTH02 (20D outcome calculation) | Separate authorization, not bundled |
| AUTH-RC61-01 (TPEx error reporting) | Separate authorization |
| AUTH-RC61-03 (TradingShares parser) | Separate authorization |
| Historical Repair | Requires separate explicit authorization |
| V3 Activation | ACTIVATION_BLOCKED (independent chain) |
| Cron installation | Stage B declined (Session 36), not bundled |
| Any `--execute` backfill run | Requires separate explicit authorization |

---

## 6. Known Limitations

1. Post-deployment effectiveness requires running `--execute` backfill (needs separate AUTH)
2. Historical NULL volume (129,636 rows) will NOT be automatically repaired by deploying RC-2 alone
3. TPEx ordinary stocks (SET-C: 21,846 rows) have NULL volume from a separate root cause — RC-2 does not fix that
4. AUTH01 (1,440 TWSE single-stock backfill) remains independently blocked

---

## 7. 15 Final Questions

**Q1: Is the exact line targeted by RC-2 unique in the production file?**
A: YES. `    if len(sid) > 4 and not sid.isdigit():` appears exactly once (line ~98). TC02 PASS.

**Q2: Does applying RC-2 produce a deterministic hash?**
A: YES. SHA-256 of patched content = `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` deterministically. TC03 PASS.

**Q3: Can RC-2 be fully reverted with no residual?**
A: YES. Revert restores `4bb88de2...` with zero residual of patched text. TC24–TC25 PASS.

**Q4: Does RC-2 affect any stock in the research universe (stocks table)?**
A: NO. All 826 stocks have 4-digit IDs; `len(4) > 4` is FALSE for all. TC06–TC07 PASS.

**Q5: Does RC-2 affect 0050 (benchmark)?**
A: NO. `len('0050')=4 ≤ 4`. Neither the length check nor name-keyword check excludes 0050. TC08–TC09 PASS.

**Q6: Is the Innovation Board stock 6423 affected?**
A: NO. `len('6423')=4 ≤ 4`. Remains eligible. TC10 PASS.

**Q7: What was the original bug?**
A: `and not sid.isdigit()` made len>4 pure-numeric IDs (warrants 7xxxxx, 5-digit ETFs 00858) pass the exclusion filter and get included in backfill. This generated 129,636 NULL volume rows (SET-A + SET-B).

**Q8: Does RC-2 fix ALL the NULL volume rows?**
A: NO. RC-2 fixes SET-A (107,590 warrants) + SET-B (175 5-digit ETFs). SET-C (21,846 TPEx ordinary) has a different root cause (TPEx API field mapping). SET-D (25 from 6423) is a data anomaly.

**Q9: Does RC-2 make any new DB writes?**
A: NO. `_is_excluded()` is a pure filter function. RC-2 adds zero DB write paths. TC30 PASS.

**Q10: Does RC-2 trigger any HTTP requests?**
A: NO. `_is_excluded()` performs only string/arithmetic operations. Network is never touched. TC16–TC22 PASS.

**Q11: Does RC-2 affect foe_v1 signal generation?**
A: NO. Signal generation uses the research universe (stocks table, U3), which is entirely 4-digit and unaffected.

**Q12: Does RC-2 affect Hybrid Entry P1–P4?**
A: NO. Same reason — Hybrid Entry operates on the research universe.

**Q13: Does approving RC-2 authorize executing backfill?**
A: NO. AUTH-RC61-02 authorizes code deployment only. Executing backfill requires a separate explicit authorization with `--execute` flag.

**Q14: Does approving RC-2 authorize AUTH01?**
A: NO. AUTH01 (1,440 TWSE single-stock calls) is an independent authorization covering historical data repair.

**Q15: Is there any reason NOT to authorize RC-2?**
A: No new blocking reasons found in S63. The patch is single-line, deterministic, fully reversible, offline-safe, with zero false exclusions. Known limitation: will not repair existing NULL volume rows — that requires separate `--execute` authorization.

---

## 8. Session 63 Test Summary

| Group | Tests | Passed |
|---|---|---|
| Patch Identity | TC01–TC05 | 5/5 |
| Universe Contract & False Exclusion | TC06–TC15 | 10/10 |
| Offline Zero-network | TC16–TC22 | 7/7 |
| Offline Rehearsal | TC23–TC30 | 8/8 |
| Authorization Boundary | TC31–TC35 | 5/5 |
| Final Verdict | TC36–TC40 | 5/5 |
| **Total S63** | **40** | **40/40** |

**Full regression**: 4313 passed, 4 skipped (S62 baseline: 4273)

---

## 9. Final Verdict

```
RC-2 (AUTH-RC61-02): GO_FOR_AUTHORIZATION

PATCH_IDENTITY          : VERIFIED
UNIVERSE_CONTRACT       : VERIFIED (5 universes)
FALSE_EXCLUSION         : ZERO FALSE EXCLUSIONS
BENCHMARK_PRESERVED     : VERIFIED (0050 unaffected)
OFFLINE_NETWORK         : ZERO_NETWORK_VERIFIED
REHEARSAL               : PASS (apply/revert round-trip)
PRODUCTION_INTEGRITY    : UNCHANGED (4bb88de2...)
AUTH_BOUNDARIES         : CORRECTLY_SCOPED

Current state  : AUTHORIZATION_PENDING
Next state     : AUTHORIZED (requires explicit user authorization)
Deployment     : NOT EXECUTED (S63 safety constraint honored)
AUTH01/AUTH02  : NOT_AUTHORIZED (unchanged, independent)
```

---

*Session 63 · 2026-11-11 · ZERO_PRODUCTION_WRITE / NO_DEPLOYMENT*
