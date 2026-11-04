# Hybrid Forward Shadow — Data Lineage

**Rule version:** hybrid_v1  
**Rule freeze date:** 2026-11-05 (commit 6602c3b)

---

## Data Flow

```
DailyPrice (SQLite)          ForwardSignal (Neon PostgreSQL)
      │                                 │
      ▼                                 ▼
TradingCalendar              ForwardSignalService.get_signals_for_date()
(0050 proxy)                 (research_version=v2_research_v2)
      │                                 │
      └─────────────┬───────────────────┘
                    ▼
          HybridEntryStrategy.classify()
          (rule_version=hybrid_v1, frozen)
                    │
                    ▼
          classify_capture()          ◄── trade_date vs RULE_FREEZE_DATE
          + compute_decision_hash()       trade_date vs captured_at
                    │
                    ▼
          hybrid_forward_decision     (append-only, never updated)
                    │
                    ▼  (after maturity_date passes)
          hybrid_forward_outcome      (append-only, keyed by decision_id+horizon)
                    │
                    ▼
          hybrid_forward_run_log      (one row per execution)
```

---

## Input Sources

### DailyPrice (SQLite — research DB)

- **Location:** `data/platform.db`, table `daily_prices`
- **Schema:** `stock_id, date, open, high, low, close, volume`
- **Freshness check:** `MAX(date)` must be ≤ 7 calendar days before `trade_date`; otherwise
  the run is blocked with `BLOCKED_STALE_DATA`
- **Used for:** TradingCalendar construction (0050 dates as proxy), market regime features,
  MA20 slope/trend/gap calculations
- **NOT production data:** This is the local research SQLite, not production Neon PostgreSQL

### ForwardSignal (Neon PostgreSQL — production read-only)

- **Location:** production Neon, table `forward_signals`
- **Filter:** `research_version = 'v2_research_v2'`, `signal_date = trade_date`
- **Used for:** `v2_entry_label` (the V2 ForwardSignal recommendation for each stock)
- **Immutability:** ForwardSignals are never modified by this pipeline. They are inputs only.
- **Frozen signals:** Signals with `signal_date < 2026-11-05` are frozen and immutable per
  the production ForwardSignal immutability guarantee.

---

## Decision Record Anatomy

```
hybrid_forward_decision:
  stock_id            ← from ForwardSignal
  trade_date          ← the date signals were generated
  rule_version        ← "hybrid_v1" (constant, frozen)
  research_version    ← "v2_research_v2"
  v2_entry_label      ← from ForwardSignal (input)
  hybrid_action       ← output of HybridEntryStrategy.classify()
  rule_reason         ← which P1/P2/P3/P4 rule triggered
  rule_priority       ← 1–4
  market_regime       ← derived from DailyPrice
  ma20_slope_pct      ← derived from DailyPrice
  ma20_trend          ← derived from DailyPrice
  ma20_gap_pct        ← derived from DailyPrice
  feature_cutoff_date ← last date used for feature computation
  input_data_as_of    ← date of latest DailyPrice available at compute time
  input_data_hash     ← sha256(inputs)[:16] — detects if inputs changed on re-run
  decision_hash       ← sha256(outputs)[:16] — detects if outputs changed on re-run
  capture_classification ← PROSPECTIVE / LATE_CAPTURE / RETROSPECTIVE_RECONSTRUCTION / INVALID_DATA
  captured_at         ← UTC timestamp when inserted
  run_id              ← UUID linking to run_log row
```

---

## Capture Classification Logic

```python
def classify_capture(trade_date, captured_at, input_data_as_of, trading_days_since_trade):
    if trade_date < RULE_FREEZE_DATE:          # 2026-11-05
        return RETROSPECTIVE_RECONSTRUCTION    # pre-freeze: in-sample only
    if input_data_as_of < trade_date:
        return INVALID_DATA                    # used future data as inputs
    if trading_days_since_trade <= 1:
        return PROSPECTIVE                     # captured on time — valid OOS
    return LATE_CAPTURE                        # captured late — timing bias
```

`trading_days_since_trade` = `TradingCalendar.count_trading_days(trade_date, captured_at.date())`.

---

## Outcome Record Anatomy

```
hybrid_forward_outcome:
  decision_id          ← FK to hybrid_forward_decision.id
  stock_id             ← denormalised copy (for query convenience)
  trade_date           ← denormalised copy
  rule_version         ← denormalised copy
  horizon              ← "5d", "10d", or "20d"
  maturity_date        ← TradingCalendar.add_trading_days(entry_date, n)
  maturity_trading_days ← n (5, 10, or 20)
  v1_net_return        ← net return if entered using V1 logic
  v2_net_return        ← net return if entered using V2 logic
  hybrid_net_return    ← net return under hybrid decision
  hybrid_vs_v1_delta   ← hybrid_net_return - v1_net_return
  hybrid_vs_v2_delta   ← hybrid_net_return - v2_net_return
  data_source_version  ← which DailyPrice version used for outcome
  calculation_version  ← "1.0" (bumped if calculation logic changes)
  outcome_status       ← MATURED / PENDING / CONFLICT / INVALID
  calculated_at        ← UTC timestamp
```

Outcomes are immutable once `outcome_status = MATURED`. A re-run with the same
`(decision_id, horizon, calculation_version)` and same values skips silently (idempotent).
A different value raises `ConflictError`.

---

## Immutability Guarantees

| Table | Insert | Update | Delete |
|-------|--------|--------|--------|
| `hybrid_forward_decision` | Append-only via `insert_decision()` | Never | Never |
| `hybrid_forward_outcome` | Append-only via `insert_outcome()` | Never | Never |
| `hybrid_forward_run_log` | Upsert on `run_id` (status/finished_at updated for same run) | Only within same run | Never |

The access layer (`hybrid_forward_db.py`) does not expose any update or delete function for
decision or outcome tables. Direct SQL `UPDATE` on these tables is not issued anywhere in the codebase.

---

## OOS Validity Hierarchy

For strategy validation purposes, only use rows where:

```sql
capture_classification = 'PROSPECTIVE'
AND outcome_status = 'MATURED'
```

All other classification values should be excluded from performance claims. The dashboard
enforces this by calling `get_matured_performance()` which filters to `PROSPECTIVE` by default.

---

## Known Limitations

1. **TradingCalendar is a proxy.** Built from 0050 DailyPrice dates, not an authoritative
   exchange calendar. Holidays not in 0050's history (e.g., unexpected closures) may be missing.

2. **DailyPrice open prices are approximated.** `open ≈ previous_close` (DailyPrice has no
   independent open column). This affects outcome calculation accuracy by a small amount.

3. **ForwardSignal dependency.** If production ForwardSignal generation is delayed, the shadow
   runner will return `BLOCKED_MISSING_SIGNALS` and that date's prospective record is lost.
   There is no retrospective recovery for PROSPECTIVE classification.

4. **No bootstrap CI yet.** `get_matured_performance()` returns mean returns only.
   Bootstrap CI and paired t-test are planned for Phase 2 (after n ≥ 200 matured records).
