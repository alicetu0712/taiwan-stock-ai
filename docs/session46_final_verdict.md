# Session 46 Final Verdict — Data Freshness Recovery & Prospective Evidence Validation

**Date:** 2026-11-09  
**Session:** S46 — PARTS A through M  
**Analyst:** Alice Tu  
**Test Count:** 2661 passed, 1 skipped (baseline 2575 + 86 new)

---

## Final Verdict Enums

| Dimension | Verdict |
|---|---|
| Data freshness root cause | ROOT_CAUSE_CONFIRMED |
| Cluster maturity impact | MATURE_BUT_DATA_INCOMPLETE (3 clusters) |
| Isolated 5D recovery | ISOLATED_COMPUTABLE (4 clusters), PENDING_NEON (2) |
| Strict 5D baseline | UNCHANGED (grand mean +0.81%, CI [-1.4%, +3.0%]) |
| Prospective provenance | ALL_GENUINE_PROSPECTIVE (6 non-null clusters) |
| 20D data dependency | NOT_YET_MATURE (all 6 clusters) |
| Guardrail G01 | PASS |
| Guardrail G02 | CONDITIONAL |
| Guardrail G03 | FAIL (3 strict, need ≥10) |
| Guardrail G04 | FAIL (80% overlap, design constraint) |
| Overall guardrails | GUARDRAILS_FAIL |
| Workflow status | EVIDENCE_PIPELINE_PARTIAL_DATA_FRESHNESS_BLOCKED |
| Activation | ACTIVATION_BLOCKED (unchanged from S45) |
| Production state | NOT MODIFIED |

---

## 20 Q&A

**Q1: Why is local SQLite stuck at 2026-11-05?**  
A1: The pipeline cron (`hybrid_shadow_cron.py`) was not running from Nov 02–08. The first confirmed cron execution was `2026-11-09T08:00:17Z`. Nov 04/05 data exists because of a manual `backfill_daily_prices.py` run documented in the DailyPrice Pipeline project.

**Q2: What was the primary root cause of the data freshness gap?**  
A2: `SCHEDULER_NOT_TRIGGERED`. The cron scheduler was not active for 7 trading days (Nov 02–08). This is the primary cause, independent of quality gate or provider issues.

**Q3: Why did the Nov 09 cron attempt fail?**  
A3: `PROVIDER_NOT_READY`. The TWSE API returned `api_date=2026-11-06` for all 4 attempts (08:00, 08:35, 09:05, 09:35 UTC). After 3 retries, the cron exited with `BLOCKED_STALE_DATA`. This is a temporal issue — the provider publishes updated data later in the trading day.

**Q4: What does "MATURE_BUT_DATA_INCOMPLETE" mean?**  
A4: The calendar-based 5th trading day has already passed (the market window has closed), but the local SQLite database lacks intermediate-date prices (Oct 29/30/Nov 02/03 have only 0050 proxy). The exit price is available in the DB (e.g., Nov 04 for Oct 28 fill), but the proxy counter (`_count_exit_days` using 2330/TSMC) only sees 2 days instead of 5.

**Q5: Why didn't the Oct 28 fill become a strict baseline cluster?**  
A5: The strict baseline uses `_count_exit_days >= 5` as the proxy-based exit criterion. For Oct 28 fill, the proxy only counts Nov 04 and Nov 05 (2 days), because Oct 29/30/Nov 02/03 have no TSMC data in local SQLite. Despite the actual exit price being available on Nov 04 (calendar 5th TD), the proxy count is 2/5 → not strict.

**Q6: What is the Oct 28 fill's isolated research result?**  
A6: V3 mean = -13.18%, A_direct mean = -15.94%, Delta = **+2.75 pp**. Both strategies lost money in a down market, but V3 lost less. This is directionally consistent with the frozen baseline (+0.81% grand mean). Status: RESEARCH_ONLY, not part of strict baseline.

**Q7: Does the Oct 28 isolated result change the final verdict?**  
A7: No. The frozen baseline (3 strict clusters, grand mean +0.81%) is unchanged. The Oct 28 result is RESEARCH_ONLY and cannot be promoted to the strict baseline due to G03 requirements (N < 10).

**Q8: What is the expanded grand mean if Oct 28 is included?**  
A8: +1.60% (4 finite clusters: +1.07%, +2.76%, -1.49%, +2.75%). Still SIGNIFICANCE_INCONCLUSIVE — N=4 is insufficient for reliable statistical inference.

**Q9: Are the signals genuinely prospective?**  
A9: Yes. All 6 non-null fill clusters verified as GENUINE_PROSPECTIVE. For every cluster, `locked_at < execution_date`, `execution_price_type = 'NEXT_OPEN'`, and the schema is append-only. No look-ahead bias identified.

**Q10: What is the 1 NULL exec_date cluster?**  
A10: Signals with `trade_date = 2026-10-28` (n=259) have `execution_date = NULL`. These signals were generated but no execution date was assigned — likely because the pipeline was blocked on Nov 06+ when execution would have occurred. Excluded from comparison.

**Q11: Why does the 5D baseline remain at exactly 3 clusters?**  
A11: The strict baseline (computed by `canonical_5d_baseline_s44.py` using the proxy exit criterion) has not changed since S44. Data freshness gap prevented Oct 21, Oct 22, and Oct 28 fills from meeting the strict proxy threshold. These 3 fills are MATURE_BUT_DATA_INCOMPLETE — their calendar windows closed but proxy data is thin.

**Q12: When could G03 (strict cluster count) possibly pass?**  
A12: Only after: (1) pipeline fully restored and backfilling Nov 02/03/06/09, (2) ~7 more weeks of uninterrupted prospective data generating new fill clusters, and (3) those new clusters reaching their calendar 5th TD. Earliest realistic G03 PASS ≈ early January 2027.

**Q13: Can G04 (window overlap) be remediated?**  
A13: Yes, but requires a design decision: either weekly-spaced fills (non-overlapping 5D windows) or bootstrap CI on cluster-level means. No design change was authorized in S46. G04 remains FAIL.

**Q14: What are all 6 calendar 5th TDs for the fill clusters?**  
A14: Oct 13→Oct 21, Oct 14→Oct 28, Oct 16→Nov 05, Oct 21→Oct 30, Oct 22→Nov 02, Oct 28→Nov 04.

**Q15: Why are Oct 30 and Nov 02 exit dates listed as ISOLATED_PENDING_NEON?**  
A15: Local SQLite has only 1 stock (0050) on Oct 30 and Nov 02. The actual exit prices for Oct 21 and Oct 22 fills are available in Neon DB (638 stocks), but Neon read access for research computation is not currently authorized.

**Q16: What would happen if the Nov 02/03 backfill were executed?**  
A16: Oct 21 and Oct 22 fills would gain intermediate-date prices in local SQLite, allowing their proxy exit-day counts to reach 5. This would promote them from MATURE_BUT_DATA_INCOMPLETE to MATURE_AND_COMPLETE, increasing the strict cluster count from 3 to 5.

**Q17: When are 20D outcomes computable for the earliest fill cluster?**  
A17: The Oct 13 fill has a calendar 20th TD of **Nov 14** — 5 trading days from the analysis date. Even if the pipeline is restored today, the exit price is not yet available. All 6 clusters are NOT_YET_MATURE for 20D as of Nov 09.

**Q18: What is the difference between Neon and local SQLite pipeline state?**  
A18: Neon (PostgreSQL production) has a separate pipeline that produced 638 stocks/day for Oct 29–Nov 06. Local SQLite has only 0050 for those dates except Nov 04/05 (manual backfill). Research baselines exclusively use local SQLite. Neon is a production system, not a research source.

**Q19: Was any production system modified in S46?**  
A19: No. All S46 work was read-only research analysis plus new research modules and test files. Production fingerprints unchanged: `forward_signals count = 2605`, `daily_prices max (SQLite) = 2026-11-05`, V3 Parameter Hash = `be43e8ca977d9fdd`, Crontab Hash = `3acaf480cb5dcdd44f40dd9d464955a1`.

**Q20: What is the activation status and what would change it?**  
A20: `ACTIVATION_BLOCKED`. Unchanged from S45. Two independent blockers: (1) G03 FAIL — insufficient strict clusters for reliable statistical inference; (2) G04 FAIL — adjacent window overlap 80%, violating independence assumption. Resolving data freshness (backfilling Nov 02/03/06/09) would address G03 progress, but G04 requires a design decision. Neither can be resolved in a single session.

---

## Key Numbers Summary

| Metric | Value |
|---|---|
| Strict baseline clusters | 3 |
| Grand mean D | +0.81% |
| CI 95% | [-1.4%, +3.0%] |
| Expanded clusters (finite) | 4 |
| Expanded grand mean | +1.60% |
| Oct 28 isolated D | +2.75% |
| Total fill clusters | 6 non-null + 1 null |
| GENUINE_PROSPECTIVE | 6/6 non-null |
| MATURE_BUT_DATA_INCOMPLETE | 3 |
| MATURE_AND_COMPLETE | 3 |
| NOT_YET_MATURE (5D) | 0 |
| NOT_YET_MATURE (20D) | 6 |
| New tests in S46 | 86 |
| Total tests | 2661 passed, 1 skipped |

---

## Production Fingerprints (Unchanged)

| Item | Value |
|---|---|
| `forward_signals` count | 2605 |
| `daily_prices` max (SQLite) | 2026-11-05 |
| V3 Parameter Hash | `be43e8ca977d9fdd` |
| Crontab Hash | `3acaf480cb5dcdd44f40dd9d464955a1` |
| SESSION | 46 |
