# Session 71L — Commit Semantics Audit

**Session**: 71L  
**Verdict**: `WRITE_COMMITTED_PROXY_ACCURATE`

---

## SQLite Commit Location

**File**: `scripts/backfill_daily_prices.py`

```
Line 450: conn = sqlite3.connect(db_path)   ← opens connection (auto-commit OFF by default)
...
Line 534: _write_df_to_sqlite(conn, twse_df)  ← INSERT OR IGNORE, NO COMMIT
Line 541: _write_df_to_sqlite(conn, tpex_df)  ← INSERT OR IGNORE, NO COMMIT
Line 546: conn.commit()                        ← THE ACTUAL COMMIT (per trading date)
Line 547: print(f"  Committed {target_d} ✓")
...
Line 550: conn.close()                         ← after all dates in loop
```

The `conn.commit()` at line 546 is **inside** the `for target_d in missing_dates:` loop — meaning one commit per trading date. Python's `sqlite3` module default is NOT auto-commit, so rows are not visible until `conn.commit()` is explicitly called.

---

## write_committed=True Accuracy Analysis

The integrated wrapper sets `write_committed=True` after `check_market_freshness()` returns `FULL_MARKET_FRESH`.

**Chain of custody**:
1. `conn.commit()` at line 546 → rows written to SQLite WAL, now readable
2. `check_market_freshness(conn, today, ...)` → reads row count for today
3. `FULL_MARKET_FRESH` requires a minimum row count (non-benchmark stocks)
4. Readable rows require `conn.commit()` to have completed
5. Therefore: `FULL_MARKET_FRESH` ⟹ `conn.commit()` completed
6. Therefore: `write_committed=True` after `FULL_MARKET_FRESH` is an **accurate proxy**

**Conclusion**: `write_committed=True` is NOT early — it is set AFTER confirmed data visibility. No implementation change required.

---

## Crash Window Analysis (Summary)

There exists a window between:
- `conn.commit()` at backfill line 546 (data written to SQLite)
- `write_committed=True` written to state file (by wrapper)

If a SIGKILL occurs in this window:
- State file remains `status=RUNNING`
- PID is dead
- `SameDayStateGuard.check()` → `WRITE_OUTCOME_UNKNOWN` → **fail-closed**
- Manual intervention required to verify data and clear state

This is **correct behavior** — conservative fail-closed protects against double-write more than partial-write.

See `session71l_crash_window_analysis.md` for full analysis.
