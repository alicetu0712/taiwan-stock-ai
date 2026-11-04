"""
scripts/run_effectiveness_analysis.py — Entry Timing V2 Effectiveness Analysis

RESEARCH ONLY — NOT A PRODUCTION SYSTEM.

Generates research signals via EntryTimingAnalyzer on real DailyPrice OHLC,
enriches with trend state and 0050-based market regime, runs all analysis
(Parts A through D), and saves results to data/effectiveness_analysis.json.

Data limitations:
  - Signal source: EntryTimingAnalyzer (NOT production ForwardSignal pipeline)
  - No production ForwardSignal history in local SQLite
  - 0050 used as market regime proxy; Taiwan small-cap names excluded from stocks
  - Signal period: 2024-10-01 to 2026-09-15 (safe 20D forward coverage)
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

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "effectiveness_analysis.json")

SIGNAL_START = date(2024, 10, 1)
SIGNAL_END   = date(2026, 9, 15)   # DailyPrice ends 2026-10-28; need 22 forward bars
SAMPLE_STOCKS = 150
MIN_TOTAL_BARS = 300    # total bars in full period
MIN_HIST_BARS = 70      # bars before signal needed (60 for MA60 + 10 slope lookback)
MIN_FWD_BARS  = 22      # forward bars needed for 20D simulation
SIGNAL_STEP_DAYS = 5    # weekly-ish signal checks
EXPIRY_DAYS = 10        # WAIT_FOR_* expiry window
DEDUP_WINDOW = 28       # calendar days for 28-day dedup

# Walk-forward windows (no parameter fitting; purely chronological stratification)
WALK_FORWARD_WINDOWS = [
    {"name": "W1", "test_start": date(2025, 1, 1),  "test_end": date(2025, 2, 28), "embargo_days": 25, "is_oos": False},
    {"name": "W2", "test_start": date(2025, 3, 1),  "test_end": date(2025, 4, 30), "embargo_days": 25, "is_oos": False},
    {"name": "W3", "test_start": date(2025, 5, 1),  "test_end": date(2025, 6, 30), "embargo_days": 25, "is_oos": False},
    {"name": "W4", "test_start": date(2025, 7, 1),  "test_end": date(2025, 8, 31), "embargo_days": 25, "is_oos": False},
    {"name": "W5", "test_start": date(2025, 9, 1),  "test_end": date(2025, 10, 31), "embargo_days": 25, "is_oos": False},
    {"name": "W6", "test_start": date(2025, 11, 1), "test_end": date(2025, 12, 31), "embargo_days": 25, "is_oos": False},
    {"name": "W7", "test_start": date(2026, 1, 1),  "test_end": date(2026, 2, 28), "embargo_days": 25, "is_oos": False},
    {"name": "W8", "test_start": date(2026, 3, 1),  "test_end": date(2026, 4, 30), "embargo_days": 25, "is_oos": False},
    {"name": "W9", "test_start": date(2026, 5, 1),  "test_end": date(2026, 6, 30), "embargo_days": 25, "is_oos": False},
    {"name": "OOS", "test_start": date(2026, 7, 1), "test_end": date(2026, 9, 15), "embargo_days": 25, "is_oos": True},
]


# ── Data loading ──────────────────────────────────────────────────────────────

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
        (stock_id, str(SIGNAL_START - timedelta(days=200)), str(SIGNAL_END + timedelta(days=50)))
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for col in ["open", "close", "high", "low"]:
        df[col] = df[col].astype(float)
    return df


def _compute_regime_lookup(conn: sqlite3.Connection) -> Dict[date, str]:
    """
    For each trading date, determine market regime using 0050 MA20 and slope.

    bull:    0050 close > MA20_0050 AND MA20 slope > 0.3%
    bear:    0050 close < MA20_0050 AND MA20 slope < -0.3%
    neutral: everything else
    """
    rows = conn.execute(
        "SELECT date, close FROM daily_prices "
        "WHERE stock_id='0050' AND date BETWEEN ? AND ? ORDER BY date",
        (str(SIGNAL_START - timedelta(days=100)), str(SIGNAL_END + timedelta(days=10)))
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

        ma20 = sum(closes[i-19:i+1]) / 20

        # 10-bar MA20 slope
        if i >= 29:
            ma20_prev = sum(closes[i-29:i-9]) / 20
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


# ── Signal enrichment ─────────────────────────────────────────────────────────

def _enrich_signal(
    signal_date: date,
    stock_id: str,
    entry_label: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    ma20: float,
    ma20_gap_pct: float,
    prior_20d_high: Optional[float],
    history: pd.DataFrame,          # bars UP TO AND INCLUDING signal_date
    regime_lookup: Dict[date, str],
) -> dict:
    """
    Compute trend state and enrichment fields from pre-signal history.
    Returns a dict of EnrichedSignal kwargs (minus simulation results).
    """
    from src.research.effectiveness_analyzer import (
        STOP_BUFFER,
        classify_ma20_gap_bucket,
        classify_ma_slope,
        compute_ma_slope,
    )

    closes = list(history["close"])
    n = len(closes)

    # MA20 slope (needs ≥ MA20_SLOPE_BARS + 20 closes)
    ma20_slope_pct = compute_ma_slope(closes)
    ma20_trend = classify_ma_slope(ma20_slope_pct)

    # MA60 slope
    ma60: Optional[float] = None
    ma60_slope_pct: Optional[float] = None
    ma60_trend: Optional[str] = None
    if n >= 70:
        ma60 = round(sum(closes[-60:]) / 60, 4)
        # Slope: compare MA60 now vs 10 bars ago
        if n >= 70:
            ma60_prev = round(sum(closes[-70:-10]) / 60, 4)
            ma60_slope_pct = round((ma60 - ma60_prev) / ma60_prev * 100, 4) if ma60_prev > 0 else 0.0
            ma60_trend = classify_ma_slope(ma60_slope_pct)

    close_now = closes[-1] if closes else entry_price
    price_vs_ma20 = "above" if close_now >= ma20 else "below"
    price_vs_ma60: Optional[str] = None
    if ma60 is not None:
        price_vs_ma60 = "above" if close_now >= ma60 else "below"

    ma20_gap_bucket = classify_ma20_gap_bucket(ma20_gap_pct)
    market_regime = regime_lookup.get(signal_date, "unknown")

    # Planned entry
    if entry_label == "WAIT_FOR_PULLBACK" and stop_price:
        planned_entry_price = stop_price / (1.0 - STOP_BUFFER)
    else:
        planned_entry_price = entry_price

    ma20_derived = stop_price / (1.0 - STOP_BUFFER) if stop_price else 0.0

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
        "ma20_gap_bucket": ma20_gap_bucket,
        "market_regime": market_regime,
        "planned_entry_price": planned_entry_price,
        "ma20_derived": ma20_derived,
    }


def _run_simulation(
    sig_dict: dict,
    ohlcv: pd.DataFrame,
    sim,
    expiry_days: int,
    extra_fees: float = 0.0,
) -> Tuple[Optional[float], Optional[float], bool, Optional[str], dict]:
    """
    Run V1 and V2 simulation for one signal.
    Returns (v1_ret, v2_ret, v2_filled, v2_no_fill_reason, extra_fields).
    """
    signal_date = sig_dict["signal_date"]
    stop_price = sig_dict["stop_price"]
    target_price = sig_dict["target_price"]
    entry_label = sig_dict["entry_label"]

    # Minimum forward bar check
    post_bars = ohlcv[ohlcv["date"] > signal_date]
    if len(post_bars) < MIN_FWD_BARS:
        return None, None, False, "INSUFFICIENT_HIST", {}

    v1_trade = sim.simulate_v1(signal_date, sig_dict["stock_id"], stop_price, target_price, ohlcv)
    if v1_trade.fill_price and v1_trade.fill_price >= target_price:
        return None, None, False, "GAP_UP_PERVERSE", {}

    v1_ret = v1_trade.net_return_pct
    if v1_ret is None:
        return None, None, False, "V1_NO_RETURN", {}

    if extra_fees != 0.0 and v1_trade.filled:
        v1_ret = round(v1_ret - extra_fees, 4)

    v2_trade = sim.simulate_v2(
        signal_date=signal_date,
        stock_id=sig_dict["stock_id"],
        entry_label=entry_label,
        planned_entry=sig_dict["planned_entry_price"],
        stop_price=stop_price,
        target_price=target_price,
        ohlcv=ohlcv,
        prior_20d_high=sig_dict.get("prior_20d_high"),
        expiry_days=expiry_days,
    )

    v2_filled = v2_trade.filled and v2_trade.net_return_pct is not None
    if v2_filled:
        v2_ret = v2_trade.net_return_pct
        if extra_fees != 0.0:
            v2_ret = round(v2_ret - extra_fees, 4)
    else:
        v2_ret = 0.0  # SA-7

    extra = {
        "v1_stop_hit": v1_trade.stop_hit,
        "v1_target_hit": v1_trade.target_hit,
        "v2_stop_hit": v2_trade.stop_hit if v2_filled else False,
        "v2_target_hit": v2_trade.target_hit if v2_filled else False,
        "v1_mae": v1_trade.mae_pct,
        "v1_mfe": v1_trade.mfe_pct,
        "v2_mae": v2_trade.mae_pct if v2_filled else None,
        "v2_mfe": v2_trade.mfe_pct if v2_filled else None,
        "v2_waiting_days": v2_trade.waiting_days if v2_filled else 0,
        "v2_no_fill_reason": v2_trade.no_fill_reason if not v2_filled else None,
    }

    return v1_ret, v2_ret, v2_filled, None, extra


# ── Main ──────────────────────────────────────────────────────────────────────

def run_effectiveness_analysis() -> None:
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Local SQLite not found at {DB_PATH}")
        return

    from src.analyzers.entry_timing import EntryTimingAnalyzer
    from src.research.effectiveness_analyzer import EnrichedSignal, run_data_integrity_audit, run_group_analysis, run_ma20_audit, run_sensitivity_matrix, run_walk_forward
    from src.research.execution_simulator import EntryTimingExecutionSimulator

    conn = sqlite3.connect(DB_PATH)
    sim = EntryTimingExecutionSimulator()

    print("=== Entry Timing V2 Effectiveness Analysis ===")
    print(f"Period:  {SIGNAL_START} to {SIGNAL_END}")
    print(f"Stocks:  up to {SAMPLE_STOCKS}")
    print("WARNING: RESEARCH ONLY — NOT A LIVE BUY SIGNAL\n")

    # ── Select stocks ─────────────────────────────────────────────────────────
    rows = conn.execute("""
        SELECT stock_id FROM daily_prices
        WHERE date BETWEEN ? AND ?
        GROUP BY stock_id HAVING COUNT(*) >= ?
        ORDER BY stock_id
        LIMIT ?
    """, (str(SIGNAL_START - timedelta(days=200)), str(SIGNAL_END + timedelta(days=50)),
          MIN_TOTAL_BARS, SAMPLE_STOCKS)).fetchall()
    stock_ids = [r[0] for r in rows]
    print(f"Eligible stocks: {len(stock_ids)}")

    # ── Compute 0050 regime lookup ────────────────────────────────────────────
    regime_lookup = _compute_regime_lookup(conn)
    print(f"Regime dates: {len(regime_lookup)} trading days")

    # ── Load all OHLCV per stock (single DB hit per stock) ───────────────────
    print("Loading OHLCV data...", end=" ", flush=True)
    ohlcv_by_stock: Dict[str, pd.DataFrame] = {}
    for sid in stock_ids:
        df = _load_all_ohlcv(conn, sid)
        if not df.empty:
            ohlcv_by_stock[sid] = df
    print(f"{len(ohlcv_by_stock)} stocks loaded")
    conn.close()

    # ── Generate and enrich signals ───────────────────────────────────────────
    analyzer = EntryTimingAnalyzer()
    all_raw: List[dict] = []  # raw signal dicts before dedup
    ohlcv_cache: Dict[Tuple, pd.DataFrame] = {}  # (stock_id, signal_date) → ohlcv slice

    signal_date = SIGNAL_START
    skipped = 0
    while signal_date <= SIGNAL_END:
        for stock_id in stock_ids:
            df = ohlcv_by_stock.get(stock_id)
            if df is None:
                continue

            # History up to signal_date (inclusive)
            hist = df[df["date"] <= signal_date]
            if len(hist) < MIN_HIST_BARS:
                skipped += 1
                continue

            result = analyzer.analyze(stock_id, hist)
            if result.entry_label not in ("ENTRY_READY", "WAIT_FOR_PULLBACK", "WAIT_FOR_BREAKOUT"):
                continue
            if result.stop_price is None or result.target_price is None:
                continue

            enriched_kw = _enrich_signal(
                signal_date=signal_date,
                stock_id=stock_id,
                entry_label=result.entry_label,
                entry_price=float(result.entry_price) if result.entry_price else 100.0,
                stop_price=float(result.stop_price),
                target_price=float(result.target_price),
                ma20=float(result.ma20) if result.ma20 else 0.0,
                ma20_gap_pct=float(result.ma20_gap_pct) if result.ma20_gap_pct else 0.0,
                prior_20d_high=float(result.prior_20d_high) if result.prior_20d_high else None,
                history=hist,
                regime_lookup=regime_lookup,
            )
            enriched_kw["is_raw"] = True
            enriched_kw["is_dedup_kept"] = True  # will be updated in dedup pass
            enriched_kw["is_matured"] = True       # will be updated after simulation

            # Cache ohlcv slice for simulation
            full_ohlcv = df[df["date"] >= signal_date - timedelta(days=5)].copy()
            ohlcv_cache[(stock_id, signal_date)] = full_ohlcv

            all_raw.append(enriched_kw)

        signal_date += timedelta(days=SIGNAL_STEP_DAYS)

    print(f"Raw signals generated: {len(all_raw)}  (skipped {skipped} low-history checks)")

    # ── 28-day dedup ─────────────────────────────────────────────────────────
    seen: Dict[str, date] = {}
    for sig in sorted(all_raw, key=lambda x: x["signal_date"]):
        last = seen.get(sig["stock_id"])
        if last is None or (sig["signal_date"] - last).days > DEDUP_WINDOW:
            seen[sig["stock_id"]] = sig["signal_date"]
        else:
            sig["is_dedup_kept"] = False

    deduped_count = sum(1 for s in all_raw if s["is_dedup_kept"])
    dedup_removed = len(all_raw) - deduped_count
    print(f"After 28-day dedup: {deduped_count} signals (removed {dedup_removed})")

    # ── Simulate V1 and V2 (base parameters) ─────────────────────────────────
    print("Running V1/V2 simulations...", end=" ", flush=True)
    enriched_signals: List[EnrichedSignal] = []
    sim_errors = 0

    for sig in all_raw:
        ohlcv = ohlcv_cache.get((sig["stock_id"], sig["signal_date"]), pd.DataFrame())
        if ohlcv.empty:
            sig["is_matured"] = False
            sig["v1_ret"] = None
            sig["v2_ret"] = None
            sig["v2_filled"] = False
            sim_errors += 1
        else:
            v1_ret, v2_ret, v2_filled, skip_reason, extra = _run_simulation(
                sig, ohlcv, sim, EXPIRY_DAYS
            )
            sig["is_matured"] = (v1_ret is not None)
            sig["v1_ret"] = v1_ret
            sig["v2_ret"] = v2_ret
            sig["v2_filled"] = v2_filled
            sig["v2_no_fill_reason"] = skip_reason or extra.get("v2_no_fill_reason")
            sig["paired_delta"] = round(v2_ret - v1_ret, 4) if (v1_ret is not None and v2_ret is not None) else None
            sig.update({k: extra.get(k) for k in [
                "v1_stop_hit", "v1_target_hit", "v2_stop_hit", "v2_target_hit",
                "v1_mae", "v1_mfe", "v2_mae", "v2_mfe", "v2_waiting_days",
            ]})

        # Build EnrichedSignal
        es = EnrichedSignal(
            signal_date=sig["signal_date"],
            stock_id=sig["stock_id"],
            entry_label=sig["entry_label"],
            entry_price=sig.get("entry_price", 100.0),
            stop_price=sig["stop_price"],
            target_price=sig["target_price"],
            ma20=sig.get("ma20", 0.0),
            ma20_gap_pct=sig.get("ma20_gap_pct", 0.0),
            prior_20d_high=sig.get("prior_20d_high"),
            ma20_slope_pct=sig.get("ma20_slope_pct", 0.0),
            ma20_trend=sig.get("ma20_trend", "flat"),
            ma60=sig.get("ma60"),
            ma60_slope_pct=sig.get("ma60_slope_pct"),
            ma60_trend=sig.get("ma60_trend"),
            price_vs_ma20=sig.get("price_vs_ma20", "above"),
            price_vs_ma60=sig.get("price_vs_ma60"),
            ma20_gap_bucket=sig.get("ma20_gap_bucket", "0-2%"),
            market_regime=sig.get("market_regime", "unknown"),
            planned_entry_price=sig.get("planned_entry_price", 0.0),
            v1_ret=sig.get("v1_ret"),
            v2_ret=sig.get("v2_ret"),
            v2_filled=sig.get("v2_filled", False),
            v2_no_fill_reason=sig.get("v2_no_fill_reason"),
            v1_stop_hit=sig.get("v1_stop_hit", False),
            v1_target_hit=sig.get("v1_target_hit", False),
            v2_stop_hit=sig.get("v2_stop_hit", False),
            v2_target_hit=sig.get("v2_target_hit", False),
            v1_mae=sig.get("v1_mae"),
            v1_mfe=sig.get("v1_mfe"),
            v2_mae=sig.get("v2_mae"),
            v2_mfe=sig.get("v2_mfe"),
            v2_waiting_days=sig.get("v2_waiting_days", 0),
            paired_delta=sig.get("paired_delta"),
            is_matured=sig.get("is_matured", True),
            is_raw=True,
            is_dedup_kept=sig.get("is_dedup_kept", True),
            ma20_derived=sig.get("ma20_derived", 0.0),
        )
        enriched_signals.append(es)

    valid_paired = sum(1 for s in enriched_signals
                       if s.is_dedup_kept and s.is_matured
                       and s.v1_ret is not None and s.v2_ret is not None)
    print(f"done  (valid paired: {valid_paired}, sim errors: {sim_errors})")

    # ── Sensitivity variants ───────────────────────────────────────────────────
    print("Running sensitivity variants...", end=" ", flush=True)

    def _build_variant_signals(expiry_days: int, extra_fees: float = 0.0, dedup_only: bool = True) -> List[EnrichedSignal]:
        """Re-run simulation with different parameters on the same raw signals."""
        variant_sigs = []
        for sig in all_raw:
            if dedup_only and not sig["is_dedup_kept"]:
                continue
            ohlcv = ohlcv_cache.get((sig["stock_id"], sig["signal_date"]), pd.DataFrame())
            if ohlcv.empty:
                continue
            v1r, v2r, v2f, _, extra = _run_simulation(sig, ohlcv, sim, expiry_days, extra_fees)
            if v1r is None or v2r is None:
                continue
            es = EnrichedSignal(
                signal_date=sig["signal_date"],
                stock_id=sig["stock_id"],
                entry_label=sig["entry_label"],
                entry_price=sig.get("entry_price", 100.0),
                stop_price=sig["stop_price"],
                target_price=sig["target_price"],
                ma20=sig.get("ma20", 0.0),
                ma20_gap_pct=sig.get("ma20_gap_pct", 0.0),
                prior_20d_high=sig.get("prior_20d_high"),
                ma20_slope_pct=sig.get("ma20_slope_pct", 0.0),
                ma20_trend=sig.get("ma20_trend", "flat"),
                ma60=sig.get("ma60"),
                ma60_slope_pct=sig.get("ma60_slope_pct"),
                ma60_trend=sig.get("ma60_trend"),
                price_vs_ma20=sig.get("price_vs_ma20", "above"),
                price_vs_ma60=sig.get("price_vs_ma60"),
                ma20_gap_bucket=sig.get("ma20_gap_bucket", "0-2%"),
                market_regime=sig.get("market_regime", "unknown"),
                planned_entry_price=sig.get("planned_entry_price", 0.0),
                v1_ret=v1r, v2_ret=v2r, v2_filled=v2f,
                v1_stop_hit=extra.get("v1_stop_hit", False),
                v1_target_hit=extra.get("v1_target_hit", False),
                v2_stop_hit=extra.get("v2_stop_hit", False),
                v2_target_hit=extra.get("v2_target_hit", False),
                v1_mae=extra.get("v1_mae"),
                v1_mfe=extra.get("v1_mfe"),
                v2_mae=extra.get("v2_mae"),
                v2_mfe=extra.get("v2_mfe"),
                v2_waiting_days=extra.get("v2_waiting_days", 0),
                paired_delta=round(v2r - v1r, 4),
                is_matured=True,
                is_raw=True,
                is_dedup_kept=True,
                ma20_derived=sig.get("ma20_derived", 0.0),
            )
            variant_sigs.append(es)
        return variant_sigs

    base_sigs = [s for s in enriched_signals if s.is_dedup_kept and s.is_matured and s.v1_ret is not None and s.v2_ret is not None]
    sens_variants = [
        {"name": "base",           "description": "Base: expiry=10d, fees=0.585%", "signals": base_sigs},
        {"name": "expiry_5",       "description": "Short wait: expiry=5d",         "signals": _build_variant_signals(5)},
        {"name": "expiry_3",       "description": "Very short wait: expiry=3d",    "signals": _build_variant_signals(3)},
        {"name": "expiry_15",      "description": "Long wait: expiry=15d",         "signals": _build_variant_signals(15)},
        {"name": "high_fees_0.8",  "description": "Higher fees: 0.8% round-trip",  "signals": _build_variant_signals(10, extra_fees=0.215)},
        {"name": "no_dedup",       "description": "All raw signals (no 28d dedup)", "signals": _build_variant_signals(10, dedup_only=False)},
    ]
    print("done")

    # ── Run all analyses ──────────────────────────────────────────────────────
    print("Running analyses...")

    integrity = run_data_integrity_audit(enriched_signals)
    ma20_audit = run_ma20_audit(enriched_signals)
    group_analysis = run_group_analysis(enriched_signals)
    walk_forward = run_walk_forward(enriched_signals, WALK_FORWARD_WINDOWS)
    sensitivity = run_sensitivity_matrix(sens_variants)

    # ── Overall summary ───────────────────────────────────────────────────────
    overall_stats = group_analysis.get("overall", {})
    overall_delta = overall_stats.get("paired_delta_mean")
    oos_window = next((w for w in walk_forward if w.get("is_oos")), None)
    oos_delta = oos_window.get("paired_delta_mean") if oos_window else None
    n_valid = integrity.get("valid_paired_count", 0)
    ci = overall_stats.get("paired_delta_ci95")

    # Verdict logic
    if n_valid < 50:
        verdict = "INSUFFICIENT DATA"
    elif oos_delta is not None and ci and ci["lo"] > 0:
        verdict = "VALIDATED"
    elif overall_delta is not None and ci and ci["hi"] < 0:
        verdict = "NOT SUPPORTED"
    else:
        verdict = "CONDITIONAL"

    summary = {
        "overall_paired_delta": overall_delta,
        "overall_fill_rate": overall_stats.get("fill_rate_pct"),
        "overall_v1_mean": overall_stats.get("v1_mean"),
        "overall_v2_mean": overall_stats.get("v2_mean"),
        "overall_n": n_valid,
        "oos_paired_delta": oos_delta,
        "oos_n": oos_window.get("n") if oos_window else None,
        "oos_pass_fail": oos_window.get("pass_fail") if oos_window else None,
        "verdict": verdict,
    }

    # ── Save JSON ─────────────────────────────────────────────────────────────
    def _jsonify(obj):
        """Convert dates and unserializable objects for JSON."""
        if isinstance(obj, date):
            return str(obj)
        if isinstance(obj, dict):
            return {k: _jsonify(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_jsonify(x) for x in obj]
        return obj

    output = _jsonify({
        "generated_at": str(date.today()),
        "config": {
            "signal_start": SIGNAL_START,
            "signal_end": SIGNAL_END,
            "sample_stocks": SAMPLE_STOCKS,
            "step_days": SIGNAL_STEP_DAYS,
            "expiry_days": EXPIRY_DAYS,
            "dedup_window": DEDUP_WINDOW,
        },
        "total_raw_signals": len(all_raw),
        "total_deduped_signals": deduped_count,
        "data_integrity_audit": integrity,
        "ma20_audit": ma20_audit,
        "group_analysis": group_analysis,
        "walk_forward": walk_forward,
        "sensitivity_matrix": sensitivity,
        "summary": summary,
    })

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved → {OUTPUT_PATH}")

    # ── Print summary ─────────────────────────────────────────────────────────
    _print_summary(output, walk_forward, sensitivity)


def _print_summary(output: dict, walk_forward: list, sensitivity: list) -> None:
    s = output["summary"]
    integrity = output["data_integrity_audit"]

    print("\n" + "=" * 60)
    print("ENTRY TIMING V2 EFFECTIVENESS ANALYSIS — SUMMARY")
    print("=" * 60)
    print(f"\n── Data ──")
    print(f"  Raw signals:          {output['total_raw_signals']}")
    print(f"  After dedup:          {output['total_deduped_signals']}")
    print(f"  Matured & paired:     {s['overall_n']}")
    print(f"  Unique stocks:        {integrity.get('unique_stocks')}")
    print(f"  Concentration warn:   {integrity.get('concentration_warning')}")
    print(f"  MA20 audit:           {output['ma20_audit'].get('assessment')}")

    print(f"\n── Overall (All Windows) ──")
    _fmt = lambda v: f"{v:+.2f}%" if v is not None else "N/A"
    print(f"  V1 mean:              {_fmt(s.get('overall_v1_mean'))}")
    print(f"  V2 FOS mean:          {_fmt(s.get('overall_v2_mean'))}")
    print(f"  Paired Delta (V2-V1): {_fmt(s.get('overall_paired_delta'))}")
    print(f"  Fill Rate:            {s.get('overall_fill_rate')}%")

    print(f"\n── Walk-forward ──")
    for w in walk_forward:
        tag = " [OOS]" if w.get("is_oos") else ""
        pf = w.get("pass_fail", "?")
        delta = w.get("paired_delta_mean")
        n = w.get("n", 0)
        print(f"  {w['name']:<6}{tag:<6}: {pf:<18} delta={_fmt(delta)}  n={n}")

    print(f"\n── OOS ──")
    print(f"  OOS delta:            {_fmt(s.get('oos_paired_delta'))}")
    print(f"  OOS n:                {s.get('oos_n')}")
    print(f"  OOS pass/fail:        {s.get('oos_pass_fail')}")

    print(f"\n── Sensitivity ──")
    for v in sensitivity:
        if v["variant"] == "_overall":
            print(f"  Overall robustness:  {v['note']}")
        elif not v.get("is_fragile"):
            pass
        else:
            print(f"  FRAGILE: {v['variant']} — {v['note']}")

    print(f"\n── VERDICT: {s['verdict']} ──")
    print("RESEARCH ONLY — NOT A LIVE BUY SIGNAL")
    print("=" * 60)


if __name__ == "__main__":
    run_effectiveness_analysis()
