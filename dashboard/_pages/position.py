"""
pages/position.py — 模型持倉追蹤（模擬）頁
"""

import json as _json
import logging
import os
from datetime import date
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from dashboard.loaders import load_stock_prices

logger = logging.getLogger(__name__)


def _get_neon_url() -> str:
    """每次呼叫都強制從 .env 重讀，避免 Streamlit hot-reload 沿用舊值。"""
    from dotenv import load_dotenv as _lde

    _lde(dotenv_path=Path(__file__).parent.parent.parent / ".env", override=True)
    return os.getenv("NEON_URL") or os.getenv("DATABASE_URL") or ""


@st.cache_data(ttl=120)
def load_positions(status: str = "active") -> list:
    """直連 Neon 讀取 position_monitor，不依賴 get_session()。"""
    neon_url = _get_neon_url()
    if not neon_url:
        return []
    if neon_url.startswith("sqlite"):
        try:
            from sqlalchemy import select

            from src.database import PositionMonitor, get_session

            s = get_session()
            rows = (
                s.execute(
                    select(PositionMonitor)
                    .where(PositionMonitor.status == status)
                    .order_by(PositionMonitor.date_entered.desc())
                )
                .scalars()
                .all()
            )
            result = [
                {
                    "id": r.id,
                    "stock_id": r.stock_id,
                    "name": r.stock_name or r.stock_id,
                    "date_entered": str(r.date_entered),
                    "entry_price": r.entry_price,
                    "target_price": r.target_price,
                    "stop_loss_price": r.stop_loss_price,
                    "target_pct": r.target_pct,
                    "stop_loss_pct": r.stop_loss_pct,
                    "position_pct": r.position_pct,
                    "rec_level": r.rec_level,
                    "rec_score": r.rec_score,
                    "rationale": r.ai_price_rationale or "",
                    "status": r.status,
                    "exit_date": str(r.exit_date) if r.exit_date else None,
                    "exit_price": r.exit_price,
                    "exit_reason": r.exit_reason,
                    "pnl_pct": r.pnl_pct,
                    "mc_result": _json.loads(r.mc_result or "null"),
                }
                for r in rows
            ]
            s.close()
            return result
        except Exception as e:
            logger.warning(f"load_positions SQLite failed: {e}")
            return []
    try:
        import psycopg

        conn = psycopg.connect(neon_url)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, stock_id, stock_name, date_entered, entry_price,
                   target_price, stop_loss_price, target_pct, stop_loss_pct,
                   position_pct, rec_level, rec_score, confidence, ai_price_rationale,
                   status, exit_date, exit_price, exit_reason, pnl_pct, mc_result
            FROM position_monitor
            WHERE status = %s
            ORDER BY date_entered DESC
        """,
            (status,),
        )
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close()
        conn.close()
        result = []
        for row in rows:
            r = dict(zip(cols, row))
            r["name"] = r.pop("stock_name") or r["stock_id"]
            r["rationale"] = r.pop("ai_price_rationale") or ""
            r["mc_result"] = _json.loads(r["mc_result"]) if r.get("mc_result") else None
            r["date_entered"] = (
                str(r["date_entered"]) if r.get("date_entered") else None
            )
            r["exit_date"] = str(r["exit_date"]) if r.get("exit_date") else None
            result.append(r)
        return result
    except Exception as e:
        logger.warning(f"load_positions failed: {e}")
        return []


def _monte_carlo_chart(pos: dict) -> None:
    """從預存的 mc_result JSON 繪製蒙地卡羅模擬圖。"""
    mc = pos.get("mc_result")
    if not mc:
        st.caption("蒙地卡羅資料尚未計算，待下次每日更新後顯示。")
        return

    fig = go.Figure()
    days = mc["days"]
    sample_paths = mc["sample_paths"]
    target_price = mc.get("target_price") or pos.get("target_price")
    stop_loss_price = mc.get("stop_loss_price") or pos.get("stop_loss_price")
    entry_price = mc.get("entry_price") or pos.get("entry_price")

    for path in sample_paths:
        fig.add_trace(
            go.Scatter(
                x=days,
                y=path,
                mode="lines",
                line=dict(color="rgba(150,150,150,0.15)", width=1),
                showlegend=False,
                hoverinfo="skip",
            )
        )

    fig.add_hline(
        y=target_price,
        line=dict(color="#2ecc71", dash="dash", width=2),
        annotation_text=f"目標 {target_price:.1f}",
        annotation_position="right",
    )
    fig.add_hline(
        y=stop_loss_price,
        line=dict(color="#e74c3c", dash="dash", width=2),
        annotation_text=f"停損 {stop_loss_price:.1f}",
        annotation_position="right",
    )
    fig.add_hline(
        y=entry_price,
        line=dict(color="#3498db", width=1.5),
        annotation_text=f"進場 {entry_price:.1f}",
        annotation_position="right",
    )

    fig.update_layout(
        height=300,
        margin=dict(l=10, r=80, t=10, b=30),
        yaxis_title="價格",
        xaxis_title="交易日",
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("達標機率", f"{mc['prob_target']:.1f}%")
    col2.metric("停損機率", f"{mc['prob_stop_loss']:.1f}%")
    col3.metric("期望報酬", f"{mc['expected_pnl_pct']:+.1f}%")


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
        if sp is not None else ""
    )
    target_marker = (
        f'<div style="position:absolute;left:{tp:.1f}%;top:-3px;'
        f'width:2px;height:12px;background:#43a047;border-radius:1px"></div>'
        if tp is not None else ""
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


def page_positions() -> None:
    st.markdown(
        '<div class="section-title">📈 模型持倉追蹤（模擬）</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "此區為依據模型推薦與歷史資料建立的模擬追蹤紀錄，並不代表使用者實際下單。實際交易請以「我的實際交易紀錄」為準。"
    )

    tab_active, tab_closed = st.tabs(["🟢 持倉中", "📋 歷史紀錄"])

    with tab_active:
        if not (os.getenv("NEON_URL") or os.getenv("DATABASE_URL")):
            st.error("請設定 NEON_URL 環境變數（.env 或 Streamlit secrets）")
            return
        positions = load_positions("active")
        if not positions:
            st.info("目前無持倉。每次推薦時系統會自動建立追蹤記錄。")
        else:
            total_alloc = sum(p["position_pct"] or 0 for p in positions)
            n_pos = len(positions)

            def _w(p):
                return (
                    (p["position_pct"] or 0) / total_alloc
                    if total_alloc > 0
                    else 1 / n_pos
                )

            weighted_cur = sum(_w(p) * (p["pnl_pct"] or 0) for p in positions)

            def _exp(p):
                mc = (p["mc_result"] or {}).get("expected_pnl_pct")
                if mc is not None:
                    return mc
                ep = p.get("entry_price") or 0
                tp = p.get("target_price") or 0
                return ((tp - ep) / ep * 100) if ep > 0 and tp > ep else 0.0

            weighted_exp = sum(_w(p) * _exp(p) for p in positions)
            cash_pct = max(0.0, 100.0 - total_alloc)

            if total_alloc > 100:
                st.warning(
                    f"⚠️ 建議倉位合計 {total_alloc:.0f}%，超過 100%。模型推薦過度分散或資金不足，以下損益數字為正規化後的比例，需人工取捨。"
                )

            st.markdown("#### 📊 目前配置總覽")
            r1c1, r1c2 = st.columns(2)
            r1c1.metric("持倉支數", f"{n_pos} 支", help="目前追蹤中的活躍持倉數")
            r1c2.metric(
                "剩餘現金",
                f"{cash_pct:.0f}%",
                delta=f"已配置 {min(total_alloc, 100):.0f}%",
                delta_color="off",
                help="100% 代表總資金，已配置為所有活躍持倉建議倉位合計",
            )
            r2c1, r2c2 = st.columns(2)
            r2c1.metric(
                "整體預期報酬",
                f"{weighted_exp:+.2f}%",
                help="各持倉目標漲幅（或蒙地卡羅期望值）按持倉比例加權平均",
            )
            r2c2.metric(
                "整體目前損益",
                f"{weighted_cur:+.2f}%",
                help="各持倉現價損益按持倉比例加權平均",
            )

            # ── 組合風險：產業集中度 ───────────────────────────────────
            try:
                from src.services.portfolio_risk_service import (
                    compute_portfolio_exposure,
                )

                exposure = compute_portfolio_exposure(positions)
                if exposure and exposure.get("industry_weights"):
                    level_map = {
                        "high": ("🔴", "#ffebee", "#c62828"),
                        "medium": ("🟡", "#fff8e1", "#f57f17"),
                        "low": ("🟢", "#e8f5e9", "#2e7d32"),
                    }
                    c_icon, c_bg, c_color = level_map.get(
                        exposure["concentration_level"], ("🟢", "#e8f5e9", "#2e7d32")
                    )
                    sorted_ind = sorted(
                        exposure["industry_weights"].items(), key=lambda x: -x[1]
                    )
                    ind_bars = "".join(
                        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">'
                        f'<div style="width:90px;font-size:0.72rem;color:#555;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{ind}</div>'
                        f'<div style="flex:1;background:#e0e0e0;border-radius:3px;height:10px">'
                        f'<div style="width:{min(pct, 100):.0f}%;background:{"#e53935" if pct >= 50 else "#f57f17" if pct >= 35 else "#43a047"};height:10px;border-radius:3px"></div>'
                        f"</div>"
                        f'<div style="font-size:0.72rem;color:#555;width:35px;text-align:right">{pct:.0f}%</div>'
                        f"</div>"
                        for ind, pct in sorted_ind
                    )
                    st.markdown(
                        f"""
<div style="background:{c_bg};border:1px solid {c_color}44;border-radius:8px;padding:10px 14px;margin:10px 0">
  <div style="font-size:0.78rem;font-weight:700;color:{c_color};margin-bottom:8px">{c_icon} 組合產業集中度</div>
  {ind_bars}
  {f'<div style="font-size:0.68rem;color:{c_color};margin-top:6px">最高集中度：{exposure["top_industry"]} {exposure["top_industry_pct"]:.0f}% — 再加碼同產業需留意集中風險</div>' if exposure["concentration_level"] in ("high", "medium") else ""}
</div>""",
                        unsafe_allow_html=True,
                    )
            except Exception as _pe:
                logger.debug(f"portfolio risk panel: {_pe}")

            st.divider()

            prices_now = load_stock_prices()

            for pos in positions:
                sid = pos["stock_id"]
                name = pos["name"]
                curr = prices_now.get(sid)
                pnl = (
                    ((curr - pos["entry_price"]) / pos["entry_price"] * 100)
                    if curr
                    else None
                )
                level = pos["rec_level"] or "B"
                with st.expander(
                    f"{'🟢' if (pnl or 0) >= 0 else '🔴'} {name}（{sid}）  "
                    f"{f'{pnl:+.1f}%' if pnl is not None else '—'}  ｜  {level}級  ｜  建倉 {pos['date_entered']}",
                    expanded=False,
                    key=f"pos_{pos['id']}",
                ):
                    # ── Level 1：即時狀態 ─────────────────────────────────
                    pnl_color   = "#00897b" if (pnl or 0) >= 0 else "#e53935"
                    pnl_str     = f"{pnl:+.1f}%" if pnl is not None else "—"
                    price_label = f"NT$ {curr:.2f}" if curr else "尚無即時報價"
                    st.html(
                        f'<div style="margin:2px 0 10px 0">'
                        f'<span style="font-size:1.5rem;font-weight:800;color:#222">'
                        f'{price_label}</span>'
                        f'<span style="font-size:0.95rem;font-weight:700;'
                        f'color:{pnl_color};margin-left:10px">{pnl_str}</span>'
                        f'</div>'
                    )

                    st.html(_position_progress_html(
                        pos.get("entry_price"),
                        pos.get("stop_loss_price"),
                        pos.get("target_price"),
                        curr,
                    ))

                    summary_parts = [level + "級", f"建倉 {pos['date_entered']}"]
                    if pos["position_pct"]:
                        summary_parts.insert(0, f"倉位 {pos['position_pct']:.0f}%")
                    st.caption("　·　".join(summary_parts))

                    if pos["rationale"]:
                        st.caption(f"📌 {pos['rationale']}")

                    if curr:
                        col_close, _ = st.columns([1, 3])
                        if col_close.button("手動關倉", key=f"close_{sid}_{pos['id']}"):
                            try:
                                from src.database import PositionMonitor, get_session

                                s2 = get_session()
                                p = s2.query(PositionMonitor).get(pos["id"])
                                if p:
                                    p.status = "closed_manual"
                                    p.exit_date = date.today()
                                    p.exit_price = curr
                                    p.exit_reason = "MANUAL"
                                    p.pnl_pct = round(pnl, 2)
                                    s2.commit()
                                s2.close()
                                st.cache_data.clear()
                                st.success(f"已關倉 {name}（{pnl:+.1f}%）")
                                st.rerun()
                            except Exception as e:
                                st.error(f"關倉失敗：{e}")

                    # ── Level 2：情境模擬 ─────────────────────────────────
                    with st.expander("🎲 歷史波動情境模擬", expanded=False):
                        st.caption(
                            "此模擬依歷史波動產生可能路徑，不代表未來價格預測，"
                            "也不是經校準的上漲機率。"
                        )
                        _monte_carlo_chart(pos)

                    # ── Level 3：交易計劃 ─────────────────────────────────
                    with st.expander("📋 交易計劃", expanded=False):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("進場價", f"{pos['entry_price']:.2f}")
                        c2.metric(
                            "目標價",
                            f"{pos['target_price']:.2f}" if pos["target_price"] else "—",
                            delta=(
                                f"+{pos['target_pct']:.1f}%"
                                if pos["target_pct"]
                                else None
                            ),
                        )
                        c3.metric(
                            "停損價",
                            (
                                f"{pos['stop_loss_price']:.2f}"
                                if pos["stop_loss_price"]
                                else "—"
                            ),
                            delta=(
                                f"{pos['stop_loss_pct']:.1f}%"
                                if pos["stop_loss_pct"]
                                else None
                            ),
                            delta_color="inverse",
                        )
                        c4.metric(
                            "建議倉位",
                            f"{pos['position_pct']:.0f}%" if pos["position_pct"] else "—",
                        )

    with tab_closed:
        for status in [
            "closed_profit",
            "closed_loss",
            "closed_signal",
            "closed_manual",
        ]:
            rows = load_positions(status)
            for pos in rows:
                icon = {
                    "closed_profit": "✅",
                    "closed_loss": "❌",
                    "closed_signal": "⚠️",
                    "closed_manual": "🔷",
                }.get(status, "—")
                pnl = pos["pnl_pct"] or 0
                color = "#2ecc71" if pnl >= 0 else "#e74c3c"
                st.markdown(
                    f"{icon} **{pos['name']}**（{pos['stock_id']}）"
                    f"  {pos['date_entered']} → {pos['exit_date'] or '—'}"
                    f"  ｜ 損益 <span style='color:{color};font-weight:700'>{pnl:+.1f}%</span>"
                    f"  ｜ {pos['exit_reason'] or '—'}",
                    unsafe_allow_html=True,
                )
        if not any(
            load_positions(s)
            for s in ["closed_profit", "closed_loss", "closed_signal", "closed_manual"]
        ):
            st.info("尚無歷史紀錄。")
