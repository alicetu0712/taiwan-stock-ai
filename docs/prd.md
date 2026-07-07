PRD v6.0
AI Taiwan Equity Research Platform
Version 6.0
Chapter 1｜Executive Summary
Product Name
AI Taiwan Equity Research Platform
Product Vision
打造一套專業級 AI 股票研究平台，透過自動化資料蒐集、基本面分析、技術分析、籌碼分析、新聞情緒分析及 AI 評分模型，每日收盤後自動分析台灣上市櫃股票，協助投資人快速找到值得深入研究的投資標的。
本系統定位為 AI 股票研究助理（AI Equity Research Assistant），目的在於提升研究效率與資訊整合能力，不提供投資保證，也不執行任何自動交易。

Product Goal
建立一套可長期運作的 AI 股票研究平台，使使用者能夠：
每天自動獲得台股研究報告
快速了解市場趨勢
快速篩選高品質公司
降低研究時間
提高選股效率
建立長期投資資料庫
持續追蹤推薦績效
透過 AI 持續優化研究模型
Product Positioning
本產品不是：
股票推薦群組
飆股預測工具
自動下單程式
當沖交易系統
本產品定位為：
AI Taiwan Equity Research Platform
一套結合：
基本面分析
技術面分析
籌碼分析
新聞分析
公司治理分析
產業分析
總體經濟分析
的智慧研究平台。
Target Users
主要使用者：
Beginner Investors（投資新手）
需求：
不會看財報
不懂 K 線
想知道股票值不值得研究
希望透過 AI 學習投資
Long-term Investors（中長期投資人）
需求：
尋找高品質企業
關注企業體質
希望找到合理買點
降低情緒化交易
Active Investors（主動投資人）
需求：
每日掌握市場資訊
快速篩選股票
節省研究時間
建立固定研究流程
Core Philosophy
本平台遵循以下四項核心原則：
1. Company Quality First（公司品質優先）
先確認公司是否具有良好的基本面，再考慮是否值得投資。
AI 將優先分析：

營收
EPS
ROE
ROA
毛利率
財務健康
公司治理
避免因短期股價上漲而忽略企業體質。
2. Timing Second（進場時機其次）
好公司也需要好的買點。
AI 於確認公司品質後，再分析：

均線
成交量
K 線
MACD
RSI
KD
支撐／壓力
判斷目前是否具備較佳的觀察或布局時機。
3. Explainable AI（可解釋 AI）
AI 不得僅提供分數或結論。
每次推薦股票時，必須清楚說明：

為什麼推薦？
哪些因素加分？
哪些因素扣分？
有哪些風險？
是否值得持續觀察？
所有評分皆需具備可追溯性。
4. Quality over Quantity（品質優於數量）
每日最多推薦三檔股票，而非固定推薦三檔。
若當日沒有符合最低品質標準的股票，系統應明確輸出：

「今日沒有符合本策略條件的股票。」
系統不得為了湊足數量而降低選股標準。
Product Objectives
本平台需完成以下目標：
每日自動分析全市場上市櫃股票。
自動蒐集公開市場資料。
建立完整股票研究資料庫。
建立 AI 評分模型。
每日產出研究報告。
建立歷史推薦績效資料。
提供回測功能。
提供透明、可解釋的 AI 分析結果。
Out of Scope（非本期功能）
為保持第一版專案聚焦，以下功能不納入 MVP：
自動下單
串接券商交易 API
槓桿商品分析（期貨、選擇權）
海外股票分析（後續版本）
加密貨幣分析（後續版本）
即時逐筆交易分析（後續版本）
Chapter 1 完

Chapter 2｜Functional Requirements（功能需求）
2.1 系統總覽（System Overview）
本系統由八大核心模組組成：
                AI Taiwan Equity Research Platform

                         Scheduler
                             │
                             ▼
                     Data Collection Layer
                             │
                             ▼
                     Data Validation Layer
                             │
                             ▼
                     Fundamental Analysis
                             │
                             ▼
                     Technical Analysis
                             │
                             ▼
                      Chip Analysis
                             │
                             ▼
                  News & Macro Analysis
                             │
                             ▼
                 AI Investment Committee
                             │
                             ▼
                  AI Rating & Report Engine
                             │
                             ▼
             Dashboard / PDF / Excel / Markdown
所有模組皆需模組化設計，可獨立測試與擴充。
2.2 Scheduler（自動排程）
⛔ 重要限制：APScheduler 在 macOS 上會造成 segfault，已永久禁用。
  - scheduler.py 中禁止使用 APScheduler（BlockingScheduler / BackgroundScheduler）
  - 現行方案：main.py 每日手動執行（或由使用者設定 macOS launchd / cron 呼叫 main.py）
  - 自動觸發排程應透過 OS 級排程工具（launchd / crontab），不在 Python 內實作

功能目標
每日於指定時間執行所有分析流程（目前須手動觸發 python main.py）。
執行時間
僅於台灣股票交易日執行。
建議排程：
15:35
確認收盤資料是否完整
↓
15:40
更新股價資料
↓
15:45
更新法人資料
↓
15:50
更新新聞
↓
15:55
AI 分析
↓
16:00
產生每日研究報告
↓
16:05
自動輸出：
Markdown
Excel
PDF（可選）
↓
可選：
Email
LINE
Telegram
交易日判斷
系統需正確識別台股交易日：
排除條件：
  週六、週日
  農曆新年假期（通常 4～6 天）
  清明節、兒童節
  勞動節
  端午節
  中秋節
  國慶日
  其他法定假日
建議做法：
  維護一份年度台股交易日曆
  或整合 TWSE 公告的休市日期
  非交易日執行時，系統應明確標示並中止分析

Acceptance Criteria
✓ 每日自動執行
✓ 執行失敗可重新執行
✓ 完整記錄 Log
✓ 正確識別台股假日，假日不執行分析

2.3 Data Collection（資料蒐集）
功能目標
每日自動蒐集台股公開資訊。
不得依賴人工更新。
股票價格
每日取得：
股票代號
公司名稱
開盤價
最高價
最低價
收盤價
漲跌幅
成交量
成交金額
法人資料
每日取得：
外資買賣超
投信買賣超
自營商買賣超
財報資料
依公告更新：
EPS
ROE
ROA
毛利率
營業利益率
淨利率
負債比
流動比率
自由現金流
公司資訊
更新：
資本額
市值
上市日期
所屬產業
流通股數
新聞
每日更新：
即時新聞
重大訊息
法說會
財報公告






2.4 Data Validation（資料驗證）
AI 不得直接分析資料。
需先確認資料品質。
驗證項目
確認：
✓ 是否更新成功
✓ 是否缺漏
✓ 是否重複
✓ 是否異常
例如：
成交量突然變成：
999999999999
則：
判定：
異常資料。
若資料不完整
例如：
今天沒有法人資料。
則：
AI 不可分析。
需顯示：
今日資料尚未完整更新。

2.5 股票範圍
分析：
上市
上櫃
排除：
ETF
ETN
權證
牛熊證
興櫃
停止交易股票
全額交割股
處置股（預設排除，可由使用者設定是否納入）

2.6 Company Filter（第一層篩選）
AI 第一件事情不是看 K 線。
而是：
先淘汰體質差公司。
第一層
公司品質
例如：
上市超過：
3 年
市值：
至少 100 億
（門檻可調）
資本額：
至少 20 億
（門檻可調）
平均成交金額：
至少 1 億
（門檻可調）
財務
EPS（TTM）
必須 > 0
ROE
至少 15%
ROA
至少 8%
負債比
不得過高（預設 60%，可調）
成長
最近三年至五年：
營收
EPS
ROE
ROA
整體趨勢需維持穩定或改善。
AI 應以趨勢為主，不要求每一年都高於前一年，避免因景氣循環或一次性事件誤判。
若未通過
直接淘汰。
不進入下一階段。

2.7 AI Analysis Pipeline（AI 分析流程）
只有通過第一層公司品質篩選的股票。
才開始：
基本面分析
↓
技術面分析
↓
籌碼分析
↓
新聞分析
↓
產業分析
↓
總體經濟分析
↓
AI Investment Committee
↓
AI Score
↓
Top 3

Chapter 2 完

Chapter 3｜Data Sources & Research Scope（資料來源與研究範圍）
3.1 功能目標（Objective）
系統需每天自動蒐集、整理並驗證台灣股票市場相關公開資訊，作為 AI 分析模型的資料來源。
所有資料來源皆應以合法公開資料為原則，避免依賴未授權或不穩定來源。
AI 僅能使用完成驗證且品質符合標準的資料進行分析。
3.2 資料來源（Data Sources）
本系統應整合下列資料來源：
一、市場交易資料
用途：
提供每日價格與成交資訊。
內容包含：
股票代號
股票名稱
開盤價
最高價
最低價
收盤價
漲跌幅
成交量
成交金額
建議來源：
TWSE（上市）
TPEx（上櫃）
二、公司基本資料
用途：
建立公司基本資料庫。
內容：
公司名稱
股票代號
產業分類
上市／上櫃別
上市日期
資本額
市值
流通股數
三、財務資料（Financial Data）
用途：
分析企業基本面。

資料來源（依優先順序）：
  1. 本地 DB financial_quarters 表（quarter=0 為年度資料）
     由 scripts/import_financials.py 從 MOPS 批量匯入
     每季執行一次即可更新
  2. FinMind Python library（已停用，macOS segfault 問題）

⚙️ MOPS 財務資料收集架構（2026-07-01 實作）：
  主要收集器：src/collectors/mops_collector.py
    - 端點 1：https://mops.twse.com.tw/mops/api/t164sb04（合併損益表）
      → 取得：EPS、毛利率%、營益率%、淨利率%
    - 端點 2：https://mops.twse.com.tw/mops/api/t164sb03（合併資產負債表）
      → 取得：總資產、總負債、股東權益、流動資產、流動負債
      → 計算：ROE = 淨利/股東權益、ROA = 淨利/總資產、負債比率、流動比率
  批量匯入腳本：scripts/import_financials.py
    - 支援參數：--missing（只補缺失）、--years（年數）、--stock（單支）
    - 存入 financial_quarters 表（year=西元年, quarter=0 代表年度資料）
  備用收集器：src/collectors/goodinfo_collector.py
    - 來源：goodinfo.tw/tw/StockBzPerformance.asp
    - 限制：有 IP 速率限制（約 20 次請求後封鎖 30 分鐘以上）
    - 用途：MOPS 無法取得時的手動補充
  fallback 路徑：
    financial_collector.build_financial_summary() 呼叫 _build_summary_from_db()
    → 讀取 financial_quarters（quarter=0）→ 組成 FundamentalAnalyzer 所需格式
    → 若 DB 無資料，再嘗試 FinMind token

分析項目：
營收
月營收
季營收
年營收
AI 需分析：
月營收 YoY
季營收 YoY
年營收成長率
最近 3～5 年營收趨勢
加分條件：
穩定成長
優於產業平均
非一次性成長
EPS（每股盈餘）
分析：
單季 EPS
近四季 EPS（TTM）
最近 5 年 EPS
AI 需分析：
是否逐年改善
是否持續成長
是否優於同產業平均
AI 不得僅因單一年 EPS 偏高即判定為優質公司。
ROE（股東權益報酬率）
AI 需分析：
最近五年：
平均值
成長趨勢
穩定性
評估標準：
小於 8%
普通
10～15%
良好
15%以上
優秀
20%以上
非常優秀
但需確認是否維持多年。
ROA（資產報酬率）
分析：
最近五年：
平均值
成長趨勢
AI 需判斷：
公司是否有效運用資產創造獲利。
毛利率
分析：
最近五年：
平均毛利率
毛利率趨勢
AI 判斷：
毛利率是否維持穩定。
若長期高於產業平均，
代表：
企業具有較高競爭力。
財務健康
分析：
負債比率
流動比率
速動比率
自由現金流
營業現金流
AI 需避免推薦：
財務結構惡化
長期自由現金流為負
過度依賴借款經營
股票估值
分析：
PER（本益比）
PB（股價淨值比）
PEG（若可取得）
股息殖利率
AI 判斷：
好公司不代表任何價格都值得投資。
估值過高時，
需降低推薦分數。
3.3 公司治理（Corporate Governance）
AI 每季更新：
分析：
董監持股比例
董監質押比例
內部人增減持
股利政策
公司治理評鑑（若資料可取得）
加分：
董監持股穩定
董監近期增持
股利政策穩定
扣分：
董監大量減持
高比例股權質押
公司治理重大缺失
3.4 籌碼資料（Chip Data）
每日更新：
分析：
外資
投信
自營商
融資
融券
AI 需分析：
近：
3 日
5 日
20 日
是否：
連續買超
由賣轉買
三大法人同步買超
3.5 新聞資料（News）
每日更新：
包含：
公司重大訊息
法說會
財報公告
新產品
新訂單
擴廠
合作案
政策
AI 需判斷：
利多
中性
利空
並產生：
新聞摘要
關鍵字
情緒分析
3.6 總體經濟（Macro Data）
每日或每週更新：
分析：
美國股市
匯率
利率
國際油價
台灣加權指數
OTC 指數
VIX（若可取得）
全球重大經濟事件
AI 需評估：
是否影響：
今日推薦股票。
3.7 研究範圍（Research Scope）
系統分析：
✔ 上市股票
✔ 上櫃股票
預設排除：
ETF
ETN
權證
牛熊證
興櫃
全額交割股
長期停止交易股票
處置股（可由使用者設定是否納入）

3.8 資料更新頻率
| 資料類型               | 更新頻率     |
| ------------------ | -------- |
| 股價                 | 每個交易日    |
| 成交量                | 每個交易日    |
| 法人買賣超              | 每個交易日    |
| 新聞                 | 每個交易日    |
| 月營收                | 每月       |
| 季財報（EPS、ROE、ROA 等） | 每季       |
| 年報資料               | 每年       |
| 公司治理資料             | 每季或依公告更新 |

Chapter 3 完

Chapter 4｜AI Stock Rating Engine（AI 股票評分引擎）
4.1 功能目標（Objective）
AI 股票評分引擎（AI Stock Rating Engine）是本系統的核心模組。
其目的不是預測股價，而是透過多維度分析，從所有上市櫃股票中篩選出值得進一步研究的公司。
AI 必須遵循：
品質優先、時機其次（Quality First, Timing Second）
系統不得因單一指標優秀而推薦股票，而應綜合評估企業品質、估值、技術面、籌碼與風險。
4.2 AI 選股流程（Selection Pipeline）
系統每日依照以下流程分析股票：
全市場股票

↓

資料驗證

↓

第一層：硬性篩選（Hard Filter）

↓

第二層：公司品質評分（Company Quality）

↓

第三層：進場時機評分（Timing）

↓

第四層：AI 投資委員會（Investment Committee）

↓

產生每日研究名單（最多三檔）

4.3 第一層：硬性篩選（Hard Filter）
此階段的目的為排除明顯不符合長期投資條件的公司。
以下條件皆應設計為可調整參數，預設值如下：
公司基本條件
上市／上櫃滿 3 年以上
市值 ≥ 100 億元
資本額 ≥ 20 億元
平均每日成交金額 ≥ 1 億元

✅ 已修（v6.4）：main.py Step 1c 每日從 TWSE t187ap03_L 取得資本額（實收資本額）及發行股數，
存入 Stock.capital / outstanding_shares，並於 Step 6 filter_stock() 傳入 capital_b 和 market_cap_b。
市值 = outstanding_shares × 1000 × close / 1e8（億）。
財務條件
EPS（TTM）> 0
ROE ≥ 15%
ROA ≥ 8%
負債比率 ≤ 60%
成長條件
近 3～5 年整體趨勢：
營收穩定或成長
EPS 穩定或成長
ROE 穩定或改善
ROA 穩定或改善
排除條件
全額交割股
財務異常公司
長期虧損公司
重大財報異常
長期流動性不足
重大違法或重大風險事件
未通過硬性篩選者，不進入後續評分。

4.3.1 資料不完整時的降級模式（Fallback Mode）
當財務資料（EPS、ROE、ROA）暫時無法取得時，
系統不得直接跳過財務篩選，也不得以滿分替代。
降級策略：
  財務條件無法驗證 → 僅執行「可驗證的條件」
  可驗證項目：
    上市年數
    市值
    平均成交金額
    近期股價趨勢（替代財務成長指標）
      如果股價在過去 60 個交易日低於 MA20 超過 70% 的時間：
        視為「趨勢偏弱」，自動降低評分
  財務條件缺失時的處理：
    Company Quality Score 的財務維度改為「不評分」（而非給 0 或給滿分）
    剩餘可用維度的權重等比例重新分配
    需在報告中明確標示：
    ⚠️ 本分析財務資料不完整，僅供技術面及流動性參考
    Confidence Score 上限：75%

4.4 第二層：公司品質評分（Company Quality Score）
通過第一層後，AI 針對公司長期價值進行評估。
評估構面
基本面
營收成長
EPS
ROE
ROA
毛利率
營業利益率
淨利率
財務健康
負債比率
自由現金流
流動比率
速動比率
公司治理
董監持股
董監質押
股利政策
公司治理評鑑
估值
PER
PB
PEG（若可取得）
殖利率
產業競爭力
AI 比較同產業公司：
ROE 是否高於同業平均
毛利率是否高於同業平均
EPS 成長是否領先同業
營收成長是否優於同業
AI 不只看絕對數值，而是看相對競爭力。

4.4.1 動態評分權重（Dynamic Weighting）
各維度預設權重如下（已實作於 config.py SCORE_WEIGHTS）：
  品質（Company Quality）：40%
  時機（Technical Timing）：25%
  籌碼（Market Behavior）：20%
  情報（Market Intelligence）：10%
  風險（Risk Penalty，從總分扣除）：5%

動態重分配規則（decision.py，三層觸發）：
  [1] 品質資料不可用（quality_score = 0）→ 40% 等比分給時機/籌碼/情報
  [2] 無真實籌碼資料（has_real_chip_data = False）→ 20% 等比分給時機/情報
  [3] 無真實新聞/情報（has_real_intelligence = False，v6.4）→ 10% 等比分給其他有效維度
  ※ 規則 [3] 實現背景：RSS/MOPS 新聞 API 長期抓到 0 篇，10% 權重長期給中性 60 分造成扭曲
  已實作於 src/engines/decision.py evaluate() 方法

4.4.2 品質分快取（Quality Score Cache）
當 FinMind 財務資料不可用時：
  系統從 analysis_results 讀取該股票最近一次有效的 quality_score（quality_score > 0）
  財務基本面每季才變動，跨日借用合理
  若快取存在 → 使用快取值，維持四維度全評分（不觸發動態加權）
  若快取不存在 → quality_score = 0，觸發動態加權（4.4.1）
  已實作於 main.py _quality_cache，在 Step 1 載入，Step 7 深度分析時套用

4.5 第三層：進場時機評分（Timing Score）
當公司品質確認後，AI 才分析目前是否適合觀察或布局。
技術面
分析：
MA5
MA10
MA20
MA60
MA120
MA240
判斷：
多頭排列
黃金交叉
死亡交叉
股價是否站穩均線
成交量
AI 判斷：
價漲量增：加分
價漲量縮：觀察
價跌量增：扣分
價跌量縮：中性
技術指標
分析：
RSI
MACD
KD
Bollinger Bands
ATR
AI 不可依單一指標決定結果。
籌碼
分析：
外資
投信
自營商
近：
3 日
5 日
20 日
AI 判斷：
是否：
法人同步買超
法人連續買超
籌碼集中
4.6 第四層：AI 投資委員會（Investment Committee）
本系統採用多角色 AI 分析，而非單一模型。
AI 角色包括：
基本面分析師
負責：
財務報表
EPS
ROE
ROA
公司品質
技術分析師
負責：
K 線
均線
成交量
技術指標
籌碼分析師
負責：
法人
融資
融券
籌碼集中度
產業研究員
負責：
產業趨勢
市場競爭力
景氣循環
風險管理師
負責：
波動性
財務風險
新聞事件
流動性
最後由：
Chief Investment Officer（CIO AI）
整合所有分析結果，決定是否列入每日研究名單。
4.7 推薦原則
系統每日最多推薦三檔股票。
若沒有符合條件的公司，應直接輸出：
今日沒有符合本研究策略的股票。
系統不得為了維持固定數量而降低標準。
4.8 Explainable AI
每檔股票必須提供完整分析理由，包括：
推薦原因
加分因素
扣分因素
主要風險
建議觀察重點
不得僅提供分數或星等。

Chapter 4 完

Chapter 5｜Fundamental Analysis Engine（基本面分析引擎）
5.1 功能目標（Objective）
基本面分析引擎（Fundamental Analysis Engine）負責評估公司的長期經營品質、獲利能力、財務健康及成長潛力。
AI 應避免受到短期市場波動影響，優先評估企業是否具有持續創造價值的能力。
本模組為整體評分的重要基礎。
5.2 分析原則（Analysis Principles）
AI 不得僅依賴單一財務數據判斷公司優劣。
所有分析應遵循以下原則：
一、趨勢優先
優先觀察：
近 3～5 年整體趨勢。
避免僅依單一年資料做判斷。
二、穩定優先
AI 偏好：
長期穩定成長。
而非：
一年暴增。
隔年暴跌。
三、同產業比較
所有重要財務指標。
應與：
同產業公司比較。
例如：
ROE：
18%
若：
同產業平均：
12%
則：
屬於：
優秀。
反之：
若：
產業平均：
25%
則：
18%
僅屬普通。
5.3 營收分析（Revenue Analysis）
分析：
月營收
季營收
年營收
AI 分析：
月營收 YoY
季營收 YoY
年營收成長率
最近五年營收趨勢
AI 判斷：
是否：
穩定成長
成長速度增加
優於產業平均
扣分：
長期衰退
波動過大
僅一次性爆發
5.4 EPS 分析
分析：
最近：
五年 EPS
TTM EPS
EPS YoY
EPS QoQ
AI 判斷：
公司是否具有：
持續創造獲利能力。
AI 不要求：
每一年都創新高。
AI 觀察：
整體是否呈現：
向上趨勢。
加分：
五年整體向上
波動小
TTM 持續改善
扣分：
長期衰退
大幅震盪
長期虧損
5.5 ROE 分析
AI 分析：
最近五年：
ROE
AI 評估：
平均值
趨勢
穩定性
參考：
ROE
<8%
普通
10~15%
良好
15%以上
優秀
20%以上
非常優秀。
AI 更重視：
是否：
長期維持。
5.6 ROA 分析
分析：
最近五年：
ROA
AI 判斷：
公司是否有效利用資產。
加分：
ROA
逐步改善。
扣分：
ROA
持續下降。
5.7 毛利率分析
分析：
最近五年：
毛利率。
AI 判斷：
產品競爭力。
例如：
毛利率：
40%
若：
維持：
五年以上。
代表：
具有：
品牌。
技術。
產品優勢。
5.8 財務健康
分析：
負債比率。
流動比率。
速動比率。
自由現金流。
營業現金流。
AI 判斷：
是否：
具有：
健康財務。
避免：
借新還舊。
高槓桿。
現金不足。
5.9 股票估值
分析：
PER
PB
PEG
殖利率
AI 判斷：
公司很好。
不代表：
現在值得買。
估值：
若：
遠高於：
產業平均。
則：
降低推薦分數。
5.10 Company Quality Score（公司品質評分）
AI 建立：
Company Quality Score。
評估：
公司品質。
而非：
短線股價。
評分：
公司規模。
營收。
EPS。
ROE。
ROA。
毛利率。
財務健康。
公司治理。
產業競爭力。
股票估值。

5.11 Explainable AI
AI 必須說明：
例如：
公司近五年營收呈穩定成長，EPS 整體趨勢向上，ROE 長期維持 18% 以上，毛利率高於同產業平均，財務結構穩健，估值仍處合理區間，因此 Company Quality Score 評定為 A 級。
5.12 估值計算補強（v6.4）
financial_quarters 表的 per/pbr 欄位多數為空（goodinfo 匯入覆蓋率低）。
✅ 即時計算 P/E（main.py Step 6）：
  若 DB 無 per 且 eps_ttm > 0 且 close > 0：
    fin_sum["per"] = round(close / eps_ttm, 1)
  此方式讓 fundamental.py _score_valuation() 對幾乎所有有財務資料的股票生效，
  valuation_score（最高 10 分）從「大部分給 5 分預設值」升級為真實評分。

Chapter 5 完

Chapter 6｜Technical Analysis Engine（技術分析引擎）
6.1 功能目標（Objective）
技術分析引擎負責評估股票目前的市場趨勢、買賣力道與市場情緒，協助 AI 判斷是否為適合觀察或布局的時機。
技術分析不作為唯一推薦依據，而是建立在公司基本面通過篩選後，用於評估進場時機。
6.2 分析原則（Analysis Principles）
AI 應遵循以下原則：
原則一：先基本面，再技術面
技術面僅用於確認市場趨勢與進場時機。
不得因技術面強勢，而推薦基本面不佳的公司。
原則二：多指標交叉驗證
AI 不可依單一技術指標決定結果。
需綜合：
均線
成交量
K 線型態
MACD
RSI
KD
波動率
共同判斷。
原則三：趨勢重於預測
AI 不預測股價。
AI 判斷：
目前：
市場趨勢是否健康。
6.3 均線分析（Moving Average）
最低歷史資料需求：
  MA5 / MA10 / MA20：最少 20 個交易日（約 1 個月）
  MA60：最少 60 個交易日（約 3 個月）
  MA120：最少 120 個交易日（約 6 個月）
  MA240：最少 240 個交易日（約 12 個月）
若資料不足，該均線標記為「無效」並從評分中排除。
AI 不得用部分資料強行推算長期均線。
例如：只有 30 天資料，不可計算 MA60。

分析：
MA5
MA10
MA20
MA60
MA120
MA240
AI 判斷：
多頭排列
MA5 > MA10 > MA20 > MA60
代表：
趨勢健康。
中長期偏多。
加分。
空頭排列
MA5 < MA20 < MA60
代表：
趨勢偏弱。
降低評分。
股價位置
若：
股價位於：
MA20
MA60
MA120
全部上方。
代表：
市場願意給予較高價格。
屬於：
偏強。
若：
跌破：
MA20。
代表：
需開始留意。
跌破：
MA60。
代表：
中期趨勢轉弱。
6.4 成交量分析（Volume Analysis）
成交量代表：
市場是否願意用資金支持目前股價。
AI 需分析：
今日成交量。
5 日均量。
20 日均量。
成交量變化率。
Bull Case（加分）
價漲量增
AI 判斷：
代表：
買盤積極。
趨勢健康。
上漲可信度提高。
提高評分。
量增突破整理區
代表：
可能開始新的趨勢。
提高評分。
Bear Case（扣分）
價漲量縮
代表：
追價意願不足。
可能：
短線過熱。
降低評分。
價跌量增
代表：
賣壓增加。
市場信心下降。
降低評分。
價跌量縮
代表：
賣壓減弱。
AI 判斷：
中性。
需等待：
新的方向。
6.5 支撐與壓力（Support & Resistance）
AI 自動辨識：
近期：
重要支撐。
重要壓力。
突破平台。
跌破平台。
AI 判斷：
目前：
風險報酬比。
例如：
若：
距離支撐很近。
風險：
較小。
若：
距離壓力很近。
需留意：
追高風險。
6.6 K 線型態（Candlestick Analysis）
AI 辨識：
長紅 K
長黑 K
十字線
錘頭
上吊線
吞沒
跳空缺口
晨星
黃昏星
AI 判斷：
是否：
多頭反轉。
空頭反轉。
整理。
趨勢延續。
6.7 技術指標（Indicators）
分析：
RSI
AI 判斷：
RSI
30 以下：
可能超賣。
70 以上：
可能過熱。
AI 不會單獨依 RSI 作出結論。
MACD
AI 判斷：
黃金交叉。
死亡交叉。
柱狀體：
是否持續增強。
KD
AI 判斷：
黃金交叉。
死亡交叉。
高檔鈍化。
低檔鈍化。
Bollinger Bands
分析：
波動。
突破。
壓縮。
ATR
分析：
波動程度。
避免：
高風險股票。
6.8 Technical Timing Score
AI 建立：
Timing Score。
評估：
目前：
是否值得：
開始觀察。
不是：
保證：
一定會上漲。
6.9 Explainable AI
AI 每次需說明：
例如：
技術面分析
股價目前站穩 MA20 與 MA60，呈現多頭排列，顯示中期趨勢仍然健康。
今日出現價漲量增，成交量高於 20 日平均量，代表市場買盤積極。
MACD 柱狀體持續放大，RSI 為 61，尚未進入過熱區。
短線需留意前波高點附近壓力，但整體技術面仍維持偏多格局。
6.10 AI 不推薦情況
即使公司品質很好。
若：
股價距離 MA20 過遠
RSI > 80
連續暴漲
價漲量縮
接近重大壓力區
AI 可給出：
公司品質良好，但目前技術面風險偏高，建議等待較佳觀察時機。
Chapter 6 完

Chapter 7｜Market Behavior Engine（市場行為分析引擎）
7.1 功能目標（Objective）
市場行為分析引擎負責分析市場資金流向、法人行為與投資人情緒，評估是否有大型資金持續流入或流出個股。
本模組目的不是追蹤單日買賣超，而是判斷市場是否支持目前的股價趨勢。
7.2 分析原則（Analysis Principles）
AI 應遵循以下原則：
原則一：連續性優於單日數據
單日大量買超或賣超可能受特殊事件影響。
AI 應優先分析：
近 3 日
近 5 日
近 20 日
整體趨勢。
原則二：價格必須配合資金
法人買超不一定代表股價會上漲。
AI 必須同時分析：
股價
成交量
法人
若三者方向一致，可信度較高。
原則三：多方交叉驗證
不得因單一法人買超就提高評分。
需同時觀察：
外資
投信
自營商
融資
融券
市場成交量
7.3 外資分析（Foreign Institutional Investors）
分析項目：
每日買賣超
近 3 日
近 5 日
近 20 日
AI 判斷：
Bull Case（加分）
外資連續買超
買超金額逐步增加
股價同步上漲
成交量同步放大
代表：
市場資金持續流入。
可信度高。
Bear Case（扣分）
外資大量賣超
股價跌破重要均線
成交量增加
代表：
市場資金流出。
降低評分。
7.4 投信分析（Investment Trust）
AI 分析：
近：
3 日
5 日
20 日
是否：
持續加碼。
AI 特別關注：
投信連續買超。
因為：
通常代表：
中長期布局。
7.5 自營商分析（Dealer）
分析：
買超。
賣超。
連續性。
AI 判斷：
是否：
與外資方向一致。
若：
三大法人：
同步買超。
可信度提高。
7.6 融資分析（Margin Financing）
AI 判斷：
散戶是否：
過度追價。
Bull Case
股價：
上漲。
融資：
沒有明顯增加。
代表：
較健康。
Bear Case
股價：
上漲。
融資：
快速增加。
代表：
散戶開始追價。
AI 提醒：
短線風險提高。
7.7 融券分析（Short Selling）
AI 分析：
融券變化。
若：
融券持續增加。
需判斷：
是否：
市場開始看空。
若：
融券回補。
則：
可能形成：
軋空行情。
AI 提供：
說明。
但：
不得單獨作為推薦依據。
7.8 主力行為（Major Participant Behavior）
若資料可取得：
AI 分析：
主力買賣超
籌碼集中度
大戶持股比例
AI 判斷：
是否：
大型資金：
開始布局。
7.9 市場情緒（Market Sentiment）
AI 綜合：
成交量
漲跌家數
強勢族群
新聞情緒
建立：
Market Sentiment。
例如：
Bullish
Neutral
Bearish
7.10 Market Behavior Score
AI 建立：
Market Behavior Score。
分析：
外資
投信
自營商
融資
融券
主力
市場情緒
評估：
目前：
市場是否支持：
股價持續走強。
7.11 Explainable AI
AI 必須提供：
例如：
市場行為分析
外資已連續五個交易日買超，投信同步加碼，自營商維持偏多操作。
股價與成交量同步上升，顯示資金流向與價格方向一致。
融資增幅有限，未出現散戶大量追價情形，籌碼結構仍屬健康。
綜合判斷，目前市場行為偏向多方。
7.12 AI 不推薦情況
即使：
公司品質很好。
若：
外資持續賣超
投信持續調節
融資暴增
股價跌破 MA20
價跌量增
AI 應說明：
公司基本面仍然優秀，但目前市場資金尚未支持股價，建議持續觀察，等待市場行為改善後再重新評估。
7.11 法人資料可用性與 Fallback 策略（v6.4）
TWSE/TPEx 法人 API（MI_QFIIS、MI_SITC、MI_PROP）通常於收盤後 15:30~17:00 更新，
main.py 若於更新前執行，會取得空回應，原本只能給 50 分中性值。

✅ Fallback 機制（main.py Step 2）：
  當日 API 返回空資料 → 查詢 DB 最近一個交易日（T-1）的法人資料（通常有 1000+ 支）
  → behavior_score 使用真實 T-1 法人資料計算，has_real_chip_data = True
  → 優於完全中性（50 分）的替代值，大幅改善 20% 行為權重的有效性
  → 日誌：「當日法人 API 未更新，使用 YYYY-MM-DD DB 資料（N 筆）」

Chapter 7 完

Chapter 8｜Market Intelligence Engine（市場情報引擎）
8.1 功能目標（Objective）
Market Intelligence Engine 負責整合所有可能影響股票價值的外部資訊。
本模組除了分析新聞外，亦分析：
公司重大訊息
法說會
產業資訊
政策變化
國際事件
總體經濟
AI 不應只分析新聞情緒。
更應分析：
事件是否真正影響公司未來基本面。
8.2 Input（輸入資料）
系統每日蒐集：
公司新聞
包含：
新產品
新客戶
接單
擴廠
投資
併購
人事異動
公司公告
例如：
重大訊息
法說會
財報公告
股利政策
現金增資
庫藏股
減資
產業新聞
例如：
AI
半導體
PCB
散熱
機器人
生技
車用電子
國際新聞
例如：
美國聯準會政策
美國科技股財報
地緣政治
關稅
匯率
油價
總體經濟
例如：
CPI
利率
PMI
GDP
失業率
匯率
8.3 AI 分析流程（Process）
AI 必須依照以下流程分析資訊：
收集新聞

↓

去除重複新聞

↓

事件分類

↓

重要性評估

↓

情緒分析

↓

影響期間分析

↓

影響公司分析

↓

產生 Intelligence Score
8.4 新聞分類（Classification）
AI 必須將所有事件分類。
例如：
公司營運
接單
擴廠
新產品
客戶
財務
財報
EPS
股利
公司治理
董事異動
經營權
重大訴訟
產業
新技術
政策
景氣循環
國際
利率
匯率
戰爭
關稅
8.5 Event Importance（事件重要性）
AI 必須判斷：
事件的重要程度。
分級：
★★★★★
重大影響
例如：
財報遠優預期
新產能
全球合作
★★★★☆
中度影響
例如：
新產品
新客戶
★★★☆☆
普通
例如：
一般新聞。
★★☆☆☆
低影響。
★☆☆☆☆
可忽略。
8.6 Event Duration（影響期間）
AI 必須分析：
事件影響多久。
例如：
短期
1~5 天
例如：
熱門新聞。
中期
1~3 個月
例如：
法說會。
長期
半年以上
例如：
擴廠。
重大合作。
AI 技術突破。
8.7 Sentiment Analysis（情緒分析）
AI 不可只分：
利多。
利空。
中性。
還需判斷：
可信度。
例如：
利多新聞。
但：
來源可信度低。
則：
降低影響。
8.8 Fundamental Impact（基本面影響）
AI 必須回答：
事件是否：
真正影響：
公司：
EPS。
營收。
ROE。
ROA。
例如：
新聞：
公司開新門市。
AI 判斷：
影響：
有限。
新聞：
取得 Apple 長約。
AI 判斷：
可能：
長期提升：
EPS。
提高：
Company Quality。
8.9 Intelligence Score
AI 建立：
Market Intelligence Score。
分析：
新聞。
產業。
政策。
國際。
Macro。
最後：
評估：
事件是否：
值得改變：
投資看法。
8.10 Explainable AI
AI 每次需提供：
例如：
市場情報分析
公司宣布取得大型國際客戶長期合作案，預期將於未來兩年逐步貢獻營收。
AI 判斷此事件屬於長期基本面利多，而非短期題材炒作，因此提高 Intelligence Score。
另一方面，美國利率政策仍存在不確定性，短期市場可能持續波動，建議留意後續政策變化。
8.11 Acceptance Criteria（驗收標準）
系統必須能：
✅ 自動收集新聞與公告
✅ 自動去除重複內容
✅ 分類事件
✅ 判斷重要性
✅ 判斷影響期間
✅ 評估對基本面的影響
✅ 產生可閱讀的 AI 摘要
Chapter 8 完

Chapter 9｜Decision Engine（AI 決策引擎）
9.1 功能目標（Objective）
Decision Engine 為整個系統的核心決策模組。
其主要功能為整合：
Company Quality Score
Technical Timing Score
Market Behavior Score
Market Intelligence Score
Risk Score
最終產生：
是否列入推薦名單
推薦理由
主要風險
AI Confidence Score
Decision Engine 不得依單一指標做出推薦。
9.2 Input（輸入）
Decision Engine 接收各分析模組輸出。
包含：
基本面
Company Quality Score
EPS 趨勢
ROE 趨勢
ROA 趨勢
財務健康
估值分析
技術面
Technical Timing Score
均線趨勢
成交量分析
技術指標
支撐與壓力
市場行為
Market Behavior Score
外資
投信
自營商
融資
融券
市場情報
Intelligence Score
新聞分析
產業分析
Macro Analysis
風險分析
財務風險
技術風險
市場風險
流動性風險
新聞事件風險
9.3 Decision Rules（決策規則）
Decision Engine 必須依照以下流程：
Hard Filter

↓

Company Quality

↓

Technical Timing

↓

Market Behavior

↓

Market Intelligence

↓

Risk Review

↓

Final Recommendation
若任何 Hard Filter 未通過。
不得進入推薦。
9.4 Recommendation Level（推薦等級）
系統定義五種研究等級：
Level A+
★★★★★
Strong Research Candidate
代表：
公司品質佳。
市場趨勢佳。
值得優先研究。
Level A
★★★★☆
Research Candidate
值得持續觀察。
Level B
★★★☆☆
Watch List
基本面不錯。
等待較佳時機。
Level C
★★☆☆☆
Observation Only
暫不建議列入研究名單。
Level D
★☆☆☆☆
Not Recommended
不建議研究。
9.5 AI Confidence Score
除了推薦等級。
AI 必須提供：
Confidence Score。
範圍：
0~100%
代表：
AI 對本次分析的信心程度。

Confidence Score 計算規則：
基礎分：100 分
扣分項目（每項獨立計算，以 decision.py _calc_confidence() 實作為準）：
  財務資料不完整（無 EPS / ROE / ROA）：-20 分
  技術時機分 = 0（無有效技術資料）：-15 分
  技術面與基本面方向相反（quality 高但 timing 低，或反之）：-10 至 -15 分
  風險分數偏低（risk_score < 65）：-10 至 -20 分

  ⚠️ 以下為 PRD 原始規劃、尚未實作於 decision.py：
  歷史價格資料不足（< 60 個交易日）：-15 分（規劃值）
  歷史價格資料不足（< 120 個交易日）：-10 分（規劃值）
  籌碼資料不足（< 5 個交易日）：-10 分（規劃值）
  新聞資料無法取得：-5 分（規劃值）
  市場波動異常（大盤跌幅 > 2%）：-5 分（規劃值）
  即將公布財報（3 個交易日內）：-5 分（規劃值）

最終 Confidence Score = MAX(0, 100 - 所有扣分總和)

等級對照：
  90~100：高信心，資料完整，各面向一致
  75~89：中高信心，有少量缺失
  60~74：中等信心，需謹慎參考
  < 60：信心不足，建議等待資料完整後重新評估

若：
Confidence
低於：
70%。
AI 必須提醒：
本次分析信心不足，建議持續觀察。
Confidence 低於 70% 的分析結果不列入推薦名單（config.py RECOMMENDATION_RULES min_confidence=70.0）。
9.6 Recommendation Rules（推薦規則）
每日：
最多：
推薦三檔。
不是：
固定：
三檔。
例如：
今天：
只有：
一家公司。
符合：
全部條件。
則：
只推薦：
一檔。
若：
沒有符合。
輸出：
今日沒有符合本研究策略的股票。
9.7 Explainable Recommendation（可解釋推薦）
每檔股票皆需輸出：
一、推薦摘要
一句話說明：
為何值得研究。
二、主要優勢
例如：
EPS 五年成長
ROE 長期 18%
法人連買
多頭排列
三、主要風險
例如：
接近壓力區
RSI 偏高
外部市場波動
四、建議觀察重點
例如：
是否突破前高
下季財報
月營收
五、AI 結論
例如：
公司品質優異，目前市場資金亦呈偏多，但股價已接近前波壓力區，建議持續觀察成交量是否放大後再重新評估。

9.7.1 AI Prompt 設計原則（Prompt Integrity Rules）
為確保 AI 結論可信且不誤導使用者，prompt 設計需遵守以下規則：

禁止捏造（No Fabrication）：
  AI 只能引用 prompt 中明確提供的數字與資料
  禁止自行補充任何未提供的財務數字（EPS、ROE、股價、成交量、壓力位等）
  若資料不足，須明確說明「資料待補充」，而非以合理數字填充

財務資料狀況標記（has_quality flag）：
  quality_score > 0：告知 AI「有財務資料」，可描述品質評分
  quality_score = 0：告知 AI「無財務資料，本次採動態加權，依技術面+籌碼面評分」
  AI 結論需反映實際資料可信度，不得以「品質優異」掩蓋財務資料缺失

推薦一致性（Recommendation Consistency）：
  若品質資料缺失而被動態加權推上名單，AI 結論必須如實說明局限性
  不得在品質評分為 0 時寫出「公司體質優異」等無依據的正面評語

技術面說明限制：
  禁止虛構具體股價（如「突破 X 元」）除非 watch_points 中已提供技術壓力位
  已實作於 src/ai/claude_analyst.py _build_prompt() 及 SYSTEM_PROMPT 第 6 條

9.8 每日研究報告（Daily Research Report）
系統每日收盤後應產出完整研究報告。
內容包括：
今日市場摘要
加權指數
OTC 指數
成交金額
強勢產業
弱勢產業
市場情緒
今日研究名單
最多：
三檔。
每檔包含：
股票名稱
股票代號
Recommendation Level
Confidence Score
Company Quality
Technical Timing
Market Behavior
Market Intelligence
Risk Summary
AI Recommendation
今日未推薦原因
若：
無推薦。
AI 必須說明：
例如：
今日多數股票估值偏高，且技術面尚未形成健康突破，因此系統未產生研究名單。
9.9 Acceptance Criteria
系統必須：
✅ 每日產出完整研究報告。
✅ 所有推薦皆提供理由。
✅ 所有推薦皆提供風險。
✅ 不符合條件可不推薦任何股票。
Chapter 9 完

Chapter 10｜Backtesting & Strategy Validation（回測與策略驗證）
10.1 功能目標（Objective）
Backtesting Engine 負責驗證 AI 研究策略於歷史市場中的表現。
目的不是證明策略一定成功，而是持續衡量：
是否具有穩定性
是否優於市場
是否需要調整
所有策略更新皆應先完成回測，再決定是否正式採用。
10.2 回測範圍（Backtesting Scope）
系統需支援：
歷史期間
最近 1 年
最近 3 年
最近 5 年
最近 10 年（若資料可取得）
投資期間
每次推薦後：
追蹤：
5 個交易日
10 個交易日
20 個交易日
60 個交易日
120 個交易日
10.3 回測流程（Backtesting Process）
歷史資料

↓

套用策略

↓

產生推薦股票

↓

模擬持有

↓

計算績效

↓

輸出統計結果

↓

策略比較
10.4 回測績效指標（Performance Metrics）
系統至少應提供：
勝率（Win Rate）
成功交易比例。
平均報酬率（Average Return）
平均每次推薦的報酬率。
最大回撤（Maximum Drawdown）
策略歷史最大虧損幅度。
平均持有期間
每筆推薦平均持有多久。
報酬／風險比（Risk / Reward Ratio）
AI 判斷：
策略是否值得。
年化報酬率（Annualized Return）
長期績效。
Alpha（若可計算）
是否：
跑贏：
大盤。
Beta（若可計算）
波動程度。
Sharpe Ratio（若可計算）
每承擔一單位風險所獲得的超額報酬。
10.5 Benchmark（比較基準）
AI 必須比較：
本策略
VS
市場。
例如：
台灣加權指數
同產業平均（若可取得）
AI 需回答：
策略：
是否：
真的優於：
市場。
10.6 Strategy Comparison（策略比較）
系統允許建立：
多個版本。
例如：
Version 1
ROE >15%
Version 2
ROE >18%
Version 3
加入：
毛利率。
AI 自動比較：
哪個版本：
表現最好。
10.7 Strategy Validation（策略驗證）
新增任何規則。
例如：
加入：
ROA。
不得：
直接套用。
需：
先完成：
回測。
若：
績效改善。
才可：
建議：
採用。
10.7.1 推薦後即時績效追蹤（Live Performance Tracking）
每次產出 Research Candidate 後：
系統應自動建立績效追蹤記錄：
  推薦日期
  股票代號
  推薦當日收盤價（基準價）
  推薦當日 Confidence Score
  推薦當日評分明細（品質 / 時機 / 籌碼 / 風險）
追蹤週期：
  推薦後 5、10、20、60、120 個交易日
  每個節點記錄收盤價，計算報酬率
自動評估：
  報酬率 > 0：標記「正報酬」
  報酬率 ≥ 10%：標記「勝出」
  報酬率 < -10%：標記「止損」
統計彙整（每月自動計算）：
  推薦次數
  勝率（正報酬比例）
  平均報酬率
  最佳 / 最差推薦
  各評分維度與後續報酬的相關係數（用於持續優化權重）
Dashboard 顯示：
  最近 30 / 90 / 365 天推薦績效摘要
  每檔推薦的歷史成效可展開查看

10.8 AI Learning（策略學習）
AI 每月分析：
哪些因子：
真正有效。
例如：
因子	命中率
EPS 長期成長	74%
ROE >15%	71%
價漲量增	66%
外資連買	63%
MACD 黃金交叉	59%
AI 可提出：
建議提高 EPS 權重。
但：
不得：
自動修改策略。
需：
使用者：
確認。
10.9 Strategy Version Control（策略版本管理）
所有策略：
需保留版本。
例如：
Version 1.0
Version 1.1
Version 2.0
可比較：
不同版本。
長期績效。
10.10 Acceptance Criteria
系統必須：
✅ 可回測至少最近一年。
✅ 可同時比較多個策略版本。
✅ 可輸出完整績效報告。
✅ 可驗證新增規則是否有效。
Chapter 10 完

Chapter 11｜Research Workflow & Event Calendar（研究流程與事件管理）
11.1 功能目標（Objective）
Research Workflow 負責管理 AI 每日研究流程，確保所有分析皆依照固定程序執行，避免因資料缺漏、重大事件或未更新資訊而產生錯誤研究結果。
AI 必須遵循固定研究流程，不得跳過任何步驟。
11.2 每日研究流程（Daily Research Workflow）
每日交易日收盤後，系統依照以下順序執行：
開始

↓

確認今日是否為交易日

↓

更新所有市場資料

↓

驗證資料完整性

↓

更新重大事件

↓

執行 Hard Filter

↓

基本面分析

↓

技術面分析

↓

市場行為分析

↓

市場情報分析

↓

風險分析

↓

Decision Engine

↓

產生每日研究報告

↓

寫入歷史資料庫

↓

開始績效追蹤
11.3 Event Calendar（重大事件日曆）
系統需建立完整事件日曆。
事件包含：
公司事件
財報公布
法說會
月營收公布
股東會
除權息
現金增資
減資
庫藏股
董監改選
重大訊息公告
國內事件
利率決議
CPI
GDP
PMI
政策發布
國際事件
美國聯準會（Fed）利率決議
美國 CPI
美國 PPI
美國非農就業
美國 GDP
美國科技股財報季
地緣政治事件
國際油價重大波動
11.4 Event Risk（事件風險）
AI 必須分析：
事件距離今天：
還有多久。
例如：
距離：
財報公布
剩：
一天。
AI 必須提醒：
公司即將公布財報，短期波動可能增加。
Confidence Score：
降低。
例如：
Fed
今晚公布利率。
AI 必須提醒：
市場可能因利率政策產生波動。
11.5 Event Impact（事件影響）
AI 必須回答：
事件：
是否：
真正影響：
公司。
例如：
Apple
財報。
對：
台積電。
可能：
高度相關。
AI：
提高：
事件重要性。
例如：
美國油價。
對：
IC 設計。
影響：
有限。
AI：
降低：
事件權重。
11.6 Research Status（研究狀態）
每家公司皆建立：
Research Status。
例如：
Researching
目前分析中。
Watch List
值得持續觀察。
Recommended
今日推薦。
Waiting
等待：
財報。
法說會。
突破。
Rejected
目前：
不建議研究。
11.7 AI Checklist（AI 檢查清單）
每檔股票分析前。
AI 必須完成：
☑ 基本面
☑ 技術面
☑ 市場行為
☑ 市場情報
☑ 事件風險
☑ 公司治理
☑ 財務健康
☑ 估值
☑ 最終風險檢查
全部完成。
才可：
產生：
Recommendation。
11.8 Report Generation（報告產生）
每日：
最多：
三份完整研究報告。
每份包含：
Executive Summary
一句話：
說明：
為何值得研究。
Company Quality
公司品質。
Technical Timing
目前：
是否：
適合觀察。
Market Behavior
市場是否支持。
Intelligence
重大事件。
Risk
主要風險。
Final Opinion
AI：
最終結論。
11.9 Acceptance Criteria
系統必須：
✅ 每日依固定流程執行。
✅ 建立事件日曆。
✅ 分析事件風險。
✅ 將事件納入推薦邏輯。
Chapter 11 完

Chapter 12｜Risk Management Engine（風險管理引擎）
12.1 Product Objective
風險管理引擎（Risk Management Engine）負責評估每檔股票目前可能面臨的風險。
AI 不僅需要找出值得研究的公司，更需要識別可能導致研究失敗的因素。
所有推薦股票皆需完成完整風險分析。
12.2 Design Principle
風險分析不以股價漲跌作為唯一依據。
AI 應從：
公司
市場
產業
技術
財務
總體經濟
六個面向進行評估。
12.3 Company Risk
分析：
財務風險
包含：
EPS 持續衰退
ROE 持續下降
ROA 持續下降
毛利率惡化
自由現金流惡化
公司治理風險
分析：
董監持股下降
高比例股權質押
重大訴訟
經營權問題
重大內控缺失
營運風險
分析：
客戶集中度
供應鏈
擴廠風險
接單風險
12.4 Market Risk
AI 分析：
目前：
市場是否：
處於：
高風險。
例如：
台股修正
美國股市修正
全球避險情緒增加
成交量明顯下降
AI：
降低：
Confidence Score。
12.5 Industry Risk
AI 分析：
是否：
產業開始：
衰退。
例如：
AI。
半導體。
PCB。
散熱。
機器人。
AI 判斷：
目前：
屬於：
成長期。
成熟期。
衰退期。
12.6 Technical Risk
分析：
RSI 是否過熱
股價是否偏離 MA20
是否接近歷史壓力
是否爆大量
若：
技術面：
風險提高。
降低：
Timing Score。
12.7 Liquidity Risk
分析：
成交量。
成交金額。
若：
流動性不足。
AI：
避免：
推薦。
12.8 Macro Risk
分析：
利率
匯率
CPI
國際事件
地緣政治
AI 判斷：
是否：
增加：
市場風險。
12.9 Risk Score
AI 建立：
Risk Score。
分級：
A
低風險
B
普通
C
偏高
D
高風險
E
避免研究
12.10 Explainable Risk
AI 必須說明：
例如：
雖然公司基本面優秀，但目前股價距離 MA20 已超過 15%，且接近歷史壓力區，加上美國即將公布 CPI，短期市場波動風險提高，因此建議等待更佳觀察時機。
12.11 Risk Recommendation
AI 最後需回答：
是否：
值得：
現在研究。
而不是：
是否一定會漲。
12.12 Acceptance Criteria
系統必須：
✓ 完整分析所有風險。
✓ 所有推薦皆附風險摘要。
✓ 風險分析納入最終推薦。
12.13 財報季節風險自動偵測（v6.4）
台灣上市公司財務報告法定公告截止日：
  Q1（1-3月）→ 5/15；Q2（4-6月）→ 8/14；Q3（7-9月）→ 11/14；年報 → 3/31
當分析日距截止日 ≤ 14 日曆天時，系統自動產生事件風險警示注入 upcoming_events：
  「財報季節風險：距 Q2 財報公告截止（YYYY-MM-DD）還有 N 天，短期波動可能增加」
風險評分由 risk.py _event_risk() 計算扣分（已有實作，v6.4 起自動觸發）。
實作：main.py _get_earnings_risk_events(trade_date) → 傳入 risk_eng.analyze()

Chapter 12 完

Chapter 13｜Research Lifecycle（研究生命週期管理）
13.1 Product Objective
Research Lifecycle 負責管理每一家公司的研究狀態。
AI 不應每天重新分析所有股票而忽略歷史結果。
系統需保存每家公司完整研究歷程。
建立長期研究資料庫。
13.2 Research Status
每家公司皆具有研究狀態。
Stage 1
Universe
全市場股票。
約：
1800+ 檔。
尚未分析。
Stage 2
Qualified
通過：
Hard Filter。
代表：
基本條件符合。
值得：
開始分析。
Stage 3
Researching
AI 開始：
基本面。
技術面。
市場行為。
市場情報。
完整研究。
Stage 4
Watch List
公司品質良好。
但是：
目前：
尚未到最佳研究時機。
例如：
技術面整理
財報即將公布
接近壓力區
AI：
持續觀察。
Stage 5
Research Candidate
今日：
最值得研究。
每日：
最多：
三檔。
Stage 6
Archived
因：
基本面惡化
重大利空
財務異常
公司治理問題
停止：
研究。
但：
保留：
完整歷史。
13.3 Status Transition（狀態轉換）
Universe
      │
      ▼
Qualified
      │
      ▼
Researching
      │
 ┌────┴────┐
 ▼         ▼
Watch List Candidate
 │         │
 └────┬────┘
      ▼
 Archived
AI 必須記錄：
每一次：
狀態變化。
13.4 Decision Journal（研究日誌）
每次分析。
皆建立：
Decision Journal。
內容（以 decision_journal 表實際欄位為準）：
分析日期（date）。
股票（stock_id）。
品質分（quality_score）。
時機分（timing_score）。
行為分（behavior_score）。
信心度（confidence）。
推薦等級（rec_level）。
動作（action）。
理由（reason）。
市場環境（market_env）。
版本（strategy_version）。

⚠️ 實作備註：decision_journal 表目前不含 intelligence_score 與 risk_score，
與 analysis_results 表欄位不完全一致。待補齊。
例如：
2026/07/01
2330
Company Quality
94
Timing
86
Market
91
Confidence
95%
推薦：
Research Candidate
原因：
EPS
ROE
ROA
持續改善。
外資：
連買。
AI：
長期看好。
13.5 Change Log（變更紀錄）
若：
公司：
從：
Research Candidate
↓
Watch List
AI 必須記錄：
原因。
例如：
成交量下降。
財報公布前。
RSI
過熱。
若：
Watch List
↓
Archived
需：
完整紀錄：
原因。
例如：
EPS
連兩季衰退。
ROE
下降。
重大訴訟。
13.6 Historical Research（歷史研究）
AI 可查詢：
任何公司：
過去：
一年。
三年。
五年。
所有研究紀錄。
例如：
2330
過去：
曾推薦：
幾次。
成功：
幾次。
失敗：
幾次。
原因：
為何。
13.7 Recommendation Consistency（推薦一致性）
AI 必須避免：
今天：
推薦。
明天：
完全相反。
除非：
重大事件。
例如：
財報。
重大新聞。
市場崩盤。
否則：
AI 必須：
維持：
一致性。
13.8 Portfolio Research（研究池）
建立：
三個研究池。
Core Research
公司品質：
最高。
適合：
長期研究。
Active Research
目前：
最值得研究。
每日更新。
Watch Pool
等待：
更好：
Timing。
13.9 Acceptance Criteria
系統必須：
✓ 保存所有研究紀錄。
✓ 保存所有推薦紀錄。
✓ 保存所有風險分析。
✓ 保存所有版本。
✓ 可查詢歷史。
Chapter 13 完


Chapter 14｜Research Dashboard（研究儀表板）
14.1 Product Objective
Dashboard 為使用者每天進入系統後的主要介面。
目標不是提供大量數據，而是協助使用者在最短時間內掌握市場概況、研究重點與風險提醒。
Dashboard 應採資訊分層設計，重要資訊優先顯示。
14.2 Dashboard Layout
首頁分為九大區塊：
────────────────────────────────────

AI Taiwan Equity Research Platform

────────────────────────────────────

① 今日市場摘要

② AI Executive Summary

③ Research Candidates（最多 3 檔）

④ Watch List

⑤ 市場風險提醒

⑥ 今日重大事件

⑦ 強勢／弱勢產業

⑧ 策略績效

⑨ Decision Journal

────────────────────────────────────
14.3 今日市場摘要（Market Overview）
每日顯示：
指數
台灣加權指數
OTC 指數
市場成交
成交金額
上漲家數
下跌家數
平盤家數
市場情緒
AI 判定：
Bullish
Neutral
Bearish
並提供一句摘要。
例如：
今日市場由電子權值股帶動，加權指數收高，但成交量未明顯放大，市場情緒偏多但追價意願仍需觀察。
14.4 AI Executive Summary
Dashboard 最上方需提供：
AI 今日研究摘要。
例如：
今日共有 1,856 檔股票完成分析，其中 142 檔通過基本面篩選，21 檔進入深入研究階段，最終 2 檔符合研究候選條件。本日市場整體偏多，但因兩日後有重要經濟數據公布，建議控制追價風險。
14.5 Research Candidates
每日最多顯示：
三家公司。
每家公司包含：
股票代號
公司名稱
Company Quality
Timing
Market Behavior
Intelligence
Risk
Confidence
Recommendation Level
點擊後
可展開：
完整研究報告。
14.6 Watch List
顯示：
目前值得持續追蹤。
但：
尚未進入：
Research Candidate。
例如：
等待：
突破。
財報。
法說會。
月營收。
14.7 Risk Center（風險中心）
集中顯示：
今日：
所有：
重要風險。
例如：
Fed 利率決議
美國 CPI
台積電法說
財報週
地緣政治
AI：
說明：
是否：
影響：
目前研究。
14.8 Industry Heatmap（產業熱度）
每日分析：
熱門：
產業。
例如：
AI
★★★★★
半導體
★★★★☆
PCB
★★★☆☆
生技
★★☆☆☆
航運
★☆☆☆☆
AI：
說明：
為何：
強。
為何：
弱。
14.9 Strategy Performance
Dashboard 顯示：
最近：
5 日。
20 日。
60 日。
一年。
策略績效。
例如：
勝率：
67%
平均報酬：
11.4%
最大回撤：
5.8%
是否：
跑贏：
加權指數。
14.10 Decision Journal
顯示：
最近：
AI
推薦。
包含：
日期。
股票。
推薦理由。
最後績效。
可點擊：
查看：
完整分析。
14.11 Search
支援：
搜尋：
任何股票。
例如：
輸入：
2330。
立即顯示：
所有：
歷史研究。
目前：
AI 評估。
事件。
財報。
研究紀錄。
14.12 Why Not Report
Dashboard
提供：
按鈕：
為何今天沒有推薦？
AI：
回答：
例如：
股票：
XXXX
原因：
EPS 長期下降
外資持續賣超
接近財報
ROE 低於產業平均
因此：
未進入：
Research Candidate。
14.13 Acceptance Criteria
Dashboard 必須：
✅ 五秒內掌握市場。
✅ 三十秒內完成閱讀。
✅ 不需閱讀大量文字。
✅ AI 自動整理重點。
Chapter 14 完

Chapter 15｜Strategy Configuration（策略設定中心）
15.1 Product Objective
Strategy Configuration 提供使用者管理 AI 研究策略的能力。
所有篩選條件、評分權重及推薦規則皆應可設定，避免將商業邏輯寫死於程式中。
系統應支援建立多套策略，並可透過回測比較其歷史績效。
15.2 設定原則（Configuration Principles）
所有策略參數皆應：
可調整
可版本化
可匯出
可回測
可恢復預設值
使用者修改策略後，系統不得立即套用於正式推薦，需先完成回測。
15.3 基本面策略
使用者可調整：
公司規模
最低市值
最低資本額
最低平均成交金額
上市年數
營收
最近三年整體趨勢向上
最近五年整體趨勢向上
月營收 YoY 最低門檻
年營收成長率最低門檻
EPS
可設定：
TTM EPS 必須大於 0
最近三年整體趨勢向上
最近五年整體趨勢向上
EPS 年增率最低門檻
ROE
可設定：
最低 ROE
最近三年整體趨勢
最近五年整體趨勢
預設：
15%。
ROA
可設定：
最低：
8%。
並分析：
趨勢。
毛利率
可設定：
最低：
毛利率。
是否：
需高於：
產業平均。
財務健康
可設定：
負債比率上限
自由現金流是否必須為正
流動比率最低值
速動比率最低值
股票估值
可設定：
PER 上限
PB 上限
PEG 上限
殖利率最低值（選用）
15.4 技術面策略
使用者可設定：
均線
是否：
必須：
站上：
MA20
MA60
MA120
是否：
必須：
多頭排列。
成交量
可設定：
最低：
成交量。
是否：
必須：
價漲量增。
RSI
可設定：
最高：
70。
最低：
30。
MACD
是否：
需要：
黃金交叉。
KD
是否：
需要：
黃金交叉。
15.5 市場行為策略
可設定：
外資：
近：
幾日：
買超。
投信：
近：
幾日：
買超。
三大法人：
是否：
同步買超。
融資：
是否：
快速增加。
15.6 Intelligence Strategy
可設定：
重大新聞：
權重。
產業：
權重。
Macro：
權重。
事件：
重要性門檻。
15.7 Risk Strategy
可設定：
是否：
排除：
處置股
全額交割股
財務異常
財報公布前
法說會前
以及：
Confidence Score
最低門檻。
15.8 Recommendation Strategy
可設定：
每日：
最多：
推薦：
幾檔。
預設：
三檔。
最低：
Confidence：
70%（config.py RECOMMENDATION_RULES min_confidence=70.0）。
最低：
Company Quality：
A。
15.9 Strategy Version
系統需建立：
版本。
例如：
Growth Strategy v1.0
Balanced Strategy v2.0
Value Strategy v1.0
每個版本：
皆可：
回測。
比較。
還原。
15.10 Acceptance Criteria
系統必須：
✓ 所有策略皆可調整。
✓ 不需修改程式。
✓ 所有修改皆可回測。
✓ 所有版本皆可保存。
Chapter 15 完

Chapter 16｜System Architecture（系統架構）
16.1 Product Objective
本系統採用模組化（Modular Architecture）設計。
所有功能皆可獨立開發、測試及維護，避免高耦合設計，提升後續擴充性與可維護性。
各模組之間透過標準化介面交換資料，不直接依賴彼此的內部實作。
16.2 Overall Architecture
                    AI Taiwan Equity Research Platform

┌────────────────────────────────────────────────────────┐
│                  Presentation Layer                    │
│ Dashboard │ Daily Report │ Search │ Strategy Setting   │
└────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────┐
│                  Decision Layer                        │
│ Decision Engine │ Report Generator │ Confidence Engine │
└────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────┐
│                  Analysis Layer                        │
│ Fundamental │ Technical │ Market │ Intelligence │ Risk │
└────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────┐
│                    Data Layer                          │
│ Price │ Financial │ Chip │ News │ Events │ Database    │
└────────────────────────────────────────────────────────┘
16.3 Module List
系統由以下核心模組組成：
Data Collection Engine
負責：
每日收集：
股價
財報
法人
新聞
總體經濟
公司治理
Data Validation Engine
負責：
檢查：
缺漏值
重複資料
異常數值
更新時間
避免 AI 使用錯誤資料。
Fundamental Analysis Engine
分析：
營收
EPS
ROE
ROA
毛利率
負債
PER
PB
PEG
現金流
輸出：
Company Quality。
Technical Analysis Engine
分析：
MA
成交量
RSI
KD
MACD
K線
支撐
壓力
輸出：
Timing。
Market Behavior Engine
分析：
外資
投信
自營商
融資
融券
輸出：
Market Behavior。
Market Intelligence Engine
分析：
新聞
法說會
財報
國際事件
Macro
輸出：
Intelligence。
Risk Engine
分析：
所有：
風險。
輸出：
Risk Summary。
Decision Engine
整合：
全部分析。
輸出：
Research Candidate。
Report Generator
產生：
Markdown。
PDF。
Excel。
Dashboard。
16.4 Data Flow
Scheduler

↓

Collect Data

↓

Validate Data

↓

Hard Filter

↓

Fundamental

↓

Technical

↓

Market Behavior

↓

Market Intelligence

↓

Risk

↓

Decision Engine

↓

Daily Report

↓

Dashboard

↓

Historical Database
16.5 System Principles
所有模組必須遵循：
Single Responsibility
每個模組：
只做：
一件事情。
例如：
Fundamental Engine
不能：
分析：
MACD。
Low Coupling
模組：
彼此：
獨立。
方便：
修改。
High Cohesion
同一模組：
功能：
集中。
Extensibility
未來新增：
ETF。
美股。
港股。
Crypto。
不得：
修改：
核心架構。
16.6 AI Responsibility
Rule Engine 負責：
Hard Filter
計算指標
財務規則
技術規則
風險規則
LLM 負責：
摘要
Explainable AI
研究報告
Recommendation Reason
Why Not Report
Rule Engine 與 LLM 的職責必須明確分離。
16.7 Error Handling
任何分析失敗時：
不得：
中止整個流程。
例如：
新聞資料失敗。
仍可：
完成：
基本面。
技術面。
並於報告中標示：
新聞資料暫時不可用。
16.8 Logging
所有流程：
需保存：
開始時間。
完成時間。
分析股票數。
錯誤。
版本。
方便：
Debug。

16.8.1 ExecutionLog 去重規則（Deduplication）
每個交易日的 execution_logs 應只保留最新一筆：
同一日期若執行多次（如重跑回補、手動強制執行），後次執行覆蓋前次紀錄
實作方式：每次執行完成後，寫入前先刪除同日舊紀錄，或以最新 id 為準
Dashboard 查詢層亦應防禦性去重：使用 MAX(id) GROUP BY date，避免多筆同日紀錄導致 UI 顯示異常
執行紀錄查詢範圍：預設載入最近 90 天（90 筆），避免筆數過少時歷史日期被截斷
16.8.2 股票名稱注入規則（Stock Name Injection）
分析 pipeline 啟動時（Step 1 完成後），從本地 stocks 表載入全股票名稱對照表 _stock_name_map：

  _stock_name_map: dict = {r.stock_id: r.name for r in session.query(StockModel).all() if r.name}

後續所有模組（決策引擎傳入 name 參數、report_generator 報告標題）皆從此對照表取名，確保報告標題格式為「台積電（2330）」而非「2330（2330）」。

優先順序：_stock_name_map → TWSE API 即時欄位 → 預設使用 stock_id

16.8.3 Dashboard 推薦卡片資料來源（Recommendation Card Data Flow）
推薦卡片資料來源依以下優先順序讀取：

1. 優先：load_db_recommendations(date)
   直接從 Neon recommendations 表讀取，同時 JOIN stocks 表取得股票名稱，從 ai_conclusion 欄位取得 AI 結論。
   此方式最可靠，不受報告 markdown 格式影響。

2. 降級：parse_recs_from_report(content)
   當 DB 無推薦記錄時，解析當日 markdown 報告中 ## ③ Research Candidates 段落。

3. 補充：results_df fallback
   當 DB 與報告皆無推薦時，使用 AnalysisResults 評分最高前 8 名補充顯示。

股票名稱顯示規則（render_rec_card）：
  - 有股票名稱（name ≠ stock_id）：顯示「名稱 / 代號 · TWSE」兩行
  - 無股票名稱（name = "" 或 = stock_id）：僅顯示「代號」一行，不重複

16.9 資料庫架構（Dual-Database Architecture）
本系統採用雙資料庫設計：

本地端（Local — SQLite）
用途：
  每日重量級資料儲存（股價歷史、法人原始資料）
  技術分析運算來源
  需要大量歷史資料的模組（MA60、MA120 等）
  財務年度資料（由 MOPS 批量匯入）
儲存內容：
  DailyPrice（每日股價，建議保留最近 2 年）
  InstitutionalData（法人買賣超歷史）
  FinancialQuarter（年度財務資料，quarter=0 = 年度；由 MOPS 匯入）
  Stocks（股票基本資料）
特性：
  本地運算，無網路延遲
  資料量大，不適合雲端同步

⚙️ FinancialQuarter 資料說明（2026-07-01 起）：
  quarter=0：年度資料（MOPS 年底 Q4 合併報表計算而來）
  欄位：eps, roe, roa, gross_margin, op_margin, net_margin, debt_ratio, current_ratio
  批量匯入：python3 scripts/import_financials.py --missing --years 7
  單支更新：python3 scripts/import_financials.py --stock 2330
  ROE/ROA 計算方式：淨利 ÷ 年底股東權益/總資產（非平均值，與 goodinfo 略有差異）

雲端（Cloud — Neon PostgreSQL）
用途：
  Dashboard（手機 / 雲端版）讀取分析結果
  Streamlit Community Cloud 連接
  多裝置同步
儲存內容：
  AnalysisResults（每日分析評分）
  Recommendations（推薦記錄）
  DailyReports（每日市場報告）
  ExecutionLogs（執行紀錄）
  ResearchStatus（研究狀態）
特性：
  輕量，僅分析結果，無原始價格資料
  保留最近 90 天（可調整）

同步流程：
  本地分析完成 → sync_to_neon.py → 推送至 Neon
  同步範圍僅限上述雲端儲存內容
  每日執行一次（分析完成後）

16.10 Acceptance Criteria
系統必須：
✓ 所有模組可獨立測試。
✓ 單一模組異常不影響整體。
✓ 可新增分析模組。
✓ 可支援未來更多市場。
✓ 本地 DB 與雲端 DB 職責清晰分離，不混用。
Chapter 16 完

Chapter 17｜Deployment & Operations（部署與維運）
17.1 Product Objective
本系統應支援全自動化部署與每日定時執行，確保研究流程穩定、可靠且可追蹤。
系統應以無人值守（Unattended Operation）為設計目標，在無需人工介入的情況下，自動完成資料更新、分析、報告產出與歷史資料保存。
17.2 System Availability
系統目標：
每日交易日自動執行
非交易日不執行完整分析流程（僅更新必要資料）
支援手動重新執行指定日期的分析
所有執行結果均需保存紀錄

17.2.1 歷史日期回補模式（Backfill Mode）
當以 --date 參數指定過去日期（trade_date < 今日）時，系統進入回補模式：

資料來源切換（不呼叫 LIVE API）：
股價資料：從本地 SQLite daily_prices 表讀取指定日期的歷史股價
法人資料：從本地 SQLite institutional_data 表讀取指定日期的歷史法人資料
市場摘要（index close 等）：設為 None（歷史 API 不提供即時盤後整體指數）

不重寫原始資料：
回補模式不覆寫 daily_prices 與 institutional_data（原始歷史資料已存在，無需重寫）
僅更新 analysis_results、daily_reports、execution_logs

邏輯判斷：
is_backfill = (trade_date < date.today())
為 True → 從 DB 讀取歷史資料
為 False → 呼叫 TWSE API 取得當日最新資料

錯誤處理：
若 DB 中無該日期的股價資料 → 記錄錯誤並中止，不產生空白分析結果

17.3 Scheduler
每日交易日流程：
時間	工作內容
15:35	確認收盤資料完整
15:40	更新股價資料
15:45	更新法人資料
15:50	更新新聞與重大事件
15:55	執行 AI 分析
16:00	產生研究報告
16:05	更新 Dashboard／Research Workspace
16:10	啟動回測與歷史資料更新（可背景執行）
若資料來源延遲，系統應等待至設定時限，逾時則標示資料不完整並記錄原因。
17.4 Error Recovery
系統需具備以下能力：
自動重試
當資料來源短暫失敗時：
自動重試（可設定次數）
若仍失敗，保留錯誤紀錄
部分失敗
若新聞模組失敗：
基本面分析仍可執行
技術面分析仍可執行
報告需標示新聞分析未完成
不得因單一模組異常而中止全部流程。
17.5 Monitoring
系統需監控：
每日執行成功率
執行時間
資料更新時間
錯誤率
資料完整率
管理者應可查看歷史執行紀錄。
17.6 Data Retention
系統應保存：
每日分析結果
每日研究報告
AI 推薦紀錄
Decision Journal
回測結果
策略版本
建議長期保存，以支援歷史分析與策略驗證。
17.7 Security
系統應符合以下原則：
不儲存使用者券商帳號或密碼
不提供自動交易功能
不修改任何外部資料來源
僅使用合法公開資料
保留完整操作紀錄
17.8 Scalability
系統應支援未來擴充：
ETF
美股
港股
日本股市
歐洲股市
更多資料來源
不需重構核心架構。
17.9 Acceptance Criteria
系統必須：
✅ 每日自動執行分析流程
✅ 保留完整 Log
✅ 支援重新分析歷史日期
✅ 單一模組失敗不影響其他模組
Chapter 17 完

Chapter 18｜Acceptance Criteria（產品驗收標準）
18.1 Product Vision Validation
完成後，本產品應符合以下定位：
AI Taiwan Equity Research Platform
而非：
股票推薦群組
飆股預測工具
自動交易系統
產品核心價值為：
提供高品質、可解釋、可驗證的股票研究。
18.2 Functional Acceptance
系統必須完成：
資料蒐集
每日更新市場資料
每日更新法人資料
每日更新新聞
每季更新財報
基本面分析
支援：
營收分析
EPS
ROE
ROA
毛利率
財務健康
估值分析
技術分析
支援：
均線
成交量
RSI
KD
MACD
K 線
支撐
壓力
市場分析
支援：
外資
投信
自營商
新聞
總體經濟
事件分析
Decision Engine
可：
產生 Company Quality
產生 Timing
產生 Risk
產生 Research Candidate
報告
每日自動產生：
Executive Summary
Daily Research Report
Why Not Report
Decision Journal
18.3 Performance Acceptance
系統應符合：
完成全市場分析
報告可於每日分析完成後產生
查詢股票分析應快速回應
Dashboard 開啟流暢
18.4 Explainable AI
每一次研究結果皆需包含：
推薦理由
未推薦理由
主要風險
關鍵數據
後續觀察事項
不得僅輸出分數。
18.5 Quality Standard
AI 每日最多產出：
3 檔 Research Candidate。
若當日無符合條件標的，應明確說明原因。
不得為了維持固定數量而降低標準。
18.6 Future Roadmap（後續版本）
Version 6.1（近期優化）
台股假日日曆整合（精確識別休市日）
Confidence Score 精細化計算（已定義於 9.5）
推薦後即時績效追蹤（已定義於 10.7.1）
Hard Filter 降級模式（財務不可用時改用趨勢替代）
MA 最低資料天數驗證
✅ 已完成：歷史日期回補模式（Backfill Mode）— 已實作於 main.py（詳見 17.2.1）
✅ 已完成：ExecutionLog 去重機制 — Dashboard 防禦性去重查詢 + DB 清理（詳見 16.8.1）
✅ 已完成：動態評分權重（Dynamic Weighting）— 無財務資料時 40% 品質權重等比重分（詳見 4.4.1）
✅ 已完成：品質分快取（Quality Score Cache）— 跨日借用最近有效評分（詳見 4.4.2）
✅ 已完成：AI Prompt 設計原則 — 禁止捏造、has_quality 旗標、財務缺失揭露（詳見 9.7.1）
✅ 已完成：analysis_results Upsert — 重跑分析時正確更新現有記錄（非跳過）
✅ 已完成：recommendations Upsert — --force 重跑時更新 ai_conclusion 等所有欄位（非跳過）
✅ 已完成：Dashboard 股票名稱 — load_stock_names 優先讀本地 DB stocks 表
✅ 已完成：報告股票名稱注入 — _stock_name_map 從 stocks 表建立，報告標題格式正確（詳見 16.8.2）
✅ 已完成：Dashboard 推薦卡片 DB 優先 — load_db_recommendations() 直接讀 recommendations 表，確保名稱與 AI 結論正確（詳見 16.8.3）
✅ 已完成：推薦卡片名稱不重複 — render_rec_card 無名稱時只顯示代號一次（詳見 16.8.3）
✅ 已完成：持倉管理系統 v1 — 含蒙地卡羅模擬、AI 動態停損/目標價、自動出場訊號（詳見 Chapter 19）
✅ 已完成：MOPS 財務資料收集器 — src/collectors/mops_collector.py，使用 t164sb04+t164sb03 官方 API，計算 EPS/ROE/ROA/毛利率/負債比/流動比率（詳見 3.2 三）
✅ 已完成：financial_collector DB fallback — build_financial_summary() 優先讀取本地 DB，無資料再嘗試 FinMind（詳見 3.2 三）
✅ 已完成：財務批量匯入腳本 — scripts/import_financials.py，支援 --missing/--years/--stock，MOPS 官方 API 無 IP 封鎖（詳見 3.2 三）
✅ 已完成：main.py 財務呼叫修復 — build_financial_summary() 移除 if FINMIND_TOKEN 條件，改為無條件呼叫，確保 DB fallback 生效，修復 253 支股票品質分=0 的根本原因
✅ 已完成：歷史分析批次回補腳本 — scripts/backfill_history.py，自動跳過股價資料不足（<200 支）的日期，支援 --limit N 參數，已回補 486 天歷史分析結果
✅ 已完成：持倉歷史回填腳本 — scripts/backfill_positions.py，從 recommendations 表重建所有歷史持倉，逐日掃描 daily_prices 判斷觸及目標/停損，計算整體績效報告
✅ 已完成：持倉 Dashboard key 重複修復 — 同一股票多筆持倉時 expander/button key 改為 pos_{id}/close_{sid}_{id}，修復 StreamlitDuplicateElementKey 錯誤
✅ 已完成：position_monitor 同步至 Neon — 本地 144 筆持倉全量推送，Dashboard 持倉頁即時可見
✅ 已完成：Sidebar 有效最早日期修正 — 由 DB min(date) 改為 COUNT(stock_id)≥200 的最早日期，避免顯示 2017-01-03（只有 10 支股票的無效日期）；並清除 263 筆 2017/2018 稀疏資料
✅ 已完成：歷史 Dashboard 統計全為 0 修正 — load_exec_logs(limit=90) 只取最近 90 筆，超出範圍的歷史日期（如 2024-07-01）統計顯示 0；改為查無資料時直接查 DB 取得該日 ExecutionLog
✅ 已完成：雲端 Dashboard 歷史資料同步 — 本地 SQLite 的 execution_logs（+694）、daily_reports（+462）、analysis_results（+8655）、recommendations（+106）全量同步至 Neon，雲端版可查閱所有歷史報告
✅ 已完成：Sidebar 研究起始日期修正 — 改顯示「研究起始：第一筆推薦日期（2025-10-27）」，因 2024 年資料雖存在但 max_score=59.5 未達門檻（65 分），全年無推薦，從 2025-10-27 起才有實質研究紀錄
✅ 已完成：日期選擇器下限設為 2025-01-01 — date_input min_value=2025-01-01，使用者無法再選擇 2024 日期；設定頁「最早股價日期」改為查詢 2025 年起的最早日期
✅ 已完成：date_input value < min_value 崩潰修復 — session 快取殘留 2024 日期時 value < min_value=2025-01-01 觸發 StreamlitAPIException；加入 max(selected_date, min_date) 夾值後傳入
✅ 已完成：手機版資料庫狀態優化 — 股價/法人資料僅存本機 SQLite，Neon 版顯示 0 造成混淆；改為 price_cnt>0 時才顯示股價/法人格，否則只顯示推薦紀錄並加說明文字「股價／法人原始資料存於本機，行動版不顯示」

19.24 Neon 自動同步穩定化（2026-07-02）
  問題：main.py Step 11 Neon 自動同步仍不穩定
  根因：sync_to_neon.py 同步 1 天資料實測需 ~290 秒，--days 3 必定超時；
        timeout=300s 緩衝不足（幾乎剛好等於實際耗時）

  修法（main.py Step 11）：
    - --days 3 → --days 1（每日執行只需同步當天，不需重複同步歷史）
    - timeout=300 → timeout=600（290s 實測 + 310s 緩衝）

  驗證：sync_to_neon.py --days 1 實測結果
    analysis_results: 更新 642 筆
    recommendations:  更新 4 筆
    daily_reports:    更新 2 筆
    execution_logs:   更新 42 筆
    research_status:  同步 566 筆
    總計：690 筆，耗時 ~290 秒，同步成功

19.23 2026-07-02 每日分析執行紀錄
  執行時間：70.4 秒（含 AI 報告生成）
  分析股票：6306 檔 → 196 通過硬性篩選 → 0 推薦
  大盤方向：0050=107.80 vs MA60=97.57 → 多頭（正常模式）
  今日無推薦：196 支通過篩選但均未達評分門檻（65 分）
  持倉管理：台積電 2330 浮盈 8.4%，追蹤停損自動上移至保本價 2310
  加權指數：47,018.99（+1.94%），成交 1,367.8 億（修正欄位名後首次正確抓取）
  Neon 同步：Step 11 subprocess timeout=120s 不足，改為 300s

19.22 main.py Neon 自動同步 NameError 修正（2026-07-02）
  問題：main.py 執行完畢後 Step 11 Neon 自動同步崩潰
        NameError: name 'os' is not defined
  根因：Step 11 使用 os.environ.get("NEON_URL") 但 main.py 頂部未 import os
  修法：main.py 第 27 行加入 import os
  附注：7/2 分析本身成功完成（32.7 秒，196 通過篩選，0 推薦）
        台積電 2330 浮盈 8.4%，追蹤停損自動上移至保本價 2310
        Anthropic API 餘額不足，AI 文字報告暫停生成（需充值）

19.21 加權指數顯示 N/A 修正（2026-07-02）
  問題：所有分析報告的「加權指數」欄位顯示 N/A，無法顯示大盤數值
  根因：TWSE FMTQIK API 欄位格式已更新，fetch_market_summary() 仍使用舊欄位名：
        - 舊（不存在）："Index"、"Closing"、"TradingValue"
        - 新（實際）：  "TAIEX"、"Change"、"TradeValue"
        因此迴圈找不到任何匹配行，函式回傳 {}，報告寫入 N/A

  修法（src/collectors/price_collector.py）：
    - 改用正確欄位名：index_close = row["TAIEX"]、change = row["Change"]
    - 漲跌幅百分比 = change / (taiex - change) × 100
    - 成交金額：TradeValue / 1e9（億元）
    - 驗證：修正後成功抓到 47,018.99 點，漲跌 +1.94%，成交 1,367.8 億

  注意：歷史報告（含 7/2）已存入 N/A，需重新執行 main.py 才能補正當天數值

19.20 蒙地卡羅圖表 KeyError 修正（2026-07-02）
  問題：dashboard 開啟持倉頁時崩潰，KeyError: 'target_price'
  根因：_monte_carlo_chart() 直接從 mc_result JSON 讀取 target_price / stop_loss_price /
        entry_price，但回填計算儲存的 mc_result 只含模擬統計數字，未存這三個價格欄位
  修法（dashboard/app.py line 888）：
    改為 mc.get("target_price") or pos.get("target_price")，優先讀 mc，
    無資料時 fallback 到 pos dict 本身的欄位（pos 來自 position_monitor 資料表，必有此欄）

19.19 蒙地卡羅回填計算（2026-07-02）
  問題：持倉頁面顯示「蒙地卡羅資料尚未計算，待下次每日更新後顯示」
  根因：backfill_positions.py 只建立持倉記錄，未執行 MC 模擬；mc_result 欄位為空

  修法：
    - 對全部 9 筆 active 持倉，取各股最近 252 筆日收盤計算歷史日報酬率
    - 呼叫 src/engines/monte_carlo.simulate()（sim_days=20, n_paths=1000）
    - 結果寫回 SQLite PositionMonitor.mc_result（JSON）並同步至 Neon

  9 筆 active 持倉 MC 結果：
    聯發科 2454：期望報酬 +11.9%，目標達成機率 63.9%
    漢唐   2404：期望報酬  +8.0%，目標達成機率 57.1%
    台積電 2330：期望報酬  +7.7%，目標達成機率 49.2%
    元大台灣50 0050：期望報酬 +7.4%，目標達成機率 43.6%
    台新新光金 2887：期望報酬 +6.9%，目標達成機率 50.0%
    中信金 2891：期望報酬  +4.6%，目標達成機率 32.7%
    元大高股息 0056：期望報酬 +4.0%，目標達成機率 20.9%
    臺企銀 2834：期望報酬  +1.6%，目標達成機率  8.4%
    星宇航空 2646：期望報酬 -1.1%，目標達成機率  1.4%

19.18 資金控管：100% 預算上限強制執行（2026-07-02，v6.3）
  問題：系統每次有推薦就開倉，累積 23 支 × 10% = 230%，超出 100% 總資金限制
  根因：open_position() 與 backfill_positions.py 皆未檢查剩餘資金是否充足

  修法：
    [1] position_manager.py（open_position）
        - 開倉前查詢所有 active 持倉的 position_pct 加總
        - 若 total_used + new_pct > 100%，記錄 log 並拒絕開倉（return False）

    [2] backfill_positions.py
        - 新增 budget_used dict 追蹤模擬資金（按推薦日期順序處理）
        - 同一股票已有持倉，或 total_used + new_pct > 100% 時跳過
        - 本次重跑：144 筆推薦 → 120 筆實際建倉，24 筆因資金不足跳過

    [3] dashboard/app.py
        - 移除「每筆建議倉位」
        - 改顯示「剩餘現金 = 100% - Σ(active position_pct)」
        - delta 顯示「已配置 X%」

  績效對比（重跑後）：
    持倉數：144 → 120（-24 筆資金不足跳過）
    勝率：60.3% → 64.0%
    平均損益：+3.79% → +4.46%
    平均虧損：-4.90% → -4.48%
    盈虧比：1.94 → 2.12
    剩餘現金：正確顯示 10%（9 支 active × 10% = 已配置 90%）

19.17 持倉總覽「已配置資金」顯示邏輯修正（2026-07-02，v6.2.2）
  問題：「已配置資金 230%，已滿倉（超過 100%）」顯示怪異
  根因：持倉是分批在不同日期建立，並非同時持有 23 支各 10%；
        直接累加 position_pct 毫無意義，230% 只是歷史推薦倉位的加總

  修法（dashboard/app.py）：
    - 移除「已配置資金 %」metric
    - 改顯示「每筆建議倉位」= total_alloc / n_pos（各推薦平均建議倉位）
    - help 說明：A+=30%、A=20%、B=10%，讓使用者了解評分與倉位的對應關係

19.16 Dashboard 持倉總覽指標修正（2026-07-02，v6.2.1）
  問題：配置總覽顯示「已配置資金 230%、現金 0%、整體預期報酬 +0.00%、損益偏高」
  根因：
    - 已配置 230%：23 支 × 10% = 230%，未正規化到 100% 基礎
    - 預期報酬 0.00%：回填持倉無蒙地卡羅結果（mc_result 為空），fallback 值硬寫 0
    - 損益偏高：Σ(position_pct/100 × pnl) 分母預設 100%，但實際配置 230%，數字被放大

  修法（dashboard/app.py）：
    - 正規化權重：weight_i = position_pct_i / total_alloc（以實際總配置為分母）
    - weighted_cur = Σ(weight_i × pnl_i)：真正的加權平均損益
    - weighted_exp fallback：mc_result 無資料時改用 (target_price - entry_price) / entry_price
    - 已配置資金顯示實際 total_alloc%；現金 > 0 才顯示「現金 X%」，否則顯示「已滿倉」

  附加：backfill_positions.py 同步加入追蹤停損 + 30 日強制出場的歷史模擬邏輯，
        使歷史回填結果與線上持倉管理邏輯保持一致

19.15 報酬率提升改版（2026-07-02，v6.2）
  目標：從整體加權報酬 1.46% 提升至更高水準
  分析根因：49 筆「訊號出場」僅 +0.83%，佔已平倉 34%，嚴重拉低均值

  [1] 追蹤停損（position_manager.py）
    - 浮盈 >= 8%：停損上移至進場成本（保本，不讓獲利歸零）
    - 浮盈 >= 12%：停損上移至 +6%（鎖定部分獲利）
    - 動態更新 stop_loss_price 存入 DB，下次掃描即生效
    - 預期：達標均報酬從 +16.93% 提升至 +20%+

  [2] 30 交易日強制出場（position_manager.py）
    - 持倉 >= 45 日曆天（≈30 交易日）且 abs(pnl) < 8%：強制以收盤價出場
    - 出場原因：TIME_LIMIT，狀態歸入 closed_signal
    - 解放停滯資本，讓 49 筆 +0.83% 的部位釋放再投入

  [3] 空頭市場過濾器（main.py + decision.py）→ v6.4 升級為三段式
    - 以 0050 ETF 收盤價 vs 60 日均線偏離度（%）判斷市場方向
    - 多頭（deviation > +3%）：正常推薦，最多 3 支，門檻 65 分
    - 謹慎（-3% ~ +3%）：最多 2 支，門檻提升至 68 分
    - 空頭（deviation < -3%）：僅 A+/A 等級，最多 1 支，門檻提升至 72 分
    - 原二元設計（空頭門檻 70 分）已取代為三段漸進設計

  [4] 績優股評分強化（fundamental.py）
    - 連續 3 年 EPS 正成長：+8 分加成
    - 連續 5 年 EPS 正成長：+15 分加成（績優核心特徵）
    - EPS 分項權重上限從 20 分提升至 35 分
    - 預期：推薦股票更偏向真正的長期成長型績優股

19.14 模型完整性修復（2026-07-02，v6.1 重大改版）
  針對七項模型漏洞進行修復：

  [1] Look-ahead Bias（main.py）
    - 問題：回補歷史日期時，DailyPrice/AnalysisResult 查詢使用全部未來資料
    - 修復：加入 date <= trade_date 過濾條件，確保技術指標只用當日及之前的價格

  [2] 籌碼分無效中性值（market_behavior.py + decision.py）
    - 問題：無法人資料時 behavior_score 給 50（中性），納入加權計算造成失真
    - 修復：新增 has_real_chip_data 旗標；無真實籌碼時 behavior 20% 權重重分配給 timing/intelligence

  [3] 財務資料時間點前視（goodinfo_collector.py + financial_collector.py + main.py）
    - 問題：歷史回補使用「現在已知的」財務年報，2025-01-15 分析已含 2024 年報（實際要 2025-04-01 後才公告）
    - 修復：加入 as_of_date 參數；只使用年報申報期限（年度 Y → Y+1/4/1）已過的年度

  [4] 組合產業集中度（decision.py）
    - 問題：無上限，可能全部推薦都是半導體
    - 修復：select_top_n 加入同產業最多 2 支限制

  [5] Neon 自動同步（main.py）
    - 問題：需手動執行 sync_to_neon.py，容易忘記造成手機版資料落後
    - 修復：run_pipeline 完成後自動執行 Step 11（sync_to_neon.py --days 3）
    - NEON_URL 從環境變數或 .env 讀取

  [6] Hard Filter 產業別閾值（hard_filter.py + main.py）
    - 問題：ROE≥15%/ROA≥8% 對金融業不適用（結構性高負債、低 ROA）
    - 修復：辨識銀行/保險/證券/金控等關鍵字，採放寬標準：ROE≥8%、ROA≥0.5%、負債比≤95%
    - 同時傳入 industry 欄位讓 Hard Filter 知道產業類別

  [7] Dashboard 候選 UI 誤導（dashboard/app.py）
    - 問題：無推薦時 fallback 到 results_df.head(8)，標題仍顯示「今日研究候選」
    - 修復：fallback 時改顯示「分析宇宙（N 檔，未達推薦門檻）」並加警告文字

19.13 2024 年無推薦說明（預期行為）
  - 股價資料範圍：2024-07-01 起，但 2024 全年 0 筆推薦
  - 根本原因：2024 資料量不足，歷史 K 棒少 → 技術分偏低 → total_score 最高僅 59.5（台積電 2024-07-23）
  - 推薦門檻：total_score ≥ 65 + confidence ≥ 70%
  - 2024 資料仍保留在 DB 供歷史回顧，不影響報酬率計算
  - 有效報酬率計算起始：2025-10-27（第一筆推薦，台股 AI 研究正式啟動）

19.12 Neon 同步架構（2026-07-02 確認）
  本地 SQLite（原始資料）→ Neon PostgreSQL（雲端 Dashboard 讀取來源）
  同步脫節歷史：
    - scripts/sync_to_neon.py 預設只同步 90 天
    - 雲端 Dashboard 讀不到 2024-07-01 等歷史日期 → 顯示「尚無報告」與統計全 0
  根本原因：
    - ExecutionLog 本地 782 筆 / Neon 只有 26 筆
    - DailyReport 本地 485 筆 / Neon 只有 23 筆
    - AnalysisResult 本地 15,438 筆 / Neon 只有 6,783 筆
  修復方式：
    1. dashboard/app.py：load_exec_logs 超出 90 筆快取範圍時改為直查 DB
    2. 執行全量推送 python3 -c "..." 將本地所有日期（非 Neon 已有者）批次插入
    3. 標準補同步指令：python3 scripts/sync_to_neon.py --db-url "..." --days 999

19.11 歷史持倉績效實測（最終版，含資金限制 + 追蹤停損 + 時間強制出場）
  資料範圍：2025-10-27 ~ 2026-07-02（137 個交易日）
  建倉規則：100% 總倉位上限、同股不重複、依推薦日期順序處理
  出場規則：目標價達標、固定停損、追蹤停損（8% 保本／12% 鎖 +6%）、時間強制出場（45 日無方向 abs(pnl)<8%）
  目標/停損設定：B 級目標 +10%、停損 -7%；A 級目標 +15%、停損 -8%
  ┌─────────────────────────────────────────┐
  │  總建倉：120 筆（144 筆推薦中 24 筆資金不足跳過）
  │  勝率：64.0%（71 勝 / 40 負）          │
  │  平均損益：+4.46%                       │
  │  平均獲利：+9.50%                       │
  │  平均虧損：-4.48%                       │
  │  盈虧比：2.12                           │
  │  持倉中：9 筆                           │
  └─────────────────────────────────────────┘
  同步方式：python3 scripts/backfill_positions.py 後用 psycopg2 推送至 Neon

16.9.1 財務資料導入後的 Hard Filter 行為說明（2026-07-02 實測確認）
  財務資料填入後，Hard Filter 嚴格度顯著提高：
  - 有財務資料的股票 → 走嚴格路徑（ROE ≥ 15%、ROA ≥ 8%、EPS > 0、負債比 ≤ 60%）
  - 無財務資料的股票（ETF、特殊架構）→ 走流動性降級路徑（日均成交金額 ≥ 1 億）
  - ROE/ROA 不達標的股票（如 ROE < 15%）正確被 Hard Filter 淘汰，不進入深度分析
  → 這是預期行為，說明財務篩選機制正常運作

  2026-07-02 乾淨重跑實測結果：
  - 分析股票：187 支（較修復前 428 支大幅收斂，嚴格篩選後）
  - 品質分 > 0：16 支，前排：川湖（77）、台積電（73）、聯陽/聯詠/億豐（75）
  - 品質分 = 0：171 支（ETF 及流動性篩選通過者）
  - 今日無推薦：技術時機分偏低（非交易日，法人資料尚未更新）
  - 結論：財務品質篩選機制運作正常，推薦標準嚴格

  重跑分析前清除舊紀錄的標準做法：
    python3 -c "from src.database import init_db, get_session, AnalysisResult; s=get_session(init_db()); s.query(AnalysisResult).filter(AnalysisResult.date=='YYYY-MM-DD').delete(); s.commit()"
    python3 main.py

Chapter 19｜Position Management（持倉管理系統）

19.1 設計原則
本系統為研究輔助工具（非自動交易系統），持倉管理模組旨在：
  - 追蹤每次推薦後的假設性持倉表現
  - 提供量化的出場訊號（而非主觀判斷）
  - 透過蒙地卡羅模擬評估風險/報酬分布
  - 紀錄完整研究生命週期（建倉→持有→出場）

19.2 持倉比例分配（依評分加權 + 信心動態調整）
  基礎倉位（依等級）：
    A+ 級：30%｜A 級：20%｜B 級：10%｜C 級：5%
  動態信心調整（v6.4）：
    - 以 80% 信心度為基準，每 10% 差距加減 5%
    - 信心 70% → 基礎 -5%；信心 90% → 基礎 +5%
    - 單支持倉上限 35%，調整範圍 ±10%
    - 範例：A 級（20%）× 信心 90% → 25%；× 信心 70% → 15%
  總倉位上限：100%（已實作，2026-07-02 v6.3）
    - open_position() 開倉前查詢 active 持倉加總，超過 100% 拒絕開倉
    - backfill_positions.py 歷史回填同步模擬此限制
  ⚠️ 最多同時持有 5 支：尚未實作，目前僅限制 100% 總倉位上限，待補齊支數硬上限。
  倉位僅為研究建議，不代表實際下單比例

19.3 AI 動態停損 / 目標價設定
  - 每次推薦時，Claude 根據評分等級 + 歷史波動度動態決定目標價與停損價
  - 輸出格式：TARGET_PCT、STOP_LOSS_PCT、RATIONALE
  - 備案（無 API 時）：依等級使用規則式預設值
    A+：目標 +20~30%，停損 -8%
    A ：目標 +12~20%，停損 -8%
    B ：目標 +8~15%，停損 -7%
  - 實作：src/ai/claude_analyst.py → generate_price_targets()

19.4 出場訊號（自動偵測）
每日執行 check_exit_signals()，偵測以下條件（全部觸發自動關倉）：
  TARGET_HIT        ：現價 ≥ 目標價
  STOP_LOSS         ：現價 ≤ 停損價（原始固定停損）
  TRAILING_STOP     ：現價 ≤ 動態追蹤停損價（浮盈 8% 後上移至保本；浮盈 12% 後鎖 +6%）
  WEAK_TECHNICAL    ：技術時機分 < 45 AND 市場行為分 < 40（雙弱）
  INSTITUTIONAL_EXIT：市場行為分 < 40（法人持續大幅賣超）
  TIME_LIMIT        ：持倉 ≥ 45 日曆天且 pnl < 0（虧損無復甦）強制出場；浮盈 0~8% 延長至 90 天
  MANUAL            ：使用者在 Dashboard 手動關倉

追蹤停損邏輯（position_manager.py，2026-07-02 v6.2 實作）：
  TRAILING_BREAKEVEN_PCT = 8.0   # 浮盈 >= 8%：停損移至進場價（保本）
  TRAILING_LOCK_PCT      = 12.0  # 浮盈 >= 12%：停損移至 +6%（鎖利）
  TRAILING_LOCK_FLOOR    = 6.0   # 鎖利後停損保留的最低獲利 %
  TIME_LIMIT_DAYS        = 45    # ≈ 30 個交易日；虧損才強制出場，小浮盈給 90 天（v6.4 修正）

19.5 蒙地卡羅模擬
  - 引擎：src/engines/monte_carlo.py
  - 參數：1000 條路徑 × 20 個交易日
  - 輸入：近 60 日歷史收盤價計算之日報酬率分布（μ, σ）
  - 抽樣分佈：Student's t（df=4），捕捉台股厚尾報酬特性（v6.4 升級）
      - 比正態分佈多 ~3× 的極端事件機率，stop_loss 機率估計更保守
      - 單日報酬限制 ±20%（clip）；scipy 不可用時 fallback 至常態分佈
  - 輸出：
      - 達目標價機率（%）
      - 觸及停損機率（%）
      - 期望報酬（%）
      - 價格路徑分布圖（含 P5、P25、P75、P95 區間）
  - 路徑採樣：50 條用於 Plotly 圖表渲染（monte_carlo.py 預設 sample_n=50）

19.6 資料庫設計
表名：position_monitor
  id, stock_id, stock_name, date_entered, entry_price
  target_price, stop_loss_price, target_pct, stop_loss_pct
  position_pct（建議倉位%）
  ai_price_rationale（Claude 說明）
  rec_level, rec_score, confidence
  status（active / closed_profit / closed_loss / closed_manual / closed_signal）
  exit_date, exit_price, exit_reason, pnl_pct
  mc_result（TEXT / JSON，預算蒙地卡羅結果，供雲端 Dashboard 直接讀取）
  created_at, updated_at

19.7 Dashboard 整合
  Tab：📈持倉（第四個 tab，排在歷史之後）
  持倉中 Tab 頂部（配置總覽，手機 2×2 排列）：
    - 持倉支數
    - 剩餘現金% = 100% - Σ(active position_pct)；delta 顯示「已配置 X%」
    - 整體預期報酬%（MC expected_pnl 加權平均；無 MC 時 fallback 用目標價距離估算）
    - 整體目前損益%（pnl_pct 按 position_pct/total_alloc 正規化加權平均）
  持倉中 Tab 各股展開：
    - 進場/目標/停損/倉位 metrics
    - 現價即時損益
    - AI 停損依據說明
    - 蒙地卡羅模擬圖（從 mc_result JSON 繪製，不需 DailyPrice）
    - 手動關倉按鈕
  歷史紀錄 Tab：
    - 依狀態顯示所有已關閉持倉（達標/停損/訊號/手動）
    - 顯示入場/出場日期、損益%、關倉原因

19.8 資料讀取策略
  - load_positions() 使用 psycopg2 直連 Neon（不透過 get_session()）
  - 原因：Streamlit Cloud 上 get_session() 可能 fallback 到本機 SQLite（無回填資料）
  - mc_result 預算於本機、存入 Neon，雲端免讀 daily_prices 即可繪圖

19.9 歷史持倉回填（Backfill）
  - 從 recommendations 表取每支股票最早推薦日為建倉日
  - 規則式停損/目標（B 級：目標 +10%、停損 -7%；A 級：目標 +15%、停損 -8%）
  - 逐日掃描 daily_prices high/low，模擬追蹤停損 + 30 日強制出場邏輯（與線上一致）
  - 資金控管：按推薦日期順序處理，total_used + new_pct > 100% 時跳過
  - active 持倉用最新收盤計算浮動損益
  - 最新回填結果（2026-07-02，v6.4 含動態倉位 + 修正 TIME_LIMIT）：
      144 筆推薦 → 118 筆建倉（26 筆因資金不足跳過）
      已平倉 109 筆 / 持倉中 9 筆
      勝率 62.4%（68 勝 / 41 負）
      平均損益 +4.59%，平均獲利 +10.00%，平均虧損 -4.37%，盈虧比 2.29
      Sharpe Ratio：0.62（每筆交易，rf≈1.5%/年）
      最大累積回撤：28.00%
      同期 0050 報酬：+68.97%（2024-07-01 ~ 2026-07-02，兩年累計）
  - 蒙地卡羅：回填完成後批次計算全部 118 筆，同步至 Neon（Dashboard 即時可見）

19.10 手機版適配
  Tab CSS：6 個 tab 時字體縮至 0.62rem，letter-spacing -0.02em
  配置總覽：st.columns(2) × 2 排（2×2），避免 4 欄在手機過擠
  metric 字體：數值 1.1rem、標籤 0.7rem

Chapter 19 完

當前版本：v6.8.13（2026-07-07）
✅ 財務資料串接完成（EPS / ROE / ROA 多年歷史，MOPS + goodinfo 雙源）
✅ 硬性篩選完整運作（ROE ≥ 15%、ROA ≥ 8%；金融業放寬版；市值/資本額每日更新）
✅ 三段式市場方向過濾（多頭/謹慎/空頭，依 0050 偏離 MA60 漸進調整）
✅ 持倉管理系統（追蹤停損、動態倉位大小依信心調整、時間強制出場修正、100% 資金上限）
✅ 蒙地卡羅模擬（1000 路徑 × 20 日，Student's t 厚尾分佈，存 DB 供雲端 Dashboard 顯示）
✅ 歷史持倉回填（v6.4 重跑：118 筆，勝率 62.4%，均損益 +4.59%，盈虧比 2.29，Sharpe 0.62）
  - 回填報告含：Sharpe Ratio、最大累積回撤（28%）、0050 同期報酬 Benchmark
  - 蒙地卡羅批次計算全部 118 筆（Student's t），同步至 Neon
✅ Neon 雲端同步（每日自動執行，timeout=600s）
✅ 連續 EPS 成長加分（5 年 +15 分、3 年 +8 分）
✅ 法人資料 T-1 fallback（當日 API 未更新時使用最近 DB 資料，behavior_score 恢復真實）
✅ 估值即時計算 P/E（close / eps_ttm，DB 無 per 時自動補算）
✅ 智慧情報無資料時動態重分配 10% 權重
✅ 財報季節風險自動偵測（距截止日 ≤14 天自動觸發風險扣分）
✅ Look-ahead bias 修正（goodinfo_collector 年報日期過濾 bug 修正；季報按 Q1~Q4 公告截止日過濾）
✅ 安全性強化（移除所有 hardcoded Neon 密碼；所有憑證改為 NEON_URL 環境變數；Neon 已換新 endpoint）
✅ Dashboard 持倉顯示修正：@st.cache_data 內不可呼叫 st.*，移除後持倉正常載入（v6.5.1）
✅ 環境變數強制更新：load_dotenv(override=True)，防止 Streamlit 熱重載沿用舊 NEON_URL（v6.5.2）
✅ main.py Step 1c NameError 修正：backfill_date → is_backfill（v6.5.2）
✅ sync_to_neon.py 加入 position_monitor 全量同步，持倉狀態即時反映於 Dashboard（v6.5.3）
✅ sync_to_neon.py UniqueViolation 修正：INSERT 帶入本機 id，重置 Neon sequence（v6.5.3）
✅ NEON_URL 強制每次從 .env 重讀（_get_neon_url()），徹底解決 Streamlit hot-reload 沿用舊連線的問題（v6.5.4）
✅ Streamlit Cloud Secrets 更新為新 Neon endpoint（ep-lively-butterfly-aoba7o2b），手機版 Dashboard 連線恢復正常（v6.5.5）
✅ config.py 防護：NEON_URL 存在時本機引擎強制走 SQLite，防止 shell 殘留 DATABASE_URL 誤連舊 Neon endpoint（v6.5.6）
✅ 全量歷史資料重新匯入新 Neon（16,979 筆），手機版 Dashboard 歷史資料恢復完整（v6.5.7）
✅ config.py：本機 DB 不存在時自動改用 NEON_URL 作為 DATABASE_URL，Streamlit Cloud 上所有 get_session() 呼叫改讀 Neon，歷史資料正常顯示（v6.5.8）
✅ 加權指數漲跌幅顏色修正：改用 float 解析判斷正負，不再依賴字串含 '+' 符號，未帶正號的漲幅也能正確顯示綠色（v6.5.9）
✅ 新增「🧪回測」頁面：計算所有歷史推薦的 +5/+20/+60 日報酬、勝率、Sharpe Ratio、最大回撤（MDD）與累積報酬曲線。145 筆推薦驗證結果：20 日勝率 72.7%、均報酬 +4.59%、Sharpe 1.70（v6.6.0）
✅ 回測頁 Styler.applymap → map 修正（pandas >= 2.1 相容性）（v6.6.1）
✅ stock_research.db 從 git 移除；.gitignore 補上 *.db / *.sqlite 防止 DB 檔再次進版控（v6.6.2）
✅ 回測頁全面升級（v6.7.0）：
  - 誠實結論卡：模型均報酬、0050 同期均報酬、Alpha、勝率、p 值、一句話結論（✅/⚠️/❌）
  - Monte Carlo 隨機選股基準（1000 次模擬）：從相同股票池隨機抽選，繪製分布直方圖並標示模型位置百分位
  - 新增 0056（高股息）為第二基準，三線累積報酬曲線（策略 vs 0050 vs 0056）
  - 各基準完整統計表：IR、t 值、p 值、MDD、顯著性
  - 目前誠實驗證結果（2026-07）：模型 20 日均報酬 +4.59%，vs 0050 Alpha -0.31%（p=0.70，不顯著），落於隨機選股分布第 5 百分位 → 當前報酬為牛市 beta，非選股 alpha
✅ 結論卡日期顯示修正：由「最後推薦日」改為「今天日期」，數據本身不受影響（v6.7.1）
✅ Neon 同步效能修正（v6.7.2）：每日自動同步加 --skip-prices，只同步當日分析結果（秒級完成），不再全量跑 8,677 筆 daily_prices；每次新交易日收盤後單獨補同步當日股價
✅ Dashboard timeout 從 300s 提升至 1200s，避免分析觸發後逾時錯誤（v6.7.2）
✅ 今日推薦卡片加入目標價 / 停損價 / 現價三方塊（v6.8.0）：有 PositionMonitor 紀錄用模型計算值，否則用當日收盤 ×+10%/-7% 估算
✅ 💼我的交易 Tab 全新上線（v6.8.0）：
  - 新增 user_trades DB 表，記錄使用者真實下單（股票、買入日、價格、張數）
  - 目前持倉：即時損益%、損益金額、信號燈（觸停損 / 達目標 / 持有過久 / 觀察中）
  - 蒙地卡羅 20 日預測：從當前股價出發，基於歷史日報酬分布，顯示達目標 / 觸停損機率
  - 記錄出場：填出場日期 + 價格，自動計算實現損益
  - 歷史績效：勝率、平均報酬、總實現損益（萬元）、明細表
  - 資料透過 Neon 雙向同步（本機 + 手機版皆可使用）
✅ 我的交易 Tab 穩定性修正（v6.8.1）：
  - UserTrade ImportError 修正：改用 importlib.util 從絕對路徑強制載入 src.database，
    bypass sys.modules 快取與 Streamlit CWD 問題
  - sys.path 改用 Path(__file__).resolve() 取得絕對路徑（避免 CWD 相對路徑失效）
  - 零股支援：shares 欄位語意改為「股數」（非張數），1 張 = 1000 股，零股直接填股數；
    所有 P&L 計算移除 ×1000
  - 股票名稱自動帶出：表單送出時從 stocks 表查詢，無需手動輸入
  - 現價格子加入資料日期標籤（如「2026-07-06」），明示為前一交易日收盤價
✅ 回測正確性修正（v6.8.2）：
  - 20 日報酬改為「第 20 交易日」（取 price list 第 20 筆），非日曆天 >= 20 天
  - Monte Carlo 隨機基準改從每日 AnalysisResult 實際分析過的股票池抽選，非歷史推薦集合
  - MDD 欄位改名為「推薦序列 MDD」，明示非真實投資組合回撤
✅ 股價日期錯位修正（v6.8.3）：
  - price_collector.py 改用 API 回傳的民國日期（Date 欄位，格式 '1150706'）轉換西元日期
    作為存入 DB 的 trade_date，不再用 date.today()
  - 修正根源：TWSE/TPEx API 盤中仍回傳前一交易日資料，但程式用今日日期存入造成日期超前
✅ 回測誠實度強化（v6.8.4）：
  - 回測報酬扣除交易成本：手續費（買+賣 0.285%）+ 證交稅（0.3%）= 0.585%（不含滑價）
  - 誠實結論卡加注：報酬已扣成本；同一檔多次推薦樣本非獨立，p 值可能偏樂觀
  - 推薦卡片目標價來源標示：PositionMonitor 模型算出顯示「目標價」，
    fallback 估算（×1.10/×0.93）明確顯示「目標價 (估)」
  - MC 隨機基準說明文字修正：明確說明股票池為「AnalysisResult 且有價格資料」，
    非全體分析股票（受 price_map 範圍限制）
  - compute_backtest / compute_random_baseline：except 改為 logger.exception，不再靜默失敗
✅ 回測 / 持倉顯示修正（v6.8.5）：
  - MC 隨機基準真正修正：price query 擴展為「所有 AnalysisResult 股票 ∪ 曾推薦股票 ∪ 0050/0056」，
    stock pool 不再受限於歷史推薦集合，基準比較更公平
  - 累積報酬曲線標題改為「推薦序列累積報酬（各筆 20 日報酬連乘）」，
    加說明：同期多檔推薦或持倉重疊時此數字非真實投資組合報酬
  - 持倉配置總覽：total_alloc > 100% 時顯示 warning，明示數字為正規化後比例，需人工取捨
  - 補充確認：_ret_at 20 日報酬已於 v6.8.2 改為第 20 個交易日（index 法），非日曆天
✅ Dashboard 版本字串更新（v6.8.6）：
  - page_title、市場資訊列、側邊欄、footer 四處版本號由 v6.0 統一更新為 v6.8
✅ 🔬模型驗證頁全面升級（v6.8.7）：
  - Tab 名稱：🧪回測 → 🔬模型驗證
  - compute_backtest：加入 20 交易日冷卻期，同股票重複推薦不計入獨立樣本（提升 p 值可信度）
  - 新增 _calc_beta()：Beta = Cov(策略報酬, 0050 報酬) / Var(0050 報酬)
  - 新增 _model_confidence()：依樣本數 / p 值 / Alpha / IR 四項綜合，輸出 1–5 星信心分數
  - 頁面頂部：模型信心分數卡（星等 + 一句話說明）
  - 完整 3×3 指標卡：樣本數（冷卻後）、均報酬（扣成本）、Alpha、Beta、Sharpe、IR、p 值、勝率 vs 0050、推薦序列 MDD
  - 結論列：明示已扣成本、已套用冷卻期、回測期間偏短警告
✅ 成本與冷卻期一致性修正（v6.8.8）：
  - compute_backtest：0050 / 0056 benchmark 同樣扣除 0.585% 成本，Alpha 兩邊基準一致
  - compute_random_baseline：每筆模擬扣同樣 0.585%；加入每輪獨立冷卻追蹤（bisect 快查）；
    deduped recs 邏輯與 compute_backtest 對齊
  - 頁面 disclaimer：明確說明「模型、0050、0056、隨機基準報酬均已扣除 0.585%，未扣滑價」
  - 指標標籤加「淨」字：20日均報酬（淨）、Alpha vs 0050（淨）
✅ 持倉 / 交易頁語意澄清（v6.8.9）：
  - 持倉 Tab：「📈持倉」→「📈模型持倉」
  - 持倉 section title：「持倉追蹤」→「模型持倉追蹤（模擬）」
  - 加 caption 說明：此區為依模型推薦與歷史資料建立的模擬追蹤，不代表實際下單；
    實際交易請以「我的實際交易紀錄」為準
  - 我的交易 section title：「我的交易紀錄」→「我的實際交易紀錄」
✅ Random baseline 可重現性修正（v6.8.10）：
  - compute_random_baseline 加入固定 seed：`_rng = random.Random(42)`
  - 改用 `_rng.choice()` 取代 `random.choice()`，確保每次模擬結果可重現、便於驗證
✅ 停牌/下市/倖存者偏差/小樣本處理（v6.8.11）：
  - compute_backtest：推薦超過 35 天但無 20 日報酬時不再靜默刪除
    - 停牌（有部分後續交易）：用最後成交價計算報酬，標記「⚠️ 停牌」
    - 下市（完全無後續交易）：視為 -100% 損失，標記「❌ 下市」
    - rows 加入 data_flag 欄位，明細表顯示「備注」欄
  - page_backtest 樣本數警告：
    - n < 30：紅色 st.error，說明統計結論可靠性低
    - n < 60：黃色 st.warning，建議累積至 60+ 筆
  - disclaimer 加入：停牌/下市計數說明（幾筆用替代方法計入）
  - disclaimer 加入：倖存者偏差說明（分析池僅含現存有完整價格資料的股票，
    歷史已下市標的無法納入，可能使績效偏高）
✅ Yahoo Finance HTTP 備援（v6.8.12）：
  - 背景：TWSE OpenAPI 有時延遲到 18:00-19:00 才更新當日收盤價
  - 新增 _fetch_yahoo_one()：直接呼叫 Yahoo Finance chart API（requests）
    不使用 yfinance 套件（macOS 上會 segfault）
  - 新增 fetch_yfinance_daily()：
    - 只補抓 AnalysisResult 追蹤股票 + 0050/0056（~593 支），避免全市場 6000+ 逐一呼叫
    - 0.05s 間隔避免 rate limit
  - fetch_all_prices() 自動偵測 API 回傳日期 < 今天 → 啟用 Yahoo 備援
  - 同步修正 TPEx SSL 憑證問題（requests verify=False）
✅ 7/7 收盤價日期錯誤修正（v6.8.13）：
  - 問題根因：前次 session 呼叫 fetch_all_prices(trade_date=date.today()) 時
    將 TWSE 7/6 資料強制標成 7/7 日期存入 DB（共 1225 筆）
  - 修正：刪除全部錯誤 7/7 資料，改用 Yahoo Finance HTTP API 正確存入
    - 2345（智邦）：2645 → 2455
    - 0050：108.25 → 106.20
  - 後續：TWSE OpenAPI 更新後再補全部市場 7/7 資料

---

## 模型可信度評估（2026-07-02）

| 項目 | 狀態 | 說明 |
|------|------|------|
| 基本面評分 | ✅ 第一版修正完成 | 年報截至 4/1 後才使用；季報依 Q1~Q4 公告截止日過濾 |
| 未來函數驗證 | ⚠️ 待長期驗證 | 需跨越 1～2 個完整年報＋季報週期（至少至 2027 Q1）才能確認偏差已消除 |
| 回測樣本 | ⚠️ 樣本期間偏短 | 145 筆推薦，2025-10 至今約 8 個月，未涵蓋完整一個財報年度 |
| 5/20/60 日績效 | ✅ 已建立 | 20 日勝率 72.7%、均報酬 +4.59%、Sharpe 1.70 |
| 策略參數最佳化 | ⏳ 尚未完成 | 滾動視窗驗證、過擬合檢驗 |

**整體模型可信度：7 / 10**（2026-07-02 重新評估）

| 項目 | 狀態 | 說明 |
|------|------|------|
| 基本面評分 | ✅ 第一版修正完成 | 年報截至 4/1 後才使用；季報依 Q1~Q4 公告截止日過濾 |
| 未來函數驗證 | ⚠️ 待長期驗證 | 需跨越 1～2 個完整年報＋季報週期（至少至 2027 Q1）|
| 絕對報酬 | ✅ 正向 | 20 日均 +4.59%，勝率 72.7%，Sharpe 1.70 |
| vs 大盤 Alpha | ❌ 不顯著 | Alpha -0.31%，p=0.70，無統計顯著超額報酬 |
| vs 隨機選股 | ❌ 落後 | Monte Carlo 1000 次模擬，模型僅位於第 5 百分位 |
| 回測樣本 | ⚠️ 偏短 | 145 筆推薦，約 8 個月，未涵蓋完整財報年度 |
| 策略參數最佳化 | ⏳ 尚未完成 | 滾動視窗驗證、過擬合檢驗未做 |

評分說明：絕對報酬看起來好，但 Monte Carlo 和 Alpha 都顯示這段期間的獲利主要來自牛市 beta，而非選股能力。誠實面對數據，暫降回 7 分。目標：累積至 2027 Q1 後跨市場環境驗證，若 Alpha 顯著 → 可升至 9。

---

待完成 / 規劃中：
⏳ decision_journal: 5 支持倉上限硬上限（目前只限 100% 資金，見 19.2 ⚠️）
⏳ Confidence Score: 6 項計劃扣分尚未實作（見 9.5）
⏳ 長期回測驗證：跨越完整年報+季報週期（目標 2027 Q1 後重新評估未來函數偏差）
⏳ ETF 研究 / 產業比較強化

Version 7.0（規劃中）
美股研究
全球市場分析
多市場策略比較

Version 8.0（遠期）
多 Agent 協作
自然語言查詢
自訂研究模板
18.7 Product Success Metrics（產品成功指標）
產品成功可由以下指標衡量：
每日分析成功率
每日資料完整率
報告產出成功率
策略回測穩定性
使用者研究效率提升
Research Candidate 長期表現優於基準指數（作為持續追蹤目標，而非保證）
Chapter 18 完