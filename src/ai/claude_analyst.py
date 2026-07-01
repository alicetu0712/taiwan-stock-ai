"""
claude_analyst.py — Claude AI 整合（Explainable AI，PRD Chapter 4.8）

使用 Anthropic Claude 為每檔推薦股票生成：
  - 可解釋的投資研究摘要
  - 推薦理由
  - 加分/扣分因素
  - 主要風險
  - AI CIO 結論

若無 API Key，系統仍可正常運作，僅跳過 AI 文字說明。
"""

import logging
from typing import Optional

from config import ANTHROPIC_API_KEY, AI_CONFIG

logger = logging.getLogger(__name__)


class ClaudeAnalyst:
    """
    Claude AI 分析師。
    角色：AI Investment Committee 的 Explainable AI 生成器。
    """

    SYSTEM_PROMPT = """你是一位資深的台灣股票研究分析師，擅長結合基本面、技術面與籌碼分析。
你的任務是根據量化分析數據，生成清晰、專業且易懂的投資研究說明。

重要原則：
1. 公司品質優先（Company Quality First）：先確認公司體質再談時機
2. 可解釋性（Explainable AI）：每個結論都必須有具體數據支撐，且只能引用 prompt 中明確提供的數字
3. 誠實揭露風險：不隱藏缺點和風險
4. 不保證報酬：說明觀察重點，而非預測漲跌
5. 使用繁體中文，語氣專業但不艱澀
6. 嚴禁捏造：不得虛構任何未在 prompt 中提供的財務數字（EPS、ROE、股價、成交量等）；若資料不足，請直接說明「資料待補充」"""

    def __init__(self):
        self.client = None
        if ANTHROPIC_API_KEY:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                logger.info("Claude API initialized successfully.")
            except ImportError:
                logger.warning("anthropic package not installed. Run: pip install anthropic")
            except Exception as e:
                logger.warning(f"Claude API initialization failed: {e}")
        else:
            logger.warning("ANTHROPIC_API_KEY not set. AI explanations will use rule-based fallback.")

    def generate_price_targets(
        self,
        rec,              # StockRecommendation
        daily_returns: list = None,   # 歷史日報酬率
    ) -> dict:
        """
        為推薦股票生成 AI 動態停損價與目標價。
        回傳 {"target_price", "stop_loss_price", "target_pct", "stop_loss_pct", "rationale"}
        """
        close = getattr(rec, "close", None) or getattr(rec, "close_price", None)
        if not close or close <= 0:
            return self._rule_based_price_targets(rec)

        # 計算歷史波動度
        vol_str = ""
        if daily_returns and len(daily_returns) >= 20:
            import numpy as np
            sig = float(np.std(daily_returns)) * 100
            vol_str = f"近 {len(daily_returns)} 日日均波動：{sig:.2f}%（年化約 {sig * (252**0.5):.1f}%）"

        prompt = f"""請為以下台灣股票設定合理的「目標價」與「停損價」：

股票代號：{rec.stock_id}
公司名稱：{rec.name}
現價（推薦當日收盤）：{close:.2f} 元
推薦等級：{rec.rec_level}（{rec.stars}）
綜合評分：{rec.total_score:.0f}/100
技術時機分：{rec.timing_score:.0f}/100
市場行為分：{rec.behavior_score:.0f}/100
{vol_str}

主要優勢：{'; '.join(rec.advantages[:3]) if rec.advantages else '無'}
主要風險：{'; '.join(rec.risks[:3]) if rec.risks else '無'}

請根據：
1. 技術面支撐/壓力位（不要虛構具體數字，以百分比推估）
2. 歷史波動度（若有提供）
3. 推薦等級（等級高可給較寬的目標）

輸出格式（嚴格遵守，不要加其他文字）：
TARGET_PCT: [數字]
STOP_LOSS_PCT: [數字]（負數，例如 -8.0）
RATIONALE: [一句話說明依據]

限制：
- TARGET_PCT 範圍：A+=20~30%, A=12~20%, B=8~15%
- STOP_LOSS_PCT 範圍：-5% 到 -12%
- 不得虛構支撐/壓力位的具體股價數字"""

        if self.client is None:
            return self._rule_based_price_targets(rec)

        try:
            response = self.client.messages.create(
                model      = AI_CONFIG["model"],
                max_tokens = 200,
                temperature= 0.2,
                system     = self.SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": prompt}],
            )
            return self._parse_price_targets(response.content[0].text, rec, close)
        except Exception as e:
            logger.warning(f"Price target generation failed ({rec.stock_id}): {e}")
            return self._rule_based_price_targets(rec)

    def _parse_price_targets(self, text: str, rec, close: float) -> dict:
        import re
        target_pct   = None
        sl_pct       = None
        rationale    = ""

        for line in text.strip().split("\n"):
            m = re.match(r"TARGET_PCT:\s*([\d.]+)", line)
            if m:
                target_pct = float(m.group(1))
            m = re.match(r"STOP_LOSS_PCT:\s*(-?[\d.]+)", line)
            if m:
                sl_pct = float(m.group(1))
            m = re.match(r"RATIONALE:\s*(.+)", line)
            if m:
                rationale = m.group(1).strip()

        if target_pct is None or sl_pct is None:
            return self._rule_based_price_targets(rec)

        # 確保停損為負值
        sl_pct = -abs(sl_pct)
        target_price    = round(close * (1 + target_pct / 100), 2)
        stop_loss_price = round(close * (1 + sl_pct / 100), 2)
        return {
            "target_price":    target_price,
            "stop_loss_price": stop_loss_price,
            "target_pct":      round(target_pct, 1),
            "stop_loss_pct":   round(sl_pct, 1),
            "rationale":       rationale,
        }

    def _rule_based_price_targets(self, rec) -> dict:
        """無 API 或解析失敗時的規則式備案。"""
        close = getattr(rec, "close", None) or getattr(rec, "close_price", None) or 100.0
        level_map = {"A+": (25.0, -8.0), "A": (15.0, -8.0), "B": (10.0, -7.0)}
        target_pct, sl_pct = level_map.get(rec.rec_level, (10.0, -7.0))
        return {
            "target_price":    round(close * (1 + target_pct / 100), 2),
            "stop_loss_price": round(close * (1 + sl_pct / 100), 2),
            "target_pct":      target_pct,
            "stop_loss_pct":   sl_pct,
            "rationale":       f"依 {rec.rec_level} 等級規則設定目標 +{target_pct}% / 停損 {sl_pct}%",
        }

    def generate_research_report(
        self,
        rec,   # StockRecommendation
    ) -> dict:
        """
        為單一推薦股票生成完整研究報告文字。
        回傳 dict 包含各說明欄位。
        """
        if self.client is None:
            return self._rule_based_report(rec)

        prompt = self._build_prompt(rec)
        try:
            response = self.client.messages.create(
                model      = AI_CONFIG["model"],
                max_tokens = AI_CONFIG["max_tokens"],
                temperature= AI_CONFIG["temperature"],
                system     = self.SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            return self._parse_response(text, rec)
        except Exception as e:
            logger.warning(f"Claude API call failed ({rec.stock_id}): {e}")
            return self._rule_based_report(rec)

    def generate_no_recommendation_report(
        self,
        market_summary: dict,
        n_analyzed: int,
        n_qualified: int,
        fail_reasons: list,
        trade_date,
    ) -> str:
        """
        當今日無推薦標的時，生成說明報告。
        """
        if self.client is None:
            return self._rule_based_no_rec(n_analyzed, n_qualified, fail_reasons)

        prompt = f"""今日（{trade_date}）對台灣股市 {n_analyzed} 檔股票完成全面分析，
其中 {n_qualified} 檔通過基本面篩選，但最終無任何標的達到推薦標準。

主要淘汰原因統計：
{chr(10).join(f'- {r}' for r in fail_reasons[:5])}

大盤市場狀況：
- 市場情緒：{market_summary.get('sentiment', 'N/A')}
- 上漲家數：{market_summary.get('up_count', 'N/A')}
- 下跌家數：{market_summary.get('down_count', 'N/A')}

請用兩至三段話說明今日為何沒有推薦標的，並給予投資人適當建議。"""

        try:
            response = self.client.messages.create(
                model      = AI_CONFIG["model"],
                max_tokens = 500,
                temperature= 0.3,
                system     = self.SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            logger.warning(f"Claude no-rec report failed: {e}")
            return self._rule_based_no_rec(n_analyzed, n_qualified, fail_reasons)

    def generate_market_summary(self, market_data: dict, trade_date) -> str:
        """生成每日市場摘要（AI 版本）。"""
        if self.client is None:
            return self._rule_based_market_summary(market_data)

        prompt = f"""請根據以下台灣股市今日（{trade_date}）資料，生成一段簡短的市場摘要（約100字）：

加權指數：{market_data.get('index_close', 'N/A')}
漲跌幅：{market_data.get('index_change_pct', 'N/A')}%
總成交金額：{market_data.get('total_amount_b', 'N/A')} 億元
上漲家數：{market_data.get('up_count', 'N/A')}
下跌家數：{market_data.get('down_count', 'N/A')}
市場情緒：{market_data.get('sentiment', 'N/A')}

請用一段話描述今日市場狀況，重點說明成交量是否支撐漲勢，以及市場情緒。"""

        try:
            response = self.client.messages.create(
                model      = AI_CONFIG["model"],
                max_tokens = 200,
                temperature= 0.3,
                system     = self.SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            logger.warning(f"Claude market summary failed: {e}")
            return self._rule_based_market_summary(market_data)

    # ── Private Methods ───────────────────────────────────────

    def _build_prompt(self, rec) -> str:
        """建立 Claude prompt。"""
        adv_str   = "\n".join(f"  • {a}" for a in rec.advantages) or "  （無明顯優勢資料）"
        risk_str  = "\n".join(f"  • {r}" for r in rec.risks)     or "  （無明顯風險資料）"
        watch_str = "\n".join(f"  • {w}" for w in rec.watch_points) or "  （無特別觀察重點）"

        has_quality = rec.quality_score > 0
        quality_context = (
            f"公司品質評分（Company Quality）：{rec.quality_score:.0f}/100（{rec.quality_grade} 級）"
            if has_quality else
            "公司品質評分：無財務資料（系統採動態加權，本次評分依據技術面與籌碼面）"
        )

        fundamental_instruction = (
            "【基本面說明】\n根據品質評分說明公司體質（2-3句）。禁止虛構任何財務數字（EPS、ROE、營收等），僅根據提供的評分與優劣勢作說明。"
            if has_quality else
            "【基本面說明】\n目前無財務資料，請如實說明「本次進入研究名單的依據為技術面與籌碼面表現，財務基本面資料待補充」（1-2句）。禁止捏造任何財務數字。"
        )

        close_price = getattr(rec, 'close_price', None) or getattr(rec, 'close', None)
        price_line = f"當日收盤價：{close_price:.2f} 元" if close_price else ""

        return f"""請為以下台灣股票生成專業的投資研究報告：

=== 股票資訊 ===
股票代號：{rec.stock_id}
公司名稱：{rec.name}
所屬市場：{rec.market}
所屬產業：{rec.industry or '未分類'}
分析日期：{rec.date}
{price_line}

=== 量化分析評分 ===
• {quality_context}
• 技術時機評分（Timing）：{rec.timing_score:.0f}/100
• 市場行為評分（Market Behavior）：{rec.behavior_score:.0f}/100
• 綜合評分（Total Score）：{rec.total_score:.0f}/100
• 推薦等級：{rec.rec_level}（{rec.stars}）
• 分析信心：{rec.confidence:.0f}%

=== 系統分析優勢 ===
{adv_str}

=== 系統分析風險 ===
{risk_str}

=== 建議觀察重點 ===
{watch_str}

⚠️ 重要限制：
- 只能根據上方提供的數據作說明，禁止虛構任何未提供的財務數字、股價、成交量、法說會資訊
- 若某項資料為「無」，請如實說明資料不足，不得自行補充假設

請提供以下內容（使用繁體中文）：

【推薦摘要】
一句話說明為何值得研究此標的（根據實際有資料的維度）。

{fundamental_instruction}

【技術面說明】
根據技術時機評分（{rec.timing_score:.0f}分）說明目前技術面狀況（2-3句）。禁止虛構具體股價數字（如突破幾元）。

【主要風險】
條列 2-3 項主要風險（僅根據上方「系統分析風險」欄位，不得自行發明）。

【AI 結論】
根據現有資料給出整體評估（3-4句）。若財務資料不足，需明確說明此局限性。

注意：本系統為研究輔助工具，所有結論僅供研究參考，不構成投資建議。"""

    def _parse_response(self, text: str, rec) -> dict:
        """解析 Claude 回應，提取各段落。"""
        result = {
            "ai_summary":     "",
            "fundamental_ai": "",
            "technical_ai":   "",
            "risks_ai":       "",
            "conclusion_ai":  text,   # 預設整段
        }

        sections = {
            "【推薦摘要】":   "ai_summary",
            "【基本面說明】": "fundamental_ai",
            "【技術面說明】": "technical_ai",
            "【主要風險】":   "risks_ai",
            "【AI 結論】":    "conclusion_ai",
        }

        current_key = None
        lines = text.split("\n")
        buffer = []

        for line in lines:
            matched = False
            for header, key in sections.items():
                if header in line:
                    if current_key and buffer:
                        result[current_key] = "\n".join(buffer).strip()
                    current_key = key
                    buffer = []
                    matched = True
                    break
            if not matched and current_key:
                buffer.append(line)

        if current_key and buffer:
            result[current_key] = "\n".join(buffer).strip()

        return result

    def _rule_based_report(self, rec) -> dict:
        """無 Claude API 時的規則式文字生成（備案）。"""
        quality_desc = {
            "A+": "公司體質非常優秀，長期競爭力強，是值得深入研究的優質標的。",
            "A":  "公司基本面良好，獲利能力穩定，具備長期投資價值。",
            "B":  "公司體質尚可，基本面指標在可接受範圍。",
            "C":  "公司體質普通，基本面有部分待改善之處。",
            "D":  "公司體質較弱，基本面指標偏低。",
        }

        return {
            "ai_summary":     rec.summary,
            "fundamental_ai": quality_desc.get(rec.quality_grade, ""),
            "technical_ai":   self._format_technical_ai(rec),
            "risks_ai":       "\n".join(f"• {r}" for r in rec.risks[:3]),
            "conclusion_ai":  rec.ai_conclusion,
        }

    def _format_technical_ai(self, rec) -> str:
        """格式化技術面說明（規則式）。"""
        parts = []
        if rec.timing_score >= 70:
            parts.append("技術面呈偏多格局，趨勢健康。")
        elif rec.timing_score >= 50:
            parts.append("技術面中性，等待更明確方向。")
        else:
            parts.append("技術面偏弱，建議等待訊號改善。")
        return " ".join(parts)

    def _rule_based_no_rec(
        self,
        n_analyzed: int,
        n_qualified: int,
        fail_reasons: list,
    ) -> str:
        reasons = "、".join(fail_reasons[:3]) if fail_reasons else "基本面或技術面條件不足"
        return (
            f"今日共分析 {n_analyzed} 檔股票，其中 {n_qualified} 檔通過初步篩選，"
            f"但最終無標的達到本策略最低研究標準。"
            f"主要原因包括：{reasons}。"
            f"建議投資人耐心等待市場出現符合條件的標的，切勿因缺乏推薦而降低投資標準。"
        )

    def _rule_based_market_summary(self, market_data: dict) -> str:
        sentiment = market_data.get("sentiment", "Neutral")
        index     = market_data.get("index_close", "N/A")
        pct       = market_data.get("index_change_pct", "N/A")
        amt       = market_data.get("total_amount_b", "N/A")
        sentiment_desc = {"Bullish": "偏多", "Bearish": "偏空", "Neutral": "中性"}.get(sentiment, "中性")
        return (
            f"今日加權指數收 {index} 點，漲跌幅 {pct}%，"
            f"大盤成交金額 {amt} 億元，市場情緒{sentiment_desc}。"
        )
