"""
effectiveness_analyzer.py — Entry Timing V2 Strategy Effectiveness Analysis

RESEARCH ONLY — NOT A LIVE TRADING SYSTEM.

Pure-function module: accepts pre-generated EnrichedSignal lists, returns
structured analysis dicts.  No database dependency; all I/O handled by callers.

Analysis layers:
  A) Data Integrity Audit   — signal counts, dedup, maturity, concentration
  A2) MA20 Audit            — stop-derived MA20 vs actual analyzer MA20
  B)  Group Analysis        — by entry_label, trend, MA gap, market regime
  C)  Walk-forward          — time-ordered test windows with embargo
  D)  Sensitivity Matrix    — variant parameters compared to base
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional


# ── Constants ─────────────────────────────────────────────────────────────────

SLOPE_RISING_THRESHOLD = 0.3    # MA slope % threshold to call "rising"
SLOPE_FALLING_THRESHOLD = -0.3
MA20_SLOPE_BARS = 10
MIN_GROUP_SAMPLE = 10            # minimum n for bootstrap CI
INSUFFICIENT_SAMPLE_N = 30       # minimum n for reliable conclusions
MULTIPLE_TEST_N = 20             # approximate comparison count for Bonferroni note
STOP_BUFFER = 0.03               # mirrors execution_simulator.STOP_BUFFER


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class EnrichedSignal:
    """
    One research signal with all context needed for effectiveness analysis.

    Simulation fields (v1_ret, v2_ret, etc.) are set by the caller after
    running EntryTimingExecutionSimulator.  v2_ret = 0.0 for no-fill (SA-7).
    """

    # Core signal
    signal_date: date
    stock_id: str
    entry_label: str
    entry_price: float
    stop_price: float
    target_price: float

    # MA state from EntryTimingAnalyzer
    ma20: float
    ma20_gap_pct: float
    prior_20d_high: Optional[float]

    # Trend state (computed from pre-signal price history)
    ma20_slope_pct: float = 0.0
    ma20_trend: str = "flat"           # "rising" / "flat" / "falling"
    ma60: Optional[float] = None
    ma60_slope_pct: Optional[float] = None
    ma60_trend: Optional[str] = None
    price_vs_ma20: str = "above"       # "above" / "below"
    price_vs_ma60: Optional[str] = None
    ma20_gap_bucket: str = "0-2%"      # "<0%" / "0-2%" / "2-5%" / ">5%"

    # Market regime on signal_date (derived from 0050)
    market_regime: str = "unknown"     # "bull" / "neutral" / "bear" / "unknown"

    # Planned entry reference price
    planned_entry_price: float = 0.0

    # Simulation results — base parameters
    v1_ret: Optional[float] = None
    v2_ret: Optional[float] = None     # actual fill return or 0.0 (SA-7)
    v2_filled: bool = False
    v2_no_fill_reason: Optional[str] = None
    v1_stop_hit: bool = False
    v1_target_hit: bool = False
    v2_stop_hit: bool = False
    v2_target_hit: bool = False
    v1_mae: Optional[float] = None
    v1_mfe: Optional[float] = None
    v2_mae: Optional[float] = None
    v2_mfe: Optional[float] = None
    v2_waiting_days: int = 0
    paired_delta: Optional[float] = None

    # Data quality flags
    is_matured: bool = True      # True if ≥22 forward bars existed at simulation time
    is_raw: bool = True
    is_dedup_kept: bool = True

    # MA20 audit
    ma20_derived: float = 0.0    # stop_price / (1 - STOP_BUFFER) — for audit only


# ── Utility functions ─────────────────────────────────────────────────────────

def compute_ma_slope(closes: List[float], n_bars: int = MA20_SLOPE_BARS) -> float:
    """
    Percentage change in MA20 over the last n_bars bars.

    Uses (MA20_now - MA20_n_bars_ago) / MA20_n_bars_ago × 100.
    Returns 0.0 when insufficient data to avoid masking missing-data bugs.
    """
    if len(closes) < n_bars + 1:
        return 0.0
    ma_now = sum(closes[-20:]) / min(20, len(closes))
    ma_prev_start = max(0, len(closes) - 20 - n_bars)
    ma_prev_end = max(0, len(closes) - n_bars)
    prev_window = closes[ma_prev_start:ma_prev_end]
    if not prev_window:
        return 0.0
    ma_prev = sum(prev_window) / len(prev_window)
    if ma_prev == 0:
        return 0.0
    return round((ma_now - ma_prev) / ma_prev * 100.0, 4)


def classify_ma_slope(slope_pct: float) -> str:
    if slope_pct > SLOPE_RISING_THRESHOLD:
        return "rising"
    if slope_pct < SLOPE_FALLING_THRESHOLD:
        return "falling"
    return "flat"


def classify_ma20_gap_bucket(gap_pct: float) -> str:
    if gap_pct < 0:
        return "<0%"
    if gap_pct < 2.0:
        return "0-2%"
    if gap_pct < 5.0:
        return "2-5%"
    return ">5%"


def _mean(lst: List[float]) -> Optional[float]:
    return round(sum(lst) / len(lst), 4) if lst else None


def _median(lst: List[float]) -> Optional[float]:
    if not lst:
        return None
    s = sorted(lst)
    n = len(s)
    mid = n // 2
    return round((s[mid - 1] + s[mid]) / 2, 4) if n % 2 == 0 else round(s[mid], 4)


def _bootstrap_ci(
    rets: List[float],
    n_boot: int = 1000,
    seed: int = 42,
) -> Optional[Dict]:
    """
    Bootstrap 95% CI for the mean.  Returns None when n < MIN_GROUP_SAMPLE to
    avoid misleadingly tight CIs on tiny samples.
    """
    if len(rets) < MIN_GROUP_SAMPLE:
        return None
    rng = random.Random(seed)
    n = len(rets)
    boot_means = []
    for _ in range(n_boot):
        sample = [rets[rng.randint(0, n - 1)] for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    lo = boot_means[int(0.025 * n_boot)]
    hi = boot_means[int(0.975 * n_boot)]
    return {"lo": round(lo, 4), "hi": round(hi, 4)}


def _stat_note(n: int) -> str:
    if n < MIN_GROUP_SAMPLE:
        return f"INSUFFICIENT SAMPLE (n={n}, CI omitted)"
    if n < INSUFFICIENT_SAMPLE_N:
        return f"LOW SAMPLE (n={n}, results indicative only)"
    return ""


# ── Core analysis: group statistics ──────────────────────────────────────────

def compute_group_stats(signals: List[EnrichedSignal], label: str = "") -> Dict:
    """
    Aggregate performance metrics for a filtered set of signals.

    Only uses signals where both v1_ret and v2_ret are populated (valid pairs).
    Callers must have already applied SA-7 (v2_ret = 0.0 for no-fill).
    """
    valid = [
        s for s in signals
        if s.v1_ret is not None and s.v2_ret is not None
    ]
    n = len(valid)

    if n == 0:
        return {
            "label": label, "n": 0, "n_filled": 0, "fill_rate_pct": None,
            "v1_mean": None, "v1_median": None,
            "v2_mean": None, "v2_median": None,
            "paired_delta_mean": None, "paired_delta_ci95": None,
            "v1_win_rate": None, "v2_win_rate": None,
            "v1_mae_mean": None, "v1_mfe_mean": None,
            "v2_mae_mean": None, "v2_mfe_mean": None,
            "v1_stop_rate": None, "v1_target_rate": None,
            "v2_stop_rate": None, "v2_target_rate": None,
            "avg_waiting_days": None,
            "positive_missed_upside": None, "avoided_loss": None, "n_no_fill": 0,
            "insufficient_sample": True,
            "stat_note": f"INSUFFICIENT SAMPLE (n=0, CI omitted)",
        }

    n_filled = sum(1 for s in valid if s.v2_filled)
    n_no_fill = n - n_filled

    v1_rets = [s.v1_ret for s in valid]
    v2_rets = [s.v2_ret for s in valid]
    deltas = [s.v2_ret - s.v1_ret for s in valid]

    # Missed opportunity: only no-fill signals
    no_fill_v1 = [s.v1_ret for s in valid if not s.v2_filled]
    pos_missed = [r for r in no_fill_v1 if r > 0]
    neg_missed = [r for r in no_fill_v1 if r < 0]

    # MAE/MFE
    v1_maes = [s.v1_mae for s in valid if s.v1_mae is not None]
    v1_mfes = [s.v1_mfe for s in valid if s.v1_mfe is not None]
    v2_maes = [s.v2_mae for s in valid if s.v2_filled and s.v2_mae is not None]
    v2_mfes = [s.v2_mfe for s in valid if s.v2_filled and s.v2_mfe is not None]

    wait_days = [float(s.v2_waiting_days) for s in valid if s.v2_filled and s.v2_waiting_days > 0]

    return {
        "label": label,
        "n": n,
        "n_filled": n_filled,
        "fill_rate_pct": round(n_filled / n * 100, 2) if n else None,
        "v1_mean": _mean(v1_rets),
        "v1_median": _median(v1_rets),
        "v2_mean": _mean(v2_rets),
        "v2_median": _median(v2_rets),
        "paired_delta_mean": _mean(deltas),
        "paired_delta_ci95": _bootstrap_ci(deltas),
        "v1_win_rate": round(sum(1 for r in v1_rets if r > 0) / n * 100, 2) if n else None,
        "v2_win_rate": round(sum(1 for r in v2_rets if r > 0) / n * 100, 2) if n else None,
        "v1_mae_mean": _mean(v1_maes),
        "v1_mfe_mean": _mean(v1_mfes),
        "v2_mae_mean": _mean(v2_maes),
        "v2_mfe_mean": _mean(v2_mfes),
        "v1_stop_rate": round(sum(1 for s in valid if s.v1_stop_hit) / n * 100, 2) if n else None,
        "v1_target_rate": round(sum(1 for s in valid if s.v1_target_hit) / n * 100, 2) if n else None,
        "v2_stop_rate": round(sum(1 for s in valid if s.v2_stop_hit) / n_filled * 100, 2) if n_filled else None,
        "v2_target_rate": round(sum(1 for s in valid if s.v2_target_hit) / n_filled * 100, 2) if n_filled else None,
        "avg_waiting_days": _mean(wait_days),
        "positive_missed_upside": _mean(pos_missed),
        "avoided_loss": _mean(neg_missed),
        "n_no_fill": n_no_fill,
        "insufficient_sample": n < INSUFFICIENT_SAMPLE_N,
        "stat_note": _stat_note(n),
    }


# ── Part A: Data Integrity Audit ──────────────────────────────────────────────

def run_data_integrity_audit(raw_signals: List[EnrichedSignal]) -> Dict:
    """
    Audit the signal dataset for concentration, maturity, and coverage gaps.

    Concentration warning fires when the top stock accounts for >15% of
    deduped matured signals — a known source of spurious results in
    Taiwan small-cap research.
    """
    deduped = [s for s in raw_signals if s.is_dedup_kept]
    matured = [s for s in deduped if s.is_matured]
    valid_paired = [s for s in matured if s.v1_ret is not None and s.v2_ret is not None]

    # Entry label distribution (deduped matured)
    label_dist = dict(Counter(s.entry_label for s in matured))

    # Stock concentration: top-5 by count
    stock_counts = Counter(s.stock_id for s in matured)
    top5_count = sum(c for _, c in stock_counts.most_common(5))
    top1_count = stock_counts.most_common(1)[0][1] if stock_counts else 0
    total_matured = len(matured)
    top5_pct = round(top5_count / total_matured * 100, 2) if total_matured else 0.0

    # Monthly distribution
    monthly: Dict[str, int] = defaultdict(int)
    for s in matured:
        key = s.signal_date.strftime("%Y-%m")
        monthly[key] += 1

    # Regime distribution
    regime_dist = dict(Counter(s.market_regime for s in matured))

    return {
        "raw_count": len(raw_signals),
        "dedup_count": len(deduped),
        "matured_count": total_matured,
        "valid_paired_count": len(valid_paired),
        "unique_stocks": len(set(s.stock_id for s in matured)),
        "unique_dates": len(set(s.signal_date for s in matured)),
        "entry_label_dist": label_dist,
        "stock_top5_pct": top5_pct,
        "monthly_dist": dict(sorted(monthly.items())),
        "regime_dist": regime_dist,
        "missing_maturity_count": len(deduped) - total_matured,
        "dedup_removed": len(raw_signals) - len(deduped),
        "concentration_warning": (top1_count / total_matured > 0.15) if total_matured else False,
        "primary_dataset": "dedup_matured_valid",
    }


# ── Part A2: MA20 Audit ───────────────────────────────────────────────────────

def run_ma20_audit(signals: List[EnrichedSignal]) -> Dict:
    """
    Validate that stop_price / (1 - STOP_BUFFER) closely approximates the
    actual MA20 output from EntryTimingAnalyzer.

    This matters because WAIT_FOR_PULLBACK uses the derived MA20 as its
    planned_entry reference.  Large deviations would indicate that the
    EntryTimingAnalyzer's stop formula changed, or that some signals used
    a non-standard stop calculation.
    """
    auditable = [s for s in signals if s.is_dedup_kept and s.is_matured and s.ma20 > 0]
    n = len(auditable)

    if n == 0:
        return {
            "n_audited": 0,
            "ma20_vs_derived_mean_abs_diff": None,
            "ma20_vs_derived_median_diff": None,
            "ma20_vs_derived_max_abs_diff": None,
            "pct_within_1pct": None,
            "wait_pullback_n": 0,
            "wait_pullback_entry_vs_ma20_mean_diff_pct": None,
            "assessment": "NO_DATA",
            "notes": ["No auditable signals found."],
        }

    diffs = [s.ma20 - s.ma20_derived for s in auditable]
    abs_diffs = [abs(d) for d in diffs]
    rel_abs_diffs = [abs(s.ma20 - s.ma20_derived) / s.ma20 * 100 for s in auditable if s.ma20 > 0]

    pct_within = round(sum(1 for d in rel_abs_diffs if d < 1.0) / len(rel_abs_diffs) * 100, 2)
    mean_abs = round(sum(abs_diffs) / n, 4)
    max_abs = round(max(abs_diffs), 4)
    sorted_diffs = sorted(diffs)
    median_diff = round(sorted_diffs[n // 2], 4) if n % 2 else round(
        (sorted_diffs[n // 2 - 1] + sorted_diffs[n // 2]) / 2, 4
    )

    # WAIT_FOR_PULLBACK sub-audit
    wp_sigs = [s for s in auditable if s.entry_label == "WAIT_FOR_PULLBACK" and s.ma20 > 0]
    wp_entry_diffs = [
        (s.planned_entry_price - s.ma20) / s.ma20 * 100
        for s in wp_sigs
    ]
    wp_mean_diff = round(sum(wp_entry_diffs) / len(wp_entry_diffs), 4) if wp_entry_diffs else None

    # Assessment: mean relative error
    mean_rel = sum(rel_abs_diffs) / len(rel_abs_diffs) if rel_abs_diffs else 0.0
    if mean_rel < 0.5:
        assessment = "ACCURATE"
    elif mean_rel < 2.0:
        assessment = "MINOR_DEVIATION"
    else:
        assessment = "SIGNIFICANT_DEVIATION"

    notes = [
        f"stop_derived MA20 = stop / (1 - {STOP_BUFFER}).  Deviation arises when "
        "EntryTimingAnalyzer uses a non-standard stop multiplier for a signal.",
        f"pct_within_1pct={pct_within}%  — proportion where derived MA20 is within 1% of actual.",
    ]
    if assessment == "SIGNIFICANT_DEVIATION":
        notes.append(
            "SIGNIFICANT_DEVIATION detected.  WAIT_FOR_PULLBACK trigger thresholds "
            "may be systematically mis-estimated.  Review EntryTimingAnalyzer stop formula."
        )

    return {
        "n_audited": n,
        "ma20_vs_derived_mean_abs_diff": mean_abs,
        "ma20_vs_derived_median_diff": median_diff,
        "ma20_vs_derived_max_abs_diff": max_abs,
        "pct_within_1pct": pct_within,
        "wait_pullback_n": len(wp_sigs),
        "wait_pullback_entry_vs_ma20_mean_diff_pct": wp_mean_diff,
        "assessment": assessment,
        "notes": notes,
    }


# ── Part B: Group Analysis ────────────────────────────────────────────────────

def run_group_analysis(signals: List[EnrichedSignal]) -> Dict:
    """
    Stratified performance comparison across all analysis dimensions.

    Uses only dedup-kept, matured, valid-paired signals.
    Groups with n < INSUFFICIENT_SAMPLE_N are labelled as such — they are
    hypothesis-generating only and must not be used to select parameters.
    """
    base = [
        s for s in signals
        if s.is_dedup_kept and s.is_matured
        and s.v1_ret is not None and s.v2_ret is not None
    ]

    def _by(key_fn) -> Dict:
        groups: Dict[str, List[EnrichedSignal]] = defaultdict(list)
        for s in base:
            groups[key_fn(s)].append(s)
        return {k: compute_group_stats(v, label=k) for k, v in sorted(groups.items())}

    result = {
        "overall": compute_group_stats(base, label="overall"),
        "by_entry_label": _by(lambda s: s.entry_label),
        "by_ma20_trend": _by(lambda s: s.ma20_trend),
        "by_ma60_trend": _by(lambda s: s.ma60_trend or "unknown"),
        "by_price_vs_ma20": _by(lambda s: s.price_vs_ma20),
        "by_price_vs_ma60": _by(lambda s: s.price_vs_ma60 or "unknown"),
        "by_ma20_gap_bucket": _by(lambda s: s.ma20_gap_bucket),
        "by_market_regime": _by(lambda s: s.market_regime),
        "multiple_testing_note": (
            f"Multiple Testing Risk: ~{MULTIPLE_TEST_N} comparisons performed. "
            f"Bonferroni-corrected alpha ≈ {0.05 / MULTIPLE_TEST_N:.4f}. "
            "Treat subgroup findings as hypothesis-generating only."
        ),
        "stat_significance_note": (
            "Groups with n < 30 are marked insufficient_sample=True and must not "
            "be used as evidence for or against V2.  Confidence intervals should "
            "not be compared across groups without correction for multiple testing."
        ),
    }
    return result


# ── Part C: Walk-forward Validation ──────────────────────────────────────────

def run_walk_forward(
    signals: List[EnrichedSignal],
    windows: List[Dict],
) -> List[Dict]:
    """
    Evaluate walk-forward windows in chronological order.

    Each window uses only signals from the test period.  Parameters are
    fixed — no parameter selection or tuning is performed per window.
    Embargo (embargo_days) is enforced by the caller when defining windows;
    this function enforces it by filtering signal_date >= test_start.

    pass_fail convention:
      PASS            — paired_delta_mean >= -1.0 (within 1 pp of zero)
      FAIL            — paired_delta_mean < -1.0
      INSUFFICIENT_DATA — n < MIN_GROUP_SAMPLE
    """
    base = [
        s for s in signals
        if s.is_dedup_kept and s.is_matured
        and s.v1_ret is not None and s.v2_ret is not None
    ]

    results = []
    for w in windows:
        t_start = w["test_start"] if isinstance(w["test_start"], date) else date.fromisoformat(w["test_start"])
        t_end = w["test_end"] if isinstance(w["test_end"], date) else date.fromisoformat(w["test_end"])

        window_sigs = [s for s in base if t_start <= s.signal_date <= t_end]
        stats = compute_group_stats(window_sigs, label=w["name"])

        # Dominant regime in this window
        regime_counts = Counter(s.market_regime for s in window_sigs)
        dominant_regime = regime_counts.most_common(1)[0][0] if regime_counts else "unknown"

        if stats["n"] < MIN_GROUP_SAMPLE:
            pass_fail = "INSUFFICIENT_DATA"
        elif stats["paired_delta_mean"] is not None and stats["paired_delta_mean"] >= -1.0:
            pass_fail = "PASS"
        else:
            pass_fail = "FAIL"

        results.append({
            "name": w["name"],
            "test_start": str(t_start),
            "test_end": str(t_end),
            "is_oos": w.get("is_oos", False),
            "embargo_days": w.get("embargo_days", 0),
            "dominant_regime": dominant_regime,
            "pass_fail": pass_fail,
            **stats,
        })

    return results


# ── Part D: Sensitivity Matrix ────────────────────────────────────────────────

def run_sensitivity_matrix(
    variants: List[Dict],
) -> List[Dict]:
    """
    Compare variant parameters against the base configuration.

    Each variant must supply its own pre-simulated signals list under
    variants[i]["signals"].  is_fragile = True when the variant's
    paired_delta deviates from base by more than 0.5 percentage points,
    indicating the result is sensitive to that assumption.

    Callers must not use the best-performing variant as the new default.
    """
    # Find base variant delta for fragility comparison
    base_delta: Optional[float] = None
    for v in variants:
        if v.get("name") == "base":
            base_stats = compute_group_stats(v["signals"], label="base")
            base_delta = base_stats.get("paired_delta_mean")
            break

    results = []
    fragile_count = 0

    for v in variants:
        v_signals = v.get("signals", [])
        stats = compute_group_stats(v_signals, label=v["name"])
        delta = stats.get("paired_delta_mean")

        is_fragile = False
        if delta is not None and base_delta is not None and v.get("name") != "base":
            is_fragile = abs(delta - base_delta) > 0.5
        if is_fragile:
            fragile_count += 1

        note = ""
        if is_fragile:
            note = f"FRAGILE: delta differs from base by {abs((delta or 0) - (base_delta or 0)):.2f}pp"
        elif stats["n"] < INSUFFICIENT_SAMPLE_N:
            note = stats["stat_note"]

        results.append({
            "variant": v["name"],
            "description": v.get("description", ""),
            "n": stats["n"],
            "paired_delta_mean": delta,
            "v1_mean": stats.get("v1_mean"),
            "v2_mean": stats.get("v2_mean"),
            "fill_rate_pct": stats.get("fill_rate_pct"),
            "paired_delta_ci95": stats.get("paired_delta_ci95"),
            "is_fragile": is_fragile,
            "note": note,
        })

    overall_robustness = "FRAGILE" if fragile_count > len(results) // 2 else "ROBUST"
    # Attach overall assessment to last entry for easy retrieval
    results.append({
        "variant": "_overall",
        "description": "Overall sensitivity robustness assessment",
        "n": None,
        "paired_delta_mean": None,
        "v1_mean": None,
        "v2_mean": None,
        "fill_rate_pct": None,
        "paired_delta_ci95": None,
        "is_fragile": fragile_count > 0,
        "note": f"{overall_robustness}: {fragile_count}/{len(results)-1} variants are fragile",
    })

    return results
