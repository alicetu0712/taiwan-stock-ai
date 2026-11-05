# Approval B Execution Report — Historical Research Initialization

**Date:** 2026-11-05  
**Git HEAD:** 1c42cb3  
**Executor:** Session 18 (Claude Code)  
**Authorization:** Approval B only. Approval C NOT authorized or executed.  
**Scope:** EntryTimingResearchService.run_for_date() × 5 trading dates (2026-10-29 ~ 2026-11-04).

---

## Execution Summary

| Item | Value |
|---|---|
| Git HEAD | 1c42cb3 |
| Database | Neon PostgreSQL (neondb, public schema) |
| Target table | v2_shadow_signals (research_version = v2_research_v1) |
| Trading dates processed | 5 of 5 |
| Total source signals | 1,750 |
| Total rows inserted | 1,021 |
| Total errors (insufficient OHLC) | 729 |
| Total skipped (duplicate) | 0 |
| Transaction result | SUCCESS (per-row commit, IntegrityError fallback) |
| Unauthorized writes | NONE |

---

## PART B — Authorization Scope Confirmed

- **Executed:** `EntryTimingResearchService.run_for_date(trade_date=<date>)`
- **NOT executed:** `ShadowRecalculationService.recalculate()` (Approval C)
- **Write target:** `v2_shadow_signals` only (INSERT only, no UPDATE/DELETE)
- **Read sources:** `forward_signals` (Neon), `daily_prices` (Neon)
- **ForwardSignal writes:** NONE
- **Hybrid tables touched:** NONE

---

## PART C — Pre-Execution Safety Gate (all PASS)

| Check | Result |
|---|---|
| C-1 Database identity | neondb, public schema, Neon PostgreSQL 18.6 ✅ |
| C-2 Research schema ORM | UniqueConstraint (trade_date, stock_id, research_version), ResearchBase∩Base=∅ ✅ |
| C-3 Formal signal source | 1,750 signals, null_labels=0, duplicates=0, execution_date intact ✅ |
| C-4 Market data | 637-638 stocks/day OHLC, all 5 dates are weekdays (Thu/Fri/Mon/Tue/Wed) ✅ |
| C-5 Write scope | v2_shadow_signals INSERT only, no UPDATE/DELETE, Hybrid NOT accessed ✅ |
| Abort conditions | None triggered ✅ |

---

## PART D — Pre-write Snapshot

| Metric | Before |
|---|---|
| forward_signals count | 1,750 |
| forward_signals fingerprint | `5a92173f79b800a4` |
| v2_shadow_signals total | 0 |
| v2_research_v1 count | 0 |
| v2_research_v2 count | 0 |
| hybrid_forward_decision count | 21 (data/platform.db) |
| hybrid_forward_decision fingerprint | `fc4056bb08b5a6b0` |

---

## PART E — Daily Results

| Trade Date | Source Signals | Inserted | Errors* | Skipped | Insert Rate | Verdict |
|---|---:|---:|---:|---:|---:|---|
| 2026-10-29 | 323 | 191 | 132 | 0 | 59.1% | PASS ✅ |
| 2026-10-30 | 361 | 210 | 151 | 0 | 58.2% | PASS ✅ |
| 2026-11-02 | 316 | 187 | 129 | 0 | 59.2% | PASS ✅ |
| 2026-11-03 | 369 | 213 | 156 | 0 | 57.7% | PASS ✅ |
| 2026-11-04 | 381 | 220 | 161 | 0 | 57.7% | PASS ✅ |
| **Total** | **1,750** | **1,021** | **729** | **0** | **58.3%** | **SUCCESS** |

\* Errors = stocks with insufficient OHLC history (< 21 bars in DailyPrice). Handled gracefully by service (errors += 1, no exception propagated). No abort triggered.

**Note:** Insert rate ~58% is consistent across all 5 dates, confirming stable behavior. The ~42% error rate reflects OHLC data coverage gaps for some stocks in Neon.

---

## PART F — Research Version Integrity

| Check | Result |
|---|---|
| research_version distribution | `{'v2_research_v1': 1021}` — all rows correct ✅ |
| is_legacy distribution | `{False: 1021}` — none marked legacy ✅ |
| is_legacy=TRUE rows | 0 ✅ |
| Duplicate v1 per (trade_date, stock_id) | 0 ✅ |
| v2_research_v2 rows written | 0 (Approval C not executed) ✅ |
| Skip-check filter confirmed | research_version == 'v2_research_v1' correctly isolates v1 from future v2 rows ✅ |
| PROSPECTIVE contamination | None — all rows are historical, is_legacy=False ✅ |
| ForwardSignal timestamps modified | NONE ✅ |

---

## PART G — Idempotency

Verified on isolated SQLite (not re-run against production Neon):

| Test | Result |
|---|---|
| Skip-check fires for existing v1 rows | 2/2 skipped ✅ |
| v2_research_v2 row does NOT block v1 creation | Confirmed ✅ |
| Duplicate v1 INSERT raises IntegrityError | Caught, rolled back ✅ |
| Row count unchanged after simulated re-run | 3 → 3, diff=0 ✅ |
| **IDEMPOTENCY** | **PASS ✅** |

---

## PART H — Post-execution Integrity

| Metric | Before | After | Difference |
|---|---:|---:|---:|
| forward_signals count | 1,750 | 1,750 | +0 ✅ |
| forward_signals fingerprint | `5a92173f79b800a4` | `5a92173f79b800a4` | UNCHANGED ✅ |
| v2_shadow_signals total | 0 | 1,021 | +1,021 ✅ |
| v2_research_v1 | 0 | 1,021 | +1,021 ✅ |
| v2_research_v2 | 0 | 0 | +0 ✅ |
| hybrid_forward_decision count | 21 | 21 | +0 ✅ |
| hybrid_forward_decision fingerprint | `fc4056bb08b5a6b0` | `fc4056bb08b5a6b0` | UNCHANGED ✅ |

**DATA INTEGRITY: PASS ✅ — no DATA_INTEGRITY_INCIDENT**

---

## PART I — Dashboard Read-only Verification

| Check | Result |
|---|---|
| v2_research_v1 query | 200 rows returned, no ProgrammingError ✅ |
| Dates in v2_research_v1 result | 2026-10-29 ~ 2026-11-04 ✅ |
| research_version filter correct | All returned rows = v2_research_v1 ✅ |
| is_legacy in result | All False ✅ |
| v2_research_v2 query | 0 rows — B_COMPLETE_C_PENDING ✅ |
| Schema error | None ✅ |
| Connection error | None ✅ |
| **Dashboard status** | **QUERY_OK** |

---

## PART J — Regression Tests

| Suite | Count | Status |
|---|---|---|
| Full test suite | **1,706 passed** | ✅ |
| Modified files Ruff lint | 0 errors | ✅ |

No code changes were made in this session (pure execution). Test count unchanged from Session 17.

---

## Final Verdict

### Initialization
**SUCCESS** — 5/5 trading dates completed, 1,021 rows inserted, 0 duplicates, 0 unauthorized writes.

### Data Integrity
**PASS** — ForwardSignals fingerprint unchanged, Hybrid fingerprint unchanged, research_version 100% correct.

### Dashboard
**QUERY_OK** — v2_research_v1 queryable, v2_research_v2 empty (expected: Approval C not yet run).

### Overall
**B_COMPLETE_C_PENDING**

---

## Answers to Required Questions

1. **Approval B 是否成功？** YES — 5/5 dates processed, all PASS.
2. **實際處理幾個交易日？** 5 dates: 2026-10-29, 2026-10-30, 2026-11-02, 2026-11-03, 2026-11-04.
3. **新增多少研究資料？** 1,021 rows (all research_version = v2_research_v1).
4. **哪些日期沒有訊號或缺少行情？** 無日期缺訊號。729 個 signal 因 OHLC < 21 bars 而跳過（服務 errors 計數器），非日期級別失敗。
5. **是否有任何既有研究資料被修改？** NO — v2_shadow_signals 在執行前有 0 rows，不存在既有資料。
6. **ForwardSignals 是否完全不變？** YES — count 1,750 unchanged, fingerprint `5a92173f79b800a4` unchanged.
7. **Hybrid Forward Decisions 是否完全不變？** YES — count 21 unchanged, fingerprint `fc4056bb08b5a6b0` unchanged.
8. **Dashboard 是否正常？** YES — QUERY_OK, v1 data present, v2 empty (B_COMPLETE_C_PENDING).
9. **是否可以進入 Approval C 授權評估？** YES — schema correct, v2_research_v1 baseline established, no data integrity issues.
10. **是否有需要使用者處理的問題？** 無阻擋問題。注意：~42% error rate (insufficient OHLC history) 為正常現象，代表 Neon DailyPrice 未覆蓋所有 ForwardSignal 股票的完整歷史。若希望提高覆蓋率，需額外回補 DailyPrice 資料（超出本次授權範圍）。

---

## Next Step (requires separate authorization)

**Approval C — Shadow Recalculation** (not yet authorized):
```python
ShadowRecalculationService.recalculate(research_session, prod_session, date_from, date_to)
```
- Reads v2_research_v1 rows, generates v2_research_v2 rows using updated research logic
- Append-only, skip-check on (trade_date, stock_id, research_version == 'v2_research_v2')
- Prerequisite: Approval B complete ✅ (1,021 v2_research_v1 rows available)
