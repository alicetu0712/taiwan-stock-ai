# Session 61 — RC61-03 TradingShares Volume Acceptance

**Verdict: RC3_ACCEPTANCE_PASS**

## Scope

RC61-03-TPEX-VOLUME patches `fetch_tpex_historical` in `scripts/backfill_daily_prices.py` at line 284. Only the volume field name is changed (`TradeVolume` → `TradingShares`). The amount field (`TradeValue`) and all OHLC fields are unchanged. TWSE line 136 is not modified.

## Evidence for TradingShares Field Name

Session 58 P02 included a live WebFetch of the TPEx bulk OpenAPI endpoint. The raw JSON payload explicitly contained the field `TradingShares`. The script was reading `TradeVolume`, which is absent in TPEx responses, causing `row.get("TradeVolume", "")` to return an empty string, which `_strip_num` converts to `None`, which is stored as NULL.

Specific confirmed data point: stock 2317 (HonHai) on 2026-11-06 — `TradingShares` = 89,094,382 raw shares → 89,094.382 千股 after dividing by 1,000. This is consistent with the TWSE volume scale.

## Volume Unit Verification

| Exchange | API Field | Divisor | DB Unit | Note |
|----------|-----------|---------|---------|------|
| TWSE | TradeVolume | 1,000 | 千股 | Unchanged by RC-3 |
| TPEx (before) | TradeVolume (absent) | 1,000 | NULL | Bug |
| TPEx (after) | TradingShares | 1,000 | 千股 | Correct |

The `/1000` divisor at line 303 applies to both exchanges and is not changed by RC-3.

## PP-03 Exclusion

The amount field at line 285 reads `TradeValue`. PP-03 would change this to `TransactionAmount`. PP-03 carries MEDIUM confidence (HYPOTHESIS — field name was not directly confirmed in S58 probe). PP-03 is NOT included in RC-3. The amount field remains as `TradeValue`.

## Acceptance Test Results

| Test | Description | Result |
|------|-------------|--------|
| V01 | TPEx row with TradingShares=89094382 → NULL before patch | PASS |
| V02 | TPEx row with TradingShares=89094382 → 89094.382 after patch | PASS |
| V03 | Volume unit /1000 confirmed (S58 P02 fixture) | PASS |
| V04 | TWSE path uses TradeVolume (unchanged by RC-3) | PASS |
| V05 | Amount field still uses TradeValue (PP-03 excluded) | PASS |
| V06 | TradingShares=0 → 0.0 (not NULL) | PASS |
| V07 | TradingShares missing → NULL | PASS |
| V08 | Both exchanges tested; no cross-contamination | PASS |

## TWSE Path Unchanged

The TWSE functions (`fetch_twse_historical`, `_parse_twse_openapi_list`) use `TradeVolume` at lines 217 and 136 respectively. Those lines are not touched by RC-3. After applying RC-3, verifying that line 136 still reads `TradeVolume` is a required deployment step.

## Limitations

- Does NOT repair the existing 21,846 historical NULL volume rows in daily_prices (SET-C). Those rows were written with the old field name and remain NULL. Repair requires AUTH01 (TWSE) or is BLOCKED (TPEx).
- Amount field (`TradeValue`) may still produce NULL for TPEx stocks if the field is absent. PP-03 is excluded until the correct field name is confirmed.
- TPEx Historical Repair remains BLOCKED (no verified per-stock historical endpoint).

## Authorization Status

NOT_AUTHORIZED. Requires independent explicit user approval via AUTH-RC61-03.
