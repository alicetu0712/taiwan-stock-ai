# Session 64 — RC-2 Controlled Deployment Runbook

## ⚠ DO NOT EXECUTE IN SESSION 64 OR ANY SESSION WITHOUT EXPLICIT USER AUTHORIZATION ⚠

**All commands in this document are TEMPLATES ONLY.**
**No command may be executed until the user provides the Authorization Text verbatim (see PART G of Session 64 spec).**

---

## Critical Pre-condition: Cron Installed (UNEXPECTED)

**FINDING**: `crontab -l` reveals the cron IS installed:
```
0 16 * * 1-5  .../python3 .../hybrid_shadow_cron.py --execute >> .../hybrid_cron.log 2>&1
```

**Implication**: After RC-2 is deployed, the NEXT cron run (next weekday 16:00 Asia/Taipei) will call `backfill_daily_prices.py --execute` with the new `_is_excluded()` logic. Warrants and 5-digit ETFs will be excluded automatically on the next scheduled run.

**Action required before deployment**: Decide whether to:
1. Leave cron running (RC-2 takes effect at next 16:00 run) — LOW risk, intended behavior
2. Temporarily disable cron before deploy to control timing — requires separate authorization
3. Deploy RC-2 only outside of trading hours to minimize timing ambiguity

---

## P1. Pre-deployment Checklist (12 Confirmations)

All 12 must be explicitly confirmed before proceeding:

| # | Check | Command (Template) | Expected |
|---|---|---|---|
| CD-01 | Explicit authorization received | (manual) | Authorization text confirmed verbatim |
| CD-02 | Authorization scope confirmed | (manual) | Code only, no backfill, no Cron change |
| CD-03 | Production host confirmed | `hostname && whoami` | macOS, `alicetu` |
| CD-04 | Base commit confirmed | `git rev-parse HEAD` | `816ca2eaf40216838555f36a1b1c9f6aff5d6b47` |
| CD-05 | File hash confirmed | `shasum -a 256 scripts/backfill_daily_prices.py` | `4bb88de2...` (full 64-char) |
| CD-06 | Clean target confirmed | `git status --short` | (no output) |
| CD-07 | Cron state confirmed | `crontab -l` | `0 16 * * 1-5 .../hybrid_shadow_cron.py --execute` (INSTALLED — document timing decision) |
| CD-08 | No active backfill process | `pgrep -f backfill_daily_prices` | (no output) |
| CD-09 | DB row count baseline | `sqlite3 data/platform.db "SELECT COUNT(*) FROM daily_prices;"` | `534770` |
| CD-10 | Rollback artifact ready | Confirm backup file exists (Step B2) | `backfill_daily_prices.py.bak-PRE-RC2` |
| CD-11 | Monitoring owner designated | (manual) | Named person or process |
| CD-12 | Stop conditions acknowledged | (manual) | See §P4 Stop Conditions |

---

## P2. Deployment Steps (Minimum-change)

Execute only after ALL 12 pre-deployment checks pass.

### Step A: Verify Target
```bash
# DO NOT EXECUTE IN SESSION 64
shasum -a 256 scripts/backfill_daily_prices.py
# Expected output:
# 4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9  scripts/backfill_daily_prices.py
# STOP if hash does not match exactly.
```

### Step B: Create Exact Backup
```bash
# DO NOT EXECUTE IN SESSION 64
cp scripts/backfill_daily_prices.py scripts/backfill_daily_prices.py.bak-PRE-RC2
shasum -a 256 scripts/backfill_daily_prices.py.bak-PRE-RC2
# Expected: same 4bb88de2... hash as original
# STOP if backup hash does not match.
```

### Step C: Apply Exact Diff
```bash
# DO NOT EXECUTE IN SESSION 64
# Method: Python in-place replacement (deterministic, no patch tool dependency)
python3 - <<'EOF'
import hashlib, shutil, sys

ORIG = "    if len(sid) > 4 and not sid.isdigit():"
PATCHED = "    if len(sid) > 4:"
TARGET = "scripts/backfill_daily_prices.py"
EXPECTED_ORIG_HASH = "4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9"
EXPECTED_PATCH_HASH = "4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb"

with open(TARGET) as f:
    src = f.read()

actual_hash = hashlib.sha256(src.encode()).hexdigest()
if actual_hash != EXPECTED_ORIG_HASH:
    print(f"STOP: hash mismatch. Got {actual_hash[:16]}...")
    sys.exit(1)

count = src.count(ORIG)
if count != 1:
    print(f"STOP: original text found {count} times (expected 1)")
    sys.exit(1)

patched = src.replace(ORIG, PATCHED, 1)
patched_hash = hashlib.sha256(patched.encode()).hexdigest()
if patched_hash != EXPECTED_PATCH_HASH:
    print(f"STOP: patched hash mismatch. Got {patched_hash[:16]}...")
    sys.exit(1)

with open(TARGET, "w") as f:
    f.write(patched)

print(f"RC-2 applied. Patched hash: {patched_hash}")
EOF
```

### Step D: Verify Patched Hash
```bash
# DO NOT EXECUTE IN SESSION 64
shasum -a 256 scripts/backfill_daily_prices.py
# Expected output:
# 4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb  scripts/backfill_daily_prices.py
# STOP if hash does not match exactly.
```

### Step E: Verify Syntax
```bash
# DO NOT EXECUTE IN SESSION 64
python3 -c "import ast; ast.parse(open('scripts/backfill_daily_prices.py').read()); print('SYNTAX_OK')"
# Expected: SYNTAX_OK
```

### Step F: Verify No Unrelated Changes
```bash
# DO NOT EXECUTE IN SESSION 64
git diff scripts/backfill_daily_prices.py
# Expected output must contain ONLY the single-line RC-2 change.
# If any other change appears: STOP — investigate before proceeding.
```

### Step G: Verify No Execution Trigger
```bash
# DO NOT EXECUTE IN SESSION 64
python3 -c "from scripts.backfill_daily_prices import _is_excluded; print(_is_excluded('台積電', '2330'))"
# Expected: False
# This import-only check confirms no execution was triggered.
```

### Step H: Record Deployment Evidence
```bash
# DO NOT EXECUTE IN SESSION 64
echo "RC-2 deployed at $(date)" >> logs/deployment_rc2.log
shasum -a 256 scripts/backfill_daily_prices.py >> logs/deployment_rc2.log
git rev-parse HEAD >> logs/deployment_rc2.log
```

---

## P3. What Deployment Does NOT Include

| Excluded Action | Requires Separate Authorization |
|---|---|
| Running `--execute` backfill | Explicit separate authorization |
| AUTH01 (1,440 TWSE calls) | AUTH01 authorization |
| Historical repair | AUTH02 authorization |
| Cron installation/removal | Cron authorization |
| DB INSERT/UPDATE/DELETE | Execute authorization |
| Neon writes | Neon authorization |
| V3 activation | V3 activation decision |
| Strategy recalculation | Not applicable |

---

## P4. Stop Conditions (Must Abort Deployment)

Abort immediately and preserve evidence if any of the following occur:

| # | Condition | Action |
|---|---|---|
| S01 | Pre-deploy hash ≠ `4bb88de2...` | STOP — REAUTHORIZATION_REQUIRED |
| S02 | Original text count ≠ 1 | STOP — drift detected |
| S03 | Patched hash ≠ `4eb6eacf...` | STOP — patch did not apply correctly |
| S04 | Syntax check fails | STOP — investigate |
| S05 | Unrelated diff detected | STOP — investigate |
| S06 | Import triggers network call | STOP — REAUTHORIZATION_REQUIRED |
| S07 | Import opens production DB | STOP — REAUTHORIZATION_REQUIRED |
| S08 | Unexpected process spawned | STOP — REAUTHORIZATION_REQUIRED |
| S09 | Benchmark 0050 is now excluded | STOP — rollback immediately |
| S10 | Any 4-digit stock is now excluded | STOP — rollback immediately |
| S11 | Scheduler fires during deployment | STOP — wait for cron window to pass |
| S12 | Deployment environment differs from verified | STOP — REAUTHORIZATION_REQUIRED |

---

## P5. Post-deployment Verification (No Backfill Required)

These checks can be performed immediately after deployment without running backfill:

| Check | Command (Template) | Expected |
|---|---|---|
| File hash | `shasum -a 256 scripts/backfill_daily_prices.py` | `4eb6eacf...` |
| Syntax | `python3 -c "import ast; ast.parse(...);"` | OK |
| Static diff | `git diff HEAD scripts/backfill_daily_prices.py` | Single-line RC-2 only |
| Offline unit tests | `python3 -m pytest tests/test_session63_rc2_authorization.py -q` | All pass (TC37 will now FAIL — expected, confirms deployment) |
| Import safety | `python3 -c "from scripts.backfill_daily_prices import _is_excluded"` | No output (no side effect) |
| Benchmark preservation | `python3 -c "from scripts.backfill_daily_prices import _is_excluded; print(_is_excluded('元大台灣50', '0050'))"` | `False` |
| Cron state | `crontab -l` | Unchanged from pre-deployment |
| DB row count | `sqlite3 data/platform.db "SELECT COUNT(*) FROM daily_prices;"` | `534770` (unchanged) |

> **Note on TC37**: After deployment, `test_tc37_no_deployment_executed` WILL fail because the patch has been applied. This is correct behavior — the test is a "not yet deployed" guard. Remove or update TC37 post-deployment.

**What cannot be verified without backfill**:
- Actual reduction in warrant/5-digit-ETF inclusions in future runs
- NULL volume row reduction
- Production data quality improvement

---

## P6. Cron Timing Guidance

The cron runs at `0 16 * * 1-5` (16:00 weekdays, Asia/Taipei).

Recommended deployment window: **Outside 15:30–16:30 Asia/Taipei** to avoid race conditions with cron. Best window: morning hours before market open.

After RC-2 is deployed, the NEXT scheduled cron run will automatically apply the new exclusion logic. No manual trigger is needed. No separate cron authorization is needed for the existing scheduled run to pick up the change.
