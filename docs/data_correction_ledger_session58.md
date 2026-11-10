# Data Correction Ledger — Session 58

**Correction Status**: CORRECTIONS_RECONCILED  
**Date**: 2026-11-10

All 5 corrections have been reconciled across S50 / S57 / S58. Production `daily_prices` is unchanged — these corrections are for the pending INSERT_CANDIDATE manifest, not existing records.

---

## Correction 1: Nov03 2317 Close Price

| Field | Value |
|-------|-------|
| Stock | 2317 鴻海 (Foxconn) |
| Date | 2026-11-03 |
| Original value | 245.0 (S55 _S50_VERIFIED_PRICES) |
| Corrected value | **245.5** |
| Evidence | S50 _VERIFIED_RECORDS (line 124) + S58 P02 direct probe |
| Confidence | HIGH — two independent sources |

S55's `_S50_VERIFIED_PRICES` extracted close-only data with rounding/truncation error. The authoritative S50 `_VERIFIED_RECORDS` and S58 direct endpoint probe both return 245.5.

Error magnitude: 0.5 / 245.0 = **0.2%**

---

## Correction 2: Nov09 2330 Close Price

| Field | Value |
|-------|-------|
| Stock | 2330 台積電 (TSMC) |
| Date | 2026-11-09 |
| Original value | 2200.0 (S56 auth01_impact_simulation_s56.py) |
| Corrected value | **2235.0** |
| Evidence | S50 _VERIFIED_RECORDS (line 134) |
| Confidence | MEDIUM — from S50 source; not independently probed in S58 |

S58 did not independently re-probe 2330/Nov09 (pilot used 2317/2882 for November). The correction stands from S50 source; independently verified in S57.

Error magnitude: 35 / 2235 = **1.6%**

---

## Correction 3: Oct29 Record Count

| Field | Value |
|-------|-------|
| Stocks | multiple |
| Date | 2026-10-29 |
| Original value | 3 stocks (S55/S56: 2330/2454/2317) |
| Corrected value | **6 stocks** (S50: adds 2891/6505/3008) |
| Evidence | S50 _VERIFIED_RECORDS (6 entries); S58 P03 confirms 2454 |
| Confidence | HIGH for count; MEDIUM for volume=None reason on 2891/6505/3008 |

S55/S56 used a manually extracted close-price subset. S50 `_VERIFIED_RECORDS` has 6 Oct29 entries: 2330/2454/2317 with FULL OHLCV+volume; 2891/6505/3008 with OHLC and volume=None.

The volume=None for 3 stocks may reflect a parsing gap (S58 direct probes always returned volume; raw API data may have been parsed incorrectly in S50 for those 3 stocks).

---

## Correction 4: Nov06/09 OHLCV Quality Upgrade

| Field | Value |
|-------|-------|
| Stock | 2317, 2882 |
| Dates | 2026-11-06, 2026-11-09 |
| Original assessment | CLOSE_ONLY (S50 had close only for 2330/2454) |
| Corrected assessment | **FULL_OHLCV_WITH_VOLUME confirmed** |
| Evidence | S58 P02 (2317) and P05 (2882) direct probes |
| Confidence | HIGH — direct S58 probes |

S50 only probed 2330 and 2454 for Nov06/09 — both returned close-only. S58 probed 2317 and 2882 for the same dates — both returned FULL OHLCV+volume. Nov06/09 are NOT inherently close-only dates; S50 coverage was simply limited to 2330/2454.

---

## Correction 5: Recovery Runtime Estimate

| Field | Value |
|-------|-------|
| Scope | All gap dates |
| S57 estimate | ~6.6 hours (1969 calls/date × 6 dates = ~11,814 calls) |
| S58 correction | **~40 minutes** (599 stocks × 2 months = 1,198 calls × 2s) |
| Root cause 1 | Monthly API semantics: 1 call = all trading days in calendar month |
| Root cause 2 | Research universe: 599 four-digit TWSE stocks (not 1969 all ordinary) |
| Confidence | HIGH — confirmed by endpoint verification |

---

## QG Impact

None of these corrections affect Q03/G04 or genuinely prospective decisions. The corrections apply to INSERT_CANDIDATE manifest entries pending AUTH01 authorization.

**Canonical V2 fingerprint**: `6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f` — UNCHANGED.
