"""
portfolio_service.py — 持倉管理服務層

提供持倉讀寫的統一介面，Dashboard 不直接操作 PositionMonitor ORM。
"""

import logging
from datetime import date
from typing import List, Optional

logger = logging.getLogger(__name__)


class PortfolioService:
    """持倉追蹤的讀寫服務。"""

    @staticmethod
    def get_positions() -> List[dict]:
        """回傳所有持倉監控記錄。"""
        try:
            from sqlalchemy import select

            from src.database import PositionMonitor, get_session

            s = get_session()
            rows = s.execute(select(PositionMonitor)).scalars().all()
            s.close()
            return [
                {
                    "stock_id": r.stock_id,
                    "entry_date": r.entry_date,
                    "entry_price": r.entry_price,
                    "target_price": r.target_price,
                    "stop_loss_price": r.stop_loss_price,
                    "position_pct": r.position_pct,
                    "status": r.status,
                    "notes": r.notes,
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"PortfolioService.get_positions failed: {e}")
            return []

    @staticmethod
    def upsert_position(
        stock_id: str,
        entry_price: Optional[float] = None,
        target_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        position_pct: Optional[float] = None,
        entry_date: Optional[date] = None,
        status: str = "active",
        notes: str = "",
    ) -> bool:
        """新增或更新持倉記錄，回傳是否成功。"""
        try:
            from src.database import PositionMonitor, get_session

            s = get_session()
            pm = s.query(PositionMonitor).filter_by(stock_id=stock_id).first()
            if pm is None:
                pm = PositionMonitor(stock_id=stock_id)
                s.add(pm)
            if entry_price is not None:
                pm.entry_price = entry_price
            if target_price is not None:
                pm.target_price = target_price
            if stop_loss_price is not None:
                pm.stop_loss_price = stop_loss_price
            if position_pct is not None:
                pm.position_pct = position_pct
            if entry_date is not None:
                pm.entry_date = entry_date
            pm.status = status
            if notes:
                pm.notes = notes
            s.commit()
            s.close()
            return True
        except Exception as e:
            logger.warning(f"PortfolioService.upsert_position({stock_id}) failed: {e}")
            return False

    @staticmethod
    def get_monte_carlo_summary(stock_id: str) -> dict:
        """
        回傳個股的蒙地卡羅模擬摘要（若存在）。

        Returns dict with keys: target_prob, stop_prob, expected_return, paths, or empty dict.
        """
        try:
            from src.database import PositionMonitor, get_session

            s = get_session()
            pm = s.query(PositionMonitor).filter_by(stock_id=stock_id).first()
            s.close()
            if pm is None:
                return {}
            return {
                "target_price": pm.target_price,
                "stop_loss_price": pm.stop_loss_price,
                "position_pct": pm.position_pct,
                "status": pm.status,
            }
        except Exception as e:
            logger.warning(
                f"PortfolioService.get_monte_carlo_summary({stock_id}) failed: {e}"
            )
            return {}
