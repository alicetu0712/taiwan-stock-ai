# Calendar & 20D Readiness — Session 54

**Calendar Verdict**: CALENDAR_E2E_VERIFIED (unchanged from S52/S53)
**20D Verdict**: TWENTY_D_NOT_READY

## 20D Maturity Matrix

| Fill Date | 20TD Exit Date | Missing Window Dates | Pipeline Complete |
|-----------|---------------|---------------------|-------------------|
| 2026-10-13 | **2026-11-12** | Nov06, Nov09, Nov10 | ✗ |
| 2026-10-14 | 2026-11-13 | Nov06, Nov09, Nov10 | ✗ |
| 2026-10-16 | 2026-11-17 | Nov06, Nov09, Nov10 | ✗ |
| 2026-10-21 | 2026-11-20 | Nov06, Nov09, Nov10 | ✗ |
| 2026-10-22 | 2026-11-23 | Nov06, Nov09, Nov10 | ✗ |
| 2026-10-28 | 2026-11-25 | Nov06, Nov09, Nov10 | ✗ |

All 6 clusters: `auth02_pending=True`, `ready=False`.

## Critical Deadline

**2026-11-12** is the earliest 20TD maturity date (Oct13 cluster). This is NOT a hard deadline for data recovery:
- Nov12 is the earliest MATURITY date — if data is backfilled before Nov12, the 20D outcome can still be computed.
- Nov12 is NOT the date after which data is permanently unavailable — market data for Nov06/09/10 remains retrievable via TWSE single-stock API.
- Urgency: HIGH, but framed correctly as "earliest outcome window opens" not "data permanently lost."

## Canonical Constants (S54 — unchanged from S53)

```
CANONICAL_FILL_DATES = [
    "2026-10-13", "2026-10-14", "2026-10-16",
    "2026-10-21", "2026-10-22", "2026-10-28"
]

CANONICAL_20TD_EXITS = {
    "2026-10-13": "2026-11-12",
    "2026-10-14": "2026-11-13",
    "2026-10-16": "2026-11-17",
    "2026-10-21": "2026-11-20",
    "2026-10-22": "2026-11-23",
    "2026-10-28": "2026-11-25",
}
```

## Calendar E2E Verification (from S52/S53)

- TaiwanTradingCalendar SSOT: verified (S42)
- Canonical fill dates: Oct13/14/16/21/22/28 (Oct27 NOT a fill date — corrected S52)
- 5TD exit dates verified against TradingCalendar
- Dedup-by-trading-days confirmed correct

## Module

`src/research/baseline_fingerprint_reconciliation_s54.py` — PART G
