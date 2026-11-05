# Hybrid Cron Installation Audit

**Date:** 2026-11-05  
**Status:** ✅ INSTALLED & VERIFIED (manual run confirmed BLOCKED_PARTIAL_MARKET, fail-closed)

---

## Pre-Installation Verification

| # | Check | Status | Detail |
|---|-------|--------|--------|
| 1 | Python executable exists | ✅ PASS | `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` |
| 2 | Cron script exists | ✅ PASS | `scripts/hybrid_shadow_cron.py` |
| 3 | Log dir exists and writable | ✅ PASS | `logs/` |
| 4 | SQLite DB isolated from Neon | ✅ PASS | `data/platform.db`, DATABASE_URL not set |
| 5 | No interactive shell required | ✅ PASS | `--execute` flag; no stdin |
| 6 | Timezone verified | ✅ PASS | System UTC+8 (Asia/Taipei); cron hour = 16 |
| 7 | No Neon write credentials in env | ✅ PASS | DATABASE_URL is empty |
| 8 | No existing crontab conflicts | ✅ PASS | Crontab was empty before install |
| 9 | Existing crontab backed up | ✅ DONE | Backed up to scratchpad (empty) |
| 10 | Safe disable/restore procedure | ✅ DOCUMENTED | `docs/hybrid_cron_rollback.md` |
| 11 | macOS Full Disk Access | ✅ USER CONFIRMED | User manually added /usr/sbin/cron to FDA |
| 12 | Full-Market Freshness Gate | ✅ ACTIVE | BLOCKED_PARTIAL_MARKET correctly detected |

---

## Installation Record

**Installed:** 2026-11-05 at ~18:09 Taiwan time (after today's 16:00 slot)  
**Installed by:** `echo "..." | crontab -`  
**Verified by:** `crontab -l`

```
0 16 * * 1-5  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py --execute >> /Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log 2>&1
```

Entry count: **1** (no duplicates)

---

## Timezone Critical Note

**macOS cron uses system timezone, NOT UTC.**

This Mac runs at **UTC+8 (Asia/Taipei)**. Therefore:

| Schedule | Fires at (local) | Fires at (UTC) | Correct? |
|----------|-----------------|----------------|----------|
| `0 8 * * 1-5` | 08:00 Taiwan time | 00:00 UTC | ❌ WRONG |
| `0 16 * * 1-5` | **16:00 Taiwan time** | **08:00 UTC** | ✅ CORRECT |

---

## Manual Run Result (2026-11-05 18:09 Taiwan)

Executed with `env -i` (simulates cron minimal environment):

```
Trading day: ✓ 2026-11-05
Backfill: TWSE api_date=2026-11-04 != target 2026-11-05 → quality gate BLOCKED (0 rows inserted)
Freshness: BENCHMARK_ONLY_UPDATED (0050=11-05, non-0050=0)
Status: BLOCKED_PARTIAL_MARKET
Exit code: 0 (expected/clean)
Shadow runner: NOT invoked ✓
```

This is the **correct fail-closed behavior** — TWSE full-market data not yet published at 18:09.

---

## First Scheduled Run

**Installed at:** 18:09 Taiwan (after today's 16:00 slot already passed)  
**Next scheduled trigger:** 2026-11-06 (Friday) 16:00 Taiwan time  
**Status:** `AWAITING_FIRST_SCHEDULED_RUN`

---

## Risk Summary

| Risk | Severity | Mitigation |
|------|----------|-----------|
| SINGLE_DEVICE_FAILURE_RISK | ⚠️ Medium | Add off-device backup (iCloud/external) |
| Mac sleep at 16:00 | ⚠️ Medium | Manual recovery via `--check-missed` |
| macOS Full Disk Access | ✅ Resolved | User manually enabled FDA for /usr/sbin/cron |
| USE_NEON=true in env | ℹ️ Info | Dashboard only; cron unaffected |
| Orphan WAL file | ℹ️ Info | Not harmful; `platform 2.db-wal` from July |

---

## Rollback Command

```bash
crontab -l | grep -v hybrid_shadow_cron | crontab -
crontab -l 2>&1 | grep hybrid_shadow_cron || echo "Removed ✓"
```
