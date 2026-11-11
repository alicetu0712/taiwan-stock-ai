"""
Session 71 — Bundle A Acceptance Tests

Maps to Session 70 acceptance test plan (docs/session70_acceptance_test_plan.md).
Tests are offline-only: no DB writes, no Provider HTTP, no Streamlit rendering.
Streamlit st.markdown calls are captured via mock.

Authorization: AUTH-S71-BUNDLE-A
"""

from __future__ import annotations

import ast
from datetime import date, timedelta
from unittest.mock import MagicMock, patch


# ── L1: Contract Unit Tests ───────────────────────────────────────────────────


class TestDataFreshnessContract:
    """TC-C01 through TC-C04: DataFreshnessContract staleness classification."""

    def test_tc_c01_staleness_days_stale_multi(self):
        """TC-C01: 2026-11-05 from baseline → positive staleness (data is stale)."""
        from dashboard.components import _staleness_days

        lag = _staleness_days("2026-11-05")
        # As of 2026-11-11 this is 6 calendar days; always > 0 going forward
        assert lag > 0, f"Expected positive staleness, got {lag}"

    def test_tc_c01_staleness_days_today_is_zero(self):
        """TC-C01: today → 0 (current)."""
        from dashboard.components import _staleness_days

        assert _staleness_days(date.today()) == 0

    def test_tc_c01_staleness_days_none_is_unknown(self):
        """TC-C01: None → -1 (unknown)."""
        from dashboard.components import _staleness_days

        assert _staleness_days(None) == -1

    def test_tc_c01_staleness_days_future_is_zero(self):
        """TC-C01: future date → 0 (not stale)."""
        from dashboard.components import _staleness_days

        future = date.today() + timedelta(days=30)
        assert _staleness_days(future) == 0

    def test_tc_c02_build_freshness_label_current(self):
        """TC-C02: staleness_days=0 → current indicator."""
        with patch("streamlit.markdown") as mock_md:
            from dashboard.components import data_freshness_banner

            data_freshness_banner(date.today(), staleness_days=0, source_label="K 線")
            assert mock_md.called
            html_arg = mock_md.call_args[0][0]
            assert "✓" in html_arg or "fr-current" in html_arg

    def test_tc_c02_build_freshness_label_stale(self):
        """TC-C02: staleness_days=5 → stale indicator."""
        with patch("streamlit.markdown") as mock_md:
            from dashboard.components import data_freshness_banner

            data_freshness_banner("2026-11-05", staleness_days=5, source_label="K 線")
            assert mock_md.called
            html_arg = mock_md.call_args[0][0]
            assert "⚠" in html_arg or "fr-stale" in html_arg or "落後" in html_arg

    def test_tc_c03_is_display_compliant_t2(self):
        """TC-C03: T2 看盤 — chart_freshness_header does not raise on valid input."""
        with patch("streamlit.markdown"):
            from dashboard.components import chart_freshness_header

            # Must not raise with valid chart_max_date
            chart_freshness_header("2026-11-05", "2026-11-05")

    def test_tc_c03_research_banner_callable(self):
        """TC-C03: research_only_banner does not raise."""
        with patch("streamlit.markdown"):
            from dashboard.components import research_only_banner

            research_only_banner(protocol_version="v8.0", cutoff_date="2026-10-09")

    def test_tc_c04_eod_price_ssot_in_chart_header(self):
        """TC-C04: chart_freshness_header renders chart max date, not today."""
        rendered_calls = []
        with patch("streamlit.markdown", side_effect=lambda html, **kw: rendered_calls.append(html)):
            from dashboard.components import chart_freshness_header

            chart_freshness_header("2026-11-05", None)

        assert rendered_calls, "No st.markdown call made"
        combined = " ".join(rendered_calls)
        # Must contain the specific date, not just "today"
        assert "2026-11-05" in combined, f"Chart date not in output: {combined[:200]}"
        # Must contain EOD label
        assert "EOD" in combined or "收盤" in combined, f"EOD label missing: {combined[:200]}"


# ── Edge Case Tests ───────────────────────────────────────────────────────────


class TestEdgeCases:
    """TC-EC01 through TC-EC04."""

    def test_tc_ec01_empty_data_no_crash(self):
        """TC-EC01: None chart_max_date → Unknown-safe, no exception."""
        with patch("streamlit.markdown") as mock_md:
            from dashboard.components import chart_freshness_header

            chart_freshness_header(None, None)  # Must not raise
            assert mock_md.called
            html = mock_md.call_args[0][0]
            assert "未確認" in html or "unknown" in html.lower() or "fr-unknown" in html

    def test_tc_ec01_none_freshness_banner_no_crash(self):
        """TC-EC01: None as_of_date → 'unknown' text, no exception."""
        with patch("streamlit.markdown") as mock_md:
            from dashboard.components import data_freshness_banner

            data_freshness_banner(None)
            assert mock_md.called
            html = mock_md.call_args[0][0]
            assert "未確認" in html or "fr-unknown" in html

    def test_tc_ec02_eod_badge_not_live(self):
        """TC-EC02: eod_disclaimer_badge renders EOD label, not live."""
        with patch("streamlit.markdown") as mock_md:
            from dashboard.components import eod_disclaimer_badge

            eod_disclaimer_badge()
            assert mock_md.called
            html = mock_md.call_args[0][0]
            assert "EOD" in html
            assert "即時" not in html.replace("非即時", "")  # "非即時" is OK, "即時" alone is not

    def test_tc_ec03_string_date_handled(self):
        """TC-EC03: string date input handled same as date object."""
        from dashboard.components import _staleness_days

        d_obj = date(2026, 11, 5)
        d_str = "2026-11-05"
        assert _staleness_days(d_obj) == _staleness_days(d_str)

    def test_tc_ec04_research_cutoff_not_shown_as_stale(self):
        """TC-EC04: research_only_banner should NOT show staleness warning for cutoff."""
        rendered = []
        with patch("streamlit.markdown", side_effect=lambda html, **kw: rendered.append(html)):
            from dashboard.components import research_only_banner

            research_only_banner(protocol_version="v8.0", cutoff_date="2026-10-09")

        combined = " ".join(rendered)
        # Should show "研究截止" framing, NOT "落後 N 天"
        assert "研究截止" in combined or "2026-10-09" in combined
        assert "落後" not in combined, f"'落後' should not appear in research banner: {combined[:300]}"


# ── UI Contract Tests (import and structure) ──────────────────────────────────


class TestUIContracts:
    """TC-UI01 through TC-UI06: file-level contract verification."""

    def test_tc_ui01_t2_has_chart_freshness_header_import(self):
        """TC-UI01: market_watch.py imports and calls chart_freshness_header."""
        with open("dashboard/_pages/market_watch.py") as f:
            src = f.read()
        assert "chart_freshness_header" in src
        assert "dashboard.components" in src

    def test_tc_ui01_t2_uses_price_df_max_not_today(self):
        """TC-UI01: chart max date must come from price_df, not date.today()."""
        with open("dashboard/_pages/market_watch.py") as f:
            src = f.read()
        # chart_freshness_header call must reference price_df, not date.today()
        assert 'price_df["date"].max()' in src
        # The variable name passed should be the stock-specific max
        assert "_chart_max_date" in src

    def test_tc_ui02_t2_eod_label_via_component(self):
        """TC-UI02: T2 uses chart_freshness_header which includes EOD badge."""
        # The chart_freshness_header always adds 'EOD · 非即時' in its output
        rendered = []
        with patch("streamlit.markdown", side_effect=lambda html, **kw: rendered.append(html)):
            from dashboard.components import chart_freshness_header
            chart_freshness_header("2026-11-05", None)
        combined = " ".join(rendered)
        assert "EOD" in combined
        assert "非即時" in combined

    def test_tc_ui03_t0_has_persistent_freshness_anchor(self):
        """TC-UI03: overview.py has freshness anchor that shows regardless of days_old."""
        with open("dashboard/_pages/overview.py") as f:
            src = f.read()
        # Must call data_freshness_banner (always visible)
        assert "data_freshness_banner(" in src
        # Must still preserve the existing conditional freshness_html
        assert "freshness_html" in src
        assert "days_old > 1" in src

    def test_tc_ui04_t5_has_research_banner(self):
        """TC-UI04: research_backtest.py has research_only_banner at page top."""
        with open("dashboard/_pages/research_backtest.py") as f:
            src = f.read()
        assert "research_only_banner(" in src
        # Must be before the page's title HTML (early in page_research_backtest)
        rb_start = src.index("def page_research_backtest")
        rb_banner = src.index("research_only_banner(", rb_start)
        rb_html = src.index("st.html(", rb_start)
        assert rb_banner < rb_html, "research_only_banner must appear before page HTML"

    def test_tc_ui04_t6_has_research_banner(self):
        """TC-UI04: entry_timing_research.py has research_only_banner."""
        with open("dashboard/_pages/entry_timing_research.py") as f:
            src = f.read()
        assert "research_only_banner(" in src

    def test_tc_ui05_sidebar_has_staleness_color(self):
        """TC-UI05: app.py sidebar uses data_freshness_banner instead of plain caption."""
        with open("dashboard/app.py") as f:
            src = f.read()
        assert "data_freshness_banner(" in src
        assert "MODEL_VERSION" in src
        # Old plain caption should be gone
        assert 'st.caption(f"最新：{newest}")' not in src

    def test_tc_ui06_t1_live_monitor_unchanged(self):
        """TC-UI06: live_monitor.py is NOT modified in this session."""
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True
        )
        # live_monitor.py should NOT appear in any diff
        assert "live_monitor.py" not in result.stdout

    def test_sidebar_model_version_shown(self):
        """PART H: Sidebar shows Production Model Version."""
        with open("dashboard/app.py") as f:
            src = f.read()
        assert "正式模型" in src or "MODEL_VERSION" in src
        assert "研究結果不代表正式交易建議" in src


# ── No-Drift Safety Tests ─────────────────────────────────────────────────────


class TestNoDrift:
    """Verify no signal, model, DB, or cron changes."""

    def test_rc2_hash_unchanged(self):
        """RC-2 backfill script hash must equal the deployed RC-2 hash."""
        import hashlib

        with open("scripts/backfill_daily_prices.py", "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        expected = "4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb"
        assert actual == expected, f"RC-2 hash mismatch: {actual}"

    def test_model_version_unchanged(self):
        """MODEL_VERSION in src/database.py must still be v8.0."""
        with open("src/database.py") as f:
            src = f.read()
        assert 'MODEL_VERSION = "v8.0"' in src

    def test_build_chart_unchanged(self):
        """build_chart call in market_watch.py must not be modified."""
        with open("dashboard/_pages/market_watch.py") as f:
            src = f.read()
        assert "fig = build_chart(price_df, analysis or {}, stock_name)" in src

    def test_plotly_chart_unchanged(self):
        """st.plotly_chart call must not be modified."""
        with open("dashboard/_pages/market_watch.py") as f:
            src = f.read()
        assert '"scrollZoom": True, "displayModeBar": False' in src

    def test_no_provider_http_in_components(self):
        """components.py must not contain any HTTP calls."""
        with open("dashboard/components.py") as f:
            src = f.read()
        for forbidden in ["requests.", "urllib", "httpx", "fetch_intraday", "urlopen"]:
            assert forbidden not in src, f"Forbidden HTTP call '{forbidden}' found in components.py"

    def test_no_db_write_in_components(self):
        """components.py must not query DB or write to session state."""
        with open("dashboard/components.py") as f:
            src = f.read()
        for forbidden in ["get_session()", "sqlite3.connect", "session.add", "session.commit"]:
            assert forbidden not in src, f"Forbidden DB call '{forbidden}' found in components.py"

    def test_cron_not_modified(self):
        """hybrid_shadow_cron.py must not be modified in this session."""
        import subprocess

        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True
        )
        modified = result.stdout.strip().split("\n")
        assert not any("hybrid_shadow_cron" in f for f in modified), \
            "cron script was modified!"

    def test_components_syntax_valid(self):
        """All new/modified files must parse without syntax errors."""
        files = [
            "dashboard/components.py",
            "dashboard/_pages/market_watch.py",
            "dashboard/_pages/overview.py",
            "dashboard/_pages/research_backtest.py",
            "dashboard/_pages/entry_timing_research.py",
            "dashboard/app.py",
        ]
        for path in files:
            with open(path) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    assert False, f"Syntax error in {path}: {e}"

    def test_research_v2_isolation_note_preserved(self):
        """V2-specific isolation text in entry_timing_research.py must be preserved."""
        with open("dashboard/_pages/entry_timing_research.py") as f:
            src = f.read()
        assert "V2 標籤不影響正式買賣決策" in src

    def test_cutoff_label_preserved_in_research_backtest(self):
        """RESEARCH_CUTOFF_DATE label must still be defined in research_backtest.py."""
        with open("dashboard/_pages/research_backtest.py") as f:
            src = f.read()
        assert '_CUTOFF_LABEL = "2026-10-09"' in src
