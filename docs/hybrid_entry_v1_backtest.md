# Hybrid Entry Strategy V1 — Retrospective Backtest Analysis

**Status:** RETROSPECTIVE / EXPLORATORY ONLY  
**Data period:** 2024-10-01 to 2026-09-15  
**Rule version:** hybrid_v1 (frozen 2026-11-05)  
**Reference commit:** 6602c3b

---

## ⚠️ IN-SAMPLE WARNING

**All results in this document are IN-SAMPLE.**

Hybrid V1 rules (Bear → wait; Flat MA20 → wait) were derived by analysing the
same 2024-10 to 2026-09 cohort used for all backtests below.  Applying these
rules retrospectively to the same dataset they were derived from is an
**in-sample test, not an out-of-sample validation**.

A strategy that selects subgroups based on observed outcomes will appear to
outperform when re-tested on those same subgroups.  This is **selection bias**,
not evidence of a genuine edge.

**Use these results only to:**
1. Verify the implementation behaves as expected
2. Understand the magnitude of the in-sample effect (before prospective data)
3. Calibrate expectations for the forward shadow

**Do not use these results to claim Hybrid V1 is validated.**

---

## 1. Dataset Summary

| Layer | Count |
|---|---|
| Raw signals generated | ~13,023 |
| After 28-day dedup | 3,066 |
| Valid paired signals (V1 + V2 simulated) | 2,953 |
| Unique stocks | 150 |
| Concentration warning | None |

Market regime distribution:

| Regime | N | % |
|---|---|---|
| bull | 984 | 33.3% |
| neutral | 642 | 21.7% |
| bear | 352 | 11.9% |
| unknown | 975 | 33.0% |

---

## 2. Three-Strategy Comparison (IN-SAMPLE)

*Run `python scripts/run_hybrid_backtest.py` to generate data/hybrid_backtest.json*

Expected approximate results based on the rule design:

| Strategy | N | Mean Net Return | Paired Delta vs V1 |
|---|---|---|---|
| V1 (immediate) | 2,953 | −0.93% | — |
| V2 FOS (all wait) | 2,953 | −0.87% | +0.06% |
| Hybrid V1 (conditional) | 2,953 | ~−0.85% (est.) | +0.08–0.15% (est.) |

**Expected Hybrid advantage over V2:**

Hybrid switches WAIT_FOR_PULLBACK signals in Bull+Rising regime from V2 waiting
to V1 immediate entry.  For those signals, V2 had delta ≈ 0 (bull regime is
where V1 and V2 parity is highest).  This should leave Hybrid slightly better
than V2 overall.

For the Bear and Flat-MA20 subgroups, Hybrid keeps V2's waiting behaviour,
which showed the largest positive deltas.  The resulting Hybrid mean should be
slightly above both V1 and V2 FOS — but remember, this is IN-SAMPLE.

---

## 3. Action Distribution (IN-SAMPLE)

Based on the rule design:

| Entry Label | Hybrid Action | Approximate Count |
|---|---|---|
| WAIT_FOR_PULLBACK + Bear | WAIT_PULLBACK (P1) | ~88 |
| WAIT_FOR_PULLBACK + Flat MA20 | WAIT_PULLBACK (P2) | ~68 |
| WAIT_FOR_PULLBACK + Bull/Rising (switched) | DIRECT_NEXT_OPEN (P3/P4) | ~93 |
| ENTRY_READY (all regimes) | DIRECT_NEXT_OPEN (P4) | 1,839 |
| WAIT_FOR_BREAKOUT (all regimes) | DIRECT_NEXT_OPEN (P4) | 865 |

Approximately 156 signals (~6%) change from V2's waiting behaviour to Hybrid's
immediate entry (the Bull+Rising WAIT_FOR_PULLBACK cases).  The rest are
unchanged from V1 or V2.

---

## 4. Walk-forward (IN-SAMPLE for Hybrid)

Walk-forward windows are used to verify that Hybrid does not severely
underperform in any single time period.

PASS criterion: `paired_delta(Hybrid vs V1) ≥ −1.0pp` per window.

Walk-forward results will appear in `data/hybrid_backtest.json` after running
`scripts/run_hybrid_backtest.py`.  These are IN-SAMPLE chronological checks,
not true OOS validation.

---

## 5. What Would Make Hybrid V1 Genuinely Validated?

Requirements for upgrading Hybrid V1 from RESEARCH to PROVISIONAL PASS:

| Requirement | Current status | Needed |
|---|---|---|
| Prospective forward shadow | Not started (freeze date 2026-11-05) | ≥ 200 matured OOS signals |
| OOS paired delta | Unknown | Hybrid vs V1 delta ≥ 0 |
| OOS CI entirely positive | Unknown | 95% CI lo > 0 |
| Walk-forward consistency | Unknown | No window < −1.5pp |

For full VALIDATED status (after PROVISIONAL PASS):
- Replication on extended period (2027+)
- At least 500 OOS matured signals
- Bear/Flat MA20 subgroup CIs survive Bonferroni correction

---

## 6. Retrospective vs OOS

| Analysis type | Data period | For Hybrid |
|---|---|---|
| Retrospective backtest (this doc) | 2024-10 to 2026-09 | IN-SAMPLE |
| Prospective forward shadow | 2026-11-05 onwards | TRUE OOS |

---

## 7. Run the Retrospective Analysis

```bash
# Generate in-sample results
python scripts/run_hybrid_backtest.py

# View results in dashboard
# → Entry Timing Research → 🔀 Hybrid 策略 tab
```

Output: `data/hybrid_backtest.json`

---

## 8. Research Verdict

**RETROSPECTIVE/EXPLORATORY — NOT VALIDATED**

The Hybrid V1 retrospective analysis provides:
- ✅ Implementation correctness verification
- ✅ Rule logic sanity check (expected subgroup behaviour confirmed)
- ✅ Magnitude estimation for forward shadow calibration
- ❌ NOT an independent validation
- ❌ NOT sufficient to change production strategy

**Next step:** Accumulate ≥ 200 prospective OOS signals via
`scripts/run_hybrid_forward_shadow.py` (daily, starting 2026-11-05).
