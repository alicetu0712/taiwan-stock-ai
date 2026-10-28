"""tests/test_position_presenter.py — Unit tests for PositionPresenter."""

import pytest

from src.presentation.position_presenter import PositionCard, PositionPresenter


_POS = {
    "stock_id": "2330",
    "name": "台積電",
    "date_entered": "2024-01-15",
    "entry_price": 100.0,
    "target_price": 120.0,
    "stop_loss_price": 90.0,
    "target_pct": 20.0,
    "stop_loss_pct": -10.0,
    "position_pct": 20.0,
    "rec_level": "A",
    "rec_score": 85.0,
    "rationale": "突破整理區",
    "status": "active",
    "exit_date": None,
    "exit_price": None,
    "exit_reason": None,
    "pnl_pct": None,
    "mc_result": None,
}


class TestPositionPresenterPresent:
    def test_returns_position_card(self):
        p = PositionPresenter()
        card = p.present(_POS, 110.0)
        assert isinstance(card, PositionCard)

    def test_pnl_positive(self):
        card = PositionPresenter().present(_POS, 110.0)
        assert card.pnl == pytest.approx(10.0)
        assert card.pnl_str == "+10.0%"
        assert card.pnl_icon == "🟢"
        assert card.pnl_color == "#00897b"

    def test_pnl_negative(self):
        card = PositionPresenter().present(_POS, 95.0)
        assert card.pnl == pytest.approx(-5.0)
        assert card.pnl_str == "-5.0%"
        assert card.pnl_icon == "🔴"
        assert card.pnl_color == "#e53935"

    def test_pnl_none_when_no_price(self):
        card = PositionPresenter().present(_POS, None)
        assert card.pnl is None
        assert card.pnl_str == "—"
        assert card.pnl_icon == "🟢"  # default: (None or 0) >= 0

    def test_price_label_with_price(self):
        card = PositionPresenter().present(_POS, 110.0)
        assert card.price_label == "NT$ 110.00"

    def test_price_label_no_price(self):
        card = PositionPresenter().present(_POS, None)
        assert card.price_label == "尚無即時報價"

    def test_price_html_contains_price_and_pnl(self):
        card = PositionPresenter().present(_POS, 110.0)
        assert "110.00" in card.price_html
        assert "+10.0%" in card.price_html

    def test_summary_caption_full(self):
        card = PositionPresenter().present(_POS, 110.0)
        assert "倉位 20%" in card.summary_caption
        assert "A級" in card.summary_caption
        assert "建倉 2024-01-15" in card.summary_caption

    def test_summary_caption_no_position_pct(self):
        pos = {**_POS, "position_pct": None}
        card = PositionPresenter().present(pos, 110.0)
        assert "倉位" not in card.summary_caption
        assert "A級" in card.summary_caption

    def test_summary_caption_default_level(self):
        pos = {**_POS, "rec_level": None}
        card = PositionPresenter().present(pos, 110.0)
        assert "B級" in card.summary_caption

    def test_progress_html_present(self):
        card = PositionPresenter().present(_POS, 110.0)
        assert len(card.progress_html) > 0
        assert "進場 100.0" in card.progress_html


class TestPositionProgressHtml:
    def _html(self, entry, stop, target, curr):
        return PositionPresenter._position_progress_html(entry, stop, target, curr)

    def test_no_entry_returns_empty(self):
        assert self._html(None, 90.0, 120.0, 110.0) == ""

    def test_curr_above_entry_green(self):
        html = self._html(100.0, 90.0, 120.0, 110.0)
        assert "#43a047" in html

    def test_curr_between_stop_and_entry_orange(self):
        html = self._html(100.0, 90.0, 120.0, 95.0)
        assert "#f57f17" in html

    def test_curr_below_stop_red(self):
        html = self._html(100.0, 90.0, 120.0, 88.0)
        assert "#e53935" in html

    def test_curr_none_grey(self):
        html = self._html(100.0, 90.0, 120.0, None)
        assert "#90a4ae" in html

    def test_labels_in_html(self):
        html = self._html(100.0, 90.0, 120.0, 110.0)
        assert "停損 90.0" in html
        assert "進場 100.0" in html
        assert "現價 110.0" in html
        assert "目標 120.0" in html

    def test_no_stop_still_renders(self):
        html = self._html(100.0, None, 120.0, 110.0)
        assert "進場 100.0" in html
        assert "目標 120.0" in html

    def test_no_target_still_renders(self):
        html = self._html(100.0, 90.0, None, 95.0)
        assert "進場 100.0" in html
        assert "停損 90.0" in html
