# Session 59 — Q&A (20 Questions)

**Date**: 2026-11-10

---

**Q1: What was the S58 "5,737 NULL volume" reference error?**

S58 incorrectly cited 5,737 as the production NULL volume count. Actual count = 129,636. The 5,737 was from S57's live probe of the TPEx bulk endpoint (number of rows returned in a single bulk response on a specific date), not the cumulative production NULL volume. S59 forensics confirmed the true count via direct DB query: `SELECT COUNT(*) FROM daily_prices WHERE volume IS NULL` → 129,636.

---

**Q2: What are the two confirmed root causes of NULL volume?**

RC-59-01 (107,765 rows): Warrant IDs (6-digit pure numeric like 700022) not excluded by `_is_excluded` logic bug at line 98. RC-59-02 (21,846 rows): TPEx field name mismatch — script reads `row.get("TradeVolume")` but TPEx API returns field named `TradingShares`.

---

**Q3: Why did `_is_excluded` fail to exclude 6-digit warrant IDs?**

Line 98 condition: `if len(sid) > 4 and not sid.isdigit()`. For ID "700022": `len("700022") > 4` = True, `not "700022".isdigit()` = `not True` = False. The AND makes the whole condition False → warrant ID is not excluded → enters pipeline → volume stored as NULL. Fix (PP-01, NOT AUTHORIZED): change to `if len(sid) > 4:`.

---

**Q4: How was the TradingShares field confirmed?**

S58 WebFetch of a live TPEx bulk API response (Nov04 probe) returned a JSON payload with field name `"TradingShares"` explicitly visible. This is DIRECTLY_CONFIRMED evidence. The script reads `row.get("TradeVolume", "")` which returns `""` for a TPEx row → `_strip_num("")` returns None → stored as NULL volume.

---

**Q5: Why are 2024-2025 daily_prices clean (0 NULL volume)?**

TPEx data was not fetched during 2024–2025. The backfill script's TPEx path was only executed for recent 2026 dates. All 129,636 NULL rows are confined to Jun–Sep 2026 and Nov04/05, corresponding to dates where TPEx fetching was run.

---

**Q6: What is the volume unit for both TWSE and TPEx?**

Both use 千股 (thousands of shares). The DB stores `volume = raw_shares / 1000`. TWSE: `TradeVolume / 1000`. TPEx (post-fix): `TradingShares / 1000`. The divisor is consistent — there is no unit mismatch between exchanges, only a field name mismatch in the TPEx parser.

---

**Q7: What is the T2 compliance verdict and what changed from S58?**

T2_COMPLIANCE_UNVERIFIED — unchanged from S58. No new compliance documentation was found in S59. The same 3 URL probes from S58 (2× 404, 1× Swagger UI without policy text) remain the only evidence. Rate limit and automated access policy are still unverified.

---

**Q8: Why does S59 use 712 stocks instead of S58's 599?**

S58 used 599 from S50's heuristic count of 4-digit numeric stocks in the v8.0 research universe. S59 queried `daily_prices` directly for stocks active in 2026 (Aug–Nov 2026), yielding 712 active 4-digit non-ETF TWSE stocks. This is a more accurate scope for recovery planning. The full TWSE stocks table has 826 entries.

---

**Q9: How many stock-month API calls are needed for full T2 recovery?**

1,424 (712 eligible stocks × 2 months: October 2026 + November 2026). One API call returns all trading days in a calendar month. At 2s delay sequential: ~47 minutes runtime. Requires AUTH01 authorization + TWSE compliance confirmation.

---

**Q10: What is the Oct13 cluster exit date and what are the two blockers?**

Oct13 cluster execution dates: Oct13/14/16. Using 20 trading days: exit dates approximately Nov12–16. Two blockers: (1) AUTH02 NOT AUTHORIZED — user must explicitly authorize 20D computation; (2) `daily_prices` max = 2026-11-05 — exit prices for Nov12+ are not yet in the DB. Both blockers must be resolved before computation can proceed.

---

**Q11: Is Nov12 a hard deadline for the Oct13 20D computation?**

No. Nov12 is the 20TD exit DATE, not an expiry for the analysis. If `daily_prices` is eventually backfilled through Nov12 and AUTH02 is authorized, the computation can proceed even after Nov12 has passed. The entry used NEXT_OPEN execution (prices known at trade time), so the outcome retains its analytical validity as a forward-looking measurement. The binding constraint is AUTH02 authorization, not the calendar.

---

**Q12: What is the AUTH02 scope for Oct13-16?**

1,091 signals with `execution_date` in Oct13/14/16. Entry prices: `execution_price` column in `forward_signals` (all present). Exit prices: `daily_prices.close` at the 20TD exit date for each stock. Benchmark: 0050 close at same exit date. Output columns: `fwd_return_20d`, `alpha_20d` in `forward_signals`. NOT AUTHORIZED.

---

**Q13: What is fwd_return_20d count for all October+ signals?**

0 (all NULL). No 20D outcomes have been computed for any of the 1,977 Oct+ signals. This is the expected state — safety constraints prohibit execution without AUTH02 authorization.

---

**Q14: What does the repair eligibility manifest show?**

5 entries: (1) 2330/2454/2317 — TWSE stocks, INSERT_CANDIDATE, verified OHLCV from S58 pilot, AUTH01_PENDING; (2) 1240 — TPEx ordinary stock, REPAIR_BLOCKED_NO_SOURCE (no verified TPEx per-stock historical endpoint discovered); (3) ALL_WARRANTS — WARRANT_FILTER_FIX_PREFERRED (removing warrants via PP-01 code fix is preferable to individual row repair).

---

**Q15: What is the TPEx parser patch deployment status?**

NOT_AUTHORIZED, PRINT_ONLY_CONFIRMED. The patch bundle has 3 changes ready (PP-01 warrant exclusion, PP-02 TradingShares volume, PP-03 amount field — HYPOTHESIS). All 10 schema compatibility tests pass in isolated environment. 4 repair simulation tests pass on temporary SQLite. NOT deployed to production. Deployment requires explicit user authorization.

---

**Q16: Can the TPEx alternative source (bulk endpoint) be used for historical repair?**

No. RC-03 (DATE_PARAM_IGNORED, confirmed S57/S58) means the bulk endpoint ignores the date parameter — it always returns the most recent data. No per-stock historical TPEx endpoint was found. TPEx ordinary stock historical data repair verdict: VOLUME_REPAIR_BLOCKED_NO_SOURCE.

---

**Q17: What is the G03 status?**

G03 = 0/10. Unchanged from S42. G03 requires 10 genuine prospective decisions with known outcomes. Data recovery, 20D computation, root cause analysis, and parser verification do not generate new prospective decisions. Only Stage B authorization + live pipeline execution can increase G03.

---

**Q18: What is the G04 status?**

G04 = STRUCTURAL_FAIL. Unchanged. Weekly spacing of genuine prospective decisions cannot be achieved retroactively. No new decisions were generated in S59. Even if G03 decisions were created today, G04 requires weekly spacing across the decision history.

---

**Q19: What is the production data integrity status?**

PRODUCTION_UNCHANGED_VERIFIED. `daily_prices` max = 2026-11-05 (unchanged). Oct29 non-0050 rows = 0 (unchanged). `forward_signals` = 2,605 total, 2,236 v8.0 (unchanged). TPEx patch not deployed (PRINT_ONLY_CONFIRMED). Canonical V2 fingerprint = `6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f` (unchanged). 4,072 regression tests pass.

---

**Q20: What are the authorization priorities after S59?**

| Priority | Action | Status | Notes |
|----------|--------|--------|-------|
| 1 | TWSE compliance confirmation | NOT_STARTED | Prerequisite for AUTH01 |
| 2 | AUTH02 (Oct13 cluster 20D) | NOT_AUTHORIZED | Requires pipeline recovery through Nov12 first |
| 3 | TPEx Parser Patch (PP-01/02/03) | NOT_AUTHORIZED | No compliance dependency; verify PP-03 field name |
| 4 | AUTH01 full T2 recovery | NOT_AUTHORIZED | After compliance confirmed |
| 5 | Stage B Cron Probe | EXPLICITLY_DECLINED (S36) | Remains frozen |
