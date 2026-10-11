"""
test_scorecard.py — Overlapping Samples dedup 邏輯測試

核心驗證：
  - _dedup_cohort 正確去除同一股票在冷卻期（交易日）內的重複訊號
  - _summary_stats 的 20D 和 60D 統計使用各自的 Dedup 樣本，而非 Raw N
  - 測試使用 Mon-Fri 模擬日曆（與 dedup_utils 保持一致）
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

# Stub streamlit before importing scorecard so the module loads without
# the real streamlit package.  cache_data must be a passthrough decorator
# so @st.cache_data(ttl=...) annotated functions remain callable.
if "streamlit" not in sys.modules:
    _st = MagicMock()
    _st.cache_data = lambda **_kw: (lambda f: f)
    sys.modules["streamlit"] = _st

from dashboard._pages.scorecard import (
    _dedup_cohort,
    _stats_block,
    _summary_stats,
)


# ── helpers ───────────────────────────────────────────────────

def _mon_fri(start: date, end: date) -> list:
    """Generate Mon-Fri trading dates between start and end inclusive."""
    cal, d = [], start
    while d <= end:
        if d.weekday() < 5:
            cal.append(d)
        d += timedelta(days=1)
    return cal


# Mon-Fri calendar covering Jan-Mar 2024 (used across tests)
_TEST_CAL = _mon_fri(date(2024, 1, 1), date(2024, 3, 31))


def _row(stock_id: str, trade_date: date, alpha_20: float | None = None,
         alpha_60: float | None = None, outcome: str | None = None) -> dict:
    return {
        "stock_id":       stock_id,
        "trade_date":     str(trade_date),
        "decision_label": "buy",
        "alpha_20d":      alpha_20,
        "alpha_60d":      alpha_60,
        "outcome_note":   outcome or ("EXPIRED" if alpha_20 is not None else None),
        "fwd_return_20d": alpha_20,
        "fwd_return_60d": alpha_60,
    }


# ── _dedup_cohort ─────────────────────────────────────────────

class TestDedupCohort:
    """Tests use _TEST_CAL (Mon-Fri Jan–Mar 2024). Exact trading-day counts."""

    def test_no_overlap_keeps_all(self):
        rows = [
            _row("2330", date(2024, 1, 2)),
            _row("2454", date(2024, 1, 2)),
            _row("2330", date(2024, 3, 1)),  # ~42 tdays >> 20 → kept
        ]
        result = _dedup_cohort(rows, n_trading_days=20, market_calendar=_TEST_CAL)
        assert len(result) == 3

    def test_within_cooldown_drops_second(self):
        rows = [
            _row("2330", date(2024, 1, 2)),
            _row("2330", date(2024, 1, 15)),  # 9 tdays < 20 → dropped
        ]
        result = _dedup_cohort(rows, n_trading_days=20, market_calendar=_TEST_CAL)
        assert len(result) == 1
        assert result[0]["trade_date"] == "2024-01-02"  # earliest kept

    def test_exactly_at_boundary_kept(self):
        # Jan 2 → Jan 30 = exactly 20 Mon-Fri tdays → kept (boundary)
        rows = [
            _row("2330", date(2024, 1, 2)),
            _row("2330", date(2024, 1, 30)),
        ]
        result = _dedup_cohort(rows, n_trading_days=20, market_calendar=_TEST_CAL)
        assert len(result) == 2

    def test_one_below_boundary_dropped(self):
        # Jan 2 → Jan 29 = 19 Mon-Fri tdays → dropped
        rows = [
            _row("2330", date(2024, 1, 2)),
            _row("2330", date(2024, 1, 29)),
        ]
        result = _dedup_cohort(rows, n_trading_days=20, market_calendar=_TEST_CAL)
        assert len(result) == 1

    def test_different_stocks_independent(self):
        rows = [
            _row("2330", date(2024, 1, 2)),
            _row("2454", date(2024, 1, 3)),  # different stock, not affected
            _row("2330", date(2024, 1, 5)),  # same stock, 3 tdays < 20 → dropped
        ]
        result = _dedup_cohort(rows, n_trading_days=20, market_calendar=_TEST_CAL)
        stock_ids = [r["stock_id"] for r in result]
        assert stock_ids.count("2330") == 1
        assert stock_ids.count("2454") == 1

    def test_chain_dedup_three_signals(self):
        """Jan 2 kept → Jan 10 (5 tdays) dropped → Feb 5 (24 tdays) kept → Feb 10 (4 tdays) dropped."""
        rows = [
            _row("2330", date(2024, 1, 2)),
            _row("2330", date(2024, 1, 10)),
            _row("2330", date(2024, 2, 5)),
            _row("2330", date(2024, 2, 10)),  # Sat — 4 tdays < 20
        ]
        result = _dedup_cohort(rows, n_trading_days=20, market_calendar=_TEST_CAL)
        kept_dates = [r["trade_date"] for r in result]
        assert "2024-01-02" in kept_dates
        assert "2024-02-05" in kept_dates
        assert len(result) == 2


# ── _summary_stats cohort isolation ─────────────────────────

class TestSummaryStatsDedup:
    def _make_rows(self):
        """
        Stock A appears 5 times, each 5 days apart (Jan 2, 7, 12, 17, 22).
        Via Mon-Fri calendar: Jan7 is Sun, so spans are 3/8/11/14 tdays — all < 20.
        Only the first A signal is kept; Stock B (once) always kept → n_dedup_20 = 2.
        """
        base = date(2024, 1, 2)
        rows = []
        for i in range(5):
            rows.append(_row("A", base + timedelta(days=5 * i), alpha_20=2.0))
        rows.append(_row("B", base, alpha_20=-1.0))
        return rows

    def test_raw_n_counts_all_buy_rows(self):
        rows = self._make_rows()
        stats = _summary_stats(rows, market_calendar=_TEST_CAL)
        assert stats["n_raw"] == 6

    def test_20d_dedup_n_reduced(self):
        rows = self._make_rows()
        stats = _summary_stats(rows, market_calendar=_TEST_CAL)
        # A: 5 signals but only 1 kept; B: 1 kept → dedup_20 = 2
        assert stats["n_dedup_20"] == 2

    def test_20d_stats_use_dedup_sample(self):
        """With Raw N=6 the stats would be +2,+2,+2,+2,+2,−1 → avg=1.5, wr=83%.
        With 20D Dedup (A once + B once): avg=(2−1)/2=0.5, wr=50%."""
        rows = self._make_rows()
        stats = _summary_stats(rows, market_calendar=_TEST_CAL)
        s20 = stats["s20"]
        assert s20["n"] == 2
        assert abs(s20["avg_alpha"] - 0.5) < 0.01, f"Expected 0.5 got {s20['avg_alpha']}"
        assert s20["winrate"] == 50.0

    def test_60d_dedup_n_leq_20d_dedup_n(self):
        """60D Dedup is always a subset of (or equal to) 20D Dedup."""
        rows = self._make_rows()
        stats = _summary_stats(rows, market_calendar=_TEST_CAL)
        assert stats["n_dedup_60"] <= stats["n_dedup_20"]

    def test_empty_rows_returns_zero_n(self):
        stats = _summary_stats([], market_calendar=_TEST_CAL)
        assert stats["n_raw"] == 0
        assert stats["s20"]["n"] == 0
        assert stats["s60"]["n"] == 0

    def test_ci95_none_when_only_one_sample(self):
        rows = [_row("A", date(2024, 1, 2), alpha_20=1.0)]
        stats = _summary_stats(rows, market_calendar=_TEST_CAL)
        assert stats["s20"]["ci95"] is None

    def test_ci95_present_with_two_samples(self):
        rows = [
            _row("A", date(2024, 1, 2), alpha_20=2.0),
            _row("B", date(2024, 1, 2), alpha_20=0.0),
        ]
        stats = _summary_stats(rows, market_calendar=_TEST_CAL)
        assert stats["s20"]["ci95"] is not None
        assert stats["s20"]["ci95"] > 0


# ── _stats_block separate denominators ────────────────────────

def _matured_row(alpha: float, outcome: str | None) -> dict:
    """Minimal row dict for _stats_block tests."""
    return {"alpha_20d": alpha, "outcome_note": outcome}


class TestStatsBlockDenominators:
    """Alpha stats use alpha_n; outcome rates use outcome_n.
    Rows with alpha but no outcome_note are excluded from outcome denominator."""

    def test_alpha_n_counts_rows_with_alpha(self):
        rows = [
            _matured_row(1.0, "EXPIRED"),
            _matured_row(2.0, "T1_HIT"),
            _matured_row(-1.0, None),    # alpha set, outcome unknown
        ]
        result = _stats_block(rows, "alpha_20d")
        assert result["n"] == 3          # all three have alpha

    def test_outcome_n_excludes_null_outcome(self):
        rows = [
            _matured_row(1.0, "EXPIRED"),
            _matured_row(2.0, "T1_HIT"),
            _matured_row(-1.0, None),    # alpha set, outcome unknown
        ]
        result = _stats_block(rows, "alpha_20d")
        assert result["n_outcome"] == 2  # only EXPIRED + T1_HIT

    def test_t1_rate_uses_outcome_n(self):
        # 1 T1_HIT out of 2 rows with outcome → 50%
        # But if n were used (3): 33%
        rows = [
            _matured_row(1.0, "T1_HIT"),
            _matured_row(-1.0, "STOP_TRIGGERED"),
            _matured_row(0.5, None),   # alpha present, outcome unknown
        ]
        result = _stats_block(rows, "alpha_20d")
        assert result["n"] == 3
        assert result["n_outcome"] == 2
        assert result["t1_rate"] == 50.0   # 1/2 not 1/3

    def test_stop_rate_uses_outcome_n(self):
        rows = [
            _matured_row(1.0, "T1_HIT"),
            _matured_row(-1.0, "STOP_TRIGGERED"),
            _matured_row(0.5, None),
        ]
        result = _stats_block(rows, "alpha_20d")
        assert result["stop_rate"] == 50.0  # 1/2 not 1/3

    def test_outcome_n_zero_returns_none_rates(self):
        rows = [
            _matured_row(1.0, None),
            _matured_row(2.0, None),
        ]
        result = _stats_block(rows, "alpha_20d")
        assert result["n"] == 2
        assert result["n_outcome"] == 0
        assert result["t1_rate"] is None
        assert result["stop_rate"] is None
        assert result["ambiguous_rate"] is None

    def test_winrate_uses_alpha_n(self):
        # 2 positive, 1 negative, all have outcomes → winrate = 2/3
        rows = [
            _matured_row(1.0, "T1_HIT"),
            _matured_row(2.0, "EXPIRED"),
            _matured_row(-1.0, "STOP_TRIGGERED"),
        ]
        result = _stats_block(rows, "alpha_20d")
        assert result["n"] == 3
        assert abs(result["winrate"] - 66.7) < 0.1
