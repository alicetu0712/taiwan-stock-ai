# 20D Research Readiness — Session 43

## 1. Summary

As of 2026-11-09, **no fill-date cluster has sufficient exit data for a 20D return window**.

| Metric | Value |
|--------|-------|
| Evaluation date | 2026-11-09 |
| daily_prices max date (TSMC) | 2026-11-05 |
| Fill clusters with 20 exit days | 0 / 4 |
| Overall verdict | NOT_READY_FOR_20D |

## 2. Per Fill-Date Maturity

| Fill Date | n Signals | TSMC Exit Days Available | Required | % Complete | Status | ETA |
|-----------|-----------|--------------------------|----------|------------|--------|-----|
| Oct 13 | 46 | ~15 | 20 | 75% | PARTIAL | ~Nov 25 |
| Oct 14 | 27 | ~14 | 20 | 70% | PARTIAL | ~Nov 26 |
| Oct 16 | 55 | ~13 | 20 | 65% | IMMATURE | ~Nov 28 |
| Oct 21 | 39 | ~10 | 20 | 50% | IMMATURE | ~Dec 04 |

(TSMC = 2330, used as representative stock)

## 3. Why 20D Windows Are Not Yet Available

Taiwan Stock Exchange operates roughly 20 trading days per month. For fill Oct 13:
- Need: 20 trading days after Oct 13
- Available: trading days Oct 14 → Nov 05 = approximately 15 days
- Gap: ~5 more trading days needed (available ~Nov 25)

The data gap from Oct 23-27 (zero common stock data) reduces the count of available exit days.

## 4. 20D vs 5D Comparison

| Dimension | 5D Window | 20D Window |
|-----------|-----------|------------|
| Available clusters | 3 (strict) | 0 |
| Window overlap | ~80% (adjacent) | Potentially non-overlapping |
| Evidence quality | Weak (N=3) | N/A — not ready |
| Statistical independence | Violated | Would be better |

The 20D window has a theoretical advantage: clusters spaced ≥4 weeks apart would not overlap. But this benefit is inaccessible until sufficient price data accumulates.

## 5. 20D Activation Prerequisites

For a valid 20D analysis:
1. At least 3 fill-date clusters with 20 complete exit days each
2. All clusters from v8.0 signals only (already satisfied for Oct 12-16 signal dates)
3. G03 guardrail: ≥5 clusters → requires Nov-Dec 2026 signal accumulation
4. G04 guardrail: may naturally pass if clusters spaced ≥4 weeks apart

## 6. Blocking Issues

1. `daily_prices` max date (Nov 05) is insufficient for any 20D window; earliest fill date is Oct 13, needs 20 TDs (est. ~Nov 25)
2. Data gap Oct 23-27 reduces available exit days for all clusters
3. No Nov-Dec 2026 signal clusters yet available for comparison

## 7. Recommended Next Check

Re-evaluate 20D readiness when:
- `daily_prices` max date reaches 2026-11-28 (for fill Oct 13 20D window)
- Nov 2026 cron signals have accumulated (for new fill clusters)

Expected timeline: late Nov 2026 for first 20D windows; Dec 2026 for meaningful 20D comparison.
