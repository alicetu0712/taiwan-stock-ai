# Historical Recovery Manifest — Session 58

**Status**: INSERT_CANDIDATE (all entries)  
**Authorization**: AUTH01_PENDING  
**Date**: 2026-11-10

---

## Manifest Overview

| Date | Records | Full OHLCV+V | Partial | Close-only | In DB |
|------|---------|-------------|---------|-----------|-------|
| 2026-10-29 | 7 | 5 (3 S50 + 2 S58) | 3 | 0 | 0 |
| 2026-10-30 | 3 | 3 (1 S50 + 2 S58) | 0 | 0 | 0 |
| 2026-11-02 | 3 | 3 (1 S50 + 2 S58) | 0 | 0 | 0 |
| 2026-11-03 | 2 | 2 (S58) | 0 | 0 | 0 |
| 2026-11-06 | 4 | 2 (S58) | 0 | 2 (S50) | 0 |
| 2026-11-09 | 4 | 2 (S58) | 0 | 2 (S50) | 0 |
| **Total** | **23** | **17** | **3** | **4** | **0** |

---

## Oct29 Records (7)

| Stock | Name | O | H | L | C | V | Tier | Source |
|-------|------|---|---|---|---|---|------|--------|
| 2330 | TSMC | 2420 | 2425 | 2390 | 2415 | 18.4M | FULL_S50 | S50 |
| 2454 | MediaTek | 4205 | 4225 | 4000 | 4045 | 6.9M | FULL_S58 | S58 P03 |
| 2317 | Foxconn | 250 | 253.5 | 247 | 248 | 21.4M | FULL_S50 | S50 |
| 2891 | CTBC | 74.5 | 76.2 | 74.1 | 75.3 | - | PARTIAL | S50 |
| 6505 | FPCC | 102.5 | 103 | 98.5 | 98.6 | - | PARTIAL | S50 |
| 3008 | Largan | 6315 | 6315 | 5815 | 5815 | - | PARTIAL | S50 |
| 1301 | Formosa | 75.3 | 76.1 | 73.8 | 73.9 | 19.1M | FULL_S58 | S58 P04 |

## Oct30 Records (3)

| Stock | Name | O | H | L | C | V | Tier | Source |
|-------|------|---|---|---|---|---|------|--------|
| 2330 | TSMC | 2380 | 2380 | 2360 | 2370 | 36.6M | FULL_S50 | S50 |
| 2454 | MediaTek | 3820 | 3990 | 3805 | 3915 | 13.0M | FULL_S58 | S58 P03 |
| 1301 | Formosa | 72.2 | 72.8 | 70.3 | 72.5 | 25.2M | FULL_S58 | S58 P04 |

## Nov02 Records (3)

| Stock | Name | O | H | L | C | V | Tier | Source |
|-------|------|---|---|---|---|---|------|--------|
| 2330 | TSMC | 2310 | 2345 | 2310 | 2330 | 41.2M | FULL_S50 | S50 |
| 2317 | Foxconn | 244.5 | 252 | 242.5 | 251 | 49.9M | FULL_S58 | S58 P02 |
| 2882 | Cathay | 117 | 117.5 | 114.5 | 116 | 28.3M | FULL_S58 | S58 P05 |

## Nov03 Records (2)

| Stock | Name | O | H | L | C | V | Tier | Source |
|-------|------|---|---|---|---|---|------|--------|
| 2317 | Foxconn | 249 | 250 | 243.5 | **245.5** | 44.1M | FULL_S58 | S58 P02 |
| 2882 | Cathay | 116 | 116.5 | 112 | 113 | 29.7M | FULL_S58 | S58 P05 |

Note: 245.5 corrects the 245.0 value used in S55/S56.

## Nov06 Records (4)

| Stock | Name | O | H | L | C | V | Tier | Source |
|-------|------|---|---|---|---|---|------|--------|
| 2330 | TSMC | - | - | - | 2135 | - | CLOSE_ONLY | S50 |
| 2454 | MediaTek | - | - | - | 3390 | - | CLOSE_ONLY | S50 |
| 2317 | Foxconn | 213 | 227.5 | 212.5 | 224.5 | 89.1M | FULL_S58 | S58 P02 |
| 2882 | Cathay | 103.5 | 109 | 101 | 106 | 48.7M | FULL_S58 | S58 P05 |

## Nov09 Records (4)

| Stock | Name | O | H | L | C | V | Tier | Source |
|-------|------|---|---|---|---|---|------|--------|
| 2330 | TSMC | - | - | - | **2235** | - | CLOSE_ONLY | S50 |
| 2454 | MediaTek | - | - | - | 3725 | - | CLOSE_ONLY | S50 |
| 2317 | Foxconn | 226.5 | 246 | 226.5 | 239 | 50.4M | FULL_S58 | S58 P02 |
| 2882 | Cathay | 105.5 | 113.5 | 105.5 | 111 | 31.3M | FULL_S58 | S58 P05 |

Note: 2330/Nov09 close corrected to 2235.0 (from S56's 2200.0).

---

## Coverage Simulation

| Date | Before (%) | After Manifest (%) | After Full T2 (%) | QG Before | QG After Full |
|------|-----------|-------------------|------------------|-----------|--------------|
| Oct29 | 0.0% (0/599) | 1.2% (7/599) | ~100% (599/599) | FAIL | PASS_LIKELY |
| Oct30 | 0.0% | 0.5% (3/599) | ~100% | FAIL | PASS_LIKELY |
| Nov02 | 0.0% | 0.5% (3/599) | ~100% | FAIL | PASS_LIKELY |
| Nov03 | 0.0% | 0.3% (2/599) | ~100% | FAIL | PASS_LIKELY |
| Nov06 | 0.0% | 0.7% (4/599) | ~100% | FAIL | PASS_LIKELY |
| Nov09 | 0.0% | 0.7% (4/599) | ~100% | FAIL | PASS_LIKELY |

**Denominator**: 599 (v8.0 research universe — four-digit TWSE stocks). NOT 1969 (all ordinary).

**Conclusion**: Manifest alone is insufficient for QG PASS on any date. Full T2 recovery would achieve PASS. Both require AUTH01.
