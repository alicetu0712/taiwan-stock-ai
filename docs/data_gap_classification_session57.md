# Data Gap Classification — Session 57

**Session ID**: S57  
**Date**: 2026-11-10

---

## Classification Summary

| Date | Rows | Classification | Ordinary | ETF | Warrants | Vol Null | S50 Records |
|------|------|----------------|----------|-----|----------|----------|-------------|
| 2026-10-08 | 1 | HISTORICAL_BACKFILL | 0 | 1 | 0 | 0 | 1 (2330 close) |
| 2026-10-15 | 1 | HISTORICAL_BACKFILL | 0 | 1 | 0 | 0 | 1 |
| 2026-10-19 | 1 | HISTORICAL_BACKFILL | 0 | 1 | 0 | 0 | 1 |
| 2026-10-20 | 1 | HISTORICAL_BACKFILL | 0 | 1 | 0 | 0 | 1 |
| 2026-10-27 | 1 | HISTORICAL_BACKFILL | 0 | 1 | 0 | 0 | 1 |
| 2026-10-29 | 1 | BENCHMARK_ONLY | 0 | 1 | 0 | 0 | **6** |
| 2026-10-30 | 1 | BENCHMARK_ONLY | 0 | 1 | 0 | 0 | 2 |
| 2026-11-02 | 1 | BENCHMARK_ONLY | 0 | 1 | 0 | 0 | 1 |
| 2026-11-03 | 1 | BENCHMARK_ONLY | 0 | 1 | 0 | 0 | 1 |
| 2026-11-04 | 6957 | PARTIAL_COVERAGE | 1969 | 159 | 4829 | 5715 | 0 |
| 2026-11-05 | 6589 | PARTIAL_COVERAGE | 1967 | 159 | 4463 | ~4463 | 0 |
| 2026-11-06 | 0 | DATE_MISSING | 0 | 0 | 0 | 0 | 2 (close only) |
| 2026-11-09 | 0 | DATE_MISSING | 0 | 0 | 0 | 0 | 2 (close only) |

**Focus window** (AUTH01 scope): Oct29/30/Nov02/03/Nov06/09

---

## Classification Definitions

**HISTORICAL_BACKFILL**: Oct08–Oct27 (outside primary focus window). 1 row = 0050
benchmark only. These dates predate the pipeline incidents under investigation.

**BENCHMARK_ONLY**: Oct29/30/Nov02/03. 1 row = 0050 (ETF benchmark). No ordinary stocks.
Root cause RC-05: pipeline ran but only fetched benchmark.

**PARTIAL_COVERAGE**: Nov04/05. Rows exist (6957/6589) but contaminated by:
- Warrant rows (4829/4463): 7xx and 02x prefix, NOT ordinary stocks
- TPEx volume NULL (5715/4463): structural limitation of TPEx bulk endpoint
- 881 ordinary stocks with null/zero volume on Nov04 (suspended/low-liquidity)

**DATE_MISSING**: Nov06/09. Zero rows. Root cause RC-04: SCHEDULER_NOT_TRIGGERED.
S50 research snapshots confirm these were valid trading days (2330/2454 have close data).

---

## S50 Research Snapshots Available

| Date | Stock | Open | High | Low | Close | Volume | Quality |
|------|-------|------|------|-----|-------|--------|---------|
| Oct29 | 2330 | 2420.0 | 2425.0 | 2390.0 | 2415.0 | 18403916 | FULL_OHLCV_V |
| Oct29 | 2454 | 4205.0 | 4225.0 | 4000.0 | 4045.0 | 6867223 | FULL_OHLCV_V |
| Oct29 | 2317 | 250.0 | 253.5 | 247.0 | 248.0 | 21358260 | FULL_OHLCV_V |
| Oct29 | 2891 | 74.5 | 76.2 | 74.1 | 75.3 | None | OHLCV_NO_V |
| Oct29 | 6505 | 102.5 | 103.0 | 98.5 | 98.6 | None | OHLCV_NO_V |
| Oct29 | 3008 | 6315.0 | 6315.0 | 5815.0 | 5815.0 | None | OHLCV_NO_V |
| Oct30 | 2330 | 2380.0 | 2380.0 | 2360.0 | 2370.0 | 36615931 | FULL_OHLCV_V |
| Oct30 | 2454 | 3820.0 | 3990.0 | 3805.0 | 3915.0 | 13044171 | FULL_OHLCV_V |
| Nov02 | 2330 | 2310.0 | 2345.0 | 2310.0 | 2330.0 | 41165068 | FULL_OHLCV_V |
| Nov03 | 2317 | 249.0 | 250.0 | 243.5 | **245.5** | 44139321 | FULL_OHLCV_V |
| Nov06 | 2330 | — | — | — | 2135.0 | None | CLOSE_ONLY |
| Nov06 | 2454 | — | — | — | 3390.0 | None | CLOSE_ONLY |
| Nov09 | 2330 | — | — | — | **2235.0** | None | CLOSE_ONLY |
| Nov09 | 2454 | — | — | — | 3725.0 | None | CLOSE_ONLY |

**Corrections from S55/S56**:
- Nov03 2317 close: 245.5 (not 245.0 as documented in S55/S56)
- Nov09 2330 close: 2235.0 (not 2200.0 as documented in S56)
- Oct29 count: 6 records (not 3 as S55 documented; S55 used CLOSE_ONLY subset)

---

## Recovery Priority Tiers

| Priority | Dates | Reason |
|----------|-------|--------|
| P1 — AUTH01 scope | Oct29/30/Nov02/03 | PRIMARY gap dates for V3 research signals |
| P2 — missing | Nov06/09 | DATE_MISSING; SCHEDULER_NOT_TRIGGERED |
| P3 — historical | Oct08/15/19/20/27 | Pre-incident; lower priority |
| Existing | Nov04/05 | Rows present; warrants excluded from analysis |

---

## Coverage Before / After (Partial S50 Insert)

For AUTH01 scope (using S50 research snapshots only, no T2 recovery):

| Date | Before | S50 Rows | Coverage | QG Impact |
|------|--------|----------|----------|-----------|
| Oct29 | 1 (0050) | 6 stocks | 6/1969 = 0.30% | NO_CHANGE |
| Oct30 | 1 (0050) | 2 stocks | 2/1969 = 0.10% | NO_CHANGE |
| Nov02 | 1 (0050) | 1 stock | 1/1969 = 0.05% | NO_CHANGE |
| Nov03 | 1 (0050) | 1 stock | 1/1969 = 0.05% | NO_CHANGE |

No Quality Gate changes from partial S50 insert alone.
Full recovery (T2 single-stock) would achieve ~100% coverage.
