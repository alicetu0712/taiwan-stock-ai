# ForwardSignals Count Reconciliation — Session 37

**Date:** 2026-11-08  
**Audit Type:** Read-only count reconciliation  
**Version:** session37_v1

---

## 1. ForwardSignalsReconciliationReport Summary

**Verdict: `COUNT_RECONCILED`**

The discrepancy between 2605 (Session 35) and 2236 (Session 36) is fully explained by a model_version filter. No data was lost, deleted, or modified between sessions. The difference is a query filter difference only.

---

## 2. The Two Counts

| Source | Count | Query / Context |
|---|---|---|
| **Source A: 2605** | 2605 | `SELECT COUNT(*) FROM forward_signals` — no filter (all versions) |
| **Source B: 2236** | 2236 | `SELECT COUNT(*) FROM forward_signals WHERE model_version="v8.0"` — v8.0 only |
| **Difference** | 369 | v6.0 signals (is_valid=False) |

---

## 3. Breakdown

| model_version | is_valid | Count | Date Range | Note |
|---|---|---|---|---|
| v6.0 | False (0) | 369 | 2026-10-09 to 2026-10-11 | Invalidated, legacy |
| v8.0 | True (1) | 2236 | 2026-10-12 to 2026-10-28 | Current valid signals |
| **Total** | — | **2605** | 2026-10-09 to 2026-10-28 | — |

---

## 4. Session-by-Session Count History

| Session | Reported Count | Filter | Explanation |
|---|---|---|---|
| Session 35 | 2605 | None (total) | "ForwardSignals: 2605 筆" = all records |
| Session 36 | 2236 (v8.0 valid) + 369 (v6.0 invalid) | model_version filter | Correctly decomposed |
| Session 37 | 2605 total / 2236 v8.0 / 369 v6.0 | Verified by direct query | CONFIRMED |

---

## 5. V6.0 Signal Details

| Date | V6.0 Signal Count | Daily_prices for Date | Note |
|---|---|---|---|
| 2026-10-09 | 349 | 0 (not in DB) | Signals generated from Oct 7 prices (look-ahead concern) |
| 2026-10-10 | 10 | 0 (National Holiday) | Signals for a holiday date using stale prices |
| 2026-10-11 | 10 | 0 (not in DB) | Signals for a date with no price data |
| **Total** | **369** | — | — |

**V6.0 is_valid=False explanation:**
- These signals were generated under model version v6.0 and subsequently invalidated when v8.0 was adopted
- The `is_valid=False` flag marks them as not to be used in production or research
- They remain in the database as historical record

**V6.0 universe composition (same methodology issue):**
| Stock type | Count |
|---|---|
| In master (TWSE) | 208 |
| Orphan 4-digit | 127 |
| ETF-like (5/6-digit) | 34 |

V6.0 also included ETFs — the universe contamination issue predates v8.0.

---

## 6. V8.0 Signal Details

| Date | Count | In-master | Orphan 4-digit | ETF-like |
|---|---|---|---|---|
| 2026-10-12 | 348 | 191 | 124 | 33 |
| 2026-10-13 | 387 | 214 | 135 | 38 |
| 2026-10-14 | 356 | 198 | 126 | 32 |
| 2026-10-16 | 261 | 153 | 86 | 22 |
| 2026-10-21 | 302 | 167 | 111 | 24 |
| 2026-10-22 | 323 | 182 | 117 | 24 |
| 2026-10-28 | 259 | 152 | 88 | 19 |
| **Total** | **2236** | **1257 (56.2%)** | **787 (35.2%)** | **192 (8.6%)** |

---

## 7. Duplicate Check

| Check | Result |
|---|---|
| Duplicate (stock_id, trade_date, model_version) | **0** |
| Duplicate (stock_id, trade_date, model_version, is_valid) | **0** |

No duplicate signals exist.

---

## 8. Source and Fingerprint Metadata

| Field | V8.0 Value |
|---|---|
| source_price_date | NULL (all 2236) |
| overnight_rule_version | NULL (all 2236) |
| total_score range | 14.0 to 83.5 |
| confidence range | 40.0 to 100.0 |
| fwd_return_20d | NULL (all 2236, outcomes not computed) |
| fwd_return_60d | NULL (all 2236, outcomes not computed) |
| FS score sum (v8.0) | 88,497.6 |

**Note:** `source_price_date = NULL` means no record of which price date was used for computation. This creates an audit gap — it is unknown whether signals used the correct trade_date prices or stale prices from a prior date.

---

## 9. Database Identity

| Item | Value |
|---|---|
| Database path | data/platform.db |
| Table | forward_signals |
| Total rows (all versions) | 2605 |
| Neon (remote DB) | Not queried — local SQLite only |
| Second database | None found |

There is no evidence of a second database containing ForwardSignals. The 2605 vs 2236 difference is entirely due to the model_version filter.

---

## 10. Unresolved Questions

| Question | Status |
|---|---|
| Why is source_price_date NULL for all v8.0 signals? | UNRESOLVED — documentation/logging gap |
| Were V6.0 Oct 9–11 signals computed from stale (Oct 7) prices? | PROBABLE (no price data for Oct 9–11) — not confirmed by code audit |
| Why does the ForwardSignals engine include ETFs? | UNRESOLVED — code audit not completed; no universe filter found |
| Are the 787 orphan 4-digit signals from TPEx common stocks? | UNRESOLVED — cannot distinguish TPEx vs TWSE without exchange metadata |

---

## 11. Verdict

**`COUNT_RECONCILED`**

- 2605 = total (v6.0 + v8.0)
- 2236 = v8.0 valid only
- Difference = 369 v6.0 (is_valid=False)
- No data loss, no modification, no second database
- No duplicate records
- ETF contamination is a separate methodology issue, not a count discrepancy
