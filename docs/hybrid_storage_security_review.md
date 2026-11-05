# Hybrid Forward Shadow — Storage Security Review

**Review date:** 2026-11-05  
**Scope:** Research SQLite pipeline only — no production systems reviewed  
**Status:** CONDITIONAL PASS — see findings below

---

## 1. Data Boundary Classification

### Boundary 1: Production Trading Data (READ-ONLY by this pipeline — NEVER WRITTEN)

| Data type | Location | Pipeline access |
|-----------|----------|----------------|
| BUY / STRONG BUY recommendations | Neon PostgreSQL, `recommendations` table | None |
| Frozen ForwardSignals (v8.0) | Neon PostgreSQL, `forward_signals` table | None |
| ACTUAL trade executions | Neon PostgreSQL, `trade_executions` table | None |
| PAPER monitor positions | Neon PostgreSQL, `position_monitor` table | None |
| Decision Center entries | Neon PostgreSQL, `decision_journal` table | None |
| MODEL_VERSION v8.0 config | `config.py` constants | None |

**Verification:** The runner `run_hybrid_forward_shadow.py` opens only `sqlite3.connect(DB_PATH)`. No `get_session()` (SQLAlchemy/Neon) call is made anywhere in the shadow pipeline.

### Boundary 2: Research Input Data (READ-ONLY)

| Data type | Source | Access pattern |
|-----------|--------|----------------|
| DailyPrice (0050 and stocks) | SQLite `daily_prices` table | SELECT only |
| Trading calendar | SQLite `daily_prices` (0050 dates) | SELECT only |
| Market regime features | Computed from DailyPrice | In-memory |
| MA20 slope/trend/gap | Computed from DailyPrice | In-memory |

No writes are made to `daily_prices` or any other existing SQLite table.

### Boundary 3: Hybrid Research Storage (WRITE)

| Data type | Location | Access pattern |
|-----------|----------|----------------|
| `hybrid_forward_decision` | SQLite `data/platform.db` | INSERT (append-only) |
| `hybrid_forward_outcome` | SQLite `data/platform.db` | INSERT (append-only) |
| `hybrid_forward_run_log` | SQLite `data/platform.db` | INSERT + UPDATE (same run_id only) |

---

## 2. Credential Scope Analysis

### Production Neon PostgreSQL

| Check | Result |
|-------|--------|
| `NEON_URL` referenced in shadow runner | ❌ Not referenced |
| `NEON_URL` referenced in `hybrid_forward_db.py` | ❌ Not referenced |
| `NEON_URL` referenced in `storage_adapter.py` | ✅ Referenced only to BLOCK if RESEARCH_PG_URL equals it |
| `DATABASE_URL` used in shadow pipeline | ❌ Not used |
| SQLAlchemy `get_session()` called in shadow pipeline | ❌ Not called |

**Verdict:** Production Neon PostgreSQL is **completely isolated** from the shadow pipeline.

### GitHub Actions Secrets

| Secret | Used in hybrid shadow workflow | Purpose |
|--------|-------------------------------|---------|
| `NEON_URL` | ❌ Not used | Production only |
| `RESEARCH_PG_URL` | ❌ Not configured yet | Option C placeholder |
| `AWS_ACCESS_KEY_ID` | ❌ Not used | Option B placeholder |
| Any other secret | ❌ Not used | N/A |

The hybrid shadow workflow requires **zero new secrets** for Option A (artifact cache).

---

## 3. Environment Variables

### Production environment (Streamlit Cloud / GitHub Actions)

| Variable | Shadow pipeline reads it | Shadow pipeline writes it |
|----------|------------------------|--------------------------|
| `NEON_URL` | ❌ No | ❌ No |
| `DATABASE_URL` | ❌ No | ❌ No |
| `USE_NEON` | ❌ No | ❌ No |
| `ANTHROPIC_API_KEY` | ❌ No | ❌ No |
| `FINMIND_TOKEN` | ❌ No | ❌ No |

The shadow runner only uses: `DB_PATH` (a file path constant in the script itself, not an env var).

### Research-only variables (Option C future)

| Variable | Purpose | Safety check |
|----------|---------|-------------|
| `RESEARCH_STORAGE_BACKEND` | Switch between sqlite/postgresql | Defaults to `sqlite` |
| `RESEARCH_PG_URL` | Research PostgreSQL URL | `get_research_storage()` asserts it ≠ `NEON_URL` |

---

## 4. Security Findings

### FINDING S-01: No production database URL isolation check at runner startup

**Severity:** LOW  
**Description:** The runner `run_hybrid_forward_shadow.py` does not explicitly assert that `NEON_URL` is not used. It doesn't connect to Neon, but there is no startup assertion confirming this.  
**Current mitigation:** Code review confirms no `get_session()` or `NEON_URL` reference in the runner.  
**Recommendation:** The GitHub Actions workflow step "Confirm research-only environment" (step 2e) already checks and prints a warning if `NEON_URL` is set. This is sufficient for the current risk level.  
**Status:** ACCEPTED — low risk, warning in workflow

### FINDING S-02: SQLite file at `data/platform.db` is not encrypted at rest

**Severity:** LOW  
**Description:** `data/platform.db` stores research decisions and DailyPrice data. It is not encrypted.  
**Data sensitivity:** The file contains stock tickers, MA20 values, and research classifications. It does NOT contain production trade records, passwords, or financial account data.  
**Recommendation:** Acceptable for a local research file. If the file is uploaded to GitHub artifact cache, it will be stored within the GitHub account's encrypted artifact storage (AES-256 at rest per GitHub documentation).  
**Status:** ACCEPTED — data not sensitive enough to require file-level encryption

### FINDING S-03: Dashboard does not expose DB credentials

**Severity:** PASS  
**Description:** `_render_storage_health_panel()` in `entry_timing_research.py` uses `SQLiteResearchStorage.get_storage_info()` which returns only `db_name` (filename only, not full path), `file_exists`, `file_size_kb`, and `is_production=False`.  
**Verification:** The panel does not render `db_path`, does not render `NEON_URL`, does not render any password or token.  
**Status:** PASS

### FINDING S-04: PostgreSQL URL collision guard implemented

**Severity:** PASS  
**Description:** `get_research_storage()` in `storage_adapter.py` explicitly checks that `RESEARCH_PG_URL != NEON_URL` before instantiating `PostgreSQLResearchStorage`. This prevents accidental research writes to the production database.  
**Test coverage:** SA29 verifies this guard raises `ValueError` with message "SECURITY".  
**Status:** PASS

### FINDING S-05: No secrets in workflow YAML

**Severity:** PASS  
**Description:** The hybrid shadow workflow (`.github/workflows/hybrid_forward_shadow.yml`) references no secrets. The `confirm_persistence` input is a human-readable confirmation string, not a credential.  
**Status:** PASS

---

## 5. Production Isolation Checklist

| Check | Status | Evidence |
|-------|--------|---------|
| Shadow runner never calls `get_session()` | ✅ VERIFIED | Code review of `run_hybrid_forward_shadow.py` |
| Shadow runner never imports `DATABASE_URL` | ✅ VERIFIED | No import of `config.DATABASE_URL` in runner |
| `hybrid_forward_db.py` only imports `sqlite3` | ✅ VERIFIED | File header + imports section |
| `storage_adapter.py` blocks RESEARCH_PG_URL = NEON_URL | ✅ VERIFIED | SA29 test passes |
| Workflow step confirms no Neon writes | ✅ IMPLEMENTED | Step 2e in workflow |
| Dashboard H panel shows is_production=False | ✅ VERIFIED | `get_storage_info()` returns fixed value |
| Dashboard H panel doesn't expose DB path | ✅ VERIFIED | Only `db_name` (filename only) returned |
| No production schema changes by this pipeline | ✅ VERIFIED | Shadow pipeline creates only 3 new tables in SQLite |

---

## 6. Final Security Verdict

| Dimension | Verdict |
|-----------|---------|
| Production database isolation | **VERIFIED** |
| Credential exposure | **VERIFIED — no credentials in code, workflow, or logs** |
| Data boundary enforcement | **VERIFIED** |
| Dashboard sensitive data exposure | **VERIFIED — masked** |
| PostgreSQL collision guard | **VERIFIED — test SA29** |
| Overall security posture | **CONDITIONAL PASS** |

**Conditional on:** When Option C (PostgreSQL) is implemented, a full security review of `RESEARCH_PG_URL` credential handling, DB permissions (read/write only on research tables, no access to `forward_signals`, `recommendations`, etc.), and network access rules will be required.
