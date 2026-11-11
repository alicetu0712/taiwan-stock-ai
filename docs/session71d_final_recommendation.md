# Session 71D — Final Recommendation

**Date**: 2026-11-11  
**Check Time**: 2026-11-11 14:16–14:25 CST  
**Authorization**: AUTH-S71-BUNDLE-A (read-only acceptance phase)

---

## 1. Part J — Final Verdict

| Category | Verdict |
|---|---|
| **RC-2 H3** | `H3_PENDING` |
| **RC-2 Filter** | `FILTER_EFFECT_UNVERIFIED` (file verified, no post-deployment runtime yet) |
| **Data Provenance** | `DATA_SOURCE_PARTIALLY_RECONCILED` |
| **SQLite Identity** | `SQLITE_IDENTITY_PARTIAL` |
| **Bundle A Freshness** | `FRESHNESS_CONTRACT_VERIFIED` |
| **Production** | `PRODUCTION_UNCHANGED_VERIFIED` |
| **Authorization** | `NO_NEW_IMPLEMENTATION_AUTHORIZED` |

---

## 2. Evidence-Based Findings

### F-01 (VERIFIED): Neon is the dashboard data source

**Description**: The dashboard app connects to Neon PostgreSQL (not local SQLite) when `USE_NEON=true` is set in `.env`.

**Evidence**: `config.py` runtime resolution; `DATABASE_URL` confirmed as `postgresql://...@neon.tech/...`; `get_session()` path analysis.

**File/Line**: `config.py:50`, `.env:USE_NEON=true`

**Impact**: Prior S71B/C "534,770 rows / max 2026-11-05" baseline was local SQLite stats, NOT dashboard production data.

**Confidence**: HIGH (VERIFIED)

**Recommended Action**: Update project memory and future session docs to distinguish "Local SQLite (backfill target)" from "Neon (dashboard source)".

**Authorization**: None required (documentation only)

---

### F-02 (VERIFIED): S71C screenshots used real Neon production data

**Description**: The fixture `fixture_71c.py` imported actual dashboard page functions which connect to Neon. T2 "2026-11-10" and T0 "2026-11-10" came from real Neon data.

**Evidence**: Neon query confirmed `daily_prices[2465] max = 2026-11-10`; fixture code shows `page_market_watch(SEL_DATE)` with no DB override.

**Impact**: S71C visual acceptance was performed against REAL PRODUCTION DATA. The screenshots are valid.

**Confidence**: HIGH (VERIFIED)

**Recommended Action**: None. Screenshots remain valid evidence.

---

### F-03 (VERIFIED): Local SQLite contains 111,710 warrant-like rows (pre-RC2)

**Description**: Local SQLite has 111,710 rows where `len(stock_id) > 4`, written before RC-2 deployment. Future cron runs will NOT add more.

**Evidence**: Read-only SQLite query confirmed.

**File/Line**: `data/platform.db` (read-only)

**Impact**: RC-2 patch prevents new warrant-like rows from being written to local SQLite. Existing rows are pre-existing, not new contamination.

**Confidence**: HIGH (VERIFIED)

**Recommended Action**: Historical cleanup is a separate decision (not in scope for Session 71D).

**Authorization**: Historical cleanup would require new authorization.

---

### F-04 (VERIFIED): RC-2 scope is local SQLite only — does NOT affect Neon

**Description**: `backfill_daily_prices.py` explicitly "NEVER touches production Neon" (line 5). RC-2 filter applies only to local SQLite writes. Neon is updated by GitHub Actions separately.

**Evidence**: Script header; `from config import DB_PATH` (not `DATABASE_URL`); `sqlite3.connect(DB_PATH)`.

**Impact**: RC-2 effectiveness can only be tested via local SQLite writes. Neon warrant cleanup (if needed) requires separate GitHub Actions work.

**Confidence**: HIGH (VERIFIED)

---

### F-05 (VERIFIED): H3 PENDING at 14:20 CST — no post-deployment cron yet

**Description**: Zero Nov 11 entries in `logs/hybrid_cron.log`. RC-2 deployed Nov 11 morning; next natural cron at 16:00 CST.

**Evidence**: `grep "\[2026-11-11" logs/hybrid_cron.log → 0 entries`

**Impact**: H3 cannot be classified until 16:05 CST.

**Confidence**: HIGH (VERIFIED)

---

### F-06 (VERIFIED): Prior session baseline documentation error

**Description**: Sessions S66–S71C consistently stated "DB: 534,770 rows, max_date 2026-11-05" as "production" database stats. These numbers describe local SQLite, not what the dashboard actually reads (Neon).

**Evidence**: Local SQLite query = 534,770 / max 2026-11-05; Neon query = 409,039 / max 2026-11-10.

**Impact**: No functional impact (screenshots were still from real Neon data). Documentation only.

**Confidence**: HIGH (VERIFIED)

**Recommended Action**: Correct memory files to distinguish the two stores.

---

## 3. Part K — Executive Summary (White-language Q&A)

**Q1: 11/11 16:00 的 Cron 是否自然執行？**  
尚未到 16:00（稽核時間 14:20 CST）。0 筆 Nov 11 log 記錄。H3_PENDING。

**Q2: RC-2 是否真的在正式執行中生效？**  
尚未可驗證。RC-2 檔案 hash 正確（4eb6eacf...），下次 cron 執行時會使用此版本。但「有執行」不等於「有生效」。需等 16:05 後查 log。

**Q3: QG 是否通過？**  
上一次（Nov 10）QG FAIL（TWSE api_date=2026-11-09 ≠ target 2026-11-10）。Nov 11 QG 結果未知，需等 16:05 後確認。

**Q4: SQLite 是否更新？**  
Local SQLite 仍是 Nov 10 狀態（534,770 rows, max 2026-11-05）。Nov 11 Cron 尚未執行。

**Q5: 若未更新，實際原因是什麼？**  
H3_PENDING — Cron 尚未到 16:00，不是因為失敗，而是時間未到。

**Q6: T2 股票 2465 的 11/10 K 線來自哪裡？**  
來自 **Neon PostgreSQL**。`daily_prices[2465]` 在 Neon 中 max=2026-11-10，由 GitHub Actions 在 Nov 10 寫入。S71C Fixture 透過 `get_session()` → `USE_NEON=true` → Neon 取得此資料。

**Q7: T0 的 11/10 股價來自哪裡？**  
同樣來自 **Neon PostgreSQL**。`page_today` 內 `load_today_data()` 呼叫 `MAX(DailyPrice.date)` 透過 `get_session()` → Neon → 2026-11-10。

**Q8: 正式 SQLite 最新日期究竟是哪一天？**  
這個問題本身有歧義。需區分兩個資料庫：
- **Dashboard 使用（Neon）**: max = **2026-11-10**（這才是用戶看到的「最新」）
- **Local SQLite（cron backfill）**: max = **2026-11-05**（cron 的 write target，與 dashboard 無關）

**Q9: Session 71C 的截圖是否使用 Fixture？**  
是，使用 Isolated Fixture（port 8502）。但 Fixture 透過正式 app 程式碼連接 **Neon**（非 local SQLite），因此截圖呈現的是真實正式資料。

**Q10: Bundle A 的日期標示是否正確？**  
**是，完全正確。** `chart_freshness_header` 使用 `price_df["date"].max()` = Neon per-stock date = 2026-11-10。這是正確的設計。日期正確，資料來源正確，顯示文字正確。

**Q11: 有沒有把測試資料誤認成正式資料？**  
反過來。之前誤把「正式資料（Neon = 2026-11-10）」稱為「Fixture 生成的日期」，其實它是真實的 Neon production 資料。另外，S71B/C 誤把「Local SQLite（2026-11-05）」稱為「正式 DB 基線」，但 dashboard 從不讀 local SQLite。

**Q12: 是否需要任何修正？**  
**程式碼不需要修正。** Bundle A 實作正確，資料來源正確，日期邏輯正確。唯一需要的是**文件/記憶修正**：釐清「Local SQLite = backfill target」vs「Neon = dashboard source」的區別。

**Q13: 哪些問題仍然缺乏證據？**  
1. H3 Nov 11 16:00 cron 執行結果（`FILTER_EFFECT_UNVERIFIED`）
2. TWSE Nov 11 是否能提供正確 api_date（QG pass/fail 未知）
3. Local SQLite 111,710 筆 warrant-like 資料是否需要清理（需要額外授權決策）

**Q14: 是否可以繼續 Session 72？**  
可以，但 Session 71D 的指示明確禁止在此 session 開始 Session 72。H3 仍 PENDING，不阻塞 Bundle A 的驗收結案（已於 S71C 完成）。

**Q15: 哪些後續行動需要使用者另外授權？**  
1. **H3 最終確認**：16:05 後執行 `session71d_rc2_h3_runtime_audit.md` 的查驗程序
2. **Local SQLite warrant 清理**：111,710 筆 pre-RC2 warrant-like rows 是否需要刪除
3. **Neon warrant 確認**：Neon 中的 `len>4` entries（006201 等）是否為預期的 ETF 子基金
4. **Session 72 授權**：任何新功能開發、Phase 1B、或其他新 Session 的正式授權

---

## 4. Session 71D Deliverables

| File | Status |
|---|---|
| `docs/session71d_preflight.md` | ✓ Created |
| `docs/session71d_rc2_h3_runtime_audit.md` | ✓ Created |
| `docs/session71d_data_source_provenance.md` | ✓ Created |
| `docs/session71d_sqlite_identity_audit.md` | ✓ Created |
| `docs/session71d_bundle_a_freshness_verification.md` | ✓ Created |
| `docs/session71d_final_recommendation.md` | ✓ Created (this file) |

---

## 5. No Production Changes

| Check | Status |
|---|---|
| Python / Streamlit code | UNCHANGED |
| `components.py` | UNCHANGED |
| `market_watch.py` | UNCHANGED |
| `overview.py` | UNCHANGED |
| RC-2 (`backfill_daily_prices.py`) | UNCHANGED (hash `4eb6eacf...` verified) |
| Local SQLite | UNCHANGED (534,770 rows, max 2026-11-05) |
| Neon | UNCHANGED (read-only queries only) |
| Cron | UNCHANGED |
| ForwardSignals | UNCHANGED |
| MODEL_VERSION | v8.0 UNCHANGED |
