# Session 71G — Acceptance Test Plan

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / MIGRATION_DESIGN_ONLY  
**Note**: Tests designed here; not executed

---

## 1. Test Plan Scope

This plan covers two distinct acceptance phases:

| Phase | Trigger | Purpose |
|---|---|---|
| **Phase 1: H3** | Next natural cron fire (Nov 12 16:00 CST) | RC-2 runtime acceptance under existing cron |
| **Phase 2: launchd migration acceptance** | After migration authorized and deployed | Verify new scheduler behavior |

These are INDEPENDENT. H3 must not be declared PASS based on launchd loading alone.

---

## 2. Phase 1 — H3 Cron Natural Runtime Acceptance

### Pre-conditions
- 2026-11-12 is a trading day: `True` (confirmed)
- Machine must be awake at 16:00 CST
- RC-2 hash must be `4eb6eacf...`
- No dual scheduler (cron only)

### AT-H3-01: Trigger Evidence

```bash
# After 16:00:30 CST on Nov 12:
grep "\[2026-11-12" logs/hybrid_cron.log | head -3
```

| Check | Accept Criterion | Fail Criterion |
|---|---|---|
| First log entry exists | Contains `[2026-11-12T08` (UTC) | Zero entries after 16:05 CST |
| Trigger time | Within ± 90 seconds of 16:00 CST | > 5 minutes after 16:00 |
| `--execute` flag | Log shows `EXECUTE` mode | Log shows `DRY-RUN` |

### AT-H3-02: RC-2 Version

```bash
shasum -a 256 scripts/backfill_daily_prices.py
```

| Check | Accept Criterion |
|---|---|
| SHA-256 | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` |
| `_is_excluded()` present | `grep "if len(sid) > 4:" scripts/backfill_daily_prices.py` → line 98 |

### AT-H3-03: RC-2 Filter Runtime Effect

```bash
# After cron completes:
python3 << 'EOF'
import sqlite3
con = sqlite3.connect("file:data/platform.db?mode=ro", uri=True)
c = con.cursor()
c.execute("SELECT COUNT(*), MAX(date) FROM daily_prices WHERE date > '2026-11-05'")
new_total, new_max = c.fetchone()
print(f"New rows: {new_total}, Max date: {new_max}")

# RC-2 contamination check
c.execute("""
  SELECT stock_id, COUNT(*) cnt FROM daily_prices 
  WHERE date > '2026-11-05' AND LENGTH(stock_id) > 4
  GROUP BY stock_id LIMIT 5
""")
suspicious = c.fetchall()
print(f"RC-2 contamination (len>4): {suspicious}")
con.close()
EOF
```

| Check | Accept Criterion | H3 Verdict |
|---|---|---|
| New rows > 0 | QG PASS → SQLite updated | H3 PASS (filter runtime verified) |
| New rows = 0 | QG FAIL → `BLOCKED_STALE_DATA` | H3 CONDITIONAL (cron fired but QG blocked; filter UNVERIFIED) |
| Contamination = 0 | No len>4 IDs in new rows | RC-2 filter RUNTIME_VERIFIED |
| Contamination > 0 | RC-2 filter not working | RC-2 FILTER_FAIL |

### AT-H3-04: Quality Gate Outcome

```bash
grep "\[2026-11-12" logs/hybrid_cron.log | grep -E "BLOCKED|SUCCESS|FAIL|api_date|freshness"
```

Both `BLOCKED_STALE_DATA` and `SUCCESS` are acceptable H3 outcomes — what matters is that cron fired with RC-2.

### AT-H3-05: Production Isolation

```bash
# Check Neon unchanged (using existing Neon check)
python3 -c "
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
load_dotenv()
url = os.getenv('NEON_URL','')
if url:
    e = create_engine(url.replace('postgres://','postgresql://'))
    with e.connect() as c:
        r = c.execute(text('SELECT COUNT(*), MAX(date) FROM daily_prices'))
        print('Neon:', r.fetchone())
else:
    print('NEON_URL not set')
"
```

Expected: Neon row count / max date unchanged from last check (Nov 10 date, 409,039 rows).

### H3 Decision Matrix

| All AT-H3-01 to AT-H3-05 pass | H3 = `ACCEPTED` |
|---|---|
| AT-H3-01 passes, AT-H3-03 has 0 new rows | H3 = `H3_CONDITIONAL_CRON_FIRED_QG_BLOCKED` — cron fired with RC-2, filter cannot be tested |
| AT-H3-01 fails (no log entry) | H3 = `H3_PENDING` again — escalate to launchd migration |
| AT-H3-03 contamination > 0 | H3 = `H3_FAIL` — RC-2 filter defective — STOP |

---

## 3. Phase 2 — LaunchD Migration Acceptance

**Pre-condition**: launchd migration completed per `session71g_cutover_rollback_plan.md` and authorized.

### AT-LD-01: LaunchD Loading Verified

```bash
launchctl list com.antigravity.stockplatform.dailybackfill
```

Accept: entry exists with label, PID="-"

### AT-LD-02: Crontab Removed

```bash
crontab -l | grep hybrid_shadow_cron
```

Accept: empty (zero matches)

### AT-LD-03: Schedule Verification

```bash
# Verify plist schedule
/usr/libexec/PlistBuddy -c "Print :StartCalendarInterval" \
  ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist
```

Accept: 5 entries, each with Hour=16, Minute=0, Weekday 1-5

### AT-LD-04: First Natural launchd Fire

(Same checks as AT-H3-01 to AT-H3-05, but under launchd)

Additional check:
```bash
# Verify trigger_source = "cron_scheduled" (not "manual")
python3 -c "
import json
s = json.load(open('data/.cron_state.json'))
print('trigger_source:', s.get('trigger_source'))
print('status:', s.get('status'))
print('today:', s.get('today'))
"
```

Accept: `trigger_source = "cron_scheduled"` (launchd stdout is not a TTY → `isatty()=False`)

### AT-LD-05: No Duplicate Job Verification

```bash
# Verify only one scheduler active
crontab -l | grep hybrid | wc -l    # → 0
launchctl list | grep antigravity | wc -l  # → 1
```

### AT-LD-06: QG Preserved

Verify `run_quality_gate()` still called inside backfill (static check):

```bash
grep -n "run_quality_gate" scripts/backfill_daily_prices.py
# Expected: lines 504-505 (unchanged)
```

### AT-LD-07: RC-2 Preserved

```bash
shasum -a 256 scripts/backfill_daily_prices.py
# Expected: 4eb6eacf...
```

### AT-LD-08: SQLite Isolation

```bash
python3 -c "
import sqlite3
c=sqlite3.connect('file:data/platform.db?mode=ro',uri=True).cursor()
c.execute('SELECT COUNT(*),MAX(date) FROM daily_prices')
print(c.fetchone())
"
# Compare to pre-migration baseline — should grow (not shrink; not Neon)
```

### AT-LD-09: Catch-up Behavior Test (Optional)

If user is willing to test:
1. At 15:55, let machine go to sleep
2. At 16:30, wake machine (full user wake, lid open)
3. Observe: launchd should fire within ~60-120 seconds
4. Check log for new `[today]` entries
5. Verify SQLite updated or QG blocked appropriately

---

## 4. Test Result Template

### Phase 1 (H3)

| Test | Result | Verdict |
|---|---|---|
| AT-H3-01 Trigger | PENDING | PENDING |
| AT-H3-02 RC-2 Version | PENDING | PENDING |
| AT-H3-03 Filter Effect | PENDING | PENDING |
| AT-H3-04 QG Outcome | PENDING | PENDING |
| AT-H3-05 Production Isolation | PENDING | PENDING |
| **H3 Overall** | PENDING | `H3_PENDING` |

### Phase 2 (LaunchD)

| Test | Result | Verdict |
|---|---|---|
| AT-LD-01 Loading | NOT STARTED | PENDING |
| AT-LD-02 Crontab Removed | NOT STARTED | PENDING |
| AT-LD-03 Schedule | NOT STARTED | PENDING |
| AT-LD-04 Natural Fire | NOT STARTED | PENDING |
| AT-LD-05 No Duplicate | NOT STARTED | PENDING |
| AT-LD-06 QG Preserved | NOT STARTED | PENDING |
| AT-LD-07 RC-2 Preserved | NOT STARTED | PENDING |
| AT-LD-08 SQLite Isolation | NOT STARTED | PENDING |
| **LaunchD Acceptance** | NOT STARTED | `PENDING_AUTHORIZATION` |
