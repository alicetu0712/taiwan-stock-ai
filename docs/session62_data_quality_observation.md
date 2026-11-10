# Session 62 — Data Quality Observation Plan

## Scope

Define how to observe the effect of each RC patch without executing production backfill.
Pre-deployment observations use unit tests and frozen fixtures. Post-deployment observations
require authorized backfill execution (AUTH required separately).

**No production backfill was executed in Session 62.**

---

## Observation Plan

| RC | Phase | Metric | Baseline | Target | Method | Window | Failure Threshold | Requires Backfill | Observable Without Backfill |
|----|-------|--------|----------|--------|--------|--------|-------------------|:-----------------:|:---------------------------:|
| RC61-01 | Pre-deployment | `summary["errors"]` captures TPEx date mismatch | 0% — mismatches go to `print()` only | 100% — mismatches in `summary["errors"]` | Static code inspection + unit test (TC in S61) | Immediate | Asymmetric handling confirmed before deployment | No | Yes |
| RC61-01 | Post-deployment | Error list populated on first dry-run with known mismatch date | Mismatch not in errors | Mismatch in errors | `python scripts/backfill_daily_prices.py` (no `--execute`), inspect return value | First dry-run after deployment | `summary["errors"]` unchanged on mismatch date → patch not applied | No | Yes |
| RC61-02 | Pre-deployment | `_is_excluded()` behavior for 6-digit and 5-digit pure-numeric IDs | `700022` returns `False` (BUG); `2330` returns `False` (correct) | `700022` returns `True`; `2330` returns `False` | S61 eligibility test cases (simulation) | Immediate | Any TWSE/TPEx ordinary stock (4-digit) incorrectly excluded | No | Yes |
| RC61-02 | Post-deployment | New `len>4` rows in `daily_prices` after deploy date | BASELINE_UNAVAILABLE — historical warrants already present | 0 new `len>4` rows for dates after deployment | `SELECT COUNT(*) FROM daily_prices WHERE LENGTH(stock_id)>4 AND date > 'DEPLOY_DATE'` | First 3 backfill runs after AUTH authorized + `--execute` | >0 new `len>4` rows → patch not effective | Yes | No |
| RC61-03 | Pre-deployment | `TradingShares` field parsing via frozen S58 fixture | `TradeVolume` absent in TPEx API → `NULL` volume | `TradingShares` present → non-NULL volume | S61 volume test V01: `TradingShares=89094382` → `89094.382` 千股 | Immediate | V01 produces NULL after patch → field not changed | No | Yes |
| RC61-03 | Post-deployment | TPEx ordinary stock NULL volume rate for new backfill dates | 100% NULL for 21,846 historical rows; 100% NULL for new rows (before patch) | <1% NULL for new TPEx ordinary stocks after deployment | `SELECT COUNT(*), SUM(CASE WHEN volume IS NULL THEN 1 ELSE 0 END) FROM daily_prices WHERE date > 'DEPLOY_DATE' AND LENGTH(stock_id)=4` | First 3 TPEx backfill runs after AUTH + `--execute` | >5% NULL rate for new ordinary stocks → field still wrong | Yes | No |

---

## Pre-deployment Observation Evidence

All pre-deployment observations are executable without backfill:

```
python -m pytest tests/test_session61_release_candidates.py -k "rc1 or rc2 or rc3" -v
```

Key frozen fixtures:
- **V01** (RC-3): `{"TradingShares": "89094382", "Open": "241"}` → volume = 89094.382 千股.
  Source: S58 live probe, 2317/Nov06. Encodes confirmed TPEx field name.
- **E01** (RC-1): `api_date="2026-10-29", target="2026-11-05"` → `summary["errors"]` contains
  mismatch message after patch.

---

## Guardrails — 20D / AUTH02 / TWSE

### 20D Outcomes

Canonical fill dates: Oct13, Oct14, Oct16, Oct21, Oct22, Oct28.

| Cluster | Signals | Exit Window | Status |
|---------|---------|-------------|--------|
| Oct13-16 | 1,091 | ~Nov12-16 | DATA_BLOCKED (exit > DB max Nov05) |
| Oct21-22 | 563 | ~Nov19-21 | NOT_YET_MATURE |
| Oct28 | 323 | ~Nov26-Dec01 | NOT_YET_MATURE |

AUTH02 NOT_AUTHORIZED. No new 20D outcomes computed in Session 62.

### TWSE Historical Backfill

- PIT Universe: 720 candidates (Aug2026+), 717 on Nov05.
- Estimated requests: 1,440 stock-months.
- T2 compliance: UNVERIFIED.
- AUTH01 NOT_AUTHORIZED.

No large-scale TWSE requests issued in Session 62.

### Prospective Collection

- Genuine V3 Prospective N=0.
- G03: FAIL. G04: STRUCTURAL_FAIL.
- V3 Activation: BLOCKED.
- No prospective collection activities performed in Session 62.

---

## DQ Verdict

**DQ_ACCEPTANCE_PARTIAL**

Pre-deployment metrics: all pre-deployment observations are verifiable via unit tests and
static analysis without backfill execution. These are PASS.

Post-deployment metrics: require authorized backfill execution. Cannot be verified until
user grants AUTH-RC61-XX and explicitly runs `--execute`. These remain PENDING.

No QG thresholds lowered. Coverage improvement from RC-2 is reclassification only, not new
data recovery.

---

## Limitations

- Post-deployment SQL queries are specifications — not executed in this session.
- Baseline for RC-2 post-deployment metric is BASELINE_UNAVAILABLE because historical
  warrant/ETF rows already exist in `daily_prices`; only the absence of NEW len>4 rows
  can be measured.
- RC-3 historical 21,846 NULL rows remain NULL after code deployment (parser fix only
  affects future fetches).

---

## Next Action

Pre-deployment observations are complete. Post-deployment observations require:
1. User grants AUTH-RC61-XX for each desired RC.
2. Apply exact diff.
3. Run `python scripts/backfill_daily_prices.py` without `--execute` (dry-run) first.
4. If dry-run clean, run with `--execute` for actual write.
5. Execute post-deployment SQL queries to confirm DQ metrics.
