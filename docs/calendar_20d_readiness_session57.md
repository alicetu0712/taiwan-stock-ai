# Calendar & 20D Readiness — Session 57

**Session ID**: S57  
**Date**: 2026-11-10  
**Status**: CALENDAR_VERIFIED | 20D_NOT_READY (AUTH02 not authorized)

---

## TaiwanTradingCalendar_v1 Status

**Verified**: E2E tests pass (S56). Calendar service confirmed operational.
**Pipeline integration**: Not yet wired into daily pipeline pre-flight (design only in HC-05).
**Gap date confirmation**: S50 research data confirms Nov06/09 were valid trading days.

---

## 20D Window Status

| Cluster | Signal Dates | Execution Dates | Maturity (20TD) | Maturity Calendar |
|---------|-------------|-----------------|----------------|-------------------|
| Oct13 | 1 signal | Oct14 (NEXT_OPEN) | ~Nov12 | **2 trading days from today** |
| Oct22 | Multiple | Oct22–Oct23 | ~Nov19 | 7 trading days |
| Oct28/29 | Multiple | Oct29–Nov03 | ~Nov26–Dec02 | 12–17 trading days |

**AUTH02 not authorized** → 20D computation blocked for all clusters.

---

## Oct13 Urgency

The Oct13 cluster (execution_date=2026-10-14) is the most time-sensitive:
- 20 trading days from Oct14 → maturity ~Nov12
- Today (Nov10) + 2 trading days = Nov12 (expected maturity)
- **Window closes ~Nov12** — after that, Nov12 close price is the final 20D outcome

If AUTH02 is not authorized before Nov12, the Oct13 20D measurement must still be taken
after maturity (using the Nov12 close price retrospectively), but the window is now live.

---

## Canonical V2 Fingerprint

**Unchanged from S55/S56**: `6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f`

This fingerprint uses `execution_date` field for cluster membership (not `trade_date`).
Two independent verifications in S56 confirmed stability.

---

## Production Integrity Check

No production changes in S57:

| Item | Value | Change |
|------|-------|--------|
| daily_prices max | 2026-11-05 | Unchanged |
| Oct29 non-0050 rows | 0 | Unchanged |
| Crontab hash | 3acaf480cb5dcdd44f40dd9d464955a1 | Unchanged |
| V3 param hash | be43e8ca977d9fdd | Unchanged |
| Canonical V2 FP | 6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f | Unchanged |
| TPEx patch state | PRINT_ONLY_CONFIRMED | Not deployed |

---

## Authorization Summary

| Auth | Purpose | Urgency | Status |
|------|---------|---------|--------|
| AUTH01 | Historical backfill Oct29–Nov09 | MEDIUM | PENDING |
| AUTH02 | 20D outcome computation | **HIGH (Nov12 deadline)** | NOT_AUTHORIZED |
| TPEx patch | Error observability improvement | HIGH (structural permanent failure) | NOT_AUTHORIZED |
| Stage B Cron Probe | V3 genuine prospective | LOW (G03 blocked regardless) | EXPLICITLY_DECLINED (S36) |
