# Session 68 — Provider, Quality Gate & SQLite Report

## Status: QG_UNVERIFIED (post-RC2) / NO_WRITE_QG_BLOCKED (pre-RC2 runs)

---

## 1. Provider Evidence from Existing Logs (G1)

No new provider calls have been made since RC-2 deployment. All evidence below is from pre-RC2 runs.

### Available Log Evidence

| Run Date (CST) | TWSE api_date | Target Date | Mismatch | QG Result | DB Write |
|---|---|---|---|---|---|
| 2026-11-09 16:00 | 2026-11-06 | 2026-11-09 | YES (3 days) | FAILED | NONE |
| 2026-11-09 (retry 1–3) | — | — | — | FAILED | NONE |
| 2026-11-10 16:00 | 2026-11-09 | 2026-11-10 | YES (1 day) | FAILED | NONE |
| 2026-11-10 (retry 1) | 2026-11-09 | 2026-11-10 | YES | FAILED | NONE |
| 2026-11-10 (retry 2) | 2026-11-09 | 2026-11-10 | YES | FAILED | NONE |
| 2026-11-10 (retry 3) | 2026-11-09 | 2026-11-10 | YES | FAILED | NONE |

**Pattern**: TWSE API returning stale `api_date` (prior trading day instead of current day).

### Provider Classification
```
PRE_EXISTING_FAILURE_CONFIRMED
Classification: api_date mismatch — provider-side data freshness issue
RC-2 relationship: UNRELATED — this failure appeared on Nov 9 and Nov 10, 
                   both before RC-2 deployment on Nov 11 00:46 CST
```

### Post-RC2 Provider Status
- Zero post-RC2 HTTP requests made
- `PROVIDER_STATUS_UNVERIFIED` for post-RC2 period

---

## 2. Quality Gate (G2)

### Pre-RC2 QG Evidence

| Check | Nov 9 | Nov 10 | Source |
|---|---|---|---|
| QG executed | YES | YES | hybrid_cron.log |
| QG passed | NO | NO | hybrid_cron.log |
| Failure reason | api_date mismatch | api_date mismatch | hybrid_cron.log |
| Coverage numerator | Unknown | Unknown | Not in log |
| Coverage denominator | Unknown | Unknown | Not in log |
| DB write blocked | YES | YES | "not writing to DB" |

### QG Root Cause Classification (pre-RC2)
```
PRE_EXISTING_FAILURE_CONFIRMED
Failure type: TWSE api_date != target date
Root cause: TWSE provider returning stale date
RC-2 caused: NO — both failures predate RC-2 deployment
```

### Post-RC2 QG Status
```
QG_UNVERIFIED — no post-RC2 cron run has executed
```

### Pre-existing Failure Warning
If the next post-RC2 cron run shows the same `api_date` mismatch:
- **Classification**: `PRE_EXISTING_FAILURE_CONFIRMED` — not a RC-2 regression
- **Action**: Record as separate issue; do NOT rollback RC-2
- **Action**: Do NOT modify QG, Provider, or RC-2 logic

---

## 3. QG Interaction with RC-2 (G2 / F3)

RC-2 applies `_is_excluded()` **during parsing**, before the DataFrame is passed to QG. This means:

1. QG runs on the FILTERED DataFrame (warrants/5-digit ETFs excluded)
2. The QG coverage numerator = eligible stocks that have OHLCV data
3. The QG coverage denominator = ALL eligible stocks after RC-2 filter

**Potential edge case** (noted in S65): `_MIN_COVERED_STOCKS` threshold. If the raw API response count was used as denominator before, and RC-2 reduces the count, coverage percentage might change. However:
- Recent QG failures are `api_date` mismatch, not coverage count failures
- This edge case cannot be verified without a successful post-RC2 run

---

## 4. SQLite Integrity (H1/H2/H3)

### Read-only DB State

| Metric | S66 Baseline | S67 | S68 (Current) | Delta S67→S68 | Status |
|---|---|---|---|---|---|
| `daily_prices` rows | 534,770 | 534,770 | 534,770 | 0 | UNCHANGED |
| `stocks` rows | 826 | 826 | 826 | 0 | UNCHANGED |
| Max trade date | 2026-11-05 | 2026-11-05 | 2026-11-05 | — | UNCHANGED |
| DB Path | `data/platform.db` | Same | Same | — | UNCHANGED |

### Warrant Contamination Check
```sql
-- Query run S68 (read-only):
SELECT COUNT(*) FROM daily_prices
WHERE LENGTH(stock_id) > 4 AND stock_id GLOB '[0-9]*'
AND date > '2026-11-05';
-- Result: 0
```
**Result**: 0 rows — no warrant/5-digit-ETF contamination in any date after 2026-11-05.

**Interpretation**: This result means there are **no new rows at all** after 2026-11-05 (new rows = 0). It does NOT confirm RC-2 filter effect. The count is 0 because no backfill has succeeded, not because warrants were filtered.

### New Rows After 2026-11-05
```sql
SELECT COUNT(*) FROM daily_prices WHERE date > '2026-11-05';
-- Result: 0
```

No new data has been written since RC-2 deployment.

### Write Classification
```
Pre-RC2 period: NO_WRITE_QG_BLOCKED
Post-RC2 period: WRITE_STATUS_UNVERIFIED (no cron run yet)
```

### Data Freshness
```
Max date: 2026-11-05
Missing trading days (approximate): Nov 6, 7, 10, 11
Data lag: ~5 trading days
Cause: PRE_EXISTING_QG_FAILURE blocking all writes since at least Nov 6
```

This data freshness issue is independent of RC-2 and predates it.

---

## 5. Write Authorization Matrix

| Write Type | Authorized | Occurred This Session |
|---|---|---|
| Scheduled cron write (after QG pass) | YES | NO |
| Manual backfill | NO | NO |
| Historical repair | NO | NO |
| Neon ForwardSignals write | NO | NO |
| DB schema change | NO | NO |
| SQLite direct write | NO | NO |

---

## 6. Post-RC2 QG Expected Behavior

**Scenario A: api_date issue resolved**
- QG PASS → new rows inserted for Nov 6, 7, 10, 11
- RC-2 filter removes warrants/5-digit-ETFs from input before QG
- Expected: 0 warrant rows in new data
- Classification: `AUTHORIZED_SCHEDULED_WRITE`

**Scenario B: api_date issue continues**
- QG FAIL → no DB write
- Classification: `NO_WRITE_QG_BLOCKED` + `PRE_EXISTING_FAILURE_CONFIRMED`
- RC-2 rollback: NOT indicated

**Scenario C: New QG failure type emerges**
- Must investigate whether related to RC-2 filter reducing coverage count
- Classification: `ROOT_CAUSE_UNVERIFIED` pending analysis
- Rollback decision: requires evidence RC-2 caused it
