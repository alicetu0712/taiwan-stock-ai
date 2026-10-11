"""
test_scorecard.py — Overlapping Samples dedup 邏輯測試

核心驗證：
  - _dedup_cohort 正確去除同一股票在冷卻期內的重複訊號
  - _summary_stats 的 20D 和 60D 統計使用各自的 Dedup 樣本，而非 Raw N
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard._pages.scorecard import (
    _DEDUP_20_DAYS,
    _DEDUP_60_DAYS,
    _dedup_cohort,
    _summary_stats,
)


# ── helpers ───────────────────────────────────────────────────

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
    def test_no_overlap_keeps_all(self):
        rows = [
            _row("2330", date(2024, 1, 2)),
            _row("2454", date(2024, 1, 2)),
            _row("2330", date(2024, 3, 1)),  # 59 days later — beyond 28d window
        ]
        result = _dedup_cohort(rows, cooldown_calendar_days=28)
        assert len(result) == 3

    def test_within_cooldown_drops_second(self):
        rows = [
            _row("2330", date(2024, 1, 2)),
            _row("2330", date(2024, 1, 15)),  # 13 days later — within 28d cooldown
        ]
        result = _dedup_cohort(rows, cooldown_calendar_days=28)
        assert len(result) == 1
        assert result[0]["trade_date"] == "2024-01-02"  # earliest kept

    def test_exactly_at_boundary_kept(self):
        rows = [
            _row("2330", date(2024, 1, 2)),
            _row("2330", date(2024, 1, 30)),  # exactly 28 days later — kept
        ]
        result = _dedup_cohort(rows, cooldown_calendar_days=28)
        assert len(result) == 2

    def test_different_stocks_independent(self):
        rows = [
            _row("2330", date(2024, 1, 2)),
            _row("2454", date(2024, 1, 3)),  # different stock, not affected
            _row("2330", date(2024, 1, 5)),  # same stock, within cooldown
        ]
        result = _dedup_cohort(rows, cooldown_calendar_days=28)
        stock_ids = [r["stock_id"] for r in result]
        assert stock_ids.count("2330") == 1
        assert stock_ids.count("2454") == 1

    def test_chain_dedup_three_signals(self):
        """First kept → second dropped → third kept (28+ days after first)."""
        rows = [
            _row("2330", date(2024, 1, 2)),   # kept
            _row("2330", date(2024, 1, 10)),  # dropped (8 days)
            _row("2330", date(2024, 2, 5)),   # kept (34 days from Jan 2)
            _row("2330", date(2024, 2, 10)),  # dropped (5 days from Feb 5)
        ]
        result = _dedup_cohort(rows, cooldown_calendar_days=28)
        kept_dates = [r["trade_date"] for r in result]
        assert "2024-01-02" in kept_dates
        assert "2024-02-05" in kept_dates
        assert len(result) == 2


# ── _summary_stats cohort isolation ─────────────────────────

class TestSummaryStatsDedup:
    def _make_rows(self):
        """
        Stock A appears 5 times, each 5 days apart (Jan 2, 7, 12, 17, 22).
        Max span = 20 calendar days < 28d cooldown → dedup keeps only the first.
        Stock B appears once on Jan 2 → always kept.
        """
        base = date(2024, 1, 2)
        rows = []
        # 5 A signals, 5 days apart — all fall within 28d of the first
        for i in range(5):
            rows.append(_row("A", base + timedelta(days=5 * i), alpha_20=2.0))
        # 1 B signal
        rows.append(_row("B", base, alpha_20=-1.0))
        return rows

    def test_raw_n_counts_all_buy_rows(self):
        rows = self._make_rows()
        stats = _summary_stats(rows)
        assert stats["n_raw"] == 6

    def test_20d_dedup_n_reduced(self):
        rows = self._make_rows()
        stats = _summary_stats(rows)
        # A: 5 signals but only 1 kept; B: 1 kept → dedup_20 = 2
        assert stats["n_dedup_20"] == 2

    def test_20d_stats_use_dedup_sample(self):
        """With Raw N=6 the stats would be +2,+2,+2,+2,+2,−1 → avg=1.5, wr=83%.
        With 20D Dedup (A once + B once): avg=(2−1)/2=0.5, wr=50%."""
        rows = self._make_rows()
        stats = _summary_stats(rows)
        s20 = stats["s20"]
        assert s20["n"] == 2
        assert abs(s20["avg_alpha"] - 0.5) < 0.01, f"Expected 0.5 got {s20['avg_alpha']}"
        assert s20["winrate"] == 50.0

    def test_60d_dedup_n_leq_20d_dedup_n(self):
        """60D Dedup is always a subset of (or equal to) 20D Dedup."""
        rows = self._make_rows()
        stats = _summary_stats(rows)
        assert stats["n_dedup_60"] <= stats["n_dedup_20"]

    def test_empty_rows_returns_zero_n(self):
        stats = _summary_stats([])
        assert stats["n_raw"] == 0
        assert stats["s20"]["n"] == 0
        assert stats["s60"]["n"] == 0

    def test_ci95_none_when_only_one_sample(self):
        rows = [_row("A", date(2024, 1, 2), alpha_20=1.0)]
        stats = _summary_stats(rows)
        # 1 matured sample → CI cannot be computed
        assert stats["s20"]["ci95"] is None

    def test_ci95_present_with_two_samples(self):
        rows = [
            _row("A", date(2024, 1, 2), alpha_20=2.0),
            _row("B", date(2024, 1, 2), alpha_20=0.0),
        ]
        stats = _summary_stats(rows)
        assert stats["s20"]["ci95"] is not None
        assert stats["s20"]["ci95"] > 0
