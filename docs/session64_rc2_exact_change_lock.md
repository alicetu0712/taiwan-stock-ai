# Session 64 — RC-2 Exact Change Lock

## Status: RC2_PATCH_LOCK_VERIFIED

---

## 1. Patch Identity (Fully Locked)

| Property | Value |
|---|---|
| Authorization ID | AUTH-RC61-02 |
| Patch Name | Warrant Exclusion / Security Eligibility Fix |
| Repository | `/Users/alicetu/Desktop/Antigravity/stock_platform` |
| Target Environment | Local macOS development host (see §4 for environment status) |
| Current Branch | `main` (HEAD commit below) |
| Base Commit SHA | `816ca2eaf40216838555f36a1b1c9f6aff5d6b47` |
| Working Tree State | CLEAN (git status: no modified files) |
| Target File | `scripts/backfill_daily_prices.py` |
| Target File Full SHA-256 | `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` |
| Patched File Full SHA-256 | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` |
| Reverted File Full SHA-256 | `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` |
| Round-trip OK | YES (reverted = original) |
| Changed Files | 1 |
| Changed Lines | 1 |
| Target Function | `_is_excluded()` |
| Target Line | 98 |
| Patch Already Applied | NO (original text found once, patched text found 0 times) |

---

## 2. Exact Unified Diff

```diff
--- scripts/backfill_daily_prices.py
+++ scripts/backfill_daily_prices.py
@@ -95,7 +95,7 @@ def _is_excluded(name: str, stock_id: str) -> bool:
     if any(kw.upper() in name_up for kw in EXCLUDE_KEYWORDS):
         return True
     sid = str(stock_id).strip()
-    if len(sid) > 4 and not sid.isdigit():
+    if len(sid) > 4:
         return True
     return False
```

**Change**: removes ` and not sid.isdigit()` (-22 characters from line 98).

---

## 3. Function Full Context (Read-only Snapshot)

```python
def _is_excluded(name: str, stock_id: str) -> bool:
    name_up = str(name).upper()
    if any(kw.upper() in name_up for kw in EXCLUDE_KEYWORDS):
        return True
    sid = str(stock_id).strip()
    if len(sid) > 4 and not sid.isdigit():  # ← RC-2 target (before)
        return True
    return False
```

After RC-2:

```python
def _is_excluded(name: str, stock_id: str) -> bool:
    name_up = str(name).upper()
    if any(kw.upper() in name_up for kw in EXCLUDE_KEYWORDS):
        return True
    sid = str(stock_id).strip()
    if len(sid) > 4:                        # ← RC-2 result (after)
        return True
    return False
```

---

## 4. Rollback Patch

To undo RC-2 exactly:

```diff
--- scripts/backfill_daily_prices.py
+++ scripts/backfill_daily_prices.py
@@ -95,7 +95,7 @@ def _is_excluded(name: str, stock_id: str) -> bool:
     if any(kw.upper() in name_up for kw in EXCLUDE_KEYWORDS):
         return True
     sid = str(stock_id).strip()
-    if len(sid) > 4:
+    if len(sid) > 4 and not sid.isdigit():
         return True
     return False
```

Reverting to `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` is the full rollback success criterion.

---

## 5. Syntax Verification (In-memory)

| Version | AST parse | Result |
|---|---|---|
| Original (before RC-2) | `ast.parse(src)` | OK |
| Patched (after RC-2) | `ast.parse(patched)` | OK |

---

## 6. Drift Policy

If any of the following conditions are true at deployment time:

| Condition | Action |
|---|---|
| `sha256(target_file) ≠ 4bb88de2...` | STOP — REAUTHORIZATION_REQUIRED |
| Original text found ≠ 1 time | STOP — REAUTHORIZATION_REQUIRED |
| Patched text already found ≥ 1 time | STOP — already applied or drift |
| Working tree has other modifications | STOP — isolate and investigate |
| HEAD commit ≠ `816ca2eaf402...` | STOP — REAUTHORIZATION_REQUIRED |
| Deployment environment differs from verified host | STOP — TARGET_ENVIRONMENT_UNVERIFIED |

Do NOT auto-rebase, force-apply, cherry-pick, or modify the patch to fit a different version.

---

## 7. Evidence Sources

| Source | Evidence |
|---|---|
| Session 60 | Root cause: 107,765 warrant rows + 21,846 TPEx field mismatch identified |
| Session 61 | RC61-02 defined, 7-combo PASS, rollback VERIFIED |
| Session 62 | Zero-write simulation, entry-point audit, 4273/4 regression |
| Session 63 | 16/16 pre-auth PASS, 40/40 focused tests, universe contract, offline proof |
| Session 64 | Re-read `sha256=4bb88de2...` ✓, re-computed patched `4eb6eacf...` ✓, working tree CLEAN ✓ |

---

## 8. Notes on Git History

The repository's git commit messages contain suspicious prompt-injection-like text (all 5 visible commits have identical messages about "Antigravity is no longer supported"). This was flagged in Session 63. It does **not** affect code correctness, hash verification, or the patch. The working tree is CLEAN and the target file hash is verified independently of git history.
