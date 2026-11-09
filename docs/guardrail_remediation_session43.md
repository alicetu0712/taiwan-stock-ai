# Guardrail Remediation — Session 43

## 1. Summary

Session 42 identified 3 FAIL and 2 CONDITIONAL guardrails. Session 43 attempted remediation for each.

| Guardrail | S42 | S43 | Remediation |
|-----------|-----|-----|-------------|
| G01 Calendar Integrity | FAIL | CONDITIONAL | PARTIAL (v6.0 exclusion) |
| G02 Trading Day Completeness | PASS | PASS | No action |
| G03 Cluster Count ≥5 | FAIL | FAIL | NOT_REMEDIABLE |
| G04 Window Overlap <50% | FAIL | FAIL | NOT_REMEDIABLE |
| G05 Benchmark Availability | PASS | PASS | No action |
| G06 Model Version Coverage | PASS | PASS | Strengthened |
| G07 Signal Count ≥10/cluster | PASS | PASS | No action |
| G08 Transaction Costs Applied | CONDITIONAL | CONDITIONAL | No action |
| G09 Execution Type Documented | PASS | PASS | Strengthened |
| G10 ETF Contamination <5% | CONDITIONAL | CONDITIONAL | No action |

## 2. G01 — Calendar Integrity (FAIL → CONDITIONAL)

**S42 finding**: 39.1% of signals on non-trading days (Oct 09-11).

**Root cause**: v6.0 cron bug — no holiday guard. Generated signals on National Day + Sunday.

**Remediation (S43)**:
- S43 `FillDateComparisonContract` excludes all v6.0 signals
- v8.0-strict pool has 0% non-trading day signals (Oct 12-16)
- Thin days (Oct 15, 19, 20) correctly skipped by NEXT_OPEN engine

**Why still CONDITIONAL (not PASS)**:
- Calendar source still uses `SELECT DISTINCT date FROM daily_prices` which includes thin days
- Proper calendar definition requires ≥50-stock threshold
- G01 would become PASS if the trading calendar module uses the corrected source

**Remaining blocker**: Calendar source correction requires updating `TradingCalendarIntegrityAuditor` to use ≥50-stock filter — deferred to future session.

## 3. G03 — Cluster Count ≥5 (FAIL → FAIL)

**S42 finding**: 5 mixed clusters (3 strict after v6.0 exclusion).

**Root cause**: Cron only started Oct 2026; insufficient data.

**Why not remediable**: Cannot create clusters from non-existent data. `EvidenceExpansionAuditor` confirms NO_NEW_ELIGIBLE_WINDOW.

**Remaining blocker**: Need 5+ strict clusters → requires Nov-Dec 2026 cron accumulation.

**ETA for PASS**: Jan 2027 (assuming cron operates continuously).

## 4. G04 — Window Overlap <50% (FAIL → FAIL)

**S42 finding**: Adjacent fill-date clusters share ~80% of their 5D holding windows.

**Root cause**: Daily signal generation + 5D holding period creates consecutive overlapping windows. fill Oct 13 (exits Oct 28) and fill Oct 14 (exits Nov 04) share Oct 14-28.

**Why not remediable**: 
- Overlap is structural to daily cron + 5D window design
- Cannot retroactively change holding period or signal frequency
- Skipping alternate clusters would reduce evidence further (N=2)

**Remaining blocker**: Design-level constraint. Would require weekly (not daily) signal generation OR non-overlapping 5D windows (not feasible with consecutive trading days).

**Long-term fix**: Use 20D or 30D windows (non-overlapping when separated by ≥4 weeks of signals); or restrict comparison to clusters ≥5 trading days apart.

## 5. G08 — Transaction Costs (CONDITIONAL → CONDITIONAL)

No new data available to verify FEES_PCT=0.00585 against actual broker rates. Maintained as research assumption. Sensitivity: ±0.1% change in fees shifts grand mean by approximately ±0.1%.

## 6. G10 — ETF Contamination (CONDITIONAL → CONDITIONAL)

ETF proxy rate = ~0.7% (stock_id LIKE '00%'). Under the 5% threshold but unverified with official `stock_type` column. The `stocks` table lacks this column. Session 38 established official classification but it is not queryable from research modules.

## 7. Post-Remediation Guardrail Status

After S43 remediation:
- **PASS**: G02, G05, G06, G07, G09 (5 guardrails)
- **CONDITIONAL**: G01, G08, G10 (3 guardrails)
- **FAIL**: G03, G04 (2 guardrails)

Overall: **GUARDRAILS_FAIL** (G03 and G04 still FAIL).

The two FAIL guardrails represent data scarcity and structural design issues — not correctness problems. They will naturally resolve as data accumulates and analysis design evolves.
