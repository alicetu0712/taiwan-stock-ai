"""
pages/overview.py — 今日分析頁（今日推薦 + 市場摘要 + Watch List）
"""

import logging
import re
from datetime import date

import streamlit as st

from dashboard.loaders import (
    load_analysis_results,
    load_current_regime,
    load_db_recommendations,
    load_evidence_stats,
    load_exec_logs,
    load_market_health,
    load_opportunity_recs,
    load_pipeline_funnel,
    load_report,
    load_stock_names,
    load_stock_prices,
    load_watch_recs,
    parse_market_summary,
    parse_recs_from_report,
)

logger = logging.getLogger(__name__)


def render_rec_card(r: dict, current_regime: str = "neutral", portfolio_exposure: dict = None) -> None:
    from src.engines.decision import decision_label, tomorrow_triggers, trade_thesis, position_sizing as _ps

    # ── Raw data ────────────────────────────────────────────────
    dl         = decision_label(r)
    triggers   = tomorrow_triggers(r)
    thesis     = trade_thesis(r)
    price      = r.get("price")
    entry_low  = r.get("entry_low")
    entry_high = r.get("entry_high")
    stop_p     = r.get("stop_price") or r.get("stop_loss_price")
    t1         = r.get("target1")
    t2         = r.get("target2") or r.get("target_price")
    atr        = r.get("atr")
    scores     = r.get("scores", {})
    conf       = r.get("confidence", 0)
    level      = r.get("level", "B")
    name       = r.get("name", "")
    sid        = r.get("sid", "")
    setup      = r.get("setup_type") or "none"
    signal     = r.get("trade_signal") or "wait"
    ma20_gap   = r.get("ma20_gap") or 0.0
    pt_val     = r.get("price_trend_score") or 0
    vol_r      = r.get("vol_ratio") or 0.0
    advantages = r.get("advantages", [])
    risks_raw  = r.get("risks", [])
    consecutive = r.get("consecutive_days", 1)
    is_buy     = signal in ("strong_buy", "buy")

    # ── Classify items: financial vs technical ──────────────────
    _FIN_KW = ("EPS", "毛利率", "營益率", "獲利", "財務", "ROE", "負債", "股利", "現金流", "本益比")
    def _is_fin(s): return any(kw in s for kw in _FIN_KW)
    tech_adv  = [a for a in advantages if not _is_fin(a)]
    fin_adv   = [a for a in advantages if _is_fin(a)]
    tech_risk = [x for x in risks_raw if not _is_fin(x)]
    fin_risk  = [x for x in risks_raw if _is_fin(x)]

    # ── Setup-specific narratives ───────────────────────────────
    def _professional_judgment():
        """一行技術判斷，精簡不白話。"""
        if setup == "near_breakout":
            return f"股價接近前 20 日高點，量比 {vol_r:.1f}x，但尚未完成有效突破。"
        if setup == "pullback_buy":
            return "回踩至支撐區，量縮整理後出現轉強訊號，進場條件已成立。" if is_buy else f"多頭趨勢仍在，股價回踩至 MA10 附近（量比 {vol_r:.1f}x），等待止穩確認。"
        if setup == "breakout":
            return f"股價突破前 20 日高點，量比 {vol_r:.1f}x，突破型態確立。"
        if setup == "trending":
            return "多頭趨勢延伸，均線排列健康，動能持續。"
        if setup == "breakdown":
            return "均線轉為空頭排列，趨勢結構已轉弱。"
        if setup == "pullback_hold":
            return "上升趨勢健康回測，MA20 支撐守穩。"
        if setup == "failed_breakout":
            return "突破嘗試失敗，多方假設不再成立。"
        return dl.get("reason", "")

    def _plain_language():
        """💬 白話解釋：不解釋名詞，解釋這對買賣代表什麼。"""
        if setup == "near_breakout":
            return (
                "這檔股票目前走勢不差，也有人在買，但前面還有一道「之前漲不上去的價格」。<br>"
                "現在先不要急著買，等它真的漲過這個位置，證明有能力繼續往上。<br>"
                "突破後如果漲太多、價格已經離合理區間太遠，那就不追，等它回來再說。"
            )
        if setup == "pullback_buy":
            if is_buy:
                return (
                    "這檔股票在上漲途中拉回休息，現在已經確認這個位置撐得住，準備繼續往上。<br>"
                    "這是比較好的進場時機——不是漲很多才追，而是等它回來確認後再買，進場成本相對低。"
                )
            return (
                "這檔股票原本在上漲，最近只是回到平均成本附近休息，目前還沒有明顯轉壞。<br>"
                "現在要看的不是它能不能創新高，而是這個位置能不能撐住。<br>"
                "撐住後重新往上 → 可以考慮買；跌破而且站不回來 → 先不要買。"
            )
        if setup == "breakout":
            return (
                "股價已經突破之前一直過不去的位置，代表買方目前比較強。<br>"
                "現在不是在等突破，而是在看「突破後的價格還值不值得買」。<br>"
                "價格還在合理範圍 → 可以考慮進場；已經衝太高 → 不追，等回檔。"
            )
        if setup == "trending":
            return (
                "這檔股票持續在上漲軌道內，不是突破也不是回踩，就是一路走高。<br>"
                "進場邏輯是：只要趨勢不轉壞，可以繼續跟著走。<br>"
                "最重要的是設好停損，因為趨勢跟蹤最怕突然反轉，停損是保護自己的防線。"
            )
        if setup == "breakdown":
            return (
                "這檔股票的走勢已經往下破壞，不適合用「跌很多所以便宜」的邏輯去買。<br>"
                "持有的人要考慮要不要先出場；沒有持有的人，現在不是買進的時機。"
            )
        if setup == "pullback_hold":
            return (
                "這檔股票目前只是在上漲途中正常整理，趨勢還沒有被破壞。<br>"
                "不需要特別操作，繼續持有，等趨勢回復往上。"
            )
        if setup == "failed_breakout":
            return (
                "原本以為要突破，結果沒成功，而且之後表現疲軟。<br>"
                "這代表之前「準備要上漲」的理由已經不成立了，需要重新評估。"
            )
        return ""

    def _scenario_paths():
        """三條情境路徑，用實際 stop/t1/t2 價格。"""
        s_str = f"${stop_p:.1f}" if stop_p else "停損價"
        t1_str = f"${t1:.1f}" if t1 else "目標一"
        t2_str = f"${t2:.1f}" if t2 else "目標二"
        if setup == "near_breakout":
            scenarios = [
                ("🟢", "突破成功",   f"站上前 20 日高點且量能維持 → 往 {t1_str} / {t2_str} 發展，可依計畫進場。"),
                ("🟡", "碰壓力回檔", f"衝高但無法收在壓力上方 → 拉回測試支撐，守住再等下次突破機會。"),
                ("🔴", "型態失敗",   f"突破失敗後轉弱，跌破 {s_str} → Near Breakout 假設失效，不再等待。"),
            ]
        elif setup == "pullback_buy":
            if is_buy:
                scenarios = [
                    ("🟢", "支撐守穩續升", f"守住 MA10，動能回升 → 往 {t1_str} / {t2_str} 推進。"),
                    ("🟡", "震盪整理再上", "支撐反覆測試，短線震盪 → 整理完成後繼續觀察。"),
                    ("🔴", "跌破支撐",     f"MA10 / MA20 均告失守，跌破 {s_str} → 訊號失效。"),
                ]
            else:
                scenarios = [
                    ("🟢", "止穩轉多",   f"量縮守住 MA10 後反彈 → 進入 BUY 情境，往 {t1_str} 發展。"),
                    ("🟡", "繼續盤整",   "在支撐附近反覆測試 → 繼續 WAIT，觀察後續動能。"),
                    ("🔴", "跌破支撐",   f"無法守住 MA10 / MA20，跌破 {s_str} → 回踩假設失效。"),
                ]
        elif setup == "breakout":
            scenarios = [
                ("🟢", "突破延伸",   f"站穩突破位置，量能持續 → 往 {t1_str} / {t2_str} 發展。"),
                ("🟡", "突破後回測", "漲過快後拉回測試突破點 → 若守住可加碼；若跌破縮手觀望。"),
                ("🔴", "假突破",     f"回跌至突破點以下，量縮 → 跌破 {s_str}，突破假設失效，出場。"),
            ]
        elif setup == "trending":
            scenarios = [
                ("🟢", "趨勢延伸",   f"均線繼續多頭，動能持續 → 往 {t1_str} / {t2_str} 推進。"),
                ("🟡", "短線回測均線", "漲多後小回測試 MA20 → 守住則趨勢完整，繼續持有。"),
                ("🔴", "趨勢反轉",   f"均線死叉或跌破 {s_str} → 趨勢假設失效，出場。"),
            ]
        elif setup == "breakdown":
            scenarios = [
                ("🟢", "強力反彈", "底部有強力量能支撐，有機會快速反彈，但概率低，需謹慎。"),
                ("🟡", "低位盤整", "在低位橫盤，等待訊號明朗化再判斷。"),
                ("🔴", "持續下跌", f"跌破 {s_str} 繼續探底 → 不宜逢低接。"),
            ]
        else:
            return ""
        rows = "".join(
            f'<div style="display:flex;gap:8px;align-items:flex-start;padding:5px 0;'
            f'border-bottom:1px solid #f0f0f0">'
            f'<span style="font-size:0.95rem;flex-shrink:0;line-height:1.4">{icon}</span>'
            f'<div><div style="font-weight:700;font-size:0.74rem;color:#333">{lbl}</div>'
            f'<div style="font-size:0.72rem;color:#555;margin-top:1px;line-height:1.5">{desc}</div></div>'
            f'</div>'
            for icon, lbl, desc in scenarios
        )
        return f"""
<div style="background:#fafafa;border:1px solid #e8eaf0;border-radius:8px;padding:10px 12px;margin:8px 0 4px">
  <div style="font-size:0.62rem;font-weight:700;color:#78909c;letter-spacing:.05em;margin-bottom:6px">未來可能怎麼走</div>
  {rows}
</div>"""

    def _historical_analog_html(ev: dict):
        """歷史類似情境統計，接在情境路徑下方。"""
        re_ev = ev.get("research", {})
        r_n   = re_ev.get("n", 0)
        if r_n < 5:
            return ""
        r20          = re_ev.get("alpha_20d", {})
        r60          = re_ev.get("alpha_60d", {})
        tier_emoji   = re_ev.get("tier_emoji", "🔴")
        median_20    = r20.get("median")
        wr_20        = r20.get("winrate")
        p25_20       = r20.get("p25")
        p75_20       = r20.get("p75")
        median_60    = r60.get("median")
        wr_60        = r60.get("winrate")
        if median_20 is None:
            return (
                f'<div style="font-size:0.7rem;color:#888;padding:4px 0">'
                f'📊 歷史相似情境 {r_n} 次 {tier_emoji}，統計數據尚在累積。</div>'
            )
        sign20 = "+" if median_20 >= 0 else ""
        range_str = (
            f"{p25_20:+.1f}% ～ {p75_20:+.1f}%"
            if (p25_20 is not None and p75_20 is not None) else "—"
        )
        m60_str = f"60D 中位數 {median_60:+.1f}%　60D 勝率 {wr_60:.0f}%" if median_60 is not None else ""
        return f"""
<div style="background:#f8f9fa;border:1px dashed #cfd8dc;border-radius:8px;padding:9px 12px;margin:4px 0 10px">
  <div style="font-size:0.62rem;font-weight:700;color:#78909c;letter-spacing:.05em;margin-bottom:5px">
    📊 歷史相似走勢　{tier_emoji} {r_n} 次類似情境
  </div>
  <div style="font-size:0.75rem;color:#333;line-height:1.75">
    20D 中位數 <b>{sign20}{median_20:.1f}%</b>
    25–75% 範圍 <b>{range_str}</b>
    20D 勝率 <b>{wr_20:.0f}%</b>
    {f"<br>{m60_str}" if m60_str else ""}
  </div>
  <div style="font-size:0.62rem;color:#aaa;margin-top:4px">
    以上為相同 Setup × 市場情境的歷史分布，非 AI 預測。實際路徑受多種因素影響。
  </div>
</div>"""

    def _mc_dist_html(mc: dict):
        """🎲 價格波動模擬：本股歷史波動特性，與 Setup 情境無關。"""
        p50 = mc.get("p50")
        if p50 is None:
            return ""
        p10     = mc.get("p10")
        p25     = mc.get("p25")
        p75     = mc.get("p75")
        p90     = mc.get("p90")
        sigma   = mc.get("sigma_daily")
        n_hist  = mc.get("n_hist", 0)
        sig_str = f"　日波動（σ）{sigma:.1f}%" if sigma else ""
        def _p(v): return f"${v:.1f}" if v is not None else "—"
        return f"""
<div style="background:#f3f4f8;border:1px solid #dce0ec;border-radius:8px;padding:9px 12px;margin:4px 0 10px">
  <div style="font-size:0.62rem;font-weight:700;color:#5c6bc0;letter-spacing:.05em;margin-bottom:5px">
    🎲 價格波動模擬（本股歷史波動特性）
  </div>
  <div style="font-size:0.73rem;color:#333;line-height:1.9">
    20D 分布&nbsp;&nbsp;
    <span style="color:#888;margin-right:3px">10%</span><b>{_p(p10)}</b>&nbsp;&nbsp;
    <span style="color:#888;margin-right:3px">25%</span><b>{_p(p25)}</b>&nbsp;&nbsp;
    <span style="color:#888;margin-right:3px">中位</span><b>{_p(p50)}</b>&nbsp;&nbsp;
    <span style="color:#888;margin-right:3px">75%</span><b>{_p(p75)}</b>&nbsp;&nbsp;
    <span style="color:#888;margin-right:3px">90%</span><b>{_p(p90)}</b>
  </div>
  <div style="font-size:0.62rem;color:#9e9e9e;margin-top:4px">
    依近 {n_hist} 個交易日日報酬（Student-t，零漂移）推算{sig_str}。不反映 Setup 情境、不預測方向。
  </div>
</div>"""

    def _checklist_conclusion():
        """checklist 下方的「所以現在」結論，setup-specific。"""
        if setup == "near_breakout":
            return (
                "<b>所以現在：先等。</b><br>"
                "如果突破成功：看價格是否仍在合理進場區 → 可以買。<br>"
                "如果突破後漲太高：不追，等回檔。<br>"
                "如果一直突破不了：繼續觀察，不要因為等太久而降低標準。"
            )
        if setup == "pullback_buy":
            return (
                "<b>所以現在：等止穩確認。</b><br>"
                "量縮守住支撐 → 進場條件成立，可依計畫買進。<br>"
                "跌破支撐且無法收復 → 觀望，這次回踩可能是轉弱。"
            )
        if setup == "trending":
            return (
                "<b>所以現在：可以考慮進場。</b><br>"
                "在合理進場區買進，設好停損，跟著趨勢走。<br>"
                "若股價短期衝太高脫離均線太遠，等一次小回後再進場。"
            )
        return ""

    def _tech_label():
        if pt_val >= 70: return "偏強", "#2e7d32", "#e8f5e9"
        if pt_val >= 50: return "普通", "#f57f17", "#fff8e1"
        return "偏弱", "#c62828", "#ffebee"

    def _fin_label():
        n_pos, n_neg = len(fin_adv), len(fin_risk)
        if n_pos == 0 and n_neg == 0: return "—", "#888", "#f5f5f5"
        if n_pos > n_neg: return "改善", "#2e7d32", "#e8f5e9"
        if n_neg > n_pos: return "惡化", "#c62828", "#ffebee"
        return "穩定", "#1565c0", "#e3f2fd"

    def _plain_tech():
        if setup == "near_breakout":
            return "趨勢與量能都偏強，目前唯一缺少的是價格正式突破前波壓力。"
        if setup == "pullback_buy":
            return "回踩至支撐已確認止穩，趨勢與量能均符合進場條件。" if is_buy else "趨勢仍在，目前處於回踩整理階段，觀察能否在支撐位止穩轉強。"
        if setup == "breakout":
            vol_desc = f"成交量放大（量比 {vol_r:.1f}x）" if vol_r >= 1.5 else "成交量尚可"
            return f"股價突破前高，{vol_desc}，型態已正式確立。"
        if setup == "trending":
            return "多頭趨勢延伸，均線排列健康，動能持續。"
        if setup == "breakdown":
            return "均線轉為空頭排列，趨勢已轉弱，不宜逢低接。"
        return ""

    def _plain_fundamental():
        n_pos, n_neg = len(fin_adv), len(fin_risk)
        if n_pos == 0 and n_neg == 0:
            return "財務資料不完整，基本面評估暫不可用。"
        if n_pos > n_neg:
            return "公司基本面持續改善，獲利成長提供技術訊號的基本面支撐。"
        if n_neg > n_pos:
            main_risk = fin_risk[0] if fin_risk else ""
            return f"基本面存在隱憂（{main_risk}），技術訊號需搭配更嚴格的進場紀律。"
        return "基本面加分，但獲利空間仍有限，不代表可以忽略買進價格。"

    def _plain_invalidation():
        stop_str = f"${stop_p:.1f}" if stop_p else "停損價"
        if setup == "near_breakout":
            return f"突破失敗後若股價明顯轉弱，或跌破 {stop_str}，原本「準備向上突破」的假設已不成立，不要因為它之前是 {level} 級而硬等。"
        if setup == "pullback_buy":
            return f"若跌破 MA10 且無法收復，或 {stop_str} 被穿破，回踩健康的假設失效，不適合繼續等待。"
        if setup == "breakout":
            return f"若股價回跌至突破點以下且量縮，或跌破 {stop_str}，突破假設失敗，應出場觀望。"
        if setup == "trending":
            return f"若均線出現死叉或 {stop_str} 被跌破，趨勢延伸假設失效。"
        return f"若 {stop_str} 被跌破，訊號假設已不成立。"

    def _checklist():
        if setup == "near_breakout":
            vol_ok = vol_r >= 1.5
            return [
                ("🟢", "趨勢", "符合"),
                ("🟢" if vol_ok else "🟡", "量能", f"符合｜{vol_r:.1f}x" if vol_ok else f"待觀察｜{vol_r:.1f}x"),
                ("🟡", "突破", "尚未確認"),
            ]
        if setup == "pullback_buy":
            vol_ok = vol_r <= 1.2
            return [
                ("🟢", "趨勢", "符合"),
                ("🟢" if is_buy else "🟡", "支撐", "已確認止穩" if is_buy else "近MA10，待確認"),
                ("🟢" if vol_ok else "🟡", "量縮", f"符合｜{vol_r:.1f}x" if vol_ok else f"{vol_r:.1f}x，待收斂"),
            ]
        if setup == "breakout":
            vol_ok = vol_r >= 1.5
            return [
                ("🟢", "趨勢", "符合"),
                ("🟢", "突破", "已確認"),
                ("🟢" if vol_ok else "🟡", "量能", f"符合｜{vol_r:.1f}x" if vol_ok else f"量比 {vol_r:.1f}x，偏弱"),
            ]
        if setup == "trending":
            has_pressure = any("壓力" in x for x in tech_risk)
            return [
                ("🟢", "趨勢", "符合"),
                ("🟢", "動能", "持續延伸"),
                ("🟡" if has_pressure else "🟢", "壓力", "注意前波壓力" if has_pressure else "無明顯壓力"),
            ]
        return []

    # ── Load evidence early (needed for historical analog) ──────
    _ev = {}
    if setup != "none" and signal != "sell":
        try:
            _ev = load_evidence_stats(setup, current_regime)
        except Exception:
            _ev = {}

    # ── Monte Carlo: stock's own historical volatility (NOT setup-conditioned) ──
    _mc: dict = {}
    if price and price > 0:
        try:
            from src.services.evidence_service import monte_carlo_dist
            _mc = monte_carlo_dist(sid, price)
        except Exception:
            _mc = {}

    # ── Build HTML blocks ────────────────────────────────────────
    price_str = f"NT$ {price:,.1f}" if price else "—"
    sig_bg    = "#e8f5e9" if signal == "strong_buy" else "#e3f2fd" if signal == "buy" else "#eceff1"
    sig_col   = "#1a7f4b" if signal == "strong_buy" else "#1565c0" if signal == "buy" else "#546e7a"
    label_text = dl["label"]

    consec_html = (
        f'<span style="font-size:0.63rem;color:#546e7a;background:#eceff1;'
        f'padding:2px 7px;border-radius:10px;margin-left:6px;vertical-align:middle">'
        f'🔄 連續第 {consecutive} 日入選</span>'
    ) if consecutive >= 2 else ""

    t_lbl, t_col, t_bg = _tech_label()
    f_lbl, f_col, f_bg = _fin_label()
    tech_metrics = f"PT {pt_val:.0f}　｜　MA20 {ma20_gap:+.1f}%　｜　量比 {vol_r:.1f}x"

    tech_rows = (
        "".join(f'<div style="color:#2e7d32">✓ {a}</div>' for a in tech_adv[:3]) +
        "".join(f'<div style="color:#c62828">⚠ {x}</div>' for x in tech_risk[:2])
    )
    fin_rows = (
        "".join(f'<div style="color:#2e7d32">✓ {a}</div>' for a in fin_adv[:3]) +
        "".join(f'<div style="color:#c62828">⚠ {x}</div>' for x in fin_risk[:2])
    )

    pt_html = f'<div style="font-size:0.7rem;color:#666;margin-top:4px;font-style:italic">{_plain_tech()}</div>'
    pf_html = f'<div style="font-size:0.7rem;color:#666;margin-top:4px;font-style:italic">{_plain_fundamental()}</div>'

    # Checklist (WAIT only)
    checklist = _checklist()
    check_html = ""
    if checklist and not is_buy:
        rows = "".join(
            f'<div style="display:flex;gap:8px;align-items:center;padding:2px 0">'
            f'<span style="width:20px">{icon}</span>'
            f'<span style="width:50px;font-weight:600;font-size:0.76rem;color:#333">{lbl}</span>'
            f'<span style="font-size:0.76rem;color:#555">{val}</span>'
            f'</div>'
            for icon, lbl, val in checklist
        )
        conclusion = _checklist_conclusion()
        conclusion_html = (
            f'<div style="margin-top:8px;font-size:0.75rem;color:#37474f;line-height:1.65;'
            f'border-top:1px solid #e0e0e0;padding-top:7px">{conclusion}</div>'
        ) if conclusion else ""
        check_html = f"""
<div style="background:#f8f9fa;border-radius:8px;padding:10px 12px;margin:10px 0">
  <div style="font-size:0.62rem;font-weight:700;color:#78909c;letter-spacing:.05em;margin-bottom:6px">現在還差什麼</div>
  {rows}
  {conclusion_html}
</div>"""

    # Triggers (WAIT only — skip BUY)
    trig_html = ""
    if not is_buy and triggers:
        trig_rows = "".join(f'<div style="padding:2px 0;font-size:0.76rem;color:#37474f">{t}</div>' for t in triggers)
        trig_html = f"""
<div style="background:#fafafa;border-left:3px solid #90a4ae;padding:8px 12px;margin:8px 0;border-radius:0 6px 6px 0">
  <div style="font-size:0.62rem;font-weight:700;color:#546e7a;letter-spacing:.05em;margin-bottom:5px">轉為 BUY 的條件</div>
  {trig_rows}
</div>"""

    # Trading plan
    plan_html = ""
    plan_label = "交易計畫" if is_buy else "確認後，怎麼交易"
    plan_opacity = "1" if is_buy else "0.65"
    if price and stop_p and t1:
        risk_pts = price - stop_p
        if risk_pts > 0:
            rr       = round((t1 - price) / risk_pts, 1)
            rr_col   = "#00897b" if rr >= 2.0 else "#ffb300" if rr >= 1.5 else "#e53935"
            e_str    = f"{entry_low:.1f}–{entry_high:.1f}" if (entry_low and entry_high) else f"~{price:.1f}"
            t2_str   = f" / {t2:.1f}" if t2 else ""
            stop_pct = round((stop_p - price) / price * 100, 1)
            t1_pct   = round((t1 - price) / price * 100, 1)
            plan_html = f"""
<div style="opacity:{plan_opacity};background:#f8f9fa;border-radius:8px;padding:10px 12px;margin:10px 0">
  <div style="font-size:0.62rem;font-weight:700;color:#78909c;letter-spacing:.05em;margin-bottom:6px">{plan_label}</div>
  <div style="display:flex;gap:7px;flex-wrap:wrap">
    <div style="flex:1;min-width:60px;background:#fff8e1;border-radius:6px;padding:5px 8px;text-align:center">
      <div style="font-size:0.58rem;color:#f57f17;font-weight:600">進場</div>
      <div style="font-size:0.84rem;font-weight:800;color:#f57f17">{e_str}</div>
    </div>
    <div style="flex:1;min-width:60px;background:#fce4ec;border-radius:6px;padding:5px 8px;text-align:center">
      <div style="font-size:0.58rem;color:#c62828;font-weight:600">停損</div>
      <div style="font-size:0.84rem;font-weight:800;color:#c62828">{stop_p:.1f}</div>
      <div style="font-size:0.58rem;color:#c62828">{stop_pct}%</div>
    </div>
    <div style="flex:1;min-width:60px;background:#e8f5e9;border-radius:6px;padding:5px 8px;text-align:center">
      <div style="font-size:0.58rem;color:#2e7d32;font-weight:600">目標</div>
      <div style="font-size:0.84rem;font-weight:800;color:#2e7d32">{t1:.1f}{t2_str}</div>
      <div style="font-size:0.58rem;color:#2e7d32">+{t1_pct}%</div>
    </div>
    <div style="flex:1;min-width:60px;background:#e3f2fd;border-radius:6px;padding:5px 8px;text-align:center">
      <div style="font-size:0.58rem;color:#1565c0;font-weight:600">R/R</div>
      <div style="font-size:0.84rem;font-weight:800;color:{rr_col}">{rr}x</div>
    </div>
  </div>
</div>"""
    elif entry_low and entry_high and is_buy:
        plan_html = f"""
<div style="background:#fff8e1;border-left:3px solid #f57f17;border-radius:0 6px 6px 0;padding:7px 11px;margin:8px 0">
  <div style="font-size:0.62rem;font-weight:700;color:#e65100;margin-bottom:2px">進場區間</div>
  <div style="font-size:0.95rem;font-weight:800;color:#e65100">NT$ {entry_low:.1f} – {entry_high:.1f}</div>
  <div style="font-size:0.62rem;color:#bf360c;margin-top:2px">停損 / 目標數據待補全</div>
</div>"""

    # Position sizing (BUY only)
    ps_html = ""
    if is_buy and price and stop_p and t1 and price > stop_p:
        from config import POSITION_SIZING as _PS_CFG
        capital      = st.session_state.get("ps_capital",      _PS_CFG["capital_ntd"])
        max_risk_pct = st.session_state.get("ps_max_risk_pct", _PS_CFG["max_risk_pct"])
        ps = _ps(entry=price, stop=stop_p, capital=capital,
                 max_risk_pct=max_risk_pct,
                 max_single_pct=_PS_CFG["max_single_pct"],
                 lot_size=_PS_CFG["lot_size"])
        if ps and ps.get("lots", 0) == 0 and ps.get("min_lot_ntd"):
            ps_html = (
                f'<div style="background:#fff3e0;border-left:3px solid #ff8f00;padding:5px 10px;'
                f'margin:4px 0;border-radius:0 6px 6px 0;font-size:0.72rem;color:#bf360c">'
                f'⚠ 1張需 NT${ps["min_lot_ntd"]:,}，超出曝險上限，無法試算部位。</div>'
            )
        elif ps and ps.get("lots", 0) > 0:
            cap_note = '<span style="color:#e65100">（已達曝險上限）</span>' if ps["capped"] else ""
            ps_html = f"""
<div style="background:#f3e5f5;border-radius:8px;padding:8px 12px;margin:4px 0">
  <div style="font-size:0.62rem;color:#6a1b9a;font-weight:700;margin-bottom:5px">部位試算　風控 {max_risk_pct}% ／ 資金 NT${capital:,.0f}</div>
  <div style="display:flex;gap:6px;flex-wrap:wrap">
    <div style="flex:1;min-width:52px;text-align:center">
      <div style="font-size:0.58rem;color:#7b1fa2">建議張數</div>
      <div style="font-size:0.84rem;font-weight:700;color:#4a148c">{ps['lots']} 張{cap_note}</div>
    </div>
    <div style="flex:1;min-width:52px;text-align:center">
      <div style="font-size:0.58rem;color:#7b1fa2">部位金額</div>
      <div style="font-size:0.84rem;font-weight:700;color:#4a148c">NT${ps['position_ntd']:,}</div>
    </div>
    <div style="flex:1;min-width:52px;text-align:center">
      <div style="font-size:0.58rem;color:#7b1fa2">實際風險</div>
      <div style="font-size:0.84rem;font-weight:700;color:#c62828">NT${ps['actual_risk_ntd']:,}</div>
    </div>
  </div>
</div>"""

    # Portfolio context (BUY only)
    portfolio_html = ""
    if portfolio_exposure and is_buy:
        try:
            from src.services.portfolio_risk_service import portfolio_context_for_stock
            ctx = portfolio_context_for_stock(r.get("industry"), portfolio_exposure)
            if ctx.get("message"):
                w_bg  = "#fff3cd" if ctx["should_warn"] else "#e8f5e9"
                w_bd  = "#ff8f00" if ctx["should_warn"] else "#43a047"
                w_col = "#bf360c" if ctx["should_warn"] else "#2e7d32"
                portfolio_html = f"""
<div style="background:{w_bg};border-left:3px solid {w_bd};padding:5px 10px;margin:4px 0;border-radius:0 6px 6px 0">
  <div style="font-size:0.62rem;color:{w_col};font-weight:600;margin-bottom:1px">組合角度</div>
  <div style="font-size:0.73rem;color:{w_col}">{ctx['message']}</div>
</div>"""
        except Exception:
            pass

    # Invalidation
    inv_html = ""
    inv_items = (thesis.get("invalidations") or []) if thesis else []
    if inv_items:
        inv_rows = "".join(
            f'<div style="color:#c62828;font-size:0.75rem;padding:1px 0">❌ {inv}</div>'
            for inv in inv_items
        )
        inv_html = f"""
<div style="background:#fff8f8;border-left:3px solid #ef9a9a;padding:8px 12px;margin:10px 0;border-radius:0 6px 6px 0">
  <div style="font-size:0.62rem;font-weight:700;color:#b71c1c;letter-spacing:.05em;margin-bottom:5px">什麼情況代表判斷錯了</div>
  {inv_rows}
  <div style="font-size:0.7rem;color:#888;margin-top:5px;font-style:italic">{_plain_invalidation()}</div>
</div>"""

    # Data quality footer string
    dq_str = ""
    dq = r.get("data_quality")
    if dq:
        try:
            from src.validators.stock_data_quality import DQFlag, _FLAG_ICON
            _icon = lambda v: _FLAG_ICON.get(DQFlag(v), "?") if v else "❌"
            _dq_lvl = dq.get("confidence", "medium")
            completeness = "100%" if _dq_lvl == "high" else "85%" if _dq_lvl == "medium" else "70%"
            dq_str = (
                f"資料完整度 {completeness}　"
                f"股價{_icon(dq.get('price'))}　MA60{_icon(dq.get('ma60'))}　"
                f"量能{_icon(dq.get('volume'))}　PT{_icon(dq.get('pt_score'))}　"
                f"法人{_icon(dq.get('institution'))}　財務{_icon(dq.get('financial'))}"
            )
        except Exception:
            pass

    _total_score = scores.get("total") or 0

    # ── Main card HTML ───────────────────────────────────────────
    st.html(f"""
<div style="border:1px solid #e0e0e0;border-radius:12px;padding:16px 18px;margin-bottom:4px;background:#fff">

  <!-- 1. Header -->
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
    <div>
      <span style="font-size:1.1rem;font-weight:800;color:#1a1a2e">{name}</span>
      <span style="font-size:0.78rem;font-weight:400;color:#888;margin-left:6px">{sid}</span>
      {consec_html}
      <div style="font-size:1rem;font-weight:700;color:#333;margin-top:2px">{price_str}</div>
    </div>
    <div style="text-align:right">
      <span style="background:{sig_bg};color:{sig_col};font-weight:800;font-size:0.95rem;padding:5px 14px;border-radius:20px">{label_text}</span>
    </div>
  </div>

  <!-- 2. 專業判斷 + 白話解釋 -->
  <div style="margin-bottom:14px">
    <div style="font-size:0.75rem;color:#546e7a;margin-bottom:6px">{_professional_judgment()}</div>
    <div style="background:#f0f4ff;border-left:3px solid #667eea;border-radius:0 8px 8px 0;
                padding:9px 13px;font-size:0.79rem;color:#333;line-height:1.65">
      <span style="font-weight:700;color:#667eea">💬 白話解釋</span><br>
      {_plain_language()}
    </div>
  </div>

  <!-- 3. 情境路徑 + 歷史類比 + 波動模擬 -->
  {_scenario_paths()}
  {_historical_analog_html(_ev)}
  {_mc_dist_html(_mc)}

  <!-- 4a. 技術面 -->
  <div style="margin-bottom:10px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
      <span style="font-size:0.68rem;font-weight:700;color:#90a4ae;letter-spacing:.06em">技術面</span>
      <span style="background:{t_bg};color:{t_col};font-size:0.63rem;font-weight:700;padding:1px 8px;border-radius:10px">{t_lbl}</span>
      <span style="font-size:0.66rem;color:#b0bec5">{tech_metrics}</span>
    </div>
    <div style="font-size:0.76rem;line-height:1.65;padding-left:4px">{tech_rows}</div>
    {pt_html}
  </div>

  <!-- 3b. 基本面 -->
  <div style="margin-bottom:12px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
      <span style="font-size:0.68rem;font-weight:700;color:#90a4ae;letter-spacing:.06em">基本面</span>
      <span style="background:{f_bg};color:{f_col};font-size:0.63rem;font-weight:700;padding:1px 8px;border-radius:10px">{f_lbl}</span>
    </div>
    <div style="font-size:0.76rem;line-height:1.65;padding-left:4px">{fin_rows}</div>
    {pf_html}
  </div>

  <!-- 4. 現在還差什麼 (WAIT only) -->
  {check_html}

  <!-- 5. 轉為 BUY 的條件 (WAIT only) -->
  {trig_html}

  <!-- 6. 交易計畫 -->
  {plan_html}

  <!-- 7. 部位試算 + 組合角度 (BUY only) -->
  {ps_html}{portfolio_html}

  <!-- 8. 什麼情況代表判斷錯了 -->
  {inv_html}

  <!-- 9. 模型資訊（dimmed） -->
  <div style="font-size:0.62rem;color:#ccc;margin-top:10px;border-top:1px solid #f5f5f5;padding-top:6px;line-height:1.6">
    模型資訊　PT {pt_val:.0f}｜綜合 {_total_score:.0f}｜信心 {conf}%｜{level} 級｜{setup}
    <br>{dq_str}
  </div>

</div>""")

    # ── Expander: raw scores + AI conclusion ────────────────────
    with st.expander("📊 原始評分"):
        col1, col2 = st.columns(2)
        with col1:
            st.metric("綜合", f"{scores.get('total', 0):.0f}")
            st.metric("品質", f"{scores.get('quality', 0):.0f}")
            st.metric("時機", f"{scores.get('timing', 0):.0f}")
        with col2:
            st.metric("籌碼", f"{scores.get('behavior', 0):.0f}")
            st.metric("風險", f"{scores.get('risk', 0):.0f}")
            if atr:
                st.metric("ATR", f"{atr:.2f}")
        conclusion = r.get("conclusion", "")
        if conclusion:
            st.markdown(f"> {conclusion}")

    # ── Data completeness badge ─────────────────────────────────
    _missing_raw = r.get("missing_data_factors") or ""
    _missing_list = [f for f in _missing_raw.split(",") if f] if _missing_raw else []
    _factor_label = {"quality": "基本面", "behavior": "籌碼"}
    if _missing_list:
        _nominal_weights = {"quality": 20, "behavior": 15}
        _missing_pct = sum(_nominal_weights.get(f, 0) for f in _missing_list)
        _completeness = 100 - _missing_pct
        _warn_items = "　".join(f'⚠️ {_factor_label.get(f, f)} 資料缺失' for f in _missing_list)
        _rw_note    = "　".join(f'{_factor_label.get(f, f)} {_nominal_weights.get(f, 0)}% → 重分配至技術面' for f in _missing_list)
        st.html(
            f'<div style="background:#fff8e1;border:1px solid #ffe082;border-radius:7px;'
            f'padding:8px 12px;margin-bottom:8px">'
            f'<span style="font-size:0.68rem;color:#f57f17;font-weight:700">資料完整度 {_completeness}%</span>'
            f'<span style="font-size:0.68rem;color:#e65100;margin-left:10px">{_warn_items}</span>'
            f'<div style="font-size:0.63rem;color:#9e9e9e;margin-top:3px">{_rw_note}；此分數與完整資料的同分標的可信度不同</div>'
            f'</div>'
        )

    # ── Evidence panel (expander only, data already loaded above) ──
    if setup != "none" and signal != "sell":
        ev = _ev
        re_ev = ev.get("research", {})
        fe_ev = ev.get("forward", {})
        narrative    = ev.get("narrative", "")
        r_n          = re_ev.get("n", 0)
        r_tier_emoji = re_ev.get("tier_emoji", "🔴")
        r_tier_label = re_ev.get("tier_label", "樣本不足")
        f_total      = fe_ev.get("total_recorded", 0)
        f_m20        = fe_ev.get("matured_20d", 0)
        f_m60        = fe_ev.get("matured_60d", 0)
        f_tier_emoji = fe_ev.get("tier_emoji", "🔴")
        f_tier_label = fe_ev.get("tier_label", "尚無 OOS 資料")
        _r_wr        = re_ev.get("alpha_20d", {}).get("winrate")
        _r_detail    = (f"（{r_n} 筆，20D 勝率 {_r_wr:.0f}%）" if (r_n >= 10 and _r_wr is not None) else f"（{r_n} 筆）")
        _narrative_html = (
            f'<div style="font-size:0.73rem;color:#555;margin-top:7px;font-style:italic">💬 {narrative}</div>'
            if narrative else ""
        )
        st.html(
            f'<div style="background:#f8f9fa;border:1px solid #e0e0e0;border-radius:8px;'
            f'padding:10px 14px;margin-bottom:8px">'
            f'<div style="font-size:0.65rem;color:#888;font-weight:700;letter-spacing:.05em;margin-bottom:6px">驗證強度</div>'
            f'<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:0.76rem;color:#333">'
            f'<span>🧪 Research：{r_tier_emoji} {r_tier_label} {_r_detail}</span>'
            f'<span>🔒 Forward：{f_tier_emoji} {f_tier_label}（20D 成熟 {f_m20} 筆）</span>'
            f'</div>{_narrative_html}</div>'
        )
        with st.expander(f"📊 類似訊號歷史績效（{setup} × {current_regime}）"):
            st.markdown("**🧪 Research（In-Sample）**")
            if r_n < 10:
                st.caption(f"{r_tier_emoji} 樣本不足（{r_n} 筆），無法計算可靠統計。")
            else:
                r20 = re_ev.get("alpha_20d", {})
                r60 = re_ev.get("alpha_60d", {})
                c1, c2 = st.columns(2)
                with c1:
                    st.metric("類似情境", f"{r_n} 次")
                    if r20.get("mean") is not None: st.metric("20D Alpha 均值", f"{r20['mean']:+.1f}%")
                    if r60.get("mean") is not None: st.metric("60D Alpha 均值", f"{r60['mean']:+.1f}%")
                with c2:
                    if r20.get("winrate") is not None: st.metric("20D 勝率", f"{r20['winrate']:.0f}%")
                    if r60.get("winrate") is not None: st.metric("60D 勝率", f"{r60['winrate']:.0f}%")
                st.caption(f"證據強度：{r_tier_emoji} {r_tier_label}")
            st.divider()
            st.markdown("**🔒 Forward Validation（真實 OOS）**")
            c3, c4 = st.columns(2)
            with c3:
                st.metric("已記錄訊號", f"{f_total} 筆")
                st.metric("20D 已成熟", f"{f_m20} 筆")
                if f_m20 >= 10:
                    f20 = fe_ev.get("alpha_20d", {})
                    if f20.get("mean") is not None: st.metric("20D Alpha", f"{f20['mean']:+.1f}%")
            with c4:
                st.metric("60D 已成熟", f"{f_m60} 筆")
                if f_m20 >= 10:
                    f20 = fe_ev.get("alpha_20d", {})
                    if f20.get("winrate") is not None: st.metric("20D 勝率", f"{f20['winrate']:.0f}%")
            if f_m20 < 10:
                st.caption(f"{f_tier_emoji} Forward 樣本累積中（{f_m20} 筆 20D 已成熟）")
            else:
                st.caption(f"證據強度：{f_tier_emoji} {f_tier_label}")


def page_today(selected_date: date) -> None:
    report = load_report(selected_date)
    logs = load_exec_logs()
    results_df = load_analysis_results(selected_date)
    mkt = parse_market_summary(report) if report else {}

    idx_val = mkt.get("index", "—")
    idx_chg = mkt.get("change", "—")
    sentiment = mkt.get("sentiment", "—")
    try:
        _chg_val = float(str(idx_chg).replace("%", "").replace("+", ""))
        chg_color = (
            "#00c851" if _chg_val > 0 else "#ff4444" if _chg_val < 0 else "#aaaaaa"
        )
    except Exception as e:
        logger.debug(f"index change color parse failed: {e}")
        chg_color = "#aaaaaa"

    today_log = (
        logs[logs["date"] == selected_date]
        if not logs.empty
        else __import__("pandas").DataFrame()
    )
    if today_log.empty:
        try:
            from src.database import ExecutionLog, get_session

            _s = get_session()
            _el = (
                _s.query(ExecutionLog)
                .filter_by(date=selected_date)
                .order_by(ExecutionLog.id.desc())
                .first()
            )
            _s.close()
            if _el:
                import pandas as pd

                today_log = pd.DataFrame(
                    [
                        {
                            "date": _el.date,
                            "status": _el.status,
                            "analyzed": _el.total_stocks,
                            "qualified": _el.qualified_stocks,
                            "recs": _el.recommended_stocks,
                        }
                    ]
                )
        except Exception as e:
            logger.debug(f"today_log DB fallback failed: {e}")
    analyzed = int(today_log.iloc[0]["analyzed"]) if not today_log.empty else 0
    qualified = int(today_log.iloc[0]["qualified"]) if not today_log.empty else 0
    status = today_log.iloc[0]["status"] if not today_log.empty else "—"

    # 直接從 recommendations 表算，避免 execution_log 記錄值與實際不符
    try:
        from sqlalchemy import text as _text
        from src.database import get_session as _gs
        _s = _gs()
        recs_cnt = _s.execute(
            _text("SELECT COUNT(*) FROM recommendations WHERE date=:d AND tier='recommend' AND is_valid IS NOT FALSE"),
            {"d": selected_date},
        ).scalar() or 0
        _s.close()
    except Exception:
        recs_cnt = int(today_log.iloc[0]["recs"]) if not today_log.empty else 0

    st.markdown(
        f"""
    <div class="market-card">
      <div style="display:flex; justify-content:space-between; align-items:flex-start">
        <div>
          <div style="font-size:0.75rem; opacity:0.7">加權指數</div>
          <div class="index-val">{idx_val}</div>
          <div class="index-chg" style="color:{chg_color}">{idx_chg}</div>
        </div>
        <div style="text-align:right">
          <div style="font-size:0.75rem; opacity:0.7">市場情緒</div>
          <div style="font-size:1.1rem; font-weight:700; margin-top:4px">{
            '🟢 偏多' if sentiment == 'Bullish' else '🔴 偏空' if sentiment == 'Bearish' else '⚪ 中性'
          }</div>
          <div style="font-size:0.75rem; opacity:0.7; margin-top:4px">漲 {mkt.get('up', '—')} / 跌 {mkt.get('down', '—')}</div>
        </div>
      </div>
      <div class="market-meta">{selected_date} · AI Taiwan Equity Research v6.8</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
    <div class="stat-grid">
      <div class="stat-box">
        <div class="stat-val">{analyzed}</div>
        <div class="stat-lbl">分析股票</div>
      </div>
      <div class="stat-box">
        <div class="stat-val">{qualified}</div>
        <div class="stat-lbl">通過篩選</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:#764ba2">{recs_cnt}</div>
        <div class="stat-lbl">Core Picks</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="font-size:1.4rem">{'✅' if status == 'success' else '❌' if status == 'failed' else '—'}</div>
        <div class="stat-lbl">執行狀態</div>
      </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    if not report:
        st.warning(f"尚無 {selected_date} 的分析報告，請先執行分析。")
        return

    stock_names = load_stock_names()
    stock_prices = load_stock_prices()
    recs = load_db_recommendations(selected_date)

    for r in recs:
        if not r.get("name"):
            r["name"] = stock_names.get(r["sid"], "")
    for r in recs:
        if r["price"] is None:
            r["price"] = stock_prices.get(r["sid"])

    # P2: Pipeline funnel
    funnel = load_pipeline_funnel(selected_date)
    if funnel:
        universe  = funnel.get("universe", 0)
        with_price = funnel.get("with_price", 0)
        hf_pass   = funnel.get("hard_filter_pass", 0)
        final_rec = funnel.get("recommended", 0)
        st.markdown(
            f"""
<div style="background:#f8f9fa;border-radius:8px;padding:7px 14px;margin:6px 0 10px;font-size:0.74rem;color:#546e7a">
  <span style="font-weight:600">今日掃描漏斗：</span>
  全市場 <b>{universe:,}</b> 檔
  → 有價格 <b>{with_price:,}</b>
  → 通過初篩 <b>{hf_pass}</b>
  → Core Picks <b>{final_rec}</b>
</div>""",
            unsafe_allow_html=True,
        )

    # No-Trade Today banner
    health    = load_market_health(selected_date)
    _h_level  = health.get("level", "green")
    _h_mstatus = health.get("market_status", "TRADING_DAY")
    _h_last_td = health.get("last_trading_day")

    if _h_level == "closed":
        # ── 休市日專用 banner ───────────────────────────────────
        _is_holiday = _h_mstatus == "HOLIDAY"
        _closed_label = "國定假日" if _is_holiday else "週末"
        _last_td_str  = _h_last_td.strftime("%Y/%m/%d") if _h_last_td else "—"
        _note = ""
        if recs:
            _note = (
                f'<div style="font-size:0.74rem;color:#5d4037;margin-top:8px;'
                f'background:#fff3e0;border-radius:6px;padding:5px 10px">'
                f'⚠️ 以下顯示的是 <b>{_last_td_str}</b> 的歷史收盤分析，'
                f'<b>不是 {selected_date} 的新交易訊號</b>。</div>'
            )
        st.markdown(
            f"""
<div style="background:#e8f5e9;border:1.5px solid #a5d6a7;border-radius:10px;padding:12px 16px;margin:8px 0 12px">
  <div style="font-size:1.05rem;font-weight:800;color:#2e7d32;margin-bottom:4px">🟢 今日台股{_closed_label}休市</div>
  <div style="font-size:0.82rem;color:#388e3c">最近有效交易日：<b>{_last_td_str}</b></div>
  {_note}
</div>""",
            unsafe_allow_html=True,
        )

    elif _h_level in ("red", "yellow"):
        # ── 交易日異常 banner ───────────────────────────────────
        _h_regime  = health.get("regime", "neutral")
        _h_pass    = health.get("pass_rate", 0.0)
        _h_conds   = health.get("conditions", [])
        _h_color   = "#c62828" if _h_level == "red" else "#f57f17"
        _h_bg      = "#ffebee" if _h_level == "red" else "#fff8e1"
        _h_border  = "#ef9a9a" if _h_level == "red" else "#ffe082"
        _h_icon    = "🔴" if _h_level == "red" else "🟡"
        _h_title   = "今日不建議交易" if _h_level == "red" else "今日交易需審慎"
        _cond_html = "".join(f'<li style="font-size:0.77rem;margin-bottom:2px">{c}</li>' for c in _h_conds)
        st.markdown(
            f"""
<div style="background:{_h_bg};border:1.5px solid {_h_border};border-radius:10px;padding:12px 16px;margin:8px 0 12px">
  <div style="font-size:1.05rem;font-weight:800;color:{_h_color};margin-bottom:6px">{_h_icon} {_h_title}</div>
  <ul style="margin:0;padding-left:16px;color:{_h_color}">
    {_cond_html}
  </ul>
  <div style="font-size:0.65rem;color:#888;margin-top:6px">通過率 {_h_pass:.1f}% · 市場趨勢 {_h_regime}</div>
</div>""",
            unsafe_allow_html=True,
        )

    # P3: Diversity health warning (monitor only, no scoring change)
    if len(recs) >= 2:
        from collections import Counter
        rec_industries = [r.get("industry", "") for r in recs if r.get("industry")]
        if rec_industries:
            top_ind, top_cnt = Counter(rec_industries).most_common(1)[0]
            if top_cnt == len(recs):
                st.warning(
                    f"⚠️ 多樣性監控：今日 {len(recs)} 支 Core Picks 均屬同一產業（{top_ind}）。"
                    f"市場今日可能高度集中，建議交叉確認是否為整體行情性現象。"
                )

    if not recs:
        recs_section = re.search(
            r"## ③ Research Candidates.*?\n(.*?)(?=## ④|## 免責)", report, re.DOTALL
        )
        content = recs_section.group(1) if recs_section else ""
        recs = parse_recs_from_report(content)
        for r in recs:
            if r.get("price") is None:
                r["price"] = stock_prices.get(r.get("sid", ""))
            p = r.get("price")
            if p and not r.get("target_price"):
                r["target_price"] = round(p * 1.10, 1)
                r["stop_loss_price"] = round(p * 0.93, 1)

    is_fallback = False
    if not recs and not results_df.empty:
        is_fallback = True
        top_df = results_df.head(8)
        for _, row in top_df.iterrows():
            sid = row["stock_id"]
            name = row.get("name") or stock_names.get(sid) or ""
            recs.append(
                {
                    "name": name,
                    "sid": sid,
                    "price": stock_prices.get(sid),
                    "level": row.get("rec_level", "C") or "C",
                    "scores": {
                        "quality": row.get("quality", 0),
                        "timing": row.get("timing", 0),
                        "behavior": row.get("behavior", 0),
                        "risk": row.get("risk", 0),
                        "total": row.get("total", 0),
                    },
                    "confidence": row.get("confidence", 0),
                    "advantages": [],
                    "risks": [],
                    "watch": [],
                    "conclusion": "",
                }
            )

    if recs:
        if is_fallback:
            st.markdown(
                f'<div class="section-title">分析宇宙（{len(recs)} 檔，未達推薦門檻）</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "⚠️ 本日無符合條件的推薦標的（total_score < 65 或 confidence < 70%），以下為分析分數最高的股票，僅供參考。"
            )
        else:
            st.markdown(
                f'<div class="section-title">Core Picks（{len(recs)} 檔）</div>',
                unsafe_allow_html=True,
            )
        current_regime = load_current_regime()
        try:
            from dashboard.loaders import load_portfolio_exposure as _lpe
            portfolio_exposure = _lpe()
        except Exception:
            portfolio_exposure = {}
        cols_data = [recs[i::2] for i in range(2)]
        col_left, col_right = st.columns(2)
        for rec in cols_data[0]:
            with col_left:
                render_rec_card(rec, current_regime, portfolio_exposure)
        for rec in cols_data[1]:
            with col_right:
                render_rec_card(rec, current_regime, portfolio_exposure)
    else:
        st.info("今日尚無分析資料，請先執行分析。")

    # ── New Opportunities（分數動能強勁但在冷卻期外的新股）──────────
    opp_recs = load_opportunity_recs(selected_date)
    if opp_recs:
        st.markdown(
            f'<div class="section-title">🔥 New Opportunities（{len(opp_recs)} 檔，觀察追蹤中）</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "⚡ 分數動能突出但尚未進入正式 Core Picks。追蹤 4–8 週績效後再決定是否納入正式推薦。"
        )
        for opp in opp_recs:
            if not opp.get("name"):
                opp["name"] = stock_names.get(opp["sid"], "")
            if opp["price"] is None:
                opp["price"] = stock_prices.get(opp["sid"])
            sc5  = opp.get("score_change_5d")
            tc5  = opp.get("timing_change_5d")
            bc5  = opp.get("behavior_change_5d")
            sc5_str = f"{sc5:+.1f}" if sc5 is not None else "—"
            tc5_str = f"{tc5:+.1f}" if tc5 is not None else "—"
            bc5_str = f"{bc5:+.1f}" if bc5 is not None else "—"

            def _badge(label, val, val_str, threshold=5):
                bg = "#e65100" if val and val >= threshold else "#37474f"
                arrow = "▲ " if val and val > 0 else ""
                return f'<span style="background:{bg};color:#fff;border-radius:4px;padding:2px 7px;font-size:0.68rem;font-weight:700">{arrow}{label} {val_str}</span>'

            badges = (
                _badge("總5D", sc5, sc5_str, 5)
                + " " + _badge("技術5D", tc5, tc5_str, 8)
                + " " + _badge("籌碼5D", bc5, bc5_str, 8)
            )
            total = opp.get("total_score", opp["scores"].get("total", 0))
            name  = opp.get("name", "") or opp["sid"]
            sid   = opp["sid"]
            price = opp.get("price")
            price_str = f"NT$ {price:,.1f}" if price else "—"
            adv_tags = "".join(
                f'<span class="tag-good">✓ {a[:18]}</span>'
                for a in opp.get("advantages", [])[:2]
            )
            st.markdown(
                f"""
<div style="background:#1a1a2e;border:1px solid #e65100;border-radius:8px;padding:12px 16px;margin-bottom:8px">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px">
    <div>
      <span style="font-weight:700;font-size:1rem;color:#f0f6fc">{name}</span>
      <span style="color:#aaa;font-size:0.75rem;margin-left:8px">{sid} · {price_str}</span>
    </div>
    <span style="background:#333;color:#ddd;border-radius:4px;padding:2px 7px;font-size:0.7rem">總分 {total:.0f}</span>
  </div>
  <div style="margin-top:8px;display:flex;gap:4px;flex-wrap:wrap">{badges}</div>
  {f'<div style="margin-top:6px">{adv_tags}</div>' if adv_tags else ''}
  {f'<div style="color:#ccc;font-size:0.78rem;margin-top:6px">{opp["summary"]}</div>' if opp.get("summary") else ''}
</div>""",
                unsafe_allow_html=True,
            )

    # Watch List — 由 DecisionEngine.select_watchlist() 產生（percentile + min_score + confidence）
    watch_recs_list = load_watch_recs(selected_date)
    if watch_recs_list:
        with st.expander(f"📋 Watch List（{len(watch_recs_list)} 檔，當日相對最強、待觀察）"):
            for w in watch_recs_list:
                sc5 = w.get("score_change_5d")
                sc5_str = f"（5D {sc5:+.1f}）" if sc5 is not None else ""
                display_name = f"{w['name']}（{w['sid']}）" if w['name'] != w['sid'] else w['sid']
                st.markdown(
                    f"**{display_name}** — 綜合 {w['total_score']:.0f} | "
                    f"技術 {w['timing_score']:.0f} | 籌碼 {w['behavior_score']:.0f} | "
                    f"信心 {w['confidence']:.0f}%{sc5_str}"
                )
