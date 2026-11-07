# V3 Prospective Shadow Research Readiness

**Research Only — Not for Production Deployment**  
Session 29 | 2026-11-06 | Framework: `v3_shadow_v1`

---

## 1. Executive Summary

This document establishes the V3 Prospective Shadow Research framework — the infrastructure required to accumulate genuine out-of-sample (OOS) evidence for V3 entry timing, beginning 2026-11-06. The framework is architecturally complete and all tests pass. **However, activation is CONDITIONAL** pending Hybrid Cron acceptance (first successful prospective write has not yet occurred).

**Current Status:**

| Component | Status |
|---|---|
| V3 Framework | `V3_PROSPECTIVE_FRAMEWORK_READY` |
| Data Integrity | `DATA_INTEGRITY_PARTIAL` (platform.db fresh; Nov-6 cron not yet run) |
| Existing Cron | `CRON_ACCEPTANCE_PENDING` |
| Activation | `ACTIVATION_CONDITIONAL` |
| Evidence | `NO_PROSPECTIVE_EVIDENCE` |

---

## 2. Current Production Safety Status

### Preflight Audit (P1) — All Items Checked

| Item | Result |
|---|---|
| Git HEAD | `ad6fbb8` (Session 27 research files are untracked) |
| Working Tree | 6 untracked research files; no modified tracked files |
| MODEL_VERSION | v8.0 ✓ unchanged |
| Hybrid Rule Version | `hybrid_v1` ✓ unchanged |
| V3 Backtest PARAMETER_HASH | `be43e8ca977d9fdd` ✓ matches Session 26 expected |
| V3 Comparison PARAMETER_HASH | `1feb7a6b294a063d` ✓ matches Session 27 expected |
| ForwardSignals (buy/strong_buy) | 344 signals, fingerprint `9c0d1a16152d` |
| Hybrid Shadow Decisions | 21 entries (`hybrid_v1`, max date 2026-11-04, all RETROSPECTIVE_RECONSTRUCTION) |
| 0050 Data Freshness | 2026-11-05 ✓ |
| Non-0050 Data (2026-11-05) | 6,588 stocks (FULL_MARKET_FRESH) |
| Background Processes | No anomalous processes |

### FM11 Failure Root Cause

`test_FM11_real_db_11_05_benchmark_only` expects 2026-11-05 to show `BENCHMARK_ONLY_UPDATED` with `non_benchmark_count=0`. The test was written when only 0050 had been updated for 2026-11-05 (documented in `data/.cron_state.json`: `data_freshness: "BENCHMARK_ONLY_UPDATED"`). After the DailyPrice backfill script ran, 6,588 non-0050 stocks were added for 2026-11-05, making the actual status `FULL_MARKET_FRESH`.

**Root Cause:** Stale real-DB integration test — the expected state is a historical snapshot that is no longer accurate. This is **unrelated** to Session 29 changes. The test documents a past transient state of platform.db, not a production correctness requirement.

**Impact on Session 29:** None. FM11 is a pre-existing failure from before Session 27.

---

## 3. Existing Cron Acceptance

### Status: CRON_ACCEPTANCE_PENDING

**Evidence examined:**

| Item | Value |
|---|---|
| `data/.cron_state.json` trigger_source | `cron_scheduled` |
| Run at | 2026-11-05 18:28:50 CST (10:28:50 UTC) |
| Status | `BLOCKED_PARTIAL_MARKET` |
| Reason | "0050 updated to 2026-11-05, but non-0050 count=0" |
| Prospective writes | 0 |
| Hybrid decisions written (2026-11-05) | 0 |

The cron ran on 2026-11-05 but was correctly blocked (full market data not available at run time). The DailyPrice pipeline subsequently backfilled 2026-11-05.

**Why trigger_source alone is insufficient:** `trigger_source: "cron_scheduled"` is set by the pipeline itself — it does not prove an external scheduler invoked the process. No independent process execution evidence (OS scheduler log, GitHub Actions workflow run, cron daemon log) is available in the repository.

**2026-11-06 scheduled run (16:00 Taiwan):** Not yet confirmed as of this audit. The cron state file shows the last run was 2026-11-05.

**Conclusion:** Hybrid Cron has demonstrated correct blocked behavior (partial market → no writes). Full acceptance requires the first run that:
1. Triggers from an external scheduler (not manual).
2. Passes the FULL MARKET gate.
3. Writes ≥1 PROSPECTIVE_ELIGIBLE hybrid decision.
4. Has a verifiable external trigger source.

---

## 4. V3 Freeze Manifest

### Status: VERIFIED

The freeze manifest is computed deterministically from live code at freeze time. Any change to V3 parameters requires a new `research_version`, not a modification of this manifest.

| Field | Value |
|---|---|
| `research_version` | `v3_research_v1` |
| `strategy_version` | `v3_shadow_v1` |
| `parameter_hash` | `be43e8ca977d9fdd` |
| `source_code_hash` | computed from `v3_entry_strategy.py` |
| `execution_model_hash` | computed from `_REGIME_PARAMS` + thresholds |
| `cost_model_hash` | computed from `FEES_PCT=0.585%` |
| `benchmark_definition` | `0050 gross: open[fill_date] → close[exit_date]` |
| `signal_eligibility_rules` | `trade_signal IN ('buy','strong_buy') FROM forward_signals` |
| `freeze_effective_from` | `2026-11-06` |
| `git_head` | `ad6fbb8` |

**Freeze invariants:**
1. V3 rules frozen as of 2026-11-06. Any change requires new `research_version`.
2. Session 27/28 results did NOT alter V3 parameters ✓.
3. No modification to Hybrid P1–P4 ✓.
4. No modification to production MODEL_VERSION v8.0 ✓.

---

## 5. Prospective Capture Contract (`V3ProspectiveDecision`)

### Identity Fields
| Field | Purpose |
|---|---|
| `research_version` | "v3_research_v1" — ties to freeze manifest |
| `signal_id` | foreign key to `forward_signals.id` |
| `stock_id` | TWSE/TPEx code |
| `trade_date` | signal date |
| `decision_id` | SHA-256 of (stock_id, trade_date, research_version, payload_hash) |

### Timing Fields
| Field | Purpose |
|---|---|
| `data_available_at` | Taiwan market close time (13:30 CST) |
| `input_data_as_of` | OHLCV cutoff date — must equal trade_date |
| `captured_at` | when record was written |
| `market_timezone` | "Asia/Taipei" |

### Reproducibility Fields
| Field | Purpose |
|---|---|
| `parameter_hash` | V3_PARAMETER_HASH (`be43e8ca977d9fdd`) |
| `source_code_hash` | SHA-256 of v3_entry_strategy.py |
| `feature_snapshot_hash` | SHA-256 of MA/slope/volume inputs |
| `payload_hash` | SHA-256 of decision fields (for conflict detection) |

### Classification
| `capture_type` | Meaning |
|---|---|
| `PROSPECTIVE_ELIGIBLE` | All 10 conditions met |
| `RETROSPECTIVE_RECONSTRUCTION` | Pre-freeze date |
| `LATE_CAPTURE` | Captured after capture window |
| `MISSING_INPUT` | Insufficient OHLC or look-ahead detected |
| `INCOMPLETE_MARKET_DATA` | 0050 or full market missing |
| `FREEZE_MISMATCH` | Parameter hash drift detected |

**Key principle:** Decision records are IMMUTABLE after insertion. Outcomes are stored in `V3OutcomeRecord` in a separate table.

---

## 6. Eligibility Rules (10 Conditions)

A decision is `PROSPECTIVE_ELIGIBLE` only when **all** of the following pass:

| # | Condition | Failure Classification |
|---|---|---|
| C1 | trade_date ≥ freeze_effective_from (2026-11-06) | RETROSPECTIVE_RECONSTRUCTION |
| C2 | Freeze manifest verification passes | FREEZE_MISMATCH |
| C3 | parameter_hash matches manifest | FREEZE_MISMATCH |
| C4 | Captured within capture window (same day) | LATE_CAPTURE |
| C5 | No look-ahead (data_as_of ≤ trade_date) | MISSING_INPUT |
| C6 | 0050 data present for trade_date | INCOMPLETE_MARKET_DATA |
| C7 | ≥5,000 non-benchmark stocks on trade_date | INCOMPLETE_MARKET_DATA |
| C8 | Stock has ≥71 OHLCV bars ≤ trade_date | MISSING_INPUT |
| C9 | input_data_as_of ≤ trade_date (redundant with C5) | MISSING_INPUT |
| C10 | Market regime computable (structural, implied by C8) | — |

**Fail-closed:** Any failure returns the first failed classification immediately.

---

## 7. Append-only Design

### Unique Key
`(trade_date, stock_id, research_version)` — one decision per stock per day per version.

### Idempotency Logic

```
EXISTS same key?
├── YES + same payload_hash  → DUPLICATE_IDENTICAL (skip, return existing decision_id)
├── YES + different payload_hash → CAPTURE_CONFLICT (reject, preserve original, alert)
└── NO  → NEW_RECORD (insert)
```

**Why not `INSERT OR IGNORE`:** Silent ignore hides data corrections. `CAPTURE_CONFLICT` with same key but different payload exposes potential bugs or replay inconsistencies for manual review.

**Conflicts are non-destructive:** The original record is PRESERVED. The conflict result is returned to the caller for logging.

---

## 8. Data Integrity Gates

### Market Freshness Gates
| Gate | Condition | Fail Behavior |
|---|---|---|
| `check_0050_gate` | 0050 has data for trade_date | FAIL_NO_0050 |
| `check_market_coverage_gate` | ≥5,000 non-0050 stocks | FAIL_PARTIAL_MARKET |
| `check_stock_ohlc_gate` | Stock has ≥71 bars | FAIL_MISSING_STOCK |
| `check_look_ahead_gate` | data_as_of ≤ trade_date | FAIL_LOOK_AHEAD |
| `check_capture_window_gate` | captured on same day | FAIL_STALE_DATA |
| `check_freeze_date_gate` | trade_date ≥ 2026-11-06 | FAIL_STALE_DATA |

### Look-ahead Prevention
The `check_look_ahead_gate` and `check_prospective_eligibility` enforce that `input_data_as_of ≤ trade_date`. Any violation returns `MISSING_INPUT` and the decision is NOT marked `PROSPECTIVE_ELIGIBLE`.

This prevents: reconstructed features (future MA slopes), post-close price data, event-driven updates.

### Fail Closed
If any gate fails, `check_prospective_eligibility` returns immediately without proceeding to further checks. No `PROSPECTIVE_ELIGIBLE` decision is created when market data is incomplete.

---

## 9. Outcome Maturity

### Design: Decisions and Outcomes are SEPARATED

```
v3_prospective_decisions   (IMMUTABLE after insert)
    ↓ decision_id (read-only reference)
v3_prospective_outcomes    (append-only, versioned by outcome_version)
    horizon_days: 5 / 10 / 20
    maturity_status: NOT_MATURE / MATURE / INVALID / MISSING_DATA
```

**Rule: Original decision records are NEVER modified.** Outcomes are written to a separate table with their own version key `(decision_id, horizon_days, outcome_version)`.

### Maturity Thresholds (actual post-signal bars)
| Horizon | Bars Required | Trading Calendar |
|---|---|---|
| 5D | 5 post-signal bars | Real OHLCV from daily_prices |
| 10D | 10 post-signal bars | Real OHLCV from daily_prices |
| 20D | 20 post-signal bars | Real OHLCV from daily_prices |

Maturity uses actual trading days (bar count from daily_prices), not calendar days.

### Outcome Fields
- `gross_return`, `net_return`, `benchmark_return`, `gross_alpha`, `net_alpha`
- `entry_timing_flag`: BOTH_FILLED / D_SKIP / D_WAIT_UNFIRED (for attribution)
- `avoided_loss`, `missed_gain`: for E2 avoidance analysis
- `fill_status`, `fill_date`, `fill_price`, `exit_status`, `exit_date`, `exit_price`

---

## 10. Evidence Dashboard Contract

### Output: `EvidenceReport`

The evidence report is built from the research SQLite only. It never reads from production tables.

#### Capture Health
| Field | Type |
|---|---|
| `total_eligible_captures` | int — PROSPECTIVE_ELIGIBLE count |
| `total_rejected_captures` | int |
| `late_capture_count` | int |
| `missing_data_count` | int |
| `conflict_count` | int |
| `freeze_mismatch_count` | int |
| `latest_capture_date` | str or None |

#### Outcome Maturity
| Field | Type |
|---|---|
| `mature_5d` | int |
| `mature_10d` | int |
| `mature_20d` | int |
| `pending_outcomes` | int |

#### Performance
All performance fields are `None` until ≥20 mature outcomes exist.

#### Statistical Confidence
| Field | Note |
|---|---|
| `unique_dates` | effective independent date-blocks |
| `unique_stocks` | stock clusters |
| `stat_power_note` | warns when unique_dates < 20 |

### Evidence Level
| Level | Condition |
|---|---|
| `NO_PROSPECTIVE_EVIDENCE` | 0 PROSPECTIVE_ELIGIBLE decisions |
| `PROSPECTIVE_EVIDENCE_ACCUMULATING` | 1–49 eligible decisions |
| `PROSPECTIVE_EVIDENCE_SUFFICIENT` | ≥50 eligible decisions |

**Critical warning (always present when NO_PROSPECTIVE_EVIDENCE):**
"Historical in-sample results (Session 27: +3.66%) MUST NOT be cited as evidence of prospective OOS edge."

---

## 11. Synthetic Dry Run

All 14 scenarios from `run_synthetic_dry_run()` pass in memory:

| Scenario | Expected | Result |
|---|---|---|
| S1: Normal prospective capture | NEW_RECORD | ✓ |
| S2: Duplicate identical | DUPLICATE_IDENTICAL | ✓ |
| S3: Duplicate conflict (diff payload) | CAPTURE_CONFLICT | ✓ |
| S4: Late capture (next day) | NEW_RECORD (non-eligible) | ✓ |
| S5: Retrospective reconstruction | NEW_RECORD (non-eligible) | ✓ |
| S6: Missing 0050 | NEW_RECORD (non-eligible) | ✓ |
| S7: Freeze mismatch | NEW_RECORD (non-eligible) | ✓ |
| S8: Skip decision (AVOID_CHASING) | NEW_RECORD | ✓ |
| S9: Outcome not mature (5D) | INSERTED | ✓ |
| S10: Outcome mature (20D) | INSERTED | ✓ |
| S11: No production writes | PASS | ✓ |
| S12: Empty DB evidence report | NO_PROSPECTIVE_EVIDENCE | ✓ |
| S13: Evidence eligible count | 2 (S1+S8) | ✓ |
| S14: Evidence level | PROSPECTIVE_EVIDENCE_ACCUMULATING | ✓ |

---

## 12. Testing Results

| File | Tests | Status |
|---|---|---|
| `tests/test_v3_prospective_shadow.py` | 40 (PS-01 to PS-40) | 40/40 PASS |
| `tests/test_v3_walk_forward.py` | 40 (WF-01 to WF-40) | 40/40 PASS |
| `tests/test_v3_comparison_engine.py` | 30 (CP-01 to CP-30) | 30/30 PASS |
| Full regression | 1,901 total | 1,901 passed |
| Pre-existing FM11 failure | 1 (unrelated) | Pre-existing |

**Test coverage by category (PS tests):**

| Category | Tests |
|---|---|
| Freeze Manifest | PS-01..06 |
| Data Integrity Gates (0050, market, look-ahead, stale) | PS-07..16 |
| Eligibility Gate (10 conditions) | PS-17..22 |
| Append-only Repository (new, duplicate, conflict) | PS-23..26 |
| Outcome Separation & Maturity | PS-27..32 |
| Evidence Report | PS-33..36 |
| Synthetic End-to-end | PS-37..39 |
| Safety (no production writes) | PS-40 |

---

## 13. FM11 Root Cause

**Test:** `test_FM11_real_db_11_05_benchmark_only`  
**Expected:** `FreshnessStatus.BENCHMARK_ONLY_UPDATED` with `non_benchmark_count=0`  
**Actual:** `FreshnessStatus.FULL_MARKET_FRESH` (6,589 stocks present on 2026-11-05)

**Root Cause:** When the test was written, `platform.db` had only 0050 for 2026-11-05 (the cron ran at 18:28 CST on 2026-11-05 and was blocked at BENCHMARK_ONLY_UPDATED stage). After the cron run, the DailyPrice backfill pipeline retroactively added 6,588 non-0050 stocks for 2026-11-05. The test is a stale real-DB integration test — the DB state it was designed to verify no longer exists.

**Classification:** Pre-existing failure, unrelated to Sessions 27–29.

**Recommended fix (outside Session 29 scope):** Mark test with `pytest.mark.skip` or convert to a parameterized test that adapts to current DB state. Do NOT weaken the freshness gate logic.

---

## 14. Limitations

1. **No actual prospective decisions yet.** Framework is ready but `eligible_count=0`. First prospective signal requires Nov 6+ cron to write to `forward_signals` and V3 to process it.

2. **Cron acceptance not yet completed.** The 2026-11-06 16:00 scheduled run has not yet been verified. Until at least one PROSPECTIVE_ELIGIBLE hybrid decision exists, V3 shadow cannot be meaningfully activated.

3. **Outcome simulation not implemented.** The framework tracks maturity (`NOT_MATURE`/`MATURE`) but does not simulate fill logic. Full outcome evaluation (gross_return, net_return, etc.) requires a simulation step similar to `execution_simulator.py` applied to V3 decisions.

4. **No Neon storage.** All research is in local SQLite only. If production Neon is needed for long-term evidence storage, a separate schema migration would be required (not part of this session).

5. **Late capture classification.** The current implementation classifies a decision as `LATE_CAPTURE` if it's captured on a different calendar day than trade_date. In practice, Taiwan market closes 13:30 CST and data may not be fully processed until 15:30+. The 2-hour capture window (CAPTURE_WINDOW_HOURS=2) may need adjustment based on actual pipeline latency.

6. **Market coverage gate uses MIN_COVERED_STOCKS=5,000.** This is consistent with `full_market_freshness_gate.MIN_COVERED_STOCKS`. If the production gate changes, this value must be updated.

---

## 15. Activation Prerequisites

V3 Prospective Shadow can be activated only when ALL of the following pass:

| # | Prerequisite | Current Status |
|---|---|---|
| 1 | Existing Hybrid Cron acceptance PASS (first successful prospective write) | **PENDING** |
| 2 | V3 Parameter Freeze PASS | ✓ VERIFIED |
| 3 | Data Integrity Gates PASS (0050 + full market on activation day) | CONDITIONAL |
| 4 | Append-only Tests PASS | ✓ PASS |
| 5 | Idempotency Tests PASS | ✓ PASS |
| 6 | No Look-ahead PASS | ✓ PASS |
| 7 | Outcome Separation PASS | ✓ PASS |
| 8 | Full Regression PASS (excluding pre-existing FM11) | ✓ PASS |
| 9 | Production Isolation PASS | ✓ PASS |
| 10 | Explicit activation approval from stakeholder | **PENDING** |

**Items 1 and 10 are blocking.** The framework is architecturally ready but must NOT be activated as an automatic process until both blockers are resolved.

---

## 16. Final Verdict

### Framework
**`V3_PROSPECTIVE_FRAMEWORK_READY`**  
All framework components built, tested, and passing. Architecture correctly separates decisions from outcomes, enforces append-only semantics, and classifies eligibility with fail-closed logic.

### Data Integrity
**`DATA_INTEGRITY_PARTIAL`**  
Local platform.db is fresh (2026-11-05). Data integrity gates are implemented and tested. Full PASS requires the 2026-11-06 market session to complete with full TWSE+TPEx data before activation.

### Existing Cron
**`CRON_ACCEPTANCE_PENDING`**  
Cron ran on 2026-11-05 (blocked), 2026-11-06 scheduled run not yet confirmed. The trigger_source="cron_scheduled" string in cron_state.json is insufficient evidence of external scheduler invocation.

### Activation
**`ACTIVATION_CONDITIONAL`**  
Framework is ready. Cannot activate until: (1) Hybrid Cron produces first verified prospective write, and (2) explicit activation approval is granted.

### Evidence
**`NO_PROSPECTIVE_EVIDENCE`**  
Zero PROSPECTIVE_ELIGIBLE decisions exist as of 2026-11-06. Historical in-sample advantage (+3.66% net_alpha from Session 27) must NOT be cited as evidence of prospective OOS edge.

---

## Files

| File | Description |
|---|---|
| `src/research/v3_prospective_shadow.py` | Framework (SHADOW_VERSION: `v3_shadow_v1`) |
| `tests/test_v3_prospective_shadow.py` | 40 tests (PS-01 to PS-40) |
| `docs/v3_prospective_shadow_readiness.md` | This document |
| `src/research/v3_walk_forward.py` | Session 28 attribution engine |
| `docs/v3_walk_forward_validation.md` | Session 28 findings |
