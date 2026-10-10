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
    st.markdown('<div class="section-title">📖 平台說明</div>', unsafe_allow_html=True)
    st.caption("Antigravity v6 — AI 台股短線波段研究平台。本頁說明各頁面的設計邏輯與資料解讀方式。")

    # ── Overview ──────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 🗺 整體架構")
    st.markdown("""
本平台的設計核心是**「給你看結論，而不是讓你自己解讀數字」**。

資料流如下：

```
每日盤後 → 抓取股價 / 籌碼 / 基本面資料
   ↓
V2 AI 模型：五維度評分 + 價格趨勢分析
   ↓
Decision Center：把模型結論翻譯成白話決策
   ↓
Evidence Panel：這種型態以前表現如何？
   ↓
首頁呈現：BUY / WAIT / REDUCE / SELL AVOID
```

重要原則：**Evidence Panel 不改變 BUY/WAIT 判斷**。它的角色是「佐證」，不是決策者。
    """)

    # ── V2 Scoring ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 📊 V2 評分模型（目前版本）")
    st.markdown("""
本平台採**短線波段策略**（目標持有 20–60 個交易日）。評分由五個維度加權：

| 維度 | 權重 | 說明 |
|---|---|---|
| **股價趨勢（PriceTrend）** | **45%** | 均線結構 / 斜率 / 乖離 / 型態 / 量能 |
| **基本面品質（Quality）** | **20%** | ROE / ROA / 毛利率 / 負債比 / EPS 趨勢 |
| **動能（Timing）** | **15%** | RSI / MACD / KD — 短線動能指標 |
| **籌碼（Behavior）** | **15%** | 法人買賣超 / 融資融券 |
| **風險懲罰（Risk）** | **5%** | 波動率 / 財務槓桿 / 市場情緒 |

> V2 以**股價本身**為核心（PriceTrend 45% + Timing 15% = 60% 技術面），基本面做品質過濾器（20%），而非選股主軸。
    """)

    # ── Decision Center ───────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 🎯 Decision Center（首頁主要功能）")
    st.markdown("""
首頁每張股票卡片的核心是 **Decision Center**，它把模型的 `trade_signal` + `setup_type` 翻譯成六種白話決策：

| 決策標籤 | 意思 |
|---|---|
| **BUY ★** | 強烈買進訊號，型態與量能均佳 |
| **BUY** | 買進訊號，進場條件成立 |
| **WAIT FOR PULLBACK** | 模型看多，但現價偏離 MA20 > 5%，建議等回測 |
| **WAIT** | 尚無明確進場訊號，持續觀察 |
| **REDUCE** | 訊號轉弱、動能衰退，考慮縮減部位（但論點未失敗） |
| **SELL / AVOID** | 技術結構破壞 or 賣出訊號確立，不要進場 / 應出場 |

**REDUCE ≠ SELL**：REDUCE 代表「訊號在惡化，但還沒破壞」；SELL/AVOID 代表「論點已失效」。

---

### 交易計劃（Trading Plan）

當進場條件成立時，卡片會顯示：

| 欄位 | 計算方式 |
|---|---|
| **進場區間** | 收盤價 ± 0.3 × ATR（14日）|
| **停損** | 收盤價 − 2.0 × ATR |
| **目標一** | 收盤價 + 2.5 × ATR |
| **目標二** | 收盤價 + 5.0 × ATR |
| **R/R 比** | (目標一 − 現價) / (現價 − 停損) |

R/R ≥ 2x 為理想；< 1.5x 需謹慎。ATR 代表近期每日平均波動幅度。

---

### WAIT FOR PULLBACK 是怎麼來的？

這是**進場品質 override**，規則：
- 模型說 BUY，但 `ma20_gap > 5%`（現價偏離 MA20 超過 5%）
- → 系統把 BUY 降級為 WAIT FOR PULLBACK

這只是 UI 呈現規則，不是已驗證的交易門檻（見 `config.py` 的 `ENTRY_QUALITY`）。
    """)

    # ── Setup Types ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 📐 型態說明（Setup Types）")
    st.markdown("""
| 型態 | 意思 | 對應明日觸發條件 |
|---|---|---|
| **breakout** | 股價突破關鍵壓力，量能配合 | 量能 > 昨日 1.5x 且收高點 → 確認突破 |
| **pullback_buy** | 在上升趨勢中回測支撐 | 守住支撐 + 量縮 → 可考慮進場 |
| **pullback_hold** | 已持有，正在回測 | 維持部位，觀察是否守住 MA20 |
| **trending** | 順勢上漲中 | 量縮即為健康回測；爆量急跌需警戒 |
| **breakdown** | 支撐破壞，結構轉空 | 避免承接；等 MA20 重新翻多再評估 |
| **none** | 無明確型態 | — |
    """)

    # ── Evidence Panel ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 🔬 類似訊號歷史績效（Evidence Panel）")
    st.markdown("""
每張決策卡片底部有可展開的 **Evidence Panel**，顯示「這種型態以前表現如何」。

分為兩個部分：

### 🧪 Research（In-Sample）
- 查詢 **Research Cutoff 之前**所有相同 `setup_type` + 市場 Regime 的觀察紀錄
- 計算 20D / 60D 對 0050 的超額報酬（Alpha）和勝率
- 這是 **有看過未來的資料**，統計數字會偏樂觀

### 🔒 Forward Validation（真實 OOS）
- 查詢 **Research Cutoff 之後**實際記錄的 `ForwardSignal`
- 真正沒有偷看未來，每筆訊號在當天「凍結」特徵值
- 這才是**真實世界的驗證**，但現在樣本仍在累積

---

### 樣本數門檻（嚴格執行）

| 樣本數 | 標示 | 解讀 |
|---|---|---|
| < 10 筆 | 🔴 樣本不足 | **不給任何方向性結論** |
| 10–29 筆 | 🟡 初步觀察 | 方向僅供參考，不穩定 |
| 30–99 筆 | 🟢 有一定參考價值 | 可參考，但仍需 Forward 確認 |
| ≥ 100 筆 | 🟢 樣本充足 | 建議搭配 CI 和 OOS 一起判讀 |

> **重要**：Evidence Panel 只是「佐證」。它不改變 BUY/WAIT 標籤，也不是選股依據。
    """)

    # ── Market Regime ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 🌐 市場 Regime（大盤方向）")
    st.markdown("""
本平台以**三狀態**定義大盤方向，用來過濾 Evidence Panel 的歷史樣本：

| Regime | 條件 |
|---|---|
| **Bull（多頭）** | 0050 收盤 > MA60，且 MA60 斜率向上 |
| **Bear（空頭）** | 0050 收盤 < MA60，且 MA60 斜率向下 |
| **Neutral（中性）** | 其他（MA60 斜率持平、或多空訊號混雜） |

之所以用三狀態而非二元：市場常常在「盤整」，此時用 Bull/Bear 二分法會誤判。
    """)

    # ── Research Backtest ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 📈 Research Backtest 頁面")
    st.markdown("""
**Research Backtest** 是平台的「策略診斷室」，讓你在歷史資料上驗證模型表現。

### 資料架構
- **Research 期間**：Cutoff 日期之前（有看過未來，樣本充足）
- **Forward 期間**：Cutoff 日期之後（沒有偷看未來，樣本持續累積中）

### 樣本獨立性警告
同一支股票在不同日期可能重複出現。為了避免「重複計算」導致 n 虛高：
- **Raw**：所有觀察（可能有重複）
- **Dedup 20D**：同一支股票，至少間隔 20 個交易日才算一次
- **Dedup 60D**：間隔 60 個交易日

> **建議以 Dedup 20D 為主要參考**。Raw 的 p-value 通常過低（因重複觀察拉低了統計誤差）。

### 統計指標說明
| 指標 | 說明 |
|---|---|
| **Alpha** | 超過 0050 的報酬（正數代表跑贏大盤） |
| **勝率** | Alpha > 0 的比例 |
| **Cohen's d** | 效果量：0.2 小 / 0.5 中 / 0.8 大 |
| **Bootstrap CI** | 95% 信心區間（非參數法，更適合偏態分布） |
    """)

    # ── Position Monitor ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 📌 持倉監控頁面")
    st.markdown("""
追蹤你實際持有的部位，提供：
- 蒙地卡羅模擬（10,000 次），估算未來 20/60 日的報酬分布
- 動態停損 / 目標價更新
- 每日 P&L 與部位狀態

> 持倉資料是**本地儲存**，不會上傳。
    """)

    # ── Confidence ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## ⚪ 分析信心度")
    st.markdown("""
反映**本次分析結果的資料完整程度**。

| 扣分原因 | 影響 |
|---|---|
| 無基本面資料 | −20 |
| 歷史價格不足（< 14 天） | −15 |
| 無籌碼資料 | −10 |
| 技術面與基本面方向相反 | −10 至 −15 |
| 風險分數偏低（< 65） | −10 至 −20 |

**80%+**：高可信度 ｜ **65–79%**：資料部分缺失，參考為主 ｜ **< 65%**：建議補資料後再判斷
    """)

    # ── Data Health ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 🏥 Data Health 頁面")
    st.markdown("""
監控資料管線的健康狀態，重點包括：

- **Forward Signal 缺失偵測**：Cutoff 後有分析結果但沒有寫入 ForwardSignal 的日期 → 🔴 警告
  - 這些缺口**永遠補不回來**（ForwardSignal 必須在當天凍結才有效）
  - 一旦出現紅色警告，應盡快修復並重新執行分析

- 各資料表的最新日期、總筆數、異常偵測
    """)

    # ── Disclaimer ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## ⚠️ 使用聲明")
    st.markdown("""
本平台所有內容均為**研究與學習用途**，不構成投資建議。

- 所有分析基於歷史資料，過去表現不代表未來結果
- 模型尚在 Forward Validation 階段，有效性尚未完全確認
- 任何買賣決策請自行承擔風險

> _「Research 說它好像有效」≠「它一定有效」。等 Forward 有足夠資料，我們才確認。_
    """)


def page_settings(selected_date: date) -> None:
    st.markdown('<div class="section-title">設定 & 執行</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**查看日期**")
        _min_date = date(2025, 1, 1)
        _clamped = max(selected_date, _min_date)
        new_date = st.date_input(
            "分析日期",
            value=_clamped,
            min_value=_min_date,
            max_value=date.today(),
            label_visibility="collapsed",
        )
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
    st.markdown('<div class="section-title">部位試算設定</div>', unsafe_allow_html=True)
    st.caption("設定你的資金與風控參數，Decision Center 的「部位試算」區塊將依此計算建議張數。此設定暫存於瀏覽器 session，重新開啟頁面後回到預設值。")
    from config import POSITION_SIZING as _PS_CFG
    ps_col1, ps_col2 = st.columns(2)
    with ps_col1:
        cap = st.number_input(
            "可用資金（新台幣）",
            min_value=100_000,
            max_value=100_000_000,
            value=st.session_state.get("ps_capital", _PS_CFG["capital_ntd"]),
            step=100_000,
            format="%d",
        )
        st.session_state["ps_capital"] = cap
    with ps_col2:
        risk = st.slider(
            "單筆最大風險（%）",
            min_value=0.5,
            max_value=3.0,
            value=float(st.session_state.get("ps_max_risk_pct", _PS_CFG["max_risk_pct"])),
            step=0.5,
        )
        st.session_state["ps_max_risk_pct"] = risk
        max_loss = round(cap * risk / 100)
        st.caption(f"每筆最多虧損：NT$ {max_loss:,}")

    st.divider()
    st.markdown('<div class="section-title">資料庫狀態</div>', unsafe_allow_html=True)
    try:
        from dashboard.loaders import load_db_stats

        stats = load_db_stats()
        price_cnt = stats.get("price_cnt", 0)
        chip_cnt = stats.get("chip_cnt", 0)
        rec_cnt = stats.get("rec_cnt", 0)
        oldest = stats.get("oldest")
        newest = stats.get("newest")
        if price_cnt > 0:
            st.markdown(
                f"""
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
            """,
                unsafe_allow_html=True,
            )
            if newest:
                st.caption(f"最新股價：{newest}")
        else:
            st.markdown(
                f"""
            <div class="stat-grid">
              <div class="stat-box">
                <div class="stat-val" style="font-size:1.4rem">{rec_cnt}</div>
                <div class="stat-lbl">推薦紀錄</div>
              </div>
            </div>
            """,
                unsafe_allow_html=True,
            )
            st.caption("股價／法人原始資料存於本機，行動版不顯示")
    except Exception as e:
        logger.error(f"page_settings DB query failed: {e}")
        st.caption("資料庫暫時無法連線")
