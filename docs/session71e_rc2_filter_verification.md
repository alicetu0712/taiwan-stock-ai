# Session 71E — RC-2 Filter Verification

**Date**: 2026-11-11  
**Check Time**: 2026-11-11 14:31 CST  
**Authorization**: STRICT_READ_ONLY

---

## 1. Evidence Taxonomy

Per spec PART D, three evidence types must be kept separate:

| Type | Definition | Current Status |
|---|---|---|
| **Static Evidence** | File on disk has correct content and hash | VERIFIED |
| **Runtime Version Evidence** | Natural cron execution used RC-2 file | PENDING (cron not yet run) |
| **Filter Effect Evidence** | Execution actually excluded len>4 IDs | PENDING |

---

## 2. Static Evidence (VERIFIED)

### 2A. Hash

```
SHA-256: 4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb
File:    scripts/backfill_daily_prices.py
Method:  shasum -a 256
Time:    2026-11-11 14:31 CST
```

**Status**: `RC2_STATIC_HASH_VERIFIED`

### 2B. Filter Code

```python
# scripts/backfill_daily_prices.py:93-100
def _is_excluded(name: str, stock_id: str) -> bool:
    name_up = str(name).upper()
    if any(kw.upper() in name_up for kw in EXCLUDE_KEYWORDS):
        return True
    sid = str(stock_id).strip()
    if len(sid) > 4:          # ← RC-2 patch (was: len(sid) > 4 and not sid.isdigit())
        return True
    return False
```

**Status**: `RC2_FILTER_CODE_VERIFIED`

### 2C. Known Pre-RC2 Data in SQLite

Local SQLite `data/platform.db` has 111,710 existing rows where `len(stock_id) > 4`. These were written **before** RC-2 deployment. RC-2 prevents NEW additions; it does not clean up existing data.

---

## 3. Runtime Version Evidence

### 3A. Execution Chain

```
crontab: hybrid_shadow_cron.py --execute
  → _run_backfill() → subprocess: backfill_daily_prices.py --execute
      → uses: scripts/backfill_daily_prices.py (from SCRIPTS_DIR)
      → SCRIPTS_DIR = Path(__file__).parent = scripts/
      → resolves to: /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/backfill_daily_prices.py
```

The cron subprocess **will** use the RC-2 patched file at the above absolute path, which has hash `4eb6eacf...`. This is deterministic from the script source code.

**Status**: `RC2_RUNTIME_VERSION_INFERRED` (static path analysis, not yet runtime-confirmed)

After natural cron fires:
- Look for `[backfill] Running: .../backfill_daily_prices.py` in log
- This confirms the runtime path; combined with static hash → `RC2_RUNTIME_VERSION_VERIFIED`

---

## 4. Filter Effect Evidence

### 4A. What would constitute direct filter evidence

For Filter Effect to be VERIFIED, one of:
- Log lines showing specific `> 4` IDs were skipped (script does NOT log individual exclusions)
- DB shows new rows written, zero with `len(stock_id) > 4`
- QG passed and new legitimate 4-char stocks written, no 5+ char IDs in new rows

### 4B. What cannot substitute

| Inadequate evidence | Why |
|---|---|
| Static hash correct | Proves file content, not execution |
| DB row count unchanged | Could mean QG failure, not filter success |
| No new 5+ char rows in DB | Could be because nothing was written at all |
| Log shows backfill ran | Doesn't prove filter called correctly |

### 4C. Post-Cron Filter Check Procedure

```bash
# After cron runs and IF new rows written to SQLite:
python3 << 'EOF'
import sqlite3
con = sqlite3.connect("file:data/platform.db?mode=ro", uri=True)
c = con.cursor()
c.execute("SELECT stock_id, COUNT(*) FROM daily_prices WHERE date > '2026-11-05' GROUP BY stock_id")
new = c.fetchall()
suspicious = [(s, n) for s, n in new if len(s) > 4]
legit = [(s, n) for s, n in new if len(s) <= 4]
print(f"New rows total: {len(new)} entries")
print(f"Legitimate (len<=4): {len(legit)}")
print(f"Suspicious (len>4): {suspicious}")
# RC-2 PASS: suspicious = []
# RC-2 FAIL: suspicious has entries
con.close()
EOF
```

---

## 5. Current Verdict

| Evidence Type | Status | Confidence |
|---|---|---|
| Static hash | `VERIFIED` | HIGH |
| Filter code content | `VERIFIED` | HIGH |
| Runtime version | `INFERRED` (path deterministic) | MEDIUM (not yet runtime) |
| Filter effect | `UNVERIFIED` | — (cron not yet run) |

**Overall**: `FILTER_EFFECT_UNVERIFIED` — to be updated after 16:00 CST cron execution.
