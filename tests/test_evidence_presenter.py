"""tests/test_evidence_presenter.py — Unit tests for EvidencePresenter."""

import pytest

from src.presentation.evidence_presenter import EvidencePresenter, SampleStrength


class TestSampleStrength:
    def test_returns_sample_strength(self):
        ep = EvidencePresenter()
        ss = ep.sample_strength(15)
        assert isinstance(ss, SampleStrength)

    def test_n_less_than_10_insufficient(self):
        ss = EvidencePresenter().sample_strength(9)
        assert ss.label == "不足"
        assert ss.is_insufficient is True
        assert ss.is_initial is False

    def test_n_equals_10_initial(self):
        ss = EvidencePresenter().sample_strength(10)
        assert ss.label == "初步觀察"
        assert ss.is_insufficient is False
        assert ss.is_initial is True

    def test_n_29_initial(self):
        ss = EvidencePresenter().sample_strength(29)
        assert ss.label == "初步觀察"
        assert ss.is_initial is True

    def test_n_30_has_reference(self):
        ss = EvidencePresenter().sample_strength(30)
        assert ss.label == "有一定參考"
        assert ss.is_insufficient is False
        assert ss.is_initial is False

    def test_n_99_has_reference(self):
        ss = EvidencePresenter().sample_strength(99)
        assert ss.label == "有一定參考"

    def test_n_100_stable(self):
        ss = EvidencePresenter().sample_strength(100)
        assert ss.label == "可評估穩定性"

    def test_n_1000_stable(self):
        ss = EvidencePresenter().sample_strength(1000)
        assert ss.label == "可評估穩定性"

    def test_formatted_contains_n_and_label(self):
        ss = EvidencePresenter().sample_strength(50)
        assert "N=50" in ss.formatted
        assert "有一定參考" in ss.formatted

    def test_formatted_insufficient(self):
        ss = EvidencePresenter().sample_strength(5)
        assert "N=5" in ss.formatted
        assert "不足" in ss.formatted

    def test_thresholds_are_pre_registered(self):
        """Verify the four threshold boundaries match foe_v1 §46."""
        ep = EvidencePresenter()
        assert ep.sample_strength(9).label  == "不足"
        assert ep.sample_strength(10).label == "初步觀察"
        assert ep.sample_strength(29).label == "初步觀察"
        assert ep.sample_strength(30).label == "有一定參考"
        assert ep.sample_strength(99).label == "有一定參考"
        assert ep.sample_strength(100).label == "可評估穩定性"


class TestOvernightGroupHeadlineHtml:
    def _green(self, n, alpha):
        return {"overnight_risk": "GREEN", "N": n, "20D Alpha (avg %)": alpha}

    def _red(self, n, alpha):
        return {"overnight_risk": "RED", "N": n, "20D Alpha (avg %)": alpha}

    def test_returns_html_string_when_both_groups_present(self):
        ep = EvidencePresenter()
        html = ep.overnight_group_headline_html(
            self._green(30, 1.5), self._red(20, -0.5)
        )
        assert html is not None
        assert "GREEN" in html
        assert "RED" in html

    def test_positive_diff_green_color(self):
        ep = EvidencePresenter()
        html = ep.overnight_group_headline_html(
            self._green(30, 2.0), self._red(20, 0.0)
        )
        assert "#00897b" in html

    def test_negative_diff_red_color(self):
        ep = EvidencePresenter()
        html = ep.overnight_group_headline_html(
            self._green(30, -1.0), self._red(20, 1.0)
        )
        assert "#e53935" in html

    def test_returns_none_when_green_missing(self):
        ep = EvidencePresenter()
        result = ep.overnight_group_headline_html(None, self._red(20, -0.5))
        assert result is None

    def test_returns_none_when_red_missing(self):
        ep = EvidencePresenter()
        result = ep.overnight_group_headline_html(self._green(30, 1.5), None)
        assert result is None

    def test_returns_none_when_alpha_not_float(self):
        ep = EvidencePresenter()
        result = ep.overnight_group_headline_html(
            {"overnight_risk": "GREEN", "N": 3, "20D Alpha (avg %)": "—"},
            self._red(20, -0.5),
        )
        assert result is None

    def test_sample_strength_shown_in_html(self):
        ep = EvidencePresenter()
        html = ep.overnight_group_headline_html(
            self._green(100, 1.5), self._red(9, -0.5)
        )
        assert "可評估穩定性" in html
        assert "不足" in html

    def test_alpha_values_formatted_in_html(self):
        ep = EvidencePresenter()
        html = ep.overnight_group_headline_html(
            self._green(30, 1.50), self._red(20, -0.25)
        )
        assert "+1.50%" in html
        assert "-0.25%" in html

    def test_diff_shown_in_html(self):
        ep = EvidencePresenter()
        html = ep.overnight_group_headline_html(
            self._green(30, 2.0), self._red(20, 0.5)
        )
        assert "+1.50%" in html  # diff = 2.0 - 0.5
