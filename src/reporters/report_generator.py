"""
report_generator.py — 每日研究報告生成（PRD Chapter 9.8, 11.8）

每日產出：
  - Markdown 報告（主要輸出）
  - Excel 報告（可選）
  - Decision Journal 紀錄

報告包含：
  - 今日市場摘要
  - AI Executive Summary
  - Research Candidates（最多3檔，含完整分析）
  - Watch List
  - 風險提醒
  - 今日重大事件
  - 策略績效（若有歷史資料）
"""

import logging
from datetime import date
from pathlib import Path

from config import REPORTS_DIR

logger = logging.getLogger(__name__)


class ReportGenerator:
    """每日研究報告生成器。"""

    def __init__(self):
        self.reports_dir = REPORTS_DIR / "daily"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_daily_report(
        self,
        trade_date: date,
        recommendations: list,  # List[StockRecommendation]
        no_rec_reason: str,
        market_summary: dict,
        ai_reports: dict,  # {stock_id: {ai_summary, fundamental_ai, ...}}
        market_ai_text: str,
        n_analyzed: int,
        n_qualified: int,
        watch_list: list = None,
        upcoming_events: list = None,
        strategy_version: str = "v6.0",
    ) -> dict:
        """
        生成完整每日研究報告。
        回傳 dict 包含：md_path, md_content
        """
        md = self._build_markdown(
            trade_date=trade_date,
            recs=recommendations,
            no_rec_reason=no_rec_reason,
            market_summary=market_summary,
            ai_reports=ai_reports,
            market_ai_text=market_ai_text,
            n_analyzed=n_analyzed,
            n_qualified=n_qualified,
            watch_list=watch_list or [],
            upcoming_events=upcoming_events or [],
            strategy_version=strategy_version,
        )

        # 儲存 Markdown（本機檔案）
        md_path = self.reports_dir / f"{trade_date.isoformat()}_report.md"
        try:
            md_path.write_text(md, encoding="utf-8")
            logger.info(f"Daily report saved: {md_path}")
        except Exception as e:
            logger.warning(f"File write failed (ok on cloud): {e}")

        # 儲存 Markdown 到資料庫（雲端環境使用）
        try:
            from src.database import DailyReport, get_session

            s = get_session()
            existing = s.query(DailyReport).filter_by(date=trade_date).first()
            if existing:
                existing.content_md = md
            else:
                s.add(
                    DailyReport(
                        date=trade_date,
                        content_md=md,
                        strategy_version=strategy_version,
                    )
                )
            s.commit()
            s.close()
        except Exception as e:
            logger.warning(f"DB report save failed: {e}")

        result = {
            "md_path": str(md_path),
            "md_content": md,
        }

        # 生成 Excel（可選）
        try:
            xlsx_path = self._generate_excel(trade_date, recommendations)
            result["xlsx_path"] = str(xlsx_path)
        except Exception as e:
            logger.warning(f"Excel generation failed: {e}")

        return result

    def _build_markdown(
        self,
        trade_date,
        recs,
        no_rec_reason,
        market_summary,
        ai_reports,
        market_ai_text,
        n_analyzed,
        n_qualified,
        watch_list,
        upcoming_events,
        strategy_version,
    ) -> str:
        lines = []

        # ── 標題 ──────────────────────────────────────────────
        lines.extend(
            [
                "# AI Taiwan Equity Research Platform",
                f"## 每日研究報告 — {trade_date.strftime('%Y 年 %m 月 %d 日')}",
                "",
                f"> 策略版本：{strategy_version} | 分析股票：{n_analyzed} 檔 | 通過篩選：{n_qualified} 檔",
                "> **本報告為 AI 研究輔助工具，所有內容僅供研究參考，不構成投資建議。**",
                "",
                "---",
                "",
            ]
        )

        # ── ① 今日市場摘要 ───────────────────────────────────
        lines.append("## ① 今日市場摘要")
        lines.append("")
        if market_summary:
            sentiment = market_summary.get("sentiment", "N/A")
            sentiment_emoji = {"Bullish": "📈", "Bearish": "📉", "Neutral": "➡️"}.get(
                sentiment, ""
            )
            lines.extend(
                [
                    "| 指標 | 數值 |",
                    "| ---- | ---- |",
                    f"| 加權指數 | {market_summary.get('index_close', 'N/A')} |",
                    f"| 漲跌幅 | {market_summary.get('index_change_pct', 'N/A')}% |",
                    f"| 成交金額 | {market_summary.get('total_amount_b', 'N/A')} 億元 |",
                    f"| 上漲家數 | {market_summary.get('up_count', 'N/A')} |",
                    f"| 下跌家數 | {market_summary.get('down_count', 'N/A')} |",
                    f"| 市場情緒 | {sentiment_emoji} {sentiment} |",
                    "",
                ]
            )
        if market_ai_text:
            lines.extend([f"> {market_ai_text}", ""])

        lines.extend(["---", ""])

        # ── ② AI Executive Summary ───────────────────────────
        lines.append("## ② AI Executive Summary")
        lines.append("")
        n_recs = len(recs)
        if n_recs > 0:
            lines.append(
                f"今日共分析 **{n_analyzed}** 檔台股，**{n_qualified}** 檔通過基本面篩選，"
                f"最終有 **{n_recs}** 檔達到研究候選標準。"
            )
        else:
            lines.append(
                f"今日共分析 **{n_analyzed}** 檔台股，**{n_qualified}** 檔通過基本面篩選，"
                f"但**無任何標的達到推薦標準**。"
            )
        lines.extend(["", "---", ""])

        # ── ③ Research Candidates ────────────────────────────
        lines.append("## ③ Research Candidates（今日研究名單）")
        lines.append("")

        if not recs:
            lines.extend(
                [
                    f"> {no_rec_reason}",
                    "",
                ]
            )
        else:
            for i, rec in enumerate(recs, 1):
                lines.extend(
                    self._format_recommendation(
                        i, rec, ai_reports.get(rec.stock_id, {})
                    )
                )

        lines.extend(["---", ""])

        # ── ④ Watch List ─────────────────────────────────────
        if watch_list:
            lines.append("## ④ Watch List（持續觀察名單）")
            lines.append("")
            lines.append("| 代號 | 公司名稱 | 原因 |")
            lines.append("| ---- | -------- | ---- |")
            for w in watch_list[:10]:
                lines.append(
                    f"| {w.get('stock_id', '')} | {w.get('name', '')} | {w.get('reason', '')} |"
                )
            lines.extend(["", "---", ""])

        # ── ⑤ 重大事件提醒 ──────────────────────────────────
        if upcoming_events:
            lines.append("## ⑤ 近期重大事件提醒")
            lines.append("")
            for evt in upcoming_events[:8]:
                lines.append(f"- {evt}")
            lines.extend(["", "---", ""])

        # ── 免責聲明 ─────────────────────────────────────────
        lines.extend(
            [
                "---",
                "",
                "## 免責聲明",
                "",
                "本報告由 AI Taiwan Equity Research Platform 自動生成，僅作為研究輔助工具。",
                "所有評分、推薦等級均基於公開資料之量化分析，不代表投資建議，亦不保證投資報酬。",
                "投資人應自行評估風險，並對自身投資決策負責。",
                "",
                f"*報告生成時間：{trade_date.isoformat()} | 策略版本 {strategy_version}*",
            ]
        )

        return "\n".join(lines)

    def _format_recommendation(self, rank: int, rec, ai_report: dict) -> list:
        """格式化單一推薦股票的詳細分析。"""
        lines = []

        # 標題
        level_emoji = {"A+": "🌟", "A": "⭐", "B": "💡", "C": "👀", "D": "⚠️"}
        emoji = level_emoji.get(rec.rec_level, "")
        lines.extend(
            [
                f"### {rank}. {emoji} {rec.name}（{rec.stock_id}）—— {rec.rec_level} 級",
                "",
            ]
        )

        # 評分總覽
        lines.extend(
            [
                "| 評分項目 | 分數 | 說明 |",
                "| -------- | ---- | ---- |",
                f"| 公司品質 | **{rec.quality_score:.0f}**/100 | {rec.quality_grade} 級 |",
                f"| 技術時機 | **{rec.timing_score:.0f}**/100 | |",
                f"| 市場行為 | **{rec.behavior_score:.0f}**/100 | |",
                f"| 風險評估 | **{rec.risk_score:.0f}**/100 | （越高越安全）|",
                f"| **綜合評分** | **{rec.total_score:.0f}**/100 | {rec.stars} |",
                f"| 分析信心 | {rec.confidence:.0f}% | {'⚠️ 信心不足' if rec.confidence < 70 else ''} |",
                "",
            ]
        )

        # AI 推薦摘要
        ai_summary = ai_report.get("ai_summary") or rec.summary
        if ai_summary:
            lines.extend([f"**推薦摘要：** {ai_summary}", ""])

        # 基本面說明
        fundamental_ai = ai_report.get("fundamental_ai", "")
        if fundamental_ai:
            lines.extend(["**基本面分析**", "", fundamental_ai, ""])

        # 技術面說明
        technical_ai = ai_report.get("technical_ai", "")
        if technical_ai:
            lines.extend(["**技術面分析**", "", technical_ai, ""])

        # 主要優勢
        if rec.advantages:
            lines.append("**主要優勢**")
            lines.append("")
            for a in rec.advantages:
                lines.append(f"- ✅ {a}")
            lines.append("")

        # 主要風險
        risks_text = ai_report.get("risks_ai", "")
        if risks_text:
            lines.extend(["**主要風險**", "", risks_text, ""])
        elif rec.risks:
            lines.append("**主要風險**")
            lines.append("")
            for r in rec.risks:
                lines.append(f"- ⚠️ {r}")
            lines.append("")

        # 觀察重點
        if rec.watch_points:
            lines.append("**建議觀察重點**")
            lines.append("")
            for w in rec.watch_points:
                lines.append(f"- 🔍 {w}")
            lines.append("")

        # AI 結論
        conclusion = ai_report.get("conclusion_ai") or rec.ai_conclusion
        if conclusion:
            lines.extend(["**AI 結論**", "", f"> {conclusion}", ""])

        lines.append("---")
        lines.append("")
        return lines

    def _generate_excel(self, trade_date: date, recommendations: list) -> Path:
        """生成 Excel 報告。"""
        import pandas as pd

        xlsx_path = self.reports_dir / f"{trade_date.isoformat()}_report.xlsx"
        data = []
        for rec in recommendations:
            data.append(
                {
                    "股票代號": rec.stock_id,
                    "公司名稱": rec.name,
                    "市場": rec.market,
                    "推薦等級": rec.rec_level,
                    "星級": rec.stars,
                    "公司品質": rec.quality_score,
                    "技術時機": rec.timing_score,
                    "市場行為": rec.behavior_score,
                    "風險評分": rec.risk_score,
                    "綜合評分": rec.total_score,
                    "信心分數": rec.confidence,
                    "推薦摘要": rec.summary,
                    "AI 結論": rec.ai_conclusion,
                }
            )

        df = pd.DataFrame(data) if data else pd.DataFrame()
        df.to_excel(xlsx_path, index=False, sheet_name="研究候選名單")
        return xlsx_path
