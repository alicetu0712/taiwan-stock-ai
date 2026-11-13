# Session 71P — Backup Evidence

**Session**: 71P  
**Verdict**: `BACKUP_VERIFIED`

---

## Backup Directory

```
backups/session71p_20261113_013432/
```

Named with Session ID + Asia/Taipei timestamp.

---

## Files Backed Up

| File | Backup Name | Original Path | Backup SHA256 | Readable | Parseable |
|---|---|---|---|---|---|
| `backfill_daily_prices.py` (pre-deploy) | `backfill_daily_prices.py.orig` | `scripts/backfill_daily_prices.py` | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | ✓ | ✓ |

**Note**: Guard module (`scheduler_safety_guards.py`) not backed up separately — it was not modified during Deploy A (verify-only). It was already in production and its hash was unchanged.

---

## Backup Verification

| Check | Result |
|---|---|
| File exists in backup dir | ✓ |
| SHA256 of backup matches pre-deploy production | `4eb6eacf...` ✓ MATCH |
| File size | 24,546 bytes |
| Original permissions preserved (`-p` flag in cp) | ✓ `-rw-r--r--` |
| Original modification time | 2026-11-11 00:46 |
| Backup readable | ✓ (23,384 chars) |
| Backup parseable (ast.parse) | ✓ |
| Existing backups not overwritten | ✓ (new timestamped dir) |

---

## Rollback Procedure (Verified)

```bash
# Step 1: Confirm no active backfill
ps aux | grep backfill_daily_prices | grep -v grep

# Step 2: Restore from backup
cp -p backups/session71p_20261113_013432/backfill_daily_prices.py.orig \
       scripts/backfill_daily_prices.py

# Step 3: Verify restored hash
sha256sum scripts/backfill_daily_prices.py
# Expected: 4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb

# Step 4: Verify wrapper unchanged
sha256sum scripts/hybrid_shadow_cron.py
# Expected: 46209171...

# Step 5: Verify crontab unchanged
crontab -l
```

The restore procedure is executable without additional downloads, network access, or git operations. The backup contains the full original file content.
