"""
pages/my_trades.py — 我的實際交易紀錄頁
"""

import logging
from datetime import date

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from dashboard.db import DailyPrice, UserTrade, get_session
from dashboard.loaders import load_stock_list, load_stock_prices

logger = logging.getLogger(__name__)

BUY_FEE = 0.001425  # 買入手續費
SELL_FEE = 0.004425  # 賣出手續費 + 證交稅


def _render_trade_mc(
    trade, current_price: float, n_sim: int = 500, days: int = 20
) -> None:
    """從當前價格做 Monte Carlo 20 日預測"""
    try:
        from sqlalchemy import desc as _d

        sess = get_session()
        prices_db = (
            sess.query(DailyPrice)
            .filter_by(stock_id=trade.stock_id)
            .order_by(_d(DailyPrice.date))
            .limit(60)
            .all()
        )
        sess.close()
        if len(prices_db) >= 10:
            closes = [p.close for p in reversed(prices_db)]
            rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
            mu, sigma = float(np.mean(rets)), float(np.std(rets))
        else:
            mu, sigma = 0.0, 0.015
        np.random.seed(42)
        finals = []
        for _ in range(n_sim):
            p = current_price
            for _ in range(days):
                p *= 1 + np.random.normal(mu, sigma)
            finals.append(p)
        finals = np.array(finals)
        p5, p25, p50, p75, p95 = (np.percentile(finals, q) for q in [5, 25, 50, 75, 95])
        prob_t = (
            float((finals >= trade.target_price).mean() * 100)
            if trade.target_price
            else 0.0
        )
        prob_s = (
            float((finals <= trade.stop_price).mean() * 100)
            if trade.stop_price
            else 0.0
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("20日後中位數", f"{p50:,.1f}", f"{(p50/current_price-1)*100:+.1f}%")
        c2.metric("達目標機率", f"{prob_t:.0f}%")
        c3.metric("觸停損機率", f"{prob_s:.0f}%")
        fig = go.Figure(
            go.Histogram(x=finals, nbinsx=40, marker_color="#764ba2", opacity=0.7)
        )
        fig.add_vline(
            x=current_price, line_color="#888", line_dash="dash", annotation_text="現價"
        )
        if trade.target_price:
            fig.add_vline(
                x=trade.target_price,
                line_color="#00c851",
                line_width=2,
                annotation_text="目標",
            )
        if trade.stop_price:
            fig.add_vline(
                x=trade.stop_price,
                line_color="#ff4444",
                line_width=2,
                annotation_text="停損",
            )
        fig.update_layout(
            margin=dict(l=0, r=0, t=20, b=0),
            height=200,
            showlegend=False,
            plot_bgcolor="white",
            paper_bgcolor="white",
            xaxis_title="20日後預測價格",
            yaxis_title="模擬次數",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"5%={p5:,.1f}　25%={p25:,.1f}　中位={p50:,.1f}　75%={p75:,.1f}　95%={p95:,.1f}"
        )
    except Exception as e:
        st.caption(f"MC 計算失敗：{e}")


def page_my_trades() -> None:
    st.markdown(
        '<div class="section-title">💼 我的實際交易紀錄</div>', unsafe_allow_html=True
    )
    stock_prices = load_stock_prices()

    with st.expander("➕ 新增交易"):
        stock_list = load_stock_list()
        stock_labels = [lbl for lbl, _ in stock_list]
        with st.form("add_trade_form", clear_on_submit=True):
            stock_sel = st.selectbox(
                "股票（輸入名稱或代號搜尋）",
                options=stock_labels,
                index=None,
                placeholder="例：台積電 或 2330",
            )
            c1, c2 = st.columns(2)
            with c1:
                buy_date_in = st.date_input("買入日期", value=date.today())
                notes_in = st.text_input("備註（選填）")
            with c2:
                buy_price_in = st.number_input(
                    "買入均價（元，含手續費，依券商顯示填入）",
                    min_value=0.0,
                    step=0.5,
                    format="%.2f",
                )
                shares_in = st.number_input(
                    "股數（整張=1000股，零股直接填）", min_value=1, step=1, value=1000
                )
            c3, c4 = st.columns(2)
            with c3:
                target_in = st.number_input(
                    "目標價（0 = 自動 +10%）", min_value=0.0, step=0.5, format="%.2f"
                )
            with c4:
                stop_in = st.number_input(
                    "停損價（0 = 自動 -7%）", min_value=0.0, step=0.5, format="%.2f"
                )
            if st.form_submit_button("✅ 新增", use_container_width=True):
                sid = dict(stock_list).get(stock_sel, "") if stock_sel else ""
                if not sid or buy_price_in <= 0:
                    st.error("請選擇股票並填寫買入價格")
                else:
                    sname = stock_sel.split("（")[0].strip() if stock_sel else sid
                    t_price = (
                        target_in if target_in > 0 else round(buy_price_in * 1.10, 1)
                    )
                    s_price = stop_in if stop_in > 0 else round(buy_price_in * 0.93, 1)
                    _s = get_session()
                    _s.add(
                        UserTrade(
                            stock_id=sid.strip(),
                            stock_name=sname,
                            buy_date=buy_date_in,
                            buy_price=buy_price_in,
                            shares=int(shares_in),
                            target_price=t_price,
                            stop_price=s_price,
                            status="holding",
                            notes=notes_in,
                        )
                    )
                    _s.commit()
                    _s.close()
                    st.success(f"✅ {sname}（{sid.strip()}）已新增！")
                    st.rerun()

    _sess = get_session()
    all_trades = _sess.query(UserTrade).order_by(UserTrade.buy_date.desc()).all()
    _sess.close()
    holdings = [t for t in all_trades if t.status == "holding"]
    closed = [t for t in all_trades if t.status == "closed"]

    st.markdown(
        f'<div class="section-title">📌 目前持倉（{len(holdings)} 筆）</div>',
        unsafe_allow_html=True,
    )
    if not holdings:
        st.info("尚無持倉，點上方「新增交易」加入第一筆。")

    for trade in holdings:
        cur = stock_prices.get(trade.stock_id)
        cur_date_label = "TWSE"
        if not cur:
            try:
                from sqlalchemy import desc as _dd

                _s3 = get_session()
                _dp = (
                    _s3.query(DailyPrice)
                    .filter_by(stock_id=trade.stock_id)
                    .order_by(_dd(DailyPrice.date))
                    .first()
                )
                _s3.close()
                cur = _dp.close if _dp else None
                cur_date_label = str(_dp.date) if _dp else "—"
            except Exception as e:
                logger.debug(f"trade price fallback failed ({trade.stock_id}): {e}")
                cur = None
                cur_date_label = "—"

        days_held = (date.today() - trade.buy_date).days
        eff_buy = trade.buy_price
        net_cur = cur * (1 - SELL_FEE) if cur else None
        pnl_pct = (net_cur - eff_buy) / eff_buy * 100 if net_cur else None
        pnl_amount = (net_cur - eff_buy) * trade.shares if net_cur else None
        total_cost = eff_buy * trade.shares

        if cur and trade.stop_price and cur < trade.stop_price:
            signal, sig_color = "🔴 已觸停損，建議出場", "#ff4444"
        elif cur and trade.target_price and cur >= trade.target_price:
            signal, sig_color = "🟢 已達目標，考慮獲利了結", "#00c851"
        elif days_held > 60:
            signal, sig_color = "⚠️ 持有超過 60 日，重新評估", "#ffbb33"
        else:
            signal, sig_color = "🟡 持續觀察", "#888"

        pnl_color = (
            "#00c851"
            if pnl_pct and pnl_pct > 0
            else "#ff4444" if pnl_pct and pnl_pct < 0 else "#aaa"
        )

        st.markdown(
            f"""
        <div class="rec-card" style="border-left:5px solid {pnl_color}">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
            <div>
              <div style="font-size:1.05rem;font-weight:800">{trade.stock_name}（{trade.stock_id}）</div>
              <div style="font-size:0.75rem;color:#888">買入 {trade.buy_date} @ {trade.buy_price:,.1f}元　{trade.shares}股　持有 {days_held}日</div>
            </div>
            <div style="text-align:right">
              <div style="font-size:1.4rem;font-weight:800;color:{pnl_color}">{f"{pnl_pct:+.2f}%" if pnl_pct is not None else "—"}</div>
              <div style="font-size:0.75rem;color:{pnl_color}">{f"{pnl_amount:+,.0f}元" if pnl_amount is not None else ""}</div>
              <div style="font-size:0.6rem;color:#aaa">含買賣手續費及證交稅</div>
            </div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
            <div style="flex:1;min-width:70px;background:#f5f5f5;border-radius:6px;padding:5px 8px;text-align:center">
              <div style="font-size:0.6rem;color:#888">現價（{cur_date_label}）</div>
              <div style="font-weight:700">{f"{cur:,.1f}" if cur else "—"}</div>
            </div>
            <div style="flex:1;min-width:70px;background:#e8f5e9;border-radius:6px;padding:5px 8px;text-align:center">
              <div style="font-size:0.6rem;color:#2e7d32">目標價</div>
              <div style="font-weight:700;color:#2e7d32">{f"{trade.target_price:,.1f}" if trade.target_price else "—"}</div>
            </div>
            <div style="flex:1;min-width:70px;background:#fce4ec;border-radius:6px;padding:5px 8px;text-align:center">
              <div style="font-size:0.6rem;color:#c62828">停損價</div>
              <div style="font-weight:700;color:#c62828">{f"{trade.stop_price:,.1f}" if trade.stop_price else "—"}</div>
            </div>
            <div style="flex:1;min-width:70px;background:#fff8e1;border-radius:6px;padding:5px 8px;text-align:center">
              <div style="font-size:0.6rem;color:#f57f17">成本總額（含手續費）</div>
              <div style="font-weight:700;color:#f57f17">{total_cost:,.0f}元</div>
            </div>
          </div>
          <div style="font-size:0.85rem;color:{sig_color};font-weight:600">{signal}</div>
          {f'<div style="font-size:0.75rem;color:#aaa;margin-top:4px">備註：{trade.notes}</div>' if trade.notes else ""}
        </div>
        """,
            unsafe_allow_html=True,
        )

        col_mc, col_exit = st.columns([2, 1])
        with col_mc:
            if cur:
                with st.expander("📊 蒙地卡羅 20 日預測"):
                    _render_trade_mc(trade, cur)
        with col_exit:
            with st.expander("🚪 記錄出場"):
                with st.form(f"close_{trade.id}"):
                    sell_d = st.date_input(
                        "出場日", value=date.today(), key=f"sd_{trade.id}"
                    )
                    sell_p = st.number_input(
                        "出場價",
                        min_value=0.0,
                        step=0.5,
                        value=float(cur or trade.buy_price),
                        key=f"sp_{trade.id}",
                        format="%.2f",
                    )
                    if st.form_submit_button("確認出場"):
                        net_sell = sell_p * (1 - SELL_FEE)
                        eff_buy_c = trade.buy_price
                        r_pct = (net_sell - eff_buy_c) / eff_buy_c * 100
                        r_pnl = (net_sell - eff_buy_c) * trade.shares
                        _sx = get_session()
                        _tx = _sx.query(UserTrade).filter_by(id=trade.id).first()
                        _tx.status = "closed"
                        _tx.sell_date = sell_d
                        _tx.sell_price = sell_p
                        _tx.realized_pct = r_pct
                        _tx.realized_pnl = r_pnl
                        _sx.commit()
                        _sx.close()
                        st.success(f"損益 {r_pct:+.1f}%（{r_pnl:+,.0f}元）")
                        st.rerun()

    if closed:
        import pandas as pd

        st.markdown(
            f'<div class="section-title">📜 已出場紀錄（{len(closed)} 筆）</div>',
            unsafe_allow_html=True,
        )
        wins = [t for t in closed if t.realized_pct and t.realized_pct > 0]
        total_pnl = sum(t.realized_pnl for t in closed if t.realized_pnl)
        avg_pct = sum(t.realized_pct for t in closed if t.realized_pct) / len(closed)
        win_rate = len(wins) / len(closed) * 100
        st.markdown(
            f"""
        <div class="stat-grid">
          <div class="stat-box"><div class="stat-val">{len(closed)}</div><div class="stat-lbl">已出場筆數</div></div>
          <div class="stat-box"><div class="stat-val" style="color:{'#00c851' if win_rate >= 50 else '#ff4444'}">{win_rate:.0f}%</div><div class="stat-lbl">勝率</div></div>
          <div class="stat-box"><div class="stat-val" style="color:{'#00c851' if avg_pct > 0 else '#ff4444'}">{avg_pct:+.1f}%</div><div class="stat-lbl">平均報酬</div></div>
          <div class="stat-box"><div class="stat-val" style="font-size:1.1rem;color:{'#00c851' if total_pnl > 0 else '#ff4444'}">{total_pnl/10000:+.1f}萬</div><div class="stat-lbl">實現損益</div></div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        rows = []
        for t in sorted(closed, key=lambda x: x.sell_date or date.min, reverse=True):
            hold_days = (t.sell_date - t.buy_date).days if t.sell_date else "—"
            rows.append(
                {
                    "股票": f"{t.stock_name}（{t.stock_id}）",
                    "買入日": str(t.buy_date),
                    "買入價": f"{t.buy_price:,.1f}",
                    "出場日": str(t.sell_date or "—"),
                    "出場價": f"{t.sell_price:,.1f}" if t.sell_price else "—",
                    "股數": t.shares,
                    "持有天": hold_days,
                    "損益%": f"{t.realized_pct:+.1f}%" if t.realized_pct else "—",
                    "實現損益": f"{t.realized_pnl:+,.0f}元" if t.realized_pnl else "—",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
