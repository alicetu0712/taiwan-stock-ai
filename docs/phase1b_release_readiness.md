# Phase 1B Release Readiness — Release Freeze Verification

**Document date:** 2026-11-04 (updated 2026-11-04 — UI P&L fix applied)  
**Status:** DEPLOYMENT PREPARED (pending human approval of Production Migration)  
**Author:** Senior Release Engineer / QA Lead

---

## A. Release Candidate

| Field | Value |
|-------|-------|
| Release Candidate SHA | **d27e1b2** (HEAD, main) |
| Previous freeze SHA | **9b8203d** (docs-only) |
| Last accepted code SHA before P&L fix | **91e8d7b** |
| This commit | **d27e1b2** — `fix(ui): replace gross P&L toast with net realized_pnl from Trade Service` |
| Branch | main |
| Working tree | Clean (nothing uncommitted) |
| HEAD vs origin/main | In sync — `up to date with origin/main` |

### Commit history since original acceptance

| SHA | Type | Description |
|-----|------|-------------|
| d27e1b2 | **fix(ui)** | Replace gross P&L toast — `dashboard/_pages/position.py` + `tests/test_position_pnl_display.py` |
| 05119b5 | docs | Release readiness + migration runbook |
| 9b8203d | docs | Phase 1B acceptance report (E2E gate) |
| f75dc8c | docs | Phase 1B acceptance report (PG integration gate) |
| **91e8d7b** | **fix(security)** | Last code change before UI fix |

### Code-freeze scope

**Non-frozen files (changed in d27e1b2):**
- `dashboard/_pages/position.py` — UI toast display only (2 form handlers)
- `tests/test_position_pnl_display.py` — New test file (15 tests)

**Verified frozen (no changes):**
- `src/services/trade_service.py` — Accounting rules unchanged ✅
- `src/database.py` — Models unchanged ✅
- `scripts/migrate_trade_lifecycle.py` — Migration unchanged ✅
- `src/analyzers/` — Strategy logic unchanged ✅
- All ForwardSignal / PAPER position code — Unchanged ✅
- Entry Timing V2, v8.0 breakout, foe_v1 — Unchanged ✅

**Conclusion: d27e1b2 adds UI display fix only. No accounting rule, migration, or model changed.**

---

## B. Acceptance Evidence Traceability

### B.1 Regression Tests (HEAD = d27e1b2)

Re-executed against current HEAD (after UI fix):

```
1207 passed, 901 warnings in 28.27s
```

| Metric | Requirement | Actual |
|--------|-------------|--------|
| Pass count | 1192 (original) → **1207** (+ 15 new) | **1207 ✅** |
| Fail count | 0 | **0 ✅** |
| Coverage (CI scope) | ≥ 75% | **83.00% ✅** |

Coverage re-measured on HEAD:

```
src/analyzers/entry_timing.py      97%
src/analyzers/fundamental.py       77%
src/analyzers/technical.py         81%
TOTAL                              83.00%  ✅
```

Note: 83.00% vs previously reported 82.71% — minor variation from test execution environment differences. Both exceed the 75% gate.

### B.2 Lint (CI-scoped: `src/ dashboard/ tests/ config.py`)

| Tool | Scope | Result |
|------|-------|--------|
| ruff | src/ dashboard/ tests/ config.py | ✅ PASS (CI confirmed run 41776383669) |
| black | src/ dashboard/ tests/ config.py | ✅ PASS |
| isort | src/ dashboard/ tests/ config.py | ✅ PASS |
| flake8 | src/ dashboard/ tests/ config.py | ✅ PASS |

**Known pre-existing lint issues outside CI scope (`scripts/` directory):**

18 ruff errors + 10 black reformats in `scripts/backfill_*.py`, `scripts/init_db.py`, `scripts/run_*.py`, etc. These files:
- Are not in the CI lint scope
- Were not modified during Phase 1B development
- Are operational/backfill scripts, not Phase 1B trade lifecycle code
- Do not affect Phase 1B correctness

Impact assessment: **None for Phase 1B release.** These are pre-existing technical debt unrelated to ACTUAL Trade Lifecycle.

### B.3 GitHub CI

| Item | Value |
|------|-------|
| CI run URL (last verified) | https://github.com/alicetu0712/taiwan-stock-ai/actions/runs/41776383669 |
| Commit verified | 91e8d7b (pre-UI-fix) |
| Result at 91e8d7b | ✅ success (lint + test Python 3.11 + test Python 3.13) |
| d27e1b2 CI | Pushed to origin/main; CI triggered automatically on push |
| d27e1b2 CI verification | **Pending human check** — visit Actions tab to confirm pass |

> CI lint scope covers `dashboard/_pages/position.py` and `tests/test_position_pnl_display.py`.
> Local verification: `ruff check dashboard/ tests/test_position_pnl_display.py` passes (no new errors).

### B.4 PostgreSQL Integration Evidence

| Item | Value |
|------|-------|
| Method | embedded-postgres 18.6.3 (Python package, real PostgreSQL binary) |
| PG Version | PostgreSQL 18.6 on aarch64-apple-darwin25.6.0 |
| Test DB | `taiwan_stock_test` (Unix socket, NOT Production Neon, SSL=None) |
| Scenarios | 29 / 32 assertion checks PASS |
| Commit tested | 91e8d7b (trade lifecycle code unchanged in d27e1b2) |
| Test script | scratchpad: `pg_integration_test.py` |

Scenarios covered: Fresh migration, repeated migration (idempotent), schema drift detection, FK×2, partial unique index (`uix_te_idempotency_key`), dry-run, DDL rollback, DDL audit (committed=1 rolled_back=0), schema validation (9 checkpoints), FK enforcement, pipeline no-DDL, full ACTUAL trade lifecycle, idempotency conflict, oversell atomicity, 2-connection concurrent race.

> Trade lifecycle code (trade_service, database, migration) is unchanged in d27e1b2 — PG integration results carry over.

### B.5 Browser E2E Evidence

| Item | Value |
|------|-------|
| Method | Playwright 1.64.1 + Chromium headless → Streamlit 1.58 on port 8763 |
| Database | embedded-postgres 18.6, `taiwan_stock_e2e` (NOT Production Neon) |
| Flow | BUY → 加碼 → 部分賣出 → 全部賣出 → 歷史紀錄 |
| Result | **18/18 PASS** |
| Screenshots | 17 Playwright screenshots captured |
| Commit tested | 91e8d7b (UI toast assertions check DB state, not toast text — d27e1b2 toast change is compatible) |

> E2E assertions verify DB state (realized_pnl values, status=closed) not toast text. The toast label change
> in d27e1b2 (gross→net, label change) does not affect E2E assertion criteria.

---

## C. Trade P&L Final Reconciliation

Independent calculation — does NOT call `trade_service._recalculate_position()`.  
Implements the same algorithm (`_recalculate_position` docstring: cost_basis + WAC + realized).

### C.1 Input Scenario

| Step | Side | Shares | Price | Fee | Tax |
|------|------|--------|-------|-----|-----|
| 1 | BUY | 1,000 | 100.00 | 142 | 0 |
| 2 | BUY (加碼) | 500 | 105.00 | 75 | 0 |
| 3 | SELL (部分賣出) | 500 | 110.00 | 214 | 0 |
| 4 | SELL (全部賣出) | 1,000 | 115.00 | 442 | 0 |

### C.2 Step-by-step Calculation

```
After BUY 1 (1000@100, fee=142):
  cost_basis = 1000×100 + 142 = 100,142
  remaining  = 1,000
  avg_cost   = 100,142 / 1,000 = 100.1420

After BUY 2 (500@105, fee=75):
  cost_basis = 100,142 + 500×105 + 75 = 100,142 + 52,575 = 152,717
  remaining  = 1,500
  avg_cost   = 152,717 / 1,500 = 101.81133...  → stored: 101.8113

After SELL (500@110, fee+tax=214):
  cost_of_sold  = 101.81133... × 500     = 50,905.6667
  proceeds      = 500×110                = 55,000
  net_proceeds  = 55,000 - 214           = 54,786
  realized_this = 54,786 - 50,905.6667  = 3,880.3333  → stored: 3,880.33
  cost_basis    = 152,717 - 50,905.6667 = 101,811.3333
  remaining     = 1,000
  avg_cost      = 101,811.3333 / 1,000  = 101.81133...

After SELL (1000@115, fee+tax=442):
  cost_of_sold  = 101.81133... × 1,000  = 101,811.3333
  proceeds      = 1,000×115             = 115,000
  net_proceeds  = 115,000 - 442         = 114,558
  realized_this = 114,558 - 101,811.3333 = 12,746.6667
  realized_cum  = 3,880.3333 + 12,746.6667 = 16,627.0000  → stored: 16,627.00
  remaining     = 0
  status        = closed
```

### C.3 Reconciliation Results

| Metric | Expected | System Reports | Match |
|--------|----------|----------------|-------|
| WAC after both BUYs | 101.8113 | 101.8113 | ✅ |
| realized_pnl after partial sell | 3,880.33 | 3,880.33 | ✅ |
| realized_pnl after full sell (CUMULATIVE) | 16,627.00 | 16,627.00 | ✅ |
| remaining after partial sell | 1,000 | 1,000 | ✅ |
| remaining after full sell | 0 | 0 | ✅ |
| status after full sell | closed | closed | ✅ |

**All P&L figures verified correct. No RELEASE BLOCKER.**

### C.4 Single-trade vs Cumulative P&L — UI Fix Applied (d27e1b2)

| View | Value | Where shown | Before fix | After fix (d27e1b2) |
|------|-------|-------------|-----------|---------------------|
| Partial sell incremental net | 3,880.33 | 部分賣出 toast | ❌ Not shown | ✅ "本次已實現淨損益 +3,880" |
| Full sell this-trade net | 12,746.67 | — | ❌ n/a | ✅ Included in cumulative |
| **Cumulative net P&L** | **16,627.00** | 全部賣出 toast | ❌ 13,189 (gross, no fee) | ✅ "累計已實現淨損益 +16,627" |
| DB `actual_positions.realized_pnl` | 16,627.00 | Position summary metric | ✅ Already correct | ✅ Unchanged |

**UI display issue — FIXED in d27e1b2:**

| Handler | Before | After |
|---------|--------|-------|
| `_render_full_sell_form()` | `(exec_price - avg_cost) × remaining` = 13,188.70 (gross, no fee) | `pos.realized_pnl` from DB post-commit = **16,627.00** (cumulative net) |
| `_render_partial_sell_form()` | ❌ No P&L shown | `pos.realized_pnl - prev_realized` from DB = **3,880.33** (incremental net) |

Both handlers now read `realized_pnl` from the ORM object after `s.commit()`, using Trade Service's `_recalculate_position()` result. No separate UI formula.

### C.5 Rounding Rules

```python
_P4 = Decimal('0.0001')   # avg_cost_per_share: 4 decimal places
_P2 = Decimal('0.01')     # realized_pnl, total_cost_basis: 2 decimal places
ROUND_HALF_UP in both cases
```

All calculations use Python `Decimal` throughout — no floating-point rounding errors.

---

## D. Migration Version Inventory

**Script:** `scripts/migrate_trade_lifecycle.py`  
**SHA-256:** `da95d80bc2093839a5ebfd024294e30b0aa1147201785d2c6b0ce6ccabb77ba5`

### D.1 Table Creation (via `Base.metadata.create_all()`)

| Table | Columns | Key Constraints |
|-------|---------|-----------------|
| `actual_positions` | 19 | PK(id), FK(forward_signal_id→forward_signals), INDEX(stock_id) |
| `trade_executions` | 17 | PK(id), FK(position_id→actual_positions), FK(linked_forward_signal_id), UNIQUE INDEX(idempotency_key) WHERE NOT NULL |
| `position_plan_changes` | 8 | PK(id), FK(position_id→actual_positions), INDEX(position_id) |

### D.2 Approved Migrations (`_APPROVED_MIGRATIONS`)

| Name | Table | Type | PG Only | Idempotent |
|------|-------|------|---------|-----------|
| v1.1_add_idempotency_key | trade_executions | ALTER TABLE ADD COLUMN IF NOT EXISTS | No | ✅ IF NOT EXISTS |
| v1.2_add_idempotency_key_unique_index | trade_executions | CREATE UNIQUE INDEX IF NOT EXISTS (partial WHERE NOT NULL) | No | ✅ IF NOT EXISTS |
| v1.3_add_fk_actual_positions_fwd_signals | actual_positions | ALTER TABLE ADD CONSTRAINT | Yes | Via verify() check |
| v1.4_add_fk_trade_executions_positions | trade_executions | ALTER TABLE ADD CONSTRAINT | Yes | Via verify() check |
| v1.5_add_fk_position_plan_changes_positions | position_plan_changes | ALTER TABLE ADD CONSTRAINT | Yes | Via verify() check |
| v1.6_add_fk_trade_executions_linked_signal | trade_executions | ALTER TABLE ADD CONSTRAINT | Yes | Via verify() check |

---

## E. GitHub Production Protection

### E.1 Workflow Safety Analysis (from source code)

| Check | Evidence | Status |
|-------|----------|--------|
| `migrate.yml` trigger | `on: workflow_dispatch` only — no `push`, no `pull_request` | ✅ Manual only |
| CI (`test.yml`) triggers migration | `on: push` / `on: pull_request` — does NOT reference `migrate.yml` | ✅ CI cannot trigger migration |
| `NEON_URL` in CI test workflow | `grep NEON_URL .github/workflows/test.yml` → empty | ✅ Not exposed in CI |
| `dry-run` job requires environment | No `environment:` in dry-run job | ✅ Dry-run is unrestricted |
| `production` job requires environment | `environment: production` in production job | ✅ Gate present in YAML |
| Confirm token enforcement | `if [ "${{ inputs.confirm }}" != "MIGRATE_PRODUCTION" ]; then exit 1; fi` | ✅ Token check in job |
| Concurrency lock | `concurrency: group: schema-migration, cancel-in-progress: false` | ✅ No parallel migrations |
| `NEON_URL` exposed before approval | Secret only used inside `production` job steps (after environment gate) | ✅ Not pre-approval |

### E.2 GitHub Environment Protection — Limitations

| Item | Evidence | Status |
|------|----------|--------|
| `production` environment created | API confirmed in prior session: `env id=26212785653, protection_rules=[required_reviewers]` | ✅ VERIFIED (prior session) |
| Required reviewer: alicetu0712 | API response: `reviewers=[{type: User, login: alicetu0712}]` | ✅ VERIFIED (prior session) |
| Re-verification this session | `gh` CLI not installed; no GITHUB_TOKEN in this environment | ⚠️ CANNOT RE-VERIFY via API |
| `prevent_self_review` | Set to `false` — owner can self-approve | ⚠️ KNOWN LIMITATION |

**Critical caveat on Required Reviewers effectiveness:**

GitHub's Required Reviewers for Environments enforces human approval ONLY if:
1. The repository is public, OR
2. The repository is private AND the account has GitHub Pro/Team/Enterprise

If the repository is **private + GitHub Free plan**, the environment protection rules are created but the enforcement mechanism may be limited or non-functional (GitHub silently skips the approval gate).

**This cannot be verified programmatically from local environment.** Human verification required:
- Log in to github.com → Settings → Environments → production
- Confirm that the "Required reviewers" protection rule shows as active
- Optionally: trigger a test workflow_dispatch (dry-run only, no NEON_URL) and verify the approval gate appears

---

## F. Deployment Readiness Gate-by-Gate

| Gate | Requirement | Result | Evidence |
|------|-------------|--------|----------|
| UI P&L | 單筆與累計淨損益正確顯示 | ✅ PASS | d27e1b2: gross→net fix; 15 new tests PASS; DB values confirmed correct |
| Release Integrity | RC SHA verified, code frozen | ✅ PASS | d27e1b2 is RC; trade_service/models/migration unchanged from 91e8d7b |
| PostgreSQL Integration | Real PG tests PASS | ✅ PASS | 29 scenarios / 32 assertions, embedded PG 18.6 (trade code unchanged) |
| Browser E2E | 18/18 PASS | ✅ PASS | Playwright + Streamlit + embedded PG 18.6 (DB assertions unaffected by toast fix) |
| Full Regression | 1207 tests PASS | ✅ PASS | Re-run on d27e1b2: 1207/1207 |
| Coverage | ≥ 75% | ✅ PASS | 83.00% on d27e1b2 |
| GitHub CI | Latest RC CI PASS | NOT VERIFIED | d27e1b2 pushed to origin; CI run triggered, pending human check at Actions tab |
| Trade P&L | Independent recalculation matches | ✅ PASS | WAC=101.8113, partial=3,880.33, cumulative=16,627.00; all correct; UI now matches |
| Migration Safety | Dry-run / Preflight / Drift | ✅ PASS | All 6 migrations verified on embedded PG; script SHA fingerprinted |
| Backup | Pre-migration backup | BLOCKED | Neon backup documented in Runbook §2 but NOT yet executed — human action required |
| GitHub Approval | Required Reviewer enforcement | NOT VERIFIED | YAML gate present; prior session API confirmed env; plan-dependency unknown without browser login |
| Production Permissions | Minimal privilege | ✅ PASS | `NEON_URL` only in production job post-approval; not in CI; concurrency locked |
| Recovery | Executable runbook | ✅ PASS | `docs/phase1b_production_migration_runbook.md` §7 rollback decision tree documented |

---

## G. Known Limitations & Remaining Requirements

### Before Executing Production Migration (Human Actions Required)

1. **Verify GitHub CI for d27e1b2** — Go to github.com/alicetu0712/taiwan-stock-ai/actions and confirm the CI run for `d27e1b2` passes (lint + test). Expected: same as 91e8d7b since only `dashboard/` and `tests/` changed.

2. **Verify GitHub Required Reviewer enforcement** — Log in to github.com → Settings → Environments → `production`. Confirm "Required reviewers" rule is enforced (not silently bypassed due to plan restrictions).

3. **Take Neon Production backup** — In Neon Console, create snapshot labeled `phase1b-premigration-YYYYMMDD` before triggering any migration.

4. **Trigger migration with confirm token** — Use `confirm = "MIGRATE_PRODUCTION"` in workflow_dispatch inputs.

### Resolved Issues (were blocking, now fixed)

5. ~~**UI success toast P&L is a gross estimate**~~ — **FIXED in d27e1b2.** Both partial and full sell toasts now show net P&L from DB. See §C.4.

### Non-blocking Known Issues

6. **`scripts/` lint issues** — Pre-existing, out of CI scope, not Phase 1B code.

7. **`prevent_self_review=false`** — Solo developer; owner can approve own migration. Acceptable trade-off.

---

## H. Final Decision

## ✅ DEPLOYMENT PREPARED

**Release Candidate: `d27e1b2`**  
**All technically verifiable gates PASS.**  
**Three items require human action before triggering migration:**

1. Verify CI passes for d27e1b2 (Actions tab on GitHub)
2. Verify GitHub Required Reviewer gate is active (browser login to Environments settings)
3. Take Production Neon database backup (Neon Console → Branch → Create snapshot)

**Production Migration remains NOT EXECUTED — awaiting explicit operator trigger.**
