"""
pages/market_watch.py — 看盤頁

股價走勢 + MA5/10/20/60 + 成交量 + Setup 狀態
打開就能直接看出：突破 / 回踩 / 上漲趨勢 / 過熱 / 跌破
"""

import logging
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard.loaders import (
    load_latest_pt_analysis,
    load_price_chart_data,
    load_stock_names,
    load_watchable_stocks,
)

logger = logging.getLogger(__name__)

# ── 視覺常數 ──────────────────────────────────────────────────────

_SETUP_META = {
    "breakout":      {"label": "突破前高",      "color": "#0288d1", "bg": "#0d47a1", "icon": "🚀"},
    "pullback_buy":  {"label": "回踩買點 MA10", "color": "#43a047", "bg": "#1b5e20", "icon": "🟢"},
    "pullback_hold": {"label": "回踩守穩 MA20", "color": "#66bb6a", "bg": "#2e7d32", "icon": "🟩"},
    "trending":      {"label": "趨勢延伸",       "color": "#42a5f5", "bg": "#1565c0", "icon": "📈"},
    "overextended":  {"label": "過度乖離",       "color": "#ffa726", "bg": "#e65100", "icon": "🔥"},
    "breakdown":     {"label": "趨勢破壞",       "color": "#ef5350", "bg": "#b71c1c", "icon": "🔴"},
    "none":          {"label": "無明確型態",     "color": "#78909c", "bg": "#263238", "icon": "⬜"},
}

_SIGNAL_META = {
    "strong_buy": {"label": "強買", "color": "#00c851"},
    "buy":        {"label": "買進", "color": "#33b5e5"},
    "wait":       {"label": "等待", "color": "#ffbb33"},
    "reduce":     {"label": "減碼", "color": "#ff8800"},
    "sell":       {"label": "賣出", "color": "#ff4444"},
}

_MA_COLORS = {
    "ma5":  {"color": "#e0e0e0", "width": 1.2, "dash": "solid"},
    "ma10": {"color": "#4fc3f7", "width": 1.5, "dash": "solid"},
    "ma20": {"color": "#ffb74d", "width": 2.0, "dash": "solid"},
    "ma60": {"color": "#ce93d8", "width": 1.8, "dash": "solid"},
}

_CHART_BG    = "#0d1117"
_CHART_PAPER = "#161b22"
_GRID_COLOR  = "#21262d"


# ── 計算均線 ──────────────────────────────────────────────────────

def _add_mas(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    for p in [5, 10, 20, 60]:
        if len(df) >= p:
            df[f"ma{p}"] = close.rolling(p).mean().round(2)
    return df


# ── Plotly 圖表 ───────────────────────────────────────────────────

def build_chart(df: pd.DataFrame, analysis: dict, stock_name: str = "") -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.update_layout(
            height=420,
            paper_bgcolor=_CHART_PAPER,
            plot_bgcolor=_CHART_BG,
            font=dict(color="#c9d1d9"),
            annotations=[dict(
                text="無價格資料", showarrow=False,
                font=dict(size=16, color="#666"),
                xref="paper", yref="paper", x=0.5, y=0.5
            )],
        )
        return fig

    df = _add_mas(df.copy())
    setup = analysis.get("setup_type") or "none"
    sm = _SETUP_META.get(setup, _SETUP_META["none"])

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
    )

    # ── K 線 ──────────────────────────────────────────────────────
    fig.add_trace(
        go.Candlestick(
            x=df["date"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="K線",
            increasing=dict(line=dict(color="#ef5350", width=1), fillcolor="#ef5350"),
            decreasing=dict(line=dict(color="#26a69a", width=1), fillcolor="#26a69a"),
            hovertext=[
                f"開 {o:.1f}　高 {h:.1f}　低 {l:.1f}　收 {c:.1f}"
                for o, h, l, c in zip(df["open"], df["high"], df["low"], df["close"])
            ],
            hoverinfo="x+text",
        ),
        row=1, col=1,
    )

    # ── MA 線 ─────────────────────────────────────────────────────
    for ma_key, mc in _MA_COLORS.items():
        if ma_key in df.columns:
            visible_df = df[df[ma_key].notna()]
            if not visible_df.empty:
                fig.add_trace(
                    go.Scatter(
                        x=visible_df["date"], y=visible_df[ma_key],
                        name=ma_key.upper(),
                        line=dict(color=mc["color"], width=mc["width"], dash=mc["dash"]),
                        mode="lines",
                        hovertemplate=f"{ma_key.upper()} %{{y:.1f}}<extra></extra>",
                    ),
                    row=1, col=1,
                )

    # ── MA20 乖離帶（僅在有 MA20 時顯示）─────────────────────────
    if "ma20" in df.columns:
        ma20_last = df["ma20"].dropna().iloc[-1] if not df["ma20"].dropna().empty else None
        if ma20_last:
            # 10% 過熱線（虛線）
            fig.add_hline(
                y=round(ma20_last * 1.10, 1),
                line=dict(color="#ffa726", width=1, dash="dot"),
                annotation_text="MA20 +10%",
                annotation_font=dict(color="#ffa726", size=10),
                row=1, col=1,
            )

    # ── 當前價橫線 ────────────────────────────────────────────────
    cur_price = float(df["close"].iloc[-1])
    fig.add_hline(
        y=cur_price,
        line=dict(color="#ffffff", width=1, dash="dot"),
        row=1, col=1,
    )

    # ── 成交量 ────────────────────────────────────────────────────
    vol_colors = []
    for i in range(len(df)):
        if i == 0:
            vol_colors.append("#66bb6a")
        else:
            vol_colors.append(
                "#ef5350" if df["close"].iloc[i] < df["close"].iloc[i - 1] else "#66bb6a"
            )

    fig.add_trace(
        go.Bar(
            x=df["date"], y=df["volume"],
            name="成交量",
            marker_color=vol_colors,
            marker_line_width=0,
            hovertemplate="<b>%{x|%m/%d}</b><br>量 %{y:,.0f}<extra></extra>",
        ),
        row=2, col=1,
    )

    # ── 20日均量線 ────────────────────────────────────────────────
    if len(df) >= 20:
        df["vol_ma20"] = df["volume"].rolling(20).mean()
        visible_vol = df[df["vol_ma20"].notna()]
        fig.add_trace(
            go.Scatter(
                x=visible_vol["date"], y=visible_vol["vol_ma20"],
                name="均量",
                line=dict(color="#ffb74d", width=1.5),
                mode="lines",
                hovertemplate="均量 %{y:,.0f}<extra></extra>",
            ),
            row=2, col=1,
        )

    # ── Layout ───────────────────────────────────────────────────
    fig.update_layout(
        height=500,
        paper_bgcolor=_CHART_PAPER,
        plot_bgcolor=_CHART_BG,
        font=dict(color="#c9d1d9", size=11),
        legend=dict(
            orientation="h", x=0, y=1.02,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10),
        ),
        hovermode="x",
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis2=dict(
            type="category",
            showgrid=True, gridcolor=_GRID_COLOR,
            showticklabels=True,
            tickangle=-45, tickfont=dict(size=9),
            nticks=10,
        ),
        xaxis=dict(
            type="category",
            showgrid=False, showticklabels=False,
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(
            showgrid=True, gridcolor=_GRID_COLOR,
            side="right",
        ),
        yaxis2=dict(
            showgrid=True, gridcolor=_GRID_COLOR,
            side="right",
        ),
        dragmode="pan",
    )

    # Setup 型態標示（右上角 annotation）
    fig.add_annotation(
        text=f"{sm['icon']} {sm['label']}",
        xref="paper", yref="paper",
        x=0.01, y=0.97,
        font=dict(color=sm["color"], size=12, family="monospace"),
        bgcolor=_CHART_BG,
        bordercolor=sm["color"],
        borderwidth=1,
        borderpad=4,
        showarrow=False,
        xanchor="left",
    )

    return fig


# ── Setup Banner ─────────────────────────────────────────────────

def _render_setup_banner(analysis: dict, stock_id: str, stock_name: str) -> None:
    setup   = analysis.get("setup_type") or "none"
    signal  = analysis.get("trade_signal") or "wait"
    gap     = analysis.get("ma20_gap")
    vol_r   = analysis.get("volume_ratio")
    pt      = analysis.get("price_trend_score")
    level   = analysis.get("rec_level") or "—"

    sm  = _SETUP_META.get(setup, _SETUP_META["none"])
    sig = _SIGNAL_META.get(signal, _SIGNAL_META["wait"])

    gap_str = f"{gap:+.1f}%" if gap is not None else "—"
    gap_color = "#ef5350" if (gap or 0) > 10 else "#43a047" if (gap or 0) < 5 else "#ffb74d"
    vol_str = f"{vol_r:.1f}×" if vol_r is not None else "—"
    pt_str  = f"{pt:.0f}" if pt is not None else "—"

    display_name = f"{stock_name}（{stock_id}）" if stock_name and stock_name != stock_id else stock_id

    st.markdown(
        f"""
<div style="
    background: {sm['bg']}22;
    border: 1px solid {sm['color']}66;
    border-left: 4px solid {sm['color']};
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
">
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
    <div>
      <span style="font-size:1.25rem;font-weight:800;color:#f0f6fc">{display_name}</span>
    </div>
    <span style="
        background:{sm['color']}33;
        color:{sm['color']};
        border:1px solid {sm['color']}88;
        border-radius:6px;
        padding:4px 12px;
        font-size:0.85rem;
        font-weight:700;
    ">{sm['icon']} {sm['label']}</span>
    <span style="
        background:{sig['color']}33;
        color:{sig['color']};
        border:1px solid {sig['color']}88;
        border-radius:6px;
        padding:4px 12px;
        font-size:0.85rem;
        font-weight:700;
    ">{sig['label']}</span>
  </div>
  <div style="display:flex;gap:20px;flex-wrap:wrap;font-size:0.8rem;color:#8b949e">
    <div>
      <span style="display:block;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em">PriceTrend</span>
      <span style="font-size:1.1rem;font-weight:700;color:#c9d1d9">{pt_str}</span>
    </div>
    <div>
      <span style="display:block;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em">MA20乖離</span>
      <span style="font-size:1.1rem;font-weight:700;color:{gap_color}">{gap_str}</span>
    </div>
    <div>
      <span style="display:block;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em">量比</span>
      <span style="font-size:1.1rem;font-weight:700;color:#c9d1d9">{vol_str}</span>
    </div>
    <div>
      <span style="display:block;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em">等級</span>
      <span style="font-size:1.1rem;font-weight:700;color:#c9d1d9">{level}</span>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


# ── MA 數值列 ────────────────────────────────────────────────────

def _render_ma_row(df: pd.DataFrame) -> None:
    if df.empty:
        return
    df = _add_mas(df.copy())
    cur = float(df["close"].iloc[-1])
    items = [("現價", cur, None)]
    for p, color in [(5, "#e0e0e0"), (10, "#4fc3f7"), (20, "#ffb74d"), (60, "#ce93d8")]:
        key = f"ma{p}"
        if key in df.columns and not df[key].dropna().empty:
            val = float(df[key].dropna().iloc[-1])
            items.append((f"MA{p}", val, color))

    cols = st.columns(len(items))
    for col, (label, val, color) in zip(cols, items):
        if label == "現價":
            col.metric(label, f"{val:,.1f}")
        else:
            diff = round((cur - val) / val * 100, 1)
            sign = "+" if diff >= 0 else ""
            delta_color = "normal" if diff >= 0 else "inverse"
            col.metric(
                label=label,
                value=f"{val:,.1f}",
                delta=f"{sign}{diff}%",
                delta_color=delta_color,
                help=f"現價 vs {label}",
            )


# ── 主頁 ─────────────────────────────────────────────────────────

def page_market_watch(selected_date: date) -> None:
    stock_names = load_stock_names()
    watchable   = load_watchable_stocks(selected_date)

    # ── 股票選擇器 ──────────────────────────────────────────────
    col_search, col_toggle = st.columns([3, 1])

    with col_toggle:
        view_mode = st.radio(
            "模式",
            options=["單股", "全覽"],
            horizontal=True,
            label_visibility="collapsed",
        )

    with col_search:
        # 下拉選項：今日推薦清單
        if watchable:
            options = [
                f"{w['sid']} {w['name'] or stock_names.get(w['sid'], '')}".strip()
                for w in watchable
            ]
            default_idx = 0
            sel_str = st.selectbox(
                "選擇股票",
                options=options,
                index=default_idx,
                label_visibility="collapsed",
                placeholder="選擇股票或輸入代號…",
            )
            sel_sid = sel_str.split()[0] if sel_str else ""
        else:
            manual = st.text_input(
                "輸入股票代號",
                placeholder="例：2330",
                max_chars=6,
                label_visibility="collapsed",
            )
            sel_sid = manual.strip()

    # ── 額外手動輸入（在下拉旁邊） ───────────────────────────────
    manual_override = st.text_input(
        "或直接輸入代號",
        placeholder="2330",
        max_chars=6,
        label_visibility="visible",
        key="mw_manual",
    )
    if manual_override.strip():
        sel_sid = manual_override.strip()

    # ── 全覽模式 ─────────────────────────────────────────────────
    if view_mode == "全覽" and watchable:
        st.markdown(
            f'<div style="color:#8b949e;font-size:0.8rem;margin-bottom:12px">'
            f'今日 {len(watchable)} 檔推薦 — 全覽模式（點選單股切換詳細圖）'
            f'</div>',
            unsafe_allow_html=True,
        )
        for w in watchable:
            sid  = w["sid"]
            name = w["name"] or stock_names.get(sid, "")
            _render_compact_card(sid, name, selected_date)
        return

    # ── 單股詳細模式 ─────────────────────────────────────────────
    if not sel_sid:
        st.markdown(
            """
<div style="text-align:center;color:#8b949e;padding:80px 0">
  <div style="font-size:2.5rem">📈</div>
  <div style="margin-top:12px;font-size:0.95rem">選擇今日推薦股票，或輸入任意代號</div>
</div>
""",
            unsafe_allow_html=True,
        )
        return

    stock_name = stock_names.get(sel_sid, "")
    analysis   = load_latest_pt_analysis(sel_sid)
    price_df   = load_price_chart_data(sel_sid, days=90)

    if price_df.empty:
        st.warning(f"尚無 {sel_sid} 的價格資料。")
        return

    # ── Setup Banner ─────────────────────────────────────────────
    if analysis:
        _render_setup_banner(analysis, sel_sid, stock_name)
    else:
        st.markdown(
            f'<div style="color:#8b949e;font-size:0.85rem;margin-bottom:10px">'
            f'{sel_sid} {stock_name} — 尚無分析記錄，僅顯示走勢圖'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── MA 數值列 ─────────────────────────────────────────────────
    _render_ma_row(price_df)
    st.markdown("<div style='margin-bottom:6px'></div>", unsafe_allow_html=True)

    # ── 主圖 ──────────────────────────────────────────────────────
    fig = build_chart(price_df, analysis or {}, stock_name)
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displayModeBar": False})

    # ── MA 說明 ───────────────────────────────────────────────────
    st.markdown(
        """
<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:0.72rem;color:#8b949e;margin-top:4px">
  <span><span style="color:#e0e0e0">━</span> MA5</span>
  <span><span style="color:#4fc3f7">━</span> MA10</span>
  <span><span style="color:#ffb74d">━</span> MA20（基準線）</span>
  <span><span style="color:#ce93d8">━</span> MA60</span>
  <span style="margin-left:8px"><span style="color:#ffa726">╌</span> MA20 +10% 過熱線</span>
</div>
""",
        unsafe_allow_html=True,
    )


# ── 全覽模式：每股小卡 ─────────────────────────────────────────────

def _render_compact_card(sid: str, name: str, sel_date: date) -> None:
    analysis = load_latest_pt_analysis(sid)
    price_df = load_price_chart_data(sid, days=60)
    setup    = (analysis.get("setup_type") or "none") if analysis else "none"
    signal   = (analysis.get("trade_signal") or "wait") if analysis else "wait"
    sm       = _SETUP_META.get(setup, _SETUP_META["none"])
    sig      = _SIGNAL_META.get(signal, _SIGNAL_META["wait"])

    cur_price  = float(price_df["close"].iloc[-1]) if not price_df.empty else None
    gap        = analysis.get("ma20_gap") if analysis else None
    pt         = analysis.get("price_trend_score") if analysis else None

    gap_str    = f"{gap:+.1f}%" if gap is not None else "—"
    gap_color  = "#ef5350" if (gap or 0) > 10 else "#43a047" if (gap or 0) < 5 else "#ffb74d"
    price_str  = f"NT${cur_price:,.1f}" if cur_price else "—"
    pt_str     = f"{pt:.0f}" if pt is not None else "—"
    disp_name  = f"{name}（{sid}）" if name and name != sid else sid

    with st.expander(
        f"{sm['icon']} {disp_name}  ·  {sm['label']}  ·  {sig['label']}  ·  {price_str}",
        expanded=False,
    ):
        if analysis:
            col1, col2, col3 = st.columns(3)
            col1.metric("PriceTrend", pt_str)
            col2.metric("MA20乖離", gap_str)
            col3.metric(
                "量比",
                f"{analysis.get('volume_ratio', 0):.1f}×"
                if analysis.get("volume_ratio")
                else "—",
            )

        if not price_df.empty:
            fig = build_chart(price_df, analysis or {}, name)
            fig.update_layout(height=380)
            st.plotly_chart(
                fig, use_container_width=True,
                config={"scrollZoom": True, "displayModeBar": False},
            )
