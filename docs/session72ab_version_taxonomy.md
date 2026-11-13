# Session 72AB — Version Taxonomy

**Session**: 72AB  
**Verdict**: `VERIFIED`

---

## Version Registry

| Component | Version | Location | Status | Display Rule |
|---|---|---|---|---|
| UI | v6.8 | `app.py` page_title | Active | Sidebar footer only |
| 正式模型 (Strategy) | v8.0 | `src/database.py:MODEL_VERSION` | Active | Sidebar: `正式策略：v8.0` |
| V1 Model (frozen label) | v8.0 | `src/database.py:V1_MODEL_VERSION` | Frozen | Internal only |
| Decision Engine | v2.0 | `src/engines/decision.py` | Active | 版本資訊頁 only |
| foe_v1 (Forward Outcome) | v1 | `src/engines/outcome_evaluation.py` | Active | 版本資訊頁 only |
| overnight_v1 | v1 | `src/engines/overnight_risk.py` | Active | 版本資訊頁 only |
| Candidate Pool | v1.0 | `src/services/candidate_pool_service.py` | Active | 版本資訊頁 only |
| Entry Timing V2 | v2 | `src/research/` | Shadow (研究中) | Research-only label |
| Breakout Logic | v8.0 | `src/engines/breakout.py` | Active | 版本資訊頁 only |
| V3 Entry Timing | v3 | `src/engines/v3_entry/` (if exists) | **Frozen** | "Frozen — 未啟用" label |

---

## Display Rules by Page Type

### 一般使用者頁面（今日決策、個股分析、我的持倉）
```
正式策略：v8.0
```
No other version identifiers shown. Users should not need to understand version numbers.

### 策略績效頁面
Show research-only banner on Shadow/V2/V3 content:
```
此結果僅供研究，不屬於正式交易訊號。
```

### 系統管理 → 版本資訊（唯一完整版本展示頁）
Full table as implemented in `_render_version_info()` in isolated `app.py`.

---

## What NOT to Do

| Mistake | Correct Approach |
|---|---|
| `MODEL_VERSION = "v6.8"` | `MODEL_VERSION = "v8.0"` (UI version ≠ model version) |
| Show V3 in main navigation | V3 is Frozen — only visible in 版本資訊 with "Frozen" label |
| Show V2 shadow as official BUY | Explicit `research_only` empty_state label required |
| Replace all version numbers with `MODEL_VERSION` variable | UI version stays "v6.8"; model version uses `MODEL_VERSION` variable |
| Activate V3 by importing v3 modules | No v3 imports in production or isolated app.py |
