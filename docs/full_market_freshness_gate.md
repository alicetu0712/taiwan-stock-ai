# Full-Market Freshness Gate

**Author:** System  
**Date:** 2026-11-05  
**Status:** ACTIVE (implemented in `src/research/full_market_freshness_gate.py`)

---

## Purpose

The Full-Market Freshness Gate answers one question before each prospective run:

> *Is today's market data complete enough across the full stock universe?*

It is distinct from the two other data quality layers:

| Gate | File | What it checks |
|------|------|----------------|
| DailyPrice Quality Gate | `dailyprice_quality_gate.py` | Content validity (OHLC plausibility, anomalies) |
| OHLC Continuity Gate | `ohlc_continuity_gate.py` | Historical completeness (gap detection, 500-day window) |
| **Full-Market Freshness Gate** | `full_market_freshness_gate.py` | Whether TODAY's data is complete across the full universe |

---

## Motivation

The backfill script fetches 0050 (benchmark ETF) and all TWSE stocks from FUGLE/TWSE APIs. These two datasets arrive on different schedules:

- **0050**: Fetched individually — may succeed even if full-market STOCK_DAY_ALL API returns stale data.
- **Non-0050 stocks**: Fetched via STOCK_DAY_ALL batch API — arrives 15:30–16:00 Taiwan time.

If only 0050 is updated, the old Step 4b (`_get_db_last_date() == today`) would have passed, and the shadow runner would have made prospective decisions based on a universe of **0 stocks** — a silent data failure.

---

## Logic

```
check_market_freshness(conn, trade_date, is_trading_day=None)
```

**Decision tree:**

```
is_trading_day == False?
  └─ MARKET_CLOSED (not blocked — not an error)

0050 max_date < trade_date?
  ├─ is_trading_day == True  → PROVIDER_NOT_READY (blocked)
  └─ is_trading_day == None  → STALE (blocked)

0050 max_date >= trade_date AND non-0050 count == 0?
  └─ BENCHMARK_ONLY_UPDATED (blocked)

0050 max_date >= trade_date AND 0 < non-0050 < 1,000?
  └─ PARTIAL_MARKET_UPDATE (blocked)

0050 max_date >= trade_date AND non-0050 >= 1,000?
  └─ FULL_MARKET_FRESH (passes)
```

---

## Statuses

| Status | is_blocked | Meaning |
|--------|-----------|---------|
| `FULL_MARKET_FRESH` | False | Full universe available. Proceed. |
| `PARTIAL_MARKET_UPDATE` | True | 0050 updated, but < 1,000 non-0050 stocks. |
| `BENCHMARK_ONLY_UPDATED` | True | 0050 updated, non-0050 count = 0. |
| `STALE` | True | 0050 not updated for today (is_trading_day=None). |
| `PROVIDER_NOT_READY` | True | 0050 not updated on a trading day — data not yet published. |
| `MARKET_CLOSED` | False | Non-trading day. Normal exit. |
| `UNKNOWN` | True | DB error or empty DB. |

---

## Threshold: `MIN_COVERED_STOCKS = 1,000`

Taiwan's TWSE lists ~1,750 stocks; TPEx adds another ~800. The threshold of 1,000 is conservative — any day with >= 1,000 non-0050 stock rows has real TWSE market data. A partial batch that delivers < 1,000 stocks indicates a failed or incomplete API response.

Historical baseline: 2026-11-04 delivered **6,956 non-0050 stocks** (well above threshold).

---

## Integration Points

### hybrid_shadow_cron.py (Step 4b)

```python
freshness_report = check_market_freshness(db_conn_check, today, is_trading_day=True)
# FULL_MARKET_FRESH → proceed
# STALE / PROVIDER_NOT_READY → result["status"] = "BLOCKED_STALE_DATA"
# BENCHMARK_ONLY_UPDATED / PARTIAL_MARKET_UPDATE → result["status"] = "BLOCKED_PARTIAL_MARKET"
```

Both `BLOCKED_STALE_DATA` and `BLOCKED_PARTIAL_MARKET` are in `clean_statuses` — cron exits with code 0 (expected condition, not an error).

### run_hybrid_forward_shadow.py (bypass protection)

The shadow runner also calls this gate independently (after OHLC gate, before stock universe fetch). This prevents bypassing the cron pipeline by running the shadow runner directly.

---

## Tests

FM01–FM20 in `tests/test_full_market_freshness_gate.py` (20/20 PASS as of 2026-11-05).

Key integration tests:
- **FM11**: Real DB, 2026-11-05 → `BENCHMARK_ONLY_UPDATED` (0050=11-05, non-0050=0)
- **FM12**: Real DB, 2026-11-04 → `FULL_MARKET_FRESH` (6,956 stocks)
