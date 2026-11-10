# Calendar End-to-end Audit — Session 52

**Analysis date**: 2026-11-10  
**Session**: S52  
**SSOT**: `src/research/calendar_contract_s50.py` → `get_corrected_exit()`  
**Verdict**: CALENDAR_E2E_VERIFIED

---

## Corrected Exit Dates (all 6/6 verified)

| Fill date | 5TD exit (corrected) | 20TD exit (corrected) | 5TD S46 error | 20TD S46 error |
|-----------|---------------------|----------------------|---------------|----------------|
| 2026-10-13 | 2026-10-20 | 2026-11-12 | 2026-10-21 (Δ+1d) | 2026-11-14 (Δ+2d) |
| 2026-10-14 | 2026-10-21 | 2026-11-13 | 2026-10-28 (Δ+5d) | 2026-11-17 (Δ+4d) |
| 2026-10-16 | 2026-10-27 | 2026-11-17 | 2026-11-05 (Δ+7d) | 2026-11-19 (Δ+2d) |
| 2026-10-21 | 2026-10-30 | 2026-11-20 | 2026-10-30 (✓) | 2026-11-24 (Δ+4d) |
| 2026-10-22 | 2026-11-02 | 2026-11-23 | 2026-11-02 (✓) | 2026-11-25 (Δ+2d) |
| 2026-10-28 | 2026-11-04 | 2026-11-25 | 2026-11-04 (✓) | 2026-12-02 (Δ+7d) |

All 6/6 5TD matches ✓, all 6/6 20TD matches ✓.

---

## Call-site Inventory

| Module | Reference | Status | Frozen? | Risk |
|--------|-----------|--------|---------|------|
| `prospective_comparison_s46.py` | `_CALENDAR_5TD`, `_CALENDAR_20TD` | LEGACY_FROZEN | ✓ | LOW |
| `cluster_eligibility_expansion_s47.py` | S46 reference | LEGACY_FROZEN | ✓ | LOW |
| `pipeline_coverage_audit_s48.py` | `_CORRECT_5TD`, `_CORRECT_20TD` | LEGACY_FROZEN | ✓ | LOW |
| `prospective_evidence_audit_s49.py` | `get_corrected_calendar_exit()` | LEGACY_FROZEN | ✓ | LOW |
| `calendar_contract_s50.py` | `get_corrected_exit()` | SSOT_COMPLIANT | — | NONE |
| `pipeline_root_cause_s51.py` | no calendar math | NO_TRADING_DAY_OFFSET | — | NONE |
| `prospective_recorder_s51.py` | no calendar math | NO_TRADING_DAY_OFFSET | — | NONE |
| `pipeline_forensics_s52.py` | no calendar math | NO_TRADING_DAY_OFFSET | — | NONE |
| `provenance_audit_s52.py` | `get_corrected_exit()` | SSOT_COMPLIANT | — | NONE |

No LEGACY_ACTIVE_BUG or non-frozen modules using erroneous dates.

---

## S46 Legacy Isolation

S46 inline dicts contain erroneous dates preserved for audit. These dicts are **not callable from any active research path**. The module is frozen (not modified since S46). No path from active code calls the S46 erroneous values.

---

## Off-by-one Analysis

Risk: LOW. The SSOT uses hardcoded trading-day calendars, not `timedelta(days=N)`. S46's errors (Δ ranging from +1d to +7d) were due to incorrect trading-day counting in the inline dicts, not off-by-one in arithmetic. The corrected SSOT was verified against official Taiwan trading calendar.

---

## Holiday Handling

SSOT hardcodes trading days. Taiwan national holidays are excluded from trading-day sequences. No dynamic calendar lookup — future fill clusters beyond Oct 28 will require new SSOT entries.

---

## 20D Readiness (from calendar perspective)

- Earliest 20TD maturity: **2026-11-12** (Oct 13 cluster, 2 calendar days from analysis date)
- Latest 20TD maturity: **2026-11-25** (Oct 28 cluster)
- All 6 clusters: BLOCKED_PIPELINE (pipeline_data_available=False overrides)
