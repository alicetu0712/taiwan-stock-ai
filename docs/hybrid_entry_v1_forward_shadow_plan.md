# Hybrid Entry Strategy V1 — Forward Shadow Validation Plan

**Status:** ACTIVE — started 2026-11-05  
**Rule version:** hybrid_v1  
**Rule frozen commit:** 6602c3b  
**Operated by:** `scripts/run_hybrid_forward_shadow.py` (daily, after market close)

---

## 1. Purpose

This document specifies how prospective out-of-sample (OOS) validation of
Hybrid Entry Strategy V1 will be conducted.

**Key principle:** Evidence only accumulates from signals generated AFTER the
rule freeze date (2026-11-05).  Retrospective analysis cannot substitute.

---

## 2. What the Forward Shadow Does

The shadow pipeline (`scripts/run_hybrid_forward_shadow.py`):

1. Runs daily after market close for each stock in the universe
2. Generates an entry signal (via simplified EntryTimingAnalyzer logic)
3. Applies `HybridDecisionService` to decide: WAIT_PULLBACK or DIRECT_NEXT_OPEN
4. Records the full decision (features + action) in `hybrid_forward_shadow` SQLite table
5. Backfills outcome returns for records that matured ~20D earlier

**Shadow, not live:** This system records decisions but does NOT execute trades.
It is research infrastructure only and has no connection to ACTUAL/PAPER Trade
Service.

---

## 3. Schema

SQLite table: `hybrid_forward_shadow` in `data/platform.db`

```sql
CREATE TABLE IF NOT EXISTS hybrid_forward_shadow (
    stock_id              TEXT NOT NULL,
    signal_date           TEXT NOT NULL,
    rule_version          TEXT NOT NULL,
    v2_entry_label        TEXT,
    market_regime         TEXT,
    ma20_trend            TEXT,
    ma20_slope_pct        REAL,
    hybrid_action         TEXT NOT NULL,     -- WAIT_PULLBACK / DIRECT_NEXT_OPEN
    rule_reason           TEXT,
    rule_priority         INTEGER,
    feature_cutoff_date   TEXT,
    calculated_at         TEXT,
    -- filled in after hold period matures (~20D later)
    outcome_5d            REAL,
    outcome_10d           REAL,
    outcome_20d           REAL,
    outcome_recorded_at   TEXT,
    PRIMARY KEY (stock_id, signal_date, rule_version)
);
```

**Idempotency key:** `(stock_id, signal_date, rule_version)` — `INSERT OR IGNORE`
prevents double-counting if the script runs twice on the same day.

---

## 4. Outcome Measurement

Outcomes are measured as net return (gross − 0.585% fees):

- `outcome_5d`:  close[D+5] vs close[D+1] − fees (approximate; uses close, not fill price)
- `outcome_10d`: close[D+10] vs close[D+1] − fees
- `outcome_20d`: close[D+20] vs close[D+1] − fees (primary metric)

**Limitation:** Outcomes use daily close prices, not actual fill prices.  This
is an approximation; actual fills depend on the trigger mechanism (CONFIRMED_NEXT_OPEN
for WAIT_PULLBACK, DIRECT_NEXT_OPEN for immediate).  For prospective validation,
this systematic approximation is consistent across all records.

---

## 5. No-Lookahead Guarantee

The forward shadow enforces temporal integrity:

| Invariant | Mechanism |
|---|---|
| Features from signal_date only | `_get_signal_today()` uses `date <= signal_date` filter |
| No future prices used in decision | HybridDecisionService stateless; no DB reads during decide() |
| Outcome backfilled separately | Only records with `signal_date <= today − 30D` get outcomes |
| Idempotent inserts | `INSERT OR IGNORE` — existing records never updated |

---

## 6. Run Schedule

Recommended daily schedule (after Taiwan market close, ~15:00 TWT):

```bash
python scripts/run_hybrid_forward_shadow.py

# Or with explicit date:
python scripts/run_hybrid_forward_shadow.py --date 2026-11-05
```

Signals before 2026-11-05 are automatically rejected with a warning.

---

## 7. Validation Milestones

### Milestone 1 — First Check (2027-01)

**Trigger:** ≥ 50 matured OOS signals  
**Analysis:** Summary stats only (no CI — too few signals)  
**Expected:** Hybrid delta direction confirmation

### Milestone 2 — Provisional Assessment (2027-06)

**Trigger:** ≥ 200 matured OOS signals  
**Analysis:** Full three-strategy comparison with 95% CI  
**Pass criterion:**
- Hybrid vs V1 delta ≥ 0
- Bear regime subgroup positive delta

### Milestone 3 — Validation (2027-12 or later)

**Trigger:** ≥ 500 matured OOS signals + ≥ 12 months of data  
**Analysis:** Walk-forward (3-month windows), subgroup Bonferroni correction  
**Pass criterion (PROVISIONAL PASS):**
- Hybrid vs V1: 95% CI lo > 0
- Bear and Flat MA20 subgroup deltas both positive
- No walk-forward window < −1.5pp

---

## 8. Abort Criteria

Stop the shadow and re-evaluate Hybrid V1 rules if:

| Condition | Action |
|---|---|
| Hybrid vs V1 OOS delta < −0.5pp at ≥ 100 signals | Pause shadow; review rule logic |
| Bear regime OOS delta < −1.0pp at ≥ 50 bear signals | Pause P1 rule; continue with P2 only |
| Fill rate for WAIT_PULLBACK < 50% (consistently) | Review trigger threshold (SA-1) |

If abort criteria are triggered:
1. Document the finding in a new research note
2. Do NOT modify the frozen hybrid_v1 rules — freeze them as "REJECTED"
3. Create hybrid_v2 with revised rules (new freeze, new pre-registration)

---

## 9. What the Shadow Does NOT Do

- Does NOT affect live trading signals (MODEL_VERSION v8.0, BUY/STRONG_BUY thresholds)
- Does NOT write to production Neon ForwardSignal table
- Does NOT modify ACTUAL or PAPER trade positions
- Does NOT trigger production deployments

It is append-only research infrastructure operating entirely in local SQLite.

---

## 10. Monitoring

Dashboard: Entry Timing Research → 🔀 Hybrid 策略 → 🔮 前瞻影子 tab

Shows:
- Total shadow records
- Matured records with outcomes
- Average 20D outcome by action type
- Sample size warnings

---

## 11. Expected Timeline

| Date | Expected OOS signals | Status |
|---|---|---|
| 2026-11-05 | 0 | Shadow starts |
| 2026-12-01 | ~200 (25D × ~8 stocks/day) | First month |
| 2027-01-15 | ~500 | Milestone 1 check |
| 2027-06-01 | ~2,000 | Milestone 2 provisional assessment |
| 2027-12-01 | ~5,000+ | Milestone 3 full validation |

Stock count per day varies with market conditions and signal filter.
Estimates based on 150-stock universe × 20–30% signal rate.
