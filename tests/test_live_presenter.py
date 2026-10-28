"""tests/test_live_presenter.py — Unit tests for LivePresenter."""

from unittest.mock import MagicMock

import pytest

from src.presentation.live_presenter import LiveCard, LivePresenter


# ── fmt_pct ──────────────────────────────────────────────────────────────────

def test_fmt_pct_positive():
    assert LivePresenter.fmt_pct(2.5) == "+2.5%"


def test_fmt_pct_negative():
    assert LivePresenter.fmt_pct(-1.3) == "-1.3%"


def test_fmt_pct_zero():
    assert LivePresenter.fmt_pct(0.0) == "+0.0%"


def test_fmt_pct_none():
    assert LivePresenter.fmt_pct(None) == "—"


# ── overnight_risk_badge ─────────────────────────────────────────────────────

def test_overnight_risk_badge_green():
    html = LivePresenter.overnight_risk_badge("GREEN")
    assert "穩定" in html
    assert "#00897b" in html


def test_overnight_risk_badge_red():
    html = LivePresenter.overnight_risk_badge("RED")
    assert "高風險" in html
    assert "#c62828" in html


def test_overnight_risk_badge_unknown_level_fallback():
    html = LivePresenter.overnight_risk_badge("NONEXISTENT")
    assert "資料不足" in html


# ── status_badge_html ─────────────────────────────────────────────────────────

def test_status_badge_html():
    ld = MagicMock()
    ld.bg = "#e8f5e9"
    ld.color = "#2e7d32"
    ld.icon = "🟢"
    ld.label = "觀察進場"
    html = LivePresenter.status_badge_html(ld)
    assert "#e8f5e9" in html
    assert "🟢" in html
    assert "觀察進場" in html


# ── price_delta_html ──────────────────────────────────────────────────────────

def test_price_delta_html_positive():
    html = LivePresenter.price_delta_html(110.0, 100.0, "vs 訊號")
    assert "+10.0%" in html
    assert "#00897b" in html


def test_price_delta_html_negative():
    html = LivePresenter.price_delta_html(90.0, 100.0, "vs 訊號")
    assert "-10.0%" in html
    assert "#e53935" in html


# ── plain_text_html ───────────────────────────────────────────────────────────

def test_plain_text_html_with_content():
    html = LivePresenter.plain_text_html("買在支撐帶下緣")
    assert "買在支撐帶下緣" in html
    assert "💬" in html


def test_plain_text_html_empty():
    assert LivePresenter.plain_text_html("") == ""


def test_plain_text_html_none_like():
    assert LivePresenter.plain_text_html("") == ""


# ── rr_html ───────────────────────────────────────────────────────────────────

def test_rr_html_none_returns_empty():
    ld = MagicMock()
    ld.rr_current = None
    assert LivePresenter.rr_html(ld) == ""


def test_rr_html_zero_returns_empty():
    ld = MagicMock()
    ld.rr_current = 0.0
    assert LivePresenter.rr_html(ld) == ""


def test_rr_html_high_rr_green():
    from src.engines.live_decision import LiveStatus

    ld = MagicMock()
    ld.rr_current = 2.5
    ld.status = LiveStatus.IN_RANGE
    html = LivePresenter.rr_html(ld)
    assert "2.5x" in html
    assert "#00897b" in html


def test_rr_html_mid_rr_orange():
    from src.engines.live_decision import LiveStatus

    ld = MagicMock()
    ld.rr_current = 1.5
    ld.status = LiveStatus.IN_RANGE
    html = LivePresenter.rr_html(ld)
    assert "1.5x" in html
    assert "#f57f17" in html


def test_rr_html_low_rr_red():
    from src.engines.live_decision import LiveStatus

    ld = MagicMock()
    ld.rr_current = 0.8
    ld.status = LiveStatus.IN_RANGE
    html = LivePresenter.rr_html(ld)
    assert "0.8x" in html
    assert "#e53935" in html


def test_rr_html_visual_only_does_not_affect_signal():
    """VISUAL_ONLY: rr colour thresholds must not change signal_label or execution guidance."""
    from src.engines.live_decision import LiveStatus

    p = LivePresenter()
    rec_base = {
        "trade_signal": "buy",
        "price": 100.0,
        "entry_low": 98.0,
        "entry_high": 102.0,
        "stop_price": 95.0,
        "target1": 115.0,
    }

    def _make_ld(rr: float):
        ld = MagicMock()
        ld.rr_current = rr
        ld.status = LiveStatus.IN_RANGE
        ld.color = "#2e7d32"
        ld.bg = "#e8f5e9"
        ld.icon = "🟢"
        ld.label = "觀察進場"
        ld.reason = "在進場區間內"
        ld.plain_text = ""
        ld.intraday_low = None
        ld.stop_price = 95.0
        ld.current_price = 100.0
        return ld

    quote = MagicMock()
    quote.trade_date = None
    quote.update_time = None

    card_low  = p.present(rec_base, _make_ld(0.5), quote, "valid", None)
    card_high = p.present(rec_base, _make_ld(3.0), quote, "valid", None)

    # signal_label must be invariant to rr
    assert card_low.signal_label == card_high.signal_label == "BUY"
    # plan_str must be invariant to rr
    assert card_low.plan_str == card_high.plan_str


# ── price_display_html ────────────────────────────────────────────────────────

def test_price_display_stale():
    quote = MagicMock()
    quote.trade_date = "20241009"
    html = LivePresenter.price_display_html(quote, None, "stale")
    assert "舊交易日資料" in html
    assert "2024/10/09" in html


def test_price_display_unknown_no_price():
    html = LivePresenter.price_display_html(None, None, "unknown")
    assert "日期未確認" in html


def test_price_display_valid_with_price():
    quote = MagicMock()
    quote.update_time = "10:30"
    html = LivePresenter.price_display_html(quote, 123.5, "valid")
    assert "123.5" in html
    assert "10:30" in html


def test_price_display_no_price():
    quote = MagicMock()
    quote.update_time = "09:05"
    html = LivePresenter.price_display_html(quote, None, "valid")
    assert "無即時成交" in html


# ── buy_note_html ─────────────────────────────────────────────────────────────

def test_buy_note_html_not_in_drop():
    from src.engines.live_decision import LiveStatus

    ld = MagicMock()
    ld.status = LiveStatus.IN_RANGE
    assert LivePresenter.buy_note_html(ld) == ""


def test_buy_note_html_entry_reconfirmed():
    from src.engines.live_decision import LiveStatus

    ld = MagicMock()
    ld.status = LiveStatus.ENTRY_RECONFIRMED
    html = LivePresenter.buy_note_html(ld)
    assert "轉強觀察訊號" in html


def test_buy_note_html_rapid_drop_low_rr():
    from src.engines.live_decision import LiveStatus

    ld = MagicMock()
    ld.status = LiveStatus.RAPID_DROP
    ld.rr_current = 0.9
    html = LivePresenter.buy_note_html(ld)
    assert "0.9x" in html
    assert "#e65100" in html


def test_buy_note_html_rapid_drop_ok_rr():
    from src.engines.live_decision import LiveStatus

    ld = MagicMock()
    ld.status = LiveStatus.RAPID_DROP
    ld.rr_current = 2.0
    html = LivePresenter.buy_note_html(ld)
    assert "Setup" in html
    assert "#888" in html


# ── plan_str_from_rec ─────────────────────────────────────────────────────────

def test_plan_str_full():
    s = LivePresenter.plan_str_from_rec(98.0, 102.0, 95.0, 115.0)
    assert "進場 98.0–102.0" in s
    assert "停損 95.0" in s
    assert "T1 115.0" in s


def test_plan_str_no_entry():
    s = LivePresenter.plan_str_from_rec(None, None, 95.0, 115.0)
    assert "停損 95.0" in s
    assert "T1 115.0" in s


def test_plan_str_empty_falls_back():
    s = LivePresenter.plan_str_from_rec(None, None, None, None)
    assert s == "交易計劃待補"


# ── overnight_card_html / overnight_l1_html (ctx=None) ───────────────────────

def test_overnight_card_html_no_ctx():
    html = LivePresenter.overnight_card_html(None, "buy", None)
    assert "尚未取得" in html


def test_overnight_l1_html_no_ctx():
    html = LivePresenter.overnight_l1_html(None, "buy", None)
    assert "尚未取得" in html


# ── drop_scenario_html ────────────────────────────────────────────────────────

def test_drop_scenario_html_not_in_drop():
    from src.engines.live_decision import LiveStatus

    ld = MagicMock()
    ld.status = LiveStatus.IN_RANGE
    assert LivePresenter.drop_scenario_html(ld, 100.0) == ""


def test_drop_scenario_html_rapid_drop():
    from src.engines.live_decision import LiveStatus

    ld = MagicMock()
    ld.status = LiveStatus.RAPID_DROP
    ld.current_price = 95.0
    ld.intraday_low = 94.0
    ld.stop_price = 92.0
    html = LivePresenter.drop_scenario_html(ld, 100.0)
    assert "急跌暫緩" in html
    assert "94.0" in html


def test_drop_scenario_html_entry_reconfirmed():
    from src.engines.live_decision import LiveStatus

    ld = MagicMock()
    ld.status = LiveStatus.ENTRY_RECONFIRMED
    ld.current_price = 98.0
    ld.intraday_low = 93.0
    ld.stop_price = 90.0
    html = LivePresenter.drop_scenario_html(ld, 100.0)
    assert "轉強確認" in html


# ── present() integration ─────────────────────────────────────────────────────

def test_present_returns_live_card():
    from src.engines.live_decision import LiveStatus

    p = LivePresenter()
    rec = {
        "trade_signal": "strong_buy",
        "price": 100.0,
        "entry_low": 98.0,
        "entry_high": 102.0,
        "stop_price": 95.0,
        "target1": 115.0,
    }
    ld = MagicMock()
    ld.rr_current = 2.0
    ld.status = LiveStatus.IN_RANGE
    ld.color = "#2e7d32"
    ld.bg = "#e8f5e9"
    ld.icon = "🟢"
    ld.label = "觀察進場"
    ld.reason = "在進場區間內"
    ld.plain_text = "支撐確立"
    ld.intraday_low = None
    ld.stop_price = 95.0
    ld.current_price = 101.0

    quote = MagicMock()
    quote.trade_date = None
    quote.update_time = "10:30"

    card = p.present(rec, ld, quote, "valid", None)

    assert isinstance(card, LiveCard)
    assert card.signal_label == "BUY ★"
    assert card.signal_color == "#1a7f4b"
    assert card.l2_expanded is False
    assert "98.0–102.0" in card.plan_str
    assert "支撐確立" in card.plain_html


def test_present_l2_expanded_for_rapid_drop():
    from src.engines.live_decision import LiveStatus

    p = LivePresenter()
    rec = {"trade_signal": "buy", "price": 100.0}
    ld = MagicMock()
    ld.rr_current = 1.0
    ld.status = LiveStatus.RAPID_DROP
    ld.color = "#e65100"
    ld.bg = "#fff3e0"
    ld.icon = "🔴"
    ld.label = "急跌暫緩"
    ld.reason = "急跌超過 3%"
    ld.plain_text = ""
    ld.intraday_low = 96.0
    ld.stop_price = 93.0
    ld.current_price = 97.0

    quote = MagicMock()
    quote.trade_date = None
    quote.update_time = None

    card = p.present(rec, ld, quote, "valid", None)
    assert card.l2_expanded is True
