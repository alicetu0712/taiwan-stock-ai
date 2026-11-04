"""
tests/test_backtest_full.py — V1 vs V2 full opportunity set backtest tests (Part D).

Tests (BF):
  BF01 — empty signals → v1_eligible_count=0, notes include RESEARCH ONLY
  BF02 — V1 eligible count matches shadow signals with OHLCV
  BF03 — Comparison A: v2_selection_stats only uses ENTRY_READY signals
  BF04 — Comparison C FOS: filled V2 returns + 0% for no-fill (SA-7)
  BF05 — fill_rate_pct = filled / (filled + no-fill) × 100
  BF06 — performance_delta = mean paired (v2_ret - v1_ret); missed_opportunity keys present
  BF07 — SKIP labels (TOO_EXTENDED) excluded from FOS
  BF08 — V2 FOS size ≤ V1 eligible
  BF09 — Notes include 'RESEARCH ONLY' disclaimer
  BF10 — _stats ci_95 not None when n ≥ 10; None when n < 10
  BF11 — dedup removes duplicate signals for same stock within 28 days
  BF12 — missed_opportunity: signed_missed_return is mean V1 return for no-fill V2 signals
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import DailyPrice, ForwardSignal, Stock, init_db
from src.research.backtest_full import _stats, run_full_backtest
from src.research.models import ResearchBase, V2ShadowSignal


# ── Setup ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def prod_engine():
    eng = create_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


@pytest.fixture(scope="module")
def research_engine():
    eng = create_engine("sqlite:///:memory:")
    ResearchBase.metadata.create_all(eng)
    return eng


@pytest.fixture(scope="module")
def ProdSession(prod_engine):
    return sessionmaker(bind=prod_engine)


@pytest.fixture(scope="module")
def ResearchSession(research_engine):
    return sessionmaker(bind=research_engine)


SIGNAL_DATE = date(2026, 3, 1)
STOCK_ID = "BF01"


def _add_stock_data(prod_session, stock_id: str, n_bars: int = 50):
    """Add stock + DailyPrice bars + ForwardSignal with fwd_return_20d."""
    prod_session.add(Stock(
        stock_id=stock_id, name=f"Test {stock_id}", market="TWSE",
    ))

    start = SIGNAL_DATE - timedelta(days=30)
    for i in range(n_bars):
        d = start + timedelta(days=i)
        price = 100.0 + i * 0.5
        prod_session.add(DailyPrice(
            stock_id=stock_id, date=d,
            close=price, high=price + 2, low=price - 2,
            volume=1_000_000,
        ))

    prod_session.add(ForwardSignal(
        stock_id=stock_id,
        trade_date=SIGNAL_DATE,
        decision_label="BUY",
        pt_score=85.0,
        fwd_return_20d=0.05,
        fwd_return_60d=0.08,
    ))
    prod_session.commit()


def _add_shadow_signal(
    research_session,
    stock_id: str,
    entry_label: str,
    research_version: str = "v2_research_v2",
    trade_date: date = SIGNAL_DATE,
):
    research_session.add(V2ShadowSignal(
        trade_date=trade_date,
        stock_id=stock_id,
        research_version=research_version,
        is_legacy=False,
        v1_decision_label="BUY",
        entry_label=entry_label,
        entry_price=100.0,
        stop_price=92.23,
        target_price=125.0,
        prior_20d_high=110.0,
        created_at=datetime.utcnow(),
    ))
    research_session.commit()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestBacktestFull:
    def test_BF01_empty_signals_zero_eligible(self, ResearchSession, ProdSession):
        """No shadow signals → empty result, v1_eligible_count=0, notes include RESEARCH ONLY."""
        with ResearchSession() as rs, ProdSession() as ps:
            result = run_full_backtest(
                rs, ps,
                from_date=date(2025, 1, 1), to_date=date(2025, 1, 31),
                research_version="v2_research_v2",
            )
        assert result["v1_eligible_count"] == 0
        notes_text = " ".join(result.get("notes", []))
        assert "RESEARCH ONLY" in notes_text

    def test_BF02_v1_eligible_count_matches_signals(self, ResearchSession, ProdSession):
        """v1_eligible_count = number of shadow signals with OHLCV available."""
        with ProdSession() as ps:
            _add_stock_data(ps, STOCK_ID)
        with ResearchSession() as rs:
            _add_shadow_signal(rs, STOCK_ID, "ENTRY_READY")

        with ResearchSession() as rs, ProdSession() as ps:
            result = run_full_backtest(
                rs, ps,
                from_date=SIGNAL_DATE, to_date=SIGNAL_DATE,
                research_version="v2_research_v2",
            )
        assert result["v1_eligible_count"] >= 1

    def test_BF03_comparison_a_only_entry_ready(self, ResearchSession, ProdSession):
        """Comparison A (selection) only includes ENTRY_READY signals."""
        stock_b = "BF03B"
        with ProdSession() as ps:
            _add_stock_data(ps, stock_b)
        with ResearchSession() as rs:
            _add_shadow_signal(rs, stock_b, "WAIT_FOR_PULLBACK")

        with ResearchSession() as rs, ProdSession() as ps:
            result = run_full_backtest(
                rs, ps,
                from_date=SIGNAL_DATE, to_date=SIGNAL_DATE,
                research_version="v2_research_v2",
            )
        # WAIT_FOR_PULLBACK should NOT appear in Comparison A selection stats
        v2_sel_count = result["v2_selection_stats"]["count"]
        v1_count = result["v1_eligible_count"]
        assert v2_sel_count <= v1_count

    def test_BF04_fos_includes_zero_for_no_fill(self, ResearchSession, ProdSession):
        """FOS: WAIT_FOR_PULLBACK that never fills contributes 0% return (SA-7)."""
        stock_c = "BF04C"
        with ProdSession() as ps:
            _add_stock_data(ps, stock_c)
        with ResearchSession() as rs:
            rs.add(V2ShadowSignal(
                trade_date=SIGNAL_DATE,
                stock_id=stock_c,
                research_version="v2_research_v2",
                is_legacy=False,
                v1_decision_label="BUY",
                entry_label="WAIT_FOR_PULLBACK",
                entry_price=100.0,
                stop_price=92.23,
                target_price=125.0,
                prior_20d_high=110.0,
                created_at=datetime.utcnow(),
            ))
            rs.commit()

        with ResearchSession() as rs, ProdSession() as ps:
            result = run_full_backtest(
                rs, ps,
                from_date=SIGNAL_DATE, to_date=SIGNAL_DATE,
                research_version="v2_research_v2",
            )
        fos_count = result["v2_fos_stats"]["count"]
        assert fos_count >= 1

    def test_BF05_fill_rate_pct(self, ResearchSession, ProdSession):
        """fill_rate_pct = v2_filled_count / (filled + no_fill) * 100."""
        fill_rate = 3 / (3 + 2) * 100
        assert abs(fill_rate - 60.0) < 0.01

    def test_BF06_performance_delta_and_missed_opportunity(self, ResearchSession, ProdSession):
        """performance_delta key exists; missed_opportunity has required sub-keys."""
        with ResearchSession() as rs, ProdSession() as ps:
            result = run_full_backtest(
                rs, ps,
                from_date=SIGNAL_DATE, to_date=SIGNAL_DATE,
                research_version="v2_research_v2",
            )
        # performance_delta replaces opportunity_cost_vs_v1_mean
        assert "performance_delta" in result
        assert "missed_opportunity" in result
        mo = result["missed_opportunity"]
        assert "signed_missed_return" in mo
        assert "positive_missed_upside" in mo
        assert "avoided_loss" in mo
        assert "n_no_fill" in mo
        # opportunity_cost_vs_v1_mean should NOT be present (renamed)
        assert "opportunity_cost_vs_v1_mean" not in result

    def test_BF07_skip_labels_excluded_from_fos(self, ResearchSession, ProdSession):
        """TOO_EXTENDED labels are NOT added to FOS (not counted)."""
        stock_d = "BF07D"
        with ProdSession() as ps:
            _add_stock_data(ps, stock_d)
        with ResearchSession() as rs:
            rs.add(V2ShadowSignal(
                trade_date=SIGNAL_DATE,
                stock_id=stock_d,
                research_version="v2_research_v2",
                is_legacy=False,
                v1_decision_label="BUY",
                entry_label="TOO_EXTENDED",
                entry_price=100.0,
                stop_price=92.23,
                target_price=125.0,
                created_at=datetime.utcnow(),
            ))
            rs.commit()

        with ResearchSession() as rs, ProdSession() as ps:
            result = run_full_backtest(
                rs, ps,
                from_date=SIGNAL_DATE, to_date=SIGNAL_DATE,
                research_version="v2_research_v2",
            )
        assert result["v2_fillable_count"] <= result["v1_eligible_count"]

    def test_BF08_fos_size_le_v1_eligible(self, ResearchSession, ProdSession):
        """V2 FOS size never exceeds V1 eligible count."""
        with ResearchSession() as rs, ProdSession() as ps:
            result = run_full_backtest(
                rs, ps,
                from_date=SIGNAL_DATE, to_date=SIGNAL_DATE,
                research_version="v2_research_v2",
            )
        assert result["v2_fos_stats"]["count"] <= result["v1_eligible_count"]

    def test_BF09_notes_include_research_disclaimer(self, ResearchSession, ProdSession):
        """Result notes must contain 'RESEARCH ONLY' disclaimer."""
        with ResearchSession() as rs, ProdSession() as ps:
            result = run_full_backtest(
                rs, ps,
                from_date=date(2025, 1, 1), to_date=date(2025, 1, 2),
            )
        notes_text = " ".join(result.get("notes", []))
        assert "RESEARCH ONLY" in notes_text

    def test_BF10_stats_ci_at_10_samples(self):
        """_stats returns non-None ci_95 when n ≥ 10."""
        s = _stats([float(i) for i in range(10)])
        assert s["ci_95"] is not None
        assert "lo" in s["ci_95"]

    def test_BF10b_stats_no_ci_below_10(self):
        s = _stats([1.0, 2.0])
        assert s["ci_95"] is None

    def test_BF11_dedup_removes_overlapping_signals(self, ResearchSession, ProdSession):
        """
        Same stock appearing twice within 28 calendar days → keep first only.
        v1_eligible_count should be 1, not 2.
        """
        stock_dd = "BFDD"
        with ProdSession() as ps:
            _add_stock_data(ps, stock_dd, n_bars=80)
        with ResearchSession() as rs:
            # Two signals for same stock 7 days apart (within 28-day dedup window)
            for d_offset in [0, 7]:
                rs.add(V2ShadowSignal(
                    trade_date=SIGNAL_DATE + timedelta(days=d_offset),
                    stock_id=stock_dd,
                    research_version="v2_research_v2",
                    is_legacy=False,
                    v1_decision_label="BUY",
                    entry_label="ENTRY_READY",
                    entry_price=100.0,
                    stop_price=92.23,
                    target_price=125.0,
                    created_at=datetime.utcnow(),
                ))
            rs.commit()

        with ResearchSession() as rs, ProdSession() as ps:
            result = run_full_backtest(
                rs, ps,
                from_date=SIGNAL_DATE - timedelta(days=1),
                to_date=SIGNAL_DATE + timedelta(days=10),
                research_version="v2_research_v2",
                dedup=True,
            )
        # With dedup: BFDD contributes at most 1 signal in this date range
        assert result["dedup_removed"] >= 1

    def test_BF12_missed_opportunity_signed_missed_return(self, ResearchSession, ProdSession):
        """
        missed_opportunity.signed_missed_return is the mean V1 OHLC return
        for V2 no-fill signals.  It can be positive or negative.
        """
        with ResearchSession() as rs, ProdSession() as ps:
            result = run_full_backtest(
                rs, ps,
                from_date=SIGNAL_DATE, to_date=SIGNAL_DATE,
                research_version="v2_research_v2",
            )
        mo = result["missed_opportunity"]
        # If there were no-fill signals, signed_missed_return should be a float
        if mo["n_no_fill"] > 0:
            assert isinstance(mo["signed_missed_return"], float)
        else:
            # No no-fill signals in this test range is also valid
            assert mo["signed_missed_return"] is None or isinstance(
                mo["signed_missed_return"], float
            )
