"""
Unit tests for src/presentation/decision_presenter.py

Verifies:
- All static lookup tables are complete
- present() returns a DecisionCard without re-deriving signals
- Each helper method handles edge cases correctly
"""

from src.presentation.decision_presenter import (
    _SETUP_LABEL,
    _SIGNAL_ATTRS,
    DecisionCard,
    DecisionPresenter,
)

PRESENTER = DecisionPresenter()

KNOWN_SETUPS = [
    "near_breakout",
    "pullback_buy",
    "breakout",
    "trending",
    "breakdown",
    "pullback_hold",
    "failed_breakout",
    "none",
]

KNOWN_SIGNALS = ["strong_buy", "buy", "wait", "sell"]


# ── Static table completeness ────────────────────────────────────────────────


class TestStaticTables:
    def test_all_setups_have_labels(self):
        for s in KNOWN_SETUPS:
            assert s in _SETUP_LABEL, f"_SETUP_LABEL missing: {s}"

    def test_all_signals_have_attrs(self):
        for sig in KNOWN_SIGNALS:
            assert sig in _SIGNAL_ATTRS, f"_SIGNAL_ATTRS missing: {sig}"
            label, col, bg = _SIGNAL_ATTRS[sig]
            assert label and col and bg

    def test_why_html_covers_all_setups_both_sides(self):
        # Every non-trivial setup should have entries for both is_buy=True and False
        for setup in KNOWN_SETUPS:
            if setup == "none":
                continue
            for is_buy in (True, False):
                result = PRESENTER._why_html(setup, is_buy)
                assert isinstance(result, str), f"_why_html({setup}, {is_buy}) not str"

    def test_why_html_nonempty_for_actionable_setups(self):
        actionable = [
            "near_breakout",
            "pullback_buy",
            "breakout",
            "trending",
            "breakdown",
            "pullback_hold",
            "failed_breakout",
        ]
        for setup in actionable:
            for is_buy in (True, False):
                result = PRESENTER._why_html(setup, is_buy)
                assert result, f"_why_html({setup}, {is_buy}) is empty"

    def test_why_html_unknown_setup_returns_string(self):
        result = PRESENTER._why_html("totally_unknown_setup", True)
        assert isinstance(result, str)


# ── Signal pass-through (no re-calculation) ──────────────────────────────────


class TestSignalPassThrough:
    def test_wait_signal_preserved(self):
        r = {"trade_signal": "wait", "setup_type": "near_breakout"}
        card = PRESENTER.present(r)
        assert card.signal_label == "WAIT"
        assert card.signal_col == "#546e7a"

    def test_strong_buy_signal_preserved(self):
        r = {"trade_signal": "strong_buy", "setup_type": "breakout"}
        card = PRESENTER.present(r)
        assert card.signal_label == "BUY ▲"
        assert card.signal_col == "#1a7f4b"

    def test_buy_signal_preserved(self):
        r = {"trade_signal": "buy", "setup_type": "pullback_buy"}
        card = PRESENTER.present(r)
        assert card.signal_label == "BUY"

    def test_sell_signal_preserved(self):
        r = {"trade_signal": "sell", "setup_type": "breakdown"}
        card = PRESENTER.present(r)
        assert card.signal_label == "SELL"

    def test_unknown_signal_defaults_to_wait(self):
        r = {"trade_signal": "unknown_future_signal", "setup_type": "none"}
        card = PRESENTER.present(r)
        assert card.signal_label == "WAIT"

    def test_pt_score_not_recalculated(self):
        r = {"trade_signal": "buy", "price_trend_score": 77.5}
        card = PRESENTER.present(r)
        assert card.pt_val == 77.5
        assert "PT 78" in card.tech_metrics  # formatted from raw value

    def test_confidence_not_recalculated(self):
        r = {"trade_signal": "wait", "confidence": 83.7}
        card = PRESENTER.present(r)
        assert card.conf == 83.7


# ── present() with minimal r ─────────────────────────────────────────────────


class TestPresentMinimal:
    def test_empty_dict_does_not_crash(self):
        card = PRESENTER.present({})
        assert isinstance(card, DecisionCard)
        assert card.signal_label == "WAIT"
        assert card.setup == "none"

    def test_returns_decision_card(self):
        r = {
            "trade_signal": "buy",
            "setup_type": "breakout",
            "name": "台積電",
            "sid": "2330",
            "price": 900.0,
            "price_trend_score": 80.0,
            "vol_ratio": 2.0,
            "ma20_gap": 3.5,
            "confidence": 85.0,
            "level": "A",
        }
        card = PRESENTER.present(r)
        assert card.name == "台積電"
        assert card.sid == "2330"
        assert card.price_str == "NT$ 900.0"
        assert card.level == "A"
        assert card.setup_label == "Breakout"

    def test_advantages_risks_split_by_fin_keywords(self):
        r = {
            "advantages": ["突破前高", "EPS 成長", "籌碼集中"],
            "risks": ["毛利率下滑", "壓力位在前"],
        }
        card = PRESENTER.present(r)
        assert "突破前高" in card.tech_adv
        assert "籌碼集中" in card.tech_adv
        assert "EPS 成長" in card.fin_adv
        assert "毛利率下滑" in card.fin_risk
        assert "壓力位在前" in card.tech_risk

    def test_price_str_none_price(self):
        card = PRESENTER.present({"price": None})
        assert card.price_str == "—"

    def test_consecutive_days_default(self):
        card = PRESENTER.present({})
        assert card.consecutive == 1

    def test_consecutive_days_read_from_r(self):
        card = PRESENTER.present({"consecutive_days": 5})
        assert card.consecutive == 5


# ── InvalidationText ─────────────────────────────────────────────────────────


class TestInvalidationText:
    def test_near_breakout_includes_level(self):
        text = PRESENTER._invalidation_text("near_breakout", 90.0, "A")
        assert "A 級" in text
        assert "$90.0" in text

    def test_pullback_buy_mentions_ma10(self):
        text = PRESENTER._invalidation_text("pullback_buy", 85.0, "B")
        assert "MA10" in text
        assert "$85.0" in text

    def test_breakout_mentions_exit(self):
        text = PRESENTER._invalidation_text("breakout", 100.0, "A+")
        assert "出場" in text

    def test_trending_mentions_death_cross(self):
        text = PRESENTER._invalidation_text("trending", 50.0, "B")
        assert "死叉" in text

    def test_unknown_setup_fallback(self):
        text = PRESENTER._invalidation_text("unknown_setup", 30.0, "C")
        assert "$30.0" in text

    def test_no_stop_price_uses_placeholder(self):
        text = PRESENTER._invalidation_text("breakout", None, "A")
        assert "停損價" in text


# ── EvidenceSummary ───────────────────────────────────────────────────────────


class TestEvidenceSummary:
    def test_empty_ev_returns_empty(self):
        assert PRESENTER._evidence_summary({}) == ""

    def test_fewer_than_5_samples_returns_empty(self):
        ev = {"research": {"n": 4, "alpha_20d": {"median": 2.0, "winrate": 60.0}}}
        assert PRESENTER._evidence_summary(ev) == ""

    def test_sufficient_samples_with_data(self):
        ev = {
            "research": {
                "n": 20,
                "alpha_20d": {"median": 3.5, "winrate": 65.0},
                "tier_emoji": "🟡",
            }
        }
        summary = PRESENTER._evidence_summary(ev)
        assert "20" in summary
        assert "3.5" in summary
        assert "65" in summary

    def test_samples_without_median_returns_accumulating_msg(self):
        ev = {"research": {"n": 10, "alpha_20d": {}, "tier_emoji": "🔴"}}
        summary = PRESENTER._evidence_summary(ev)
        assert "累積" in summary
        assert "10" in summary

    def test_negative_median_has_no_plus_sign(self):
        ev = {
            "research": {
                "n": 15,
                "alpha_20d": {"median": -2.3, "winrate": 40.0},
                "tier_emoji": "🔴",
            }
        }
        summary = PRESENTER._evidence_summary(ev)
        assert "+(-2.3)" not in summary
        assert "-2.3" in summary

    def test_positive_median_has_plus_sign(self):
        ev = {
            "research": {
                "n": 12,
                "alpha_20d": {"median": 1.8, "winrate": 58.0},
                "tier_emoji": "🟡",
            }
        }
        summary = PRESENTER._evidence_summary(ev)
        assert "+1.8" in summary


# ── Checklist ────────────────────────────────────────────────────────────────


class TestChecklist:
    def test_near_breakout_returns_3_items(self):
        items = PRESENTER._checklist("near_breakout", False, 1.2, [])
        assert len(items) == 3

    def test_near_breakout_high_vol_green(self):
        items = PRESENTER._checklist("near_breakout", False, 2.0, [])
        vol_item = next(i for i in items if i[1] == "量能")
        assert vol_item[0] == "🟢"

    def test_near_breakout_low_vol_yellow(self):
        items = PRESENTER._checklist("near_breakout", False, 1.0, [])
        vol_item = next(i for i in items if i[1] == "量能")
        assert vol_item[0] == "🟡"

    def test_near_breakout_breakthrough_always_yellow(self):
        items = PRESENTER._checklist("near_breakout", False, 3.0, [])
        bt_item = next(i for i in items if i[1] == "突破")
        assert bt_item[0] == "🟡"

    def test_pullback_buy_confirmed_support_green(self):
        items = PRESENTER._checklist("pullback_buy", True, 1.0, [])
        sup = next(i for i in items if i[1] == "支撐")
        assert sup[0] == "🟢"

    def test_pullback_buy_unconfirmed_support_yellow(self):
        items = PRESENTER._checklist("pullback_buy", False, 1.0, [])
        sup = next(i for i in items if i[1] == "支撐")
        assert sup[0] == "🟡"

    def test_breakout_3_items(self):
        items = PRESENTER._checklist("breakout", True, 2.0, [])
        assert len(items) == 3
        bt = next(i for i in items if i[1] == "突破")
        assert bt[0] == "🟢"

    def test_trending_pressure_detected(self):
        items = PRESENTER._checklist("trending", True, 1.5, ["前波壓力大"])
        pres = next(i for i in items if i[1] == "壓力")
        assert pres[0] == "🟡"

    def test_trending_no_pressure(self):
        items = PRESENTER._checklist("trending", True, 1.5, [])
        pres = next(i for i in items if i[1] == "壓力")
        assert pres[0] == "🟢"

    def test_unknown_setup_returns_empty(self):
        items = PRESENTER._checklist("breakdown", True, 1.0, [])
        assert items == []

    def test_zero_vol_ratio_handled(self):
        items = PRESENTER._checklist("near_breakout", False, 0.0, [])
        assert len(items) == 3


# ── Scenarios ────────────────────────────────────────────────────────────────


class TestScenarios:
    def test_near_breakout_3_scenarios(self):
        scens = PRESENTER._scenarios("near_breakout", False, 90.0, 100.0, 110.0)
        assert len(scens) == 3
        icons = {s[0] for s in scens}
        assert "🟢" in icons and "🟡" in icons and "🔴" in icons

    def test_near_breakout_includes_target_prices(self):
        scens = PRESENTER._scenarios("near_breakout", False, 90.0, 100.0, 110.0)
        all_text = " ".join(s[2] for s in scens)
        assert "$100.0" in all_text
        assert "$110.0" in all_text

    def test_pullback_buy_is_buy_scenarios(self):
        scens = PRESENTER._scenarios("pullback_buy", True, 80.0, 95.0, 105.0)
        assert len(scens) == 3
        green_desc = next(s[2] for s in scens if s[0] == "🟢")
        assert "MA10" in green_desc

    def test_pullback_buy_wait_scenarios(self):
        scens = PRESENTER._scenarios("pullback_buy", False, 80.0, 95.0, 105.0)
        green_desc = next(s[2] for s in scens if s[0] == "🟢")
        assert "BUY" in green_desc

    def test_breakout_3_scenarios(self):
        scens = PRESENTER._scenarios("breakout", True, 90.0, 100.0, 110.0)
        assert len(scens) == 3

    def test_trending_3_scenarios(self):
        scens = PRESENTER._scenarios("trending", True, 50.0, 60.0, 70.0)
        assert len(scens) == 3

    def test_breakdown_3_scenarios(self):
        scens = PRESENTER._scenarios("breakdown", False, 30.0, None, None)
        assert len(scens) == 3

    def test_unknown_setup_returns_empty(self):
        scens = PRESENTER._scenarios("none", False, None, None, None)
        assert scens == []

    def test_no_prices_uses_placeholders(self):
        scens = PRESENTER._scenarios("near_breakout", False, None, None, None)
        all_text = " ".join(s[2] for s in scens)
        assert "停損價" in all_text
        assert "目標一" in all_text


# ── PlainTech / PlainFundamental ─────────────────────────────────────────────


class TestPlainTextHelpers:
    def test_plain_tech_near_breakout(self):
        text = PRESENTER._plain_tech("near_breakout", False, 1.5)
        assert "壓力" in text

    def test_plain_tech_breakout_high_vol(self):
        text = PRESENTER._plain_tech("breakout", True, 2.0)
        assert "放大" in text

    def test_plain_tech_breakout_low_vol(self):
        text = PRESENTER._plain_tech("breakout", True, 1.0)
        assert "尚可" in text

    def test_plain_tech_unknown_returns_empty(self):
        assert PRESENTER._plain_tech("none", True, 1.0) == ""

    def test_plain_fundamental_no_data(self):
        text = PRESENTER._plain_fundamental([], [])
        assert "不完整" in text

    def test_plain_fundamental_mostly_positive(self):
        text = PRESENTER._plain_fundamental(["EPS 成長", "ROE 改善"], ["毛利率下滑"])
        assert "改善" in text

    def test_plain_fundamental_mostly_negative(self):
        text = PRESENTER._plain_fundamental(["EPS 成長"], ["毛利率下滑", "負債增加"])
        assert "隱憂" in text

    def test_plain_fundamental_balanced(self):
        text = PRESENTER._plain_fundamental(["EPS 成長"], ["毛利率下滑"])
        assert "加分" in text


# ── Full present() integration ────────────────────────────────────────────────


class TestPresentIntegration:
    def _make_full_r(self):
        return {
            "trade_signal": "buy",
            "setup_type": "breakout",
            "name": "聯發科",
            "sid": "2454",
            "price": 1200.0,
            "entry_low": 1190.0,
            "entry_high": 1210.0,
            "stop_price": 1140.0,
            "target1": 1320.0,
            "target2": 1440.0,
            "price_trend_score": 82.0,
            "vol_ratio": 2.1,
            "ma20_gap": 4.2,
            "confidence": 88.0,
            "level": "A+",
            "consecutive_days": 3,
            "scores": {"total": 78.0, "quality": 70.0, "timing": 85.0},
            "advantages": ["突破前高", "籌碼集中", "EPS 成長"],
            "risks": ["壓力位在前", "毛利率下滑"],
        }

    def test_full_present_returns_card(self):
        card = PRESENTER.present(self._make_full_r())
        assert isinstance(card, DecisionCard)

    def test_full_present_name_sid(self):
        card = PRESENTER.present(self._make_full_r())
        assert card.name == "聯發科"
        assert card.sid == "2454"

    def test_full_present_setup_label(self):
        card = PRESENTER.present(self._make_full_r())
        assert card.setup_label == "Breakout"

    def test_full_present_why_nonempty(self):
        card = PRESENTER.present(self._make_full_r())
        assert len(card.why_html) > 20

    def test_full_present_scenarios_nonempty(self):
        card = PRESENTER.present(self._make_full_r())
        assert len(card.scenarios) == 3

    def test_full_present_checklist_nonempty(self):
        card = PRESENTER.present(self._make_full_r())
        assert len(card.checklist) == 3

    def test_full_present_tech_metrics_contains_pt(self):
        card = PRESENTER.present(self._make_full_r())
        assert "PT 82" in card.tech_metrics

    def test_full_present_advantages_split_correctly(self):
        card = PRESENTER.present(self._make_full_r())
        assert "突破前高" in card.tech_adv
        assert "EPS 成長" in card.fin_adv
        assert "壓力位在前" in card.tech_risk
        assert "毛利率下滑" in card.fin_risk

    def test_full_present_with_evidence(self):
        ev = {
            "research": {
                "n": 25,
                "alpha_20d": {"median": 5.2, "winrate": 68.0},
                "tier_emoji": "🟢",
            }
        }
        card = PRESENTER.present(self._make_full_r(), ev)
        assert "25" in card.evidence_summary
        assert "5.2" in card.evidence_summary

    def test_full_present_dq_str_empty_without_dq(self):
        r = self._make_full_r()
        r.pop("data_quality", None)
        card = PRESENTER.present(r)
        assert card.dq_str == ""
