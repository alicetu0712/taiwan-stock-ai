# Guardrail Remediation Assessment — Session 46

**Date:** 2026-11-09  
**Session:** S46 — PART H  
**Overall Verdict:** GUARDRAILS_FAIL (G03 and G04 unchanged)

---

## Guardrail Status Summary

| ID | Name | Threshold | Current | Status |
|---|---|---|---|---|
| G01 | Prospective provenance | All GENUINE_PROSPECTIVE | 6/6 non-null ✓ | PASS |
| G02 | Signal freshness gate | ≥1 new cluster since last session | Oct 28 added | CONDITIONAL |
| G03 | Minimum strict cluster count | ≥10 strict clusters | 3 | FAIL |
| G04 | 5D window independence | <30% adjacent overlap | 80% overlap | FAIL |

---

## G01 — Prospective Provenance (PASS)

All 6 non-null fill clusters verified as GENUINE_PROSPECTIVE (see `provenance_verification_session46.md`):
- `locked_at < execution_date` for all 6 clusters
- `execution_price_type = 'NEXT_OPEN'` for all clusters
- Append-only schema; no UPDATE path
- 1 NULL exec_date cluster (Oct 28 signal) is excluded from comparison, not falsely classified

**Remediation required:** None.

---

## G02 — Signal Freshness Gate (CONDITIONAL)

S46 added Oct 28 fill to the expanded research snapshot:
- New result: D = +2.75% (directionally consistent with frozen baseline)
- Status: RESEARCH_ONLY (not part of strict baseline, G03 still FAIL)

However, Oct 22 fill remains PENDING_NEON, and pipeline is blocked (Nov 06, Nov 09 missing data).

**Remediation required:** Pipeline restoration. Next eligible new cluster after Nov 09 backfill succeeds.

---

## G03 — Minimum Strict Cluster Count (FAIL — STRUCTURAL)

| Session | Strict Clusters | Status |
|---|---|---|
| S44 | 3 | FAIL |
| S45 | 3 | FAIL |
| S46 | 3 | FAIL |

The strict cluster count has not increased across three sessions. The 3 MATURE_BUT_DATA_INCOMPLETE clusters (Oct 21, Oct 22, Oct 28) all fail the proxy exit-day test (`_count_exit_days < 5` from local SQLite). They are blocked by the data freshness gap, not by calendar maturity.

**Root cause:** Pipeline was not running Nov 02–08. Thin data for Oct 29/30/Nov 02/03 prevents the proxy counter from reaching 5 for Oct 21/22/28 fills.

**Remediation path:**
1. Restore pipeline: backfill Nov 02, Nov 03, Nov 06, Nov 09 → intermediate dates become thick
2. Oct 21 fill becomes strict once Oct 30 has ≥50 stocks in SQLite
3. Oct 22 fill becomes strict once Nov 02 has ≥50 stocks
4. Oct 28 fill remains MATURE_BUT_DATA_INCOMPLETE unless Oct 29–Nov 03 are backfilled
5. After backfill: re-run `canonical_5d_baseline_s44.py` → new strict count
6. G03 PASS requires reaching at least 10 strict clusters (needs ~7 more sessions of live data)

**Timeline estimate:** G03 cannot be remediated in a single session. Minimum ~7 more weeks of uninterrupted prospective data needed.

---

## G04 — Window Independence (FAIL — DESIGN CONSTRAINT)

Adjacent fill clusters share 80% of their signal pool because:
- Signal generation runs daily
- Each fill picks the top-N stocks from the same universe
- 5D windows from adjacent fills overlap substantially

**Remediation options:**
1. **Weekly fill spacing**: use only one fill per week (non-overlapping 5D windows). Loses data efficiency.
2. **Sector stratification**: split universe into non-overlapping sectors and alternate. Requires redesign.
3. **Bootstrap CI on cluster-level means**: explicitly models correlation. Acceptable only with ≥10 clusters.

**Current state:** No design change authorized in S46. G04 remains FAIL.

**Remediation required:** Design decision in a future session, independent of data freshness.

---

## Combined Verdict

| Dimension | Verdict |
|---|---|
| Provenance integrity | VERIFIED |
| Data freshness | BLOCKED |
| Statistical power | INSUFFICIENT (N=3 strict) |
| Window design | FAIL (design constraint) |
| **Overall** | **GUARDRAILS_FAIL** |

ACTIVATION_BLOCKED remains unchanged from S45. G03 and G04 failures are independent blockers — both must be resolved before activation can be considered.
