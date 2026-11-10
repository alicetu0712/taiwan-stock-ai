# Pipeline Root Cause Evidence Matrix — Session 51

**Analysis date**: 2026-11-10  
**Session**: S51  
**Module**: `src/research/pipeline_root_cause_s51.py`

---

## Summary

Five pipeline tiers covering 2026-10-13 → 2026-11-09 were diagnosed against 10 pipeline stages each, producing a structured evidence matrix (`PipelineRootCauseEvidenceMatrix`).

| Tier | Dates | Stock count | Trigger | Verdict |
|------|-------|-------------|---------|---------|
| TIER_655_FILL | Oct 13–28 | 655 | yfinance bulk (manual) | ROOT_CAUSE: TWSE_BULK_RETURNS_CURRENT_DATE |
| TIER_1_PROXY | Oct 29/30, Nov 02/03 | 1 (0050 only) | recover_ohlc_0050.py | ROOT_CAUSE: MAIN_PIPELINE_SILENT_FAILURE |
| TIER_6957_BACKFILL | Nov 04/05 | 6,957 | Manual backfill (fc2b4b0f) | COMPLETE — signals RETROSPECTIVE_RECONSTRUCTION |
| BLOCKED_QG | Nov 06 | 0 | hybrid_shadow_cron | ROOT_CAUSE: QUALITY_GATE_FAIL (DIRECTLY_CONFIRMED) |
| BLOCKED_STALE_DATA | Nov 09 | 0 | hybrid_shadow_cron | ROOT_CAUSE: TWSE api_date mismatch (DIRECTLY_CONFIRMED) |

---

## Evidence by Stage (abbreviated)

### TIER_655_FILL (Oct 13–28)
- **PROVIDER_RESPONSE** — HYPOTHESIS_ONLY: Bulk TWSE/TPEx API returns current-day data regardless of `date=` param (confirmed S50); yfinance used as fallback
- **COVERAGE_QG** — STRONGLY_SUPPORTED: 655 rows written; `_MIN_COVERED_STOCKS = 5000` threshold not met, implying non-standard write path
- **DATABASE_PERSISTENCE** — DIRECTLY_CONFIRMED: 655 rows in `daily_prices` for each fill date
- **DOWNSTREAM_RESEARCH** — NOT_APPLICABLE: v8.0 signals locked from prior full data; fill tier does not gate forward signals

### TIER_1_PROXY (Oct 29/30, Nov 02/03)
- **SCHEDULER_TRIGGER** — HYPOTHESIS_ONLY: `run_daily.py`/`main.py` imported (empty log files created) but `run_pipeline()` crashed before first `logger.info()` — silent failure
- **COVERAGE_QG** — HYPOTHESIS_ONLY: `recover_ohlc_0050.py --execute` wrote 0050-only rows (rowids 550256–550259, consecutive batch)
- **ROOT_CAUSE**: MAIN_PIPELINE_SILENT_FAILURE + manual proxy recovery

### TIER_6957_BACKFILL (Nov 04/05)
- **DATABASE_PERSISTENCE** — DIRECTLY_CONFIRMED: 6,957 rows, commit fc2b4b0f
- **DOWNSTREAM_RESEARCH** — DIRECTLY_CONFIRMED: `hybrid_forward_decision` rows generated Nov 04; classified RETROSPECTIVE_RECONSTRUCTION (pre RULE_FREEZE_DATE 2026-11-05)

### BLOCKED_QG (Nov 06)
- **COVERAGE_QG** — DIRECTLY_CONFIRMED: `2026-11-06: quality gate FAILED — not writing to DB` (from `hybrid_cron.log`)
- **DATABASE_PERSISTENCE** — DIRECTLY_CONFIRMED: 0 rows written
- **SECURITY_MAPPING** — HYPOTHESIS_ONLY: S38 reclassification or symbol count issue suspected

### BLOCKED_STALE_DATA (Nov 09)
- **PROVIDER_RESPONSE** — DIRECTLY_CONFIRMED: `TWSE api_date=2026-11-06 != target 2026-11-09` (from `hybrid_cron.log`)
- **SCHEDULER_TRIGGER** — DIRECTLY_CONFIRMED: cron fired at 08:00:17Z (16:00:17 Taiwan), retried 3×30min
- **Final state**: `BLOCKED_STALE_DATA` in `.cron_state.json`

---

## Evidence Level Distribution

| Level | Count |
|-------|-------|
| DIRECTLY_CONFIRMED | 18 |
| STRONGLY_SUPPORTED | 6 |
| HYPOTHESIS_ONLY | 14 |
| INSUFFICIENT_EVIDENCE | 8 |
| NOT_APPLICABLE | 4 |

---

## Production Fingerprints (verified)

- `forward_signals` count = 2605 (unchanged)
- `daily_prices` max date = 2026-11-05 (unchanged)

See also: `docs/production_fingerprints_session51.md`
