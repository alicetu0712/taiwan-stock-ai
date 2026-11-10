# Session 61 — RC61-02 Security Eligibility Acceptance

**Verdict: RC2_ACCEPTANCE_PASS**

## Scope

RC61-02-SECURITY-ELIGIBILITY patches `_is_excluded` in `scripts/backfill_daily_prices.py` (line 98). The patch affects all three call sites at lines 125, 214, and 273 (TWSE old-API, TWSE OpenAPI, and TPEx parsers).

## Universe Contract Verification

The Taiwan market uses the following stock ID conventions:

| Length | Type | Examples | Should be in daily_prices? |
|--------|------|----------|---------------------------|
| 4-digit | TWSE/TPEx ordinary stock | 2330, 1101, 6166, 6423 | Yes |
| 5-digit | ETF (00xxx series) | 00858, 00877, 00928 | No |
| 6-digit starting with 7 | Warrant | 700022, 701593 | No |
| 6-digit starting with 006/009 | ETF | 006201, 009806 | No |
| Alphanumeric (any length) | Various excluded types | Already excluded by keyword check | No |

No legitimate 5-digit or 6-digit ordinary stock codes exist in the current Taiwan market system.

## False Exclusion Audit (14 Test Cases)

| Stock ID | Name | Type | Before (bug) | After (patch) | Expected | Verdict |
|----------|------|------|-------------|---------------|----------|---------|
| 2330 | 台積電 | TWSE_ORDINARY | NOT excluded | NOT excluded | NOT excluded | PASS |
| 1101 | 台泥 | TWSE_ORDINARY | NOT excluded | NOT excluded | NOT excluded | PASS |
| 6423 | 億而得-創 | TWSE_INNOVATION | NOT excluded | NOT excluded | NOT excluded | PASS |
| 6166 | 凌華 | TPEX_ORDINARY | NOT excluded | NOT excluded | NOT excluded | PASS |
| 3673 | TPK | TPEX_ORDINARY | NOT excluded | NOT excluded | NOT excluded | PASS |
| 700022 | 台積電購01 | WARRANT_6DIG | **NOT excluded (bug)** | Excluded | Excluded | PASS |
| 701593 | 元大購01 | WARRANT_6DIG | **NOT excluded (bug)** | Excluded | Excluded | PASS |
| 006201 | 元大富櫃50 | ETF_6DIG | **NOT excluded (bug)** | Excluded | Excluded | PASS |
| 00858 | 永豐ESG | ETF_5DIG | **NOT excluded (bug)** | Excluded | Excluded | PASS |
| 00877 | 國泰永續高股息 | ETF_5DIG | **NOT excluded (bug)** | Excluded | Excluded | PASS |
| 2330 | 台積電ETF | ETF_BY_NAME | Excluded (keyword) | Excluded (keyword) | Excluded | PASS |
| 1234 | 某ETN | ETN_BY_NAME | Excluded (keyword) | Excluded (keyword) | Excluded | PASS |
| 5678 | 某特別股 | PREFERRED_BY_NAME | Excluded (keyword) | Excluded (keyword) | Excluded | PASS |
| ABC12 | 某股票 | NONSTANDARD_ALPHA | Excluded (non-digit) | Excluded (len>4) | Excluded | PASS |

**False exclusions (ordinary stocks incorrectly excluded after patch): 0**

## Coverage Semantics

Deploying RC-2 improves the QG coverage percentage because the denominator (universe) shrinks to ordinary stocks only. This is **reclassification**, not new data. The 95% QG threshold is not lowered.

Existing 107,765 historical warrant/ETF rows in daily_prices are NOT deleted by this patch.

## Limitations

- Does not delete existing warrant/ETF rows (107,765 historical rows remain).
- Does not fix TradingShares volume mismatch.
- Coverage improvement = reclassification only, NOT new data recovery.
- TWSE Historical Backfill still requires AUTH01 separately.
- If a future legitimate 5-digit ordinary stock is listed in Taiwan, it would be incorrectly excluded. No such stocks exist in the current market system.

## Authorization Status

NOT_AUTHORIZED. Requires independent explicit user approval via AUTH-RC61-02.
