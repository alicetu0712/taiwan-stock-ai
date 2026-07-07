"""
pages/guide.py — 評分說明頁 + 設定 & 執行頁
"""
import logging
import sys
from datetime import date
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)


def _run_analysis(dry_run: bool) -> None:
    import subprocess
    try:
        cmd = [sys.executable, str(Path(__file__).parent.parent.parent / "main.py")]
        if dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        if result.returncode == 0:
            st.success("✅ 分析完成！重新整理頁面查看。")
            st.cache_data.clear()
        else:
            st.error(f"執行失敗：{result.stderr[-300:]}")
    except Exception as e:
        st.error(f"錯誤：{e}")


def page_guide() -> None:
    st.markdown('<div class="section-title">📖 評分說明</div>', unsafe_allow_html=True)
    st.caption("本平台以五個維度對每支股票評分（0–100 分），綜合分由各維度加權計算。")

    st.markdown("---")
    st.markdown("### 🔵 品質分（財務體質）")
    st.markdown("""
評估公司的**基本面健康程度**，越高代表財務越穩健。

| 指標 | 說明 |
|---|---|
| ROE（股東權益報酬率） | 越高越好，長期 > 15% 為優 |
| ROA（總資產報酬率） | 衡量資產運用效率 |
| 毛利率 | 反映產品競爭力，越高越佳 |
| 負債比率 | 越低越安全，< 40% 為健康 |
| EPS 趨勢 | 每股盈餘是否持續成長 |
| 自由現金流 | 正數代表實際有在賺錢 |

**分數解讀**：90+ 財務極優 ｜ 70–89 穩健 ｜ 50–69 普通 ｜ < 50 需注意
    """)

    st.markdown("---")
    st.markdown("### 🔵 時機分（技術進場）")
    st.markdown("""
評估**現在是否是好的進場時機**，根據價格與成交量型態判斷。

| 指標 | 說明 |
|---|---|
| 均線排列（MA5/20/60） | 短中長均線多頭排列為正訊號 |
| RSI（相對強弱指標） | 30 以下超賣（可能反彈），70 以上超買（需謹慎） |
| MACD | 黃金交叉（訊號線上穿）為買進訊號 |
| KD 指標 | 低檔黃金交叉為進場參考 |
| 成交量 | 量增價漲確認趨勢，量縮要小心 |

**分數解讀**：90+ 強勢進場 ｜ 70–89 偏多 ｜ 50–69 中性 ｜ < 50 偏空或整理
    """)

    st.markdown("---")
    st.markdown("### 🔵 籌碼分（法人動向）")
    st.markdown("""
追蹤**三大法人（外資、投信、自營商）**的買賣超動向。法人資金龐大，其方向往往影響後市。

| 法人 | 特性 |
|---|---|
| 外資 | 資金最大，長線布局為主 |
| 投信（基金） | 月底、季底容易調整，短線影響較大 |
| 自營商 | 偏短線，波動較大，參考為輔 |

**正訊號**：外資 + 投信同步買超、連續多日累積買超
**負訊號**：法人大幅賣超、外資連續出走

**分數解讀**：80+ 法人積極買進 ｜ 60–79 小幅偏多 ｜ 40–59 中性 ｜ < 40 法人賣超
    """)

    st.markdown("---")
    st.markdown("### 🔵 風險分（波動風險）")
    st.markdown("""
評估**持有這支股票的風險程度**，分數越高代表風險越低（越安全）。

| 風險因子 | 說明 |
|---|---|
| 股價波動率 | 短期漲跌幅是否過大 |
| 距均線距離 | 股價離均線太遠，回測機率提高 |
| 市場情緒 | 大盤處於恐慌還是貪婪狀態 |
| 成交量異常 | 爆量可能是主力出貨訊號 |
| 財務槓桿 | 負債高的公司在景氣下行時風險加倍 |

**分數解讀**：85+ 風險極低 ｜ 70–84 風險可控 ｜ 55–69 需留意 ｜ < 55 高風險
    """)

    st.markdown("---")
    st.markdown("### 🟣 綜合分（加權總分）")
    st.markdown("""
各維度加權後的**最終評分**，反映整體投資吸引力。

| 加權比例 | 說明 |
|---|---|
| 品質 × 40% | 基本面為核心，先確認公司體質 |
| 時機 × 25% | 進場點很重要，好公司也要等好時機 |
| 籌碼 × 20% | 法人方向提供趨勢確認 |
| 情報 × 10% | 新聞、外資報告等市場情報 |
| 風險 × 5%  | 控制下行風險，保護資本 |

| 綜合分 | 等級 | 建議 |
|---|---|---|
| 85 分以上 | A+ 級 | 強烈值得深入研究 |
| 75–84 分 | A 級  | 值得深入研究 |
| 65–74 分 | B 級  | 列入觀察清單 |
| 55–64 分 | C 級  | 條件不足，繼續觀察 |
| 55 分以下 | D 級  | 不建議研究 |
    """)

    st.markdown("---")
    st.markdown("### ⚪ 分析信心度")
    st.markdown("""
反映**本次分析結果的可靠程度**，受資料完整性影響。

| 扣分原因 | 扣幾分 |
|---|---|
| 無基本面資料（FinMind 未設定） | -20 |
| 歷史價格資料不足（< 14 天） | -15 |
| 無籌碼資料 | -10 |
| 技術面與基本面方向相反 | -10 至 -15 |
| 風險分數偏低（< 65） | -10 至 -20 |

信心度 **80%+** 為高可信度；**65%** 通常代表資料不完整，結果僅供參考。
    """)


def page_settings(selected_date: date) -> None:
    st.markdown('<div class="section-title">設定 & 執行</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**查看日期**")
        _min_date = date(2025, 1, 1)
        _clamped  = max(selected_date, _min_date)
        new_date = st.date_input("分析日期", value=_clamped,
                                 min_value=_min_date, max_value=date.today(),
                                 label_visibility="collapsed")
        if new_date != selected_date:
            st.session_state["selected_date"] = new_date
            st.rerun()

    with col2:
        st.markdown("**執行分析**")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🧪 Dry-run", use_container_width=True):
                with st.spinner("執行中..."):
                    _run_analysis(dry_run=True)
        with c2:
            if st.button("▶ 今日分析", use_container_width=True):
                with st.spinner("執行中（約 30 秒）..."):
                    _run_analysis(dry_run=False)

    st.divider()
    st.markdown('<div class="section-title">資料庫狀態</div>', unsafe_allow_html=True)
    try:
        from src.database import get_session, DailyPrice, InstitutionalData, Recommendation
        from sqlalchemy import func
        s = get_session()
        price_cnt = 0
        chip_cnt  = 0
        oldest    = None
        newest    = None
        try:
            price_cnt = s.query(func.count(DailyPrice.id)).scalar() or 0
            chip_cnt  = s.query(func.count(InstitutionalData.id)).scalar() or 0
            oldest    = s.query(func.min(DailyPrice.date)).filter(DailyPrice.date >= '2025-01-01').scalar()
            newest    = s.query(func.max(DailyPrice.date)).scalar()
        except Exception as e:
            logger.debug(f"page_settings price date query failed: {e}")
        rec_cnt = s.query(func.count(Recommendation.id)).scalar() or 0
        s.close()
        if price_cnt > 0:
            st.markdown(f"""
            <div class="stat-grid">
              <div class="stat-box">
                <div class="stat-val" style="font-size:1.4rem">{price_cnt:,}</div>
                <div class="stat-lbl">股價紀錄</div>
              </div>
              <div class="stat-box">
                <div class="stat-val" style="font-size:1.4rem">{chip_cnt:,}</div>
                <div class="stat-lbl">法人紀錄</div>
              </div>
              <div class="stat-box">
                <div class="stat-val" style="font-size:1.4rem">{rec_cnt}</div>
                <div class="stat-lbl">推薦紀錄</div>
              </div>
              <div class="stat-box">
                <div class="stat-val" style="font-size:0.85rem; color:#667eea">{oldest or '—'}</div>
                <div class="stat-lbl">研究起始日期</div>
              </div>
            </div>
            """, unsafe_allow_html=True)
            if newest:
                st.caption(f"最新股價：{newest}")
        else:
            st.markdown(f"""
            <div class="stat-grid">
              <div class="stat-box">
                <div class="stat-val" style="font-size:1.4rem">{rec_cnt}</div>
                <div class="stat-lbl">推薦紀錄</div>
              </div>
            </div>
            """, unsafe_allow_html=True)
            st.caption("股價／法人原始資料存於本機，行動版不顯示")
    except Exception as e:
        logger.error(f"page_settings DB query failed: {e}")
        st.caption("資料庫暫時無法連線")
