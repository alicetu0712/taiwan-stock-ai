"""
recommend_service.py — 推薦服務層

Dashboard 透過此 Service 取得推薦資料，不直接存取 DB。
"""

import json
import logging
from datetime import date, timedelta
from typing import List

logger = logging.getLogger(__name__)


class RecommendService:
    """推薦資料的讀寫服務。"""

    @staticmethod
    def get_daily(target_date: date) -> List[dict]:
        """
        回傳指定日期的推薦名單。

        Returns:
            list[dict] — 每筆包含 sid, name, level, confidence,
                         scores, advantages, risks, conclusion 等欄位。
        """
        try:
            from sqlalchemy import desc as _desc
            from sqlalchemy import select

            from src.database import (
                AnalysisResult,
                DailyPrice,
                PositionMonitor,
                Recommendation,
                Stock,
                get_session,
            )

            s = get_session()
            recs_rows = (
                s.execute(
                    select(Recommendation)
                    .where(Recommendation.date == target_date)
                    .order_by(Recommendation.confidence.desc())
                )
                .scalars()
                .all()
            )
            stock_name_map = {
                r.stock_id: r.name
                for r in s.execute(select(Stock)).scalars().all()
                if r.name
            }
            ar_map = {
                r.stock_id: r
                for r in s.execute(
                    select(AnalysisResult).where(AnalysisResult.date == target_date)
                )
                .scalars()
                .all()
            }
            pm_map = {
                r.stock_id: r
                for r in s.execute(select(PositionMonitor)).scalars().all()
            }
            rec_ids = [r.stock_id for r in recs_rows]
            price_map = {}
            for sid in rec_ids:
                dp = s.execute(
                    select(DailyPrice)
                    .where(DailyPrice.stock_id == sid)
                    .order_by(_desc(DailyPrice.date))
                    .limit(1)
                ).scalar_one_or_none()
                if dp:
                    price_map[sid] = dp.close
            s.close()

            result = []
            for r in recs_rows:
                ar = ar_map.get(r.stock_id)
                pm = pm_map.get(r.stock_id)
                result.append(
                    {
                        "name": stock_name_map.get(r.stock_id, ""),
                        "sid": r.stock_id,
                        "price": price_map.get(r.stock_id),
                        "level": r.rec_level or "B",
                        "scores": {
                            "quality": ar.quality_score if ar else 0,
                            "timing": ar.timing_score if ar else 0,
                            "behavior": ar.behavior_score if ar else 0,
                            "risk": ar.risk_score if ar else 0,
                            "total": ar.total_score if ar else 0,
                        },
                        "confidence": r.confidence or 0,
                        "advantages": json.loads(r.advantages) if r.advantages else [],
                        "risks": json.loads(r.risks) if r.risks else [],
                        "watch": json.loads(r.watch_points) if r.watch_points else [],
                        "conclusion": r.ai_conclusion or "",
                        "summary": r.summary or "",
                        "target_price": pm.target_price if pm else None,
                        "stop_loss_price": pm.stop_loss_price if pm else None,
                        "position_pct": pm.position_pct if pm else None,
                    }
                )
            return result
        except Exception as e:
            logger.warning(f"RecommendService.get_daily({target_date}) failed: {e}")
            return []

    @staticmethod
    def get_recent(days: int = 60) -> list:
        """回傳最近 N 天的推薦記錄（flat list of dicts）。"""
        try:
            import json
            from sqlalchemy import select

            from src.database import Recommendation, get_session

            s = get_session()
            since = date.today() - timedelta(days=days)
            rows = (
                s.execute(
                    select(Recommendation)
                    .where(Recommendation.date >= since)
                    .order_by(Recommendation.date.desc())
                )
                .scalars()
                .all()
            )
            s.close()
            return [
                {
                    "date": r.date,
                    "stock_id": r.stock_id,
                    "rec_level": r.rec_level,
                    "confidence": r.confidence,
                    "summary": r.summary,
                    "advantages": json.loads(r.advantages) if r.advantages else [],
                    "risks": json.loads(r.risks) if r.risks else [],
                    "watch_points": (
                        json.loads(r.watch_points) if r.watch_points else []
                    ),
                    "ai_conclusion": r.ai_conclusion or "",
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"RecommendService.get_recent({days}d) failed: {e}")
            return []
