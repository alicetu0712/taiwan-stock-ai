# Canonical Baseline V2 — Session 55

**Version ID**: S55-canonical-v2
**Verdict**: CANONICAL_V2_VERIFIED

## Purpose

Historical fingerprint `2c8b2475c8fdc457` is UNRECOVERABLE (S55 provenance search). This new baseline captures the same research state with a stable, fully documented fingerprint.

**NOT a replacement for the historical fingerprint** — it is a NEW baseline with its own version ID.

## V2 Specification

| Field | Value |
|-------|-------|
| Version ID | `S55-canonical-v2` |
| Hash Algorithm | SHA256 (full 64-char hex — NOT truncated) |
| JSON Serialization | `json.dumps(sort_keys=True)` |
| Float Precision | 4 decimal places |
| Null Representation | None → JSON null |
| Timezone | UTC (ISO 8601) |
| Strategy | v8.0 |
| Parameter Hash | be43e8ca977d9fdd |
| Calendar Contract | TaiwanTradingCalendar_v1 |
| Methodology | cluster_level_one_sample_t_test_v1 |

## Payload Keys (Canonical, 10 total)

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
  "signal_ids_per_cluster": {"2026-10-13": [...], "2026-10-14": [...], "2026-10-16": [...]},
  "strict_fill_dates": ["2026-10-13", "2026-10-14", "2026-10-16"]
}
```

## Cluster Membership (Input Record IDs)

| Fill Date | n Signals | First ID | Last ID | Delta vs A_direct |
|-----------|-----------|----------|---------|-------------------|
| 2026-10-13 | 46 | 372 | 591 | +1.20pp |
| 2026-10-14 | 27 | 767 | 938 | +2.76pp |
| 2026-10-16 | 55 | 1106 | 1458 | −1.52pp |

Grand Mean: **+0.81pp** | CI: [−1.4pp, +3.0pp] | SIGNIFICANCE_INCONCLUSIVE

## V2 Validation Results

| Test | Result |
|------|--------|
| Deterministic reproduction (2 runs) | PASS |
| Fill dates stable | PASS |
| Signal IDs stable | PASS |
| Grand mean stable | PASS |
| Version ID stable | PASS |
| Distinct from historical fingerprints | PASS |
| Full 64-char SHA256 | PASS |
| Input mutation detection | PASS |

## Relationship to Historical

| Property | Historical (`2c8b2475c8fdc457`) | V2 |
|----------|----------------------------------|-----|
| Source | UNRECOVERABLE | `canonical_baseline_v2_s55.py` |
| Hash length | 16 chars (truncated) | 64 chars (full) |
| Cluster IDs | Not recorded | Captured per cluster |
| Self-consistent | No (doc contradiction) | Yes |
| Status | UNRECOVERABLE | VERIFIED |

## Module

`src/research/canonical_baseline_v2_s55.py` — PARTS B4+B5+B6
