"""
scripts/run_hybrid_backtest.py — Hybrid Entry Strategy V1 In-Sample Analysis

RESEARCH ONLY — NOT A PRODUCTION SYSTEM.
⚠️  RETROSPECTIVE/EXPLORATORY ONLY — ALL HYBRID RESULTS ARE IN-SAMPLE.

Hybrid V1 rules were DERIVED from the same 2024-10 to 2026-09 research cohort
used here.  Results in data/hybrid_backtest.json CANNOT be treated as OOS.
True OOS = forward shadow only, starting from rule freeze date 2026-11-05.

What this script does:
  1. Load 2024-10 to 2026-09 signals from local SQLite (same cohort as
     run_effectiveness_analysis.py).
  2. Enrich each signal with trend state + market regime.
  3. Run V1 and V2 simulations (identical to effectiveness analysis).
  4. Apply HybridDecisionService (hybrid_v1 rules, frozen 2026-11-05).
  5. Compute three-strategy comparison (V1/V2/Hybrid) and subgroup analysis.
  6. Save results to data/hybrid_backtest.json.

Output is consumed by the dashboard Hybrid tab.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.research.effectiveness_analyzer import (
    EnrichedSignal,
    STOP_BUFFER,
    classify_ma20_gap_bucket,
    classify_ma_slope,
    compute_ma_slope,
)
from src.research.execution_simulator import EntryTimingExecutionSimulator
from src.research.hybrid_backtest import run_hybrid_analysis
from src.research.hybrid_entry_strategy import RULE_VERSION, RULE_FROZEN_AT, RULE_FROZEN_COMMIT

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH     = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "hybrid_backtest.json")

SIGNAL_START   = date(2024, 10, 1)
SIGNAL_END     = date(2026, 9, 15)
SAMPLE_STOCKS  = 150
MIN_TOTAL_BARS = 300
MIN_HIST_BARS  = 70
MIN_FWD_BARS   = 22
SIGNAL_STEP    = 5     # generate signals every ~5 calendar days
EXPIRY_DAYS    = 10
DEDUP_WINDOW   = 28    # calendar days

IN_SAMPLE_DISCLAIMER = (
    "RETROSPECTIVE/EXPLORATORY ONLY. "
    "Hybrid V1 rules were derived from the same 2024-10–2026-09 dataset. "
    "These results are IN-SAMPLE for Hybrid. "
    "True OOS = forward shadow starting 2026-11-05 (run_hybrid_forward_shadow.py)."
)


# ── Helpers reused from run_effectiveness_analysis.py ────────────────────────

def _load_all_ohlcv(conn: sqlite3.Connection, stock_id: str) -> pd.DataFrame:
    rows = conn.execute(
        "SELECT date, "
        "COALESCE(open, close) as open, "
        "close, "
        "COALESCE(high, close) as high, "
        "COALESCE(low, close) as low, "
        "COALESCE(volume, 0) as volume "
        "FROM daily_prices "
        "WHERE stock_id=? AND date BETWEEN ? AND ? "
        "ORDER BY date",
        (
            stock_id,
            str(SIGNAL_START - timedelta(days=200)),
            str(SIGNAL_END + timedelta(days=50)),
        ),
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for col in ["open", "close", "high", "low"]:
        df[col] = df[col].astype(float)
    return df


def _compute_regime_lookup(conn: sqlite3.Connection) -> Dict[date, str]:
    rows = conn.execute(
        "SELECT date, close FROM daily_prices "
        "WHERE stock_id='0050' AND date BETWEEN ? AND ? ORDER BY date",
        (str(SIGNAL_START - timedelta(days=100)), str(SIGNAL_END + timedelta(days=10))),
    ).fetchall()
    if not rows:
        return {}

    dates = [date.fromisoformat(r[0]) for r in rows]
    closes = [float(r[1]) for r in rows]
    regime_map: Dict[date, str] = {}

    for i, d in enumerate(dates):
        if i < 20:
            regime_map[d] = "unknown"
            continue
        ma20 = sum(closes[i - 19 : i + 1]) / 20
        if i >= 29:
            ma20_prev = sum(closes[i - 29 : i - 9]) / 20
            slope_pct = (ma20 - ma20_prev) / ma20_prev * 100 if ma20_prev > 0 else 0.0
        else:
            slope_pct = 0.0
        close = closes[i]
        if close > ma20 and slope_pct > 0.3:
            regime_map[d] = "bull"
        elif close < ma20 and slope_pct < -0.3:
            regime_map[d] = "bear"
        else:
            regime_map[d] = "neutral"

    return regime_map


def _enrich(
    signal_date: date,
    stock_id: str,
    entry_label: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    ma20: float,
    ma20_gap_pct: float,
    prior_20d_high: Optional[float],
    history: pd.DataFrame,
    regime_lookup: Dict[date, str],
) -> dict:
    closes = list(history["close"])
    n = len(closes)

    ma20_slope_pct = compute_ma_slope(closes)
    ma20_trend = classify_ma_slope(ma20_slope_pct)

    ma60: Optional[float] = None
    ma60_slope_pct: Optional[float] = None
    ma60_trend: Optional[str] = None
    if n >= 70:
        ma60 = round(sum(closes[-60:]) / 60, 4)
        ma60_prev = round(sum(closes[-70:-10]) / 60, 4)
        ma60_slope_pct = round((ma60 - ma60_prev) / ma60_prev * 100, 4) if ma60_prev > 0 else 0.0
        ma60_trend = classify_ma_slope(ma60_slope_pct)

    close_now = closes[-1] if closes else entry_price
    price_vs_ma20 = "above" if close_now >= ma20 else "below"
    price_vs_ma60: Optional[str] = None
    if ma60 is not None:
        price_vs_ma60 = "above" if close_now >= ma60 else "below"

    if entry_label == "WAIT_FOR_PULLBACK" and stop_price:
        planned_entry_price = stop_price / (1.0 - STOP_BUFFER)
    else:
        planned_entry_price = entry_price

    return {
        "signal_date": signal_date,
        "stock_id": stock_id,
        "entry_label": entry_label,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "ma20": ma20,
        "ma20_gap_pct": ma20_gap_pct,
        "prior_20d_high": prior_20d_high,
        "ma20_slope_pct": ma20_slope_pct,
        "ma20_trend": ma20_trend,
        "ma60": ma60,
        "ma60_slope_pct": ma60_slope_pct,
        "ma60_trend": ma60_trend,
        "price_vs_ma20": price_vs_ma20,
        "price_vs_ma60": price_vs_ma60,
        "ma20_gap_bucket": classify_ma20_gap_bucket(ma20_gap_pct),
        "market_regime": regime_lookup.get(signal_date, "unknown"),
        "planned_entry_price": planned_entry_price,
        "ma20_derived": stop_price / (1.0 - STOP_BUFFER) if stop_price else 0.0,
    }


def _run_simulation(
    sig: dict,
    ohlcv: pd.DataFrame,
    sim: EntryTimingExecutionSimulator,
) -> Tuple[Optional[float], Optional[float], bool, Optional[str], dict]:
    """Run V1 + V2; return (v1_ret, v2_ret, v2_filled, no_fill_reason, extras)."""
    signal_date = sig["signal_date"]
    stop_price = sig["stop_price"]
    target_price = sig["target_price"]
    entry_label = sig["entry_label"]
    stock_id = sig["stock_id"]

    post_bars = ohlcv[ohlcv["date"] > signal_date]
    if len(post_bars) < MIN_FWD_BARS:
        return None, None, False, "INSUFFICIENT_HIST", {}

    v1 = sim.simulate_v1(signal_date, stock_id, stop_price, target_price, ohlcv)
    if not v1.filled or v1.net_return_pct is None:
        return None, None, False, "V1_NO_FILL", {}

    # SA-7: perverse gap-up on V1 entry = skip
    if v1.fill_price and v1.fill_price >= target_price:
        return None, None, False, "GAP_UP_PERVERSE", {}

    v2 = sim.simulate_v2(
        signal_date,
        stock_id,
        entry_label,
        sig["planned_entry_price"],
        stop_price,
        target_price,
        ohlcv,
        prior_20d_high=sig["prior_20d_high"],
        v1_decision_label=entry_label,
        expiry_days=EXPIRY_DAYS,
    )

    v2_ret = v2.net_return_pct if v2.filled and v2.net_return_pct is not None else 0.0

    extras = {
        "v1_stop_hit": v1.stop_hit,
        "v1_target_hit": v1.target_hit,
        "v2_stop_hit": v2.stop_hit if v2.filled else False,
        "v2_target_hit": v2.target_hit if v2.filled else False,
        "v1_mae": v1.mae_pct,
        "v1_mfe": v1.mfe_pct,
        "v2_mae": v2.mae_pct if v2.filled else None,
        "v2_mfe": v2.mfe_pct if v2.filled else None,
        "v2_waiting_days": v2.waiting_days,
    }
    return (
        v1.net_return_pct,
        v2_ret,
        v2.filled,
        v2.no_fill_reason if not v2.filled else None,
        extras,
    )


# ── Entry timing analyzer (simplified; mirrors run_effectiveness_analysis) ────

def _get_entry_label_for_signal(
    signal_date: date,
    history: pd.DataFrame,
) -> Tuple[Optional[str], float, float, float, float, float, Optional[float]]:
    """
    Derive EntryTimingAnalyzer output from price history.

    Returns:
      (entry_label, entry_price, stop_price, target_price,
       ma20, ma20_gap_pct, prior_20d_high)
    or raises ValueError if data insufficient.

    This is a simplified re-implementation of EntryTimingAnalyzer that only
    produces signals for stocks with valid MA20 / stop / target.
    """
    closes = list(history["close"])
    if len(closes) < 20:
        return None, 0, 0, 0, 0, 0, None

    ma20 = round(sum(closes[-20:]) / 20, 4)
    close_now = closes[-1]
    ma20_gap_pct = round((close_now - ma20) / ma20 * 100, 4) if ma20 > 0 else 0.0

    # stop = MA20 × (1 - 0.03); target = entry × 1.06 (2R rule)
    stop_price = round(ma20 * (1.0 - STOP_BUFFER), 4)
    target_price = round(close_now * 1.06, 4)

    # Determine entry label
    if ma20_gap_pct > 5:
        entry_label = "TOO_EXTENDED"
    elif ma20_gap_pct < 0:
        entry_label = "WAIT_FOR_PULLBACK"
        # Actually WAIT_FOR_PULLBACK means price is ABOVE MA20 zone (gap 0–3%)
        # and stock will wait to enter at MA20. Reclassify:
        entry_label = "ENTRY_READY"  # below MA20 → not a valid pullback wait
    elif 0 <= ma20_gap_pct <= 3:
        entry_label = "WAIT_FOR_PULLBACK"
    elif 3 < ma20_gap_pct <= 5:
        entry_label = "ENTRY_READY"
    else:
        entry_label = "ENTRY_READY"

    # Prior 20D high
    if len(closes) >= 21:
        prior_20d_high = round(max(closes[-21:-1]), 4)
        # WAIT_FOR_BREAKOUT if price near prior high
        if close_now >= prior_20d_high * 0.98:
            entry_label = "WAIT_FOR_BREAKOUT"
    else:
        prior_20d_high = None

    return entry_label, close_now, stop_price, target_price, ma20, ma20_gap_pct, prior_20d_high


# ── Dedup ─────────────────────────────────────────────────────────────────────

def _dedup_28d(signals: List[dict]) -> List[dict]:
    """Keep first signal per stock per 28-calendar-day window."""
    signals_sorted = sorted(signals, key=lambda s: (s["stock_id"], s["signal_date"]))
    last_kept: Dict[str, date] = {}
    kept = []
    for s in signals_sorted:
        sid = s["stock_id"]
        d = s["signal_date"]
        last = last_kept.get(sid)
        if last is None or (d - last).days >= DEDUP_WINDOW:
            kept.append(s)
            last_kept[sid] = d
    return kept


# ── Main ──────────────────────────────────────────────────────────────────────

def build_enriched_signals(conn: sqlite3.Connection) -> List[EnrichedSignal]:
    """Load, enrich, simulate all signals for 2024-10 to 2026-09."""
    regime_lookup = _compute_regime_lookup(conn)
    sim = EntryTimingExecutionSimulator()

    # Stock universe
    rows = conn.execute(
        "SELECT DISTINCT stock_id FROM daily_prices "
        "WHERE stock_id != '0050' "
        "GROUP BY stock_id HAVING COUNT(*) >= ? "
        "LIMIT ?",
        (MIN_TOTAL_BARS, SAMPLE_STOCKS),
    ).fetchall()
    stocks = [r[0] for r in rows]
    print(f"[run_hybrid_backtest] {len(stocks)} stocks in universe")

    all_sigs: List[dict] = []

    for stock_id in stocks:
        ohlcv = _load_all_ohlcv(conn, stock_id)
        if ohlcv.empty or len(ohlcv) < MIN_TOTAL_BARS:
            continue

        # Generate signals at SIGNAL_STEP-day intervals
        step = timedelta(days=SIGNAL_STEP)
        d = SIGNAL_START
        while d <= SIGNAL_END:
            history = ohlcv[ohlcv["date"] <= d]
            if len(history) < MIN_HIST_BARS:
                d += step
                continue

            (
                entry_label,
                entry_price,
                stop_price,
                target_price,
                ma20,
                ma20_gap_pct,
                prior_20d_high,
            ) = _get_entry_label_for_signal(d, history)

            if entry_label is None or entry_label in {"TOO_EXTENDED"}:
                d += step
                continue
            if stop_price <= 0 or target_price <= 0 or entry_price <= 0:
                d += step
                continue

            enriched = _enrich(
                d, stock_id, entry_label, entry_price,
                stop_price, target_price, ma20, ma20_gap_pct,
                prior_20d_high, history, regime_lookup,
            )
            all_sigs.append(enriched)
            d += step

    # Dedup
    deduped = _dedup_28d(all_sigs)
    print(f"[run_hybrid_backtest] {len(all_sigs)} raw → {len(deduped)} after 28D dedup")

    # Simulate + build EnrichedSignal objects
    enriched_signals: List[EnrichedSignal] = []
    skipped = 0
    for sig_dict in deduped:
        stock_id = sig_dict["stock_id"]
        ohlcv = _load_all_ohlcv(conn, stock_id)

        v1_ret, v2_ret, v2_filled, no_fill_reason, extras = _run_simulation(
            sig_dict, ohlcv, sim
        )
        if v1_ret is None or v2_ret is None:
            skipped += 1
            continue

        paired_delta = round(v2_ret - v1_ret, 6)
        es = EnrichedSignal(
            signal_date=sig_dict["signal_date"],
            stock_id=sig_dict["stock_id"],
            entry_label=sig_dict["entry_label"],
            entry_price=sig_dict["entry_price"],
            stop_price=sig_dict["stop_price"],
            target_price=sig_dict["target_price"],
            ma20=sig_dict["ma20"],
            ma20_gap_pct=sig_dict["ma20_gap_pct"],
            prior_20d_high=sig_dict["prior_20d_high"],
            ma20_slope_pct=sig_dict["ma20_slope_pct"],
            ma20_trend=sig_dict["ma20_trend"],
            ma60=sig_dict["ma60"],
            ma60_slope_pct=sig_dict["ma60_slope_pct"],
            ma60_trend=sig_dict["ma60_trend"],
            price_vs_ma20=sig_dict["price_vs_ma20"],
            price_vs_ma60=sig_dict["price_vs_ma60"],
            ma20_gap_bucket=sig_dict["ma20_gap_bucket"],
            market_regime=sig_dict["market_regime"],
            planned_entry_price=sig_dict["planned_entry_price"],
            v1_ret=v1_ret,
            v2_ret=v2_ret,
            v2_filled=v2_filled,
            v2_no_fill_reason=no_fill_reason,
            v1_stop_hit=extras.get("v1_stop_hit", False),
            v1_target_hit=extras.get("v1_target_hit", False),
            v2_stop_hit=extras.get("v2_stop_hit", False),
            v2_target_hit=extras.get("v2_target_hit", False),
            v1_mae=extras.get("v1_mae"),
            v1_mfe=extras.get("v1_mfe"),
            v2_mae=extras.get("v2_mae"),
            v2_mfe=extras.get("v2_mfe"),
            v2_waiting_days=extras.get("v2_waiting_days", 0),
            paired_delta=paired_delta,
            is_matured=True,
            is_raw=False,
            is_dedup_kept=True,
            ma20_derived=sig_dict["ma20_derived"],
        )
        enriched_signals.append(es)

    print(f"[run_hybrid_backtest] {len(enriched_signals)} valid paired signals ({skipped} skipped)")
    return enriched_signals


class _DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


def main() -> None:
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    try:
        enriched = build_enriched_signals(conn)
    finally:
        conn.close()

    if not enriched:
        print("[ERROR] No enriched signals generated")
        sys.exit(1)

    print(f"[run_hybrid_backtest] Running Hybrid analysis on {len(enriched)} signals…")
    result = run_hybrid_analysis(enriched)

    # Add meta
    result["meta"] = {
        "script": "scripts/run_hybrid_backtest.py",
        "rule_version": RULE_VERSION,
        "rule_frozen_at": RULE_FROZEN_AT,
        "rule_frozen_commit": RULE_FROZEN_COMMIT,
        "signal_period": f"{SIGNAL_START} to {SIGNAL_END}",
        "n_valid_signals": len(enriched),
        "disclaimer": IN_SAMPLE_DISCLAIMER,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2, cls=_DateEncoder)

    print(f"[run_hybrid_backtest] Saved → {OUTPUT_PATH}")

    comp = result.get("comparison", {})
    strategies = comp.get("strategies", {})
    print("\n── Three-strategy comparison ──")
    for strat, stats in strategies.items():
        print(f"  {strat:12s}: n={stats.get('n','?'):5d}  mean={stats.get('mean_net_ret','?'):+.3f}%  win={stats.get('win_rate','?'):.1f}%")
    print("\n── Paired deltas ──")
    for pair, stats in comp.get("paired_deltas", {}).items():
        ci = stats.get("ci_95") or {}
        print(
            f"  {pair:25s}: mean={stats.get('mean','?'):+.3f}%  "
            f"CI=[{ci.get('lo','?')},{ci.get('hi','?')}]  {stats.get('ci_verdict','')}"
        )
    print(f"\n⚠️  {IN_SAMPLE_DISCLAIMER}")


if __name__ == "__main__":
    main()
