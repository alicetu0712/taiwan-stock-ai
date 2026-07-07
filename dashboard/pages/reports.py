"""
pages/reports.py — 個股查詢 + 歷史記錄頁
"""
import logging

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.loaders import load_exec_logs, load_recent_recs, load_stock_names

logger = logging.getLogger(__name__)


def page_search() -> None:
    st.markdown('<div class="section-title">個股查詢</div>', unsafe_allow_html=True)
    sid = st.text_input("股票代號", placeholder="輸入 4 位數代號，例：2330",
                        max_chars=6, label_visibility="collapsed")

    if not sid:
        st.markdown("""
        <div style="text-align:center; color:#bbb; padding:60px 0">
          <div style="font-size:3rem">🔍</div>
          <div style="font-size:0.95rem; margin-top:10px">輸入股票代號查詢歷史研究記錄</div>
        </div>
        """, unsafe_allow_html=True)
        return

    try:
        from src.database import get_session, Recommendation, AnalysisResult
        from sqlalchemy import select
        s = get_session()
        recs = s.execute(
            select(Recommendation)
            .where(Recommendation.stock_id == sid.strip())
            .order_by(Recommendation.date.desc()).limit(30)
        ).scalars().all()
        analyses = s.execute(
            select(AnalysisResult)
            .where(AnalysisResult.stock_id == sid.strip())
            .order_by(AnalysisResult.date.desc()).limit(30)
        ).scalars().all()
        s.close()

        if not recs and not analyses:
            st.info(f"尚無 {sid} 的研究記錄。")
            return

        st.markdown(f"""
        <div class="search-result">
          <div style="font-size:1.2rem; font-weight:800">{sid}</div>
          <div style="color:#888; font-size:0.8rem">共 {len(recs)} 次推薦 · {len(analyses)} 次分析</div>
        </div>
        """, unsafe_allow_html=True)

        if analyses:
            df = pd.DataFrame([{
                "日期": a.date, "綜合": a.total_score,
                "品質": a.quality_score, "時機": a.timing_score,
            } for a in analyses]).sort_values("日期")
            fig = go.Figure()
            for col, color in [("綜合", "#764ba2"), ("品質", "#667eea"), ("時機", "#33b5e5")]:
                fig.add_trace(go.Scatter(x=df["日期"], y=df[col], name=col,
                    line=dict(color=color, width=2), mode="lines+markers", marker=dict(size=5)))
            fig.update_layout(
                margin=dict(l=0, r=0, t=10, b=0), height=260,
                legend=dict(orientation="h", y=-0.25),
                plot_bgcolor="white", paper_bgcolor="white",
                xaxis=dict(showgrid=False), yaxis=dict(range=[0, 100], gridcolor="#f0f0f0"),
            )
            st.plotly_chart(fig, use_container_width=True)

        if recs:
            st.markdown("**推薦紀錄**")
            for r in recs:
                level = r.rec_level or "B"
                color = {"A+": "#00c851", "A": "#33b5e5", "B": "#ffbb33"}.get(level, "#aaa")
                st.markdown(f"""
                <div class="history-item">
                  <div>
                    <div class="history-date">{r.date}</div>
                    <div style="font-size:0.85rem; color:#333; margin-top:2px">{r.summary or '—'}</div>
                  </div>
                  <span class="rec-badge" style="background:{color};color:{'#333' if level == 'B' else 'white'};padding:4px 10px;border-radius:20px;font-size:0.78rem;font-weight:700">{level}</span>
                </div>
                """, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"查詢失敗：{e}")


def page_history() -> None:
    st.markdown('<div class="section-title">近期推薦紀錄</div>', unsafe_allow_html=True)
    recent = load_recent_recs(days=90)
    logs   = load_exec_logs(30)
    stock_names = load_stock_names()

    if not recent.empty:
        col1, col2 = st.columns([1, 1])
        with col1:
            freq = recent.groupby("stock_id").size().reset_index(name="次數").sort_values("次數", ascending=False).head(10)
            freq["label"] = freq["stock_id"].apply(lambda s: f"{stock_names.get(s, s)}\n{s}")
            fig = px.bar(freq, x="label", y="次數",
                         color="次數", color_continuous_scale=["#e3f2fd", "#1565c0"],
                         title="近 90 日推薦次數 Top 10")
            fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=280,
                              showlegend=False, plot_bgcolor="white", paper_bgcolor="white",
                              coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            if not logs.empty:
                df_plot = logs.head(14).sort_values("date").copy()
                fig2 = go.Figure()
                fig2.add_trace(go.Bar(x=df_plot["date"], y=df_plot["analyzed"],  name="分析", marker_color="#b3c6ff"))
                fig2.add_trace(go.Bar(x=df_plot["date"], y=df_plot["qualified"], name="篩選", marker_color="#667eea"))
                fig2.add_trace(go.Bar(x=df_plot["date"], y=df_plot["recs"],      name="推薦", marker_color="#764ba2"))
                fig2.update_layout(
                    barmode="group", height=280, margin=dict(l=0, r=0, t=30, b=0),
                    title="執行紀錄（近 14 天）",
                    legend=dict(orientation="h", y=-0.3, font=dict(size=11)),
                    plot_bgcolor="white", paper_bgcolor="white",
                    xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#f0f0f0"),
                )
                st.plotly_chart(fig2, use_container_width=True)

        st.markdown("**推薦明細**")
        for _, row in recent.iterrows():
            level = row.get("rec_level", "B") or "B"
            color = {"A+": "#00c851", "A": "#33b5e5", "B": "#ffbb33"}.get(level, "#aaa")
            sid = row["stock_id"]
            name = stock_names.get(sid, "")
            display = f"{name}（{sid}）" if name else sid
            st.markdown(f"""
            <div class="history-item">
              <div>
                <div class="history-date">{row['date']}</div>
                <div class="history-sid">{display}</div>
              </div>
              <span class="rec-badge" style="background:{color};color:{'#333' if level == 'B' else 'white'};padding:4px 10px;border-radius:20px;font-size:0.78rem;font-weight:700">{level} · {row.get('confidence', 0):.0f}%</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("尚無推薦歷史。執行分析後資料會出現在這裡。")
