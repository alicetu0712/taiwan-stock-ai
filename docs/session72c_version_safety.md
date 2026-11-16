# Session 72C — Version Safety

**Session**: 72C  
**Verdict**: `VERSION_SAFETY_PASS`  
**Date**: 2026-11-13

---

## Official Strategy Version

| Item | Expected | Verified | Method |
|---|---|---|---|
| MODEL_VERSION | "v8.0" | ✓ Read from `src/database.py:MODEL_VERSION` | grep + import test |
| UI Version | "v6.8" | ✓ Hardcoded in page_config title | grep in app.py |
| Decision Engine | "v2.0" | ✓ Static in version info page | _render_version_info() |
| foe_v1 unchanged | No modification | ✓ Not referenced in any new app.py code | grep: 0 hits |
| Breakout Logic | v8.0 | ✓ Used by production recommendation engine | unchanged |

---

## V3 Frozen Status

| Check | Result |
|---|---|
| V3 code activated in app.py | ABSENT — `test_v3_not_activated` PASSED |
| V3 results shown as official signals | ABSENT — no V3 import in app.py |
| V3 visible in version info | ✓ SHOWN AS FROZEN — `_render_version_info()` table shows "V3 Entry Timing → Frozen（已凍結，未啟用）" |
| V3 would affect any trading recommendation | NO — Frozen state confirmed by test |

---

## Shadow Research Separation

| Check | Result |
|---|---|
| V2 Shadow signals shown as official BUY/SELL | NO — `page_entry_timing_research` has research-only warning |
| 進場研究 tab has research-only banner | ✓ — `st.info("此頁面為研究用途——結果僅供參考，不屬於正式交易訊號。", icon="🔬")` |
| Shadow promoted to main navigation | NO — in sub-tab under 策略績效 |
| Legacy backtest shown as current performance | NO — clearly labeled "Legacy驗證（V1 Historical）" |

---

## Version Display Rules

| Context | What is Shown |
|---|---|
| Sidebar (all users) | `正式策略：v8.0` via `st.caption(f"正式策略：{_MV}")` |
| 系統管理 → 版本資訊 | Full version taxonomy table |
| 進場研究 | `🔬` research-only banner |
| 策略績效 → 歷史回測 → Legacy | `📦 Legacy 驗證（V1 Historical）` label |
| General user pages | No version numbers shown except Official Strategy |

---

## UI Version ≠ Model Version

Confirmed by `test_ui_version_not_conflated_with_model_version` (PASSED):
- Sidebar shows "v6.8" as UI version
- Sidebar shows MODEL_VERSION separately via `st.caption(f"正式策略：{_MV}")`
- `_render_version_info()` explicitly shows separate rows for UI Version and Model Version

---

## Conclusion

All version safety requirements met:
- ✓ Official strategy v8.0 not changed
- ✓ V3 frozen and labeled
- ✓ foe_v1 unchanged (not touched)
- ✓ Shadow not promoted to official
- ✓ Legacy not conflated with current performance
- ✓ UI version and model version shown separately
