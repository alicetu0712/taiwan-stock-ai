# Non-Trading Day Signal Root Cause — Session 43

## 1. Summary

Session 42 identified that 39.1% (107/274) of forward signals were generated on non-trading days (Oct 09, 10, 11). Session 43 established the root cause: **all 107 signals are model version v6.0**, not v8.0.

## 2. Root Cause by Date

### Oct 09, 2026 — 99 signals

- **Cause**: CALENDAR_HOLIDAY (National Day holiday week — 國慶日補假)
- **Mechanism**: v6.0 cron ran on Oct 08 evening (`locked_at ≈ 2026-10-08`), labeled signals with `trade_date = 2026-10-09` (anticipated next trading session)
- **Why Oct 09 was a holiday**: National Day observance (normally Oct 10; shifted to Oct 09 that year)
- **Execution date**: NULL (no simulated fill)
- **Model version**: v6.0 (100%)

### Oct 10, 2026 — 4 signals

- **Cause**: CALENDAR_HOLIDAY (National Day, 國慶日) + Saturday
- **Mechanism**: v6.0 cron ran on the holiday itself (`locked_at ≈ 2026-10-10`). Signals labeled `trade_date = 2026-10-10`.
- **Why this happened**: v6.0 had no calendar guard for public holidays
- **Execution date**: NULL
- **Model version**: v6.0 (100%)

### Oct 11, 2026 — 4 signals

- **Cause**: WEEKEND (Sunday)
- **Mechanism**: v6.0 cron ran on Saturday Oct 10 and generated signals for the following day (Sunday Oct 11)
- **Execution date**: NULL
- **Model version**: v6.0 (100%)

## 3. Model Version Mismatch

This is the critical finding:

| Signal Dates | Model Version | Non-TD Rate | Remediation |
|-------------|---------------|-------------|-------------|
| Oct 09-11 | v6.0 | 100% | EXCLUDE_FROM_V8_COMPARISON |
| Oct 12-16 | v8.0 | 0% | PASS |

**v8.0 introduced a calendar guard** that prevents signal generation on non-trading days. The v6.0→v8.0 upgrade happened around Oct 12.

After excluding v6.0 signals, the v8.0-strict pool has zero non-trading-day signals.

## 4. Comparison Contamination History

Sessions that used the contaminated pool:

| Session | Action | Impact |
|---------|--------|--------|
| S40 | Used all signals; fill-date grouping mixed v6.0+v8.0 | Overstated comparison evidence |
| S41 | Added 7-cluster signal-date analysis; v6.0 in cluster 1 | +6.49% grand mean included v6.0 alpha |
| S42 | Switched to 5 fill-date clusters; v6.0 in fill Oct 12 cluster | +1.21% still includes v6.0 |
| S43 | Excludes fill Oct 12 cluster (v6.0); strict v8.0 only | +0.81% (3 clusters) |

## 5. Remediation Policy

For all three Oct 09-11 signal dates: **EXCLUDE_FROM_V8_COMPARISON**

Rationale:
1. Different model version (v6.0 ≠ v8.0) → apples-to-oranges comparison
2. Generated on calendar holidays/weekends → not actual market opportunities
3. NULL execution_date → no simulated fill → no real return data

## 6. Post-Remediation Calendar Integrity

After applying the EXCLUDE policy to v6.0 signals:

| Metric | Before (S42) | After (S43 strict) |
|--------|-------------|-------------------|
| Non-TD signal rate | 39.1% | 0% |
| Contaminated clusters | 1/5 | 0/3 |
| Comparable signals | 274 (mixed) | 128 (v8.0 only) |

Guardrail G01 moves from FAIL to CONDITIONAL (calendar source still uses thin days in denominator).
