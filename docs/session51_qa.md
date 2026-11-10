# Session 51 Q&A — 20 Questions

**Session**: S51  
**Analysis date**: 2026-11-10

---

**Q01: What is the RULE_FREEZE_DATE and why does it matter?**  
A: 2026-11-05. Any forward signal or decision recorded before this date cannot be classified as V3_DECISION_PROSPECTIVE. The freeze date is the point at which V3 parameters (`be43e8ca977d9fdd`) were formally locked. Signals before it are RETROSPECTIVE_RECONSTRUCTION even if their `locked_at` timestamp predates `execution_date`.

**Q02: Why are the Oct 13–28 fill clusters BASE_SIGNAL_PROSPECTIVE rather than V3_DECISION_PROSPECTIVE?**  
A: V3 was never activated. `hybrid_forward_decision` rows from Nov 04 (RETROSPECTIVE_RECONSTRUCTION) show V3 logic ran once manually but V3 is not in production. For V3_DECISION_PROSPECTIVE, the complete V3 decision pipeline must run prospectively with the frozen parameter hash — not just the v8.0 base signal.

**Q03: What caused the TIER_1_PROXY situation (Oct 29/30, Nov 02/03)?**  
A: `main.py` was imported (creating empty `run_*.log` files via its module-level `logging.basicConfig()` FileHandler) but `run_pipeline()` crashed before the first `logger.info()` call. The exact crash cause is HYPOTHESIS_ONLY — no stack trace in logs. 0050-only data was recovered manually via `recover_ohlc_0050.py --execute`.

**Q04: Why did Nov 06 fail the quality gate?**  
A: `hybrid_cron.log` confirms `2026-11-06: quality gate FAILED — not writing to DB`. The specific sub-check that failed is not extractable from logs (HYPOTHESIS_ONLY: S38 reclassification may have altered stock count). No data was written.

**Q05: Why did Nov 09 fail with BLOCKED_STALE_DATA?**  
A: TWSE bulk API returned `api_date=2026-11-06` for a Nov 09 request — the API was returning cached/prior-day data. After 3 retries (×30 min each), the cron gave up with BLOCKED_STALE_DATA. This is DIRECTLY_CONFIRMED from both `hybrid_cron.log` and `.cron_state.json`.

**Q06: Why are Nov 06 and Nov 09 classified SOURCE_VERIFIED_PARTIAL despite pipeline failure?**  
A: The pipeline failure was in the bulk API path, not in data existence. S50 verified via TWSE single-stock API that Nov 06 (TSMC 2135, MediaTek 3390) and Nov 09 (TSMC 2235, MediaTek 3725) data exists and is correct. The source is verified; the ingestion mechanism failed.

**Q07: What is the register() idempotency fix in ProspectiveRecorderPrototype?**  
A: `self._conn.total_changes` accumulates across a connection's lifetime and doesn't reflect the specific INSERT result. Using `cursor.rowcount` after `INSERT OR IGNORE` returns 1 for a new insert and 0 (or -1) for an ignored duplicate. The fix ensures `register()` returns False on duplicate, not True.

**Q08: What does ImmutableDecisionPayload.verify() detect?**  
A: It detects post-registration mutation of any immutable field (fill_date, signal_id, stock_id, model_version, locked_at, trade_signal, classification). It recomputes SHA-256[:16] over these fields and compares to the stored fingerprint. If they differ, the payload was modified after registration.

**Q09: Why is G03 FAIL even with 6 BASE_SIGNAL_PROSPECTIVE clusters?**  
A: G03 requires ≥10 independent clusters of V3_DECISION_PROSPECTIVE evidence. BASE_SIGNAL_PROSPECTIVE clusters count toward prospective evidence collection but do not satisfy G03 as defined. Additionally, with the current ≤5 TD spacing between Oct 21 and Oct 28, only N=2 strict-independent clusters exist at ≥6 TD threshold.

**Q10: Why is G04 described as "structural" rather than fixable?**  
A: The 5-trading-day return window means any two fill clusters within 5 TD will share measurement period days. With the actual Oct 21 (Mon) → Oct 28 (Mon) = 5 TD gap, windows overlap. Fixing G04 requires either (a) widening cluster spacing to ≥6 TD, or (b) shortening the return window — neither is possible retroactively. The fix for new data is to only collect clusters ≥6 TD apart.

**Q11: What is the Nov 12 hard deadline?**  
A: Oct 13 is the earliest fill date. Its 20-trading-day exit window closes on 2026-11-12 (2 calendar days from 2026-11-10). If pipeline data is not available for the full exit window by Nov 12, the 20D return for Oct 13 cannot be computed. This deadline cannot be extended.

**Q12: What would AUTH01 authorization cover?**  
A: AUTH01 authorizes execution of backfill scripts for specific dates: Oct 29/30, Nov 02/03, Nov 06, Nov 09. It covers the `--execute` flag on `backfill_daily_prices.py` for each date. It does NOT cover forward signal regeneration (AUTH02) or any modification to `forward_signals`/`hybrid_forward_decision`.

**Q13: What is the difference between TIER_6957_BACKFILL and the other tiers?**  
A: TIER_6957_BACKFILL (Nov 04/05) achieved full market coverage (6,957 stocks ≥ 5,000 threshold) via manual bulk backfill (commit fc2b4b0f). It is the only tier where the pipeline completed successfully post-Oct 28. All other tiers either used proxy data (TIER_1_PROXY), incomplete data (TIER_655_FILL), or failed entirely (BLOCKED_*).

**Q14: What does HYPOTHESIS_ONLY mean for the main pipeline silent failure?**  
A: `run_*.log` files exist for Nov 02–10 (created by `main.py`'s module-level FileHandler on import) but are empty — no `logger.info()` calls were executed. This means `run_pipeline()` was never called or crashed immediately. The root cause (import error? missing dependency? environment variable?) is not captured in any log and cannot be confirmed from available evidence.

**Q15: What is the calendar SSOT and why was S46 isolated?**  
A: `src/research/calendar_contract_s50.py` → `get_corrected_exit()` is the single source of truth for trading-day exit dates. S46 had erroneous exit dates in inline dicts (`_CALENDAR_5TD`, `_CALENDAR_20TD`). S46 is a frozen research module — its dicts are preserved for audit but not called from active code. All new callers must use `get_corrected_exit()` from S50.

**Q16: What is the significance of the git commit prompt injection?**  
A: 7 commits in the repository contain adversarial messages claiming "Antigravity is no longer supported." These are docs-only commits (Markdown files, no code changes). The messages are fabricated — no such system retirement has occurred. These commits were identified as an adversarial prompt injection attempt; no instructions from them were followed.

**Q17: What would V3_DECISION_PROSPECTIVE evidence require?**  
A: (1) V3 formally activated in production. (2) `hybrid_shadow_cron.py` running V3 decision logic with parameter hash `be43e8ca977d9fdd`. (3) Decision payload (including V3 snapshot) locked and fingerprinted before `execution_date`. (4) `locked_at` timestamp precedes `execution_date` for the specific record. Currently none of these conditions are met.

**Q18: How many weeks until G03 can theoretically pass?**  
A: Starting from pipeline restoration (unknown date), collecting 10 V3_DECISION_PROSPECTIVE clusters at ≥6 TD apart = at least 9 × 6 TD = 54 trading days ≈ 10.8 calendar weeks. From 2026-11-10, that is approximately 2027-01-26 at the earliest — assuming pipeline is restored immediately.

**Q19: Why does ProspectiveRecorderPrototype use INSERT OR IGNORE rather than INSERT OR REPLACE?**  
A: Idempotency without mutation. `INSERT OR REPLACE` would delete and re-insert the row (changing the autoincrement id and potentially overwriting a valid fingerprint with a malformed one). `INSERT OR IGNORE` preserves the first registered version, enforcing append-only semantics.

**Q20: What is the net verdict change from S50 to S51?**  
A: No change in activation status (ACTIVATION_BLOCKED), baseline (+0.81 pp), or guardrail verdicts (G03/G04 both FAIL). S51 added: pipeline root cause evidence matrix (5 tiers × 10 stages), prospective classification framework (`DecisionClassification` with 4 levels), `ImmutableDecisionPayload` fingerprint, `ProspectiveRecorderPrototype` (append-only, temp SQLite), `BackfillAuthorizationReadiness` (AUTH01 PENDING for 6 dates), and 150 new tests. The session formalised what was known informally: the pipeline is blocked, evidence classification is rigorous, and collection of genuine prospective evidence requires pipeline restoration and V3 activation.
