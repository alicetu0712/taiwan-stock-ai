# Comparable Evidence Expansion — Session 43

## 1. Summary

Session 43 conducted a systematic search for additional historical comparison windows. Result: **NO_NEW_ELIGIBLE_WINDOW**.

## 2. Artifacts Examined

| Artifact | Type | Signal Date Range | n Signals | Eligible? |
|----------|------|-------------------|-----------|-----------|
| data/platform.db | Production SQLite | Oct 2026 | 344 buy/SB | CONDITIONAL |
| data/stock_research.db | Research SQLite | N/A | 0 | No (empty) |

## 3. Candidate Windows

### W001 — Oct 2026 (Existing)

- **Status**: CONDITIONAL
- **Source**: `forward_signals` in production DB
- **Eligible signals** (v8.0 only): 128 strict, 39 conditional
- **Complete fill clusters**: 3 (fill Oct 13, 14, 16)
- **Issues**: v6.0 contamination (107 excluded); fill Oct 21 incomplete; data gap Oct 23-27
- **Action**: Already analyzed in S42-S43; no new evidence from this window

### W002 — Pre-Oct 2026 Hypothetical

- **Status**: INELIGIBLE
- **Source**: None available
- **Why ineligible**:
  - No `forward_signals` before Oct 2026 in any database
  - `stock_research.db` is empty
  - Retrospective signal reconstruction would require historical price data at time of signal — this is look-ahead bias risk (parameters were tuned on historical data)
- **Conclusion**: Any "backtest" using V3 logic on pre-Oct 2026 data would not be comparable to prospective forward signals

### W003 — Nov-Dec 2026 Future

- **Status**: INELIGIBLE
- **Source**: Ongoing cron production (`forward_signals`)
- **Why ineligible**:
  - Signals exist from Nov 04 backfill, but outcome windows not yet complete
  - `daily_prices` max = 2026-11-05; most 5D windows not computable
  - No signals in Nov yet with 5 complete exit days
- **ETA**: Nov 2026 for first complete 5D windows; Dec 2026 for meaningful cluster count

## 4. Why No Historical Archives

The V3 model (and V1/V2) uses `forward_signals` written by a production cron job that started running in Oct 2026. Before that:

- No cron was writing forward signals
- `stock_research.db` was used for backtest research but contains no prospective signal records
- Retrospective reconstruction would constitute look-ahead bias (see Section 5)

## 5. Look-Ahead Bias Risk

If we were to reconstruct "signals" for periods before Oct 2026 using V3 logic:

1. V3 parameters (thresholds, weights) were optimized on historical data up to some cutoff
2. Applying those parameters to historical data produces in-sample results, not out-of-sample
3. This would inflate apparent performance vs any baseline

**The only valid evidence is prospective signals generated before the outcome was known.** This restricts analysis to Oct 2026+.

## 6. Evidence Accumulation Timeline

| Timeline | Expected New Evidence |
|----------|-----------------------|
| Nov 2026 | First 5D windows complete for Nov signals; ~8-12 new fill clusters |
| Dec 2026 | First 20D windows complete for Oct signals; Nov signals mature |
| Jan 2027 | Enough clusters (10+) for G03 to pass; first proper WF split possible |
| Q2 2027 | Sufficient data for bootstrap CI validation |

## 7. Conclusion

No additional windows can be added to the current comparison. The only path to strengthening evidence is waiting for cron to accumulate prospective signals through Nov-Dec 2026. Any attempt to synthesize historical evidence would compromise the statistical integrity of the comparison.
