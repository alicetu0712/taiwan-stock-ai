# Session 61 — Integration & Combination Matrix

**Verdict: INTEGRATION_PASS**

## Independence Proof

Each RC modifies a distinct, non-overlapping region of `scripts/backfill_daily_prices.py`:

| RC | Function | Lines | Type of change |
|----|----------|-------|----------------|
| RC61-01 | `run_backfill` | 500–501 | Add `msg` variable + `errors.append(msg)` |
| RC61-02 | `_is_excluded` | 98 | Remove `and not sid.isdigit()` clause |
| RC61-03 | `fetch_tpex_historical` | 284–286 | Change `TradeVolume` → `TradingShares` in 3-line context |

No line overlaps. No string overlaps. The original text of each RC does not appear in the original or patched text of the others.

## Dependency Matrix

| Dependency Type | RC-1 × RC-2 | RC-1 × RC-3 | RC-2 × RC-3 |
|-----------------|-------------|-------------|-------------|
| Shared source lines | No | No | No |
| Shared functions | No | No | No (`_is_excluded` vs `fetch_tpex`) |
| Shared data flow | No | No | Sequential but independent |
| Shared schema | No | No | No |
| Import dependencies | No | No | No |
| Error handling interaction | No | No | No |
| Ordering dependencies | No | No | No |
| Rollback dependencies | No | No | No |

**Verdict: PATCH_INDEPENDENCE_VERIFIED** (not merely non-overlapping lines — data flow also independent)

Data flow note: RC-2 controls which records pass the exclusion filter; RC-3 controls how volume is parsed for records that do pass. These are sequential stages but neither depends on the other being applied. Each can be deployed, rolled back, or tested independently.

## Seven-Combination Test Results

| Combination | RCs Applied | All Applied | No Conflict | Rollback Verified | Verdict |
|-------------|-------------|-------------|-------------|-------------------|---------|
| RC-1 only | {01} | Yes | Yes | Yes | PASS |
| RC-2 only | {02} | Yes | Yes | Yes | PASS |
| RC-3 only | {03} | Yes | Yes | Yes | PASS |
| RC-1 + RC-2 | {01, 02} | Yes | Yes | Yes | PASS |
| RC-1 + RC-3 | {01, 03} | Yes | Yes | Yes | PASS |
| RC-2 + RC-3 | {02, 03} | Yes | Yes | Yes | PASS |
| RC-1 + RC-2 + RC-3 | {01, 02, 03} | Yes | Yes | Yes | PASS |

All 7 combinations verified via in-memory string substitution on a read-only copy of the production script.

## Unexpected Behavior Diffs

No unexpected behavior diffs identified. Changes are strictly additive (RC-1) or selective (RC-2 exclusion, RC-3 field name). No existing correct data is affected:

- RC-1: no data written
- RC-2: no existing rows deleted or modified
- RC-3: no existing rows overwritten (INSERT OR IGNORE is idempotent)

## Production Write Verification

No test in the integration matrix writes to `data/platform.db`. All combination tests operate on in-memory string copies of the script. The production DB mtime is verified unchanged before and after the full test suite.
