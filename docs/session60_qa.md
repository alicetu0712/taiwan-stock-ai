# Session 60 — Q&A Reference

**Q1: What is the total NULL volume count and how is it partitioned?**

Total: 129,636 rows. Partitioned into four disjoint sets:
- SET-A (107,590): 6-digit pure-numeric stock IDs (12,873 warrants + 8 ETFs)
- SET-B (175): 5-digit pure-numeric stock IDs (7 ETFs: 00858/00877/00886/00887/00888/00928/00955)
- SET-C (21,846): 4-digit stock IDs NOT in the `stocks` table (TPEx ordinary stocks)
- SET-D (25): 4-digit stock IDs IN the `stocks` table (single stock 6423 "億而得-創")

Sum: 107,590 + 175 + 21,846 + 25 = 129,636 ✓

---

**Q2: Why does SET-B (5-digit ETFs) have NULL volume if the bug is for len>4?**

The `_is_excluded` bug applies to len>4. 5-digit ETFs (00858 etc.) have len=5, which is >4. The condition `len(sid) > 4 and not sid.isdigit()` does trigger for len=5, but `isdigit()` returns `True` for `00858`, so the exclusion is blocked. These ETFs are inserted into `daily_prices`. They then get NULL volume because the TPEx bulk API returns `TradingShares` (not `TradeVolume`). Both the exclusion bug and the field mismatch apply to SET-B.

---

**Q3: Why is SET-D (6423) a different root cause from SET-A/B/C?**

Stock 6423 "億而得-創" is a 4-digit TWSE ordinary stock. It is in the `stocks` table and is processed by the TWSE parser (not TPEx). The `_is_excluded` bug does not apply (len=4). The TradingShares mismatch does not apply (TWSE path uses `TradeVolume`, which is correct for TWSE). The NULL volume on 25 specific dates is a TWSE source anomaly: the TWSE API returns carry-forward OHLC with empty/NULL volume for this illiquid Innovation Board stock on those dates. It cannot be fixed by any of the three proposed patches.

---

**Q4: What is the exact one-line code change for the warrant exclusion patch?**

In `scripts/backfill_daily_prices.py`, line 98, change:
```python
    if len(sid) > 4 and not sid.isdigit():
```
to:
```python
    if len(sid) > 4:
```
Remove ` and not sid.isdigit()`. That is the entire change.

---

**Q5: Why is PP-03 (TransactionAmount) excluded from PATCH-3?**

PP-03 proposes changing line 285 from `row.get("TradeValue", "")` to `row.get("TransactionAmount", "")`. The field name `TransactionAmount` was never directly observed in a live TPEx API probe. It is an inference based on naming convention analogy. If the actual field name is different (e.g., `TradeValue`, `TurnoverValue`, `Amount`), deploying PP-03 would leave the amount column NULL or corrupt it. The risk of a wrong amount field name is not acceptable without verification. PP-03 requires a fresh live probe before it can be authorized.

---

**Q6: What does "independent patch" mean and why does it matter?**

An independent patch is one that modifies a code region that does not overlap with any other patch, can be rolled back without affecting other patches, and can be authorized and deployed separately. This matters because it allows the reviewer to approve PATCH-2 (low risk, no data change) without also committing to PATCH-3 (data-touching). It also isolates blast radius: if PATCH-3 causes unexpected behavior, PATCH-1 and PATCH-2 are unaffected and their rollback is unambiguous.

---

**Q7: Does deploying PATCH-2 delete existing warrant rows?**

No. PATCH-2 changes `_is_excluded()` to prevent future warrant/ETF insertions. Existing rows in `daily_prices` for 7xxxxx warrants and 00xxx ETFs remain in the database. If deletion of historical warrant rows is desired, that requires a separate authorized `DELETE` migration, which is not part of PATCH-2.

---

**Q8: Does deploying PATCH-3 fix historical NULL rows in daily_prices?**

No. PATCH-3 changes the field name read during `fetch_tpex_historical()`. Only future backfill runs will benefit — they will now read `TradingShares` and get a real value instead of NULL. The 21,846 existing NULL volume rows for SET-C (TPEx ordinary stocks) remain NULL in the database after the patch. Fixing historical rows requires a separate authorized re-fetch or bulk update.

---

**Q9: What changed about the TWSE eligible stock count from S59 to S60?**

S59 hardcoded 712 as an estimate. S60 runs a live database query (Aug2026+ TWSE stocks, 4-digit, in stocks table) and returns 720. The Nov05 actual count is 717. The discrepancy is 8 stocks. Impact: 16 additional API requests (~32 seconds) compared to S59's 1,424 request plan. The recommended denominator for recovery planning is 720.

---

**Q10: What is the authorization status of all 3 patches?**

All three patches are NOT_AUTHORIZED. Explicit, independent authorization is required for each patch before deployment. The Session 60 research prompt does not constitute authorization for any patch.

---

**Q11: Why is TPEx historical repair BLOCKED?**

The only confirmed TPEx bulk API endpoint ignores the date parameter (RC-03, confirmed in S57): it always returns the most recent data regardless of which date is requested. There is no known per-stock historical endpoint for TPEx equivalent to the TWSE T2 endpoint. Without a source that can return specific historical dates for specific TPEx stocks, the 21,846 NULL rows in SET-C cannot be repaired.

---

**Q12: What is carry-forward OHLC and why does it indicate a source issue?**

Carry-forward OHLC means that the same Open/High/Low/Close values repeat across multiple consecutive trading dates. For stock 6423, Jun01–Jun10 all show identical values: O=83.4, H=85.0, L=80.3, C=82.4. Real trading activity produces different prices each day. Identical OHLC across 8 consecutive days indicates the data source is propagating the last known value (carry-forward) rather than reporting actual trades. Volume is NULL on these dates, consistent with a source that knows trading did not occur (or cannot report it) but is filling OHLC placeholders.

---

**Q13: Why are 20D clusters all DATA_BLOCKED or NOT_YET_MATURE?**

The 20-day exit date for the earliest cluster (Oct13-16) falls around Nov12-16. The database maximum date is 2026-11-05. The exit prices do not exist yet. Without exit prices, `fwd_return_20d` cannot be computed. The later clusters (Oct21-22, Oct28) have even later exit dates. Additionally, AUTH02 (authorization to compute 20D outcomes) has not been granted.

---

**Q14: What is the genuine prospective evidence count?**

N = 0. No genuine prospective 20D outcomes exist as of Session 60. The Oct2026 signals were generated under frozen parameters and are candidates, but their exit prices are not yet available in the database.

---

**Q15: Does S60 introduce any new prospective evidence?**

No. Session 60 is a research/analysis session focused on patch preparation. It does not compute any new 20D returns, alpha figures, or outcome metrics. No retrospective evidence has been reclassified as prospective. The genuine prospective evidence count remains N=0.

---

**Q16: What does "coverage improvement = reclassification" mean?**

After the warrant exclusion patch, the QG universe denominator shrinks because warrants/ETFs are removed. If the same number of ordinary stocks have valid data before and after the patch, the coverage percentage increases purely because the denominator is smaller. No new data was acquired. This is a reclassification of what belongs in the denominator, not evidence that data quality improved. It is important to distinguish this from genuine data recovery.

---

**Q17: What is the difference between PATCH-2 and PP-01-REVISED?**

PP-01-REVISED is the patch candidate as defined in the research module (`src/research/tpex_security_classification_s60.py`). PATCH-2 is the same change expressed as a deployable patch entry in the release gate (`src/research/patch_release_gate_s60.py`), with added deployment metadata (rollback instructions, stop conditions, post-deployment verification steps, authorization status). They describe the same one-line code change.

---

**Q18: Why are 25 NULL dates identical across all 4 sets?**

The most likely explanation is that the TPEx bulk API fetch failed or returned incomplete data on those 25 specific dates. SET-A, SET-B, and SET-C are all fetched via the TPEx bulk path, so a fetch failure on a given date would affect all TPEx stocks simultaneously. SET-D (stock 6423, TWSE) coincidentally also has NULL volume on the same 25 dates — this is a TWSE source anomaly that happens to align with the TPEx gap dates, but the root cause is different.

---

**Q19: What verifies PP-02 (TradingShares) but not PP-03 (TransactionAmount)?**

PP-02: Session 58 conducted a live WebFetch of the TPEx bulk API endpoint on 2026-11-06. The raw JSON payload explicitly contained the key `TradingShares`. This is direct observation — HIGH confidence.

PP-03: No live probe has observed the transaction amount field name in the TPEx API response. The name `TransactionAmount` is inferred by analogy: since volume is `TradingShares` (not `TradeVolume`), perhaps amount is `TransactionAmount` (not `TradeValue`). This analogy may be wrong. Evidence level: MEDIUM (hypothesis). It requires a live probe targeting the amount field before it can be safely deployed.

---

**Q20: What is the recommended deployment order for the 3 patches?**

1. **PATCH-2** (warrant exclusion, line 98): Smallest data blast radius. No data is changed, only future inserts are blocked. Verify 4-digit stocks still flow after deployment.
2. **PATCH-1** (error reporting, line ~500): Zero data risk. Improves observability for subsequent monitoring.
3. **PATCH-3** (TradingShares, line 284): Data-touching. Deploy after PATCH-2 output has been observed and verified over at least one production run. Do not bundle with PP-03.
