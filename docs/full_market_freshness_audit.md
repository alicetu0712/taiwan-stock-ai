# Full-Market Freshness Audit

**Date:** 2026-11-05  
**Triggered by:** Session 6 — Full-Market Freshness & Cron Permission Final Check

---

## Current DB State (as of 2026-11-05 ~18:00 Taiwan time)

| Data segment | Max date | Stock count | Notes |
|---|---|---|---|
| 0050 (benchmark ETF) | **2026-11-05** | 567 rows | Manually backfilled via `fetch_daily_price_fugle.py 0050 2026-11-05` |
| Non-0050 stocks | **2026-11-04** | 6,956 stocks | TWSE STOCK_DAY_ALL API not yet returned 11-05 data |
| `hybrid_forward_decision` | — | 21 decisions | All `RETROSPECTIVE_RECONSTRUCTION` (no PROSPECTIVE yet) |

**Gate verdict for 2026-11-05:** `BENCHMARK_ONLY_UPDATED` → `BLOCKED_PARTIAL_MARKET`

This is the **expected and correct behavior**: 0050 was backfilled manually, but the full-market API data hasn't arrived. The gate correctly blocks prospective decisions in this state.

---

## Why 0050 and Non-0050 Arrive at Different Times

```
Taiwan market close: 13:30
         ↓
TWSE processes closing data
         ↓
~15:30–16:00: STOCK_DAY_ALL API available (all ~1,750 TWSE stocks)
         ↓
~16:00+: Cron wakes up (cron 0 16 * * 1-5)
         ↓
Backfill: fetch 0050 individually (fast, usually available early)
          + fetch STOCK_DAY_ALL batch (all stocks)
         ↓
Full-Market Gate: check both benchmark AND non-0050 count
```

The manual 0050 backfill on 11-05 tested only the individual stock path. The cron pipeline on a live trading day will fetch both simultaneously — the gate ensures both succeed before allowing prospective decisions.

---

## Market Coverage Breakdown

**2026-11-04 (last full trading day):**

| Segment | Count | Date |
|---|---|---|
| 0050 | 1 (567 rows) | 2026-11-04 |
| Non-0050 in daily_prices | 6,956 | 2026-11-04 |
| Stocks in `stocks` table (TWSE only) | 826 | — |
| Stocks in daily_prices NOT in stocks table | 6,237 | — |

The `daily_prices` table contains ETFs, TPEx stocks, and other instruments not in the `stocks` table. The gate counts all non-0050 entries in `daily_prices` to get full market coverage.

**2026-11-05 (current — BENCHMARK_ONLY_UPDATED):**

| Segment | Count | Date |
|---|---|---|
| 0050 | 1 (567 rows) | 2026-11-05 |
| Non-0050 in daily_prices | 0 | 2026-11-05 |

---

## Gate History

| Date | FreshnessStatus | non-0050 count | Action |
|---|---|---|---|
| 2026-11-04 | FULL_MARKET_FRESH | 6,956 | Would allow prospective |
| 2026-11-05 | BENCHMARK_ONLY_UPDATED | 0 | BLOCKED_PARTIAL_MARKET |

---

## Cron Simulation Result (2026-11-05)

Ran `python3 scripts/hybrid_shadow_cron.py --execute` (manual test):

```
Step 4b: check_market_freshness(today=2026-11-05, is_trading_day=True)
  → FreshnessStatus.BENCHMARK_ONLY_UPDATED
  → result["status"] = "BLOCKED_PARTIAL_MARKET"
  → exit code 0 (clean exit, expected condition)
```

Shadow runner was **not invoked** — zero risk of partial-data prospective decisions.

---

## Conclusion

The full-market freshness gate is working correctly. The system is **fail-closed** on partial market data. When the cron runs live at 16:00 Taiwan on a full trading day, it will see `FULL_MARKET_FRESH` (non-0050 count ≥ 1,000) and proceed to the shadow runner.
