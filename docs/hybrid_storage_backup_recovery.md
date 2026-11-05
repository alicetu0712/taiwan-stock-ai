# Hybrid Forward Shadow — Backup & Disaster Recovery

**Research pipeline only** — does NOT cover production Neon PostgreSQL backup.  
**Rule version:** hybrid_v1 | Freeze date: 2026-11-05

---

## 1. Backup Policy

### What is backed up

| Item | Backup required | Reason |
|------|----------------|--------|
| `data/platform.db` | YES | Contains all PROSPECTIVE decisions and outcomes |
| `data/hybrid_backtest.json` | YES | In-sample comparison results |
| Source code | Via git | Already in version control |
| DailyPrice data in SQLite | YES (included in DB backup) | Needed for outcome computation |

### What is NOT backed up by this policy

| Item | Reason |
|------|--------|
| Production Neon PostgreSQL | Covered by separate production backup policy |
| ForwardSignals in production | Same |
| ACTUAL / PAPER trade records | Same |

---

## 2. Backup Frequency & Retention

### Option D (local cron — current active mode)

| Setting | Value | Rationale |
|---------|-------|-----------|
| Backup frequency | Weekly (every Sunday, or after each trading week) | 1-day RPO is acceptable for research; daily backup is overkill |
| Backup method | `cp data/platform.db data/platform.db.bak.$(date +%Y%m%d)` | Simple file copy |
| Retention | 4 weekly snapshots | Rolling 4-week window |
| Backup storage | Same machine, different directory | Simple; sufficient for single-machine setup |
| Off-machine copy | Recommended (e.g. iCloud, Time Machine, external drive) | Required if machine is lost |

**Backup command:**
```bash
mkdir -p data/backups
cp data/platform.db "data/backups/platform_$(date +%Y%m%d_%H%M).db"
# Keep only last 4 backups
ls -t data/backups/platform_*.db | tail -n +5 | xargs rm -f
```

**Add to cron:**
```cron
0 20 * * 0  cd /path/to/stock_platform && mkdir -p data/backups && cp data/platform.db "data/backups/platform_$(date +%%Y%%m%%d).db"
```

### Option A (GitHub artifact cache — when schedule is enabled)

| Setting | Value | Rationale |
|---------|-------|-----------|
| Implicit backup frequency | Every workflow run (Mon–Fri) | Each run saves a new cache entry |
| Cache key pattern | `hybrid-research-db-v1-Linux-{run_id}` | Unique per run = one entry per day |
| Retention per entry | 7 days after last access | GitHub default |
| Active retention | As long as there's at least one run per 7 calendar days | Requires weekly cache-refresh run during holidays |
| Off-platform backup | Recommended monthly | Download latest `data/platform.db` artifact and store locally |

**Cache expiry mitigation — holiday maintenance run:**
```yaml
# Add to schedule after main schedule is enabled:
# - cron: '0 8 * * 1'   # Monday 08:00 UTC = 16:00 Taiwan — weekly cache refresh
# workflow_dispatch with backfill_outcomes_only=true keeps cache alive without new decisions
```

---

## 3. RPO & RTO Targets

**These are proposed research targets, NOT production SLAs. Subject to revision.**

| Metric | Proposed Target | Notes |
|--------|----------------|-------|
| RPO (Recovery Point Objective) | 1 trading week | Lose at most 5 trading days of PROSPECTIVE decisions in worst case |
| RTO (Recovery Time Objective) | 2 hours | Time to restore backup + verify integrity + resume operation |
| Holiday gap RPO | Acceptable data loss | No PROSPECTIVE decisions during non-trading days anyway |

---

## 4. Restore Procedure

### Step 1 — Identify backup

```bash
ls -lht data/backups/platform_*.db
# Select most recent backup before the incident
```

### Step 2 — Verify backup integrity

```bash
# Check SQLite file is not corrupted
sqlite3 data/backups/platform_YYYYMMDD.db "PRAGMA integrity_check"
# Expected output: "ok"

# Verify research tables and decision count
python3 - <<'EOF'
import sqlite3
conn = sqlite3.connect("data/backups/platform_YYYYMMDD.db")
n = conn.execute("SELECT COUNT(*) FROM hybrid_forward_decision").fetchone()[0]
last = conn.execute("SELECT MAX(trade_date) FROM hybrid_forward_decision").fetchone()[0]
print(f"Decisions: {n}, Last trade_date: {last}")
# Check decision hashes are present and non-null
nullhash = conn.execute("SELECT COUNT(*) FROM hybrid_forward_decision WHERE decision_hash IS NULL").fetchone()[0]
print(f"NULL decision_hash rows: {nullhash}  (expected: 0)")
conn.close()
EOF
```

### Step 3 — Restore

```bash
# SAFETY: Create a copy of current (possibly corrupted) state before overwriting
cp data/platform.db data/platform.db.corrupted_$(date +%Y%m%d)

# Restore from backup
cp data/backups/platform_YYYYMMDD.db data/platform.db
```

### Step 4 — Verify restored DB

```bash
python3 - <<'EOF'
import sqlite3
from src.research.hybrid_forward_db import get_operational_summary
import json
conn = sqlite3.connect("data/platform.db")
summary = get_operational_summary(conn)
conn.close()
print(json.dumps(summary, indent=2, default=str))
EOF
```

**Expected:** `latest_run.status` = SUCCESS, `prospective_decisions` = same count as pre-incident.

### Step 5 — Backfill missing decisions

If some trading days were lost, they can be retrospectively recovered as `LATE_CAPTURE` (not PROSPECTIVE):

```bash
# For each missed trading day:
python3 scripts/run_hybrid_forward_shadow.py --date YYYY-MM-DD --force-stale
```

Note: These will be classified `LATE_CAPTURE` or `RETROSPECTIVE_RECONSTRUCTION` (not PROSPECTIVE) depending on the date, as designed.

---

## 5. Isolated Restore Test Results

### Test performed: `tests/test_cross_runner_persistence.py`

The following test sequence simulates a full backup/restore cycle:

```
test_CR03: Run A writes decision with known decision_hash
           → shutil.copy2(db_a, db_b)  [simulates restore from backup]
           → Run B opens db_b and verifies decision_hash is bit-for-bit identical
           RESULT: PASS
```

**Proof of correctness:** `sqlite3` database files are platform-independent binary files. `shutil.copy2()` preserves all bytes exactly. The copied file opens correctly and all rows, hashes, and FK relationships are intact (verified by CR03, CR06, CR16).

**This satisfies the requirement:** "不能只證明備份成功，還要證明可以還原並讀取原始 Decision Hash."

---

## 6. Failure Notification

### Local cron failure detection

Add a wrapper script that checks run log status and sends notification:

```bash
#!/bin/bash
# scripts/check_hybrid_shadow_health.sh
python3 - <<'EOF'
import sqlite3, sys
conn = sqlite3.connect("data/platform.db")
try:
    result = conn.execute(
        "SELECT status, started_at FROM hybrid_forward_run_log ORDER BY started_at DESC LIMIT 3"
    ).fetchall()
    consec_fail = sum(1 for r in result if r[0] in ("FAILED", "PARTIAL", "CONFLICT"))
    if consec_fail >= 2:
        print(f"ALERT: {consec_fail} consecutive failures in hybrid shadow run log")
        sys.exit(1)
    print(f"OK: Last 3 runs: {[r[0] for r in result]}")
except Exception as e:
    print(f"ERROR: Could not check run log: {e}")
    sys.exit(1)
finally:
    conn.close()
EOF
```

Add to weekly check:
```cron
0 9 * * 1  cd /path/to/stock_platform && bash scripts/check_hybrid_shadow_health.sh >> logs/health_check.log 2>&1
```

### GitHub Actions failure notification

Workflow failures appear in GitHub Actions UI. Additionally:
- `get_operational_summary()` is printed in step 2h with `if: always()` — visible even on failure
- Run status is recorded in `hybrid_forward_run_log` with `error_summary`

---

## 7. Incident Runbook

### Incident type 1: SQLite file missing or corrupted

**Symptoms:** `data/platform.db` missing or `PRAGMA integrity_check` returns errors  
**Recovery:**
1. Run `python3 scripts/run_hybrid_forward_shadow.py` — if corruption is in DailyPrice tables (not hybrid tables), the schema will recreate the hybrid tables
2. If full restore needed, follow Steps 1–5 in Section 4 above
3. Document the incident and root cause

### Incident type 2: Consecutive failures ≥ 3 (DailyPrice stale)

**Symptoms:** `status=BLOCKED_STALE_DATA` in run log; DailyPrice last_date > 7 days ago  
**Recovery:**
1. Run the DailyPrice collector: `python3 scripts/collect_daily_prices.py`
2. Verify: `python3 -c "import sqlite3; c=sqlite3.connect('data/platform.db'); print(c.execute('SELECT MAX(date) FROM daily_prices WHERE stock_id=\"0050\"').fetchone())"`
3. Re-run shadow: `python3 scripts/run_hybrid_forward_shadow.py`
4. Missed days during outage will be tagged `LATE_CAPTURE` (not PROSPECTIVE) — this is by design

### Incident type 3: GitHub artifact cache evicted (Option A — holiday gap)

**Symptoms:** Workflow runs with cache miss; no prior data available  
**Recovery:**
1. Upload a seeded `data/platform.db` as an artifact manually via GitHub UI
2. Or: re-run the shadow locally (Option D) for the gap period, then push the DB file
3. Future prevention: schedule a weekly maintenance run to keep cache alive

### Incident type 4: ConflictError in run log

**Symptoms:** `status=CONFLICT`, `conflict_count > 0`  
**Recovery:**
1. Do NOT run with `--force-stale` or attempt to overwrite
2. Check the `error_summary` in `hybrid_forward_run_log` for the affected stock/date
3. Compare with git history to verify the rule wasn't changed: `git diff 6602c3b -- src/research/hybrid_entry_strategy.py`
4. If a data issue is confirmed (DailyPrice retroactive correction), document in a correction note — the original decision remains correct
5. If a code change was the cause, freeze all further changes and investigate

---

## 8. Recovery Capability Summary

| Scenario | Recovery possible | Data loss |
|----------|------------------|-----------|
| SQLite file accidentally deleted | YES — from backup | Since last backup (up to 1 week) |
| SQLite file corrupted | YES — from backup | Since last backup |
| DailyPrice stale for 1–7 days | YES — resume; missed days = LATE_CAPTURE | 0 PROSPECTIVE records; LATE_CAPTURE recorded |
| DailyPrice stale > 7 days | YES — force-stale backfill; missed days = LATE_CAPTURE | 0 PROSPECTIVE; LATE_CAPTURE recorded |
| GitHub artifact cache evicted | YES — Option D backup + re-upload | Depends on local backup freshness |
| ConflictError | YES — original record preserved | 0 (original record unchanged) |
| Machine total loss (Option D) | YES — from off-machine backup (Time Machine/cloud) | Since last off-machine sync |
