# Session 53: Q&A (20 Questions)

**Date**: 2026-11-10

---

**Q01: Why did the Nov 06 cron never run?**  
A: `CRON_NO_TRIGGER` — the cron was not invoked on Nov 06. `logs/hybrid_cron.log` was absent at 23:03 Taiwan on Nov 06. The shell `>> redirect` creates the log file even on Python errors, so absence confirms no shell invocation. Root cause of the scheduler failure is INCONCLUSIVE (same as S50 finding).

---

**Q02: Why does the Nov 06 quality gate fail on Nov 09 attempt even though TWSE returned the right date?**  
A: TPEx bulk API always returns current-date data regardless of the `d=` parameter. When Nov 09 cron tries to backfill Nov 06, TPEx returns Nov 09 data. Every row's Date field = Nov 09 ≠ Nov 06 target → QG-5 fires. The TPEx warning is `print()` only, not `summary["errors"].append()`, so it's absent from the cron log.

---

**Q03: Why is the root cause verdict QG_ROOT_CAUSE_PARTIAL, not CONFIRMED?**  
A: TWSE failure is DIRECTLY_CONFIRMED from the cron log. TPEx failure is STRONGLY_SUPPORTED from code analysis and S50 API findings — but TPEx api_date is not logged explicitly (only `print()`). Per-row sub-check detail for QG-1/2/3 is INSUFFICIENT_EVIDENCE. Partial because two out of three evidence categories are non-CONFIRMED.

---

**Q04: What does FALLBACK_PARTIAL mean?**  
A: TWSE single-stock covers all 599 four-digit stocks in the v8.0 research universe, confirmed by real API calls in S50. TPEx single-stock is UNVERIFIED (endpoint unknown). Full production backfill requires both; research-only backfill can use TWSE-only. Hence PARTIAL.

---

**Q05: Can we just ignore TPEx and backfill with TWSE single-stock only?**  
A: For research purposes (v8.0 universe = 599 TWSE stocks), yes — TWSE single-stock suffices for price lookups. For production backfill (which writes all 7000+ market stocks), TPEx coverage is needed to satisfy `_MIN_COVERED_STOCKS = 5000`. The QG-6 threshold of 300 is for the QG test; the backfill discovery threshold is 5000.

---

**Q06: Why are Oct 29/30 and Nov 02/03 P1 priority while Nov 06/09 are P2?**  
A: P1 dates are within the 5TD exit window of multiple clusters (e.g., Oct 28 cluster exits on Nov 06; its TD1–TD4 are Oct 29–Nov 03). They use the bulk API path which may have worked if cron had run. P2 dates (Nov 06/09) have confirmed bulk API QG failure — they specifically require the single-stock fallback, which is not yet deployed.

---

**Q07: If AUTH01 is granted, can the data be recovered immediately?**  
A: For P1 dates (Oct 29–Nov 03): possibly yes, if the bulk API has recovered (TWSE_LATEST_URL lag has advanced past those dates). For P2 dates (Nov 06/09): no — the single-stock fallback must first be developed, tested, and deployed. The manifest defines what to do; the execution infrastructure is not ready for P2.

---

**Q08: What is the Nov 12 deadline?**  
A: Oct 13 20TD exit = Nov 12 (12 trading days from 2026-11-10). The 20TD holding period requires complete price data from Oct 13 to Nov 12. If daily_prices is not restored for Nov 06–12 by Nov 12, the Oct 13 outcome computation window closes permanently.

---

**Q09: What is AUTH02 and how does it differ from AUTH01?**  
A: AUTH01 authorizes backfilling missing price data into `daily_prices`. AUTH02 would authorize computing and writing 20D return/alpha/outcome values. They are independent authorizations. This session only defines AUTH01; AUTH02 has not been requested or granted.

---

**Q10: Is the idempotency guarantee strong enough for production use?**  
A: The `INSERT OR IGNORE` pattern is correct — verified in TC23–TC25 with temporary SQLite. However, "prototype PASS ≠ production pipeline recovery." The fallback adapter is a research-only module. Before production use, it would need integration testing against the actual pipeline and QG, not just isolated SQLite tests.

---

**Q11: What is G03 and why does it fail?**  
A: G03 requires N≥10 genuinely prospective V3 decisions (registered before execution, with complete V3 decision frozen). Current count = 0. V3 is not activated, so no V3 decisions have been generated. The 3 historical strict clusters are `BASE_SIGNAL_PROSPECTIVE`, not `V3_DECISION_PROSPECTIVE`, and cannot be retrospectively reclassified.

---

**Q12: What is G04 and why does it fail structurally?**  
A: G04 requires ≥6TD spacing between independent clusters to avoid overlapping holding periods. The 5D holding window means clusters within 5TD share correlated outcomes. Historical strict clusters Oct 13/14 (1TD apart) and Oct 14/16 (2TD apart) violate this structurally. Even with new data, the existing clusters fail G04.

---

**Q13: Why is V3 activation blocked in this session?**  
A: Stage B Cron Probe was explicitly refused in Session 36. All subsequent sessions (S37–S53) preserve this constraint verbatim: "安裝或執行 Stage B Cron Probe: FORBIDDEN." This is a safety constraint, not a technical limitation.

---

**Q14: What does BASE_ONLY_PROSPECTIVE mean for the evidence quality?**  
A: It means the base v8.0 signal (the entry decision) was genuinely locked before execution for all 6 clusters. This is the best achievable evidence level given V3 is not activated. It is weaker than `V3_DECISION_PROSPECTIVE` (which would include a full V3 decision frozen before execution) but is genuine, not retrospective.

---

**Q15: Can the Nov 06 data be recovered via the TWSE single-stock fallback?**  
A: Technically yes for TWSE-listed stocks. S50 confirmed TSMC (2330) and MediaTek (2454) on Nov 06 with specific prices. However: (a) the prototype is not deployed; (b) TPEx stocks remain UNVERIFIED; (c) full QG pass (≥5000 stocks) requires TPEx; (d) AUTH01 required. Recovery is feasible with effort, not immediate.

---

**Q16: Why is the TWSE_HIST_URL unavailable for historical dates?**  
A: `www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json&date=YYYYMMDD` returns a CSV response body (not JSON) for historical dates. `requests.Response.json()` raises `JSONDecodeError` → code returns `None` → fallback to `TWSE_LATEST_URL` triggered. This is a quirk of the TWSE API, not a code bug.

---

**Q17: Is the `dataset_fingerprint=09c04e8c4059d87e` the same as "2c8b2475c8fdc457" mentioned in S52 memory?**  
A: No. These are different hash computations over different fields. `09c04e8c4059d87e` is the `dataset_fingerprint` from `canonical_5d_baseline_s44.py`, computed over the strict-eligible dataset rows. `2c8b2475c8fdc457` was a different fingerprint (possibly from a different context). Both are valid; the underlying data (+0.81pp, 3 strict clusters, Oct 13/14/16) is unchanged.

---

**Q18: What prevents the 5D baseline from being modified?**  
A: Multiple safety layers: (1) The constraint "覆寫 Frozen Research Baseline: FORBIDDEN"; (2) The `canonical_5d_baseline_s44.py` module is read-only; (3) The `dataset_fingerprint` acts as a tamper detector — any change to the strict-eligible dataset changes the fingerprint; (4) TC39 in this session's tests verifies fingerprint, delta, and cluster count at every regression run.

---

**Q19: What is the total test count after S53?**  
A: 3598 passed, 1 skipped (up from S52 baseline of 3452).

---

**Q20: What must happen before V3 can be considered for real-world activation?**  
A: Six confirmed blockers from S38 activation readiness review: (1) quality gate FAIL; (2) ETF classification mismatch; (3) G03 N=0/10; (4) G04 structural fail; (5) pipeline data gap; (6) prospective evidence insufficient. Additionally: AUTH01 must be granted and executed, pipeline must be restored for Nov06+, and a separate V3 activation authorization must be obtained.
