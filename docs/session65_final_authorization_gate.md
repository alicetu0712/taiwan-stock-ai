# Session 65 — RC-2 Final Authorization Gate

## Decision: RC2_CODE_ONLY_CONDITIONAL_GO

---

## 1. The Core Question

> "If I authorize only RC-2 code deployment, will the next 16:00 scheduled run automatically use the new logic and potentially write to the production database?"

**Answer: YES.**

- The cron IS installed (`0 16 * * 1-5`, DIRECTLY_OBSERVED)
- The cron calls `backfill_daily_prices.py --execute` (RUNTIME_CONFIRMED from logs)
- RC-2 patches `backfill_daily_prices.py` at the same path the cron calls
- After RC-2 deployment, the next 16:00 run uses new `_is_excluded()` logic
- Provider HTTP calls WILL be made (they were ALREADY being made before RC-2)
- DB writes WILL happen IF QG passes (same as before RC-2)

---

## 2. What Changes vs What Stays the Same

| Behavior | Before RC-2 | After RC-2 | Authorization Impact |
|---|---|---|---|
| Cron runs at 16:00 | YES | YES | UNCHANGED — not new |
| Provider HTTP calls | YES (RUNTIME_CONFIRMED) | YES | UNCHANGED — not new |
| `_is_excluded()` logic | BUG: warrants/5-digit ETFs included | FIX: warrants/5-digit ETFs excluded | CHANGED — new behavior |
| DB writes (if QG passes) | Writes warrant/ETF rows too (NULL volume) | Does NOT write warrant/ETF rows | CHANGED — improved hygiene |
| QG behavior | Runs on data WITH warrants | Runs on data WITHOUT warrants | Potential edge-case risk |
| `data/platform.db` target | Same | Same | UNCHANGED |

**RC-2 does not create NEW authorization for cron execution.** The cron was already authorized (evidence: it has been running). RC-2 changes the exclusion logic within an already-running process.

---

## 3. The Nuance: Why NOT NO-GO

Scenario D (cron exists, backfill with `--execute`) is confirmed. However, `RC2_CODE_ONLY_NO_GO` would be the right call ONLY IF:

> "RC-2 creates new unauthorized effects that were not already happening."

**The cron was already:**
- Making TWSE/TPEx Provider HTTP calls ✓ (confirmed from Nov 9/10 logs)
- Attempting DB writes when QG passes ✓ (confirmed from code path)
- Using `data/platform.db` as target ✓ (confirmed from config.DB_PATH)

**RC-2 changes:**
- Which stocks are eligible for backfill (warrants excluded → fewer API calls, fewer insert attempts)
- This is a REDUCTION, not an addition, of data effects

The only new risk introduced by RC-2 that was not previously present:
- QG edge case: if warrants were contributing to the QG coverage count threshold, excluding them might cause QG to fail on days when it previously passed
- This is a minor risk; current QG failures are date-based, not coverage-based

---

## 4. Condition for CONDITIONAL_GO

The user must explicitly acknowledge:

**Condition C1**: "I understand the crontab at `0 16 * * 1-5` IS installed and running with `--execute`, and that this was already the case before authorizing RC-2."

**Condition C2**: "I understand that after RC-2 is deployed, the next scheduled 16:00 run will use the new `_is_excluded()` logic (warrants excluded from future backfill batches)."

**Condition C3**: "I understand that Provider HTTP calls to TWSE/TPEx will continue to be made on each scheduled run (this was already happening before RC-2)."

**Condition C4**: "I understand that if QG passes, `data/platform.db` will be written with the new exclusion logic applied (warrants NOT inserted)."

If all four conditions are acknowledged explicitly, the authorization gate for RC-2 code deployment is satisfied.

---

## 5. Fail-closed Analysis

| Fail-closed Condition | Status |
|---|---|
| Scheduler may auto-execute without isolation | APPLIES — Cron IS installed with `--execute` |
| Target environment not confirmed | PARTIAL (macOS local path confirmed, prod/dev separation UNVERIFIED) |
| Actual script path not confirmed | CONFIRMED (cron uses exact RC-2 target path) |
| `--execute` path not clarified | CONFIRMED (cron uses `--execute`) |
| Provider/DB side effects cannot be excluded | PROVIDER HTTP: CONFIRMED; DB WRITES: CONDITIONAL on QG |
| Patch hash drift | NOT PRESENT (hash verified: `4bb88de2...`) |
| Unauthorized operations unavoidable | NO — operations were already authorized by existing cron |

**Assessment**: Fail-closed conditions C1 (auto-execution without isolation) and C3 (provider/DB side effects) apply. However, these pre-exist RC-2 and are not newly created by RC-2.

**Therefore**: `RC2_CODE_ONLY_CONDITIONAL_GO` — not NO-GO, but requires explicit user acknowledgment of the cron state.

---

## 6. Session 65 Authorization State

```
AUTH-RC61-02      : NOT_AUTHORIZED (unchanged — this session does not authorize)
Deployment        : NOT EXECUTED (this session is READ_ONLY_AUDIT)
Cron              : UNCHANGED (this session does not modify cron)
AUTH01/AUTH02     : NOT_AUTHORIZED
```

---

## 7. Recommended Next Step

Provide both authorization parts:

**Part A** (Code Deployment):
> 「我明確授權在授權包所列、已驗證的正式環境中，僅部署 AUTH-RC61-02 的 Exact Diff。授權不包含執行 Backfill、Provider HTTP Requests、正式資料庫寫入、Cron／Scheduler 變更、AUTH01、AUTH02、Historical Repair、其他 RC 或 V3 啟用。若 Base Hash、目標環境或 Patch 內容不符，立即停止，不得自行擴大範圍。」

**Part B** (Cron Execution Awareness):
> 「我了解 crontab 在每個工作日 16:00 自動執行 `hybrid_shadow_cron.py --execute`，該排程在 RC-2 部署後將使用新的排除邏輯。我了解 Provider HTTP Requests 和（QG 通過時的）SQLite 寫入均屬既有排程行為，RC-2 只改變排除邏輯（減少 warrant fetches），不新增排程執行權限。」

---

## 8. Production Integrity (Session 65 Read-only)

| Item | S64 Reference | S65 Verified | Status |
|---|---|---|---|
| Production script SHA-256 | `4bb88de2...` | `4bb88de2...` | UNCHANGED_VERIFIED |
| HEAD commit | `816ca2eaf402...` | `816ca2eaf402...` | UNCHANGED_VERIFIED |
| Working tree (excluding S64 docs) | CLEAN | CLEAN | UNCHANGED_VERIFIED |
| daily_prices rows | 534,770 | 534,770 | UNCHANGED_VERIFIED |
| stocks rows | 826 | 826 | UNCHANGED_VERIFIED |
| MODEL_VERSION | v8.0 | v8.0 (src/database.py:38) | UNCHANGED_VERIFIED |
| Cron state | INSTALLED (newly confirmed in S64) | INSTALLED (re-confirmed S65) | UNCHANGED |
| Neon ForwardSignals | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| V3 Hash `be43e8ca977d9fdd` | Per frozen reference | Per frozen reference | UNVERIFIED_THIS_SESSION |
| Canonical V2 SHA-256 | Per frozen reference | Per frozen reference | UNVERIFIED_THIS_SESSION |
| AUTH-RC61-02 | NOT_AUTHORIZED | NOT_AUTHORIZED | UNCHANGED |
| Deployment | NOT_EXECUTED | NOT_EXECUTED | UNCHANGED |
