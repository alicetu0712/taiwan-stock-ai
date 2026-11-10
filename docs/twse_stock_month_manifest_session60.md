# TWSE Stock-Month Manifest — Session 60

## Purpose

The stock-month manifest records the specific (stock_id, month) pairs that need to be fetched via the TWSE single-stock monthly API (T2 endpoint) to fill the Oct29–Nov09 data gap. The full manifest contains 1,440 entries (720 stocks × 2 months). Only 5 entries have been pilot-verified (Session 58).

## Pilot-Verified Entries (5 of 1,440)

All entries have status **AUTH01_PENDING**. None have been fetched for production insertion.

| stock_id | Month | Label | Source Session | OHLCV Verified | Volume Verified | Key Evidence |
|----------|-------|-------|----------------|----------------|-----------------|--------------|
| 2330 | 202610 | October 2026 | S58 P01 | Yes | Yes | Oct29: O=2420/H=2425/L=2390/C=2415/V=18.4M; Oct30: O=2380/C=2370/V=36.6M |
| 2454 | 202610 | October 2026 | S58 P03 | Yes | Yes | Oct29: O=4205/H=4225/L=4000/C=4045/V=6.9M |
| 1301 | 202610 | October 2026 | S58 P04 | Yes | Yes | Oct29: O=75.3/H=76.1/L=73.8/C=73.9/V=19.1M |
| 2317 | 202611 | November 2026 | S58 P02 | Yes | Yes | Nov03 close=245.5 CONFIRMED; Nov06/09 full OHLCV present |
| 2882 | 202611 | November 2026 | S58 P05 | Yes | Yes | Nov02: O=117/C=116/V=28M; Nov03: O=116/C=113/V=30M |

## Full Manifest Scope

- **720 stocks** eligible (Aug2026+ TWSE, 4-digit, in stocks table)
- **2 months:** October 2026 (202610) and November 2026 (202611)
- **1,440 total API calls** at 2-second intervals → ~48 minutes runtime
- Deduplication: each (stock_id, month) pair fetched once; months map to calendar month boundaries

## Gap Dates Covered

The two months cover the following gap dates confirmed absent from `daily_prices`:

| Month | Gap Dates |
|-------|-----------|
| October 2026 | Oct29, Oct30 |
| November 2026 | Nov02, Nov03, Nov06, Nov09 |

## Authorization Requirements

**AUTH01** is required before executing any T2 API calls. The five pilot entries demonstrate the endpoint returns valid OHLCV data and the data is insertion-ready, but AUTH01 has not been granted.

**T2 compliance status:** UNVERIFIED. TWSE terms pages returned 404/Swagger during S58 investigation. No explicit rate limit was observed in the 5 pilot probes, but this does not constitute verified compliance.

## What This Manifest Does NOT Cover

- TPEx ordinary stocks: T2 endpoint is TWSE-only. No equivalent per-stock historical endpoint exists for TPEx bulk data.
- SET-A/SET-B (warrants/ETFs): Recovery not needed; these should be excluded, not repaired.
- SET-D (stock 6423): Source data anomaly; not fixable via T2 fetch.
