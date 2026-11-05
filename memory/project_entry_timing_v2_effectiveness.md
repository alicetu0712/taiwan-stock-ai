---
name: project-entry-timing-v2-effectiveness
description: Entry Timing V2 Effectiveness & OOS Validation analysis — 2953 signals, CONDITIONAL verdict, key subgroup findings
metadata:
  type: project
---

Commit `6602c3b` — Entry Timing V2 effectiveness analysis complete.

**Core results (2024-10-01 to 2026-09-15, 2,953 paired signals):**
- Overall Paired Delta: +0.06%, 95% CI [−0.05%, +0.16%] → CI spans zero → CONDITIONAL
- OOS (2026-07 to 2026-09): delta +0.06%, CI [−0.23%, +0.34%], PASS
- Walk-forward: 10/10 PASS
- Sensitivity: ROBUST (0/5 variants fragile)
- MA20 Audit: ACCURATE (100% within 1%)

**Subgroup findings (hypothesis-generating, pre-Bonferroni):**
- WAIT_FOR_PULLBACK: delta +0.25%, fill 75.5%, n=249
- Bear regime: delta +0.36%, CI [+0.02%, +0.69%]
- Flat MA20 trend: delta +0.41%, CI [+0.09%, +0.70%]
- Both subgroup CIs do NOT survive Bonferroni correction (20 comparisons → α=0.0025)

**Key files:**
- `src/research/effectiveness_analyzer.py` — pure-function analysis engine
- `scripts/run_effectiveness_analysis.py` — generates data/effectiveness_analysis.json
- `tests/test_effectiveness_analyzer.py` — 33 tests (EA01–EA23)
- `docs/entry_timing_v2_effectiveness_analysis.md` — full report
- Dashboard: 🔬 有效性分析 tab reads from data/effectiveness_analysis.json

**Why:** Per research spec, verdict cannot be upgraded to VALIDATED until OOS CI is entirely positive and subgroup hypotheses are tested on new data.

**How to apply:** 1332 tests pass. Next step = collect 500+ production ForwardSignal fills with 20D outcomes before re-evaluating VALIDATED status.

[[project_entry_timing_v2]]
