PRD：Taiwan Stock AI v7.0 — Engineering Refactor
Version：7.0
一、目標（Objective）
目前台股 AI 研究平台已完成：
AI 選股
財報分析
基本面分析
技術面分析

新聞分析
Walk-forward 驗證
回測
Dashboard
下一階段不再新增功能，而是提升：
工程品質（Engineering Quality）
目標：
讓專案達到 Senior Python Engineer / GitHub Open Source Project 的水準。
二、核心目標
提升：
Maintainability
Scalability
Readability
Testability
Reliability
而不是新增功能。
三、Dashboard 模組化（★★★★★）
現況
目前：
dashboard/
    app.py
app.py 已經越來越大。
修改
改：
dashboard/

app.py

pages/

overview.py

backtest.py

position.py

reports.py

components/

metric_card.py

stock_table.py

chart.py

utils.py
app.py
只保留：
render_overview()

render_backtest()

render_position()

render_reports()
畫面：
全部：
拆出去。
效益
減少：
app.py
2000+
行。
方便：
多人開發。
四、Backend 模組重構（★★★★★）
目前：
src/

collectors/

models/

analysis/
改：
src/

collectors/

analysis/

backtest/

services/

models/

utils/
新增：
services/

recommend_service.py

portfolio_service.py

backtest_service.py

news_service.py
目的：
Dashboard
不要：
直接：
Call
Collector。
而是：
Dashboard
↓
Service
↓
Collector
↓
Database
五、Logger（★★★★★）
目前：
部分：
except Exception:

pass
改：
logger.warning(...)

logger.error(...)
新增：
logs/

app.log

collector.log

backtest.log
Dashboard：
新增：
System Status

Collector

News

Goodinfo

Yahoo

Success Rate
六、Type Hint（★★★★）
所有：
Function
增加：
Type Hint。
例如：
def analyze(
    stock_id: str,
    as_of_date: date
) -> AnalysisResult:
避免：
Any

Dict
到處都是。
七、Unit Test（★★★★★）
新增：
tests/

test_price_collector.py

test_goodinfo.py

test_financial.py

test_backtest.py

test_score.py

test_position.py
Coverage
至少：
80%。
必測
Price
↓
Collector
↓
Score
↓
Recommendation
↓
Backtest
八、GitHub Actions（★★★★★）
新增：
.github/workflows/

test.yml
每次：
Push
自動：
pytest

ruff

black

flake8
Fail：
禁止 Merge。
九、Code Style（★★★★）
新增：
ruff

black

isort
統一：
Format。
十、Dependency（★★★★）
目前：
requirements.txt
新增：
pyproject.toml
未來：
支援：
uv

poetry
十一、README（★★★★★）
目前：
README
資訊：
不足。
新增：
Project Overview

Architecture

Screenshots

Installation

How it Works

Walk Forward

Backtest

Limitations

Future Roadmap

License
新增：
Architecture：
Dashboard

↓

Services

↓

Collectors

↓

Database

↓

Analysis

↓

Recommendation
十二、API 統一（★★★★）
Collector：
全部：
統一：
collect()

validate()

parse()

save()
不要：
每個：
命名：
不同。
十三、Exception 統一（★★★★★）
目前：
部分：
return None
改：
Result

Success

Warning

Error
Dashboard：
可以知道：
是哪裡：
失敗。
十四、資料品質監控（★★★★★）
Dashboard：
新增：
Data Health
例如：
Price

99%

Financial

95%

News

87%

Goodinfo

100%

Recommendation

Ready
方便：
知道：
是不是：
抓不到資料。
十五、Performance（★★★★）
新增：
Cache。
例如：
TTL

30分鐘
避免：
每次：
重抓。
十六、Documentation（★★★★★）
docs/
新增：
Architecture.md

Backtest.md

Collector.md

WalkForward.md

Scoring.md

Deployment.md

DeveloperGuide.md
十七、Developer Guide（★★★★）
新增：
如何新增：

Collector

↓

Analyzer

↓

Dashboard

↓

Test
方便：
未來：
維護。