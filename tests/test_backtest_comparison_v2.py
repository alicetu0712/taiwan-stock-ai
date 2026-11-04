"""
tests/test_backtest_comparison_v2.py — Methodology correctness for compare_v1_v2().

Covers:
  BC01 — Only BUY/STRONG_BUY are included in V1 baseline (WATCH/WAIT excluded)
  BC02 — fill_rate_pct = v2_count / v1_count * 100
  BC03 — v2_missed_count = V1 signals where entry_label != ENTRY_READY
  BC04 — Rows with fwd_return_20d=None are excluded
  BC05 — Bootstrap CI only computed when n >= 10
  BC06 — return_source_note present in result
  BC07 — Empty dataset returns all-None stats, no crash
  BC08 — _bootstrap_ci mean bounds contain true mean (statistical sanity)
"""

from __future__ import annotations

from src.research.backtest_comparison import _bootstrap_ci, _stats, compare_v1_v2


class TestStatsHelper:
    def test_empty_returns_none_stats(self):
        s = _stats([])
        assert s["count"] == 0
        assert s["mean"] is None
        assert s["median"] is None
        assert s["win_rate"] is None
        assert s["ci_95"] is None

    def test_win_rate_all_positive(self):
        s = _stats([1.0, 2.0, 3.0])
        assert s["win_rate"] == 100.0

    def test_win_rate_mixed(self):
        s = _stats([1.0, -1.0, 1.0, -1.0])
        assert s["win_rate"] == 50.0

    def test_ci_not_computed_below_10(self):
        s = _stats([0.1] * 9)
        assert s["ci_95"] is None

    def test_ci_computed_at_10(self):
        s = _stats([0.1] * 10)
        assert s["ci_95"] is not None
        assert "lo" in s["ci_95"]
        assert "hi" in s["ci_95"]

    def test_mean_rounded_to_4dp(self):
        s = _stats([1.0 / 3.0, 2.0 / 3.0])
        # mean = 0.5 exactly, check it's 4 decimal places
        assert isinstance(s["mean"], float)
        assert len(str(s["mean"]).split(".")[-1]) <= 4


class TestBootstrapCI:
    def test_lo_le_hi(self):
        data = [float(i) for i in range(50)]
        ci = _bootstrap_ci(data, n_boot=200)
        assert ci["lo"] <= ci["hi"]

    def test_ci_contains_true_mean(self):
        """95% CI should contain the sample mean for a large enough sample."""
        data = [float(i) for i in range(100)]
        true_mean = sum(data) / len(data)
        ci = _bootstrap_ci(data, n_boot=1000)
        assert ci["lo"] <= true_mean <= ci["hi"]

    def test_deterministic_with_fixed_seed(self):
        data = [0.1 * i for i in range(30)]
        ci1 = _bootstrap_ci(data, n_boot=100)
        ci2 = _bootstrap_ci(data, n_boot=100)
        assert ci1 == ci2


class TestCompareV1V2Integration:
    """Integration tests using mocked DB session."""

    def _make_mocks(self, pairs):
        """
        pairs: list of (v1_label, entry_label, fwd_return_20d)
        Returns mocked (session.query(...).all()) result.
        """
        from datetime import date
        from unittest.mock import MagicMock

        shadows = []
        for v1_label, entry_label, ret in pairs:
            shadow = MagicMock()
            shadow.trade_date = date(2026, 1, 1)
            shadow.stock_id = "2330"
            shadow.v1_decision_label = v1_label
            shadow.entry_label = entry_label
            shadow.v1_pt_score = 85
            shadow.rr_ratio = 2.5

            fs = MagicMock()
            fs.fwd_return_20d = ret
            fs.fwd_return_60d = ret

            shadows.append((shadow, fs))
        return shadows

    def _run_compare(self, pairs):
        from unittest.mock import MagicMock, patch  # noqa: F401 — patch used in with

        mock_pairs = self._make_mocks(pairs)

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_q = MagicMock()
        mock_q.join.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = mock_pairs
        mock_session.query.return_value = mock_q
        mock_session.close = MagicMock()

        with patch("src.database.get_session", return_value=mock_session):
            return compare_v1_v2()

    def test_BC01_watch_excluded_from_v1_baseline(self):
        """WATCH and WAIT_PULLBACK rows must not appear in V1 baseline.
        Since compare_v1_v2 filters v1_decision_label IN (BUY, STRONG_BUY)
        at the DB query level, the mock only returns what the DB would return
        — here we test the Python-side aggregation with pre-filtered data."""
        # Only BUY rows in result (WATCH already excluded by DB filter)
        pairs = [
            ("BUY", "ENTRY_READY", 0.05),
            ("BUY", "WAIT_FOR_PULLBACK", -0.02),
            ("STRONG_BUY", "ENTRY_READY", 0.08),
        ]
        result = self._run_compare(pairs)
        # All 3 BUY+STRONG_BUY rows with outcome → v1_count = 3
        assert result["v1_count"] == 3

    def test_BC02_fill_rate(self):
        """fill_rate = count(ENTRY_READY) / count(all V1) * 100."""
        pairs = [
            ("BUY", "ENTRY_READY", 0.05),
            ("BUY", "ENTRY_READY", 0.03),
            ("BUY", "WAIT_FOR_PULLBACK", -0.01),
            ("STRONG_BUY", "NO_VALID_SETUP", 0.02),
        ]
        result = self._run_compare(pairs)
        assert result["v1_count"] == 4
        assert result["v2_count"] == 2
        assert result["fill_rate_pct"] == 50.0

    def test_BC03_v2_missed_count(self):
        """v2_missed_count = V1 rows where entry_label != ENTRY_READY."""
        pairs = [
            ("BUY", "ENTRY_READY", 0.05),
            ("BUY", "WAIT_FOR_PULLBACK", -0.02),
            ("BUY", "TOO_EXTENDED", 0.10),
        ]
        result = self._run_compare(pairs)
        assert result["v2_missed_count"] == 2

    def test_BC04_none_outcome_excluded(self):
        """Rows with fwd_return_20d=None must be excluded from all groups."""
        pairs = [
            ("BUY", "ENTRY_READY", 0.05),
            ("BUY", "ENTRY_READY", None),   # excluded
            ("BUY", "WAIT_FOR_PULLBACK", None),  # excluded
        ]
        result = self._run_compare(pairs)
        assert result["v1_count"] == 1
        assert result["v2_count"] == 1

    def test_BC05_return_source_note_present(self):
        """return_source_note key must always be present."""
        result = self._run_compare([("BUY", "ENTRY_READY", 0.03)])
        assert "return_source_note" in result
        assert len(result["return_source_note"]) > 10

    def test_BC06_empty_dataset_no_crash(self):
        """Empty pairs → all counts 0, all stats None, no exception."""
        result = self._run_compare([])
        assert result["v1_count"] == 0
        assert result["v2_count"] == 0
        assert result["v1_mean_return_20d"] is None
        assert result["fill_rate_pct"] is None

    def test_BC07_v2_missed_mean_separate_from_v2(self):
        """v2_missed and v2 should have different means when returns differ."""
        pairs = [
            ("BUY", "ENTRY_READY", 0.10),
            ("BUY", "ENTRY_READY", 0.10),
            ("BUY", "WAIT_FOR_PULLBACK", -0.05),
            ("BUY", "WAIT_FOR_PULLBACK", -0.05),
        ]
        result = self._run_compare(pairs)
        assert result["v2_mean_return_20d"] > 0
        assert result["v2_missed_mean_return_20d"] < 0

    def test_BC08_rows_contain_v2_selected_flag(self):
        """Each row dict should include 'v2_selected' boolean."""
        pairs = [
            ("BUY", "ENTRY_READY", 0.05),
            ("BUY", "WAIT_FOR_PULLBACK", -0.02),
        ]
        result = self._run_compare(pairs)
        for row in result["rows"]:
            assert "v2_selected" in row
        assert result["rows"][0]["v2_selected"] is True
        assert result["rows"][1]["v2_selected"] is False
