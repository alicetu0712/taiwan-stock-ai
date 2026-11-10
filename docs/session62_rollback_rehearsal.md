# Session 62 — Rollback Rehearsal

## Scope

Verify that for every RC (and every combination of RCs), apply followed by revert restores
the production script to its exact original state. All verification is in-memory using
SHA-256 hash comparison. The production file is never modified.

Methodology:

1. Read `scripts/backfill_daily_prices.py` into memory.
2. Compute `base_hash = SHA-256(content)`.
3. Apply patch(es) via `str.replace()` → compute `after_apply_hash`.
4. Revert patch(es) in reverse order via `str.replace()` → compute `after_rollback_hash`.
5. Assert `after_rollback_hash == base_hash`.
6. Assert no residual patched text remains.

---

## 7 Rollback Cases

| Test ID | RCs Applied | base_hash (first 16) | after_apply_hash (first 16) | after_rollback_hash (first 16) | hashes_match | residual | Verdict |
|---------|-------------|----------------------|-----------------------------|-------------------------------|:------------:|:--------:|---------|
| R01 | RC61-01 | `4bb88de209df6b82` | (differs) | `4bb88de209df6b82` | True | False | ROLLBACK_VERIFIED |
| R02 | RC61-02 | `4bb88de209df6b82` | (differs) | `4bb88de209df6b82` | True | False | ROLLBACK_VERIFIED |
| R03 | RC61-03 | `4bb88de209df6b82` | (differs) | `4bb88de209df6b82` | True | False | ROLLBACK_VERIFIED |
| R04 | RC61-01 + RC61-02 | `4bb88de209df6b82` | (differs) | `4bb88de209df6b82` | True | False | ROLLBACK_VERIFIED |
| R05 | RC61-01 + RC61-03 | `4bb88de209df6b82` | (differs) | `4bb88de209df6b82` | True | False | ROLLBACK_VERIFIED |
| R06 | RC61-02 + RC61-03 | `4bb88de209df6b82` | (differs) | `4bb88de209df6b82` | True | False | ROLLBACK_VERIFIED |
| R07 | RC61-01 + RC61-02 + RC61-03 | `4bb88de209df6b82` | (differs) | `4bb88de209df6b82` | True | False | ROLLBACK_VERIFIED |

All 7 cases: `hashes_match=True`, `residual_patched_text_found=False`.

---

## Why Rollback Is Exact

Each patch is a unique string substitution with no overlapping regions:

| RC | Original text location | Uniqueness |
|----|------------------------|-----------|
| RC61-01 | Lines 500-501: `print(f"  [WARN] {target_d}: TPEx...` | Unique in script (only TPEx api_date block) |
| RC61-02 | Line 98: `if len(sid) > 4 and not sid.isdigit():` | Unique in script (only `_is_excluded` function) |
| RC61-03 | Lines 284-286: 3-line context ending with `row.get("Open", "")` | Unique via `"Open"` (TPEx); TWSE uses `"OpeningPrice"` |

Since each `str.replace(original, patched, 1)` has a unique match, the reverse operation
`str.replace(patched, original, 1)` restores exactly the original string with no ambiguity.

---

## Data Rollback Limitations Per RC

| RC | Code Rollback | Data Rollback Needed? | Notes |
|----|---------------|-----------------------|-------|
| RC61-01 | Reversible (revert 2-line print block) | No | No data written — purely diagnostic change. |
| RC61-02 | Reversible (revert 1-line boolean) | No | No new data written, no existing data deleted. Next backfill may re-insert warrants (INSERT OR IGNORE idempotent). |
| RC61-03 | Reversible (revert 3-line context) | Conditional | If a backfill was executed after deployment: new non-NULL volume rows are correct data. No DB rollback needed unless operator chooses to remove. Code rollback stops future non-NULL inserts but does not affect already-inserted rows. |

**Important:** Session 61 and Session 62 execute no production backfill. All three RCs
have `data_rollback_needed=False` as of Session 62 close.

---

## Partial Apply / Interrupted Apply Notes

If a patch application is interrupted mid-write (file system failure during `open(f, "w")`):

- The production file may be in a corrupt or partially patched state.
- **Recovery:** Restore from git: `git checkout -- scripts/backfill_daily_prices.py`.
- **Verify:** `shasum -a 256 scripts/backfill_daily_prices.py` must equal
  `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9`.
- Never rely on `git status clean` alone — verify the SHA-256.

---

## Dirty Worktree Scenario

If other uncommitted changes exist in the working tree at deploy time:

- Do not apply the patch until the working tree is clean.
- Stash or commit unrelated changes first.
- Apply the RC patch, verify, then commit the patch as a standalone commit.
- This ensures the rollback commit is isolated and reverting it does not affect
  other work in progress.

---

## Test Evidence

| Test ID | Description | Result |
|---------|-------------|--------|
| TC45 | 7 rollback rehearsal cases executed | PASS |
| TC46 | R01: RC-1 rollback restores exact hash | PASS |
| TC47 | R02: RC-2 rollback restores exact hash | PASS |
| TC48 | R03: RC-3 rollback restores exact hash | PASS |
| TC49 | R07: All-3 combined rollback restores exact hash | PASS |
| TC50 | All 7 rollback cases: hashes_match=True, residual=False | PASS |
| TC51 | In-memory round-trip verify: apply all 3, revert = original | PASS |

---

## Limitations

- In-memory SHA-256 round-trip tests confirm logical correctness of the text substitution.
  They do not test file-system level atomicity, OS-level file locks, or concurrent access.
- `git checkout --` recovery procedure is specified but not executed in this session.
- Dirty worktree scenario is a specification; interactive testing was not performed.

---

## Verdict

**ROLLBACK_VERIFIED**

---

## Next Action

Rollback evidence is complete for all 7 cases. When user grants authorization, follow
per-RC rollback steps in `session62_deployment_isolation.md`. Verify SHA-256 after any
rollback operation.
