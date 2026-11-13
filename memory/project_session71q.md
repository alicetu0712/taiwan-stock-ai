---
name: project-session71q
description: S71Q H3 最終結論：Guard AUTHORIZED 確認；QG 全部失敗（TWSE 結構性限制）；H3_GUARD_AUTHORIZED_QG_NEVER_PASSED
metadata:
  type: project
---

Deploy A 後首次自然 Cron 執行完整觀察。2026-11-13 16:00:00 CST 準時觸發，Guard 授權確認，但 TWSE 資料全日未更新，QG 4 次全部失敗。

**Why:** Deploy A 於 01:35 CST 完成（S71P）。H3 需要 Cron 觸發 + Guard 授權 + QG PASS + SQLite 寫入 + RC-2 Filter Runtime 全部確認。

**How to apply:** Guard 授權已確認（Deploy A 功能正常）。QG 失敗是 TWSE 結構性限制（與 Nov 10 相同）。全套 H3 需等下一個 TWSE 資料及時發布的交易日。

**Nov 13 執行完整紀錄**:
- 08:00:00Z = 16:00 CST：Cron 觸發 ✓
- Guard：AUTHORIZED（無 BLOCKED，exit_code=0 × 4）✓
- Initial run (08:00-08:02Z)：QG FAILED（api_date=2026-11-12 ≠ 2026-11-13）
- Retry 1 (08:32-08:35Z)：QG FAILED（同上）；中間 Mac 睡眠 ~5 小時
- Retry 2 (13:32-13:34Z = 21:32 CST)：QG FAILED（TWSE 仍給 Nov 12）
- Retry 3 (14:04-14:05Z = 22:04 CST)：QG FAILED（同上）
- Final status：`BLOCKED_STALE_DATA`；lock=released；wrapper 正常退出

**H3 最終狀態**：`H3_GUARD_AUTHORIZED_QG_NEVER_PASSED`

**QG 失敗根因**：TWSE API 全天（16:00–22:05 CST）只提供 api_date=2026-11-12（昨日資料）。與 Nov 10 完全相同模式。TWSE 只提供最新一筆發布資料，不支援同日即時查詢。非 code 問題，非 guard 問題。

**SQLite 結果**：534,770 rows / MAX(date) 2026-11-05（完全未變）

**Production hashes（全部未變）**:
- `backfill_daily_prices.py`: `202e2231...`（Deploy A，Guarded 版本）
- `hybrid_shadow_cron.py`: `46209171...`
- `scheduler_safety_guards.py`: `f6929a7c...`
- `dashboard/app.py`: `709e161c...`

**9 份文件（全部更新至最終結果）**：
1. session71q_preflight.md
2. session71q_sleep_wake_timeline.md
3. session71q_cron_execution_evidence.md（CRON_TRIGGERED_BLOCKED_STALE_DATA）
4. session71q_guard_lock_evidence.md（GUARD_AUTHORIZED_CONFIRMED）
5. session71q_quality_gate_evidence.md（ALL_FAILED_STRUCTURAL）
6. session71q_rc2_h3_evidence.md（H3_GUARD_AUTHORIZED_QG_NEVER_PASSED）
7. session71q_sqlite_freshness.md（SQLITE_UNCHANGED）
8. session71q_production_integrity.md（VERIFIED）
9. session71q_final_verdict.md（FINAL）

[[project_session71p]] — Deploy A 完成（01:35 CST）
[[project_session71f]] — Sleep root cause（Clamshell→DarkWake）
