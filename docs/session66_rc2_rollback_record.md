# Session 66 — RC-2 Rollback Record

## Status: NOT_TRIGGERED

No rollback was required during Session 66.

---

## Rollback Triggers Evaluated

All 12 triggers from Part F1 evaluated after deployment:

| # | Trigger | Occurred? |
|---|---|---|
| R01 | Patched Hash Mismatch | NO — hash `4eb6eacf...` confirmed ✓ |
| R02 | Syntax Failure | NO — AST parse OK ✓ |
| R03 | Import Failure | NO — import OK ✓ |
| R04 | RC-2 Focused Tests Failure (unexpected) | NO — 10 expected failures (deployment guards), 30 behavior tests PASS ✓ |
| R05 | Unexpected Diff | NO — single-line RC-2 change only ✓ |
| R06 | Unauthorized Network Request | NO — no HTTP triggered ✓ |
| R07 | Unauthorized DB Write | NO — row count unchanged (534,770) ✓ |
| R08 | Scheduler Mutation | NO — cron entry unchanged ✓ |
| R09 | Unexpected Security Exclusion | NO — 0050 / 2330 / 6423 all correctly NOT excluded ✓ |
| R10 | Benchmark Regression | NO — `_is_excluded('元大台灣50', '0050')` = False ✓ |
| R11 | Runtime Error Attributed to RC-2 | NO — no runtime error observed ✓ |
| R12 | Cannot Confirm Deployment State | NO — hash confirmed ✓ |

---

## Rollback Readiness

Rollback remains available:

| Item | Value |
|---|---|
| Backup file | `scripts/backfill_daily_prices.py.bak-PRE-RC2-20261111` |
| Backup SHA-256 | `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` |
| Rollback command | `cp scripts/backfill_daily_prices.py.bak-PRE-RC2-20261111 scripts/backfill_daily_prices.py` |
| Post-rollback target hash | `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` |

---

## Important: Rollback Scope Limitation

Code rollback restores `_is_excluded()` to the pre-RC-2 version.

Code rollback does NOT:
- Reverse any data written to `data/platform.db` by cron runs after deployment
- Reverse any Provider HTTP calls made by cron runs after deployment
- Change the cron schedule

If rollback is needed AFTER a cron run has executed with RC-2 logic:
- Code rollback: immediately available via backup
- Data rollback: requires separate evaluation — only needed if RC-2 incorrectly excluded valid research stocks (which is excluded by H2 verification)
