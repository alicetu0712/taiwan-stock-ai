# Backfill Candidate Manifest & Authorization Gate — Session 50

**Date:** 2026-11-10  
**Session:** S50 — PART C  
**Verdict:** PARTIALLY_READY (sample verified; full 599-stock manifest requires dry-run)  
**AUTH01:** PENDING USER AUTHORIZATION

---

## Overview

The BackfillCandidateManifest formalizes the per-record classification for each verified historical price record. It distinguishes:

| Action | Meaning |
|---|---|
| `INSERT_CANDIDATE` | Record not in DB; source verified; ready to insert |
| `SKIP_EXISTING` | Record already in DB; no conflict |
| `CONFLICT_REVIEW` | Record in DB with different value; requires review |
| `SOURCE_MISSING` | No source data available |
| `VALIDATION_FAILED` | OHLC validation failed |

---

## Sample Records (from S50 real API investigation)

The manifest in this session covers only the **verified sample records** (14–19 records from real API calls). The **full manifest** for 599 stocks × 9 dates requires running backfill_daily_prices.py in dry-run mode.

### Key records from Oct 29 (highest priority, cluster-critical):

| stock_id | name | action | close | ohlc_valid | fingerprint |
|---|---|---|---|---|---|
| 2330 | 台積電 | INSERT_CANDIDATE | 2415.0 | ✓ | sha256[:12] |
| 2454 | 聯發科 | INSERT_CANDIDATE | 4045.0 | ✓ | sha256[:12] |
| 2317 | 鴻海 | INSERT_CANDIDATE | 248.0 | ✓ | sha256[:12] |
| 2891 | 中信金 | INSERT_CANDIDATE | 75.3 | ✓ | sha256[:12] |
| 6505 | 台塑化 | INSERT_CANDIDATE | 98.6 | ✓ | sha256[:12] |
| 3008 | 大立光 | INSERT_CANDIDATE | 5815.0 | ✓ | sha256[:12] |

---

## Transaction Plan

```
For each backfill date (Oct 29/30/Nov 02/03):
  BEGIN TRANSACTION
  For each stock in universe (~599 four-digit stocks):
    INSERT OR IGNORE INTO daily_prices (date, stock_id, close, ...)
    VALUES (?, ?, ?, ...)
  COMMIT
  Verify: SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=? → must be ≥ 300
  If COUNT < 300: flag for review (do NOT rollback committed data)
END
```

**Idempotency guarantee:** `INSERT OR IGNORE` ensures duplicate runs are safe. Second run inserts 0 rows.

**Rollback rule:** Only roll back a transaction if a critical failure occurs (write error, schema violation). Do NOT roll back due to stock count < 300 — that is a coverage issue, not a data corruption issue.

---

## Idempotency Validation (Temp SQLite — S50)

The manifest's idempotency was validated in `tests/test_session50_market_sources.py` TC12:

| Run | Records inserted |
|---|---|
| First run | N (all INSERT_CANDIDATE records) |
| Second run | 0 (all existing, IGNORE triggered) |
| `idempotent` flag | True |

---

## Unresolved Risks

| Risk | Description | Mitigation |
|---|---|---|
| RISK-01 | Only sample records verified; full 599-stock manifest requires dry-run execution | Run `backfill_daily_prices.py --dry-run` before authorizing |
| RISK-02 | TPEx-listed stocks have no bulk historical API | Per-stock TWSE cross-listing check required |
| RISK-03 | Nov 06/09 backfill: pipeline root cause unresolved | Do NOT backfill Nov 06/09 until pipeline is fixed and root cause known |
| RISK-04 | Corporate action adjustments not verified | Assume unadjusted; flag post-backfill |
| RISK-05 | Stock delistings between fill date and today | May cause insert with stock_id not in current universe; verify |

---

## Authorization Gate

| Condition | Status |
|---|---|
| Sample records OHLC verified | ✓ CONFIRMED (14/14 tested) |
| Idempotency proven | ✓ CONFIRMED (second run = 0 inserts) |
| Rollback plan documented | ✓ PRESENT |
| Conflict count (sample) | 0 conflicts in sample |
| Full 599-stock dry-run | ✗ NOT DONE (requires running backfill script) |
| **AUTH01 decision** | **PENDING USER AUTHORIZATION** |

**Next step:** User must authorize AUTH01 to execute full backfill. Command (requires explicit authorization):
```bash
python3 scripts/backfill_daily_prices.py --start 2026-10-29 --end 2026-11-03 --research-only --dry-run
# Review dry-run output, then:
python3 scripts/backfill_daily_prices.py --start 2026-10-29 --end 2026-11-03 --research-only --execute
```

---

## Expected Impact After AUTH01 + P1 Backfill

| Item | Before | After P1 Backfill |
|---|---|---|
| Strict clusters | 3 (Oct 13/14/16) | 6 (all fills) |
| Oct 21 proxy count | 4 | ≥8 |
| Oct 22 proxy count | 3 | ≥7 |
| Oct 28 proxy count | 2 | ≥5 |
| G03 | FAIL (3/10) | FAIL (6/10) |
| G04 | FAIL (structural) | FAIL (unchanged) |

---

## References

- Module: `src/research/market_source_verification_s50.py`
- Functions: `build_backfill_candidate_manifest()`, `validate_manifest_idempotency_in_temp_sqlite()`
- Tests: `tests/test_session50_market_sources.py` TC10–TC15
- Prior: `docs/backfill_authorization_package_s49.md`
