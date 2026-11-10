# Session 63 — RC-2 Security Eligibility Universe Contract

## Status: UNIVERSE_CONTRACT_VERIFIED

---

## 1. Five-Universe Separation

| Universe | Definition | RC-2 Impact |
|---|---|---|
| **U1: Backfill Eligible** | What `_is_excluded()` decides | MODIFIED (bug fix) |
| **U2: Daily Prices Storage** | Rows in `daily_prices` table | READ-ONLY, no change |
| **U3: Research Universe** | Rows in `stocks` table | ZERO impact |
| **U4: Strategy Signal Universe** | Stocks that receive signals via foe_v1 / Hybrid Entry | ZERO impact |
| **U5: Benchmark Universe** | 0050 only | ZERO impact |

---

## 2. Research Universe (U3) — stocks table

```
Total entries  : 826
4-digit IDs    : 826 (100%)
Non-4-digit IDs: 0
Market         : TWSE only (NO TPEx entries)
Schema         : stock_id, name, market, industry, listing_date, capital,
                 outstanding_shares, is_excluded, updated_at, delisted_date,
                 security_status
```

**Key entries verified:**
- `0050` / 元大台灣50 / TWSE / is_excluded=0 ✓
- `6423` / 億而得-創 / TWSE / is_excluded=0 ✓
- 4-digit ETFs (0051–0081): all present, all 4-digit ✓
- Ordinary stocks (2330, 2317, etc.): all 4-digit ✓

**RC-2 logic**: `if len(sid) > 4` — FALSE for every entry in stocks table.

---

## 3. Daily Prices Storage (U2) — daily_prices table

```
len=4 rows  :  423,060  (ordinary stocks + 4-digit ETFs)
len=5 rows  :    3,131  (5-digit ETFs: 00646, 00662, 00858, 00878, …)
len=6 rows  :  108,579  (6-digit warrants/ETFs)
len>4 total :  111,710  rows
Total       :  534,770  rows
NULL volume :  129,636  rows
0050 count  :      567  rows, last_date=2026-11-05
```

RC-2 affects ONLY future backfill decisions for len>4 stock IDs. It does NOT delete or modify any existing row in `daily_prices`.

---

## 4. Backfill Eligible Universe Change (U1)

| Stock Type | len | BEFORE RC-2 | AFTER RC-2 | Correct |
|---|---|---|---|---|
| 4-digit ordinary (2330, etc.) | 4 | Eligible | Eligible | ✓ |
| 4-digit ETF (0050, 0056, etc.) | 4 | Eligible | Eligible | ✓ |
| 4-digit Innovation Board (6423) | 4 | Eligible | Eligible | ✓ |
| 5-digit ETF pure-numeric (00858) | 5 | Eligible (BUG) | Excluded (FIXED) | ✓ |
| 6-digit warrant pure-numeric (700022) | 6 | Eligible (BUG) | Excluded (FIXED) | ✓ |
| 5–6-digit alphanumeric (00631L) | 6 | Excluded | Excluded | ✓ |

**Bug scope**: RC-2 fixes exactly the case where `len>4 AND isdigit()` — these were incorrectly passing through before. 129,636 NULL volume rows in daily_prices are predominantly from this population (SET-A: 107,590 warrants, SET-B: 175 5-digit ETFs).

---

## 5. Strategy Signal Universe (U4) — Zero Impact

- foe_v1 and Hybrid Entry P1–P4 operate on the Research Universe (U3: stocks table)
- stocks table contains ONLY 4-digit IDs
- RC-2 condition `len(sid) > 4` is FALSE for all 4-digit IDs
- **No signal generation path is altered**

---

## 6. Benchmark Universe (U5) — 0050 Safety

```python
len('0050') == 4   # → 4 ≤ 4 → NOT excluded
'ETF' in '元大台灣50'.upper()  # → False
'WARRANT' in '元大台灣50'.upper()  # → False
# → _is_excluded_after('元大台灣50', '0050') == False
```

0050 remains in backfill universe under both old and new logic. Benchmark continuity GUARANTEED.

---

## 7. Verification Artifacts

| Check | Result |
|---|---|
| TC06 research_universe_all_4digit | PASS |
| TC07 rc2_zero_effect_on_stocks_table | PASS |
| TC08 benchmark_0050_not_excluded_before | PASS |
| TC09 benchmark_0050_not_excluded_after | PASS |
| TC10 innovation_board_6423_not_excluded | PASS |
| TC11 ordinary_stocks_not_excluded | PASS |
| TC12 5digit_etfs_excluded_after_rc2 | PASS |
| TC13 6digit_warrants_excluded_after_rc2 | PASS |
| TC39 zero_false_exclusion_verified (all 826) | PASS |

---

**Verdict**: `UNIVERSE_CONTRACT_VERIFIED` — RC-2 affects ONLY the backfill eligibility of len>4 pure-numeric IDs. Zero impact on Research Universe, Strategy Signal Universe, or Benchmark Universe.
