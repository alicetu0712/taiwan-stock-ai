# Session 71Q — RC-2 H3 Evidence

**Session**: 71Q  
**Verdict**: `H3_GUARD_AUTHORIZED_QG_NEVER_PASSED`  
**Updated**: 2026-11-13 22:06 CST (all retries exhausted)

---

## H3 Requirement Summary — FINAL

| Condition | Required | Final Status |
|---|---|---|
| Genuine Natural Cron Execution | YES | **CONFIRMED** ✓ (08:00:00Z = 16:00:00 CST) |
| Guard Authorization | YES | **CONFIRMED** ✓ (no BLOCKED; exit_code=0 × 4 runs) |
| QG PASS | YES | **NEVER_PASSED** ✗ (all 4 runs failed) |
| RC-2 Filter Runtime Evidence | YES | **N/A** (QG blocked all writes) |
| SQLite Write Outcome | YES | **NO_WRITE** (534,770 unchanged) |
| Post-write Freshness PASS | YES | **PROVIDER_NOT_READY** |
| No RC-2 Runtime Regression | YES | N/A (no writes) |

**Result: H3_GUARD_AUTHORIZED_QG_NEVER_PASSED**

Two of seven conditions confirmed. QG failure is structural (TWSE API limitation), not a code or guard issue. Full H3 (including RC-2 filter runtime) requires a future trading day where TWSE data is available during the cron retry window.

---

## RC-2 Filter Static Analysis (pre-runtime)

The RC-2 filter in the deployed `backfill_daily_prices.py` (hash `202e2231...`) was AST-verified in S71N and S71P:

```python
EXCLUDE_KEYWORDS = ['ETF', 'ETN', 'REIT', 'REITs', '特別股', '受益憑證', 
                    'DR', 'DEPOSITARY', 'WARRANT', 'WARRANTS']

def _is_excluded(sid, name):
    if len(sid) > 4:
        return True  # RC-2: exclude 5+ character IDs
    for kw in EXCLUDE_KEYWORDS:
        if kw in name:
            return True
    return False
```

The `len(sid) > 4` rule is unchanged from S66.

**Static analysis ≠ runtime evidence.** H3 requires actual execution evidence.

---

## H3 Blocking History

| Session | Date | Reason H3 Missed |
|---|---|---|
| S66 | 2026-11-11 | Mac asleep (Clamshell) |
| S67 | 2026-11-11 | No log — sleep |
| S68 | 2026-11-11 | 00:46 CST run (pre-Deploy-A, pre-window) |
| S71E | 2026-11-12 16:00 | Mac asleep (suspected) |
| S71I | 2026-11-12 16:00 | Mac asleep (confirmed) |
| S71Q | 2026-11-13 | **CRON FIRED — Guard AUTHORIZED — QG retrying** |

Deploy A was at 01:35 CST Nov 13. This is the **first post-Deploy-A cron execution.**  
Cron triggered at 16:00:00 CST. Guard authorization CONFIRMED. QG in retry 2/3.

---

## Expected RC-2 Filter Results (if cron runs)

For a typical trading day, approximately:
- ~2000 securities in the full TWSE/TPEx dataset
- RC-2 `len(sid) > 4` filters out securities with 5+ character IDs (warrants, structured products)
- Expected retained count: ~1000-1200 common stocks (5-digit market stocks have 4-character SIDs like "2330")
- Expected filtered count: varies by day

**Note**: Some legitimate 5-digit ETFs (e.g., "0056") have 4-character SIDs and are NOT filtered by `len > 4`. ETFs filtered by keyword are separate from the length filter.

---

## Post-16:00 H3 Evidence Checklist

After cron fires (read-only):

1. Find log entry: `[backfill] Running:` → Backfill started
2. Find log entry: `[backfill] total_written:` → Written count
3. Find log entry: `quality gate PASSED` for 2026-11-13
4. No `[BACKFILL_GUARD] BLOCKED` in log → Guard authorized
5. `SELECT MAX(date) FROM daily_prices` → should advance from 2026-11-05 to 2026-11-13
6. `SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-13' AND length(sid)>4` → should be 0 (RC-2 enforcement)
7. `SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-13'` → retained count
8. Post-write freshness in log: `FULL_MARKET_FRESH` or `PROVIDER_NOT_READY`
