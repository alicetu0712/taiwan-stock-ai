# Session 71 — Rollback Plan

**Date**: 2026-11-11  
**Authorization**: AUTH-S71-BUNDLE-A

---

## 1. What Was Changed

5 existing files modified + 2 new files created.

| File | Action | Rollback Method |
|---|---|---|
| `dashboard/components.py` | CREATED | Delete file |
| `dashboard/_pages/market_watch.py` | MODIFIED | `git checkout dashboard/_pages/market_watch.py` |
| `dashboard/_pages/overview.py` | MODIFIED | `git checkout dashboard/_pages/overview.py` |
| `dashboard/_pages/research_backtest.py` | MODIFIED | `git checkout dashboard/_pages/research_backtest.py` |
| `dashboard/_pages/entry_timing_research.py` | MODIFIED | `git checkout dashboard/_pages/entry_timing_research.py` |
| `dashboard/app.py` | MODIFIED | `git checkout dashboard/app.py` |
| `tests/test_session71_bundle_a.py` | CREATED | Delete file |

---

## 2. Full Rollback Command Sequence

If the user decides to roll back ALL Bundle A changes:

```bash
# Step 1: Restore 5 modified files to their pre-Bundle-A state
git checkout -- dashboard/_pages/market_watch.py
git checkout -- dashboard/_pages/overview.py
git checkout -- dashboard/_pages/research_backtest.py
git checkout -- dashboard/_pages/entry_timing_research.py
git checkout -- dashboard/app.py

# Step 2: Remove 2 new files
rm dashboard/components.py
rm tests/test_session71_bundle_a.py

# Step 3: Verify rollback
shasum -a 256 scripts/backfill_daily_prices.py  # Must still be 4eb6eacf...
python3 -m pytest tests/ -q  # Must return 4276 pass / 37 fail (baseline)
```

---

## 3. Partial Rollback (per-file)

If only one change needs to be reverted:

| Issue | Rollback |
|---|---|
| T2 看盤 freshness header causing issues | `git checkout -- dashboard/_pages/market_watch.py` |
| T0 today page anchor causing issues | `git checkout -- dashboard/_pages/overview.py` |
| T5 research banner causing issues | `git checkout -- dashboard/_pages/research_backtest.py` |
| T6 entry timing banner causing issues | `git checkout -- dashboard/_pages/entry_timing_research.py` |
| Sidebar staleness color causing issues | `git checkout -- dashboard/app.py` |
| All freshness display issues | Delete `dashboard/components.py` + restore all 5 files |

---

## 4. What Rollback Does NOT Do

- Does NOT affect `scripts/backfill_daily_prices.py` (RC-2 unchanged, not part of Bundle A)
- Does NOT affect `scripts/hybrid_shadow_cron.py` (not modified)
- Does NOT affect any `src/` modules
- Does NOT affect `data/platform.db` (no DB writes occurred)
- Does NOT revert Session 69 or Session 70 documents
- Does NOT revert any research data

---

## 5. Rollback Safety Verification

After rollback, confirm:

```bash
# 1. RC-2 hash still correct
shasum -a 256 scripts/backfill_daily_prices.py
# Expected: 4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb

# 2. Test suite returns to baseline
python3 -m pytest tests/ -q
# Expected: 4276 passed, 37 failed, 4 skipped

# 3. components.py gone
ls dashboard/components.py  # Should show "No such file"

# 4. market_watch.py has no chart_freshness_header reference
grep "chart_freshness_header" dashboard/_pages/market_watch.py  # Should return nothing
```

---

## 6. Rollback Verdict

| Property | Status |
|---|---|
| Rollback is fully reversible | ✓ YES |
| Rollback commands are non-destructive | ✓ YES (only restores pre-existing tracked files) |
| Rollback does NOT affect RC-2 | ✓ CONFIRMED |
| Rollback does NOT affect DB | ✓ CONFIRMED |
| Rollback does NOT affect Cron | ✓ CONFIRMED |
| Independent per-file rollback possible | ✓ YES |
