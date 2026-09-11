"""
pages/overview.py — 今日分析頁（今日推薦 + 市場摘要 + Watch List）
"""

import logging
import re
from datetime import date

import streamlit as st

from dashboard.loaders import (
    load_analysis_results,
    load_db_recommendations,
    load_exec_logs,
    load_opportunity_recs,
    load_report,
    load_stock_names,
    load_stock_prices,
    load_watch_recs,
    parse_market_summary,
    parse_recs_from_report,
)

logger = logging.getLogger(__name__)


def render_rec_card(r: dict) -> None:
    level = r.get("level", "B")
    grade_c = "Aplus" if level == "A+" else level
    scores = r.get("scores", {})
    conf = r.get("confidence", 0)
    conf_color = "#00c851" if conf >= 80 else "#ffbb33" if conf >= 60 else "#ff4444"

    score_bars = ""
    for lbl, sub, key, color in [
        ("品質", "財務體質", "quality", "#667eea"),
        ("時機", "技術進場", "timing", "#33b5e5"),
        ("籌碼", "法人動向", "behavior", "#ff8800"),
        ("風險", "波動風險", "risk", "#00c851"),
        ("綜合", "加權總分", "total", "#764ba2"),
    ]:
        val = scores.get(key, 0)
        score_bars += (
            f'<div class="score-row">'
            f'<span class="score-lbl">{lbl}<span style="font-size:0.65rem;color:#aaa;display:block;line-height:1">{sub}</span></span>'
            f'<div class="score-bar"><div class="score-fill" style="width:{val}%;background:{color}"></div></div>'
            f'<span class="score-num" style="color:{color}">{val}</span>'
            f"</div>"
        )

    adv_tags = "".join(
        f'<span class="tag-good">✓ {a[:18]}</span>' for a in r.get("advantages", [])[:3]
    )
    risk_tags = "".join(
        f'<span class="tag-risk">⚠ {r2[:18]}</span>' for r2 in r.get("risks", [])[:2]
    )
    watch_tags = "".join(
        f'<span class="tag-watch">👁 {w[:20]}</span>' for w in r.get("watch", [])[:2]
    )

    price = r.get("price")
    price_str = f"　NT$ {price:,.1f}" if price else ""

    target_price = r.get("target_price")
    stop_loss_price = r.get("stop_loss_price")
    position_pct = r.get("position_pct")
    target_is_est = False
    if price and not target_price:
        target_price = round(price * 1.10, 1)
        stop_loss_price = round(price * 0.93, 1)
        target_is_est = True
    price_block = ""
    if price and target_price:
        target_pct = round((target_price - price) / price * 100, 1)
        stoploss_pct = round((stop_loss_price - price) / price * 100, 1)
        pos_str = f"　建議部位 {position_pct:.0f}%" if position_pct else ""
        tp_label = "目標價 (估)" if target_is_est else "目標價"
        sl_label = "停損價 (估)" if target_is_est else "停損價"
        price_block = f"""
      <div style="display:flex;gap:8px;margin:8px 0 4px;flex-wrap:wrap">
        <div style="flex:1;min-width:80px;background:#e8f5e9;border-radius:6px;padding:6px 10px;text-align:center">
          <div style="font-size:0.65rem;color:#2e7d32;font-weight:600">{tp_label}</div>
          <div style="font-size:0.95rem;font-weight:800;color:#2e7d32">{target_price:,.1f}</div>
          <div style="font-size:0.65rem;color:#2e7d32">+{target_pct}%</div>
        </div>
        <div style="flex:1;min-width:80px;background:#fce4ec;border-radius:6px;padding:6px 10px;text-align:center">
          <div style="font-size:0.65rem;color:#c62828;font-weight:600">{sl_label}</div>
          <div style="font-size:0.95rem;font-weight:800;color:#c62828">{stop_loss_price:,.1f}</div>
          <div style="font-size:0.65rem;color:#c62828">{stoploss_pct}%</div>
        </div>
        <div style="flex:1;min-width:80px;background:#f3e5f5;border-radius:6px;padding:6px 10px;text-align:center">
          <div style="font-size:0.65rem;color:#6a1b9a;font-weight:600">現價</div>
          <div style="font-size:0.95rem;font-weight:800;color:#6a1b9a">{price:,.1f}</div>
          <div style="font-size:0.65rem;color:#6a1b9a">{pos_str.strip() or '—'}</div>
        </div>
      </div>"""

    name = r.get("name", "")
    sid = r.get("sid", "")
    name_html = (
        f'<div class="rec-name">{name}</div><div class="rec-sid">{sid} · TWSE{price_str}</div>'
        if name and name != sid
        else f'<div class="rec-name">{sid}</div><div class="rec-sid">TWSE{price_str}</div>'
    )
    st.markdown(
        f"""
    <div class="rec-card grade-{grade_c}">
      <div class="rec-header">
        <div>
          {name_html}
        </div>
        <span class="rec-badge badge-{grade_c}">{level} 級</span>
      </div>
      {score_bars}
      {price_block}
      <div class="tags">{adv_tags}{risk_tags}</div>
      {f'<div class="tags">{watch_tags}</div>' if watch_tags else ''}
      <div class="confidence-row">
        <span class="confidence-lbl">分析信心度</span>
        <span class="confidence-val" style="color:{conf_color}">{conf}%</span>
      </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    if r.get("conclusion"):
        with st.expander("📝 AI 結論"):
            st.markdown(f"> {r['conclusion']}")


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
    recs_cnt = int(today_log.iloc[0]["recs"]) if not today_log.empty else 0
    status = today_log.iloc[0]["status"] if not today_log.empty else "—"

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
        <div class="stat-lbl">今日推薦</div>
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
        if r["price"] is None:
            r["price"] = stock_prices.get(r["sid"])
    for r in recs:
        p = r.get("price")
        if p and not r.get("target_price"):
            r["target_price"] = round(p * 1.10, 1)
            r["stop_loss_price"] = round(p * 0.93, 1)

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
        cols_data = [recs[i::2] for i in range(2)]
        col_left, col_right = st.columns(2)
        for rec in cols_data[0]:
            with col_left:
                render_rec_card(rec)
        for rec in cols_data[1]:
            with col_right:
                render_rec_card(rec)
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
      <span style="font-weight:700;font-size:1rem">{name}</span>
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
