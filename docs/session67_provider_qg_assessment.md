# Session 67 — Provider & Quality Gate Assessment

## Status: QG_UNVERIFIED (no post-RC2 run yet)

---

## 1. Available Evidence

The most recent cron run was 2026-11-10 (BEFORE RC-2 deployment). No post-RC2 provider calls have been made.

---

## 2. Last Known Provider/QG State (from logs, pre-RC2)

| Run Date | TWSE Response | TPEx Response | QG Result | DB Write |
|---|---|---|---|---|
| 2026-11-09 | `api_date=2026-11-06 ≠ target=2026-11-09` | (error) | FAILED × 3 retries | NONE |
| 2026-11-10 | `api_date=2026-11-09 ≠ target=2026-11-10` | (error) | FAILED × 3 retries | NONE |

Pattern: TWSE API returning stale date (`api_date` = prior trading day, not current day). This is a provider-side data freshness issue, not an RC-2 issue.

**Classification**: `PRE_EXISTING_FAILURE` — observed on Nov 9 and Nov 10, both before RC-2 deployment.

---

## 3. Expected Next Run Behavior (Forecast Only)

When the first post-RC2 cron run occurs (expected: Nov 11 or next weekday 16:00 Taiwan time):

| Step | Expected Behavior |
|---|---|
| Provider fetch | TWSE + TPEx API called |
| `_is_excluded()` applied | Per RC-2: `len(sid) > 4` → excluded |
| Warrant IDs (700xxx) | EXCLUDED — len=6 pure-numeric |
| 5-digit ETF IDs (00858) | EXCLUDED — len=5 pure-numeric |
| Ordinary stocks (2330, 0050) | INCLUDED — len=4 |
| QG result | Unknown — depends on `api_date` being correct |
| If QG PASS | New rows inserted to `daily_prices` WITHOUT warrant rows |
| If QG FAIL | No DB write; `PRE_EXISTING_QG_FAILURE` applies |

---

## 4. QG Interaction with RC-2

RC-2 applies `_is_excluded()` DURING parsing, BEFORE QG. This means:
- QG runs on the FILTERED DataFrame (warrants excluded)
- If TWSE returns ~826 eligible stocks (instead of thousands including warrants), QG coverage threshold may be relevant

The `_MIN_COVERED_STOCKS = 5_000` constant (line 568) was noted as a potential edge case in Session 65. However:
- This threshold applies to the RAW API response count, not the filtered count (need to verify)
- Recent QG failures are `api_date` mismatch, not coverage count

**QG behavior post-RC2 can only be verified when a run occurs.**

---

## 5. What to Check After Next Cron Run

```
logs/hybrid_cron.log — look for:

[20xx-xx-xxTxx:xx:xxZ] Hybrid Shadow Cron — EXECUTE
[20xx-xx-xxTxx:xx:xxZ] [backfill] Running: .../backfill_daily_prices.py --execute
[20xx-xx-xxTxx:xx:xxZ] [backfill]   dates_processed : N      ← key metric
[20xx-xx-xxTxx:xx:xxZ] [backfill]   total_inserted  : N      ← new rows
[20xx-xx-xxTxx:xx:xxZ] [backfill]   errors          : ...    ← QG failures
```

Look for absence of warrant IDs (7xxxxx, 00858, 00878) in eligible list.
Compare `total_inserted` with baseline `daily_prices = 534,770`.

---

## 6. Status Declaration

```
QG_UNVERIFIED — no post-RC2 run has occurred
PROVIDER_STATUS_UNVERIFIED — no post-RC2 HTTP calls
```

Pre-existing api_date mismatch may continue. This is `PRE_EXISTING_FAILURE`, not RC-2 regression.
