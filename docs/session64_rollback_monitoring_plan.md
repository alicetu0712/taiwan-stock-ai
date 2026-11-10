# Session 64 — Rollback & Monitoring Plan (RC-2)

---

## Part 1: Rollback Plan

### 1.1 Rollback Triggers

Initiate rollback immediately on ANY of the following:

| # | Trigger | Severity |
|---|---|---|
| R01 | Post-deploy hash ≠ `4eb6eacf...` | CRITICAL — rollback immediately |
| R02 | Unexpected diff (more than single-line RC-2 change) | CRITICAL |
| R03 | Syntax failure after deployment | CRITICAL |
| R04 | Import failure after deployment | CRITICAL |
| R05 | Focused tests fail (excluding expected TC37 change) | HIGH |
| R06 | Unauthorized network activity during import | CRITICAL |
| R07 | Unauthorized DB write detected | CRITICAL |
| R08 | Scheduler side effect triggered unexpectedly | HIGH |
| R09 | Benchmark 0050 appears excluded | CRITICAL |
| R10 | Any 4-digit ordinary stock appears excluded | CRITICAL |
| R11 | Unknown security classification change detected | HIGH |
| R12 | Hash mismatch at any verification step | CRITICAL |

### 1.2 Rollback Steps

**Note: These steps apply ONLY after a deployment has been authorized and executed. No rollback needed in Session 64 — no deployment has been executed.**

```
Step R1: Stop all further deployment actions immediately.
Step R2: Preserve evidence.
         → Copy current file: cp scripts/backfill_daily_prices.py /tmp/rc2_post_deploy_snapshot.py
         → Record hash: shasum -a 256 scripts/backfill_daily_prices.py
         → Record timestamp and trigger reason in logs/deployment_rc2.log

Step R3: Verify backup exists.
         → shasum -a 256 scripts/backfill_daily_prices.py.bak-PRE-RC2
         → Expected: 4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9
         → If backup missing or hash wrong: STOP — reconstruct from git

Step R4: Restore exact original file.
         → cp scripts/backfill_daily_prices.py.bak-PRE-RC2 scripts/backfill_daily_prices.py

Step R5: Verify restored hash.
         → shasum -a 256 scripts/backfill_daily_prices.py
         → Must equal: 4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9
         → STOP if mismatch.

Step R6: Verify syntax and import.
         → python3 -c "import ast; ast.parse(open('scripts/backfill_daily_prices.py').read())"
         → python3 -c "from scripts.backfill_daily_prices import _is_excluded; print(_is_excluded('台積電', '2330'))"
         → Expected: (OK / False)

Step R7: Verify no unrelated changes.
         → git diff scripts/backfill_daily_prices.py
         → Expected: (no output — file restored to HEAD state)

Step R8: Record rollback evidence.
         → echo "RC-2 ROLLED BACK at $(date), reason: <trigger>" >> logs/deployment_rc2.log
         → shasum -a 256 scripts/backfill_daily_prices.py >> logs/deployment_rc2.log
```

### 1.3 Rollback Scope Separation

| Scope | Coverage | Notes |
|---|---|---|
| **Code Rollback** | ✓ Covered (Steps R1–R8) | Fully reversible: restore from backup or git |
| **Process Rollback** | ✓ Covered (no process launched by RC-2 itself) | Cron will auto-revert to old exclusion on next run |
| **Data Rollback** | ✗ NOT COVERED | RC-2 is a code-only change; no data was written as part of deployment |
| **Historical Data Rollback** | ✗ Not applicable | No `--execute` was run as part of this deployment |

If `--execute` was separately run (via cron or manual) AFTER deployment:
- The only data effect would be omitting some warrant/ETF rows from future backfill batches
- Existing `daily_prices` rows are NOT deleted or modified by RC-2 backfill
- No historical data rollback is required

---

## Part 2: Monitoring & Acceptance Plan

### 2.1 Deployment Acceptance (H1) — Code-only, Immediate

Can be verified immediately after deployment, without backfill:

| Check | Method | Pass Criterion |
|---|---|---|
| File hash | `shasum -a 256 scripts/backfill_daily_prices.py` | `4eb6eacf...` (full 64-char) |
| Static diff | `git diff HEAD scripts/backfill_daily_prices.py` | Single-line RC-2 change only |
| Syntax | `python3 -c "import ast; ast.parse(...)"` | OK |
| Import | `python3 -c "from scripts.backfill_daily_prices import _is_excluded"` | No crash, no output |
| Focused tests | `pytest tests/test_session63_rc2_authorization.py -q` | Passes, except TC37 expected fail |
| Zero network | Tests TC16–TC22 | All PASS |
| Rollback readiness | Backup file hash matches | `4bb88de2...` |

**Declaration**: H1 PASS = code deployed correctly and reversibly. Does NOT imply H2 or H3.

### 2.2 Functional Acceptance (H2) — Offline Fixture

Can be verified with offline unit tests (no live provider calls):

| Check | Test | Pass Criterion |
|---|---|---|
| Warrant exclusion | `_is_excluded_after('元大購01', '700022')` | `True` |
| 5-digit ETF exclusion | `_is_excluded_after('永豐ESG', '00858')` | `True` |
| Ordinary stock retention | `_is_excluded_after('台積電', '2330')` | `False` |
| Benchmark preservation | `_is_excluded_after('元大台灣50', '0050')` | `False` |
| Innovation board | `_is_excluded_after('億而得-創', '6423')` | `False` |
| Alphanumeric len>4 | `_is_excluded_after('元大富邦台50正2', '00631L')` | `True` |

**Declaration**: H2 PASS = exclusion logic is functionally correct. Does NOT imply H3.

### 2.3 Production Data Quality Acceptance (H3) — Requires Separate Authorization

The following cannot be verified until a full `--execute` backfill has been authorized and run:

| Metric | Baseline | Expected After RC-2 + Execute |
|---|---|---|
| Warrant rows included | Unknown (were incorrectly included) | Near-zero (all len>4 pure-numeric excluded) |
| 5-digit ETF rows included | Unknown (were incorrectly included) | Near-zero |
| NULL volume rows (SET-A) | 107,590 warrant rows | Expected: 0 for new backfill dates |
| NULL volume rows (SET-B) | 175 five-digit ETF rows | Expected: 0 for new backfill dates |
| Total `daily_prices` rows | 534,770 | Slightly reduced in new batches (ineligible stocks excluded) |
| Ordinary stock coverage | Unchanged | Unchanged |
| 0050 continuity | Last date: 2026-11-05 | Continues with new dates |

**Declaration**: H3 is NOT verifiable without `--execute`. Do NOT report H3 as PASS based on H1 or H2 results.

### 2.4 Cron Monitoring (Post-deploy, First Run)

After RC-2 deployment, monitor the first cron run (next 16:00 Asia/Taipei):

```
logs/hybrid_cron.log
```

Expected behavior:
- Backfill runs with `--execute` (cron is already installed with this flag)
- 6-digit/5-digit pure-numeric stocks should NOT appear in backfill candidates
- New daily_prices rows should contain no NULL volume for previously-excluded warrants
- Exit code: 0

If cron run fails: investigate `logs/hybrid_cron.log`, do NOT roll back RC-2 without evidence of causal link.

---

## Part 3: Pre-deployment Frozen State

| Item | Value | Status |
|---|---|---|
| Production script SHA-256 | `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` | VERIFIED |
| HEAD commit | `816ca2eaf40216838555f36a1b1c9f6aff5d6b47` | VERIFIED |
| Working tree | CLEAN | VERIFIED |
| daily_prices rows | 534,770 | VERIFIED |
| daily_prices max date | 2026-11-05 | VERIFIED |
| stocks rows | 826 | VERIFIED |
| MODEL_VERSION | v8.0 (src/database.py:38) | VERIFIED |
| Cron state | INSTALLED (`0 16 * * 1-5`) | VERIFIED (NOTE: previously thought NOT INSTALLED) |
| Neon ForwardSignals | UNVERIFIED (no safe read access established) | UNVERIFIED |
| V3 Hash | `be43e8ca977d9fdd` | Per frozen reference (not re-read this session) |
| Canonical V2 SHA-256 | `6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f` | Per frozen reference |
