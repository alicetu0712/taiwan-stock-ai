# Canonical Baseline V2 Preservation — Session 56

**Verdict**: CANONICAL_V2_INTEGRITY_VERIFIED

## S56 Verification

| Property | Status | Value |
|----------|--------|-------|
| Fingerprint (64-char SHA256) | VERIFIED | `6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f` |
| Deterministic (2 runs) | PASS | identical fingerprints |
| DB inputs unchanged | PASS | total_fs=2605, v8_buy=237, dp_max=2026-11-05 |
| Cluster membership stable | PASS | Oct13 n=46, Oct14 n=27, Oct16 n=55 |
| Grand mean | VERIFIED | +0.0081 (0.81pp) |

**Note on S55 doc discrepancy**: The `docs/canonical_baseline_v2_session55.md` listed Oct13 IDs 372–591, Oct14 IDs 767–938, Oct16 IDs 1106–1458. These are confirmed by running the module's exact query (`execution_date` field, not `trade_date`). An initial attempt using `trade_date` gave different IDs — confirming the importance of using `execution_date` as the cluster key.

## Mutation Tests

| Mutation | Fingerprint Changes? |
|----------|---------------------|
| db_forward_signals_total +1 | YES |
| grand_mean_delta changed | YES |
| strict_fill_dates changed | YES |
| calendar_contract changed | YES |
| parameter_hash changed | YES |
| signal_ids_per_cluster changed | YES |

## Provenance Separation

| Attribute | Historical (`2c8b2475c8fdc457`) | Canonical V2 |
|-----------|----------------------------------|--------------|
| Origin | UNRECOVERABLE | `canonical_baseline_v2_s55.py` |
| Hash algorithm | 16-char truncated | 64-char full SHA256 |
| Status | UNRECOVERABLE | VERIFIED |
| Grand mean | +0.81pp (from docs) | +0.81pp (confirmed) |
| Cluster IDs | Not recorded | Captured (372→1458) |

These two fingerprints are DISTINCT and must NEVER be used interchangeably.

## Genuine Prospective Separation

| Item | Value |
|------|-------|
| Canonical V2 grand mean | +0.81pp (historical, 5D) |
| Genuine Prospective N | 0 |
| V2 represents | Historical 5D cluster analysis only |

## Payload Keys (10 canonical)

```json
{
  "baseline_version_id": "S55-canonical-v2",
  "calendar_contract": "TaiwanTradingCalendar_v1",
  "db_daily_prices_max": "2026-11-05",
  "db_forward_signals_total": 2605,
  "db_v8_buy_signals": 237,
  "grand_mean_delta_v3_vs_a_direct": 0.0081,
  "methodology": "cluster_level_one_sample_t_test_v1",
  "parameter_hash": "be43e8ca977d9fdd",
  "signal_ids_per_cluster": {"2026-10-13": [...46 IDs], "2026-10-14": [...27 IDs], "2026-10-16": [...55 IDs]},
  "strict_fill_dates": ["2026-10-13", "2026-10-14", "2026-10-16"]
}
```

## Module

`src/research/canonical_baseline_v2_s55.py` (unchanged from S55)
