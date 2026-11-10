# Calendar Call-site Audit — Session 51

**Analysis date**: 2026-11-10  
**Session**: S51  
**SSOT**: `src/research/calendar_contract_s50.py` → `get_corrected_exit(fill_date, "5TD"/"20TD")`

---

## Call-site Inventory

| Module | Reference | Status | Frozen? | Notes |
|--------|-----------|--------|---------|-------|
| `prospective_comparison_s46.py` | `_CALENDAR_5TD`, `_CALENDAR_20TD` (inline dicts) | LEGACY_FROZEN | Yes | S46 frozen; not modified |
| `cluster_eligibility_expansion_s47.py` | References S46 calendar | LEGACY_FROZEN | Yes | S47 frozen |
| `pipeline_coverage_audit_s48.py` | `_CORRECT_5TD`, `_CORRECT_20TD` (inline dicts) | LEGACY_FROZEN | Yes | S48 frozen; corrected values inline |
| `prospective_evidence_audit_s49.py` | `get_corrected_calendar_exit()` | LEGACY_FROZEN | Yes | S49 frozen; local helper mirrors SSOT |
| `calendar_contract_s50.py` | `get_corrected_exit()` | SSOT_COMPLIANT | No | Canonical; new callers use this |
| `pipeline_root_cause_s51.py` | No trading-day offset | NO_TRADING_DAY_OFFSET | No | Date strings only; no calendar math |
| `prospective_recorder_s51.py` | No trading-day offset | NO_TRADING_DAY_OFFSET | No | Classification logic; no calendar math |

---

## S46 Isolation Confirmed

The S46 inline calendar dicts (`_CALENDAR_5TD`, `_CALENDAR_20TD`) contain the **erroneous** exit dates (documented in S47). These are preserved verbatim in the frozen module for auditability. They are **not** called from any active code path.

The S50 SSOT `get_corrected_exit()` returns corrected dates for all 6 fill clusters:

| Fill date | 5TD exit (corrected) | 20TD exit (corrected) | 5TD exit (S46 erroneous) |
|-----------|---------------------|----------------------|--------------------------|
| 2026-10-13 | 2026-10-20 | 2026-11-12 | (S46 had wrong date) |
| 2026-10-14 | 2026-10-21 | 2026-11-13 | (S46 had wrong date) |
| 2026-10-21 | 2026-10-28 | 2026-11-20 | (S46 had wrong date) |
| 2026-10-22 | 2026-10-29 | 2026-11-21 | (S46 had wrong date) |
| 2026-10-27 | 2026-11-03 | 2026-11-26 | (S46 had wrong date) |
| 2026-10-28 | 2026-11-04 | 2026-11-27 | (S46 had wrong date) |

---

## Rules for New Callers

Any new code that needs trading-day offsets **must** import from `calendar_contract_s50`:

```python
from src.research.calendar_contract_s50 import get_corrected_exit
exit_date = get_corrected_exit("2026-10-13", "20TD")  # → "2026-11-12"
```

Do not copy inline calendar dicts. Do not reference S46–S49 calendar helpers from new modules.

---

## S51 New Modules: Compliant

Both `pipeline_root_cause_s51.py` and `prospective_recorder_s51.py` contain no calendar offset computations (status: NO_TRADING_DAY_OFFSET). No SSOT violation introduced in S51.
