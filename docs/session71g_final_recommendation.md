# Session 71G — Final Recommendation

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / MIGRATION_DESIGN_ONLY  
**Zero implementation performed**

---

## 1. Part K — Final Verdicts

| Category | Verdict |
|---|---|
| **Architecture** | `LAUNCH_AGENT_RECOMMENDED` |
| **Catch-up Policy** | `CONTROLLED_CATCHUP_RECOMMENDED` (Option B: 20:00 CST deadline) |
| **Concurrency** | `CONCURRENCY_GAPS_IDENTIFIED` |
| **Migration Design** | `MIGRATION_DESIGN_READY` |
| **RC-2** | `H3_PENDING` |
| **Production** | `PRODUCTION_UNCHANGED_VERIFIED` |
| **Authorization** | `NO_SCHEDULER_CHANGE_AUTHORIZED` |

---

## 2. Documents Produced

| Document | Status | Key Finding |
|---|---|---|
| `session71g_scheduler_contract.md` | COMPLETE | 2-stage QG; backfill has NO FileLock — `CONTRACT_MISMATCH` |
| `session71g_launchd_architecture_decision.md` | COMPLETE | LaunchAgent design; log overwrite risk noted |
| `session71g_catchup_safety_policy.md` | COMPLETE | Option B (20:00 CST) recommended; next-day catch-up risk analyzed |
| `session71g_concurrency_idempotency_audit.md` | COMPLETE | Same-day sequential re-run gap; shadow runner unaudited |
| `session71g_security_environment_design.md` | COMPLETE | No secrets in plist; log truncation risk; dotenv safe |
| `session71g_cutover_rollback_plan.md` | COMPLETE | Atomic cutover; <60s dual-scheduler window; full rollback steps |
| `session71g_acceptance_test_plan.md` | COMPLETE | H3 (Phase 1) and launchd (Phase 2) test matrices |
| `session71g_final_recommendation.md` | COMPLETE | This document |

---

## 3. Part L — Executive Summary (Q&A)

**Q1: 目前 Cron 的真正執行流程是什麼？**  
七步流程（code-confirmed）：(1) FileLock → (2) 交易日確認 → (3) 時間 ≥ 15:30 確認 → (4) `backfill_daily_prices.py`（內部含 QG-1~QG-7，`INSERT OR IGNORE`） → (4b) 事後 freshness gate（0050 日期確認 + 5000股 threshold，最多 retry 3 次 × 30 分鐘） → (5) SQLite 備份 → (6) shadow runner → (7) 釋放 Lock + 寫 state file。

**Q2: LaunchAgent 還是 LaunchDaemon 比較適合？**  
**LaunchAgent**（`~/Library/LaunchAgents/`）。Script 使用使用者身份（alicetu），無需 root 權限，使用使用者 `.env` 和 file ownership。LaunchDaemon 需要 root 或 `UserName` key，不必要地提升了權限，增加維護複雜度。

**Q3: launchd 是否能解決睡眠漏跑？**  
**大部分情況可以**，但有條件：
- LaunchAgent 需要「用戶 session 活躍」才能觸發 catch-up（DarkWake 無效）
- 機器必須在同一天內（23:59 CST 前）有完整喚醒（lid open 或螢幕亮起）
- `PLATFORM_BEHAVIOR_UNVERIFIED`：catch-up 窗口大小（empirically 30-120 秒），以及 DarkWake 是否觸發 LaunchAgent，均無 Apple 官方文件保證
- **比傳統 cron 好**（cron 完全不 catch-up），但不是 100% 保證

**Q4: 補執行會帶來什麼風險？**  
主要風險：次日喚醒的 catch-up（`date.today()` 變成次日）→ 當天資料永久遺失。現有 script 無此保護。建議加入 Execution Validity Window（見 Q5）。次要風險：同天二次執行（FileLock 防止並行；但完成後的 sequential re-run 可能觸發 shadow runner 兩次）。

**Q5: 建議使用哪一種有效執行時間政策？**  
**Option B（Controlled Catch-up: 15:30–20:00 CST）**。允許最多 4 小時的 catch-up 視窗（涵蓋大多數用戶的使用情境），同時防止次日誤觸發。需要在 `hybrid_shadow_cron.py` 加入 `_within_validity_window()` 函數（需要另外授權）。

**Q6: 目前是否有 Process Lock？**  
**是，但僅在 wrapper 層**。`hybrid_shadow_cron.py` 使用 `fcntl.flock(LOCK_EX|LOCK_NB)`。`backfill_daily_prices.py` 獨立執行時**沒有**鎖保護（`CONTRACT_MISMATCH`）。

**Q7: 是否能防止同一天重複寫入？**  
**Row level YES，Pipeline level PARTIAL**。
- `INSERT OR IGNORE`：重複 `(stock_id, date)` row 被忽略 ✓  
- same-day re-run guard：**不存在**。若 cron 完成後 launchd 再次觸發，backfill 會跑一遍（找不到缺失日期 → 0 新增），但 shadow runner 可能再跑一次。

**Q8: 如何避免 Cron 與 launchd 同時執行？**  
Atomic cutover：(1) 確認無正在執行的 job → (2) 移除 crontab 條目 → (3) 寫入 plist → (4) `launchctl bootstrap` → 整個窗口 < 60 秒。在 15:55–16:05 CST 以外的時段執行。若有重疊，FileLock 會讓第二個 instance 以 `BLOCKED_LOCK` 乾淨退出。

**Q9: 是否需要修改任何正式 Python 程式？**  
**有條件**。launchd 遷移本身可在不修改 Python 程式的情況下進行，但有三個安全性缺口需要補：
1. `hybrid_shadow_cron.py`：加入 Execution Validity Window（防止次日 catch-up）
2. `hybrid_shadow_cron.py`：加入 same-day run guard（防止 shadow runner 重複執行）
3. `backfill_daily_prices.py`：加入 cron lock 檢查（獨立執行時防止衝突）

以上均需要獨立授權，不阻塞遷移，但建議在 launchd 切換同時或之前處理。

**Q10: 是否需要新增安全保護？**  
是，但均非緊急阻塞項：
- Execution Validity Window（MEDIUM priority）
- Same-day run guard（MEDIUM priority）
- Backfill standalone lock check（LOW priority）
- Shadow runner same-day dedup audit（MEDIUM priority — not fully audited this session）

**Q11: 如何進行安全切換？**  
（1）非交易時段執行（周末或 09:00–15:00 CST）→（2）確認無 running job → （3）備份 crontab → （4）移除 crontab entry（原子操作）→（5）寫入 plist → （6）`launchctl bootstrap gui/$UID <plist>` → （7）驗證單一 scheduler → 完成。全程 < 5 分鐘。見 `session71g_cutover_rollback_plan.md` G3 節。

**Q12: 如果遷移失敗，如何回滾？**  
（1）`launchctl bootout gui/$UID <label>` → （2）`crontab ~/Desktop/crontab_backup_<date>.txt` → （3）驗證 cron 恢復。估計時間 < 2 分鐘。無需資料回滾（除非有非預期寫入，需另行授權）。

**Q13: 111,710 筆歷史資料是否需要先處理？**  
**否**。歷史 warrant data（`len(stock_id) > 4`，pre-RC2 寫入）是獨立問題，與排程器遷移無關。RC-2 filter 已防止新的五碼以上 ID 寫入。歷史清理需要另外授權，不得作為遷移前置條件。

**Q14: RC-2 H3 是否仍 PENDING？**  
**是。** `H3_PENDING`。需要 2026-11-12 16:00 CST 的自然 cron 觸發並完成 H3 驗收程序（見 `session71g_acceptance_test_plan.md` Phase 1）。launchd 安裝 ≠ H3 PASS。

**Q15: 是否已經具備正式遷移條件？**  
**Migration Design READY，但 Authorization PENDING**。已完成：
- 完整呼叫鏈 code 確認
- LaunchAgent 設計（含 plist）
- Catch-up Safety Policy
- Concurrency Audit
- Security/Environment Design
- Cutover + Rollback Plan
- Acceptance Test Plan

缺少：用戶明確授權「執行遷移」。

**Q16: 還需要使用者授權哪些事項？**

| 事項 | 優先順序 | 備注 |
|---|---|---|
| H3 完成（Nov 12 自然 cron） | 高 | 需確保機器 16:00 喚醒 |
| launchd 遷移（`AUTHORIZED: execute migration`） | 中 | H3 完成後建議進行 |
| Execution Validity Window 程式修改 | 中 | 建議與遷移同時進行 |
| Same-day run guard 程式修改 | 中 | 建議與遷移同時進行 |
| Shadow runner same-day dedup 稽核 | 中 | 未在本 Session 完成 |
| 111,710 筆歷史 warrant data 清理 | 低 | 獨立工作項目 |
| Backfill standalone lock check | 低 | 安全加固 |

---

## 4. Session 71G Outcome

| Item | Verdict |
|---|---|
| **Call chain confirmed** | `CODE_VERIFIED` — from actual Python files |
| **Architecture** | `LAUNCH_AGENT_RECOMMENDED` |
| **Catch-up policy** | `CONTROLLED_CATCHUP_RECOMMENDED` |
| **Concurrency gaps** | `CONCURRENCY_GAPS_IDENTIFIED` (3 gaps; none blocking) |
| **Migration design** | `MIGRATION_DESIGN_READY` |
| **H3** | `H3_PENDING` → 2026-11-12 16:00 CST |
| **Production** | `PRODUCTION_UNCHANGED_VERIFIED` |
| **Implementation performed** | `ZERO` |
| **Authorization compliance** | `STRICT_READ_ONLY_VERIFIED` |
