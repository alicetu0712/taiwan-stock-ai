# Hybrid Forward Shadow — Off-Device Backup Plan

**Status:** DOCUMENTED (not yet implemented — awaiting approval)  
**Date:** 2026-11-05  
**Risk:** SINGLE_DEVICE_FAILURE_RISK

---

## Current Backup State

All backups reside on the same Mac as the primary database.

| Property | Value |
|---|---|
| DB path | `data/platform.db` |
| Backup dir | `data/backups/` |
| Naming | `platform_YYYYMMDD_HHMMSSz.db.bak` |
| Retention | 7 most recent backups |
| Creation | Before every shadow run (`create_backup()`) |
| Integrity check | `sqlite3.connect(backup_path).execute("PRAGMA integrity_check").fetchone()` |
| Current backup count | 1 (as of 2026-11-05) |

**Risk:** If the Mac is lost, stolen, corrupted, or fails, both the primary DB and all backups are gone. All prospective decisions accumulated are lost.

---

## Options for Off-Device Backup

These options are **NOT yet implemented**. Implementing any requires explicit user approval.

### Option A — Time Machine (macOS built-in)

Configure Time Machine to include the `data/backups/` directory.

- **Pros:** No code changes, automatic, encrypted, versioned
- **Cons:** Requires Time Machine disk attached/accessible
- **Risk mitigation:** Covers hardware failure; not drive failure if same backup disk

### Option B — iCloud Drive Sync

Symlink or move `data/backups/` into `~/Library/Mobile Documents/` (iCloud).

- **Pros:** Automatic offsite, no code changes after setup
- **Cons:** iCloud syncs plaintext SQLite — not encrypted at rest locally
- **Risk mitigation:** Covers device loss/failure; iCloud is Apple-controlled

### Option C — Git LFS or Git annex (private repo)

Push backup files to a private GitHub/GitLab repo using LFS.

- **Pros:** Versioned, offsite, controllable
- **Cons:** Requires git LFS setup; large file storage costs; backup files are ~80 MB each
- **Risk mitigation:** Full audit trail of backup history

### Option D — rclone to cloud storage

Add a cron step: after `create_backup()` succeeds, run `rclone copy data/backups/ remote:bucket/`.

- **Pros:** Flexible provider (S3, Backblaze B2, GCS); cheap storage
- **Cons:** Requires rclone install + cloud credentials in keychain; network dependency
- **Risk mitigation:** Strongest offsite guarantee

---

## Recommendation

Option B (iCloud Drive) is lowest friction for a single-developer local setup.  
Option D (rclone) is most robust if data must survive account loss.

**No action taken until user approves one of the above options.**

---

## Current Acceptable Risk Documentation

The user is aware of SINGLE_DEVICE_FAILURE_RISK. The following mitigations are already in place:

1. 7-backup rolling retention (protects against accidental deletion within device)
2. Integrity check after each backup creation
3. Restore test run manually on 2026-11-05 (rows=21, hashes_match=True)
4. RETROSPECTIVE_RECONSTRUCTION decisions (pre-2026-11-05) can be regenerated from raw API data if needed
5. PROSPECTIVE decisions (post-2026-11-05) cannot be regenerated — this is the high-value data

**Priority escalation trigger:** When PROSPECTIVE decision count exceeds 50, revisit off-device backup option.
