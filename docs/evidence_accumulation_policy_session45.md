# Evidence Accumulation Policy — Session 45

**Date:** 2026-11-09  
**Session:** S45  
**Module:** `src/research/evidence_policy_s45.py`  
**Ledger Version:** v1.0-s45

---

## Purpose

Defines the 12-point checklist that every new evidence record must pass before it can be incorporated into the strict comparison pool. Extends the Session 44 Canonical Research Data Contract.

---

## 12-Point Evidence Checklist

| ID | Check | Required | Failure Consequence |
|---|---|---|---|
| P01 | Strategy version verified (model_version = v8.0) | Yes | Exclude from comparison |
| P02 | Parameter hash verified (`be43e8ca977d9fdd`) | Yes | Abort comparison |
| P03 | Trading calendar verified (≥50-stock threshold) | Yes | Flag G01 violation |
| P04 | Execution provenance verified (NEXT_OPEN_SIMULATED) | Yes | Exclude — fill type unknown |
| P05 | Universe eligibility (common stock, not ETF-only) | Yes | Exclude from pool |
| P06 | Outcome mature (5D: 5 real TDs; 20D: 20 real TDs) | Yes | Defer |
| P07 | Price complete for all signal stocks on exit date | Yes | Exclude signal if missing; abort if >10% |
| P08 | Benchmark (0050) complete on fill + exit dates | Yes | Flag G07 violation |
| P09 | Comparison opportunity matched (A_direct baseline available) | Yes | Cannot compute paired delta |
| P10 | No look-ahead bias (signal locked before execution date) | Yes | DISQUALIFY — irrecoverable |
| P11 | No survivorship bias misrepresentation | Yes | DISQUALIFY — irrecoverable |
| P12 | No duplicate evidence inflation (same stock+date+window) | Yes | Deduplicate before inference |

---

## Provenance Classes

| Class | Definition | Eligible for Strict Comparison? |
|---|---|---|
| `GENUINE_PROSPECTIVE` | Signal locked before execution; time-stamped before market outcome | **Yes** (if P06 passes) |
| `RETROSPECTIVE_RECONSTRUCTION` | Signal re-generated using historical prices | **No** — must be labelled RETRO |
| `HISTORICAL_BACKTEST` | In-sample backtest; look-ahead bias risk | **No** |
| `UNVERIFIED` | Provenance cannot be established | **No** until verified |

---

## Current Ledger Status

| Fill Date | Eligible (P06) | Provenance | Status |
|---|---|---|---|
| Oct 13 | ✓ | GENUINE_PROSPECTIVE | **ELIGIBLE** |
| Oct 14 | ✓ | GENUINE_PROSPECTIVE | **ELIGIBLE** |
| Oct 16 | ✓ | GENUINE_PROSPECTIVE | **ELIGIBLE** |
| Oct 21 | ✗ (3/5 TDs) | GENUINE_PROSPECTIVE | DEFERRED |
| Oct 22 | ✗ (2/5 TDs) | GENUINE_PROSPECTIVE | DEFERRED |
| Oct 28 | ✗ (NULL exec) | GENUINE_PROSPECTIVE | N/A (excluded) |

---

## Deduplication Rules

Records must be unique on the combination of:
- `stock_id`
- `signal_date`
- `execution_date`
- `holding_window_start`
- `holding_window_end`

A single market event (e.g., TSMC on Oct 12) generates **one** signal record and **one** cluster contribution. Multiple signals for the same stock on the same date are a data integrity error.

---

## Overlapping Window Note

Adjacent 5D windows (G04) overlap ~80%. Deduplication by stock/date/window does not resolve the overlap issue — it must be handled at the **cluster aggregation** level (not signal level). This is documented as a DESIGN_CONSTRAINT in the guardrail assessment.
