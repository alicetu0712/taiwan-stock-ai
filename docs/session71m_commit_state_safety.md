# Session 71M — Commit Outcome & State Safety

**Session**: 71M  
**Verdict**: `UNKNOWN_COMMIT_FAIL_CLOSED_VERIFIED`

---

## Commit Proxy Accuracy (Retained from S71L)

`write_committed=True` is set AFTER `FULL_MARKET_FRESH` is confirmed.

**Chain**: `conn.commit()` (line 546) → rows readable → `FULL_MARKET_FRESH` → `write_committed=True`.

This proxy is accurate but NOT an exactly-once guarantee:
- `conn.commit()` is per-date (inside loop)
- `write_committed=True` is set once after all dates are confirmed fresh
- If crash between commit and state update: `WRITE_OUTCOME_UNKNOWN` (fail-closed)

**Exactly-once guarantee is NOT claimed** — only "fail-closed on unknown outcome".

---

## S71M-Specific: Guard Does Not Affect Commit Semantics

The S71M guard check runs BEFORE `sqlite3.connect()`. If the guard blocks:
- No connection is opened
- No data is read
- No data is written
- Returns `{"guard_blocked": True, ...}` immediately

If the guard passes, all existing commit semantics are unchanged.

---

## Scenario Coverage

| Scenario | Outcome | Evidence |
|---|---|---|
| Guard blocks before connect | No write, no state change | M-08 ✓ |
| SQLite commit before state update — crash | WRITE_OUTCOME_UNKNOWN → fail-closed | M-13 ✓, L-05 ✓ |
| Commit confirmed + post-write failure | Blocks re-write | M-14 ✓, L-07 ✓ |
| QG blocked (STALE) | write_committed NOT set | L-08 ✓ |
| Provider failure (exit=1) | write_committed NOT set | L-09 ✓ |
| Corrupted state | FAIL_CLOSED_CORRUPT | M-15 ✓, L-10 ✓ |
| Duplicate same-day execute | ALREADY_RAN_TODAY | M-14 ✓ |
| Concurrent execution | CONCURRENT_RUN | M-09 ✓ |

---

## Guard vs QG Ordering

```
run_backfill(execute=True):
  1. Guard check (check_original_entry) ← S71M addition
  2. _verify_sqlite()
  3. sqlite3.connect()
  4. _find_missing_dates()
  5. fetch_twse / fetch_tpex (PROVIDERS)
  6. run_quality_gate() (QG-1~QG-7)
  7. _write_df_to_sqlite()
  8. conn.commit()
```

Guard fires at step 1. If guard blocks, no providers are called, no QG runs, no DB writes.
This means `FULL_MARKET_FRESH` ≠ `guard authorized` — they are independent checks at different layers.
