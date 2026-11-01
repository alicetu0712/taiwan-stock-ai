"""
pages/position.py — 💼 持倉管理

頁面結構（三個分頁）：
  A. 💰 真實持倉 ACTUAL  — 使用者確認成交後建立；顯示實際損益
  B. 📊 系統模擬 PAPER   — 模型自動追蹤（position_monitor），僅供研究
  C. 📋 歷史交易紀錄     — 舊版 user_trades 唯讀歷史

嚴格隔離：ACTUAL / PAPER / RESEARCH / RECOMMENDATION
  - ACTUAL 損益完全獨立計算，不受 PAPER 影響
  - Pipeline 不自動建立 ACTUAL 持倉
  - ForwardSignal / 正式 BUY 邏輯不受修改
"""

import json as _json
import logging
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import streamlit as st

from dashboard.loaders import load_stock_prices
from src.presentation.position_presenter import PositionPresenter

logger = logging.getLogger(__name__)

_POSITION_PRESENTER = PositionPresenter()


# ── helpers ───────────────────────────────────────────────────────────────────


def _get_neon_url() -> str:
    from dotenv import load_dotenv as _lde

    _lde(dotenv_path=Path(__file__).parent.parent.parent / ".env", override=True)
    return os.getenv("NEON_URL") or os.getenv("DATABASE_URL") or ""


@st.cache_data(ttl=120)
def load_positions(status: str = "active") -> list:
    """PAPER: 直連 Neon 讀取 position_monitor，不依賴 get_session()。"""
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


def _load_actual_enriched(include_closed: bool = False) -> list:
    """
    載入 ACTUAL 持倉並加入最新股價與損益資訊。
    不使用 @st.cache_data（使用者剛記錄成交時需立即看到更新）。
    """
    try:
        from src.database import ActualPosition, get_session
        from src.services.actual_position_service import enrich_positions
        from src.services.trade_service import get_active_positions

        s = get_session()
        if include_closed:
            from sqlalchemy import select

            positions = (
                s.execute(
                    select(ActualPosition).order_by(ActualPosition.open_date.desc())
                )
                .scalars()
                .all()
            )
        else:
            positions = get_active_positions(s)
        enriched = enrich_positions(s, positions)
        s.close()
        return enriched
    except Exception as e:
        logger.warning(f"_load_actual_enriched failed: {e}")
        return []


def _pnl_color(v) -> str:
    if v is None:
        return "#888"
    return "#e53935" if v < 0 else "#43a047" if v > 0 else "#888"


def _pnl_str(v, pct=None) -> str:
    if v is None:
        return "—"
    s = f"{v:+,.0f}"
    if pct is not None:
        s += f"（{pct:+.1f}%）"
    return s


# ── ACTUAL Section A ──────────────────────────────────────────────────────────


def _render_actual_section() -> None:
    st.markdown(
        """
<div style="background:#e8f5e9;border-left:4px solid #43a047;
     border-radius:6px;padding:8px 14px;margin-bottom:12px;font-size:0.78rem;color:#2e7d32">
  💰 <strong>真實持倉 ACTUAL</strong> — 只顯示您親自確認的成交。
  損益以移動加權平均成本計算，與 PAPER 模擬完全隔離。
</div>""",
        unsafe_allow_html=True,
    )

    if st.button("🔄 重新整理持倉", key="refresh_actual"):
        st.rerun()

    enriched = _load_actual_enriched()

    if not enriched:
        st.info(
            "目前無真實持倉。\n\n"
            "請前往「📡 盤中」tab，在正式 BUY 卡片中點擊「📝 記錄實際買進」，"
            "或使用下方「手動新增持倉」按鈕。"
        )
        _render_manual_add_form()
        return

    # ── 彙總摘要 ──
    total_cost = sum(e["total_cost_basis"] for e in enriched)
    total_unrealized = sum(
        e["unrealized_pnl"] for e in enriched if e["unrealized_pnl"] is not None
    )
    total_realized = sum(e["realized_pnl"] for e in enriched)
    n_pos = len(enriched)
    n_stale = sum(1 for e in enriched if e["price_stale"] is True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("持倉支數", n_pos)
    c2.metric("總成本", f"NT$ {total_cost:,.0f}")
    c3.metric(
        "未實現損益",
        f"{total_unrealized:+,.0f}",
        help="依最新可取得股價計算；過期資料以 ⚠️ 標示",
    )
    c4.metric("已實現損益", f"{total_realized:+,.0f}")

    if n_stale > 0:
        st.warning(f"⚠️ {n_stale} 支股票的股價資料超過 5 天，未實現損益僅供參考。")

    st.divider()

    for e in enriched:
        sid = e["stock_id"]
        name = e["stock_name"]
        status_icon = {"open": "🟢", "partially_closed": "🟡", "closed": "⚪"}.get(
            e["status"], "⚪"
        )
        upnl = e["unrealized_pnl"]
        upct = e["unrealized_pct"]
        stale_tag = " ⚠️" if e["price_stale"] is True else ""
        pnl_label = (
            f"未實現 {_pnl_str(upnl, upct)}{stale_tag}"
            if upnl is not None
            else "未實現 —（無股價資料）"
        )

        with st.expander(
            f"{status_icon} {name}（{sid}）  {pnl_label}  ｜  "
            f"均價 {e['avg_cost']:.2f}  ｜  {e['remaining_shares']} 股",
            expanded=False,
            key=f"actual_pos_{e['id']}",
        ):
            _render_actual_position_detail(e)

    st.divider()
    with st.expander("➕ 手動新增持倉（MANUAL）", expanded=False):
        _render_manual_add_form()


def _render_actual_position_detail(e: dict) -> None:
    """單一 ACTUAL 持倉的詳細資訊與操作表單。"""
    import src.services.trade_service as svc
    from src.database import get_session

    pos_id = e["id"]
    sid = e["stock_id"]
    name = e["stock_name"]

    # ── Level 1：即時狀態摘要 ─────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("持股數量", e["remaining_shares"])
    c2.metric("平均成本", f"{e['avg_cost']:.2f}")
    price_label = f"{e['current_price']:.2f}" if e["current_price"] else "—"
    price_help = (
        f"資料日期：{e['price_date']}（{e['price_age_days']} 天前）"
        if e["price_date"]
        else "無股價資料"
    )
    if e["price_stale"] is True:
        price_label += " ⚠️"
    c3.metric("最新股價", price_label, help=price_help)
    c4.metric(
        "未實現損益",
        (
            _pnl_str(e["unrealized_pnl"], e["unrealized_pct"])
            if e["unrealized_pnl"] is not None
            else "—"
        ),
        delta_color="normal",
    )

    r2c1, r2c2, r2c3 = st.columns(3)
    r2c1.metric("已實現損益", f"{e['realized_pnl']:+,.0f}")
    r2c2.metric(
        "目標價",
        f"{e['target_price']:.2f}" if e["target_price"] else "—",
    )
    r2c3.metric(
        "停損價",
        f"{e['stop_price']:.2f}" if e["stop_price"] else "—",
    )

    # 原始交易計畫（AI 推薦時凍結）
    if e.get("original_plan_snapshot"):
        with st.expander("📋 原始 AI 交易計畫（唯讀）", expanded=False):
            try:
                snap = _json.loads(e["original_plan_snapshot"])
                sc1, sc2, sc3 = st.columns(3)
                sc1.metric("訊號評級", snap.get("rec_level") or "—")
                sc2.metric("綜合評分", snap.get("total_score") or "—")
                sc3.metric(
                    "信心",
                    (
                        f"{snap.get('confidence', 0):.0f}%"
                        if snap.get("confidence")
                        else "—"
                    ),
                )
                sc4, sc5, sc6 = st.columns(3)
                sc4.metric(
                    "進場區間",
                    (
                        f"{snap.get('entry_low', '—'):.1f}–{snap.get('entry_high', '—'):.1f}"
                        if snap.get("entry_low")
                        else "—"
                    ),
                )
                sc5.metric(
                    "原始停損",
                    (
                        f"{snap.get('stop_price', '—'):.1f}"
                        if snap.get("stop_price")
                        else "—"
                    ),
                )
                sc6.metric(
                    "目標 T1",
                    f"{snap.get('target1', '—'):.1f}" if snap.get("target1") else "—",
                )
                if e.get("forward_signal_id"):
                    st.caption(f"連結 ForwardSignal id={e['forward_signal_id']}")
            except Exception:
                st.code(e["original_plan_snapshot"])

    # ── Level 2：查看成交明細 ─────────────────────────────────────────────
    with st.expander("🧾 成交明細", expanded=False):
        try:
            s = get_session()
            execs = svc.get_executions(s, pos_id, include_cancelled=True)
            s.close()
            if not execs:
                st.caption("尚無成交記錄")
            else:
                for ex in execs:
                    cancel_tag = " ~~（已取消）~~" if ex.is_cancelled else ""
                    st.markdown(
                        f"{'🟢' if ex.side == 'BUY' else '🔴'} "
                        f"**{ex.side}** {ex.shares:,} 股 @ {float(ex.execution_price):.2f}"
                        f"　{ex.execution_date}"
                        f"　手續費 {float(ex.actual_fee):.0f}"
                        f"{cancel_tag}"
                    )
        except Exception as exc:
            st.error(f"讀取成交明細失敗：{exc}")

    # ── Level 3：操作表單 ─────────────────────────────────────────────────
    op_tabs = st.tabs(["📈 加碼", "📉 部分賣出", "🚪 全部賣出", "✏️ 修改計畫"])

    with op_tabs[0]:
        _render_add_buy_form(pos_id, sid, name)

    with op_tabs[1]:
        _render_partial_sell_form(pos_id, sid, name, e["remaining_shares"])

    with op_tabs[2]:
        _render_full_sell_form(pos_id, sid, name, e["remaining_shares"], e["avg_cost"])

    with op_tabs[3]:
        _render_update_plan_form(pos_id, e["target_price"], e["stop_price"])


def _render_add_buy_form(pos_id: int, sid: str, name: str) -> None:
    import src.services.trade_service as svc
    from src.database import get_session

    with st.form(key=f"add_buy_{pos_id}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        exec_date = c1.date_input("成交日期", value=date.today())
        exec_price = c2.number_input(
            "成交價格", min_value=0.01, step=0.01, format="%.2f"
        )
        c3, c4 = st.columns(2)
        shares = c3.number_input("股數", min_value=1, step=1)
        fee = c4.number_input("手續費", min_value=0.0, step=1.0, format="%.0f")
        notes = st.text_input("備註（選填）")
        if st.form_submit_button("✅ 確認加碼", type="primary"):
            try:
                s = get_session()
                svc.add_execution(
                    s,
                    pos_id,
                    "BUY",
                    exec_date,
                    execution_price=Decimal(str(exec_price)),
                    shares=int(shares),
                    actual_fee=Decimal(str(fee)),
                    transaction_tax=Decimal("0"),
                    notes=notes,
                )
                s.commit()
                s.close()
                st.success(f"✅ 加碼記錄完成：{int(shares)} 股 @ {exec_price:.2f}")
                st.rerun()
            except svc.TradeSvcError as e:
                st.error(f"加碼失敗：{e}")
            except Exception as e:
                st.error(f"系統錯誤：{e}")


def _render_partial_sell_form(pos_id: int, sid: str, name: str, remaining: int) -> None:
    import src.services.trade_service as svc
    from src.database import get_session

    st.caption(f"目前剩餘 {remaining:,} 股，賣出後自動計算已實現損益。")
    with st.form(key=f"partial_sell_{pos_id}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        exec_date = c1.date_input("成交日期", value=date.today())
        exec_price = c2.number_input(
            "成交價格", min_value=0.01, step=0.01, format="%.2f"
        )
        c3, c4 = st.columns(2)
        shares = c3.number_input("賣出股數", min_value=1, max_value=remaining, step=1)
        fee = c4.number_input("手續費＋交易稅", min_value=0.0, step=1.0, format="%.0f")
        notes = st.text_input("備註（選填）")
        if st.form_submit_button("✅ 確認賣出", type="primary"):
            try:
                s = get_session()
                svc.add_execution(
                    s,
                    pos_id,
                    "SELL",
                    exec_date,
                    execution_price=Decimal(str(exec_price)),
                    shares=int(shares),
                    actual_fee=Decimal(str(fee)),
                    transaction_tax=Decimal("0"),
                    notes=notes,
                )
                s.commit()
                s.close()
                st.success(f"✅ 賣出 {int(shares)} 股 @ {exec_price:.2f}")
                st.rerun()
            except svc.TradeSvcError as e:
                st.error(f"賣出失敗：{e}")
            except Exception as e:
                st.error(f"系統錯誤：{e}")


def _render_full_sell_form(
    pos_id: int, sid: str, name: str, remaining: int, avg_cost: float
) -> None:
    import src.services.trade_service as svc
    from src.database import get_session

    if remaining == 0:
        st.caption("持倉已為零。")
        return
    st.caption(
        f"全數賣出 {remaining:,} 股（均價 {avg_cost:.2f}）。確認後持倉將標記為 closed。"
    )
    with st.form(key=f"full_sell_{pos_id}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        exec_date = c1.date_input("成交日期", value=date.today())
        exec_price = c2.number_input(
            "成交價格", min_value=0.01, step=0.01, format="%.2f"
        )
        fee = st.number_input("手續費＋交易稅", min_value=0.0, step=1.0, format="%.0f")
        notes = st.text_input("備註（選填）")
        if st.form_submit_button("🚪 確認全部賣出", type="primary"):
            try:
                s = get_session()
                svc.add_execution(
                    s,
                    pos_id,
                    "SELL",
                    exec_date,
                    execution_price=Decimal(str(exec_price)),
                    shares=remaining,
                    actual_fee=Decimal(str(fee)),
                    transaction_tax=Decimal("0"),
                    notes=notes,
                )
                s.commit()
                s.close()
                realized = (exec_price - avg_cost) * remaining
                st.success(
                    f"✅ 全數出場 {remaining:,} 股 @ {exec_price:.2f}　"
                    f"本次實現損益 {realized:+,.0f}"
                )
                st.rerun()
            except svc.TradeSvcError as e:
                st.error(f"賣出失敗：{e}")
            except Exception as e:
                st.error(f"系統錯誤：{e}")


def _render_update_plan_form(
    pos_id: int, current_target: float, current_stop: float
) -> None:
    import src.services.trade_service as svc
    from src.database import get_session

    st.caption("修改目標價或停損價，原始 AI 計畫快照不受影響，本次修改會保留稽核記錄。")
    with st.form(key=f"update_plan_{pos_id}", clear_on_submit=True):
        field = st.selectbox(
            "修改欄位",
            ["target_price", "stop_price"],
            format_func=lambda x: "目標價" if x == "target_price" else "停損價",
        )
        default_val = current_target if field == "target_price" else current_stop
        new_val = st.number_input(
            "新價格",
            min_value=0.01,
            value=float(default_val) if default_val else 0.01,
            step=0.01,
            format="%.2f",
        )
        reason = st.text_input("修改原因（必填）")
        if st.form_submit_button("✅ 確認修改"):
            if not reason.strip():
                st.error("請填寫修改原因")
            else:
                try:
                    s = get_session()
                    svc.update_plan(s, pos_id, field, Decimal(str(new_val)), reason)
                    s.commit()
                    s.close()
                    label = "目標價" if field == "target_price" else "停損價"
                    st.success(f"✅ {label} 已修改為 {new_val:.2f}")
                    st.rerun()
                except svc.TradeSvcError as e:
                    st.error(f"修改失敗：{e}")


def _render_manual_add_form() -> None:
    """手動新增 MANUAL 持倉（不連結 ForwardSignal）。"""
    import src.services.trade_service as svc
    from src.database import get_session

    with st.form(key="manual_add_position", clear_on_submit=True):
        c1, c2 = st.columns(2)
        stock_id = c1.text_input("股票代號（如 2330）")
        stock_name = c2.text_input("股票名稱")
        c3, c4 = st.columns(2)
        exec_date = c3.date_input("成交日期", value=date.today())
        exec_price = c4.number_input(
            "成交價格", min_value=0.01, step=0.01, format="%.2f"
        )
        c5, c6 = st.columns(2)
        shares = c5.number_input("股數", min_value=1, step=1)
        fee = c6.number_input("手續費", min_value=0.0, step=1.0, format="%.0f")
        c7, c8 = st.columns(2)
        target_price = c7.number_input(
            "目標價（選填）", min_value=0.0, step=0.01, format="%.2f"
        )
        stop_price = c8.number_input(
            "停損價（選填）", min_value=0.0, step=0.01, format="%.2f"
        )
        notes = st.text_input("備註（選填）")

        if st.form_submit_button("✅ 建立持倉並記錄買進", type="primary"):
            if not stock_id.strip():
                st.error("請填寫股票代號")
            elif exec_price <= 0:
                st.error("請填寫成交價格")
            else:
                try:
                    s = get_session()
                    pos = svc.create_position(
                        s,
                        stock_id.strip(),
                        stock_name.strip() or stock_id.strip(),
                        "MANUAL",
                        exec_date,
                        target_price=(
                            Decimal(str(target_price)) if target_price > 0 else None
                        ),
                        stop_price=Decimal(str(stop_price)) if stop_price > 0 else None,
                        notes=notes,
                    )
                    svc.add_execution(
                        s,
                        pos.id,
                        "BUY",
                        exec_date,
                        execution_price=Decimal(str(exec_price)),
                        shares=int(shares),
                        actual_fee=Decimal(str(fee)),
                        transaction_tax=Decimal("0"),
                    )
                    s.commit()
                    s.close()
                    st.success(
                        f"✅ 已建立持倉：{stock_name or stock_id}（{stock_id}）"
                        f"買進 {int(shares)} 股 @ {exec_price:.2f}"
                    )
                    st.rerun()
                except svc.TradeSvcError as e:
                    st.error(f"建立失敗：{e}")
                except Exception as e:
                    st.error(f"系統錯誤：{e}")


# ── PAPER Section B ───────────────────────────────────────────────────────────

import plotly.graph_objects as go  # noqa: E402


def _monte_carlo_chart(pos: dict) -> None:
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


def _render_paper_section() -> None:
    st.markdown(
        """
<div style="background:#e3f2fd;border-left:4px solid #1565c0;
     border-radius:6px;padding:8px 14px;margin-bottom:12px;font-size:0.78rem;color:#1565c0">
  📊 <strong>系統模擬持倉 PAPER</strong> — 模型自動追蹤，<strong>不代表使用者實際下單</strong>。
  損益與 ACTUAL 完全隔離。
</div>""",
        unsafe_allow_html=True,
    )

    tab_active, tab_closed = st.tabs(["🟢 模擬持倉中", "📋 模擬歷史"])

    with tab_active:
        if not (os.getenv("NEON_URL") or os.getenv("DATABASE_URL")):
            st.error("請設定 NEON_URL 環境變數")
            return
        positions = load_positions("active")
        if not positions:
            st.info("目前無模擬持倉。每次推薦時系統會自動建立追蹤記錄。")
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
                st.warning(f"⚠️ 建議倉位合計 {total_alloc:.0f}%，超過 100%。")

            st.markdown("#### 模擬組合總覽")
            r1c1, r1c2 = st.columns(2)
            r1c1.metric("模擬持倉支數", f"{n_pos} 支")
            r1c2.metric(
                "剩餘現金比例",
                f"{cash_pct:.0f}%",
                delta=f"已配置 {min(total_alloc, 100):.0f}%",
                delta_color="off",
            )
            r2c1, r2c2 = st.columns(2)
            r2c1.metric("整體預期報酬", f"{weighted_exp:+.2f}%")
            r2c2.metric("整體目前損益", f"{weighted_cur:+.2f}%")

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
                        f'<div style="width:90px;font-size:0.72rem;color:#555;'
                        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{ind}</div>'
                        f'<div style="flex:1;background:#e0e0e0;border-radius:3px;height:10px">'
                        f'<div style="width:{min(pct, 100):.0f}%;'
                        f"background:"
                        f'{"#e53935" if pct >= 50 else "#f57f17" if pct >= 35 else "#43a047"};'
                        f'height:10px;border-radius:3px"></div></div>'
                        f'<div style="font-size:0.72rem;color:#555;width:35px;text-align:right">'
                        f"{pct:.0f}%</div></div>"
                        for ind, pct in sorted_ind
                    )
                    st.markdown(
                        f'<div style="background:{c_bg};border:1px solid {c_color}44;'
                        f'border-radius:8px;padding:10px 14px;margin:10px 0">'
                        f'<div style="font-size:0.78rem;font-weight:700;color:{c_color};margin-bottom:8px">'
                        f"{c_icon} 組合產業集中度</div>{ind_bars}</div>",
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
                level = pos["rec_level"] or "B"
                card = _POSITION_PRESENTER.present(pos, curr)
                with st.expander(
                    f"{card.pnl_icon} {name}（{sid}）  "
                    f"{card.pnl_str}  ｜  {level}級  ｜  建倉 {pos['date_entered']}",
                    expanded=False,
                    key=f"paper_pos_{pos['id']}",
                ):
                    st.html(card.price_html)
                    st.html(card.progress_html)
                    st.caption(card.summary_caption)
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
                                    p.pnl_pct = (
                                        round(card.pnl, 2)
                                        if card.pnl is not None
                                        else None
                                    )
                                    s2.commit()
                                s2.close()
                                st.cache_data.clear()
                                st.success(f"已關倉 {name}（{card.pnl_str}）")
                                st.rerun()
                            except Exception as e:
                                st.error(f"關倉失敗：{e}")
                    with st.expander("🎲 歷史波動情境模擬", expanded=False):
                        st.caption("此模擬依歷史波動產生可能路徑，不代表未來價格預測。")
                        _monte_carlo_chart(pos)
                    with st.expander("📋 交易計劃", expanded=False):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("進場價", f"{pos['entry_price']:.2f}")
                        c2.metric(
                            "目標價",
                            (
                                f"{pos['target_price']:.2f}"
                                if pos["target_price"]
                                else "—"
                            ),
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
                            (
                                f"{pos['position_pct']:.0f}%"
                                if pos["position_pct"]
                                else "—"
                            ),
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
            st.info("尚無模擬歷史紀錄。")


# ── History Section C ──────────────────────────────────────────────────────────


def _render_history_section() -> None:
    st.markdown(
        """
<div style="background:#f3e5f5;border-left:4px solid #7b1fa2;
     border-radius:6px;padding:8px 14px;margin-bottom:12px;font-size:0.78rem;color:#4a148c">
  📋 <strong>歷史交易紀錄</strong> — 舊版 user_trades 唯讀歷史 ＋ 已出場的 ACTUAL 持倉。
</div>""",
        unsafe_allow_html=True,
    )

    hist_tabs = st.tabs(["💰 ACTUAL 已出場", "🗂 舊版 user_trades"])

    with hist_tabs[0]:
        closed = _load_actual_enriched(include_closed=True)
        closed_pos = [e for e in closed if e["status"] == "closed"]
        if not closed_pos:
            st.info("尚無已出場的 ACTUAL 持倉。")
        else:
            for e in closed_pos:
                realized = e["realized_pnl"]
                color = _pnl_color(realized)
                st.markdown(
                    f"**{e['stock_name']}**（{e['stock_id']}）"
                    f"  {e['open_date']} → {e['close_date'] or '—'}"
                    f"  ｜ 已實現 <span style='color:{color};font-weight:700'>"
                    f"{realized:+,.0f}</span>"
                    f"  ｜ 均價 {e['avg_cost']:.2f}"
                    f"  ｜ {e['signal_source']}",
                    unsafe_allow_html=True,
                )

    with hist_tabs[1]:
        try:
            from dashboard._pages.my_trades import page_my_trades

            page_my_trades()
        except Exception as e:
            st.error(f"舊版交易記錄載入失敗：{e}")


# ── Main entry ────────────────────────────────────────────────────────────────


def page_positions() -> None:
    st.markdown(
        '<div class="section-title">💼 持倉管理</div>',
        unsafe_allow_html=True,
    )

    tab_actual, tab_paper, tab_hist = st.tabs(
        ["💰 真實持倉 ACTUAL", "📊 系統模擬 PAPER", "📋 歷史紀錄"]
    )

    with tab_actual:
        _render_actual_section()

    with tab_paper:
        _render_paper_section()

    with tab_hist:
        _render_history_section()
