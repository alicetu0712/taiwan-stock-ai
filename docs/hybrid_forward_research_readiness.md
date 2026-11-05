# Hybrid Forward Shadow — Forward Research Readiness

**Status:** AWAITING_FIRST_PROSPECTIVE_DECISION  
**Date:** 2026-11-05

---

## Prospective Data Classification

| Classification | Valid OOS? | Condition |
|---|---|---|
| `PROSPECTIVE` | ✅ Full OOS value | trade_date ≥ 2026-11-05, L2 PASS, captured same/next trading day |
| `LATE_CAPTURE` | ⚠️ Acceptable | trade_date ≥ 2026-11-05, captured 2+ days later (e.g., Mac sleep) |
| `RETROSPECTIVE_RECONSTRUCTION` | ℹ️ Historical only | trade_date < 2026-11-05 |
| `INVALID_DATA` | 🛑 BUG | input_data_as_of < trade_date |

**Cutoff date:** 2026-11-05 (cron installation date). All decisions before this are RETROSPECTIVE_RECONSTRUCTION.

---

## Current State (as of 2026-11-05)

| Metric | Value |
|---|---|
| Total hybrid_forward_decision rows | 21 |
| PROSPECTIVE count | **0** |
| RETROSPECTIVE_RECONSTRUCTION | 21 (trade_date = 2026-11-04) |
| LATE_CAPTURE | 0 |
| INVALID_DATA | 0 |
| First scheduled cron run | ⏳ 2026-11-06 (五) 16:00 Taiwan |

---

## Expected Timeline for Statistical Evidence

| Milestone | Estimated Date | Condition |
|---|---|---|
| First PROSPECTIVE decision | 2026-11-06 (if signals exist) | Full-market fresh + shadow SUCCESS |
| First 5D outcomes | ~2026-11-13 | 5 trading days after first decision |
| First 20D outcomes | ~2026-11-26 | 20 trading days after first decision |
| 50 PROSPECTIVE decisions | ~2027-02 (if 1–2 signals/day) | Minimum for meaningful statistics |
| 100 PROSPECTIVE decisions | ~2027-04 | Minimum for bootstrap CI |

---

## Research Questions This Data Will Answer

1. **Does the entry timing model add value over V1 baseline?**  
   Comparison: PROSPECTIVE decisions vs. V1 research_version signals on same dates

2. **What is the out-of-sample hit rate for Hybrid V1?**  
   Metric: `fwd_return_5d > 0` rate among PROSPECTIVE decisions

3. **Is the BUY/STRONG_BUY threshold well-calibrated?**  
   Metric: outcome distribution by label (ENTRY_READY vs. WAIT_*)

4. **How often does the system block correctly vs. miss good entries?**  
   Metric: BLOCKED_* days vs. PROSPECTIVE days with positive outcomes

---

## Verification Commands (run after 2026-11-06 16:00)

```bash
# Count prospective decisions
python3 -c "
import sqlite3
conn = sqlite3.connect('data/platform.db')
rows = conn.execute('''
  SELECT capture_classification, trade_date, COUNT(*)
  FROM hybrid_forward_decision
  WHERE trade_date >= '2026-11-05'
  GROUP BY capture_classification, trade_date
  ORDER BY trade_date
''').fetchall()
for r in rows:
    print(r)
conn.close()
"

# Check cron state
cat data/.cron_state.json | python3 -m json.tool

# Check active alerts
python3 -c "
from src.research.alert_state import AlertStateManager
from datetime import date
mgr = AlertStateManager()
active = mgr.active_alerts(date.today())
print(f'Active alerts today: {len(active)}')
for a in active:
    print(f'  {a.alert_type}: {a.message} (count={a.count})')
"
```

---

## Prospective Research Readiness Checklist

- [x] Cron installed (2026-11-05)
- [x] Full-market freshness gate implemented and tested
- [x] Retry policy (3 × 30 min) implemented and tested
- [x] Alert state deduplication implemented and tested
- [x] Dashboard G0 shows retry count and active alerts
- [x] capture_classification field in schema (PROSPECTIVE / LATE_CAPTURE / RETROSPECTIVE_RECONSTRUCTION)
- [ ] First scheduled run succeeds (AWAITING 2026-11-06)
- [ ] First PROSPECTIVE decision written
- [ ] 5D outcomes available (~2026-11-13)
- [ ] 20D outcomes available (~2026-11-26)
