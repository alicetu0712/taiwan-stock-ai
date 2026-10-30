"""
decision_presenter.py — Translation layer between engine output and display.

Rules:
- Reads from the r dict (engine output); never re-derives signals or scores.
- All setup-type → text mappings are static lookup tables.
- Dynamic formatting (e.g. inserting stop_p into invalidation text) reads
  raw metric values from r but does not perform any signal logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ── Static translation tables ────────────────────────────────────────────────

_SETUP_LABEL: dict[str, str] = {
    "near_breakout": "Near Breakout",
    "pullback_buy": "Pullback Buy",
    "breakout": "Breakout",
    "trending": "趨勢延伸",
    "breakdown": "趨勢轉弱",
    "pullback_hold": "回測整理",
    "failed_breakout": "突破失敗",
    "none": "無明確型態",
}

# signal → (display_label, text_color, bg_color)
_SIGNAL_ATTRS: dict[str, tuple[str, str, str]] = {
    "strong_buy": ("BUY ▲", "#1a7f4b", "#e8f5e9"),
    "buy": ("BUY", "#1565c0", "#e3f2fd"),
    "wait": ("WAIT", "#546e7a", "#eceff1"),
    "sell": ("SELL", "#c62828", "#ffebee"),
}

# (setup, is_buy) → plain-language HTML (br-separated sentences)
_WHY_HTML: dict[tuple[str, bool], str] = {
    ("near_breakout", True): (
        "這檔股票目前走勢不差，也有人在買，但前面還有一道「之前漲不上去的價格」。<br>"
        "現在先不要急著買，等它真的漲過這個位置，證明有能力繼續往上。<br>"
        "突破後如果漲太多、價格已經離合理區間太遠，那就不追，等它回來再說。"
    ),
    ("near_breakout", False): (
        "這檔股票目前走勢不差，也有人在買，但前面還有一道「之前漲不上去的價格」。<br>"
        "現在先不要急著買，等它真的漲過這個位置，證明有能力繼續往上。<br>"
        "突破後如果漲太多、價格已經離合理區間太遠，那就不追，等它回來再說。"
    ),
    ("pullback_buy", True): (
        "這檔股票在上漲途中拉回休息，現在已經確認這個位置撐得住，準備繼續往上。<br>"
        "這是比較好的進場時機——不是漲很多才追，而是等它回來確認後再買，進場成本相對低。"
    ),
    ("pullback_buy", False): (
        "這檔股票原本在上漲，最近只是回到平均成本附近休息，目前還沒有明顯轉壞。<br>"
        "現在要看的不是它能不能創新高，而是這個位置能不能撐住。<br>"
        "撐住後重新往上 → 可以考慮買；跌破而且站不回來 → 先不要買。"
    ),
    ("breakout", True): (
        "股價已經突破之前一直過不去的位置，代表買方目前比較強。<br>"
        "現在不是在等突破，而是在看「突破後的價格還值不值得買」。<br>"
        "價格還在合理範圍 → 可以考慮進場；已經衝太高 → 不追，等回檔。"
    ),
    ("breakout", False): (
        "股價已經突破之前一直過不去的位置，代表買方目前比較強。<br>"
        "現在不是在等突破，而是在看「突破後的價格還值不值得買」。<br>"
        "價格還在合理範圍 → 可以考慮進場；已經衝太高 → 不追，等回檔。"
    ),
    ("trending", True): (
        "這檔股票持續在上漲軌道內，不是突破也不是回踩，就是一路走高。<br>"
        "進場邏輯是：只要趨勢不轉壞，可以繼續跟著走。<br>"
        "最重要的是設好停損，因為趨勢跟蹤最怕突然反轉，停損是保護自己的防線。"
    ),
    ("trending", False): (
        "這檔股票持續在上漲軌道內，不是突破也不是回踩，就是一路走高。<br>"
        "進場邏輯是：只要趨勢不轉壞，可以繼續跟著走。<br>"
        "最重要的是設好停損，因為趨勢跟蹤最怕突然反轉，停損是保護自己的防線。"
    ),
    ("breakdown", True): (
        "這檔股票的走勢已經往下破壞，不適合用「跌很多所以便宜」的邏輯去買。<br>"
        "持有的人要考慮要不要先出場；沒有持有的人，現在不是買進的時機。"
    ),
    ("breakdown", False): (
        "這檔股票的走勢已經往下破壞，不適合用「跌很多所以便宜」的邏輯去買。<br>"
        "持有的人要考慮要不要先出場；沒有持有的人，現在不是買進的時機。"
    ),
    ("pullback_hold", True): (
        "這檔股票目前只是在上漲途中正常整理，趨勢還沒有被破壞。<br>"
        "不需要特別操作，繼續持有，等趨勢回復往上。"
    ),
    ("pullback_hold", False): (
        "這檔股票目前只是在上漲途中正常整理，趨勢還沒有被破壞。<br>"
        "不需要特別操作，繼續持有，等趨勢回復往上。"
    ),
    ("failed_breakout", True): (
        "原本以為要突破，結果沒成功，而且之後表現疲軟。<br>"
        "這代表之前「準備要上漲」的理由已經不成立了，需要重新評估。"
    ),
    ("failed_breakout", False): (
        "原本以為要突破，結果沒成功，而且之後表現疲軟。<br>"
        "這代表之前「準備要上漲」的理由已經不成立了，需要重新評估。"
    ),
}

# setup → WAIT-state checklist conclusion
_CHECKLIST_CONCLUSION: dict[str, str] = {
    "near_breakout": (
        "<b>所以現在：先等。</b><br>"
        "如果突破成功：看價格是否仍在合理進場區 → 可以買。<br>"
        "如果突破後漲太高：不追，等回檔。<br>"
        "如果一直突破不了：繼續觀察，不要因為等太久而降低標準。"
    ),
    "pullback_buy": (
        "<b>所以現在：等止穩確認。</b><br>"
        "量縮守住支撐 → 進場條件成立，可依計畫買進。<br>"
        "跌破支撐且無法收復 → 觀望，這次回踩可能是轉弱。"
    ),
    "trending": (
        "<b>所以現在：可以考慮進場。</b><br>"
        "在合理進場區買進，設好停損，跟著趨勢走。<br>"
        "若股價短期衝太高脫離均線太遠，等一次小回後再進場。"
    ),
}

_FIN_KW = (
    "EPS",
    "毛利率",
    "營益率",
    "獲利",
    "財務",
    "ROE",
    "負債",
    "股利",
    "現金流",
    "本益比",
)


# ── Data class ───────────────────────────────────────────────────────────────


@dataclass
class DecisionCard:
    # Identity
    name: str
    sid: str
    price_str: str
    level: str
    conf: float
    setup: str
    setup_label: str
    total_score: float
    pt_val: float
    consecutive: int

    # Level 1 — action + why + plan + invalidation + evidence
    signal_label: str
    signal_col: str
    signal_bg: str
    why_html: str
    invalidation_text: str
    evidence_summary: str

    # Level 2 — "為什麼這樣判斷？" expander
    pro_judgment: str
    checklist: list  # [(icon, lbl, val), ...]
    checklist_conclusion: str
    scenarios: list  # [(icon, lbl, desc), ...]

    # Level 3 — "專業數據" expander
    tech_metrics: str
    ma20_gap: float
    vol_ratio: float
    tech_adv: list
    tech_risk: list
    fin_adv: list
    fin_risk: list
    plain_tech: str
    plain_fundamental: str
    dq_str: str


# ── Presenter ────────────────────────────────────────────────────────────────


class DecisionPresenter:
    """
    Translate engine output (r dict + optional ev stats) into DecisionCard.
    Never re-derives BUY/WAIT/SELL, PT Score, or any risk/signal value.
    """

    def present(self, r: dict, ev: dict | None = None) -> DecisionCard:
        setup = r.get("setup_type") or "none"
        signal = r.get("trade_signal") or "wait"
        is_buy = signal in ("strong_buy", "buy")
        conf = float(r.get("confidence") or 0)
        level = r.get("level") or "B"
        name = r.get("name") or ""
        sid = r.get("sid") or ""
        price = r.get("price")
        stop_p = r.get("stop_price") or r.get("stop_loss_price")
        t1 = r.get("target1")
        t2 = r.get("target2") or r.get("target_price")
        ma20_gap = float(r.get("ma20_gap") or 0.0)
        pt_val = float(r.get("price_trend_score") or 0)
        vol_r = float(r.get("vol_ratio") or 0.0)
        advantages = r.get("advantages") or []
        risks_raw = r.get("risks") or []
        scores = r.get("scores") or {}
        consecutive = int(r.get("consecutive_days") or 1)

        price_str = f"NT$ {price:,.1f}" if price else "—"
        total_score = float(scores.get("total") or 0)

        sig_label, sig_col, sig_bg = _SIGNAL_ATTRS.get(
            signal, ("WAIT", "#546e7a", "#eceff1")
        )

        tech_adv = [a for a in advantages if not any(kw in a for kw in _FIN_KW)]
        fin_adv = [a for a in advantages if any(kw in a for kw in _FIN_KW)]
        tech_risk = [x for x in risks_raw if not any(kw in x for kw in _FIN_KW)]
        fin_risk = [x for x in risks_raw if any(kw in x for kw in _FIN_KW)]

        return DecisionCard(
            name=name,
            sid=sid,
            price_str=price_str,
            level=level,
            conf=conf,
            setup=setup,
            setup_label=_SETUP_LABEL.get(setup, setup),
            total_score=total_score,
            pt_val=pt_val,
            consecutive=consecutive,
            signal_label=sig_label,
            signal_col=sig_col,
            signal_bg=sig_bg,
            why_html=self._why_html(setup, is_buy),
            invalidation_text=self._invalidation_text(setup, stop_p, level),
            evidence_summary=self._evidence_summary(ev or {}),
            pro_judgment=self._pro_judgment(setup, is_buy, vol_r, ma20_gap),
            checklist=self._checklist(setup, is_buy, vol_r, tech_risk),
            checklist_conclusion=_CHECKLIST_CONCLUSION.get(setup, ""),
            scenarios=self._scenarios(setup, is_buy, stop_p, t1, t2),
            tech_metrics=f"PT {pt_val:.0f}　｜　MA20 {ma20_gap:+.1f}%　｜　量比 {vol_r:.1f}x",
            ma20_gap=ma20_gap,
            vol_ratio=vol_r,
            tech_adv=tech_adv,
            tech_risk=tech_risk,
            fin_adv=fin_adv,
            fin_risk=fin_risk,
            plain_tech=self._plain_tech(setup, is_buy, vol_r),
            plain_fundamental=self._plain_fundamental(fin_adv, fin_risk),
            dq_str=self._dq_str(r.get("data_quality")),
        )

    def _why_html(self, setup: str, is_buy: bool) -> str:
        key = (setup, is_buy)
        if key in _WHY_HTML:
            return _WHY_HTML[key]
        # fallback: try opposite is_buy
        fallback = (setup, not is_buy)
        return _WHY_HTML.get(fallback, "")

    def _invalidation_text(
        self, setup: str, stop_p: Optional[float], level: str
    ) -> str:
        stop_str = f"${stop_p:.1f}" if stop_p else "停損價"
        if setup == "near_breakout":
            return (
                f"突破失敗後若股價明顯轉弱，或跌破 {stop_str}，"
                f"原本「準備向上突破」的假設已不成立，不要因為它之前是 {level} 級而硬等。"
            )
        if setup == "pullback_buy":
            return (
                f"若跌破 MA10 且無法收復，或 {stop_str} 被穿破，"
                "回踩健康的假設失效，不適合繼續等待。"
            )
        if setup == "breakout":
            return (
                f"若股價回跌至突破點以下且量縮，或跌破 {stop_str}，"
                "突破假設失敗，應出場觀望。"
            )
        if setup == "trending":
            return f"若均線出現死叉或 {stop_str} 被跌破，趨勢延伸假設失效。"
        return f"若 {stop_str} 被跌破，訊號假設已不成立。"

    def _evidence_summary(self, ev: dict) -> str:
        re_ev = ev.get("research", {})
        n = re_ev.get("n", 0)
        if n < 5:
            return ""
        alpha_20 = re_ev.get("alpha_20d", {})
        median = alpha_20.get("median")
        winrate = alpha_20.get("winrate")
        tier = re_ev.get("tier_emoji", "")
        if median is None or winrate is None:
            return f"歷史相似情境 {n} 次 {tier}，統計數據累積中。"
        sign = "+" if median >= 0 else ""
        return (
            f"歷史 {n} 次相似情境 {tier}，"
            f"20日中位數 {sign}{median:.1f}%，勝率 {winrate:.0f}%。"
        )

    def _pro_judgment(
        self, setup: str, is_buy: bool, vol_r: float, ma20_gap: float
    ) -> str:
        mapping: dict[str, str] = {
            "near_breakout": f"股價接近前 20 日高點，量比 {vol_r:.1f}x，但尚未完成有效突破。",
            "pullback_buy": (
                "回踩至支撐區，模型已出現進場訊號，確認支撐成立。"
                if is_buy
                else f"多頭趨勢仍在，股價回踩至 MA10 附近（量比 {vol_r:.1f}x），等待止穩確認。"
            ),
            "breakout": f"股價突破前 20 日高點，量比 {vol_r:.1f}x，突破型態確立。",
            "trending": "多頭趨勢延伸，均線排列健康，動能持續。",
            "breakdown": "均線轉為空頭排列，趨勢結構已轉弱。",
            "pullback_hold": "上升趨勢健康回測，MA20 支撐守穩。",
            "failed_breakout": "突破嘗試失敗，多方假設不再成立。",
        }
        return mapping.get(setup, "")

    def _checklist(
        self, setup: str, is_buy: bool, vol_r: float, tech_risk: list
    ) -> list:
        if setup == "near_breakout":
            return [
                ("🟢", "趨勢", "符合"),
                ("🟡", "量能", f"目前 {vol_r:.1f}x（近 20 日均量）"),
                ("🟡", "突破", "尚未確認"),
            ]
        if setup == "pullback_buy":
            return [
                ("🟢", "趨勢", "符合"),
                (
                    "🟢" if is_buy else "🟡",
                    "支撐",
                    "已確認止穩" if is_buy else "近MA10，待確認",
                ),
                ("🟡", "量能", f"目前 {vol_r:.1f}x（近 20 日均量）"),
            ]
        if setup == "breakout":
            return [
                ("🟢", "趨勢", "符合"),
                ("🟢", "突破", "已確認"),
                ("🟡", "量能", f"目前 {vol_r:.1f}x（近 20 日均量）"),
            ]
        if setup == "trending":
            has_pressure = any("壓力" in x for x in tech_risk)
            return [
                ("🟢", "趨勢", "符合"),
                ("🟢", "動能", "持續延伸"),
                (
                    "🟡" if has_pressure else "🟢",
                    "壓力",
                    "注意前波壓力" if has_pressure else "無明顯壓力",
                ),
            ]
        return []

    def _scenarios(
        self,
        setup: str,
        is_buy: bool,
        stop_p: Optional[float],
        t1: Optional[float],
        t2: Optional[float],
    ) -> list:
        s_str = f"${stop_p:.1f}" if stop_p else "停損價"
        t1_str = f"${t1:.1f}" if t1 else "目標一"
        t2_str = f"${t2:.1f}" if t2 else "目標二"
        if setup == "near_breakout":
            return [
                (
                    "🟢",
                    "突破成功",
                    f"站上前 20 日高點且量能維持 → 往 {t1_str} / {t2_str} 發展，可依計畫進場。",
                ),
                (
                    "🟡",
                    "碰壓力回檔",
                    "衝高但無法收在壓力上方 → 拉回測試支撐，守住再等下次突破機會。",
                ),
                (
                    "🔴",
                    "型態失敗",
                    f"突破失敗後轉弱，跌破 {s_str} → Near Breakout 假設失效，不再等待。",
                ),
            ]
        if setup == "pullback_buy":
            if is_buy:
                return [
                    (
                        "🟢",
                        "支撐守穩續升",
                        f"守住 MA10，動能回升 → 往 {t1_str} / {t2_str} 推進。",
                    ),
                    (
                        "🟡",
                        "震盪整理再上",
                        "支撐反覆測試，短線震盪 → 整理完成後繼續觀察。",
                    ),
                    (
                        "🔴",
                        "跌破支撐",
                        f"MA10 / MA20 均告失守，跌破 {s_str} → 訊號失效。",
                    ),
                ]
            return [
                (
                    "🟢",
                    "止穩轉多",
                    f"量縮守住 MA10 後反彈 → 進入 BUY 情境，往 {t1_str} 發展。",
                ),
                ("🟡", "繼續盤整", "在支撐附近反覆測試 → 繼續 WAIT，觀察後續動能。"),
                (
                    "🔴",
                    "跌破支撐",
                    f"無法守住 MA10 / MA20，跌破 {s_str} → 回踩假設失效。",
                ),
            ]
        if setup == "breakout":
            return [
                (
                    "🟢",
                    "突破延伸",
                    f"站穩突破位置，量能持續 → 往 {t1_str} / {t2_str} 發展。",
                ),
                (
                    "🟡",
                    "突破後回測",
                    "漲過快後拉回測試突破點 → 若守住可加碼；若跌破縮手觀望。",
                ),
                (
                    "🔴",
                    "假突破",
                    f"回跌至突破點以下，量縮 → 跌破 {s_str}，突破假設失效，出場。",
                ),
            ]
        if setup == "trending":
            return [
                (
                    "🟢",
                    "趨勢延伸",
                    f"均線繼續多頭，動能持續 → 往 {t1_str} / {t2_str} 推進。",
                ),
                (
                    "🟡",
                    "短線回測均線",
                    "漲多後小回測試 MA20 → 守住則趨勢完整，繼續持有。",
                ),
                (
                    "🔴",
                    "趨勢反轉",
                    f"均線死叉或跌破 {s_str} → 趨勢假設失效，出場。",
                ),
            ]
        if setup == "breakdown":
            return [
                (
                    "🟢",
                    "強力反彈",
                    "底部有強力量能支撐，有機會快速反彈，但概率低，需謹慎。",
                ),
                ("🟡", "低位盤整", "在低位橫盤，等待訊號明朗化再判斷。"),
                ("🔴", "持續下跌", f"跌破 {s_str} 繼續探底 → 不宜逢低接。"),
            ]
        return []

    def _plain_tech(self, setup: str, is_buy: bool, vol_r: float) -> str:
        if setup == "near_breakout":
            return "趨勢結構偏強，目前唯一缺少的是價格正式突破前波壓力。"
        if setup == "pullback_buy":
            if is_buy:
                return "回踩至支撐已確認，模型發出進場訊號。"
            return "趨勢仍在，目前處於回踩整理階段，觀察能否在支撐位止穩轉強。"
        if setup == "breakout":
            return f"股價突破前高，成交量 {vol_r:.1f}x，型態已正式確立。"
        if setup == "trending":
            return "多頭趨勢延伸，均線排列健康，動能持續。"
        if setup == "breakdown":
            return "均線轉為空頭排列，趨勢已轉弱，不宜逢低接。"
        return ""

    def _plain_fundamental(self, fin_adv: list, fin_risk: list) -> str:
        n_pos, n_neg = len(fin_adv), len(fin_risk)
        if n_pos == 0 and n_neg == 0:
            return "財務資料不完整，基本面評估暫不可用。"
        if n_pos > n_neg:
            return "公司基本面持續改善，獲利成長提供技術訊號的基本面支撐。"
        if n_neg > n_pos:
            main_risk = fin_risk[0] if fin_risk else ""
            return f"基本面存在隱憂（{main_risk}），技術訊號需搭配更嚴格的進場紀律。"
        return "基本面加分，但獲利空間仍有限，不代表可以忽略買進價格。"

    def _dq_str(self, dq: Optional[dict]) -> str:
        if not dq:
            return ""
        try:
            from src.validators.stock_data_quality import _FLAG_ICON, DQFlag

            def _icon(v: object) -> str:
                return _FLAG_ICON.get(DQFlag(v), "?") if v else "❌"

            _dq_lvl = dq.get("confidence", "medium")
            quality_label = {
                "high": "資料品質：完整",
                "medium": "資料品質：普通",
                "low": "資料品質：不足",
            }.get(_dq_lvl, "資料品質：普通")
            return (
                f"{quality_label}　"
                f"股價{_icon(dq.get('price'))}　MA60{_icon(dq.get('ma60'))}　"
                f"量能{_icon(dq.get('volume'))}　PT{_icon(dq.get('pt_score'))}　"
                f"法人{_icon(dq.get('institution'))}　財務{_icon(dq.get('financial'))}"
            )
        except Exception:
            return ""
