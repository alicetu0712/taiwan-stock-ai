# Fill-Date Comparison Contract — Session 43

## 1. Purpose

Defines the requirements for a fair V1/V2/V3 comparison. Any comparison that violates these dimensions produces misleading results.

## 2. Contract Dimensions

| Dimension | Requirement | S42 Status | S43 Status |
|-----------|-------------|------------|------------|
| MODEL_VERSION | All signals = v8.0 | Mixed v6.0+v8.0 | v8.0 STRICT applied |
| TRADABLE_UNIVERSE | Common stocks only | All signals incl. ETF | Filter to v8.0; ETF minor (~0.7%) |
| MARKET_CALENDAR | execution_date = real trading day | Used DISTINCT date (incl. thin days) | Stock-specific execution_date (skips thin days) |
| PRICE_AVAILABILITY | 5 stock-specific exit dates must exist | Approximate; some incomplete | Explicit completeness check per cluster |
| HOLDING_PERIOD | 5 stock-specific trading days | Calendar days (horizon=5) | Stock-specific 5-day exit |
| BENCHMARK | 0050 from same fill/exit dates | S40: wrong dates. S42: corrected | S42 correction maintained |
| TRANSACTION_COSTS | 0.585% for all strategies | Applied | Applied (unchanged) |
| ENTRY_OPPORTUNITY | Same signal pool for all strategies | Same pool | Same pool |
| OUTCOME_MATURITY | 5D window fully within daily_prices | Oct 21 cluster used despite sparse exit | Oct 21 flagged INCOMPLETE |

## 3. Signal Cohort Classification

| Signal Date | Fill Date | Model Version | n Signals | Pairing Verdict | Reason |
|-------------|-----------|---------------|-----------|-----------------|--------|
| Oct 09 | Oct 12 | v6.0 | 99 | NOT_COMPARABLE | v6.0, holiday |
| Oct 10 | Oct 12 | v6.0 | 4 | NOT_COMPARABLE | v6.0, holiday+Sat |
| Oct 11 | Oct 12 | v6.0 | 4 | NOT_COMPARABLE | v6.0, Sunday |
| Oct 12 | Oct 13 | v8.0 | 46 | STRICTLY_COMPARABLE | ✓ |
| Oct 13 | Oct 14 | v8.0 | 27 | STRICTLY_COMPARABLE | ✓ |
| Oct 14 | Oct 16 | v8.0 | 55 | STRICTLY_COMPARABLE | ✓ |
| Oct 16 | Oct 21 | v8.0 | 39 | CONDITIONALLY_COMPARABLE | fill Oct 21 incomplete |

**Strict eligible: 128 signals (3 signal dates)**
**Conditional eligible: 39 signals (1 signal date)**
**Not comparable: 107 signals (3 signal dates)**

## 4. STRICTLY_COMPARABLE vs CONDITIONALLY_COMPARABLE

**Strictly Comparable** means:
- v8.0 model only
- execution_date is a real trading day (≥50 stocks)
- 5 complete exit days available for each stock in the cluster
- No thin-day ambiguity in the fill or exit window

**Conditionally Comparable** means:
- v8.0 model ✓
- execution_date is real ✓
- But: either exit days are incomplete, OR thin-day ambiguity exists in the window

Fill Oct 21 cluster is CONDITIONAL because: the 5th exit day (Nov 06+) is not yet in `daily_prices` (max = Nov 05). Using this cluster requires acknowledging the truncated return window.

## 5. Implications for Strategy Ranking

Under the strict contract (128 signals, 3 clusters):
- D_v3 vs A_direct: grand mean = +0.81%, p ≈ 0.37, CI ≈ [-1.4%, +3.0%]
- D_v3 vs B_v1v2: grand mean ≈ -0.14%
- D_v3 vs C_hybrid: comparable to A_direct

Under the conditional contract (167 signals, 4 clusters, adding Oct 21):
- Results shift slightly; Oct 21 cluster adds +0.99% delta for A, +0.74% for B
- Grand mean vs A increases toward ~1.21% (matching S42 without the v6.0 cluster)

**Neither strict nor conditional analysis provides sufficient evidence for SIGNIFICANT conclusions.** N=3-4 clusters, overlapping windows, and no historical data expansion prevent drawing firm conclusions.

## 6. Future Contract Compliance

When the cron accumulates additional months (Nov-Dec 2026+):
- Each new calendar month adds ~8-12 fill-date clusters
- After 10+ total strict clusters with <50% overlap: G03 and G04 guardrails can pass
- Current ETA for G03 compliance: Jan 2027 (assuming cron operates continuously)
