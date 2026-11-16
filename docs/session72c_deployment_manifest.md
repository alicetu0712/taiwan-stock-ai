# Session 72C — Deployment Manifest

**Session**: 72C  
**Status**: `DEPLOYMENT_MANIFEST_COMPLETE`  
**Authorization**: NOT_AUTHORIZED (requires explicit user authorization)  
**Date**: 2026-11-13

---

## Files to Deploy

| File | Source | Target | Isolated SHA256 | Required | Notes |
|---|---|---|---|---|---|
| `dashboard/app.py` | `stock_platform_72ab/dashboard/app.py` | `stock_platform/dashboard/app.py` | `aee5cd34ca285e2b122ba8cb79c663bfecfa20df9b240da9254e76ecb83a002d` | REQUIRED | Main navigation rewrite; 5-tab structure |
| `dashboard/components.py` | `stock_platform_72ab/dashboard/components.py` | `stock_platform/dashboard/components.py` | `907fa356b8335dad44b59c67622c947aac769d6aeb69b927fc2d21e7cfffcc81` | REQUIRED | Adds `empty_state()` function |

**Total**: 2 files.

---

## Files NOT Changed — Confirm Unchanged Before Deploy

| File | Expected Production SHA256 | Action |
|---|---|---|
| `scripts/backfill_daily_prices.py` | `202e2231...` | Verify unchanged |
| `scripts/hybrid_shadow_cron.py` | `46209171...` | Verify unchanged |
| `scripts/scheduler_safety_guards.py` | `f6929a7c...` | Verify unchanged |
| All `dashboard/_pages/*.py` | (various) | Verify unchanged — isolated versions identical to production |

---

## Pre-Deploy Checklist

1. `sha256sum stock_platform/dashboard/app.py` → must equal `709e161c...` (current production)
2. `sha256sum stock_platform/dashboard/components.py` → record for rollback
3. Confirm `USE_NEON=true` and `NEON_URL` are in `.env` (needed for `entry_timing_research.py`)
4. Remove prototype badge from isolated `app.py` before copying (line 247: `<span class="s72ab-badge">72AB 隔離版</span>` → remove the span)
5. Verify no other files in `stock_platform_72ab/dashboard/` differ from production

---

## Pre-Deploy: Remove Prototype Badge

Before copying `app.py` to production, remove the prototype marker:

```python
# Line 247 in isolated app.py — REMOVE before deploy:
# '<div style="font-size:0.7rem; color:#999; margin-top:3px">v6.8 <span class="s72ab-badge">72AB 隔離版</span></div>'
# Replace with original:
# '<div style="font-size:0.7rem; color:#999; margin-top:3px">v6.8</div>'
```

---

## No New Dependencies

| Dependency | Added? | Notes |
|---|---|---|
| New Python module | NO | `empty_state()` uses only `streamlit` (already installed) |
| New CSS | NO | Only the `.s72ab-badge` class (remove before deploy) |
| New assets | NO | |
| New config | NO | |
| New environment variables | NO | |
| New feature flags | NO | |
| New test fixtures | NO | |

---

## Deploy Scope Confirmation

This deployment changes ONLY the presentation layer:
- Navigation structure (10 tabs → 5 tabs)
- Tab grouping and labeling
- Sub-tab vs radio button for 2 sections in 策略績效
- Exception handling for `_render_version_info()`
- Addition of `empty_state()` to components

No service logic, signal computation, model scoring, backtest formula, forward outcome definition, or data write path is changed.
