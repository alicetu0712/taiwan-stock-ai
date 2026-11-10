# Session 54 Q&A (20 Questions)

## Q1: What is BASELINE_UNRESOLVED and why was it chosen over BASELINE_DIFFERENT?
**A**: BASELINE_UNRESOLVED means the fingerprint discrepancy cannot be resolved — not that the baselines are different. The underlying metrics (n=3, +0.81pp, Oct13/14/16) are identical across S44–S54. BASELINE_DIFFERENT would imply the actual baseline changed. The fingerprints diverge due to serialization (different JSON key names), not different data. BASELINE_UNRESOLVED accurately captures "source unresolvable, metrics confirmed same."

## Q2: Why can't `2c8b2475c8fdc457` be reproduced?
**A**: Three reasons. (1) The `reproducibility_manifest_s44.py` currently produces `f48aa7f3ea673d7c` (different from `2c8b2475c8fdc457`), so the historical fingerprint was likely computed with different DB values (smaller forward_signals count, different dp_max). (2) Even at historical data values, we don't know exactly what `total`, `v8_buy`, `dp_max`, and `strict_fds` were at the precise moment the fingerprint was generated. (3) Brute-force search across a wide parameter range confirms no match. `docs/session47_final_verdict.md` documents the transition: changed after Nov04/05 manual backfill changed `daily_prices_max`.

## Q3: What is the significance of `docs/session47_final_verdict.md`?
**A**: It explicitly documents that the fingerprint changed from `2c8b2475c8fdc457` to `09c04e8c4059d87e` between S44 and S47 due to Nov04/05 manual backfill changing `daily_prices_max`. This confirms the transition was caused by INPUT_DATA_DIFFERENCE (dp_max changed), not algorithm change. However, the S47 doc references the canonical_5d_baseline module's fingerprint, while the original S44 doc references the reproducibility_manifest module's fingerprint — confirming SERIALIZATION_DIFFERENCE was always present.

## Q4: Does BASELINE_UNRESOLVED affect any research conclusions?
**A**: No. The frozen baseline metrics (+0.81pp, n=3, SIGNIFICANCE_INCONCLUSIVE) are unchanged and confirmed reproducible via `canonical_5d_baseline_s44.py`. The fingerprint question is about audit trail integrity, not about whether the analysis is correct.

## Q5: Why is TPEx error propagation categorized as ERROR_PROPAGATION_PARTIAL and not VERIFIED?
**A**: The research adapter (`PipelineErrorEvent`) correctly captures TPEx errors in isolated test runs, so the design is VERIFIED. But production code still uses `print()` for TPEx mismatches — no production patch has been deployed. Until the production patch is applied, TPEx errors won't appear in cron logs. Hence PARTIAL.

## Q6: What one line change would fix TPEx error propagation?
**A**: In `scripts/backfill_daily_prices.py`, change:
```python
print(f"  [WARN] {target_d}: TPEx api_date={tpex_api_date} != target")
```
to:
```python
summary["errors"].append(f"{target_d}: TPEx api_date={tpex_api_date} != target — API returned wrong date")
```
This is a 1-line observability fix with no logic change. It requires production authorization.

## Q7: Why is RC-04 (why was Nov06 cron not triggered?) INSUFFICIENT_EVIDENCE?
**A**: RC-01 confirms the trigger was absent (log file missing = no invocation). But RC-01 is the symptom, not the root cause. The scheduler itself may have failed due to system reboot, cron daemon restart, server maintenance, or crontab misconfiguration. These require reading system-level cron logs (e.g., `/var/log/cron`), which were not available in S54. INSUFFICIENT_EVIDENCE correctly signals that the deeper cause is unknown, not that the absence of trigger is in doubt.

## Q8: Why is the backfill verdict BACKFILL_PARTIAL and not BACKFILL_READY_FOR_AUTHORIZATION?
**A**: P1 dates (Oct29/30, Nov02/03) have INSERT_CANDIDATE rows pending user authorization, and TPEx data is UNVERIFIED for all dates. Full coverage is not possible without TPEx data. Hence PARTIAL rather than fully ready.

## Q9: What is the significance of `INSERT OR IGNORE` in the idempotency tests?
**A**: `INSERT OR IGNORE` skips duplicate inserts (same stock_id + date primary key) rather than failing with UNIQUE constraint violation. This ensures that re-running the backfill on the same dates is safe — it won't corrupt existing data or fail mid-batch. The dry-run confirmed: first insert succeeds, repeat insert produces 0 rows changed, conflict with different values also produces 0 rows changed.

## Q10: Why can't TPEx single-stock be used as a fallback immediately?
**A**: `SOURCE_UNVERIFIED` — no session has tested the TPEx single-stock API endpoint (confirmed in S50). Before it can be used in production, the endpoint must be: (1) tested to confirm it returns historical data for specific dates, (2) rate-limit and response format verified, (3) coverage (% of v8.0 universe stocks on TPEx) measured. Deploying an unverified source for production backfill would risk silent data errors.

## Q11: What does COLLECTION_BLOCKED mean for V3?
**A**: V3 cannot collect genuine prospective decisions. The framework is ready (ImmutableDecisionPayload, ProspectiveRecorderPrototype, frozen parameters). But 5 blockers prevent actual collection: V3 not activated, no persistent evidence storage, cron modification forbidden, Nov06+ market data missing, and G03/G04 FAIL (structural cluster independence requirement). COLLECTION_BLOCKED means the machinery is built but cannot run.

## Q12: Why is Nov12 not a "hard cutoff" for data recovery?
**A**: Nov12 is the 20TD maturity date for the Oct13 cluster — the earliest exit date. If data for Nov06/09/10 is backfilled before Nov12, the 20D outcome CAN be computed on Nov12. The data itself (TWSE single-stock API) remains accessible regardless of date — historical market data doesn't expire. The urgency is that Oct13's outcome WINDOW opens on Nov12; if data is missing then, it must be backfilled retroactively after Nov12 instead of being available on the exact maturity date.

## Q13: What would need to change for G03 to pass?
**A**: (1) V3 must be activated, (2) Stage B Cron Probe must be authorized, (3) a genuine cron run must generate V3 decisions against live market data (not backfilled), (4) at least 10 such decisions must accumulate, (5) they must be recorded in the ProspectiveRecorder with ImmutableDecisionPayload fingerprints. This requires weeks to months of live operation.

## Q14: Why is G04 a STRUCTURAL_FAIL rather than just FAIL?
**A**: STRUCTURAL_FAIL indicates the problem cannot be resolved by simply waiting or collecting more data within the current time frame. G04 requires ≥60 trading days between independent cluster pairs. The strict fill dates (Oct13, Oct14, Oct16) are only 3 trading days apart — nowhere near 60TD. Even if we waited, the Oct13/14/16 clusters would always be temporally correlated. New independent clusters (60TD+ apart) must emerge from future prospective collection.

## Q15: What was the Nov09 TWSE error and why did 4 retries all fail?
**A**: TWSE_HIST_URL returns CSV for historical dates, causing `json()` to fail. The backfill script falls back to `TWSE_LATEST_URL`, which returns the most recently available data — systematically lagged by 1 trading day. On Nov09, the latest available was Nov06's data. All 4 retries queried `TWSE_LATEST_URL` and got the same Nov06 response. The root cause (LATEST_URL lag) is deterministic — retrying doesn't help.

## Q16: What is the PipelineRunSummary `all_errors_propagated` field?
**A**: A boolean flag indicating whether ALL errors (including TPEx mismatches) were captured in the structured error list rather than being silently dropped to stdout. With the production patch applied, `all_errors_propagated=True` in production runs. With the current code (print-only TPEx), `all_errors_propagated=False` in production. The research adapter sets it to True in isolated analysis.

## Q17: Why are Nov04/05 SKIP_EXISTING in the backfill manifest?
**A**: Nov04/05 were backfilled in an earlier session (S48) using the OHLC continuity gate recovery process. The production `daily_prices` table already contains non-0050 rows for those dates. Attempting to INSERT again would be redundant; `INSERT OR IGNORE` would skip them anyway. SKIP_EXISTING is the correct action.

## Q18: What is the difference between AUTH01 and AUTH02?
**A**: AUTH01 = authorization to INSERT missing daily_prices rows into production DB (the backfill authorization). AUTH02 = authorization to execute new 20D return/alpha calculations once the data is complete. AUTH01 must precede AUTH02. Neither has been granted as of S54.

## Q19: What is the PROVENANCE_SUMMARY and why is it BASE_ONLY_PROSPECTIVE?
**A**: PROVENANCE_SUMMARY classifies the nature of all forward signals:
- `v3_decision_prospective_count=0`: no V3 decisions have been made prospectively
- `base_signal_prospective_count=6`: 6 fill-date signals from the base v8.0 strategy are genuinely prospective
- `retrospective_reconstruction_count=21`: remaining signals were reconstructed retrospectively
- `classification=BASE_ONLY_PROSPECTIVE`: the only prospective evidence is base v8.0 signals; no V3 prospective evidence exists yet

## Q20: When would ACTIVATION_BLOCKED be lifted?
**A**: The ACTIVATION_BLOCKED status would change to CONDITIONAL or READY when: (1) G03 passes (≥10 genuine prospective decisions), (2) G04 passes (independent clusters ≥60TD apart), (3) market data coverage is complete (Nov06+ pipeline restored), (4) baseline fingerprint is reconciled (BASELINE_UNRESOLVED resolved to BASELINE_IDENTICAL_VERIFIED), and (5) prospective evidence shows statistically significant positive return. All five conditions must be met simultaneously.
