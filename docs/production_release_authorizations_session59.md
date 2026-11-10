# Production Release Authorization Matrix — Session 59

**Date**: 2026-11-10  
**Overall Status**: ALL ACTIONS PENDING OR BLOCKED

---

## Overview

Five authorization dimensions tracked. None are authorized as of S59. No production systems were modified.

---

## Authorization Matrix

| Auth ID | Purpose | Prerequisite | Status | Window | Risk |
|---------|---------|-------------|--------|--------|------|
| AUTH01 (full T2) | TWSE recovery, 1,424 calls, 712 stocks | Compliance confirmation | NOT_AUTHORIZED | No hard deadline | Rate limit unknown |
| AUTH01 (pilot, 23 records) | Insert 5-stock manifest into daily_prices | None | NOT_AUTHORIZED | No hard deadline | Low — small scope |
| AUTH02 | Oct13-16 20D outcomes (1,091 signals) | daily_prices through Nov12 + AUTH01 | NOT_AUTHORIZED | Closes ~Nov12 (soft) | None — read-then-write |
| TPEx Parser Patch (PP-01/02/03) | Fix warrant exclusion + TradingShares volume + amount field | None | NOT_AUTHORIZED | No deadline | PP-03 is HYPOTHESIS |
| Stage B Cron Probe | V3 genuine prospective collection | — | EXPLICITLY_DECLINED (S36) | — | — |

---

## 10 Layers: Root Cause → Genuine Evidence

| Layer | Description | S59 Status |
|-------|-------------|------------|
| 1 | Root Cause Confirmed | YES — 2 bugs, 129,636 rows |
| 2 | Parser Patch Verified | PARTIAL — PP-01/02 HIGH, PP-03 HYPOTHESIS |
| 3 | Historical Rows Recoverable | PARTIAL — TWSE stocks yes; TPEx ordinary BLOCKED_NO_SOURCE; warrants prefer code fix |
| 4 | Production Deployment Ready | YES (patch ready) — but NOT authorized |
| 5 | Production Deployment Authorized | NO |
| 6 | Historical Data Repair Authorized | NO |
| 7 | Historical Data Repair Executed | NO |
| 8 | Coverage QG Passed | NO — all gap dates FAIL |
| 9 | 20D Data Ready | NO — DATA_BLOCKED (Nov05 max) |
| 10 | Genuine V3 Prospective Evidence Available | NO — Stage B EXPLICITLY_DECLINED (S36) |

Each layer is independent. Completing Layer N does not automatically authorize Layer N+1.

---

## S59 vs S58 Changes

| Item | S58 | S59 |
|------|-----|-----|
| NULL volume count | "5,737" (incorrect) | 129,636 (corrected) |
| Root cause 1 attribution | Warrant volume fix (incomplete) | RC-59-01: warrant exclusion logic bug (107,765) CONFIRMED |
| Root cause 2 attribution | TradingShares field mismatch | RC-59-02: field mismatch (21,846) CONFIRMED |
| Eligible TWSE stocks | 599 | 712 (corrected from live DB) |
| Recovery request budget | 1,198 | 1,424 (corrected) |
| Runtime estimate | ~40 min | ~47 min (corrected) |
| Parser patch scope | 2 changes | 3 changes (PP-03 added, HYPOTHESIS) |
| Authorization status | Unchanged | Unchanged |

---

## Safety Constraints (Verbatim — All Active)

未取得獨立明確授權前，不得：
- 修改正式 Neon
- 修改正式 SQLite
- 修改正式 daily_prices
- 修改正式 forward_signals
- 執行正式 Backfill
- 修補正式 Historical Rows
- 部署 TPEx Error Patch
- 部署 TPEx Parser Patch
- 修改正式 Pipeline / Cron / Scheduler
- 執行 Stage B Cron Probe
- 修改 BTM／FDA／TCC
- 修改 GitHub Actions
- 修改 Production v8.0
- 修改 foe_v1 / Hybrid P1–P4
- 修改 V3 Frozen Parameters
- 啟用 V3 Shadow／Paper／Actual
- 執行新的 20D Return／Alpha／Outcome
- 覆寫 Historical Baseline / Canonical V2
- 將 Retrospective Evidence 當成 Genuine Prospective Evidence
