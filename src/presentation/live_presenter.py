"""
live_presenter.py — Translation layer for Live Monitor card display.

Reads from: frozen rec dict, LiveDecision (ld), intraday quote, OvernightContext.
Never re-derives: LiveStatus, RAPID_DROP thresholds, overnight risk levels,
                  ExecutionGuidance decisions, BUY/WAIT/SELL signals, rr_current.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LiveCard:
    """Pre-built HTML fragments for one live signal card."""

    # ── Header ─────────────────────────────────────────────────────────────
    signal_label: str        # "BUY ★" or "BUY"
    signal_color: str        # hex (#1a7f4b / #2ecc71)
    border_color: str        # from ld.color (live engine state — pass-through)

    # ── Level 1: always visible ─────────────────────────────────────────
    price_display: str       # HTML: formatted current price with status handling
    delta_html: str          # HTML: % change vs frozen signal price
    status_badge_html: str   # HTML: live status badge (pass-through from ld)
    reason: str              # live engine reason text (pass-through from ld.reason)
    overnight_l1_html: str   # HTML: compact risk icon + guidance badge
    plan_str: str            # plain text: "進場 X–X　停損 X　T1 X"
    rr_display: str          # HTML: R/R value with VISUAL_ONLY color coding

    # ── Level 2: expander content ───────────────────────────────────────
    buy_note_html: str       # HTML: BUY ≠ good-entry note
    plain_html: str          # HTML: wrapped ld.plain_text
    drop_html: str           # HTML: drop scenario three-stage display
    overnight_full_html: str # HTML: full overnight card with index detail

    # ── Expansion control ────────────────────────────────────────────────
    l2_expanded: bool        # True for RAPID_DROP / WATCHING_LOW / ENTRY_RECONFIRMED


class LivePresenter:
    """
    Translate live engine state into LiveCard display DTO.

    Input:  rec dict (frozen signal), ld (LiveDecision), quote, overnight_ctx
    Output: LiveCard with pre-built HTML fragments for each display level.

    Forbidden: re-deriving LiveStatus, overnight risk, execution guidance,
               BUY/WAIT/SELL signals, entry/stop/target prices, rr_current.
    """

    # Overnight risk level → (icon, text_color, bg_color, label)
    _RISK_META: dict[str, tuple] = {
        "GREEN":   ("🟢", "#00897b", "#e0f2f1", "穩定"),
        "YELLOW":  ("🟡", "#f57f17", "#fff8e1", "偏弱"),
        "RED":     ("🔴", "#c62828", "#ffebee", "高風險"),
        "UNKNOWN": ("⚪", "#78909c", "#eceff1", "資料不足"),
    }

    # VISUAL_ONLY: R/R thresholds below affect badge colour only.
    # They do NOT affect execution guidance or trading decisions.
    _RR_VISUAL_HIGH = 2.0
    _RR_VISUAL_MID  = 1.0

    def present(
        self,
        rec: dict,
        ld: object,
        quote: object | None,
        date_status: str,
        overnight_ctx: object | None,
    ) -> LiveCard:
        from src.engines.live_decision import LiveStatus

        trade_signal = rec.get("trade_signal", "")
        sig_price    = rec.get("price")
        entry_low    = rec.get("entry_low")
        entry_high   = rec.get("entry_high")
        stop_p       = rec.get("stop_price")
        t1           = rec.get("target1")
        cur_price    = getattr(ld, "current_price", None)

        drop_statuses = (
            LiveStatus.RAPID_DROP,
            LiveStatus.WATCHING_LOW,
            LiveStatus.ENTRY_RECONFIRMED,
        )

        return LiveCard(
            signal_label=("BUY ★" if trade_signal == "strong_buy" else "BUY"),
            signal_color=("#1a7f4b" if trade_signal == "strong_buy" else "#2ecc71"),
            border_color=ld.color,
            price_display=self.price_display_html(quote, cur_price, date_status),
            delta_html=(
                self.price_delta_html(cur_price, sig_price, "vs 昨日訊號價")
                if (cur_price and sig_price)
                else ""
            ),
            status_badge_html=self.status_badge_html(ld),
            reason=ld.reason,
            overnight_l1_html=self.overnight_l1_html(
                overnight_ctx, trade_signal, ld.status
            ),
            plan_str=self.plan_str_from_rec(entry_low, entry_high, stop_p, t1),
            rr_display=self.rr_html(ld),
            buy_note_html=self.buy_note_html(ld),
            plain_html=self.plain_text_html(ld.plain_text),
            drop_html=(
                self.drop_scenario_html(ld, sig_price) if sig_price else ""
            ),
            overnight_full_html=self.overnight_card_html(
                overnight_ctx, trade_signal, ld.status
            ),
            l2_expanded=(ld.status in drop_statuses),
        )

    # ── Static / class-method HTML builders ────────────────────────────

    @staticmethod
    def fmt_pct(v: float | None) -> str:
        if v is None:
            return "—"
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.1f}%"

    @classmethod
    def overnight_risk_badge(cls, risk_level: str) -> str:
        icon, color, bg, label = cls._RISK_META.get(
            risk_level, cls._RISK_META["UNKNOWN"]
        )
        return (
            f'<span style="background:{bg};color:{color};'
            f'font-weight:700;padding:2px 9px;border-radius:10px;font-size:0.78rem">'
            f'{icon} {label}</span>'
        )

    @staticmethod
    def status_badge_html(ld: object) -> str:
        return (
            f'<span style="background:{ld.bg};color:{ld.color};'
            f'font-weight:700;padding:3px 10px;border-radius:12px;font-size:0.8rem">'
            f'{ld.icon} {ld.label}</span>'
        )

    @staticmethod
    def price_delta_html(current: float, reference: float, label: str) -> str:
        diff  = current - reference
        pct   = diff / reference * 100
        color = "#00897b" if diff >= 0 else "#e53935"
        sign  = "+" if diff >= 0 else ""
        return (
            f'<span style="font-size:0.68rem;color:{color}">'
            f'{label} {sign}{pct:.1f}%</span>'
        )

    @staticmethod
    def plain_text_html(plain_text: str) -> str:
        if not plain_text:
            return ""
        return (
            f'<div style="background:#fffde7;border-radius:6px;padding:8px 10px;'
            f'margin:6px 0;font-size:0.72rem;color:#555;line-height:1.55">'
            f'💬 {plain_text}</div>'
        )

    @classmethod
    def rr_html(cls, ld: object) -> str:
        """
        Render R/R display.

        VISUAL_ONLY: _RR_VISUAL_HIGH / _RR_VISUAL_MID colour thresholds determine
        badge colour only — they do NOT affect execution guidance or trading decisions.
        """
        rr = getattr(ld, "rr_current", None)
        if rr is None or rr <= 0:
            return ""

        if rr >= cls._RR_VISUAL_HIGH:
            color = "#00897b"
        elif rr >= cls._RR_VISUAL_MID:
            color = "#f57f17"
        else:
            color = "#e53935"

        from src.engines.live_decision import LiveStatus

        price_note = (
            f'<span style="color:#aaa;font-size:0.65rem">'
            f'（以 {ld.current_price:.1f} 計）</span>'
            if (
                getattr(ld, "status", None)
                in (LiveStatus.RAPID_DROP, LiveStatus.WATCHING_LOW)
                and getattr(ld, "current_price", None)
            )
            else ""
        )
        return (
            f'<span style="color:{color};font-weight:700"> R/R {rr:.1f}x</span>'
            f'{price_note}'
        )

    @classmethod
    def overnight_card_html(
        cls, ctx: object | None, trade_signal: str, live_status: object
    ) -> str:
        if ctx is None:
            return (
                '<div style="margin:6px 0;padding:6px 10px;background:#f5f5f5;'
                'border-radius:6px;font-size:0.72rem;color:#9e9e9e">'
                '🌙 隔夜市場資料尚未取得（盤前自動建立）</div>'
            )

        from src.engines.overnight_risk import RISK_UNKNOWN
        from src.engines.execution_guidance import evaluate_execution_guidance, guidance_meta

        risk_level = ctx.risk_level or RISK_UNKNOWN
        icon, color, bg, label = cls._RISK_META.get(risk_level, cls._RISK_META["UNKNOWN"])

        rows_parts = []
        if ctx.nasdaq_return_pct is not None:
            rows_parts.append(f"Nasdaq {cls.fmt_pct(ctx.nasdaq_return_pct)}")
        if ctx.sox_return_pct is not None:
            rows_parts.append(f"SOX {cls.fmt_pct(ctx.sox_return_pct)}")
        if ctx.sp500_return_pct is not None:
            rows_parts.append(f"S&P {cls.fmt_pct(ctx.sp500_return_pct)}")
        if ctx.vix_close is not None:
            rows_parts.append(f"VIX {ctx.vix_close:.1f}")
        index_row = "　".join(rows_parts) if rows_parts else "—"

        guidance_result = evaluate_execution_guidance(
            trade_signal=trade_signal,
            live_status=live_status,
            overnight_risk=risk_level,
        )
        gmeta = guidance_meta(guidance_result.guidance)

        guidance_html = (
            f'<div style="margin-top:5px;font-size:0.72rem">'
            f'<span style="background:{gmeta["bg"]};color:{gmeta["color"]};'
            f'font-weight:700;padding:2px 8px;border-radius:8px">'
            f'{gmeta["icon"]} {gmeta["label"]}</span>'
            f'<span style="color:#666;margin-left:8px">{guidance_result.plain_text}</span>'
            f'</div>'
        )
        if guidance_result.caution and guidance_result.caution_text:
            guidance_html += (
                f'<div style="font-size:0.68rem;color:#e65100;margin-top:3px">'
                f'{guidance_result.caution_text}</div>'
            )

        return (
            f'<div style="margin:8px 0;padding:8px 10px;background:{bg};'
            f'border-left:3px solid {color};border-radius:0 6px 6px 0">'
            f'<div style="font-size:0.67rem;color:#999;margin-bottom:2px">🌙 隔夜市場風險</div>'
            f'<div style="font-size:0.85rem;font-weight:700;color:{color}">'
            f'{icon} {label}</div>'
            f'<div style="font-size:0.72rem;color:#555;margin-top:3px">{index_row}</div>'
            f'{guidance_html}'
            f'</div>'
        )

    @classmethod
    def overnight_l1_html(
        cls, ctx: object | None, trade_signal: str, live_status: object
    ) -> str:
        if ctx is None:
            return (
                '<div style="font-size:0.7rem;color:#aaa;margin:4px 0">'
                '🌙 隔夜市場尚未取得</div>'
            )

        from src.engines.overnight_risk import RISK_UNKNOWN
        from src.engines.execution_guidance import evaluate_execution_guidance, guidance_meta

        risk_level = ctx.risk_level or RISK_UNKNOWN
        icon, color, _bg, label = cls._RISK_META.get(
            risk_level, cls._RISK_META["UNKNOWN"]
        )
        risk_span = (
            f'<span style="color:{color};font-weight:700;font-size:0.72rem">'
            f'{icon} {label}</span>'
        )
        guidance_result = evaluate_execution_guidance(
            trade_signal=trade_signal,
            live_status=live_status,
            overnight_risk=risk_level,
        )
        gmeta = guidance_meta(guidance_result.guidance)
        guidance_span = (
            f'<span style="background:{gmeta["bg"]};color:{gmeta["color"]};'
            f'font-weight:700;padding:2px 8px;border-radius:8px;font-size:0.68rem;'
            f'margin-left:6px">{gmeta["icon"]} {gmeta["label"]}</span>'
        )
        return (
            f'<div style="display:flex;align-items:center;margin:4px 0">'
            f'<span style="font-size:0.67rem;color:#999;margin-right:6px">🌙</span>'
            f'{risk_span}{guidance_span}</div>'
        )

    @staticmethod
    def drop_scenario_html(ld: object, sig_price: float) -> str:
        from src.engines.live_decision import LiveStatus

        drop_statuses = (
            LiveStatus.RAPID_DROP,
            LiveStatus.WATCHING_LOW,
            LiveStatus.ENTRY_RECONFIRMED,
        )
        if getattr(ld, "status", None) not in drop_statuses:
            return ""

        cur  = getattr(ld, "current_price", None)
        ilow = getattr(ld, "intraday_low", None)

        if ilow and cur and ilow < sig_price:
            cur_color = (
                "#558b2f"
                if ld.status == LiveStatus.ENTRY_RECONFIRMED
                else "#1565c0"
            )
            narrative = (
                f'<span style="color:#333">{sig_price:.1f}</span>'
                f' <span style="color:#e53935">↘ {ilow:.1f} 最低</span>'
                f' <span style="color:{cur_color}">↗ {cur:.1f} 現價</span>'
            )
        elif cur:
            narrative = (
                f'<span style="color:#333">{sig_price:.1f}</span>'
                f' <span style="color:#e53935">↘ {cur:.1f}</span>'
            )
        else:
            narrative = f'<span style="color:#333">{sig_price:.1f}</span>'

        stage = {
            LiveStatus.RAPID_DROP:        1,
            LiveStatus.WATCHING_LOW:      2,
            LiveStatus.ENTRY_RECONFIRMED: 3,
        }[ld.status]

        stage_colors = {1: "#f57f17", 2: "#1565c0", 3: "#558b2f"}
        stage_labels = ["急跌暫緩", "觀察低點", "轉強確認"]

        def _stage_span(i: int) -> str:
            is_current = i == stage
            is_done    = i < stage
            if is_current:
                clr = stage_colors[i]
                return f'<span style="color:{clr};font-weight:700">● {stage_labels[i - 1]}</span>'
            if is_done:
                return f'<span style="color:#aaa">✓ {stage_labels[i - 1]}</span>'
            return f'<span style="color:#ddd">○ {stage_labels[i - 1]}</span>'

        stages_html = " <span style='color:#bbb'>→</span> ".join(
            _stage_span(i) for i in [1, 2, 3]
        )

        ilow_row = ""
        if ilow:
            stop_note = (
                f'<span style="color:#aaa;font-size:0.65rem"> '
                f'（盤中觀察點，非模型停損 {ld.stop_price:.1f}）</span>'
                if getattr(ld, "stop_price", None)
                else ""
            )
            ilow_row = (
                f'<div style="font-size:0.72rem;color:#555;margin-top:5px">'
                f'今日盤中觀察低點：<strong style="color:#1565c0">{ilow:.1f}</strong>'
                f'{stop_note}</div>'
            )

        border_color = stage_colors.get(stage, "#f57f17")
        return (
            f'<div style="margin:8px 0;padding:8px 10px;background:#f8f9fa;'
            f'border-left:3px solid {border_color};border-radius:0 6px 6px 0">'
            f'<div style="font-size:0.67rem;color:#999;margin-bottom:3px">今日價格走勢</div>'
            f'<div style="font-size:0.82rem;font-weight:600">{narrative}</div>'
            f'<div style="font-size:0.68rem;margin-top:5px">{stages_html}</div>'
            f'{ilow_row}'
            f'</div>'
        )

    @staticmethod
    def price_display_html(
        quote: object | None,
        cur_price: float | None,
        date_status: str,
    ) -> str:
        if date_status == "stale":
            html = '<span style="color:#e53935">⚠ 舊交易日資料</span>'
            if quote and getattr(quote, "trade_date", None):
                td = quote.trade_date
                html += (
                    f'<span style="font-size:0.62rem;color:#e53935">'
                    f' ({td[:4]}/{td[4:6]}/{td[6:]})</span>'
                )
            return html
        if date_status == "unknown" and not cur_price:
            return '<span style="color:#78909c">⚪ 日期未確認</span>'
        if cur_price:
            html = f"NT$ {cur_price:,.1f}"
            if quote and getattr(quote, "update_time", None):
                html += (
                    f'<span style="font-size:0.62rem;color:#aaa">'
                    f' ({quote.update_time})</span>'
                )
            return html
        html = '<span style="color:#f57f17">無即時成交</span>'
        if quote and getattr(quote, "update_time", None):
            html += (
                f'<span style="font-size:0.62rem;color:#aaa">'
                f' ({quote.update_time})</span>'
            )
        return html

    @staticmethod
    def buy_note_html(ld: object) -> str:
        from src.engines.live_decision import LiveStatus

        drop_statuses = (
            LiveStatus.RAPID_DROP,
            LiveStatus.WATCHING_LOW,
            LiveStatus.ENTRY_RECONFIRMED,
        )
        if getattr(ld, "status", None) not in drop_statuses:
            return ""
        if ld.status == LiveStatus.ENTRY_RECONFIRMED:
            return (
                '<div style="font-size:0.67rem;color:#558b2f;margin-top:3px">'
                '轉強觀察訊號 — 進場條件改善，但非正式 BUY 確認；仍需自行評估量價結構</div>'
            )
        rr = getattr(ld, "rr_current", None)
        # VISUAL_ONLY: rr < 1.5 selects stronger caution wording; does not affect execution guidance
        if rr is not None and rr < 1.5:
            return (
                f'<div style="font-size:0.67rem;color:#e65100;margin-top:3px">'
                f'BUY = 模型看好此 Setup ≠ 現價 R/R {rr:.1f}x 就是好時機</div>'
            )
        return (
            '<div style="font-size:0.67rem;color:#888;margin-top:3px">'
            'BUY = 模型看好此 Setup，非現在即可進場的指令</div>'
        )

    @staticmethod
    def plan_str_from_rec(
        entry_low: float | None,
        entry_high: float | None,
        stop_p: float | None,
        t1: float | None,
    ) -> str:
        parts = []
        if entry_low and entry_high:
            parts.append(f"進場 {entry_low:.1f}–{entry_high:.1f}")
        if stop_p:
            parts.append(f"停損 {stop_p:.1f}")
        if t1:
            parts.append(f"T1 {t1:.1f}")
        return "　".join(parts) if parts else "交易計劃待補"
