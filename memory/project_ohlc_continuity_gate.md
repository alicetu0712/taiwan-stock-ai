---
name: project-ohlc-continuity-gate
description: OHLCContinuityGate 完整實作：DateStatus/GateResult enums、30-day 市場閘門、CG01–CG25 tests、dashboard H3 panel（1589 tests）
metadata:
  type: project
---

OHLC Continuity Gate 完整實作（Session 3）。

**Why:** MA20_SLOPE 需要 30 consecutive closes；gap 會讓斜率計算使用非連續時間段，產生看似正常卻不可信的交易決策。核心原則：寧可今天不產生 Hybrid 訊號，也不能使用不完整的資料。

**How to apply:** 任何涉及 signal generation 或 MA 計算的修改，必須先通過 OHLCContinuityGate。

---

## 完成項目

- `src/research/ohlc_continuity_gate.py` — 完整實作
  - DateStatus: DATA_AVAILABLE | MARKET_CLOSED | EXPECTED_DATA_MISSING | UNKNOWN
  - GateResult: PASS | BLOCKED_MISSING_OHLC | BLOCKED_INSUFFICIENT_HISTORY | BLOCKED_STALE_DATA | UNKNOWN_CALENDAR | NOT_APPLICABLE
  - CONTINUITY_WINDOW=30, MA20_BARS=20, TOTAL_SLOPE_BARS=30, REGIME_BARS=30, MIN_HIST_BARS=70, STALE_TOLERANCE_DAYS=7
  - Market gate (0050 proxy) + Stock gate (last 20 market-open days)

- `src/research/hybrid_forward_db.py` — 新增 `BLOCKED_MISSING_OHLC` RunStatus

- `scripts/run_hybrid_forward_shadow.py` — gate 整合（stale guard 之後、signal generation 之前）

- `scripts/hybrid_shadow_cron.py` — Step 4b fail-closed data freshness warning

- `tests/test_ohlc_continuity_gate.py` — CG01–CG25 全數通過

- Dashboard H3 panel — `_render_ohlc_continuity_panel` in entry_timing_research.py

- 5 docs: ohlc_continuity_audit.md, ohlc_feature_dependency.md, historical_ohlc_recovery.md, hybrid_first_capture_safety.md, hybrid_cron_final_readiness.md

## 關鍵設計決策

- 2026-10-09: TaiwanTradingCalendar 標記為 國慶日補假，但 DB 有 7,586 stocks 資料 → UNKNOWN（不阻擋）
- 30-day lookback: max(TOTAL_SLOPE_BARS=30, REGIME_BARS=30) = 30
- BLOCKED_MISSING_OHLC 不是 error，是 expected during accumulation phase

## 閘門當前狀態（2026-11-05）

Gate: **GateResult.PASS**（present=30, missing=0, unknown=0）  
Hybrid signal generation unblocked for 2026-11-05.

## Session 4 完成項目

- 0050 歷史 OHLC 回補：10 個日期（10-08 重寫、10-15/19/20/27/29/30、11-02/03/05 插入）
- 曆法修正：09-28、10-23、10-26 加入 `_TWSE_HOLIDAYS`（颱風閉市＋補假）
- 10-08 損壞資料修復（7,722 rows deleted）；10-09 確認節日刪除（7,586 rows）
- Cron Step 4b 改為 fail-closed（BLOCKED_STALE_DATA，不再 warn-and-continue）
- CG16-CG19 測試更新（反映 PASS 狀態）；ETD tests 2 筆更新（10-26 颱風假）
- HC26-HC30 新增（cron fail-closed + calendar + gate integration）
- scripts/recover_ohlc_0050.py：4 ruff errors 修正（timezone/E741/F541×2）
- 5 docs: historical_ohlc_recovery_report, trading_calendar_reconciliation, continuity_gate_root_cause_review, hybrid_cron_fail_closed_validation, hybrid_go_live_readiness

## 測試統計

**1594 tests total PASS**（0 failures）

## 仍需人工批准

1. Local crontab installation（見 docs/hybrid_go_live_readiness.md）
   - Entry 已備妥：`55 7 * * 1-5 cd ... && python3 scripts/hybrid_shadow_cron.py`
2. 異地備份設定（Dropbox/NAS）— 目前備份在同一台機器
