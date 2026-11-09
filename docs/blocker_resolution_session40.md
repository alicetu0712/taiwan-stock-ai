# Blocker Resolution — Session 40

**Date:** 2026-11-09  
**Session:** 40  

---

## Blockers Resolved

### RESOLVED: EG-05 Benchmark Availability

- **Before**: Listed as CONDITIONAL (0050's status unconfirmed)
- **After**: RESOLVED
- **Evidence**: Confirmed 0050 in `daily_prices` for all 17 Oct-Nov 2026 dates. `SELECT COUNT(*) FROM daily_prices WHERE stock_id='0050' AND date >= '2026-10-12'` → 17 rows.
- **Test**: BM05 passes
- **Remaining limitation**: 0050 is an ETF and was excluded from the signal universe — this is correct. It remains usable as benchmark only.

---

### RESOLVED: EG-09 Duplicate Signals

- **Before**: Listed as unverified
- **After**: RESOLVED
- **Evidence**: 0 duplicates confirmed from Session 37 analysis. Verified in Session 40 via direct query.
- **Test**: BM05-category confirmed
- **Remaining limitation**: None.

---

## Blockers Partially Resolved

### PARTIAL: EG-02a — Point-in-time Universe (Oct 2026 Window)

- **Before**: OPEN (no listing_date column → cannot verify point-in-time)
- **After**: PARTIAL
- **Method**: Established that Oct 2026 `forward_signals` are **de facto point-in-time** because the production system only processes stocks present in the master table at signal generation time.
- **Evidence**: Production system architecture (live-generated signals); 3 confirmed delistings (2867, 6806, 6288) are NOT in the Oct 2026 signal pool.
- **Remaining limitation**: Historical backtest era (EG-02b) remains UNVERIFIED. Formal `listing_date` column not added (requires authorisation).

---

### PARTIAL: EG-10 — Overlapping Hold-period Samples

- **Before**: OPEN (no cluster correction)
- **After**: PARTIAL
- **Method**: Explicitly documented that effective N = 7 (not 274). Added STATISTICAL_CONFIDENCE_UNVERIFIED flag to all 5D comparison results. CI from bootstrap is overoptimistic.
- **Evidence**: 7 signal dates within 16 calendar days. Comparison engine confirmed.
- **Remaining limitation**: Full cluster-adjusted CI not yet implemented. Would require date-level cluster bootstrap.

---

### PARTIAL: EG-04 — Market Data Coverage (5D)

- **Before**: OPEN
- **After**: PARTIAL
- **Method**: Ran `V3ComparisonEngine.run_data_readiness_audit()`. Confirmed 274/344 (79.7%) signals have ≥5D post-bars.
- **Evidence**: DataReadinessReport: `n_5d_eligible=274, verdict_5d='READY'`
- **Remaining limitation**: 10D (1/344) and 20D (0/344) remain insufficient.

---

### PARTIAL: EG-08 — Missing Outcomes (for 5D Horizon)

- **Before**: CRITICAL OPEN (zero outcomes in `forward_signals.fwd_return_20d`)
- **After**: PARTIAL
- **Method**: Established that the V3ComparisonEngine computes 5D outcomes from `daily_prices` (read-only) WITHOUT modifying `forward_signals`. This is a research-only outcome computation.
- **Evidence**: `V3ComparisonEngine.run_comparison(horizon_days=5)` returned 274 results with actual returns.
- **Remaining limitation**: `forward_signals.fwd_return_20d` still NULL for all records. 20D outcomes must wait until 2026-12-02. 5D outcome computation is a research engine artifact, not production data.

---

### PARTIAL: V1V2-DEF — Parameter Hashes (RECOVERED)

- **Before**: OPEN (no parameter hashes for V1 and V2)
- **After**: PARTIAL (hashes computed = RECOVERED status)
- **Method**: Computed deterministic hashes from current code constants:
  - V1 (`v1_signal_only`): `13113e2933ec3017`
  - V2 (`v2_entry_timing`): `258513077a5ca6a0` (from `ma20_pullback_upper=0.03, ma20_pullback_lower=-0.05, too_extended_ma20_gap=15.0, stop_buffer=0.03`)
- **Evidence**: `src/analyzers/entry_timing.py` module-level constants, `version_definition_recovery.py`
- **Remaining limitation**: RECOVERED (not VERIFIED) — cannot confirm that current parameters match Sessions 23-25 usage without frozen commits.

---

## Blockers Still Open

| ID | Category | Severity | Required For |
|---|---|---|---|
| EG-02b | C | HIGH | Historical backtest era point-in-time verification |
| EG-12 | C | HIGH | Survivorship bias correction (3 delistings) |
| EG-07 | C | MEDIUM | Corporate action verification |
| EG-08a (20D) | D | CRITICAL | 20D outcome comparison (wait until Dec 2026) |
| STAT-POWER | D | HIGH | Statistical adequacy (need 25+ dates) |
| REGIME | D | HIGH | Multi-regime comparison |

---

## What Changed This Session

| Metric | Before (S39) | After (S40) | Change |
|---|---|---|---|
| Comparison verdict | COMPARISON_BLOCKED | RANKING_CONDITIONAL | Upgraded |
| Available 5D outcomes | 0 | 274 | +274 |
| Eligible window | None | CONDITIONAL 5D | First window |
| V1/V2 parameter hashes | Missing | RECOVERED | Added |
| V3 paired comparison | Not run | Run (N=267-274) | Executed |
| Blockers resolved | 0 | 2 fully + 5 partial | Progress |
| Tests | 2170 | 2220 | +50 |
