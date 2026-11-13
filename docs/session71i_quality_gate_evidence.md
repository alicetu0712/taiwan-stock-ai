# Session 71I — Quality Gate Evidence

**Document Status**: AWAITING_OBSERVATION  
**Preflight Timestamp**: 2026-11-11 22:06 CST  
**Target Schedule**: 2026-11-12 16:00 CST  
**H3 Status**: H3_PENDING

---

## 1. Quality Gate Architecture (From Code — Pre-verified)

### Stage 1: Scheduler Safety (Wrapper)

| Gate | Location | Description |
|---|---|---|
| FileLock | `hybrid_shadow_cron.py:315` | Exclusive process lock |
| Calendar check | `hybrid_shadow_cron.py:326` | `CALENDAR.is_trading_day(date.today())` |
| Data readiness | `hybrid_shadow_cron.py:337` | Taiwan time ≥ 15:30 CST |

### Stage 2: Data Quality Gates (Backfill)

| Gate | Location | Rule | Failure action |
|---|---|---|---|
| QG-1 | `dailyprice_quality_gate.py` | OHLC: open/close ≤ high ≥ low | Skip date |
| QG-2 | `dailyprice_quality_gate.py` | Price bounds: 0.1 ≤ price ≤ 20,000 | Skip date |
| QG-3 | `dailyprice_quality_gate.py` | Volume ≥ 0 | Skip date |
| QG-4 | `dailyprice_quality_gate.py` | No intra-batch duplicates | Skip date |
| **QG-5** | `dailyprice_quality_gate.py` | `api_date == target_d` | **Skip date (most critical)** |
| QG-6 | `dailyprice_quality_gate.py` | TWSE≥300, TPEx≥50 | Skip date |
| QG-7 | `dailyprice_quality_gate.py` | 0050 present (TWSE) | Skip date |

### Stage 3: Post-write Verification

| Gate | Location | Description |
|---|---|---|
| Freshness gate | `hybrid_shadow_cron.py:376` | `check_market_freshness()`: ≥5000 stocks with today's date |
| Retry policy | Wrapper | 3 retries × 30 min |
| Retryable | — | PROVIDER_NOT_READY, PARTIAL, BENCHMARK_ONLY |

---

## 2. Prior Run QG Evidence (Nov 10 — from log baseline)

The last run provides baseline QG behavior evidence:

```
[2026-11-10T08:34:30Z] QG-5 triggered:
  • 2026-11-10: TWSE api_date=2026-11-09 != target=2026-11-10 → FAILED
  → not writing to DB
[2026-11-10T09:37:32Z] BLOCKED_STALE_DATA (after 3 retries)
```

**QG-5 behavior confirmed in prior runs**: TWSE returned Nov 09 data when queried on Nov 10 → QG-5 blocked the write correctly. This is the same pattern expected on Nov 12 if TWSE data is not yet available.

---

## 3. Gate Execution Order (Confirmed from code)

```
Cron fires at 16:00 CST
  ↓
1. FileLock acquire
2. Calendar: is_trading_day(2026-11-12)? → YES (Wednesday)
3. Data readiness: time ≥ 15:30 CST? → YES (16:00 CST)
   ↓ passes
4. Backfill subprocess
   ├─ _find_missing_dates() → [2026-11-12, 2026-11-11, 2026-11-10, 2026-11-09, 2026-11-06]
   └─ for each date:
       ├─ Fetch TWSE + TPEx
       ├─ QG-1 through QG-7 (per date)
       ├─ RC-2 filter: _is_excluded() → remove 5+ digit stock_ids
       ├─ if QG pass: INSERT OR IGNORE + commit
       └─ if QG fail: skip date, append to errors[]
   ↓ exits 0
5. Post-write freshness gate: check_market_freshness()
   ├─ FULL_MARKET_FRESH (≥5000 stocks today) → continue
   └─ NOT FRESH → retry 3× 30min → BLOCKED_STALE_DATA
   ↓ passes
6. Backup
7. Shadow runner
8. SUCCESS
```

---

## 4. QG Evidence Checklist (PENDING)

| Gate | Expected Result | Actual Result | Verdict |
|---|---|---|---|
| FileLock | ACQUIRED → RELEASED | PENDING | — |
| Calendar (Nov 12) | TRADING_DAY | PENDING | — |
| Data readiness (16:00) | true | PENDING | — |
| QG-5 for Nov 12 | PASS or FAIL (api_date must == 2026-11-12) | PENDING | — |
| QG-5 for Nov 11, 10, 09, 06 | Likely FAIL (TWSE returns latest date) | PENDING | — |
| Post-write freshness | FULL_MARKET_FRESH or BLOCKED | PENDING | — |

---

## 5. Anticipated QG Outcomes

### Scenario A: TWSE returns Nov 12 data at 16:00 CST

| Gate | Result |
|---|---|
| QG-5 for Nov 12 | PASS |
| QG-5 for prior dates | FAIL (api_date will be Nov 12, not Nov 09/10/11) |
| Write | Nov 12 data written; Nov 06/09/10/11 NOT written (QG-5 fail for those dates) |
| Freshness gate | FULL_MARKET_FRESH (Nov 12 data present) |
| Final status | SUCCESS |

### Scenario B: TWSE not ready at 16:00 CST (api_date = Nov 11 or earlier)

| Gate | Result |
|---|---|
| QG-5 for Nov 12 | FAIL (api_date ≠ 2026-11-12) |
| Write | NOTHING written |
| Freshness gate | PROVIDER_NOT_READY |
| Retries | 3 × 30 min |
| Final status | BLOCKED_STALE_DATA |

---

## 6. What "QG FAIL" Means for H3

| Gate Result | H3 Implication |
|---|---|
| QG-5 blocked (Scenario B) | Does NOT indicate RC-2 failure. QG-5 is anti-stale data guard, independent of RC-2. H3 verdict depends on whether cron triggered naturally. |
| QG-5 passed (Scenario A) | Strongest evidence: RC-2 filter ran on passing data |
| Any QG blocked wrong-date data | Shows QG working correctly; H3 PASS still achievable |

---

## 7. Provider API Date (PENDING)

| Item | Value |
|---|---|
| Nov 12 expected api_date | `2026-11-12` (if TWSE published by 16:00) |
| Nov 10 baseline api_date | `2026-11-09` (TWSE returned wrong date) |
| Actual Nov 12 api_date | **PENDING** |

---

## 8. Post-observation Evidence (CONFIRMED)

**Observation timestamp**: 2026-11-12 20:08 CST

### QG results
Pipeline did not execute. No QG ran on Nov 12. Machine was sleeping at 16:00 CST.

---

## 9. Verdict

| Gate | Verdict |
|---|---|
| QG architecture | `VERIFIED` (from static code review) |
| Prior run QG behavior | `VERIFIED` (Nov 10 QG-5 block evidence) |
| Nov 12 QG execution | `NOT_OBSERVED` (pipeline did not trigger) |
| Nov 12 write decision | `NOT_OBSERVED` |
| Post-write verification | `NOT_OBSERVED` |
| **Overall QG Verdict** | **NOT_OBSERVED** (not FAIL) |

---

## 10. Post-Observation Update Instructions

After 2026-11-12 16:05 CST:
```bash
# QG evidence in log
grep -E "(quality gate|QG|api_date|TWSE|BLOCKED|PASS|freshness)" \
  /Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log | tail -30

# Write evidence
sqlite3 /Users/alicetu/Desktop/Antigravity/stock_platform/data/platform.db \
  "SELECT date, COUNT(*) FROM daily_prices WHERE date >= '2026-11-06' GROUP BY date ORDER BY date;"
```
