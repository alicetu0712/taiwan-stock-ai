# Hybrid Forward Shadow — Storage Deployment Readiness

**Review date:** 2026-11-05  
**Freeze commit:** 6602c3b  
**Test suite:** 1498 tests passing

---

## 1. Part A — Current State Audit Results

| Check | Result | Evidence |
|-------|--------|---------|
| HEAD SHA | 2d17227 | `git log --oneline -1` |
| Branch | main (ahead of origin by 9 commits) | `git branch -v` |
| Working tree | Clean (only `memory/` untracked — not project code) | `git status` |
| Latest GitHub CI | Unable to verify (no GH API access from local) | Manual check required |
| DailyPrice last date | 2026-10-28 | `SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'` |
| DailyPrice stock count | 14,288 distinct stocks | `SELECT COUNT(DISTINCT stock_id) FROM daily_prices` |
| SQLite usage | 7 scripts/modules use `sqlite3.connect('data/platform.db')` | `grep -rn platform.db` |
| PostgreSQL / Neon | Via `config.DATABASE_URL` → SQLAlchemy → `get_session()` (NOT used by shadow pipeline) | `config.py` |
| Hybrid research tables in SQLite | **Not yet created** (pending first shadow run) | `SELECT name FROM sqlite_master` |
| GitHub Actions workflows | 5 workflows; hybrid shadow = DEPLOYMENT READY (Option A configured) | `.github/workflows/` |
| Deployment runbook | `docs/hybrid_forward_deployment_runbook.md` | Present |

---

## 2. Part F — GitHub Actions Deployment Checklist

| Check | Workflow step | Status |
|-------|---------------|--------|
| Persistence confirmation gate | Job 1: `persistence-gate` | ✅ Implemented |
| Cache restore (Option A) | Step 2c: `actions/cache/restore@v4` | ✅ Implemented |
| Cache restore status reported | Step 2c: report step | ✅ Implemented |
| DB existence verified | Step 2d | ✅ Implemented |
| DailyPrice freshness check | Step 2d (via Python) | ✅ Implemented |
| Production Neon NOT used | Step 2e: Python check | ✅ Implemented |
| Shadow runner executed | Step 2f | ✅ Implemented |
| Research tests executed | Step 2g: 4 test files | ✅ Implemented |
| Operational summary printed | Step 2h | ✅ Implemented |
| Cache save (Option A) | Step 2i: `actions/cache/save@v4` | ✅ Implemented |
| Cache save confirmation logged | Step 2i: report step | ✅ Implemented |
| Concurrency group (no parallel runs) | `concurrency: group: hybrid-forward-shadow` | ✅ Implemented |
| Schedule commented out | `# schedule:` block | ✅ Commented out |
| `cancel-in-progress: false` | Prevents mid-run cancellation | ✅ Implemented |

**Missing for schedule enablement:**
1. Manual test run #1 with `confirm_persistence=YES` — seeds the cache
2. Manual test run #2 — verifies cache restore from run #1
3. Human approval to uncomment `schedule:` block

---

## 3. Part G — Storage Adapter Deployment Status

| Component | File | Status |
|-----------|------|--------|
| `ResearchStorageProtocol` | `src/research/storage_adapter.py` | ✅ Implemented |
| `SQLiteResearchStorage` | `src/research/storage_adapter.py` | ✅ Implemented + 30 tests |
| `PostgreSQLResearchStorage` stub | `src/research/storage_adapter.py` | ✅ Stub with full setup docs |
| `get_research_storage()` factory | `src/research/storage_adapter.py` | ✅ Implemented |
| WAL mode enabled | `SQLiteResearchStorage.__enter__` | ✅ `PRAGMA journal_mode=WAL` |
| `PRAGMA foreign_keys=ON` | `SQLiteResearchStorage.__enter__` | ✅ Enabled |
| `ensure_schema()` on open | `SQLiteResearchStorage.__enter__` | ✅ Idempotent |

---

## 4. Part I — Test Acceptance Matrix

### Storage Adapter Tests (`tests/test_storage_adapter.py` — 30 tests)

| Category | Tests | Status |
|----------|-------|--------|
| Context manager (open/close) | SA01–SA05 | ✅ PASS |
| insert_decision append-only | SA06–SA10 | ✅ PASS |
| insert_outcome | SA11–SA13 | ✅ PASS |
| upsert_run_log | SA14–SA15 | ✅ PASS |
| health_check / get_storage_info | SA16–SA20 | ✅ PASS |
| PostgreSQL stub safety | SA21–SA25 | ✅ PASS |
| get_research_storage factory | SA26–SA30 | ✅ PASS |

### Cross-runner Persistence Tests (`tests/test_cross_runner_persistence.py` — 20 tests)

| Category | Tests | Status |
|----------|-------|--------|
| Run A writes + direct read | CR01 | ✅ PASS |
| Run B reads via artifact copy | CR02–CR04 | ✅ PASS |
| Sequential 5-day accumulation | CR05 | ✅ PASS |
| Artifact copy produces valid SQLite | CR06 | ✅ PASS |
| Adapter works on restored DB | CR07 | ✅ PASS |
| Operational summary multi-run | CR08 | ✅ PASS |
| Run C: idempotent re-run | CR09–CR10 | ✅ PASS |
| Run D: conflict detection | CR11–CR12 | ✅ PASS |
| Outcome separation cross-run | CR13–CR16 | ✅ PASS |
| Summary accuracy | CR17–CR20 | ✅ PASS |

**Cross-runner persistence: VERIFIED** — 20/20 tests pass using `shutil.copy2()` to simulate GitHub artifact restore semantics.

### Full Regression

| Test Category | Count | Status |
|--------------|-------|--------|
| Hybrid forward shadow (FS01–FS55) | 56 | ✅ PASS |
| Hybrid entry strategy (HY01–HY44) | 46 | ✅ PASS |
| Storage adapter (SA01–SA30) | 30 | ✅ PASS |
| Cross-runner persistence (CR01–CR20) | 20 | ✅ PASS |
| All other platform tests | 1346 | ✅ PASS |
| **Total** | **1498** | **✅ ALL PASS** |

### Lint

```
ruff check src/research/storage_adapter.py \
           tests/test_storage_adapter.py \
           tests/test_cross_runner_persistence.py \
           dashboard/_pages/entry_timing_research.py
# → All checks passed!
```

---

## 5. Part F — Runner Persistence Proof

The following four scenarios have been tested and verified:

```
Run A → writes decisions to db_path_a
         ↓ shutil.copy2(db_path_a, db_path_b)  [simulates artifact upload+download]
Run B → opens db_path_b (new connection), reads Run A decisions: VERIFIED (CR02)
         ↓ same db_path_b
Run C → re-runs same signals: 0 inserted, 0 conflicts (idempotent): VERIFIED (CR09)
         ↓ same db_path_b
Run D → same PK, different decision_hash: ConflictError raised, original unchanged: VERIFIED (CR11-CR12)
```

---

## 6. What Still Requires Human Action

| Action | Why human | Blocking? |
|--------|-----------|-----------|
| Run one manual `workflow_dispatch` with `confirm_persistence=YES` | First run seeds the GH artifact cache | Blocks GH Actions schedule |
| Run a second manual dispatch | Verifies cache restore works | Blocks GH Actions schedule |
| Uncomment `schedule:` in `hybrid_forward_shadow.yml` | Schedule enablement requires explicit approval | Blocks GH Actions schedule |
| DailyPrice update (2026-10-28 → today) | Required for PROSPECTIVE records | Blocks first PROSPECTIVE decision |
| Decide if Option C (PostgreSQL) is needed | Requires provisioning + cost decision | Does not block current operation |

---

## 7. Final Deployment Verdict

| Dimension | Verdict |
|-----------|---------|
| **Storage — Persistence** | ✅ **VERIFIED** — CR01–CR20 pass |
| **Storage — Deployment** | ✅ **READY FOR MANUAL APPROVAL** — Option A implemented, schedule pending 2 test runs + approval |
| **Security — Isolation** | ✅ **VERIFIED** — Neon never touched, RESEARCH_PG_URL guard tested |
| **Operations — Local cron** | ✅ **READY** — Option D already running |
| **Operations — GH Actions** | ⏳ **PENDING APPROVAL** — 2 manual test runs needed |
| **Strategy evidence** | ⏸ **INSUFFICIENT DATA** — 0 PROSPECTIVE records yet (day 1 of freeze) |
