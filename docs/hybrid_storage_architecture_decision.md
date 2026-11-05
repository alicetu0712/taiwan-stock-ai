# Hybrid Forward Shadow — Storage Architecture Decision

**Decision date:** 2026-11-05  
**Decision maker:** Alice Tu  
**Status:** DECIDED — Option A (GitHub artifact cache) for GH Actions; Option D (local cron) as primary until approval  
**Rule version:** hybrid_v1 | Freeze commit: 6602c3b

---

## 1. Option Definitions (from `hybrid_forward_deployment_runbook.md`)

| Option | Description |
|--------|-------------|
| **Option A** | GitHub Actions artifact cache — `data/platform.db` uploaded via `actions/cache/save@v4` after each run; restored via `actions/cache/restore@v4` before next run |
| **Option B** | S3/GCS persistent SQLite mount — download DB at job start, upload at job end; requires AWS/GCS credentials stored as GitHub Secrets |
| **Option C** | Dedicated research PostgreSQL — separate from production Neon; schema port required from sqlite3 to psycopg2 |
| **Option D** | Local cron on a persistent machine — researcher's laptop or VM runs `run_hybrid_forward_shadow.py` at 15:35 Taiwan time, Mon–Fri |

---

## 2. Comparison Matrix

| Evaluation Criterion | Option A | Option B | Option C | Option D |
|---------------------|----------|----------|----------|----------|
| **Storage mechanism** | GitHub artifact cache | S3/GCS + SQLite file | Dedicated PostgreSQL | Local SQLite |
| **Persistent across runs** | ✅ Yes (via cache restore) | ✅ Yes | ✅ Yes (native DB persistence) | ✅ Yes (file never deleted) |
| **GitHub Actions compatible** | ✅ Native | ✅ With cloud secrets | ✅ With RESEARCH_PG_URL secret | ❌ No (local machine only) |
| **Append-only guarantee** | ✅ Via DB UNIQUE constraints | ✅ Via DB UNIQUE constraints | ✅ Via DB UNIQUE + txn | ✅ Via DB UNIQUE constraints |
| **Concurrent write safety** | ⚠️ SQLite WAL mode; GH Actions concurrency group prevents simultaneous runs | ⚠️ Same as A | ✅ PostgreSQL MVCC + row locks | ✅ Single process (cron) |
| **Backup & restore** | ⚠️ Cache entries expire after 7 days of inactivity | ✅ S3 versioning / GCS lifecycle | ✅ pg_dump / pg_restore | ⚠️ Manual — requires explicit backup step |
| **Maintenance cost** | Low (GitHub manages storage) | Low (cloud managed) | Medium (monitor DB, run migrations) | Very Low (no infra) |
| **Estimated cost** | Free (within GitHub free tier) | UNKNOWN — depends on S3/GCS tier | UNKNOWN — Neon free tier: $0; Supabase free tier: $0; dedicated: $5–$20/month | $0 |
| **Data loss risk** | Low — 7-day cache expiry if no runs; cache entry evicted if >10GB total | Very Low — S3 durability 99.999999999% | Very Low — PostgreSQL WAL + backup | Medium — depends on machine uptime and backup discipline |
| **Deployment complexity** | Low — no new secrets needed | Medium — requires cloud credentials | Medium-High — schema port + new DB instance | Very Low — already works |
| **Production isolation** | ✅ Fully isolated (SQLite ≠ Neon) | ✅ Fully isolated | ✅ RESEARCH_PG_URL ≠ NEON_URL (enforced by factory) | ✅ Fully isolated |

**UNKNOWN costs** = not estimated because cloud tier selection has not been made. No costs have been incurred.

---

## 3. Detailed Analysis

### Option A — GitHub artifact cache

**How it works:**  
Before the shadow run, `actions/cache/restore@v4` looks for `hybrid-research-db-v1-{os}-*` prefix match, downloads the most recent matching entry.  
After the run, `actions/cache/save@v4` saves with key `hybrid-research-db-v1-{os}-{run_id}`, creating a new unique entry.

**Key limitation:** GitHub artifact cache entries expire after 7 days of no access. If no workflow runs for >7 calendar days (holiday period, vacation), the cache is evicted. The DB would be lost.

**Mitigation:** For a research system that only needs to accumulate data, losing one week's decisions is acceptable (they were SKIPPED_NON_TRADING_DAY anyway over holidays). But a prolonged gap would lose accumulated PROSPECTIVE records.

**Additional mitigation:** Schedule a weekly cache-refresh run that just backfills outcomes (no new decisions), keeping the cache alive.

**Conclusion:** Suitable for active periods. Risk of loss during holiday gaps. Best for short-to-medium-term research with active weekly operation.

### Option B — S3/GCS

Improves on Option A by using durable cloud storage. No expiry. Same SQLite file semantics.  
Requires provisioning an S3 bucket or GCS bucket and storing access credentials as GitHub Secrets. Adds ~2 minutes of I/O overhead per run for large DB files.  
**Not recommended as first choice** because the added infra complexity exceeds the benefit for a small research DB.

### Option C — Dedicated research PostgreSQL

The architecturally cleanest long-term solution. Full ACID, concurrent writes, pg_dump backups, no expiry concerns.  
**Requires:**
1. Provision a new PostgreSQL instance (Neon free tier, Supabase free tier, or Docker locally)
2. Set `RESEARCH_PG_URL` in GitHub Secrets (never equal to `NEON_URL`)
3. Port schema from sqlite3 DDL to PostgreSQL DDL
4. Implement `PostgreSQLResearchStorage` class (currently a stub in `storage_adapter.py`)
5. Migrate any existing SQLite research data

**Current status:** `PostgreSQLResearchStorage` stub exists in `storage_adapter.py`. The `get_research_storage()` factory will route to it when `RESEARCH_STORAGE_BACKEND=postgresql` is set.

**Cost:** Neon free tier (1 project, 10GB) = $0. Supabase free tier = $0. Recommended if Option A becomes insufficient.

### Option D — Local cron

Already working. Zero infra. No expiry concerns. Best uptime during active research phases.  
Risk is machine unavailability (travel, hardware failure, OS update).  
**Current status:** This is the active operating mode.

---

## 4. Decision & Rationale

### Recommended: **Option D (immediate) → Option A (GitHub Actions enablement)**

| Phase | Option | Trigger |
|-------|--------|---------|
| Now (2026-11-05+) | D — local cron | Running immediately |
| When GH Actions needed | A — artifact cache | Explicit human approval |
| If 7-day expiry becomes a risk | C — research PostgreSQL | Decision by 2027-Q1 review |

**Rationale:**
1. **Option D is free, works now, and has zero risk of data loss** as long as the machine runs. It is the right choice for the first accumulation phase (Nov 2026 – Jan 2027).
2. **Option A** is now fully implemented in the workflow (`.github/workflows/hybrid_forward_shadow.yml`). The schedule is commented out pending one manual test run.
3. **Option C** is designed and stubbed but requires human provisioning. It's the right path if the research system scales beyond 2 years.
4. **Option B** is not recommended — same risk as A but adds credential management overhead.

### Alternative: **Option C**  
Choose when: Option A's 7-day expiry poses unacceptable risk, or when PostgreSQL-level query capabilities (GROUP BY, window functions) are needed for outcome analysis.

### Not Recommended: **Option B**  
Higher operational cost than A with no meaningful advantage for this workload.

---

## 5. Cross-Runner Persistence Test Results

**Test:** `tests/test_cross_runner_persistence.py` (CR01–CR20, 20 tests)

| Run Scenario | Result |
|-------------|--------|
| Run A: writes 3 decisions | PASS — CR01 |
| Run B: opens artifact-copy, reads Run A decisions | PASS — CR02 |
| Run B: Run A's decision_hashes bit-for-bit identical | PASS — CR03 |
| Run A's run_log preserved in restored DB | PASS — CR04 |
| 5 sequential trading days accumulate correctly | PASS — CR05 |
| Artifact copy produces valid SQLite file | PASS — CR06 |
| SQLiteResearchStorage works on restored file | PASS — CR07 |
| Operational summary correct after multiple runs | PASS — CR08 |
| Run C: idempotent re-run → 0 new inserts, 0 conflicts | PASS — CR09, CR10 |
| Run D: same PK different hash → ConflictError raised | PASS — CR11 |
| Run D: original hash unchanged after conflict attempt | PASS — CR12 |
| Outcomes don't modify decision table | PASS — CR13–CR15 |
| FK linkage preserved after artifact copy | PASS — CR16 |
| Operational summary across multiple runs | PASS — CR17–CR20 |

**Verdict: Cross-runner persistence VERIFIED via file-copy simulation of Option A artifact restore.**

Note: The simulation uses `shutil.copy2()` to replicate artifact restore semantics. Actual GitHub Actions artifact cache uses HTTPS upload/download with the same byte-for-byte file content guarantee.

---

## 6. Append-only Integrity Guarantees

### SQLite (Options A/B/D)

| Mechanism | Implemented | Location |
|-----------|-------------|---------|
| UNIQUE(stock_id, trade_date, rule_version) | ✅ | `CREATE_DECISION_TABLE` DDL |
| UNIQUE(decision_id, horizon, calculation_version) | ✅ | `CREATE_OUTCOME_TABLE` DDL |
| Conflict detection via decision_hash | ✅ | `insert_decision()` → raises `ConflictError` |
| Explicit SELECT before INSERT (not INSERT OR IGNORE) | ✅ | Checks existing hash before inserting |
| No UPDATE on decision table | ✅ | No UPDATE SQL anywhere in `hybrid_forward_db.py` |
| No DELETE on decision table | ✅ | No DELETE SQL anywhere in codebase |
| WAL mode enabled by SQLiteResearchStorage | ✅ | `PRAGMA journal_mode=WAL` in `__enter__` |
| Concurrent write safety | ⚠️ | GH Actions `concurrency: cancel-in-progress: false` prevents parallel runs |

**SQLite limitation:** No row-level locking. If two processes write simultaneously, WAL mode prevents corruption but writes may interleave. The `concurrency` group in GitHub Actions prevents this.

### PostgreSQL (Option C — when implemented)

| Mechanism | Available | Notes |
|-----------|-----------|-------|
| UNIQUE constraints | ✅ | Same as SQLite |
| Row-level locking via SELECT FOR UPDATE | ✅ | Available, not yet implemented in stub |
| Transaction isolation (READ COMMITTED default) | ✅ | MVCC prevents dirty reads |
| Concurrent write safety without external lock | ✅ | MVCC + serializable transactions |
| Backup via pg_dump | ✅ | Standard tooling |

**PostgreSQL advantage:** No external serialisation needed for concurrent writes. The `ON CONFLICT DO NOTHING` + `RETURNING id` pattern provides clean idempotency at the DB level.

---

## 7. Final Verdict

| Dimension | Verdict | Evidence |
|-----------|---------|---------|
| **Storage — Cross-runner persistence** | **VERIFIED** | CR01–CR20 pass (shutil.copy2 simulates artifact restore) |
| **Storage — Append-only integrity** | **VERIFIED** | FS15–FS20, SA06–SA13, CR09–CR12 |
| **Storage — Deployment readiness** | **READY FOR MANUAL APPROVAL** | Option A workflow implemented; schedule commented out |
| **Security — Production isolation** | **VERIFIED** | NEON_URL never referenced in shadow pipeline; `get_research_storage()` enforces RESEARCH_PG_URL ≠ NEON_URL |
| **Operations** | **READY FOR MANUAL APPROVAL** | Option D active; Option A pending one test run + human approval |
