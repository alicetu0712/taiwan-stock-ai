# Session 66 — RC-2 Deployment Execution Record

## Status: RC2_PATCH_DEPLOYED_VERIFIED

Deployment Timestamp: 2026-11-11 (Session 66)
Authorization: AUTH-RC61-02 (user-provided explicit authorization)
Host: Shih-Huas-MacBook-Pro-2.local
User: alicetu (uid=501)

---

## Patch Applied

### Exact Diff (as deployed)

```diff
--- a/scripts/backfill_daily_prices.py
+++ b/scripts/backfill_daily_prices.py
@@ -95,7 +95,7 @@ def _is_excluded(name: str, stock_id: str) -> bool:
     if any(kw.upper() in name_up for kw in EXCLUDE_KEYWORDS):
         return True
     sid = str(stock_id).strip()
-    if len(sid) > 4 and not sid.isdigit():
+    if len(sid) > 4:
         return True
     return False
```

### Hash Verification

| Stage | SHA-256 | Status |
|---|---|---|
| Pre-apply (expected) | `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` | VERIFIED before apply |
| Post-apply (expected) | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | VERIFIED after apply |
| Backup | `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` | VERIFIED before apply |

### Changed Files: 1
### Changed Lines: 1

---

## Post-Patch Verification

| Check | Result |
|---|---|
| `shasum -a 256 scripts/backfill_daily_prices.py` | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` ✓ |
| `git diff scripts/backfill_daily_prices.py` | Single-line RC-2 change only ✓ |
| `python3 -c "import ast; ast.parse(...);"` | SYNTAX_OK ✓ |
| `from scripts.backfill_daily_prices import _is_excluded` | Import OK, no side effects ✓ |
| Ruff | All checks passed ✓ |

---

## H1 — Code Deployment Acceptance: PASS

| Check | Result |
|---|---|
| Exact Patch | VERIFIED — only `    if len(sid) > 4:` applied |
| Patched Hash | `4eb6eacf...` ✓ |
| Syntax | PASS ✓ |
| Import | PASS ✓ |
| Ruff | PASS ✓ |
| Frozen Governance | UNCHANGED ✓ |
| Cron Unchanged | UNCHANGED (`0 16 * * 1-5` same entry) ✓ |
| No Manual Backfill | CONFIRMED — not executed ✓ |
| No Provider HTTP (from deployment) | CONFIRMED — no HTTP triggered ✓ |
| No DB Write (from deployment) | CONFIRMED — row count still 534,770 ✓ |
| Backup Verified | `4bb88de2...` ✓ |

**`RC2_CODE_DEPLOYED_VERIFIED`** — `H1_PASS`

---

## H2 — Offline Functional Acceptance: PASS

Using live patched `_is_excluded()` with no Provider calls:

| Stock | Stock ID | Expected | Actual | Label |
|---|---|---|---|---|
| 元大台灣50 | 0050 | NOT excluded | NOT excluded | PASS — benchmark preserved |
| 台積電 | 2330 | NOT excluded | NOT excluded | PASS — ordinary |
| 鴻海 | 2317 | NOT excluded | NOT excluded | PASS — ordinary |
| 億而得-創 | 6423 | NOT excluded | NOT excluded | PASS — innovation board |
| 浪凡 | 6165 | NOT excluded | NOT excluded | PASS — TPEx ordinary |
| 永豐ESG | 00858 | excluded | excluded | PASS — 5-digit ETF |
| 國泰高股息 | 00878 | excluded | excluded | PASS — 5-digit ETF |
| 元大台積電購01 | 700022 | excluded | excluded | PASS — 6-digit warrant |
| 元大富邦台50正2 | 00631L | excluded | excluded | PASS — alphanumeric >4 |

8/8 PASS — `H2_PASS` / `RC2_OFFLINE_FUNCTIONAL_PASS`

---

## S63 Focused Test Status After Deployment

30 tests PASS (behavior tests, all correct).

10 tests FAIL — all EXPECTED:
- TC01, TC26, TC27, TC36, TC40: check for ORIGINAL hash — now patched. Expected fail = confirms deployment.
- TC02: checks original text found once — now 0 (patched). Expected fail = confirms deployment.
- TC04: computes diff against original — no diff (file IS patched). Expected fail = confirms deployment.
- TC12, TC13: "before" assertions check that original `_is_excluded()` has bug — now fixed. Expected fail = confirms deployment.
- TC37: checks "no deployment executed" — now deployed. Expected fail = confirms deployment.

**Summary**: 10/10 "deployment guard" tests correctly fail, confirming RC-2 is live. 30/30 behavior tests pass.

---

## Cron / DB / Governance After Deployment

| Item | Before | After | Status |
|---|---|---|---|
| Cron entry | `0 16 * * 1-5 .../hybrid_shadow_cron.py --execute` | UNCHANGED | CRON_UNCHANGED |
| `daily_prices` rows | 534,770 | 534,770 | UNCHANGED |
| `stocks` rows | 826 | 826 | UNCHANGED |
| Max trade date | 2026-11-05 | 2026-11-05 | UNCHANGED |
| MODEL_VERSION | v8.0 | v8.0 | UNCHANGED |
| Neon ForwardSignals | UNVERIFIED | UNVERIFIED | UNCHANGED |

---

## Authorization Boundary Compliance

| Prohibited Action | Executed? |
|---|---|
| Manual Backfill | NO |
| `hybrid_shadow_cron.py --execute` (manual) | NO |
| Cron modification | NO |
| AUTH01 | NO |
| AUTH02 | NO |
| Historical Repair | NO |
| RC-1 deployment | NO |
| RC-3 deployment | NO |
| DB Schema change | NO |
| Neon write | NO |
| V3 activation | NO |
| Any file other than `backfill_daily_prices.py` | NO |

**All prohibitions honored.**
