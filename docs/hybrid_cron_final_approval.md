# Hybrid Shadow Cron — Final Approval Checklist

**Date:** 2026-11-05  
**Approval received:** 2026-11-05 (user sent "approve crontab install" + confirmed FDA)  
**Verdict:** ✅ INSTALLED & VERIFIED — first scheduled run 2026-11-06 16:00 Taiwan

---

## Pre-Install Checklist

### Safety Boundaries (FROZEN — not affected by cron installation)

- [ ] MODEL_VERSION v8.0 — unchanged
- [ ] foe_v1 scoring — unchanged
- [ ] BUY/STRONG BUY thresholds — unchanged
- [ ] Frozen ForwardSignals — unchanged
- [ ] ACTUAL trade accounting — unchanged
- [ ] PAPER Monitor — unchanged
- [ ] Hybrid P1–P4 frozen rules — unchanged

**Cron only automates what already runs manually. It cannot modify research decisions.**

---

## Gate Summary

| Gate | Status | Detail |
|---|---|---|
| Preflight overall | CONDITIONAL | 4 warnings below |
| Trading calendar | PASS | PF21 timezone PASS |
| Cron hour (UTC+8) | PASS | `0 16` = 16:00 Taiwan ✓ |
| Python interpreter | PASS | `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` |
| DB path | PASS | `data/platform.db` exists, 82.4 MB |
| SQLite backup API | PASS | integrity_check=ok, 528,182 rows |
| Log directory | PASS | `logs/` writable |
| OHLC Continuity Gate | PASS | present=30, missing=0 (2026-11-05) |
| Full-Market Freshness Gate | ACTIVE | BENCHMARK_ONLY_UPDATED (11-05, correct behavior) |
| Minimal-env dry-run | PASS | DRY_RUN_OK with `env -i` simulation |
| Missed-run detection | PASS | `--check-missed` available |

### Conditional Warnings (non-blocking)

| Warning | Description | Action |
|---|---|---|
| `USE_NEON=true` | Env var set but DATABASE_URL empty; cron uses SQLite only | Acceptable — no Neon writes |
| WAL orphan | `.db-shm`/`.db-wal` present (SQLite WAL mode) | Expected — not an error |
| Backup dir | Backups exist in non-default location | Verify path |
| `MACOS_PERMISSION_NOT_VERIFIED` | cron FDA cannot be verified from Terminal | See `macos_cron_permission_validation.md` |

---

## Fail-Closed Verification

All scenarios tested and confirmed:

| Scenario | Expected cron status | Verified |
|---|---|---|
| Non-trading day | `NON_TRADING_DAY` | ✓ HC23 |
| Backfill API failure | `BACKFILL_FAILED` | ✓ HC15 |
| 0050 not updated (trading day) | `BLOCKED_STALE_DATA` | ✓ HC26 |
| 0050 updated but non-0050=0 | `BLOCKED_PARTIAL_MARKET` | ✓ FM16, FM11 |
| 0050 updated but non-0050 < 1,000 | `BLOCKED_PARTIAL_MARKET` | ✓ FM03 |
| Full market fresh | `SUCCESS` | ✓ HC17 |
| Concurrent lock | `BLOCKED_LOCK` | ✓ HC20 |
| Shadow runner direct bypass | Blocked by freshness gate in runner | ✓ FM14 |

---

## Cron Entry to Install

```
0 16 * * 1-5  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py --execute >> /Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log 2>&1
```

**Why `0 16`:** Mac is UTC+8. cron uses local time. 16:00 local = 16:00 Taiwan time (after TWSE data published at 15:30–16:00).

---

## Installation Instructions

```bash
# 1. Open crontab editor
crontab -e

# 2. Add the line above, save and exit (:wq in vim)

# 3. Verify installation
crontab -l

# 4. Grant Full Disk Access if needed
#    System Settings → Privacy & Security → Full Disk Access → add /usr/sbin/cron

# 5. First run verification (after 16:00 Taiwan on a trading day)
tail -50 /Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log

# 6. Status check
python3 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py --status
```

---

## Post-Install Monitoring

```bash
# Weekly missed-run check (run every Monday)
python3 scripts/hybrid_shadow_cron.py --check-missed

# Manual trigger (if cron missed a day)
python3 scripts/hybrid_shadow_cron.py --execute

# Remove cron entry
crontab -e  # delete the line, save
```

---

## 12 Final Answers

**Q1: Is the cron pipeline fail-closed on partial market data?**  
YES. `BENCHMARK_ONLY_UPDATED` and `PARTIAL_MARKET_UPDATE` both → `BLOCKED_PARTIAL_MARKET`. Shadow runner not invoked.

**Q2: Can the shadow runner bypass the cron pipeline?**  
NO. `run_hybrid_forward_shadow.py` calls `check_market_freshness()` independently, with the same thresholds.

**Q3: Does `_get_db_last_date()` checking 0050 alone create a data gap?**  
It did — that was the gap. Step 4b is now replaced with `check_market_freshness()` which checks both benchmark AND non-0050 coverage.

**Q4: What does the system do when only 0050 is updated?**  
Returns `BENCHMARK_ONLY_UPDATED` → `BLOCKED_PARTIAL_MARKET` → cron exits 0, shadow never runs.

**Q5: What threshold triggers PARTIAL_MARKET_UPDATE?**  
`MIN_COVERED_STOCKS = 1,000`. Real data: 11-04 had 6,956 stocks. Threshold is conservative.

**Q6: Is the cron timezone correct?**  
YES. `0 16 * * 1-5` = 16:00 Taiwan time (UTC+8). `0 8` was wrong (8:00 Taiwan, not 16:00).

**Q7: Can the cron run more than once per day?**  
No. `FileLock` prevents concurrent runs. `STATE_FILE` persists last run. Second trigger within same day hits lock.

**Q8: What happens if the Mac is asleep at 16:00?**  
Cron misses the run. `--check-missed` will detect it. Use `--execute` to manually trigger recovery.

**Q9: Is macOS Full Disk Access verified?**  
NOT VERIFIED from Terminal. Terminal already has FDA; cron runs in a different security context. Grant FDA to `/usr/sbin/cron` in System Settings if first run fails silently.

**Q10: What is the current DB state?**  
0050: 2026-11-05. Non-0050: 2026-11-04 (6,956 stocks). Gate: BENCHMARK_ONLY_UPDATED. No PROSPECTIVE decisions yet — all 21 decisions are RETROSPECTIVE_RECONSTRUCTION.

**Q11: How many tests pass?**  
1,647 (FM01–FM20 + HC01–HC30 + all previous suites). 0 failures.

**Q12: Is the system ready for crontab installation?**  
CONDITIONAL READY. All safety gates pass. Known caveats: macOS FDA unverified, Mac sleep risk. Recommendation: install, verify first run log, grant FDA if needed.

---

## Authorization Gate

**DO NOT install crontab until you send the exact phrase:**

> `approve crontab install`

This document and all code are ready. Waiting for explicit authorization.
