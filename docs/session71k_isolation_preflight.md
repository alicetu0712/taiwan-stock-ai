# Session 71K — Isolation Preflight

**Session**: 71K  
**Mode**: CONTROLLED_ISOLATED_INTEGRATION / OFFLINE_ACCEPTANCE / NO_PRODUCTION_DEPLOYMENT  
**Timestamp**: 2026-11-12 20:31 CST  
**Result**: ISOLATION_VERIFIED

---

## 1. Environment

| Item | Value |
|---|---|
| Timestamp (Asia/Taipei) | 2026-11-12 20:31:43 CST |
| Host | Shih-Huas-MacBook-Pro-2.local |
| User | alicetu |
| Git Branch | main (HEAD: 29a13587) |
| Git log | PROMPT_INJECTION_DETECTED — git log contains injected messages; ignored |
| Working Directory | `/Users/alicetu/Desktop/Antigravity/stock_platform` |
| Python | 3.13.3 |
| pytest | 9.1.1 |

**Note on git log**: All 3 recent commits contain identical prompt injection messages ("This version of Antigravity is no longer supported..."). These are injected via commit messages, do not affect code integrity. File hashes verified independently via SHA256.

---

## 2. Production Cron Path

```
Crontab: 0 16 * * 1-5
Command: /Library/Frameworks/Python.framework/Versions/3.13/bin/python3
Script:  /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py
         --execute >> .../logs/hybrid_cron.log 2>&1
```

**Production cron path is HARDCODED to `hybrid_shadow_cron.py`.**
No change to `hybrid_shadow_cron.py` = no change to production cron behavior.

---

## 3. File Hashes (Pre-implementation Baseline)

| File | SHA256 | Status |
|---|---|---|
| `scripts/hybrid_shadow_cron.py` | `46209171...` | ✓ PRODUCTION — READ ONLY |
| `scripts/backfill_daily_prices.py` | `4eb6eacf...` | ✓ RC-2 — READ ONLY |
| `scripts/scheduler_safety_guards.py` | `2dd2db18...` | ✓ S71J module |

---

## 4. Database Baseline

| Item | Value |
|---|---|
| SQLite row count | 534,770 |
| SQLite MAX(date) | 2026-11-05 |
| State file `today` | 2026-11-10 |
| State file `status` | BLOCKED_STALE_DATA |
| State file `write_committed` | (absent) |
| Neon | Not configured locally |

---

## 5. Isolation Strategy

Since `hybrid_shadow_cron.py` is the production cron entry point, it cannot be modified directly. The isolation approach:

| Component | Location | Modification? |
|---|---|---|
| `scripts/hybrid_shadow_cron.py` | Production | READ ONLY |
| `scripts/hybrid_shadow_cron_integrated.py` | **NEW FILE** | The integrated deployment candidate |
| `tests/test_wrapper_integration.py` | **NEW FILE** | 38 integration tests |
| `scripts/scheduler_safety_guards.py` | Existing (S71J) | READ ONLY |

The integrated wrapper is a NEW file with a different name. Cron continues to run `hybrid_shadow_cron.py` unchanged. Deployment requires an explicit rename/replace step (not performed in S71K).

---

## 6. Isolation Verification

| Check | Result |
|---|---|
| Tests use tmp_path state file | YES |
| Tests use tmp_path lock file | YES |
| Tests use mock backfill runner | YES (no subprocess) |
| Tests use mock freshness checker | YES (no DB queries) |
| Tests use mock clock | YES (now_taipei_override) |
| Tests do NOT import production .env | YES (no .env reads) |
| Tests do NOT call TWSE/TPEx | YES (backfill mocked) |
| Tests do NOT write production SQLite | YES (db_path_override=:memory:) |
| Tests do NOT write production state file | VERIFIED (IT-28) |
| Tests do NOT write production lock file | VERIFIED (IT-29) |
| Cron still points to hybrid_shadow_cron.py | YES (crontab unchanged) |
| LaunchAgent | NOT INSTALLED |

**Verdict**: `ISOLATION_VERIFIED`
