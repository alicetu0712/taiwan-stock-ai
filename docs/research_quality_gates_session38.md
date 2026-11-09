# Research Universe Quality Gates — Session 38

**Date:** 2026-11-08  
**Session:** 38  
**Gate Version:** v1.0  
**Overall Verdict:** `FAIL`

---

## 1. Quality Gate Summary

| Check | Name | Verdict | Key Finding |
|---|---|---|---|
| QG-01 | Official classification coverage | PASS | 410/410 FS v8.0 stocks classified by official source |
| QG-02 | ETF contamination in v8.0 ForwardSignals | **FAIL** | 9.52% (213/2236) confirmed by official TWSE/TPEx cross-reference |
| QG-03 | TPEx common stock inclusion | **FAIL** | 0 of 897 TPEx stocks in ForwardSignals; 895 present as orphans only |
| QG-04 | Survivorship bias (delisted stocks) | **FAIL** | 99 probable delistings; 0 explicit delisted_date records; 3 confirmed mid-era |
| QG-05 | Train-test universe alignment | **FAIL** | 48% master coverage; ETF present in forward, absent in training |
| QG-06 | TWSE stock master completeness | **FAIL** | 65.1% coverage; 314 pre-existing TWSE stocks missing |
| QG-07 | source_price_date populated | UNVERIFIED | Exists in schema; population rate not fully verified |
| QG-08 | Point-in-time universe | **FAIL** | No listing_date filter; look-ahead bias unquantified |
| QG-09 | Corporate action adjustment | UNVERIFIED | Adjustment status not documented |
| QG-10 | ForwardSignals count reconciliation | PASS | COUNT_RECONCILED (Session 37) |
| QG-11 | DailyPrice coverage on signal dates | CONDITIONAL | 48% master on Oct 12–28; insufficient |
| QG-12 | Genuine prospective evidence | **FAIL** | 0 prospective decisions; all 21 RETROSPECTIVE_RECONSTRUCTION |

**Score: 2 PASS, 1 CONDITIONAL, 7 FAIL, 2 UNVERIFIED**  
**Overall: FAIL (≥ 5 individual FAIL checks)**

---

## 2. PASS Checks

### QG-01: Official Classification Coverage — PASS

All 410 unique stock_ids in FS v8.0 were classified using official TWSE and TPEx OpenAPI data.
No unclassifiable stock_ids remain. Classification is 100% complete by official source.

**Threshold met**: 100% classification coverage.

### QG-10: ForwardSignals Count Reconciliation — PASS

2605 total = 2236 v8.0 (is_valid=True) + 369 v6.0 (is_valid=False).
No duplicates confirmed. See Session 37 reconciliation document.

---

## 3. FAIL Checks (High Priority)

### QG-02: ETF Contamination — FAIL

- **Finding**: 213/2236 = 9.52% of v8.0 signals are from confirmed ETF securities
- **Threshold**: < 1% contamination
- **Official evidence**: 42 stock_ids (all 0-prefix) confirmed NOT in TWSE/TPEx common stock APIs
- **Remediation**: Filter signal generation by `security_type != ETF` using `SecurityClassificationService`

### QG-03: TPEx Inclusion — FAIL

- **Finding**: 0 of 897 TPEx common stocks in ForwardSignals; 895 present in daily_prices as orphans
- **Threshold**: TPEx either present or explicitly excluded by design decision
- **Issue**: TPEx exclusion was never documented as intentional; it is a silent omission
- **Remediation**: Either (a) load TPEx stocks and retrain, or (b) document TPEx exclusion policy

### QG-04: Survivorship Bias — FAIL

- **Finding**: 99 stocks in master not in current TWSE API; 0 `delisted_date` records; 3 confirmed delistings (2867, 6806, 6288)
- **Threshold**: Delistings documented and handled
- **Remediation**: Add `delisted_date` column; load historical TWSE delisting data

### QG-05: Train-Test Universe Alignment — FAIL

- **Finding**: SIGNIFICANT_MISMATCH (stock count ratio 57%, ETF delta 9.5%, orphan TWSE introduced)
- **Threshold**: ≥ 70% overlap, < 5% ETF rate change
- **Remediation**: Fix DailyPrice pipeline for Oct 2026 dates; apply ETF filter

### QG-06: TWSE Master Completeness — FAIL

- **Finding**: 65.1% TWSE coverage; 314 pre-existing stocks missing; 0% TPEx
- **Threshold**: ≥ 95% TWSE coverage
- **Remediation**: Load 314 missing TWSE stocks; decide on TPEx policy

### QG-08: Point-in-Time Universe — FAIL

- **Finding**: No listing_date filtering; stocks available after backtest start could appear in earlier signals
- **Threshold**: Backtest uses only stocks listed before signal date
- **Remediation**: Extract TWSE listing dates; add filtering to backtest engine

### QG-12: Genuine Prospective Evidence — FAIL

- **Finding**: 0 of 21 decisions are genuinely prospective; all computed retroactively on 2026-11-05
- **Threshold**: ≥ 1 prospective decision with actual outcome
- **Remediation**: Wait for cron to generate real prospective decisions; first outcome available 2026-12-02

---

## 4. CONDITIONAL Checks

### QG-11: DailyPrice Coverage on Signal Dates — CONDITIONAL

- **Finding**: 394–395 of 826 master stocks (48%) present on Oct 12–28 signal dates
- **Threshold**: ≥ 80% of training-era stock count
- **Actual**: 48% — below threshold but generates usable signals
- **Conditional**: Analysis can proceed with explicit caveat of reduced universe

---

## 5. UNVERIFIED Checks

### QG-07: source_price_date Population

Schema exists; population rate not verified in this session.
Check: `SELECT COUNT(*) FROM forward_signals WHERE model_version='v8.0' AND source_price_date IS NULL`

### QG-09: Corporate Action Adjustment

No documentation found on whether daily_prices are raw or adjusted.
Impact: If raw prices are used, 20d forward returns include dividend distortions.

---

## 6. Gate Consequence

The Research Universe Quality Gate at `FAIL` means:

1. **No activation decision** can be made based on current ForwardSignals
2. **Future signal batches** must use Dataset B (ETF-filtered) as the standard
3. **Performance comparisons** between training and forward phases are UNRELIABLE due to QG-05
4. **Absolute return estimates** from historical backtest are UNRELIABLE due to QG-04, QG-06, QG-08

The gate will upgrade to `CONDITIONAL` when QG-02 (ETF filtering) and QG-05 (universe alignment) are fixed.
Full `PASS` requires all 7 FAIL checks to be resolved.

---

## 7. Priority Remediation Sequence

| Priority | Check | Action Required | Authorization Needed |
|---|---|---|---|
| P1 | QG-02 | ETF filter in signal generation | Code change |
| P1 | QG-05 | Investigate Oct 2026 DailyPrice pipeline | Code investigation |
| P2 | QG-06 | Load 314 missing TWSE stocks | Schema + ETL write |
| P2 | QG-04 | Load delisting data | Schema + ETL write |
| P3 | QG-03 | TPEx policy decision | Architecture decision |
| P3 | QG-08 | Add listing_date to master | Schema migration |
| P4 | QG-12 | Wait for cron + first outcome | Cron authorization |
