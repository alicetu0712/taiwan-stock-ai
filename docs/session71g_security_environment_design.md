# Session 71G — Security & Environment Design

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / MIGRATION_DESIGN_ONLY

---

## 1. Environment Inventory

### Python Interpreter
| Item | Value | Verified |
|---|---|---|
| Absolute path | `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` | YES (crontab) |
| Exists | YES (cron runs successfully) | Inferred |
| Version | 3.13 | From path |
| Owned by | System Python framework | — |

### Working Directory
| Item | Value | Verified |
|---|---|---|
| Cron working dir | Not explicitly set in crontab (inherits cron's `/`) | Inferred |
| Subprocess working dir | `str(SCRIPTS_DIR.parent)` = stock_platform root | YES (line 244 of hybrid_shadow_cron.py) |
| Plist design | `WorkingDirectory = /Users/alicetu/Desktop/Antigravity/stock_platform` | Designed |
| Consistency | CRON_INCONSISTENCY: cron has no explicit WorkingDirectory; script computes paths from `__file__` | PARTIAL |

**Note**: Both `hybrid_shadow_cron.py` and `backfill_daily_prices.py` compute their paths from `__file__` using `Path(__file__).parent.parent`. This means working directory is NOT critical for path resolution. However, `load_dotenv()` without arguments searches for `.env` starting from CWD — requiring CWD to be the project root or a parent.

### Environment Variable Sources

| Variable | Source | Used By | Required in Plist? |
|---|---|---|---|
| `HOME` | User session | `load_dotenv()` path resolution | YES |
| `PATH` | User session | Python import resolution | YES |
| `DATABASE_URL` | `.env` via dotenv | Dashboard code (NOT backfill) | NO |
| `NEON_URL` | `.env` via dotenv | Dashboard code (NOT backfill) | NO |
| `USE_NEON` | `.env` via dotenv | Dashboard code (NOT backfill) | NO |
| `ANTHROPIC_API_KEY` | `.env` via dotenv | AI features (NOT backfill) | NO |
| `FINMIND_TOKEN` | `.env` via dotenv | FinMind data (NOT backfill) | NO |
| `PYTHONUNBUFFERED` | Plist env | Flush stdout without buffering | RECOMMENDED |

**Key finding**: The backfill pipeline uses `config.DB_PATH` (always local SQLite), **not** `DATABASE_URL`. Even though `config.py` loads all `.env` variables including Neon credentials, the backfill never references them. No Neon credentials need to be in the plist.

---

## 2. Secret Handling Assessment

### What secrets exist in `.env`?
| Secret Type | Used by backfill? | Risk if exposed |
|---|---|---|
| `NEON_URL` (PostgreSQL DSN) | NO | High (production DB credentials) |
| `ANTHROPIC_API_KEY` | NO | Medium (API billing) |
| `FINMIND_TOKEN` | NO | Low (data API) |

### Plist secret handling rules:
1. **DO NOT** write any secret values into the plist file
2. **DO NOT** write `NEON_URL`, `ANTHROPIC_API_KEY`, or `FINMIND_TOKEN` into `EnvironmentVariables` dict
3. `load_dotenv()` in `config.py` handles secret loading at runtime from `.env`
4. The plist only needs `HOME`, `PATH`, and `PYTHONUNBUFFERED`

### Does the plist expose secrets?
| Check | Status |
|---|---|
| Neon URL in plist | NOT present in design ✓ |
| API keys in plist | NOT present in design ✓ |
| Secrets in log | NOT expected — backfill doesn't log credentials ✓ |
| `.env` contents in documents | NOT included in any session document ✓ |

---

## 3. File Permissions

| File | Current Permissions | Expected Owner | Risk |
|---|---|---|---|
| `data/platform.db` | (not checked this session) | alicetu | SQLite WAL race if wrong |
| `data/.cron.lock` | `-rwxr-xr-x` (confirmed S71F) | alicetu | World-readable PID — low risk |
| `data/.cron_state.json` | (not checked) | alicetu | Contains run metadata — low sensitivity |
| `logs/hybrid_cron.log` | `-rw-r--r--` (confirmed S71F) | alicetu | Contains execution history — low sensitivity |
| `scripts/hybrid_shadow_cron.py` | (not checked) | alicetu | Should be owned by alicetu |
| `scripts/backfill_daily_prices.py` | (not checked) | alicetu | Should be owned by alicetu |
| Plist (design) | Should be `600` or `644` | alicetu | Readable by user; not writable by others |

---

## 4. User Identity

| Context | User | Group |
|---|---|---|
| Cron execution | `alicetu` (user crontab) | staff |
| LaunchAgent execution | `alicetu` (user session) | staff |
| LaunchDaemon (rejected) | root unless overridden | wheel |
| File ownership (project) | alicetu | staff |

LaunchAgent maintains the same user identity as the existing cron entry. No privilege change.

---

## 5. Network Dependencies

| Dependency | Required for | Failure behavior |
|---|---|---|
| TWSE API (`openapi.twse.com.tw`) | backfill_daily_prices.py | 3 HTTP retries, then returns empty DataFrame; QG fails; date skipped |
| TPEx API (`tpex.org.tw`) | backfill_daily_prices.py | Same as TWSE |
| Neon PostgreSQL | Dashboard (USE_NEON=true) | NOT called by backfill pipeline |
| Local SQLite | All scripts | No network dependency |

**Network unavailability behavior**: If both TWSE and TPEx return empty (network down), `backfill_daily_prices.py` skips all dates with error messages. `hybrid_shadow_cron.py` exits with `backfill.exit_code=0` (no crash). Post-backfill freshness gate returns `PROVIDER_NOT_READY` → `BLOCKED_STALE_DATA`. Script exits 0 (clean failure, no alert).

---

## 6. Log Security

### Current log path
`logs/hybrid_cron.log` (file, 106 lines, last mod Nov 10 17:37)

### launchd log behavior: CRITICAL DIFFERENCE

| Scheduler | Log behavior |
|---|---|
| cron | `>> /path/log 2>&1` → **APPENDS** to existing log |
| launchd `StandardOutPath` | **TRUNCATES** log on each invocation (overwrites) |

**Risk**: If launchd is set up with `StandardOutPath` pointing to `hybrid_cron.log`, each run will **overwrite** the previous log, losing history.

**Mitigations** (design only, not authorized):

**Option 1: Wrapper script with append**
```bash
#!/bin/bash
# /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/cron_wrapper.sh
exec >> /Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log 2>&1
exec /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
  /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py --execute
```
Then plist uses `ProgramArguments` → `["/bin/bash", "/path/to/cron_wrapper.sh"]`.

**Option 2: Separate log files per run**
Use `StandardOutPath` → `logs/hybrid_cron_latest.log`, preserve history elsewhere.

**Option 3: Accept overwrite**
The `data/.cron_state.json` already captures each run's summary. Log overwrite acceptable if state file is the primary audit trail.

**Recommendation**: Option 3 (accept overwrite) for simplicity, with `data/.cron_state.json` as the authoritative run record. If log history is needed, use Option 1 (wrapper script with append).

---

## 7. Process Exit Codes

From `hybrid_shadow_cron.py:670–676`:

```python
clean_statuses = {
    "SUCCESS", "DRY_RUN_OK", "SKIPPED_NON_TRADING_DAY", "DATA_NOT_READY",
    "BLOCKED_STALE_DATA", "BLOCKED_LOCK", "BLOCKED_PARTIAL_MARKET",
}
exit_code = 0 if result["status"] in clean_statuses else 1
```

| Status | Exit Code | launchd behavior |
|---|---|---|
| SUCCESS | 0 | Clean exit |
| BLOCKED_STALE_DATA | 0 | Clean exit (expected failure) |
| BLOCKED_LOCK | 0 | Clean exit |
| SKIPPED_NON_TRADING_DAY | 0 | Clean exit |
| BACKFILL_FAILED | 1 | launchd may restart (ThrottleInterval applies) |
| SHADOW_FAILED | 1 | launchd may restart |

**launchd restart behavior**: If `KeepAlive` is not set (not in our plist design), launchd does NOT restart on exit. Exit code 1 is logged but no restart occurs.

---

## 8. SQLite Write Target Verification

The migration must not change the SQLite write target.

| Item | Current | After Migration | Change? |
|---|---|---|---|
| DB_PATH source | `config.py:20` → `data/platform.db` | Same (config.py unchanged) | NO |
| Neon write path | None in backfill | None in backfill | NO |
| `DATABASE_URL` used by backfill | NO | NO | NO |
| SQLite absolute path | `/Users/alicetu/Desktop/Antigravity/stock_platform/data/platform.db` | Same | NO |

---

## 9. Environment Design Summary (Plist)

```xml
<key>EnvironmentVariables</key>
<dict>
    <!-- Required: dotenv path resolution -->
    <key>HOME</key>
    <string>/Users/alicetu</string>

    <!-- Required: Python and system tools -->
    <key>PATH</key>
    <string>/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/local/bin:/usr/bin:/bin</string>

    <!-- Recommended: prevent stdout buffering in subprocess -->
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>

    <!-- DO NOT ADD: DATABASE_URL, NEON_URL, ANTHROPIC_API_KEY, FINMIND_TOKEN -->
    <!-- These are loaded by load_dotenv() from .env at runtime -->
</dict>
```

---

## 10. Verdict

| Item | Status |
|---|---|
| Python path design | `VERIFIED` |
| Working directory | `DESIGN_SAFE` (plist sets explicit WorkingDirectory) |
| Secret handling | `SECURE` — no secrets in plist; dotenv handles at runtime |
| User identity | `LEAST_PRIVILEGE_VERIFIED` (alicetu, not root) |
| SQLite isolation | `UNCHANGED_VERIFIED` |
| Log behavior | `LOG_OVERWRITE_RISK` — launchd truncates; design mitigation provided |
| Network failure safety | `FAIL_CLOSED_VERIFIED` |
| Exit code behavior | `VERIFIED` — exit 0 for expected failures |
