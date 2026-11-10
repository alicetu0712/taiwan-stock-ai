# G03/G04 Statistical Eligibility — Session 56

## G03: Independent Cluster Count

**Status**: G03_FAIL (unchanged)  
**Required**: N≥10 genuine prospective clusters  
**Current**: N=0

### Why Still 0

| Reason | Detail |
|--------|--------|
| V3 not activated | No genuine prospective decisions generated |
| No ProspectiveRecorder in production | Cannot create immutable decision records |
| Backfill history | Does NOT count toward G03 (historical ≠ prospective) |
| Auth cluster N=3 | These are HISTORICAL 5D clusters, not prospective |

### Cluster Eligibility Requirements

For a cluster to count toward G03:
1. V3 decision recorded BEFORE market outcome (pre-outcome timestamped)
2. Parameters frozen at time of decision (be43e8ca977d9fdd ✓)
3. Code frozen at time of decision ✓
4. Immutable storage ✗
5. Genuine execution observable ✗
6. Independent of other clusters (non-overlapping holding windows)
7. Pre-registered analysis protocol ✓ (cluster_level_one_sample_t_test_v1)
8. Weekly spacing from adjacent clusters ✗ (G04 requirement)

### Cannot Bootstrap G03

MUST NOT use:
- Bootstrap replicates as independent clusters
- Sub-samples of existing signals as new clusters
- Historical signals re-labeled as prospective

## G04: Weekly Spacing

**Status**: G04_STRUCTURAL_FAIL (unchanged)  
**Requirement**: Weekly spacing between prospective clusters

### Why STRUCTURAL

The pipeline collects signals daily (continuous). No weekly-spacing mechanism exists in production. This is NOT a data gap — it is an algorithm/design constraint.

**Minimum fix**: Add weekly-cadence logic to V3 prospective shadow collection. This requires:
1. Algorithm change to collection trigger
2. Authorization to modify prospective collection logic

## Formal Ranking

| Assessment | Verdict |
|------------|---------|
| Exploration (N=3, historical, 5D) | RANKING_CONDITIONAL_RESEARCH_ONLY |
| Production ranking | RANKING_NOT_SUPPORTED |

### Why RANKING_NOT_SUPPORTED (Production)

- N=3 clusters (minimum for statistical claim is insufficient)
- SIGNIFICANCE_INCONCLUSIVE (CI: [-1.4pp, +3.0pp] includes 0)
- G03/G04 not met

### Why RANKING_CONDITIONAL_RESEARCH_ONLY (Exploration)

- Internal research use only: "V3 shows +0.81pp vs A_direct based on 3 historical strict fill dates"
- Explicitly labeled as CONDITIONAL RESEARCH exploration
- Cannot inform production trading decisions

## G03 Eligibility Simulation

| Future Scenario | Eligible Clusters | G03 Pass? |
|----------------|-------------------|-----------|
| AUTH01 executed | +0 (backfill) | NO |
| TPEx patch deployed | +0 | NO |
| V3 activated (now) | +0 immediately | NO (must wait for outcomes) |
| V3 + 10 weeks | Potentially +2–3/week | Possibly YES in ~3–5 months |

## V3 Activation Prerequisite

G03 cannot be met without V3 activation. V3 is ACTIVATION_BLOCKED. This is a hard dependency:

G03 → V3 Activation → Cron Authorization → Stage B Cron Probe Authorization → Stage B Never Authorized
