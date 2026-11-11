# Session 71D — RC-2 H3 Runtime Audit

**Date**: 2026-11-11  
**Check Time**: 2026-11-11 14:16–14:25 CST  
**Authorization**: AUTH-S71-BUNDLE-A (read-only acceptance phase)

---

## 1. H3 Definition (Recap)

H3 (Scheduled Runtime Acceptance) requires:
1. A **natural scheduled cron execution** after RC-2 deployment (no manual trigger)
2. The execution uses the RC-2-patched script (hash `4eb6eacf...`)
3. Results are observable in the log

---

## 2. Current State

### RC-2 Deployment Date
Session 66, 2026-11-11 (documented in memory).

### Current Time
**2026-11-11 14:20:30 CST** (06:20 UTC)

### Time Until Next Scheduled Cron
**16:00 CST − 14:20 CST ≈ 1h 40min remaining**

### Nov 11 Log Entries
```bash
grep "[2026-11-11" logs/hybrid_cron.log → 0 entries
```
**Result**: NO_NOV11_ENTRIES

---

## 3. RC-2 Filter Specification

| Version | Code | Behavior |
|---|---|---|
| Original (pre-RC2) | `if len(sid) > 4 and not sid.isdigit():` | Excludes: len>4 AND non-numeric (warrants with letter suffix) |
| Patched (RC-2) | `if len(sid) > 4:` | Excludes: ALL len>4 (warrants + numeric series codes) |

**Function**: `_is_excluded(name, stock_id)` in `scripts/backfill_daily_prices.py:93–100`

**Scope**: Local SQLite ONLY. backfill_daily_prices.py explicitly "NEVER touches production Neon."

### RC-2 Filter + EXCLUDE_KEYWORDS Interaction

```python
def _is_excluded(name: str, stock_id: str) -> bool:
    name_up = str(name).upper()
    if any(kw.upper() in name_up for kw in EXCLUDE_KEYWORDS):   # ETF, ETN, REIT, etc.
        return True
    sid = str(stock_id).strip()
    if len(sid) > 4:    # RC-2 patch
        return True
    return False

EXCLUDE_KEYWORDS = ["ETF", "ETN", "REIT", "REITs", "特別股", "受益憑證", "DR", "DEPOSITARY", "WARRANT", "WARRANTS"]
```

Stocks excluded by RC-2 `len > 4` check that were NOT excluded by name keyword:
- Warrant codes with numeric structure (e.g., `12345P` where `isdigit()` is False)
- Multi-series products with purely numeric codes `> 4 chars` that don't have keyword in name

Local SQLite currently has 111,710 rows with `len(stock_id) > 4` — these were written before RC-2 deployment. Future cron runs will NOT add more such rows.

---

## 4. Prior Cron Run Analysis (Nov 10)

```
[2026-11-10T08:00:00Z] [cron] Start
[2026-11-10T08:34:30Z] TWSE api_date=2026-11-09 != target 2026-11-10 → QG FAIL
[2026-11-10T08:34:31Z] PROVIDER_NOT_READY → retry 1/3 in 30min
[2026-11-10T09:04:31Z] Retry 2: same QG failure
[2026-11-10T09:06:57Z] PROVIDER_NOT_READY → retry 2/3
[2026-11-10T09:36:57Z] Retry 3: same QG failure
[2026-11-10T09:37:32Z] BLOCKED_STALE_DATA (after 3 retries)
[2026-11-10T09:37:32Z] [alert] NEW STALE_DATA on 2026-11-10
```

**Analysis**:
- RC-2 patch was deployed Nov 11 (Session 66)
- Nov 10 cron ran **before** RC-2 deployment → used original (pre-RC2) code
- QG failure reason: TWSE returned `api_date=2026-11-09` for `target=2026-11-10` (TWSE publishing delay)
- Zero rows written to local SQLite on Nov 10

---

## 5. RC-2 File Verification

```
SHA-256 of scripts/backfill_daily_prices.py:
  4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb  ✓ (RC-2 patched)
```

---

## 6. Expected H3 Scenarios for Nov 11 16:00 Cron

| Scenario | QG Result | SQLite Write | RC-2 Filter Observable | Classification |
|---|---|---|---|---|
| A: TWSE api_date = 2026-11-11 (today), data clean | PASS | YES | Warrant IDs absent in new rows | `H3_PASS` |
| B: TWSE api_date = 2026-11-10 (yesterday), date mismatch | FAIL | NO | Filter ran but QG blocked write | `H3_INCONCLUSIVE` |
| C: TWSE api_date = 2026-11-11 but warrant IDs appear in DB | PASS | YES but filtered wrong | `FILTER_EFFECT_FAILED` | `H3_FAIL` |
| D: Cron did not fire at 16:00 | — | NO | — | `H3_PENDING` |
| E: Runtime error in `_is_excluded()` | ERROR | Partial | — | `H3_FAIL` |

**Most likely outcome based on Nov 10 pattern**: Scenario A or B.  
Nov 10 had api_date mismatch; if TWSE publishes correctly on Nov 11, Scenario A is possible.

---

## 7. H3 Verdict (at 14:20 CST)

### `H3_PENDING`

**Reason**: No natural cron execution has occurred after RC-2 deployment. Current time is 14:20 CST; next scheduled execution is 16:00 CST (~1h 40min). No manual trigger performed (not authorized).

---

## 8. H3 Check Procedure (for user at 16:05+ CST)

```bash
# 1. Confirm natural execution occurred (UTC 08:00 = CST 16:00)
grep "\[2026-11-11T08" logs/hybrid_cron.log

# 2. Final status
grep "BLOCKED_STALE\|PROVIDER_NOT_READY\|quality gate\|Done\|H3" logs/hybrid_cron.log | \
  grep "2026-11-11" | tail -10

# 3. DB row count change
python3 << 'EOF'
import sqlite3
con = sqlite3.connect("file:data/platform.db?mode=ro", uri=True)
c = con.cursor()
c.execute("SELECT COUNT(*), MAX(date) FROM daily_prices")
print("Local SQLite:", c.fetchone())
con.close()
EOF
# Baseline: (534770, '2026-11-05')
# If changed → warrant check below

# 4. If DB changed — verify RC-2 filter worked
python3 << 'EOF'
import sqlite3
con = sqlite3.connect("file:data/platform.db?mode=ro", uri=True)
c = con.cursor()
c.execute("SELECT stock_id, COUNT(*) FROM daily_prices WHERE date > '2026-11-05' GROUP BY stock_id")
new = c.fetchall()
suspicious = [(s, n) for s, n in new if len(s) > 4]
print(f"New entries after 2026-11-05: {len(new)}")
print(f"Suspicious (len>4): {suspicious}")
# RC-2 PASS: suspicious = [] (empty)
# RC-2 FAIL: suspicious has entries
con.close()
EOF
```

---

## 9. H3 Classification Decision Table

| Evidence | Classification |
|---|---|
| Nov 11 cron log entries found, `quality gate` PASS, new SQLite rows, NO len>4 entries | `H3_PASS` + `FILTER_EFFECT_VERIFIED` |
| Nov 11 cron log entries found, `quality gate FAILED`, no new SQLite rows | `H3_INCONCLUSIVE` (pre-existing QG issue) |
| Nov 11 cron log entries found, `quality gate` PASS, new rows WITH len>4 | `H3_FAIL` + `FILTER_EFFECT_FAILED` |
| No Nov 11 cron log entries found after 16:05 CST | Investigate scheduler; `H3_PENDING` |

---

## 10. Prior H3 History

| Session | H3 Status | Key Fact |
|---|---|---|
| S66 | H3_PENDING | RC-2 just deployed (2026-11-11 morning) |
| S67 | H3_PENDING | No natural run |
| S68 | H3_PENDING | PRE_EXISTING_FAILURE_CONFIRMED for QG |
| S71B | H3_PENDING | Check at 12:49 CST |
| S71C | H3_PENDING | Check at 14:05 CST |
| **S71D** | **H3_PENDING** | Check at 14:20 CST; cron at 16:00 |
