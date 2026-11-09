# Historical Data Source Verification Matrix — Session 49

**Date:** 2026-11-09  
**Session:** S49 — PART B (P1)  
**Verdict:** SOURCE_PARTIAL (9 dates) + SOURCE_UNVERIFIED (2 dates)

---

## Summary

11 backfill candidate dates verified. All 11 are confirmed trading days per TaiwanTradingCalendar.

| Category | Count | Dates |
|---|---|---|
| INSERT_ONLY_CANDIDATE | 9 | Oct 08/15/19/20/27/29/30, Nov 02/03 |
| UNIVERSE_UNVERIFIED | 2 | Nov 06/09 |
| SOURCE_BLOCKED | 0 | — |

---

## TWSE/TPEx API Findings

### TWSE Bulk Historical (STOCK_DAY_ALL?date=YYYYMMDD)
- **Status:** NOT USABLE for historical backfill
- API ignores `date=` parameter; returns current-day data or empty body
- Confirmed: bulk historical endpoint cannot fetch past dates

### TWSE Single-Stock Historical (STOCK_DAY?date=YYYYMMDD&stockNo=XXXX)
- **Status:** SOURCE_PARTIAL — usable but requires per-stock queries
- Returns monthly data for the month containing the requested date
- **TSMC (2330) prices confirmed:**
  - Oct 27: close = 2400
  - Oct 29: close = 2415
  - Oct 30: close = 2370
- Full 655-stock backfill requires ~700 per-stock API calls

### TPEx OpenAPI (?d=RRRMMDD)
- **Status:** NOT USABLE for historical backfill
- `?d=` parameter ignored; returns current-day data (Nov 09, 13674 records)
- TPEx bulk historical cannot be fetched via OpenAPI

### TWSE OpenAPI Current State
- Returns Nov 06 data (api_date=1151106, 1099 four-digit common stock codes)
- **Confirms PROVIDER_NOT_READY root cause** for Nov 09:
  - Pipeline queried on Nov 09 but TWSE OpenAPI returned Nov 06 data
  - api_date mismatch caused PROVIDER_NOT_READY S03 failure

---

## Per-Date Source Verification

| Date | Existing Stocks | Source | Readiness | Affects Cluster? | Conflict Risk |
|---|---|---|---|---|---|
| 2026-10-08 | 1 (0050) | SOURCE_PARTIAL | INSERT_ONLY | No | LOW |
| 2026-10-15 | 1 (0050) | SOURCE_PARTIAL | INSERT_ONLY | No | LOW |
| 2026-10-19 | 1 (0050) | SOURCE_PARTIAL | INSERT_ONLY | No | LOW |
| 2026-10-20 | 1 (0050) | SOURCE_PARTIAL | INSERT_ONLY | No | LOW |
| 2026-10-27 | 1 (0050) | SOURCE_PARTIAL | INSERT_ONLY | No | LOW |
| **2026-10-29** | 1 (0050) | SOURCE_PARTIAL | INSERT_ONLY | **Oct 21** | LOW |
| **2026-10-30** | 1 (0050) | SOURCE_PARTIAL | INSERT_ONLY | **Oct 21/22** | LOW |
| **2026-11-02** | 1 (0050) | SOURCE_PARTIAL | INSERT_ONLY | **Oct 21/22/28** | LOW |
| 2026-11-03 | 1 (0050) | SOURCE_PARTIAL | INSERT_ONLY | Partial | LOW |
| 2026-11-06 | 0 | SOURCE_UNVERIFIED | UNIVERSE_UNVERIFIED | No | HIGH |
| 2026-11-09 | 0 | SOURCE_UNVERIFIED | UNIVERSE_UNVERIFIED | No | HIGH |

---

## Cluster Promotion Requirements

| Fill Date | Current Proxy | Need Backfill | After P1 Backfill |
|---|---|---|---|
| Oct 21 | 4/5 | Oct 29 | STRICT (5+) |
| Oct 22 | 3/5 | Oct 29 + Oct 30 | STRICT (5+) |
| Oct 28 | 2/5 | Oct 29 + Oct 30 + Nov 02 | STRICT (5+) |

**P1 backfill (Oct 29/30/Nov 02/03) → strict count 3 → 6**

---

## Why Nov 06/09 Are Blocked

**Nov 06 (QUALITY_GATE_FAIL):**
- Pipeline ran but QG rejected the entire data batch
- Root cause of QG failure unknown — data was incomplete/corrupted from TWSE
- Cannot safely backfill without understanding what TWSE returned that day
- UNIVERSE_UNVERIFIED — do NOT backfill without QG investigation

**Nov 09 (PROVIDER_NOT_READY):**
- TWSE OpenAPI returned Nov 06 data when queried on Nov 09
- api_date=1151106 (Nov 06) while expected 1151109 (Nov 09)
- S03 fetch failed due to stale provider data
- UNIVERSE_UNVERIFIED — do NOT backfill; Nov 09 data may not be available yet

---

## Safety Constraints

1. **SAFETY-01:** INSERT OR IGNORE — idempotent, never overwrites
2. **SAFETY-02:** Local SQLite only (data/platform.db), NOT Neon
3. **SAFETY-03:** Nov 06/09 blocked until root causes resolved
4. **SAFETY-04:** forward_signals, Cron, v8.0 rules, V3 NOT modified
5. **SAFETY-05:** Use backfill_daily_prices.py with --research-only flag
