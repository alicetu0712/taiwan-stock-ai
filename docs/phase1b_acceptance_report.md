# Phase 1B Acceptance Report — ACTUAL Trade Lifecycle

**Generated:** 2026-11-04  
**Commit SHA:** 91e8d7b  
**Branch:** main  
**Verdict:** CONDITIONAL (PostgreSQL integration + Browser E2E NOT VERIFIED)

---

## A. Environment

| Item | Value |
|------|-------|
| Python | 3.13.3 |
| Streamlit | 1.58.0 |
| Playwright | 1.64.1 (Chrome for Testing 156.0.8078.4) |
| psycopg2 | 2.9.12 |
| PostgreSQL | **NOT AVAILABLE** (docker, psql, pg_isready not found) |
| Docker | **NOT AVAILABLE** |
| SQLite (local dev DB) | Available — used for E2E service tests |
| GitHub CLI | NOT installed — accessed via API token |
| Git Commit SHA | 91e8d7b |
| Repository | github.com/alicetu0712/taiwan-stock-ai |

---

## B. PostgreSQL Integration (P0)

Docker and local PostgreSQL not available.  
All 29 scenarios: **NOT VERIFIED**.

**Reproducible Docker commands to close this gap:**

```bash
# 1. Start isolated PostgreSQL
docker run -d --name pg-phase1b \
  -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=taiwan_stock_test \
  -p 5433:5432 postgres:16-alpine

# 2. Wait for readiness
docker exec pg-phase1b pg_isready -U postgres

# 3. Run Migration dry-run
TEST_DATABASE_URL=postgresql://postgres:testpass@localhost:5433/taiwan_stock_test \
  python scripts/migrate_trade_lifecycle.py --dry-run --env local

# 4. Run actual migration
TEST_DATABASE_URL=postgresql://postgres:testpass@localhost:5433/taiwan_stock_test \
  python scripts/migrate_trade_lifecycle.py --env local

# 5. Run Phase 1B tests against PostgreSQL
TEST_DATABASE_URL=postgresql://postgres:testpass@localhost:5433/taiwan_stock_test \
  pytest tests/test_migration_safety.py tests/test_ddl_guard.py \
         tests/test_trade_lifecycle.py tests/test_trade_idempotency.py -v

# 6. Cleanup
docker stop pg-phase1b && docker rm pg-phase1b
```

| # | Scenario | Status |
|---|----------|--------|
| 1 | Fresh Migration | NOT VERIFIED |
| 2 | Legacy Schema Upgrade | NOT VERIFIED |
| 3 | Repeated Migration | NOT VERIFIED |
| 4 | Schema Drift Blocking | NOT VERIFIED |
| 5 | Global Preflight APPLIED/PENDING/BLOCKED | NOT VERIFIED |
| 6 | FK Schema/Columns/Referential Actions | NOT VERIFIED |
| 7 | Unique Index Predicate/Valid/Ready | NOT VERIFIED |
| 8 | Partial Index Expression/INCLUDE | NOT VERIFIED |
| 9 | Dry-run No DDL | NOT VERIFIED |
| 10 | Transaction Rollback | NOT VERIFIED |
| 11 | DDL Audit Accuracy | NOT VERIFIED |
| 12 | Post-migration Data Integrity | NOT VERIFIED |
| 13 | Existing Trade Records Preserved | NOT VERIFIED |
| 14 | Daily Pipeline No Auto-DDL | NOT VERIFIED (YAML: PASS) |
| 15 | ACTUAL Position Lifecycle | NOT VERIFIED (service: PASS) |
| 16 | Weighted Average Cost | NOT VERIFIED (service: PASS) |
| 17 | Fees/Taxes/Realized P&L | NOT VERIFIED (service: PASS) |
| 18 | Concurrent Idempotency | NOT VERIFIED |
| 19 | Failed Transaction Atomicity | NOT VERIFIED (service: PASS) |
| 20 | PAPER/ACTUAL Isolation | NOT VERIFIED (service: PASS) |
| 21 | Frozen ForwardSignals | NOT VERIFIED (service: PASS) |
| 22-29 | Concurrency / Partial Write | NOT VERIFIED |

---

## C. Full Regression

### pytest

```
1192 passed, 901 warnings in 25.77s
0 failed, 0 skipped
```

**Phase 1B core tests (migration + ddl + trade + idempotency):**

| Test File | Count | Result |
|-----------|-------|--------|
| test_migration_safety.py | 118 | ✅ PASS |
| test_ddl_guard.py | 31 | ✅ PASS |
| test_trade_lifecycle.py | 54 | ✅ PASS |
| test_trade_idempotency.py | 44 | ✅ PASS |
| **Phase 1B total** | **247** | **✅ PASS** |

### Coverage (CI-scoped: src/analyzers + dashboard/loaders)

```
src/analyzers/entry_timing.py      97%
src/analyzers/fundamental.py       77%
src/analyzers/technical.py         81%
TOTAL                              82.71%  ✅ ≥ 75% required
```

### Lint / Compile

| Tool | Result |
|------|--------|
| ruff | ✅ All checks passed |
| black | ✅ 132 files unchanged |
| isort | ✅ OK |
| flake8 | ✅ 0 errors |
| compileall | ✅ OK (src/ dashboard/ scripts/ tests/) |

---

## D. GitHub CI

| Item | Value |
|------|-------|
| Commit SHA | 91e8d7b |
| Workflow Run | https://github.com/alicetu0712/taiwan-stock-ai/actions/runs/41776383669 |
| CI Name | CI |
| Overall Result | ✅ **success** |
| Lint job | ✅ success (isort, ruff, black, flake8) |
| Test (Python 3.11) | ✅ success |
| Test (Python 3.13) | ✅ success |
| Migration tests in CI | ✅ included (all 1192 tests run) |

### Production Migration Safety Controls

| Control | YAML Layer | Settings Layer |
|---------|-----------|----------------|
| workflow_dispatch only (manual trigger) | ✅ | — |
| `environment: production` gate | ✅ | ✅ **VERIFIED via API** |
| Required Reviewer: alicetu0712 | ✅ | ✅ **VERIFIED via API** (env id=26212785653) |
| Confirm token "MIGRATE_PRODUCTION" required | ✅ | — |
| Concurrency lock cancel-in-progress=false | ✅ | — |
| Pre-flight dry-run before production step | ✅ | — |
| Post-migration table verification | ✅ | — |
| General CI has no NEON_URL | ✅ (not in test.yml) | — |
| Daily pipeline has no DDL | ✅ (main.py init_db only under --init-db flag) | — |

**Note:** `prevent_self_review=false` — the owner (alicetu0712) can approve their own
production migration. Acceptable for a solo developer; review flow still requires
explicit UI approval before the job proceeds.

---

## E. E2E Trade Lifecycle (Service-Level, Isolated SQLite)

**Database used:** `sqlite:////Users/alicetu/Desktop/Antigravity/stock_platform/data/platform.db`  
(Local dev SQLite — isolated from Production Neon)

**All 21 service-level criteria PASSED:**

| # | Test | Result |
|---|------|--------|
| 1 | Dashboard startup no auto-DDL | ✅ PASS |
| 2 | ACTUAL position created | ✅ PASS |
| 3 | BUY execution recorded | ✅ PASS |
| 4 | Idempotency: same key/same payload → no duplicate | ✅ PASS |
| 5 | Idempotency: same key/different payload → CONFLICT error | ✅ PASS |
| 6 | 加碼 (second BUY) execution recorded | ✅ PASS |
| 7 | Weighted average cost (fee-inclusive) = 101.8113 | ✅ PASS |
| 8 | Partial sell: remaining=1000, status=partially_closed | ✅ PASS |
| 9 | Partial realized P&L after fees: 3880.33 | ✅ PASS |
| 10 | Full sell: remaining=0, status=closed | ✅ PASS |
| 11 | Full realized P&L positive: 16627.00 | ✅ PASS |
| 12 | Closed position rejects new BUY | ✅ PASS |
| 13 | ACTUAL position_type=ACTUAL | ✅ PASS |
| 14 | PAPER/ACTUAL schema separation (ActualPosition ≠ PositionMonitor) | ✅ PASS |
| 15 | ForwardSignal count unchanged (2605 → 2605) | ✅ PASS |
| 16 | Transaction history: 4 executions (BUY×2, SELL×2) | ✅ PASS |
| 17 | Oversell rejected: TradeSvcError | ✅ PASS |
| 18 | Zero shares rejected: TradeSvcError | ✅ PASS |
| 19 | Failed transaction atomicity: no partial SELL row | ✅ PASS |
| 20 | Original plan snapshot immutable after update_plan() | ✅ PASS |
| 21 | Plan change audit trail: PositionPlanChange recorded | ✅ PASS |
| — | Browser Playwright E2E (UI layer) | ⚠️ NOT VERIFIED |

**Browser Playwright E2E:** Playwright 1.64.1 is installed with Chrome for Testing.
However, Streamlit requires an isolated PostgreSQL to run separately from Production Neon,
and no Docker/local PostgreSQL is available. Browser E2E requires human action (see Section H).

---

## F. Blocking Issues Found & Resolved This Session

### FIXED-01: `production` GitHub Environment missing (CRITICAL)

| Field | Detail |
|-------|--------|
| Discovery | API query: `GET /repos/alicetu0712/taiwan-stock-ai/environments` returned 0 environments |
| Impact | `migrate.yml` had `environment: production` in YAML but no actual GitHub Environment existed → production migration would run WITHOUT human approval |
| Resolution | Created via `PUT /repos/.../environments/production` with `required_reviewers: [alicetu0712]` |
| Verification | API confirmed: env id=26212785653, protection_rules=[required_reviewers] |
| Remaining risk | `prevent_self_review=false` — owner can approve own deployment (acceptable for solo dev) |

### FIXED-02: `create_all()` in dashboard pages (security)

| Field | Detail |
|-------|--------|
| Files | `dashboard/_pages/entry_timing_research.py:51`, `dashboard/_pages/scorecard.py:243` |
| Impact | V2 research tables would auto-create in Production Neon on page load |
| Fix | Removed both `ResearchBase.metadata.create_all(engine, checkfirst=True)` calls |
| Commit | 91e8d7b |

### FIXED-03: Black format violation

| Field | Detail |
|-------|--------|
| File | `tests/test_migration_safety.py:2069` |
| Fix | Reformatted 3-line call to single line |
| Commit | 91e8d7b |

---

## G. Acceptance Gates Summary

| Gate | Status | Evidence | Blocker |
|------|--------|----------|---------|
| PostgreSQL Migration | NOT VERIFIED | Docker unavailable | ✳ Needs Docker (runbook provided) |
| PostgreSQL Concurrency | NOT VERIFIED | Docker unavailable | ✳ Needs Docker |
| Full pytest | **PASS** | 1192/1192 passed, 26s | — |
| Coverage | **PASS** | 82.71% ≥ 75% (CI scope) | — |
| Lint / Compile | **PASS** | ruff/black/isort/flake8/compile all clean | — |
| GitHub CI | **PASS** | Run 41776383669: success (3/3 jobs) | — |
| Production Approval | **PASS** | Env `production` created, required_reviewer=alicetu0712 | ✳ Set prevent_self_review=true for stronger isolation |
| E2E Trade Service | **PASS** | 21/21 service tests PASS (isolated SQLite) | — |
| Browser E2E | NOT VERIFIED | Playwright available but no isolated PG for Streamlit | ✳ Needs Docker or manual test |
| Data Integrity | **PASS** | ForwardSignal immutable; phase-1B tables verified | — |

---

## H. Required Human Actions (to close remaining gaps)

### H-1: PostgreSQL Integration (BLOCKER for full PASS)

**Time required:** ~30 min  
**Prerequisite:** Machine with Docker installed

```bash
# Step 1: Start isolated PostgreSQL
docker run -d --name pg-phase1b \
  -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=taiwan_stock_test \
  -p 5433:5432 postgres:16-alpine

# Step 2: Set test database URL
export TEST_DATABASE_URL=postgresql://postgres:testpass@localhost:5433/taiwan_stock_test

# Step 3: Run migration
python scripts/migrate_trade_lifecycle.py --env local

# Step 4: Run all Phase 1B tests
pytest tests/test_migration_safety.py tests/test_ddl_guard.py \
       tests/test_trade_lifecycle.py tests/test_trade_idempotency.py -v

# Expected: all 247 tests pass against real PostgreSQL
# Step 5: Cleanup
docker stop pg-phase1b && docker rm pg-phase1b
```

### H-2: Browser E2E (RECOMMENDED before production)

**Time required:** ~20 min  
**Prerequisite:** Docker running PostgreSQL (from H-1)

```bash
# 1. Set .env to use isolated PostgreSQL test DB
# In .env:
#   USE_NEON=false
#   DATABASE_URL=postgresql://postgres:testpass@localhost:5433/taiwan_stock_test

# 2. Initialize DB
python scripts/init_db.py

# 3. Start Streamlit
streamlit run dashboard/app.py --server.port 8501

# 4. Manual checklist (open http://localhost:8501):
# □ App loads without CREATE TABLE in logs
# □ Click "💼持倉" tab → manual form visible
# □ Create position: stock=2330, name=台積電, price=800, shares=1000
# □ Submit → success message shown
# □ Resubmit same form → no duplicate (Streamlit idempotency key rotation)
# □ Click "加碼" → add 500@820 → avg cost updated
# □ Partial sell 500@850 → remaining=1000, realized P&L shown
# □ Full sell 1000@900 → status=closed
# □ Check PAPER position tab → no cross-contamination
# □ Verify ForwardSignal page unchanged
```

### H-3: Strengthen Production Approval (OPTIONAL)

To prevent self-approval of production migrations:

```bash
curl -X PUT \
  -H "Authorization: token <YOUR_TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/alicetu0712/taiwan-stock-ai/environments/production" \
  -d '{
    "reviewers": [{"type": "User", "id": 298095850}],
    "prevent_self_review": true
  }'
```
Note: With `prevent_self_review=true`, a second GitHub account is required to approve.
For a solo project, `prevent_self_review=false` is acceptable.

---

## I. Executive Summary

**Phase 1B ACTUAL Trade Lifecycle is functionally complete and locally verified.**

What was verified this session:
- ✅ 1192 pytest tests pass (CI: Python 3.11 + 3.13 both green)
- ✅ All lint tools clean
- ✅ Coverage 82.71% ≥ 75%
- ✅ GitHub CI `91e8d7b` fully succeeded
- ✅ Production environment protection CREATED and verified (was missing; fixed)
- ✅ Dashboard auto-DDL vulnerability patched (2 locations; commit 91e8d7b)
- ✅ 21/21 trade lifecycle service tests PASS (BUY → 加碼 → partial sell → full sell)
- ✅ Idempotency, atomicity, ForwardSignal immutability all verified

What remains NOT VERIFIED:
- ⚠️ True PostgreSQL behavior (Docker unavailable) — 29 integration scenarios
- ⚠️ Browser-level Playwright E2E (requires Docker + isolated PG for Streamlit)

---

## J. Final Decision

## CONDITIONAL

**READY after completing H-1 (PostgreSQL integration) and H-2 (Browser E2E).**

Do not execute Production Neon Migration until:
1. PostgreSQL integration tests (H-1) pass on real PostgreSQL
2. Browser E2E (H-2) checklist completed
3. GitHub production environment approval obtained (now configured — waiting for use)
