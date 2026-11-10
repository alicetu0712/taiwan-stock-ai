# Session 58 — Q&A (20 Questions)

**Date**: 2026-11-10

---

**Q1: What is the T2 compliance verdict and why?**

T2_COMPLIANCE_UNVERIFIED. TWSE terms pages at three tested URLs all returned 404 or Swagger UI without policy text. Rate limit and automated access policy cannot be confirmed. "Technically accessible" ≠ "Compliant for automated bulk access."

---

**Q2: What is the T2 pilot verdict?**

T2_PILOT_PASS. All 5 probes returned HTTP 200, stat=OK, full OHLCV+volume. Date semantics verified (monthly response). 5/5 pass within the 12-request cap.

---

**Q3: Why does T2_PILOT_PASS not authorize full recovery?**

Pilot = bounded feasibility test. Full recovery = 1,198 API calls requiring: (1) TWSE rate limit confirmation, (2) automated access policy confirmation, (3) AUTH01 explicit user authorization. None are granted.

---

**Q4: What was the S57 runtime estimate, and what is the corrected S58 estimate?**

S57 estimated ~6.6 hours (1969 calls/date × 6 dates). S58 corrects to ~40 minutes (599 stocks × 2 months = 1,198 calls × 2s). Root cause: monthly API semantics (1 call = full month) and research universe clarification (599, not 1969).

---

**Q5: What was the Nov03 2317 close controversy, and how is it resolved?**

S55/S56 used 245.0. S57 corrected to 245.5 based on S50 _VERIFIED_RECORDS. S58 P02 direct probe returned "exact closing price: 245.50 TWD" — independently confirms 245.5. RESOLVED: 245.5 is correct.

---

**Q6: Why were Nov06/09 classified as close-only, and what changed?**

S50 probed only 2330 and 2454 for Nov06/09, both returned close-only. S58 probed 2317 and 2882 for the same dates — both returned FULL OHLCV+volume. Nov06/09 are NOT inherently close-only dates; S50 coverage was simply limited. UPGRADED to FULL_OHLCV_WITH_VOLUME for TWSE stocks.

---

**Q7: What is the TPEx alternative source verdict?**

TPEX_ALTERNATIVE_UNVERIFIED. The bulk endpoint (RC-03, DATE_PARAM_IGNORED) has no historical alternative discovered. Per-stock historical endpoint URL attempt redirected to homepage. TWSE single-stock covers TWSE-listed stocks (TPEX_ALTERNATIVE_PARTIAL) but not TPEx-exclusive stocks.

---

**Q8: What is the TPEx volume field mismatch and what does it explain?**

TPEx API returns `"TradingShares"` but the pipeline script likely reads `"TradeVolume"`. This field name mismatch explains why all 5737 TPEx records in `daily_prices` have `volume=NULL`. Fix: map `TradingShares` → volume in the backfill script. Batch with existing TPEx patch.

---

**Q9: How many records are in the recovery manifest?**

23 records across 6 gap dates: 7 Oct29, 3 Oct30, 3 Nov02, 2 Nov03, 4 Nov06, 4 Nov09. 17 are FULL_OHLCV, 3 PARTIAL, 3 CLOSE_ONLY. All are INSERT_CANDIDATE pending AUTH01.

---

**Q10: What is the coverage impact of the manifest?**

Maximum 7/599 = 1.2% coverage (Oct29). QG FAIL before and after manifest. Full T2 recovery would achieve ~100% (PASS_LIKELY). Denominator is 599 (v8.0 research universe), not 1969 (all ordinary stocks).

---

**Q11: What is the 20D readiness verdict and why?**

20D_DATA_BLOCKED. Double blocker: (1) AUTH02 not authorized; (2) daily_prices max = 2026-11-05 but Oct13 cluster exit date = ~2026-11-12. Even with AUTH02, exit prices aren't in DB.

---

**Q12: What would resolve the 20D double blocker?**

Both must be resolved: (1) Explicit AUTH02 authorization; (2) daily_prices populated through Nov12 (requires AUTH01 + pipeline recovery extended to Nov12). Both are unauthorized.

---

**Q13: When does the Oct13 cluster window close?**

Exit date estimate: 2026-11-12 (2 trading days from Nov10). Window is imminent. After Nov12, the standard NEXT_OPEN entry + 20TD exit framework can still compute outcomes if exit prices are eventually backfilled — but the data gap becomes a research quality concern.

---

**Q14: Does data recovery affect G03?**

No. G03 requires genuine prospective decisions. Data recovery inserts historical OHLCV — this is not a decision. G03 = 0/10 unchanged.

---

**Q15: Does data recovery affect G04?**

No. G04 requires weekly spacing of genuine prospective decisions. No new decisions were generated. G04 = STRUCTURAL_FAIL unchanged.

---

**Q16: What is the TPEx patch deployment status?**

PATCH_DEPLOYMENT_READY. Current state: PRINT_ONLY_CONFIRMED (not deployed). Two changes: (1) error propagation fix (api_date mismatch to summary["errors"]); (2) volume field mapping (TradeVolume → TradingShares). 15/15 scenarios PASS. Does not require AUTH01.

---

**Q17: Is the Canonical V2 fingerprint still stable?**

YES. `6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f`. Not affected by S58 research activities. Production forward_signals unchanged.

---

**Q18: What is the daily_prices max date as of S58?**

2026-11-05. Unchanged from S57 and S56. No new data has been written to production.

---

**Q19: How many tests passed in S58?**

4029 passed, 1 skipped. S57 reference: 3947. Delta: +82 new tests (TC01–TC25, 82 cases). Full regression passes.

---

**Q20: What are the authorization priorities after S58?**

| Priority | Action | Status | Window |
|----------|--------|--------|--------|
| 1 | AUTH02 (Oct13 20D) | NOT_AUTHORIZED | Closes ~Nov12 |
| 2 | TPEx patch (error + volume) | NOT_AUTHORIZED | Ongoing bug |
| 3 | AUTH01 (full T2 recovery) | NOT_AUTHORIZED | No hard deadline |
| 4 | Stage B Cron Probe | EXPLICITLY_DECLINED (S36) | — |
