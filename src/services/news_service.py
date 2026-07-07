"""
news_service.py — 新聞服務層

Dashboard / main.py 透過此 Service 取得新聞，
不直接 import NewsCollector。
"""

import logging
from datetime import date
from typing import List, Optional

from src.core.result import CollectResult

logger = logging.getLogger(__name__)


class NewsService:
    """新聞蒐集與查詢服務。"""

    @staticmethod
    def fetch(trade_date: Optional[date] = None, session=None) -> CollectResult:
        """
        執行新聞抓取（委託 NewsCollector.run()）。

        Args:
            trade_date: 指定日期（None = 今日）
            session:    DB session（None = 不寫入）

        Returns:
            CollectResult — source="news", n_rows=抓到的新聞數量
        """
        try:
            from src.collectors.news_collector import NewsCollector

            return NewsCollector().run(trade_date=trade_date, session=session)
        except Exception as e:
            logger.error(f"NewsService.fetch failed: {e}")
            return CollectResult.error(f"news fetch failed: {e}", source="news")

    @staticmethod
    def get_recent_headlines(days: int = 7) -> List[dict]:
        """
        從快取或 DB 取得近期新聞標題（若有儲存）。

        目前新聞資料不寫 DB，此方法回傳空 list 保留介面。
        未來若新增 news table，在此實作查詢邏輯即可。
        """
        return []
