"""
evidence_presenter.py — Translation layer for Evidence Dashboard display.

Sample-size classification thresholds are pre-registered in foe_v1 §46.
DO NOT modify these thresholds without upgrading the protocol to foe_v2.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SampleStrength:
    """Sample-size classification per foe_v1 §46."""

    n: int
    label: str           # "不足" / "初步觀察" / "有一定參考" / "可評估穩定性"
    formatted: str       # "N=15（有一定參考）"
    is_insufficient: bool  # n < 10 — show st.warning
    is_initial: bool       # 10 <= n < 30 — show st.info


class EvidencePresenter:
    """
    Translation layer for evidence dashboard display.

    Pre-registered sample-size thresholds (foe_v1 §46):
      n < 10   → "不足"
      n < 30   → "初步觀察"
      n < 100  → "有一定參考"
      else     → "可評估穩定性"

    DO NOT add new Alpha / win-rate / MAE thresholds here.
    DO NOT modify sample-size boundaries without upgrading to foe_v2.
    """

    def sample_strength(self, n: int) -> SampleStrength:
        label = self._n_label(n)
        return SampleStrength(
            n=n,
            label=label,
            formatted=f"N={n}（{label}）",
            is_insufficient=(n < 10),
            is_initial=(10 <= n < 30),
        )

    def overnight_group_headline_html(
        self,
        green_g: dict | None,
        red_g: dict | None,
    ) -> str | None:
        """
        Build the GREEN vs RED Alpha headline HTML.

        Returns None when either group has fewer than 5 records or non-numeric alpha.
        The caller should fall back to st.caption("各組樣本尚不足 5 筆，暫無 Alpha 摘要。").
        """
        if (
            green_g is None
            or red_g is None
            or not isinstance(green_g.get("20D Alpha (avg %)"), float)
            or not isinstance(red_g.get("20D Alpha (avg %)"), float)
        ):
            return None

        diff       = green_g["20D Alpha (avg %)"] - red_g["20D Alpha (avg %)"]
        diff_color = "#00897b" if diff >= 0 else "#e53935"
        ss_green   = self.sample_strength(green_g["N"])
        ss_red     = self.sample_strength(red_g["N"])

        return (
            f'<div style="padding:8px 12px;background:#f8f9fa;border-radius:6px;'
            f'font-size:0.82rem;color:#555;margin-bottom:8px">'
            f'GREEN 組平均 Alpha '
            f'<strong style="color:#00897b">{green_g["20D Alpha (avg %)"]:+.2f}%</strong>'
            f'（{ss_green.formatted}）　RED 組 '
            f'<strong style="color:#e53935">{red_g["20D Alpha (avg %)"]:+.2f}%</strong>'
            f'（{ss_red.formatted}）　差距 '
            f'<strong style="color:{diff_color}">{diff:+.2f}%</strong>'
            f'</div>'
        )

    @staticmethod
    def _n_label(n: int) -> str:
        if n < 10:
            return "不足"
        if n < 30:
            return "初步觀察"
        if n < 100:
            return "有一定參考"
        return "可評估穩定性"
