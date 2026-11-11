# Session 70 — Final Recommendation

**Audit Date**: 2026-11-11  
**Scope**: Data Freshness & Signal Transparency  
**Execution Mode**: READ_ONLY_DESIGN_AND_VALIDATION — no production changes

---

## 1. What Was Done

| Task | Status |
|---|---|
| Data freshness audit (per-page) | COMPLETE |
| Signal provenance matrix (8 signal types) | COMPLETE |
| DataFreshnessContract design | COMPLETE |
| SignalDisplayContract (per-page) | COMPLETE |
| Shared UI component specs (5 components) | COMPLETE |
| Acceptance test plan (14 test cases) | COMPLETE |
| Implementation roadmap (Phase 0–3) | COMPLETE |
| Production state baseline | VERIFIED UNCHANGED |

---

## 2. Current State Assessment

### What Works (Do Not Touch)
- T1 盤中: live/stale distinction via `quote_date_status()` — **GOOD**
- T6 進場時機: `_render_dailyprice_freshness_panel()` — **GOOD** (reference implementation)
- T0 今日: candidate pool `as_of_label` — **ACCEPTABLE**
- T0 今日: auto-redirect "資料庫最新完成日期" notice — **ACCEPTABLE**
- Sidebar: `st.caption("最新：{newest}")` — exists, but needs staleness color

### Critical Gaps
1. **T2 看盤 K-chart**: Shows historical price chart with ZERO date indicator. User viewing on 2026-11-11 sees chart ending at 2026-11-05 without knowing data is 5 days old. **SEVERITY: HIGH**
2. **T2 看盤**: No "EOD data · non-realtime" label during market hours. **SEVERITY: HIGH**
3. **T0 今日**: Freshness anchor only appears when `days_old > 1` relative to `selected_date`. When viewing the latest available date, no indicator shows the data is stale relative to today. **SEVERITY: MEDIUM**
4. **T5/T6 Research**: No prominent "RESEARCH ONLY" banner in the UI. Only exists in docstrings and inline HTML. **SEVERITY: HIGH** (research integrity)
5. **T4 證據**: No "last evaluation date" shown. User cannot tell if outcomes are current. **SEVERITY: MEDIUM**

---

## 3. Priority Ranking

| Rank | Gap | Pages | Fix | Risk | Effort |
|---|---|---|---|---|---|
| 1 | No chart date indicator on K-chart | T2 | `chart_freshness_header()` | NONE | XS |
| 2 | No RESEARCH ONLY banner | T5, T6 | `research_only_banner()` | NONE | XS |
| 3 | T0 missing persistent freshness anchor | T0 | `data_freshness_banner()` | NONE | XS |
| 4 | Sidebar staleness no color | Sidebar | `data_freshness_banner(compact=True)` | LOW | XS |
| 5 | T4 no evaluation date | T4 | Add `MAX(forward_signal.trade_date)` label | NONE | XS |

All top 5 fixes are **XS effort + ZERO/LOW risk + display-only**.

---

## 4. The One Fix That Matters Most

**Fix T2 看盤's missing chart date label.**

This is the highest-impact, zero-risk change. Currently:
```
User opens 看盤 → sees K-chart → assumes data is current → makes decisions
                     ↑
                  SILENT: chart ends at 2026-11-05 (5 days ago)
```

After fix:
```
User opens 看盤 → sees "K 線資料截至：2026-11-05 ⚠️ 落後 5 個交易日"
               → K-chart clearly dated
               → "EOD · 非即時" badge visible
```

Change: 5 lines in `market_watch.py` + new `dashboard/components.py`. Zero risk.

---

## 5. 10 Key Q&A

| Q | A |
|---|---|
| Q1. 哪個頁面資料新鮮度問題最嚴重？ | T2 看盤 — K 線圖完全沒有任何日期標示 |
| Q2. T0 目前有沒有任何新鮮度標示？ | 有，但只有在 days_old > 1 時才顯示。當看最新日期時，完全沒有標示 |
| Q3. T1 盤中的新鮮度處理算好嗎？ | 是，live/stale 判斷完整，可作為參考 |
| Q4. T6 有沒有現成的 freshness panel？ | 有！`_render_dailyprice_freshness_panel()` 是最好的參考實作 |
| Q5. 新元件要放在哪個檔案？ | 新建 `dashboard/components.py` |
| Q6. 是否需要修改 loaders.py 的 TTL？ | 不需要，TTL 合理；只需要 display 層加標示 |
| Q7. 研究頁面（T5/T6）的 freshness 是哪種？ | IS/OOS 截止日（2026-10-09）是正確的 research freshness，不是 "stale" |
| Q8. 實作時是否會影響任何計算？ | 完全不會 — 所有修改都是 display-only |
| Q9. 多少個 test 需要通過？ | 14 個驗收測試（L1 contract + L2 UI + edge cases） |
| Q10. 整個 Phase 1A 要多久？ | 估計 2–3 小時，全部在 T2/T0/T5/T6/Sidebar 加標示 |

---

## 6. What Must NOT Change

| Item | Reason |
|---|---|
| `_render_dailyprice_freshness_panel()` | Reference implementation — keep exactly as-is |
| `overview.py` `freshness_html` conditional | Existing logic is correct — only extend |
| `quote_date_status()` | Correct stale detection |
| `RESEARCH_CUTOFF_DATE = 2026-10-09` | Research IS/OOS boundary — not a staleness date |
| All computation in `main.py` | Pipeline logic untouched |
| RC-2 patch | H3/H4 pending |
| foe_v1 protocol | Frozen |
| MODEL_VERSION v8.0 | Frozen |

---

## 7. Next Session Proposal

**Bundle A — 零風險顯示修正** (can be done in one session, 2–3 hours):

1. Create `dashboard/components.py` with 4 components
2. Add `chart_freshness_header()` to T2 看盤 (P1A-02)
3. Add `data_freshness_banner()` to T0 今日 (P1A-03)
4. Add `research_only_banner()` to T5 and T6 (P1A-04, P1A-05)
5. Upgrade sidebar caption to colored `data_freshness_banner()` (P1A-06)

**Gate**: 14 acceptance tests pass before merge.

**What to tell the user**: "我想在下一個 session 實作 Session 70 設計的五項資料新鮮度顯示修正（Bundle A），全部都是 display-only 修改，不影響任何計算。需要你授權。預計 2–3 小時，可以在同一個 session 完成。"

---

## 8. Session 70 Verdict

| Category | Status |
|---|---|
| Data Freshness Audit | `AUDIT_COMPLETE` |
| Signal Provenance Matrix | `MATRIX_COMPLETE` |
| DataFreshnessContract | `SPEC_COMPLETE` |
| SignalDisplayContract | `SPEC_COMPLETE` |
| Shared Components | `SPEC_COMPLETE` |
| Acceptance Tests | `PLAN_COMPLETE` |
| Implementation Roadmap | `ROADMAP_COMPLETE` |
| Production Code | `UNCHANGED_VERIFIED` |
| Authorization | `DESIGN_ONLY — IMPLEMENTATION_PENDING_USER_AUTHORIZATION` |

---

## 9. White-Paper Summary

**「資料目前落後幾天、使用者知道嗎？各頁面應該怎麼顯示才不會誤導？」**

**現況**：DailyPrice 最新日期是 2026-11-05，落後 5 個交易日。整個平台只有側邊欄有一行細字「最新：2026-11-05」。T2 看盤的 K 線圖完全沒有日期標示，使用者看到的 breakout 訊號其實是 5 天前的分析，根本不知道。

**最嚴重的問題**：T2 看盤。使用者在 2026-11-11 看到一張沒有日期標示的 K 線圖，預設以為是今天的資料。這不是技術 bug，是資訊設計問題。修法：在圖表上方加一行「K 線資料截至：2026-11-05 ⚠️ 落後 5 個交易日」。5 行程式碼，零風險。

**其次**：T5/T6 研究頁面沒有醒目的「研究專區」標示，使用者可能把研究訊號當作交易指令。加個 banner，30 分鐘搞定。

**現有優點**：T1 盤中的即時 vs 收盤後判斷做得很好，T6 裡有 `_render_dailyprice_freshness_panel()` 是全平台唯一的完整 freshness panel，可以當 reference。

**具體行動**：建立 `dashboard/components.py`，放 4 個 UI 元件，然後在 T0/T2/T5/T6/Sidebar 各加幾行呼叫。全部 display-only，不影響任何計算，可以隨時 git revert。
