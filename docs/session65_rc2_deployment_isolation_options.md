# Session 65 — RC-2 Deployment Isolation Options

---

## Context

The cron at `0 16 * * 1-5` IS installed and running. It calls `backfill_daily_prices.py --execute` via `hybrid_shadow_cron.py`. After deploying RC-2, the next 16:00 run will automatically use the new `_is_excluded()` logic, make Provider HTTP calls, and potentially write to `data/platform.db` if QG passes.

This means "code-only deployment" is not truly isolated from scheduled execution. Three options are presented below.

---

## Option 1 — Isolated Inactive Copy (Safest for Code Verification)

**Description**: Apply the RC-2 patch to a separate copy of the script that is NOT referenced by the crontab or any other scheduler.

**Implementation**:
```bash
# DO NOT EXECUTE IN SESSION 65
# Copy script to isolated location (NOT in scripts/)
cp scripts/backfill_daily_prices.py /tmp/rc2_test/backfill_daily_prices.py
# Apply patch in-memory
python3 -c "
  src = open('/tmp/rc2_test/backfill_daily_prices.py').read()
  patched = src.replace('    if len(sid) > 4 and not sid.isdigit():',
                        '    if len(sid) > 4:', 1)
  open('/tmp/rc2_test/backfill_daily_prices.py', 'w').write(patched)
"
# Run offline unit tests against isolated copy
python3 -m pytest tests/test_session63_rc2_authorization.py -q
```

**Assessment**:

| Property | Rating |
|---|---|
| Safety | MAXIMUM — cron never touches the isolated copy |
| Complexity | LOW — simple file copy |
| Reversibility | TRIVIAL — just delete the copy |
| Production Impact | NONE — production script untouched |
| Required Authorization | Code-only deployment authorization (this session's scope) |

**Limitation**: Does NOT constitute production deployment. No data is fixed. Research universe unaffected.

---

## Option 2 — Scheduled Execution Authorization (Safest for Production Data)

**Description**: Deploy RC-2 to production, but only after obtaining BOTH:
1. Code deployment authorization (RC-2 patch)
2. Explicit scheduled execution authorization (acknowledging next cron run will use new logic and may write to DB)

**Two-part Authorization Text**:

Part A (Code):
> 「我明確授權在已驗證的正式環境中，僅部署 AUTH-RC61-02 的 Exact Diff。」

Part B (Execution awareness):
> 「我了解該 Repository 的 crontab 在每個工作日 16:00 自動執行 `hybrid_shadow_cron.py --execute`，該排程在 RC-2 部署後將立即使用新的排除邏輯。我授權此行為。Provider HTTP Requests 和（QG 通過時的）SQLite 寫入均在已授權範圍內。」

**Assessment**:

| Property | Rating |
|---|---|
| Safety | HIGH — both authorizations are explicit |
| Complexity | LOW — single deployment, explicit scope |
| Reversibility | HIGH — rollback code restores prior behavior |
| Production Impact | DIRECT — next 16:00 run uses new logic |
| Required Authorization | Part A + Part B (both needed) |

**This is the recommended path if the user intends for RC-2 to take effect in production.**

---

## Option 3 — Separated Deployment Windows (Maximum Governance Control)

**Description**: Split into four independent authorized decisions:

| Decision | Action | Authorization |
|---|---|---|
| D1: Code Deployment | Apply RC-2 diff to production script | AUTH-RC61-02 (Part A) |
| D2: Scheduled Execution | Allow cron to run with new logic | Separate explicit acknowledgment |
| D3: Provider Fetch | TWSE/TPEx API calls | Existing ongoing authorization |
| D4: DB Write | SQLite writes when QG passes | AUTH01 (backfill execution) |

**Implementation**:
1. Deploy RC-2 at a time when no cron run is imminent (e.g., just after 16:00)
2. This gives ~24 hours before the next scheduled run
3. During that window, user can explicitly approve "first run with new logic" or temporarily pause cron

**Assessment**:

| Property | Rating |
|---|---|
| Safety | MAXIMUM governance — each decision is explicit |
| Complexity | HIGH — requires coordination |
| Reversibility | HIGH per decision |
| Production Impact | Controlled timing |
| Required Authorization | 4 separate decisions |

**Limitation**: Most complex. Appropriate if strict change management is required.

---

## Recommendation

For the current state (QG consistently failing due to data freshness issue, DB writes not occurring):

**Option 2** is recommended. The cron's Provider HTTP calls were already happening before this session. RC-2 reduces unauthorized warrant fetches. The user should provide both Part A and Part B authorizations.

If strict "code first, execution later" separation is required: **Option 3** — deploy RC-2 immediately after a 16:00 run to have the maximum safe window before next execution.

If the user ONLY wants to verify the patch without any production effect: **Option 1**.

---

## Quick Reference: Six Scenarios

| Scenario | Description | Provider HTTP Risk | DB Write Risk | Authorization Impact |
|---|---|---|---|---|
| A | Cron not installed | NONE | NONE | Code deployment is truly code-only |
| B | Cron installed, no backfill call | LOW | NONE | Code deployment is code-only for data |
| C | Cron installed, backfill without --execute | MODERATE | NONE (dry-run) | Provider calls happen, no DB writes |
| **D** | **Cron installed, backfill with --execute** | **HIGH (CONFIRMED)** | **CONDITIONAL on QG (CONFIRMED PATH)** | **Code deployment is NOT data-isolated** |
| E | Cron uses different repo copy | MODERATE | DIFFERENT target | RC-2 patch wouldn't affect that copy |
| F | Scheduler state unverifiable | HIGH | HIGH | Cannot authorize |

**Current state: Scenario D confirmed.**
