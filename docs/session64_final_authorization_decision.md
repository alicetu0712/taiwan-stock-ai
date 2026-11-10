# Session 64 — AUTH-RC61-02 Final Authorization Decision Sheet

## Default Decision: DEFER — AWAITING EXPLICIT USER DECISION

---

## Change Identity

| Property | Value |
|---|---|
| Authorization ID | AUTH-RC61-02 |
| Patch Name | Warrant Exclusion / Security Eligibility Fix |
| Base Commit SHA | `816ca2eaf40216838555f36a1b1c9f6aff5d6b47` |
| Original File SHA-256 | `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` |
| Patched File SHA-256 | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` |
| Rollback Hash | `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` |
| Target Environment | `/Users/alicetu/Desktop/Antigravity/stock_platform` (macOS, Python 3.13.3) |

---

## Scope

- **One file**: `scripts/backfill_daily_prices.py`
- **One exact patch**: Remove ` and not sid.isdigit()` from line 98 of `_is_excluded()`
- **Code Deployment Only**: No backfill, no DB migration, no cron change, no API calls

---

## Benefits

| Benefit | Detail |
|---|---|
| Warrant exclusion | 6-digit pure-numeric warrants (e.g., 700022) correctly excluded from future backfill |
| 5-digit ETF exclusion | 5-digit pure-numeric ETFs (e.g., 00858, 00878) correctly excluded from future backfill |
| Future backfill hygiene | Prevents accumulation of NULL volume rows (SET-A: warrants, SET-B: 5-digit ETFs) |
| Universe correctness | Backfill eligible universe aligns with intended research universe (4-digit stocks only) |

---

## Limitations

| Limitation | Detail |
|---|---|
| No historical repair | 129,636 existing NULL volume rows are NOT repaired by this code change alone |
| No new OHLCV | No new price data fetched by deploying the code |
| No volume recovery | Historical volume gaps remain until `--execute` backfill is separately authorized |
| No 20D outcome | Research outcomes are unaffected |
| No V3 activation | V3 remains ACTIVATION_BLOCKED independently |
| SET-C not fixed | 21,846 TPEx ordinary NULL volume rows have a different root cause, unrelated to RC-2 |

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Security eligibility false exclusion | VERY LOW — 16/16 checks pass, all 826 research stocks are 4-digit | Offline tests TC06–TC15 |
| Benchmark 0050 disruption | VERY LOW — `len('0050')=4`, unaffected by `len>4` check | TC08–TC09 PASS |
| Production drift before deployment | LOW — working tree clean, hash verified | Re-verify hash at deploy time (Step A) |
| Accidental execution during deployment | LOW — Python in-place method does not trigger `main()` | Step G import-only check |
| Rollback failure | LOW — backup copy + git restore | Backup verified in Step B |
| Cron run during deployment | MEDIUM — cron IS installed at 0 16 * * 1-5 | Deploy outside 15:30–16:30 window |

---

## Evidence Chain

| Session | Evidence | Status |
|---|---|---|
| S60 | NULL volume root cause: 107,765 warrants + 21,846 TPEx field mismatch | VERIFIED |
| S61 | RC61-02 defined, 7-combo PASS, rollback VERIFIED, 4198 tests | VERIFIED |
| S62 | Zero-write simulation, 6 entry points, ENTRYPOINT_AUDIT_PASS, 4273/4 | VERIFIED |
| S63 | 16/16 pre-auth PASS, 40 focused tests, universe contract, offline proof | VERIFIED |
| S64 | Hash re-read `4bb88de2...` ✓, re-computed patched `4eb6eacf...` ✓, working tree CLEAN ✓, 40 focused tests PASS ✓ | VERIFIED |

---

## Cron State Discrepancy (New Finding — S64)

**Previous memory stated**: "Stage B 未授權（S36 明確拒絕）；CRON_FROZEN_UNCHANGED"

**Actual state found in S64**: Cron IS installed:
```
0 16 * * 1-5  .../hybrid_shadow_cron.py --execute
```

**Impact on deployment plan**:
- After RC-2 is deployed, the existing cron will automatically use the new `_is_excluded()` logic on its next scheduled run
- This is the INTENDED behavior
- It does NOT block authorization of RC-2
- It does mean that "first backfill with new logic" will happen automatically, not requiring manual trigger
- Deployment should be timed outside the 15:30–16:30 Asia/Taipei window to avoid race conditions

---

## Decision Options

### Option A: APPROVE

Authorize AUTH-RC61-02 for immediate deployment.

**Approve if**:
- You are satisfied with the evidence chain (S60–S64)
- You accept the cron timing implication (next scheduled run will use new logic)
- You understand no historical data is repaired
- You accept that AUTH01, AUTH02, Cron changes, and other items are NOT included

**Provide the Authorization Text exactly**:
> 「我明確授權在授權包所列、已驗證的正式環境中，僅部署 AUTH-RC61-02 的 Exact Diff。授權不包含執行 Backfill、Provider HTTP Requests、正式資料庫寫入、Cron／Scheduler 變更、AUTH01、AUTH02、Historical Repair、其他 RC 或 V3 啟用。若 Base Hash、目標環境或 Patch 內容不符，立即停止，不得自行擴大範圍。」

### Option B: DEFER

Wait for additional information or a better deployment window.

**Defer if**:
- You want to review the cron timing implication before proceeding
- You prefer to deploy during a specific maintenance window
- You want to run full regression first (currently in progress, results pending)

### Option C: REJECT

Do not deploy RC-2 at this time.

**Reject if**:
- New evidence contradicts the authorization review
- Production environment has changed
- Risk tolerance has changed

---

## Current Decision: DEFER — AWAITING EXPLICIT USER DECISION

This document does NOT constitute authorization. Session 63's `GO_FOR_AUTHORIZATION` is an assessment, not an authorization.

---

## Production Integrity at Session 64 End

| Item | Before S64 | After S64 | Status |
|---|---|---|---|
| Production script | `4bb88de2...` | `4bb88de2...` | UNCHANGED |
| daily_prices rows | 534,770 | 534,770 | UNCHANGED |
| stocks rows | 826 | 826 | UNCHANGED |
| Cron | INSTALLED (0 16 * * 1-5) | INSTALLED (unchanged) | UNCHANGED |
| MODEL_VERSION | v8.0 | v8.0 | UNCHANGED |
| AUTH-RC61-02 | NOT_AUTHORIZED | NOT_AUTHORIZED | UNCHANGED |
| Deployment | NOT_EXECUTED | NOT_EXECUTED | UNCHANGED |
| AUTH01/AUTH02 | NOT_AUTHORIZED | NOT_AUTHORIZED | UNCHANGED |

---

*Session 64 · 2026-11-11 · PLANNING_ONLY / READ_ONLY_PRODUCTION / NO_DEPLOYMENT / NO_BACKFILL*
