# Production Fingerprints — Session 48

**Date:** 2026-11-09  
**Session:** S48  
**Verdict:** ALL_FROZEN_UNCHANGED

---

## Production Fingerprints

| Item | Value | Verified |
|---|---|---|
| `forward_signals` total | 2605 | ✓ |
| `forward_signals` v8.0 valid | 2236 | ✓ |
| `forward_signals` v8.0 buy+strong_buy | 237 | ✓ |
| `daily_prices` max date | 2026-11-05 | ✓ |
| `daily_prices` Nov 04 rows | 6957 (no duplicates) | ✓ |
| Baseline fingerprint | `09c04e8c4059d87e` | ✓ |
| V3 Parameter Hash | `be43e8ca977d9fdd` | ✓ |
| Crontab Hash | `3acaf480cb5dcdd44f40dd9d464955a1` | ✓ |
| MODEL_VERSION | v8.0 | ✓ |
| Frozen baseline clusters | 3 (Oct 13/14/16) | ✓ |
| Frozen baseline delta | +0.81 pp | ✓ |

---

## What Changed in S48

**New files only (no production modifications):**

| File | Type | Description |
|---|---|---|
| `src/research/pipeline_reliability_s48.py` | Research module | Pipeline root cause, coverage matrix, backfill dry-run |
| `src/research/calendar_contract_s48.py` | Research module | 20D/5D calendar correction, readiness, guardrails |
| `tests/test_session48_pipeline_reliability.py` | Tests | 107 new tests (TC01–TC34) |
| `docs/pipeline_root_cause_session48.md` | Documentation | PART B |
| `docs/data_coverage_quality_gate_session48.md` | Documentation | PART C |
| `docs/backfill_dryrun_session48.md` | Documentation | PART D |
| `docs/calendar_contract_correction_session48.md` | Documentation | PART E |
| `docs/strict_5d_readiness_session48.md` | Documentation | PART F |
| `docs/guardrails_session48.md` | Documentation | PART G |
| `docs/production_fingerprints_session48.md` | Documentation | This file |
| `docs/session48_final_verdict.md` | Documentation | PART L |

---

## What Was NOT Modified

- `data/platform.db` (production SQLite): READ-ONLY
- `forward_signals`: no INSERT, UPDATE, or DELETE
- `daily_prices`: no INSERT, UPDATE, or DELETE
- `src/research/prospective_comparison_s46.py`: not modified (S46 date errors documented but not corrected; correction requires separate authorization)
- Any Cron, Crontab, GitHub Actions
- Any production Neon DB
- Any v8.0 signal generation logic
- V3 parameters (`be43e8ca977d9fdd` hash verified unchanged)
- Hybrid P1–P4

---

## Dataset Fingerprint Note

The baseline fingerprint changed from `2c8b2475c8fdc457` (S44 reference) to `09c04e8c4059d87e` between S44 and S47. This was caused by the Nov 04/05 manual backfill changing `daily_prices_max`. The fingerprint change does not affect any baseline metrics:
- Grand mean delta: +0.81 pp (unchanged)
- Strict cluster count: 3 (unchanged)
- Statistical verdict: SIGNIFICANCE_INCONCLUSIVE (unchanged)
