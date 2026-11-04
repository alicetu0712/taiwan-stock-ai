# Phase 1B Production Migration Runbook

**Document date:** 2026-11-04 (final safety verification 2026-11-04 — RC updated to e27ee1a)  
**Migration scope:** ACTUAL Trade Lifecycle schema — 3 tables + 6 DDL changes  
**Target environment:** Production Neon PostgreSQL  
**Trigger:** Manual only (`workflow_dispatch`) — human approval required  
**Author:** Senior Engineer / DBA

---

> **CRITICAL RESTRICTION:**  
> This runbook authorizes ONLY the documented migration via GitHub Actions `migrate.yml`.  
> Do NOT connect directly to Production Neon, execute DDL from local shell, or bypass the workflow gate.  
> Do NOT trigger the workflow automatically. All production steps require explicit human action.

---

## §1. Operator Identity Verification

Before proceeding, confirm you are:

| Check | Expected | Action |
|-------|----------|--------|
| GitHub account | alicetu0712 | Log in at github.com/login |
| Repository | taiwan-stock-ai | Confirm at github.com/alicetu0712/taiwan-stock-ai |
| Branch | main | `git branch --show-current` → `main` |
| HEAD SHA | e27ee1a | `git rev-parse --short HEAD` → `e27ee1a` |
| migration script SHA | da95d80b... | `shasum -a 256 scripts/migrate_trade_lifecycle.py` |

Expected script SHA-256:
```
da95d80bc2093839a5ebfd024294e30b0aa1147201785d2c6b0ce6ccabb77ba5  scripts/migrate_trade_lifecycle.py
```

**STOP if any identity check fails.** Verify you are on the correct branch and repo before proceeding.

---

## §2. Pre-migration Backup

**Mandatory.** Take a manual backup BEFORE triggering any migration step.

### 2.1 Neon Console Snapshot

1. Go to **console.neon.tech** → your project → **Branches**
2. Click the production branch (typically `main` or the default branch)
3. Click **"Create restore point"** (or "Create snapshot" — exact label depends on Neon UI version)
4. Name it: `phase1b-premigration-YYYYMMDD` (e.g., `phase1b-premigration-20261104`)
5. Record the snapshot ID in the incident log

### 2.2 Fallback: `pg_dump` via Neon Connection

If Neon console snapshot is unavailable, run from local shell:

```bash
pg_dump \
  --no-owner --no-acl \
  --table=actual_positions \
  --table=trade_executions \
  --table=position_plan_changes \
  "$NEON_URL" \
  > backups/phase1b_premigration_$(date +%Y%m%d_%H%M%S).sql
```

> Note: This requires `NEON_URL` to be set in your local shell. Do NOT commit this file or expose the URL.

### 2.3 Backup Verification

After backup, verify it is non-empty and readable:

```bash
# For pg_dump file:
ls -lh backups/phase1b_premigration_*.sql
head -20 backups/phase1b_premigration_*.sql   # should show PostgreSQL dump header
```

For Neon console snapshot: confirm the snapshot shows in the branch timeline.

**STOP if backup is empty, corrupt, or unverifiable.**

---

## §3. Restore Verification (Dry-run of Recovery Path)

Verify you CAN restore before you migrate. This confirms the backup is valid and the restore path works.

### 3.1 Restore to a Test Branch (Recommended)

1. In Neon Console: **Branches → Create branch from snapshot**
2. Name the test branch: `phase1b-restore-test`
3. Connect to the test branch URL and verify tables exist:

```sql
-- Connect to test branch
\dt actual_positions trade_executions position_plan_changes
SELECT COUNT(*) FROM actual_positions;
SELECT COUNT(*) FROM trade_executions;
```

If row counts match the production counts noted in §2.1, restore capability is confirmed.

4. **Delete the test branch** after verification (Neon branches are free but clean up after yourself)

### 3.2 Restore Capability Checklist

| Item | Expected | Verified |
|------|----------|----------|
| Backup snapshot exists | Yes | ☐ |
| Restore branch created | Yes | ☐ |
| `actual_positions` row count matches | Yes | ☐ |
| `trade_executions` row count matches | Yes | ☐ |
| Test branch deleted after verification | Yes | ☐ |

**STOP if restore verification fails.** Do not proceed until backup is confirmed restorable.

---

## §4. Expected Schema Changes

The migration script applies 6 DDL changes to the production schema.

### 4.1 Table Creation

If tables do not yet exist in production, `Base.metadata.create_all()` creates:

| Table | DDL type | Reversible? |
|-------|----------|-------------|
| `actual_positions` | CREATE TABLE (19 cols) | Manual (DROP TABLE) |
| `trade_executions` | CREATE TABLE (17 cols) | Manual (DROP TABLE) |
| `position_plan_changes` | CREATE TABLE (8 cols) | Manual (DROP TABLE) |

For a first-time migration to production, all three tables will be created fresh.  
For a re-run on existing production data: `create_all()` is idempotent — skips tables that exist.

### 4.2 Migration Sequence

| Order | Name | DDL | Transactional | Rollback |
|-------|------|-----|---------------|---------|
| v1.1 | `v1.1_add_idempotency_key` | `ALTER TABLE trade_executions ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(64)` | ✅ Yes | `ALTER TABLE trade_executions DROP COLUMN idempotency_key` |
| v1.2 | `v1.2_add_idempotency_key_unique_index` | `CREATE UNIQUE INDEX IF NOT EXISTS uix_te_idempotency_key ON trade_executions(idempotency_key) WHERE idempotency_key IS NOT NULL` | ⚠️ Partial — `CREATE INDEX` acquires `ShareUpdateExclusiveLock`, cannot be in same transaction as other DDL on the same table | Idempotent (IF NOT EXISTS); manual: `DROP INDEX uix_te_idempotency_key` |
| v1.3 | `v1.3_add_fk_actual_positions_fwd_signals` | `ALTER TABLE actual_positions ADD CONSTRAINT fk_ap_forward_signal FOREIGN KEY (forward_signal_id) REFERENCES forward_signals(id)` | ✅ Yes | `ALTER TABLE actual_positions DROP CONSTRAINT fk_ap_forward_signal` |
| v1.4 | `v1.4_add_fk_trade_executions_positions` | `ALTER TABLE trade_executions ADD CONSTRAINT fk_te_position FOREIGN KEY (position_id) REFERENCES actual_positions(id)` | ✅ Yes | `ALTER TABLE trade_executions DROP CONSTRAINT fk_te_position` |
| v1.5 | `v1.5_add_fk_position_plan_changes_positions` | `ALTER TABLE position_plan_changes ADD CONSTRAINT fk_ppc_position FOREIGN KEY (position_id) REFERENCES actual_positions(id)` | ✅ Yes | `ALTER TABLE position_plan_changes DROP CONSTRAINT fk_ppc_position` |
| v1.6 | `v1.6_add_fk_trade_executions_linked_signal` | `ALTER TABLE trade_executions ADD CONSTRAINT fk_te_linked_signal FOREIGN KEY (linked_forward_signal_id) REFERENCES forward_signals(id)` | ✅ Yes | `ALTER TABLE trade_executions DROP CONSTRAINT fk_te_linked_signal` |

**v1.1 and v1.2 are NOT `pg_only` — they also execute on SQLite in test environments.**  
**v1.3–v1.6 are `pg_only=True` — only execute on PostgreSQL.**

### 4.3 Idempotency Guarantees

| Migration | Idempotency mechanism |
|-----------|----------------------|
| v1.1 | `IF NOT EXISTS` clause |
| v1.2 | `IF NOT EXISTS` clause |
| v1.3–v1.6 | `verify()` lambda pre-checks existence; migration skipped if already applied |

Re-running the migration script on a fully-migrated schema will produce zero changes (all 6 `PENDING → SKIPPED`).

---

## §5. Execution Procedure

### 5.1 Pre-flight Checklist

Before triggering the workflow:

- [ ] Backup completed (§2)
- [ ] Restore capability verified (§3)
- [ ] Migration script SHA verified (§1)
- [ ] Logged in as alicetu0712
- [ ] No active trades being executed (trading hours: 09:00–13:30 Taiwan time)
- [ ] `migrate.yml` reviewed — no unexpected changes
- [ ] GitHub production environment protection rule visible in Settings

**Recommended execution window:** Weekday evening after 15:00 TWN (trading closed, pre-market check possible next morning)

### 5.2 Step-by-step Execution

#### Step A: Trigger Dry-run (no production changes)

1. Go to: github.com/alicetu0712/taiwan-stock-ai/actions/workflows/migrate.yml
2. Click **"Run workflow"**
3. Set inputs:
   ```
   confirm: (leave empty)
   ```
4. The `dry-run` job runs. Wait for it to complete (typically 60–120 seconds)
5. Review output: should show `[DRY-RUN] Migration would apply: ...` for each pending migration
6. Confirm dry-run shows exactly the 6 expected migrations (v1.1–v1.6) or subset of pending ones
7. **Confirm dry-run job PASSED before proceeding**

#### Step B: GitHub Environment Approval

The `production` job will pause for approval before running.

1. GitHub sends approval request to reviewer: alicetu0712
2. Log in to GitHub notifications or directly to the workflow run URL
3. Review the deployment request; confirm it is the expected migration
4. Click **"Review deployments" → check "production" → click "Approve and deploy"**
5. The job proceeds ONLY after this approval

> If the approval gate does NOT appear, the GitHub Required Reviewers rule may not be enforced. In that case, CANCEL the workflow run and verify repo plan (see §8.2).

#### Step C: Trigger Production Migration

1. Return to: github.com/alicetu0712/taiwan-stock-ai/actions/workflows/migrate.yml
2. Click **"Run workflow"** again
3. Set inputs:
   ```
   confirm: MIGRATE_PRODUCTION
   ```
4. Click **"Run workflow"** to trigger
5. Wait for `dry-run` job to complete (included in production workflow)
6. When `production` job is awaiting approval (paused), complete GitHub Environment approval (Step B)
7. Watch the `production` job logs for progress

Expected production job log output:
```
[DRY-RUN] Starting preflight validation...
[DRY-RUN] ✅ All preflight checks passed
[PHASE 2] Applying migration: v1.1_add_idempotency_key
[PHASE 2] ✅ Migration committed: v1.1_add_idempotency_key
[PHASE 2] Applying migration: v1.2_add_idempotency_key_unique_index
[PHASE 2] ✅ Migration committed: v1.2_add_idempotency_key_unique_index
... (v1.3–v1.6 similarly)
[PHASE 3] DDL audit: planned=6 attempted=6 committed=6 rolled_back=0
[VALIDATE] ✅ Schema validation passed (9 checkpoints)
[SUCCESS] Migration complete
```

**STOP if any step fails.** Do not re-run. See §7 (Rollback Decision Tree).

---

## §6. Post-migration Validation

After `production` job completes with ✅:

### 6.1 Automated Validation (Built into Workflow)

The workflow's post-migration step runs:

```python
# From migrate.yml post-migration block
tables = ['actual_positions', 'trade_executions', 'position_plan_changes']
# Checks all three tables exist
# Workflow step fails if any table missing
```

This is a minimal check. Run additional manual validation below.

### 6.2 Manual Schema Validation

Connect to Neon and verify:

```sql
-- Check all three tables exist
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN ('actual_positions', 'trade_executions', 'position_plan_changes');
-- Expected: 3 rows

-- Check idempotency_key column was added
SELECT column_name, data_type, character_maximum_length, is_nullable
FROM information_schema.columns
WHERE table_name = 'trade_executions' AND column_name = 'idempotency_key';
-- Expected: idempotency_key | character varying | 64 | YES

-- Check partial unique index exists
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'trade_executions' AND indexname = 'uix_te_idempotency_key';
-- Expected: index with WHERE (idempotency_key IS NOT NULL)

-- Check all 4 FK constraints exist
SELECT tc.constraint_name, tc.table_name, kcu.column_name,
       ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
AND tc.table_name IN ('actual_positions', 'trade_executions', 'position_plan_changes')
ORDER BY tc.table_name;
-- Expected: fk_ap_forward_signal, fk_te_position, fk_ppc_position, fk_te_linked_signal
```

### 6.3 Application Smoke Test

1. Deploy the application (separate step from migration)
2. Navigate to the ACTUAL Positions page in the dashboard
3. Confirm the page loads without error
4. Create a minimal test BUY trade:
   - Choose a stock with an existing ForwardSignal
   - Buy quantity = 100, price = any valid price
   - Verify the trade is recorded and `actual_positions` row is created
5. Check that `trade_executions.idempotency_key` is populated for the new trade

> Note: Do NOT use real money amounts for smoke testing. Use minimal quantities.

---

## §7. Rollback Decision Tree

### 7.1 Decision Matrix

| Failure scenario | Rollback action | Downtime |
|-----------------|-----------------|---------|
| Dry-run job fails | None needed; production untouched | None |
| Production job fails BEFORE v1.1 commit | Re-run after fixing issue; no data affected | None |
| v1.1 (ADD COLUMN) committed, v1.2 fails | Option A: leave v1.1 (harmless); Option B: manual DROP COLUMN | ≤ 5 min |
| v1.2 committed, v1.3+ fails | Leave v1.1+v1.2; manually apply remaining FKs; OR restore from backup | ≤ 10 min |
| Any FK migration fails (v1.3–v1.6) | Option A: re-run script (idempotent); Option B: restore from Neon snapshot | ≤ 15 min |
| ALL migrations committed, app fails | Restore from Neon snapshot; redeploy previous app version | 15–30 min |

### 7.2 Rollback Procedure (Neon Snapshot Restore)

**Use this only if the application is broken after migration and manual DDL revert is not feasible.**

1. Go to Neon Console → Branches → production branch
2. Click **"Restore"** → select the `phase1b-premigration-YYYYMMDD` snapshot
3. Confirm restore. This is **DESTRUCTIVE** — all data written after the snapshot is lost
4. Verify row counts match the pre-migration counts recorded in §2.1
5. Notify all users that any trades recorded during the migration window may be lost

**Data loss window:** Any `actual_positions` or `trade_executions` rows written between the snapshot and the restore point will be LOST. For this reason:
- Take the backup IMMEDIATELY before migration (minimize the window)
- Execute during off-hours when no trades are expected

### 7.3 Manual DDL Rollback (Preferred for Partial Failures)

For v1.1 (ADD COLUMN):
```sql
ALTER TABLE trade_executions DROP COLUMN IF EXISTS idempotency_key;
```

For v1.2 (INDEX):
```sql
DROP INDEX IF EXISTS uix_te_idempotency_key;
```

For v1.3–v1.6 (FK constraints):
```sql
ALTER TABLE actual_positions DROP CONSTRAINT IF EXISTS fk_ap_forward_signal;
ALTER TABLE trade_executions DROP CONSTRAINT IF EXISTS fk_te_position;
ALTER TABLE position_plan_changes DROP CONSTRAINT IF EXISTS fk_ppc_position;
ALTER TABLE trade_executions DROP CONSTRAINT IF EXISTS fk_te_linked_signal;
```

After manual DDL rollback, verify the schema has returned to pre-migration state:
```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'trade_executions' AND column_name = 'idempotency_key';
-- Expected: 0 rows (column removed)

SELECT constraint_name FROM information_schema.table_constraints
WHERE constraint_type = 'FOREIGN KEY'
AND table_name IN ('actual_positions', 'trade_executions', 'position_plan_changes');
-- Expected: 0 rows (all FKs removed)
```

---

## §8. Health Check Checklist

After successful migration and application deployment:

### Immediate (T+0 to T+15 min)

| Check | Expected | Verified |
|-------|----------|----------|
| All 3 tables exist in production | Yes | ☐ |
| `idempotency_key` column present | Yes | ☐ |
| Partial unique index exists | Yes | ☐ |
| All 4 FK constraints present | Yes | ☐ |
| Application loads without 500 error | Yes | ☐ |
| ACTUAL positions page loads | Yes | ☐ |
| Existing positions (if any) display correctly | Yes | ☐ |

### Short-term (T+1 hour to T+1 trading day)

| Check | Expected | Verified |
|-------|----------|----------|
| New trade creates idempotency_key | Yes | ☐ |
| Duplicate submission rejected (idempotent) | Yes | ☐ |
| ForwardSignals unmodified | Yes | ☐ |
| PAPER positions unaffected | Yes | ☐ |
| Neon monitor shows no connection errors | Yes | ☐ |

---

## §9. Incident Escalation Procedure

### Severity Levels

| Level | Trigger | Response time | Action |
|-------|---------|---------------|--------|
| SEV-1 | Production data corruption / loss | Immediate | Execute rollback immediately; do not wait |
| SEV-2 | Application down / trades blocked | < 5 min | Assess rollback vs. hotfix; default to rollback |
| SEV-3 | Partial feature degraded (e.g., idempotency not working) | < 30 min | Manual FK/index DDL rollback; keep app running |
| SEV-4 | Display-only issue / non-critical warning | Next business day | Log issue; no immediate action |

### Escalation Contact

| Role | Person | Channel |
|------|--------|---------|
| Primary operator | alicetu0712 | GitHub @alicetu0712; alicetu12356@gmail.com |
| Neon support | support.neon.tech | For database-level issues |

### Incident Log Template

```
INCIDENT LOG — Phase 1B Migration
Date: YYYY-MM-DD HH:MM TWN
Operator: alicetu0712
Branch: main
HEAD SHA: e27ee1a
Migration script SHA: da95d80b...

Pre-migration state:
  actual_positions row count: ___
  trade_executions row count: ___
  Backup snapshot ID: ___

Migration outcome: [ SUCCESS / PARTIAL / FAILURE ]

Steps taken:
  [HH:MM] Triggered dry-run → outcome: ___
  [HH:MM] GitHub approval requested
  [HH:MM] Approval granted by: ___
  [HH:MM] Triggered production migration → outcome: ___
  [HH:MM] Post-migration validation → outcome: ___

If failure:
  Error message: ___
  Failed at migration step: v1.___
  Rollback action taken: ___
  Rollback completed at: HH:MM
  Post-rollback row counts: actual_positions=___ trade_executions=___
```

---

## §10. Post-completion Sign-off

Upon successful migration and health check:

| Item | Completed |
|------|-----------|
| All §6.2 SQL validations passed | ☐ |
| All §8 immediate health checks passed | ☐ |
| `docs/phase1b_release_readiness.md` updated with migration timestamp | ☐ |
| Incident log closed with SUCCESS outcome | ☐ |
| Neon Console shows migration snapshot labeled correctly | ☐ |
| Phase 1B declared PRODUCTION DEPLOYED in memory | ☐ |

**Phase 1B Production Migration is considered complete when all items above are checked.**

---

## Appendix A: Five-Question Final Answers

### Q1. Phase 1B 是否已安全凍結？

**答：是。** Release Candidate `e27ee1a`（lint fix，RC freeze）。核心系統（`trade_service`, `database.py`, migration script, strategy analyzers, Entry Timing V2, v8.0, foe_v1）凍結於 `91e8d7b` 不變。UI 修正在 `d27e1b2`（gross→net P&L toast）；`e27ee1a` 是 isort/black lint-only，邏輯無變更。工作樹乾淨，origin/main 同步。1207 tests PASS，83.00% coverage。CI for e27ee1a：Lint ✅ + Test 3.11 ✅ + Test 3.13 ✅（run 41783339846）。**所有凍結系統完整。**

### Q2. 交易損益是否完全正確？

**答：是，且 UI 顯示問題已於 d27e1b2 修正（Browser E2E v2 確認）。**

DB 與 Trade Service 一直正確：WAC=101.8113 ✅，部分賣出 realized=3,880.33 ✅，累計 realized=16,627.00 ✅。d27e1b2 修正了 UI toast：
- 部分賣出 toast：「✅ 賣出 500 股 @ 110.00　本次已實現淨損益 +3,880」（MutationObserver 捕捉確認）✅
- 全部賣出 toast：Streamlit st.rerun() 架構限制無法從 DOM 捕捉；DB 值 (16627.00) + 歷史紀錄 ("+16,627") 為授權驗證 ✅
- 無 gross P&L (13,189) 顯示 ✅

**DB、Trade Service、Position Summary、歷史紀錄 四方吻合。**

### Q3. 正式 Migration 前還缺什麼？

**缺一件事（人工動作）：**
1. 在 Neon Console 建立正式 DB snapshot 備份（§2）— `phase1b-premigration-YYYYMMDD`

已解決（先前 pending，現 PASS）：
- ~~確認 CI for d27e1b2 PASS~~ → e27ee1a CI ALL PASS（run 41783339846）✅
- ~~確認 GitHub approval gate 生效~~ → 公開 repo，Free plan 支援 Required Reviewers，API 確認 env id=26212785653, reviewer=alicetu0712 ✅

技術面：Migration script 已驗證、dry-run 路徑已測試、所有 6 個 migration 在 embedded PG 18.6 通過、idempotency 確認。

### Q4. GitHub Production Approval 是否確實有效？

**答：是，EFFECTIVELY ENFORCED（已確認為公開 repo）。**

| 項目 | 結果 |
|------|------|
| YAML gate | `environment: production` ✅ |
| trigger | `workflow_dispatch` only ✅ |
| NEON_URL 隔離 | 只在 production job steps ✅ |
| confirm token | `MIGRATE_PRODUCTION` check ✅ |
| concurrency lock | `cancel-in-progress: false` ✅ |
| reviewer | alicetu0712 (env id=26212785653) ✅ |
| repo 可見性 | **public** (`private=False` via API) ✅ |
| enforcement | 公開 repo → ALL plans 支援，包含 Free ✅ |

**Required Reviewers 對公開 repo 在所有 GitHub plan（含 Free）均有效。Private repo + Free plan 的 bypass 疑慮不適用於此 repo。**

### Q5. 是否已達到 DEPLOYMENT PREPARED？

**答：是，且所有可程式驗證的 gate 已全部通過。**

> ✅ **DEPLOYMENT PREPARED**  
> Release Candidate: `e27ee1a`  
> 1207 tests PASS / 83.00% coverage / UI P&L fix PASS (Browser E2E v2 confirmed)  
> CI: ALL PASS (run 41783339846) / GitHub Approval: EFFECTIVELY ENFORCED  
> Migration safety: static review PASS / 6 migrations idempotent  
>
> Production Migration 尚未執行。執行前需完成**一項**人工動作：  
> (1) 建立 Neon Production 備份（Neon Console → Branch → Create snapshot）  
>
> **DEPLOYMENT PREPARED ≠ 已部署。** 任何生產 Migration 均需明確人工授權觸發。
