# Session 55 — 20 Final Questions

## Q1: Was `2c8b2475c8fdc457` ever recoverable?

**A**: No. Git archaeology in S55 confirmed all Session 44–54 docs are UNTRACKED files — never committed. `git log --all -S "2c8b2475"` returns empty. Exhaustive parameter search across 3 payload schemas × 15+ dp_max values × v8_buy 0–2999 × 7 strict_fd combinations found no match. Verdict: HISTORICAL_BASELINE_UNRECOVERABLE.

---

## Q2: Is Canonical Baseline V2 a replacement for the historical fingerprint?

**A**: No. V2 is a NEW baseline with version ID `S55-canonical-v2` and full 64-char SHA256. It captures the same DB state and research metrics as the historical baseline claimed to, but is independently verifiable and self-consistent. It does NOT retroactively resolve the historical fingerprint.

---

## Q3: Does the UNRECOVERABLE verdict invalidate the +0.81pp finding?

**A**: No. The metrics (grand mean +0.81pp, Oct13/14/16 clusters, N=3) are confirmed by multiple independent untracked docs across S44–S54 and by current DB queries. The fingerprint discrepancy is a documentation integrity issue, not a data integrity issue.

---

## Q4: What exactly does the TPEx patch change?

**A**: It adds 2 lines to `scripts/backfill_daily_prices.py` L500–503. Currently, when `tpex_api_date != target_d`, the code only calls `print()`. The patch adds `msg = ...` and `summary["errors"].append(msg)` so the error is captured in the run summary. Zero logic change — pure observability improvement.

---

## Q5: Why is the TPEx patch PATCH_READY_FOR_AUTHORIZATION but not deployed?

**A**: Deployment requires explicit user authorization (session constraint: 修改正式 Pipeline Write is prohibited). The 12-scenario isolation simulation confirmed PASS for all scenarios, so the patch is technically ready. It awaits authorization, not engineering work.

---

## Q6: What is the difference between RC-01 and RC-02?

**A**: RC-01 (CRON_NO_TRIGGER) explains why Oct29–Nov03 have no data: the cron scheduler never triggered. RC-02 (TWSE_LATEST_URL_LAG) explains why Nov06/Nov09 have incomplete data even after a manual trigger attempt: the TWSE URL returns yesterday's data, not today's.

---

## Q7: Why is ROOT_CAUSE_PARTIAL and not ROOT_CAUSE_FULLY_RESOLVED?

**A**: RC-03 (TPEX_HIST_URL) is STRONGLY_SUPPORTED but not DIRECTLY_CONFIRMED because the TPEx error propagation defect (the very thing being fixed by the patch) masks direct evidence. RC-04 (DATABASE_WRITE_FAILURE) remains INSUFFICIENT_EVIDENCE. Full resolution requires patch deployment and re-observation.

---

## Q8: Why are Oct29/30/Nov02/03 INSERT_CANDIDATE but Nov04/05 SKIP_EXISTING?

**A**: The DB shows Nov04 has 6957 rows (6956 non-0050) and Nov05 has 6589 rows (6588 non-0050). These dates were fully backfilled in Session 49/50. Oct29/30/Nov02/03 each have exactly 1 row (the 0050 benchmark only) — they were never backfilled, so they are INSERT_CANDIDATE.

---

## Q9: Why is AUTH01 verdict PARTIAL and not READY?

**A**: PARTIAL because: (1) only 3 stocks verified on Oct29, 2 on Oct30, 1 each on Nov02/03 — not full universe coverage; (2) TPEx coverage unverified for all dates; (3) corporate actions not checked; (4) actual DB insert requires authorization not yet granted.

---

## Q10: Can the TWSE-verified prices (Oct29: 2330=2415, 2454=4045, 2317=248) be trusted?

**A**: These were verified via TWSE single-stock queries in Session 50 and preserved in `_S50_VERIFIED_PRICES` within the research module. They represent the spot price from a TWSE single-stock API call, not a full daily file. They are suitable for record-level validation but not full universe coverage.

---

## Q11: Why does G03 still FAIL in S55?

**A**: G03 requires ≥10 prospective windows. Currently 0/10. G03 FAIL has been persistent since S42. No new prospective windows opened in S55 (calendar + pipeline blockers prevent new data collection). G03 remains GUARDRAIL_FAIL.

---

## Q12: Why does G04 have a STRUCTURAL_FAIL designation rather than just FAIL?

**A**: G04 requires weekly spacing between prospective clusters. The current pipeline collects signals continuously — there is no built-in weekly spacing mechanism. This is an algorithm/design constraint, not a data gap. It cannot be fixed by simply collecting more data; it requires a structural change to the collection logic.

---

## Q13: When will 20D outcomes first become available?

**A**: The Oct13 cluster (fill date) entered ~Oct14. 20 trading days after Oct14 is approximately Nov12. As of today (2026-11-10), the first 20D outcomes may be available in ~2 trading days. However, 20D computation is currently prohibited by safety constraints.

---

## Q14: What is CRON_FROZEN_UNCHANGED and why does it persist?

**A**: The crontab hash `3acaf480cb5dcdd44f40dd9d464955a1` has been confirmed unchanged across S46–S55. The Stage B Cron Probe was explicitly NOT AUTHORIZED in Session 36. Modifying cron/crontab is a safety constraint violation. The cron schedule cannot be changed without user authorization.

---

## Q15: What is the relationship between S54 BASELINE_UNRESOLVED and S55 HISTORICAL_BASELINE_UNRECOVERABLE?

**A**: S54 verdict was BASELINE_UNRESOLVED (could not reproduce, but left open the possibility of recovery with more search). S55 performed targeted evidence-based provenance search (git log, blame, untracked file analysis, self-contradiction detection) and confirmed no recovery path exists. HISTORICAL_BASELINE_UNRECOVERABLE is a stronger verdict that closes the UNRESOLVED state.

---

## Q16: Does Canonical Baseline V2 change the statistical verdict?

**A**: No. V2 encodes the same metrics: +0.81pp grand mean, CI [−1.4pp, +3.0pp], N=3, methodology=cluster_level_one_sample_t_test_v1. The statistical verdict remains SIGNIFICANCE_INCONCLUSIVE. V2 improves fingerprint stability and documentation integrity, not statistical power.

---

## Q17: Why are Nov06/Nov09 labeled P2 instead of P1 for AUTH01?

**A**: Oct29/30/Nov02/03 are P1 because they are entirely missing (no data at all — cron never triggered). Nov06/Nov09 are P2 because they have partial data issues (TWSE_LATEST_URL_LAG returned wrong date) but the cron mechanism itself did trigger. The P1/P2 distinction reflects severity of data gap, not authorization priority.

---

## Q18: Was any production system modified in Session 55?

**A**: No. All work was read-only DB queries, temporary SQLite (isolated research), new research module creation, test creation, and documentation. The production DB (Neon), production SQLite, forward_signals, daily_prices, cron, and all frozen systems are unchanged.

---

## Q19: What is the minimum set of authorizations needed to unblock ACTIVATION?

**A**: Six items: (1) AUTH01 backfill execution, (2) TPEx patch deployment, (3) Cron recovery for missing dates, (4) G03 windows (10 prospective windows — requires (1)+(2)+(3)+(time)), (5) 20D outcome computation after maturity, (6) G04 structural fix (weekly spacing algorithm). Items 1–3 require authorization today; items 4–6 require time + authorization.

---

## Q20: What evidence would change ACTIVATION_BLOCKED to ACTIVATION_READY?

**A**: (1) AUTH01 executed + all 8 dates backfilled, (2) TPEx patch deployed, (3) G03 windows: 10+ prospective clusters with weekly spacing, (4) 20D outcomes available (Oct13 cluster matures ~Nov12), (5) Statistical verdict upgrades to SIGNIFICANT_POSITIVE (requires larger N), (6) G04 weekly spacing constraint resolved. None of these conditions are met in S55.
