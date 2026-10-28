"""
position_presenter.py — Translation layer for Position Monitor card display.

Reads from: position dict (from DB), current price.
Never re-derives: entry/target/stop prices, position sizing formulas,
                  or any engine-level trading decisions.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PositionCard:
    """Pre-built display fragments for one position card."""

    pnl: float | None    # numeric PnL % (used for display and close-action write-back)
    pnl_color: str       # hex colour for PnL text
    pnl_str: str         # "+1.5%" or "—"
    pnl_icon: str        # "🟢" or "🔴"
    price_label: str     # "NT$ 123.45" or "尚無即時報價"
    price_html: str      # complete HTML block: large price + coloured PnL
    progress_html: str   # horizontal price-bar HTML
    summary_caption: str # "倉位 20%　·　B級　·　建倉 2024-01-15"


class PositionPresenter:
    """
    Translate position data and current price into PositionCard display DTO.

    Forbidden: re-computing entry/stop/target prices, position sizing,
               or any engine-level signals.
    """

    def present(self, pos: dict, curr: float | None) -> PositionCard:
        pnl = (
            (curr - pos["entry_price"]) / pos["entry_price"] * 100
            if (curr and pos.get("entry_price"))
            else None
        )
        pnl_positive = (pnl or 0) >= 0
        pnl_color    = "#00897b" if pnl_positive else "#e53935"
        pnl_str      = f"{pnl:+.1f}%" if pnl is not None else "—"
        pnl_icon     = "🟢" if pnl_positive else "🔴"
        price_label  = f"NT$ {curr:.2f}" if curr else "尚無即時報價"

        price_html = (
            f'<div style="margin:2px 0 10px 0">'
            f'<span style="font-size:1.5rem;font-weight:800;color:#222">'
            f'{price_label}</span>'
            f'<span style="font-size:0.95rem;font-weight:700;'
            f'color:{pnl_color};margin-left:10px">{pnl_str}</span>'
            f'</div>'
        )

        progress_html = self._position_progress_html(
            pos.get("entry_price"),
            pos.get("stop_loss_price"),
            pos.get("target_price"),
            curr,
        )

        level = pos.get("rec_level") or "B"
        summary_parts = [level + "級", f"建倉 {pos['date_entered']}"]
        if pos.get("position_pct"):
            summary_parts.insert(0, f"倉位 {pos['position_pct']:.0f}%")
        summary_caption = "　·　".join(summary_parts)

        return PositionCard(
            pnl=pnl,
            pnl_color=pnl_color,
            pnl_str=pnl_str,
            pnl_icon=pnl_icon,
            price_label=price_label,
            price_html=price_html,
            progress_html=progress_html,
            summary_caption=summary_caption,
        )

    @staticmethod
    def _position_progress_html(
        entry: float | None,
        stop: float | None,
        target: float | None,
        curr: float | None,
    ) -> str:
        """Horizontal price bar: stop marker — entry marker — current dot — target marker."""
        if not entry:
            return ""
        lo = (stop or entry) * 0.97
        hi = (target or entry) * 1.03
        if hi <= lo:
            return ""

        def _p(v: float) -> float:
            return max(1.0, min(99.0, (v - lo) / (hi - lo) * 100))

        ep = _p(entry)
        sp = _p(stop) if stop else None
        tp = _p(target) if target else None
        cp = _p(curr) if curr else ep

        if curr is None:
            fill = "#90a4ae"
        elif curr >= entry:
            fill = "#43a047"
        elif stop and curr > stop:
            fill = "#f57f17"
        else:
            fill = "#e53935"

        fill_left  = min(ep, cp)
        fill_width = abs(cp - ep)

        stop_marker = (
            f'<div style="position:absolute;left:{sp:.1f}%;top:-3px;'
            f'width:2px;height:12px;background:#e53935;border-radius:1px"></div>'
            if sp is not None
            else ""
        )
        target_marker = (
            f'<div style="position:absolute;left:{tp:.1f}%;top:-3px;'
            f'width:2px;height:12px;background:#43a047;border-radius:1px"></div>'
            if tp is not None
            else ""
        )
        entry_marker = (
            f'<div style="position:absolute;left:{ep:.1f}%;top:-3px;'
            f'width:2px;height:12px;background:#1565c0;border-radius:1px"></div>'
        )
        curr_dot = (
            f'<div style="position:absolute;left:{cp:.1f}%;top:-5px;width:16px;height:16px;'
            f'background:{fill};border:2px solid white;border-radius:50%;'
            f'transform:translateX(-50%);box-shadow:0 1px 3px rgba(0,0,0,0.25)"></div>'
        )

        stop_lbl   = f"停損 {stop:.1f}" if stop else ""
        entry_lbl  = f"進場 {entry:.1f}"
        curr_lbl   = f"現價 {curr:.1f}" if curr else "尚無報價"
        target_lbl = f"目標 {target:.1f}" if target else ""

        return (
            f'<div style="margin:8px 2px 4px 2px">'
            f'<div style="position:relative;height:6px;background:#e8e8e8;border-radius:3px">'
            f'<div style="position:absolute;left:{fill_left:.1f}%;width:{fill_width:.1f}%;'
            f'height:100%;background:{fill}77;border-radius:3px"></div>'
            f'{stop_marker}{entry_marker}{target_marker}{curr_dot}'
            f'</div>'
            f'<div style="display:flex;justify-content:space-between;'
            f'font-size:0.63rem;margin-top:9px">'
            f'<span style="color:#e53935">{stop_lbl}</span>'
            f'<span style="color:#1565c0">{entry_lbl}</span>'
            f'<span style="color:{fill};font-weight:700">{curr_lbl}</span>'
            f'<span style="color:#43a047">{target_lbl}</span>'
            f'</div>'
            f'</div>'
        )
