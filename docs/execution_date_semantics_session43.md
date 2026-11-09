# Execution-Date Semantics — Session 43

## 1. Overview

Session 43 establishes formal definitions for all date fields in `forward_signals` and explains why `execution_date ≠ trade_date` for signals generated on Oct 14 and Oct 16.

## 2. Date Field Definitions

| Field | Table | Nullable | Definition |
|-------|-------|----------|------------|
| `trade_date` | forward_signals | NOT NULL | The date the cron job labeled as the trading session. May be a holiday/weekend for v6.0 signals. |
| `locked_at` | forward_signals | NOT NULL | UTC timestamp when the signal record was finalized. Represents _when analysis ran_, not when the trade would execute. |
| `execution_date` | forward_signals | NULLABLE | First trading day with stock-specific open price ≥ day after `trade_date`. Computed by NEXT_OPEN pipeline by scanning `daily_prices` per stock. NULL for v6.0 non-trading-day signals. |
| `execution_price` | forward_signals | NULLABLE | Open price on `execution_date`. Simulated fill — not an actual broker execution price. |
| `execution_price_type` | forward_signals | NULLABLE | `'NEXT_OPEN'` for all non-NULL values in Oct 2026. |

## 3. Thin-Day Anomalies

### What is a Thin Day?

A "thin day" is a date in `daily_prices` where fewer than 50 distinct stocks have price data. In Oct-Nov 2026, the following dates are thin:

| Date | Stock Count | Stocks Present | Implication |
|------|-------------|----------------|-------------|
| Oct 15 | 1 | 0050 | EXECUTION_SKIPS_THIS_DAY |
| Oct 19 | 1 | 0050 | EXECUTION_SKIPS_THIS_DAY |
| Oct 20 | 1 | 0050 | EXECUTION_SKIPS_THIS_DAY |
| Oct 27 | 1 | 0050 | EXECUTION_SKIPS_THIS_DAY |
| Oct 29 | 1 | 0050 | EXECUTION_SKIPS_THIS_DAY |
| Oct 30 | 1 | 0050 | EXECUTION_SKIPS_THIS_DAY |
| Nov 02 | 1 | 0050 | EXECUTION_SKIPS_THIS_DAY |
| Nov 03 | 1 | 0050 | EXECUTION_SKIPS_THIS_DAY |

### Why Oct 14 → Oct 16 (not Oct 15)?

The NEXT_OPEN pipeline scans `daily_prices` for each stock:

```
execution_date = MIN(date) FROM daily_prices WHERE stock_id=? AND date > trade_date
```

For common stocks (non-ETF), there is no price row on Oct 15 (0050-only). The first available date after Oct 14 is Oct 16. This is **correct behavior**, not a data error.

### Why Oct 16 → Oct 21 (not Oct 17-20)?

- Oct 17 (Friday): Not in `daily_prices` for common stocks (data gap)
- Oct 18 (Saturday): Weekend
- Oct 19 (Monday): 0050-only thin day
- Oct 20 (Tuesday): 0050-only thin day
- Oct 21 (Wednesday): First date with common stock price data → `execution_date = Oct 21`

## 4. Execution Type Classification

| Type | Definition | Oct 2026 Usage |
|------|-----------|----------------|
| NEXT_OPEN_SIMULATED | Open price on the next available trading day | All 237 non-NULL executions |
| ACTUAL_BROKER | Real broker fill | 0 (none) |
| RETROSPECTIVE | Reconstructed from historical data | 0 (none) |

**All fills in the production database are SIMULATED, not actual broker transactions.** Any performance analysis must acknowledge this distinction.

## 5. NULL Execution Dates

107 signals (all v6.0) have `execution_date = NULL`:

- Oct 09 (99 signals): cron anticipated Oct 09 as next trading day; it was a holiday
- Oct 10 (4 signals): cron ran on National Day itself
- Oct 11 (4 signals): cron generated signals for Sunday

These signals were never executed. They should be excluded from any performance comparison.

## 6. Real Trading Days in Oct-Nov 2026

Using the ≥50-stock threshold (not raw `DISTINCT date FROM daily_prices`):

**14 real trading days**: Oct 01, 02, 05, 06, 07, 12, 13, 14, 16, 21, 22, 28; Nov 04, 05.

This compares to 22 dates returned by `SELECT DISTINCT date FROM daily_prices` (which includes thin days).
