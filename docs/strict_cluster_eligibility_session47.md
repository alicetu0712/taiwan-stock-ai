# Strict Cluster Eligibility — Session 47

**Date:** 2026-11-09  
**Session:** S47 — PART D (P3)  
**Verdict:** STRICT_ELIGIBILITY_UNCHANGED

---

## Signal → Execution → Fill → Outcome Window Mapping

| Signal Date | Execution (Fill) Date | 5th Calendar TD | TSMC Proxy Count | Eligibility |
|---|---|---|---|---|
| Oct 12 | Oct 13 | Oct 20 | 7 | STRICT ✓ |
| Oct 13 | Oct 14 | Oct 21 | 6 | STRICT ✓ |
| Oct 14 | Oct 16 | Oct 27 | 5 | STRICT ✓ |
| Oct 16 | Oct 21 | Oct 30 | 4 | DATA_INCOMPLETE |
| Oct 21 | Oct 22 | Nov 02 | 3 | DATA_INCOMPLETE |
| Oct 22 | Oct 28 | Nov 04 | 2 | DATA_INCOMPLETE |
| Oct 28 | NULL | — | 0 | EXCLUDED (NULL exec_date) |

**Note:** The "5th Calendar TD" (actual TaiwanTradingCalendar 5th TD) differs from the TSMC proxy-based exit date. See PART F (20D Reconciliation doc) for the full off-by-one analysis. The canonical baseline uses TSMC proxy count ≥5 as the strict criterion.

---

## Eligibility Checklist Per Cluster

### Oct 13 Fill (Signal: Oct 12) — STRICT_ELIGIBLE

| Check | Status |
|---|---|
| Strategy version v8.0 | ✓ |
| Frozen parameters (v8.0 rules) | ✓ |
| Valid signal provenance | ✓ |
| Valid execution provenance | ✓ locked_at < execution_date |
| Valid fill price (NEXT_OPEN) | ✓ |
| Verified trading calendar | ✓ Oct 13 is trading day |
| Verified security universe | ✓ 656 stocks in DB |
| Complete 5D outcome (proxy ≥5) | ✓ 7 proxy dates |
| Complete benchmark | ✓ 0050 present |
| Transaction costs applied | ✓ FEES_PCT=0.00585 |
| Matched comparison opportunity | ✓ V3 vs A_direct |
| No look-ahead bias | ✓ locked_at < exec_date |
| No duplicate inflation | ✓ UniqueConstraint |

**Verdict: STRICT_ELIGIBLE** (46 matched signals)

### Oct 14 Fill (Signal: Oct 13) — STRICT_ELIGIBLE

Same checklist as Oct 13 fill. 27 matched signals. Proxy count = 6. **Verdict: STRICT_ELIGIBLE**

### Oct 16 Fill (Signal: Oct 14) — STRICT_ELIGIBLE

Same checklist. 55 matched signals. Proxy count = 5 (exactly meets threshold). **Verdict: STRICT_ELIGIBLE**

### Oct 21 Fill (Signal: Oct 16) — DATA_INCOMPLETE

| Check | Status |
|---|---|
| Strategy version v8.0 | ✓ |
| Valid provenance | ✓ |
| Valid fill price | ✓ |
| Verified trading calendar | ✓ Oct 21 is trading day |
| Complete 5D outcome (proxy ≥5) | ✗ **Only 4 proxy dates** |
| Required missing dates | Oct 29/30/Nov 02/03 (need ≥1 with TSMC) |

**Verdict: DATA_INCOMPLETE** — upgrade path: backfill ≥1 of {Oct 29, Oct 30, Nov 02, Nov 03}

### Oct 22 Fill (Signal: Oct 21) — DATA_INCOMPLETE

Proxy = 3. Needs ≥2 of {Oct 29, Oct 30, Nov 02, Nov 03}. **Verdict: DATA_INCOMPLETE**

### Oct 28 Fill (Signal: Oct 22) — DATA_INCOMPLETE

Proxy = 2. Needs ≥3 of {Oct 29, Oct 30, Nov 02, Nov 03}. **Verdict: DATA_INCOMPLETE**

---

## Why Incomplete Clusters Cannot Be Promoted

The `_count_exit_days` proxy checks TSMC presence in SQLite after the fill date. Currently:
- Oct 29/30/Nov 02/03: only 0050 in SQLite (TSMC absent)
- Recovery of these dates is BLOCKED (see `research_price_recovery_session47.md`)

Even if Neon read access were authorized:
- Oct 29/30/Nov 02/03 from Neon would provide TSMC prices
- This would promote Oct 21/22/28 fills to STRICT (proxy count ≥5)
- But the proxy-based exit dates (Oct 22nd for Oct 21 fill, etc.) may still not reflect actual calendar 5th TDs

**The comparison would use pre-computed frozen deltas from S43, NOT dynamically recomputed exit prices.** New clusters added would need their deltas computed fresh, requiring a separate authorized computation.

---

## Permanently Ineligible Clusters

No clusters are permanently ineligible. All 3 incomplete clusters are DATA_INCOMPLETE — their data gap can be resolved by pipeline restoration. No version mismatch or provenance failure.

---

## Verdict Summary

| Cluster | Verdict | Action Needed |
|---|---|---|
| Oct 13 fill | STRICT_ELIGIBLE | None |
| Oct 14 fill | STRICT_ELIGIBLE | None |
| Oct 16 fill | STRICT_ELIGIBLE | None |
| Oct 21 fill | DATA_INCOMPLETE | Backfill ≥1 of Oct 29/30/Nov 02/03 |
| Oct 22 fill | DATA_INCOMPLETE | Backfill ≥2 of Oct 29/30/Nov 02/03 |
| Oct 28 fill | DATA_INCOMPLETE | Backfill ≥3 of Oct 29/30/Nov 02/03 |

**Overall: STRICT_ELIGIBILITY_UNCHANGED** (3 strict, 3 incomplete — same as S44/S45/S46)
