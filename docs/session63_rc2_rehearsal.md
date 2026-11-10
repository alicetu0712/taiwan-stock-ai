# Session 63 — RC-2 Isolated Apply/Revert Rehearsal

## Status: REHEARSAL_PASS / PRODUCTION_UNCHANGED

---

## 1. Patch Identity

| Property | Value |
|---|---|
| Target file | `scripts/backfill_daily_prices.py` |
| Target function | `_is_excluded()` |
| Target line (approx) | line 98 |
| Original SHA-256 | `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` |
| Patched SHA-256 | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` |
| Reverted SHA-256 | `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9` |
| Changed lines | 1 |
| Changed files | 1 |

---

## 2. Exact Diff

```diff
-    if len(sid) > 4 and not sid.isdigit():
+    if len(sid) > 4:
```

Change: removes ` and not sid.isdigit()` (-22 characters).

---

## 3. In-Memory Apply Rehearsal

```python
with open("scripts/backfill_daily_prices.py") as f:
    src = f.read()

# Step 1: Verify original
assert hashlib.sha256(src.encode()).hexdigest() == KNOWN_ORIG_HASH

# Step 2: Apply
patched = src.replace("    if len(sid) > 4 and not sid.isdigit():",
                      "    if len(sid) > 4:", 1)

# Step 3: Verify patched hash
assert hashlib.sha256(patched.encode()).hexdigest() == KNOWN_PATCHED_HASH

# Step 4: Revert
reverted = patched.replace("    if len(sid) > 4:",
                           "    if len(sid) > 4 and not sid.isdigit():", 1)

# Step 5: Verify round-trip
assert hashlib.sha256(reverted.encode()).hexdigest() == KNOWN_ORIG_HASH
assert "    if len(sid) > 4 and not sid.isdigit():" in reverted
assert "    if len(sid) > 4:" not in reverted
```

**All 5 steps: PASS** (TC23-TC25).

---

## 4. Isolated Temp-file Rehearsal (TC27)

```python
# Write patched version to a temp file — production file never touched
with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tf:
    tf.write(patched)
    temp_path = tf.name

temp_hash = sha256_file(temp_path)
os.unlink(temp_path)  # cleanup

assert temp_hash == KNOWN_PATCHED_HASH          # temp file correct
assert sha256_file(PRODUCTION_SCRIPT_PATH) == KNOWN_ORIG_HASH  # production untouched
```

**Result: PASS** — temp file has correct patched hash; production file unchanged.

---

## 5. Drift Detection

| Scenario | Detection Method | Result |
|---|---|---|
| Original text found once | `count(RC2_ORIGINAL_TEXT) == 1` | PASS (TC02) |
| Patch not already applied | `count(RC2_PATCHED_TEXT) == 0` | PASS (TC02) |
| Dirty worktree | `hash(dirty_src) != KNOWN_ORIG_HASH` | DETECTABLE (TC29) |
| Double-apply guard | `count(RC2_ORIGINAL_TEXT) == 0` after apply | DETECTABLE (TC28) |

---

## 6. No DB Rollback Required

RC-2 is a pure code change:
- `_is_excluded()` is a pure-Python filter function
- It makes zero DB writes
- Reverting the code fully restores prior behavior
- No DB state is created by deploying or reverting RC-2

Verification: `RC2_PATCHED_TEXT` contains no `INSERT`, `sqlite3`, `conn`, `execute`, or `commit` (TC30).

---

## 7. Production File Integrity

```
BEFORE all rehearsals : 4bb88de209df6b82... ✓
AFTER  all rehearsals : 4bb88de209df6b82... ✓
Verification test     : TC26, TC36, TC37
```

**All rehearsal work was performed in-memory or in a temp file. The production script was never modified.**

---

## 8. Rehearsal Test Summary

| TC | Description | Result |
|---|---|---|
| TC23 | Apply produces KNOWN_PATCHED_HASH | PASS |
| TC24 | Revert restores KNOWN_ORIG_HASH | PASS |
| TC25 | No residual after revert | PASS |
| TC26 | Production file unchanged after all rehearsals | PASS |
| TC27 | Isolated apply to temp file | PASS |
| TC28 | Already-applied detection | PASS |
| TC29 | Dirty worktree detection | PASS |
| TC30 | No DB rollback needed | PASS |

**8/8 PASS — REHEARSAL_PASS / PRODUCTION_UNCHANGED**
