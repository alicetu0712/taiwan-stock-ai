# Session 53: AUTH01 Backfill Authorization Package

**Status**: PENDING_USER_AUTHORIZATION  
**Safety**: Manifest only. No production writes in this session.

## Purpose

This document is the per-date authorization package for restoring missing price data for Oct 29–Nov 09. All INSERT candidates require explicit user authorization before execution.

## Date Manifest

| Date | Trading Day | Existing Non-0050 Rows | Action | Priority | AUTH01 |
|------|------------|----------------------|--------|----------|--------|
| 2026-10-29 | Yes | 0 | INSERT_CANDIDATE | P1 | PENDING |
| 2026-10-30 | Yes | 0 | INSERT_CANDIDATE | P1 | PENDING |
| 2026-11-02 | Yes | 0 | INSERT_CANDIDATE | P1 | PENDING |
| 2026-11-03 | Yes | 0 | INSERT_CANDIDATE | P1 | PENDING |
| 2026-11-04 | Yes | 6956 | SKIP_EXISTING | P1 | READY |
| 2026-11-05 | Yes | 6588 | SKIP_EXISTING | P1 | READY |
| 2026-11-06 | Yes | 0 | INSERT_CANDIDATE | P2 | PENDING |
| 2026-11-09 | Yes | 0 | INSERT_CANDIDATE | P2 | PENDING |

## Prioritization

**P1 (Oct 29–Nov 05)**: These dates are within the 5TD exit window of multiple clusters. Missing data blocks 5TD outcome evaluation.

**P2 (Nov 06/09)**: Bulk API has confirmed QG failure. Requires single-stock fallback (FALLBACK_PARTIAL). Nov 06 is the 5TD exit of the Oct 28 cluster.

## Idempotency Verification

The backfill script uses `INSERT OR IGNORE` semantics. Idempotency verified in temporary SQLite (TC23–TC25):
- First insert: 2 rows written ✓
- Repeat insert: 0 rows changed (ignored) ✓
- Conflict with different value: 0 rows changed ✓
- Readback: data unchanged ✓
- Rollback: uncommitted row removed ✓

## Preconditions for P2 (Nov 06/09)

1. User authorizes explicitly for each date
2. TWSE single-stock API fallback deployed and tested
3. TPEx single-stock endpoint verified (currently UNVERIFIED)
4. Quality gate must pass (≥5000 stocks requires TPEx)
5. No modification to forward_signals as part of backfill

## Safety Constraints (Verbatim)

- **No production writes in this session**
- 修改正式 Neon: FORBIDDEN
- 修改正式 SQLite: FORBIDDEN
- 執行正式 Backfill: FORBIDDEN (requires AUTH01)
- 修改正式 daily_prices: FORBIDDEN
