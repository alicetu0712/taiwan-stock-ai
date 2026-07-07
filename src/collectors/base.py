"""
base.py — Collector 統一抽象介面

所有 Collector 實作都繼承此 ABC，強制具備：
  collect()  — 抓取原始資料
  validate() — 驗證資料品質
  parse()    — 清理 / 標準化
  save()     — 持久化到資料庫

標準執行管道透過 run() 組合上述四步，外部呼叫只需：
    result = SomeCollector().run(trade_date, session)
    if not result:
        logger.error(result.message)
"""

import logging
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Optional, Tuple

import pandas as pd

from src.core.result import CollectResult

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Collector 抽象基底類別。"""

    name: str = "base"

    # ── 四個必實作方法 ────────────────────────────────────────

    @abstractmethod
    def collect(self, trade_date: Optional[date] = None, **kwargs) -> Any:
        """向外部來源抓取資料，回傳原始結果（DataFrame 或 dict）。"""

    @abstractmethod
    def validate(self, data: Any) -> Tuple[bool, str]:
        """
        驗證資料品質。
        回傳 (ok: bool, message: str)；失敗時 message 描述原因。
        """

    @abstractmethod
    def parse(self, data: Any) -> pd.DataFrame:
        """清理、型別轉換、欄位標準化，回傳乾淨的 DataFrame。"""

    @abstractmethod
    def save(self, df: pd.DataFrame, session) -> int:
        """將 DataFrame 寫入資料庫，回傳新增筆數。"""

    # ── 標準執行管道 ──────────────────────────────────────────

    def run(
        self,
        trade_date: Optional[date] = None,
        session=None,
        **kwargs,
    ) -> CollectResult:
        """
        collect → validate → parse → save 標準流程。

        Returns:
            CollectResult  (ok=True → success/warning；ok=False → error)
        """
        logger.info(f"[{self.name}] collect start (date={trade_date})")
        try:
            data = self.collect(trade_date, **kwargs)
        except Exception as e:
            logger.error(f"[{self.name}] collect error: {e}")
            return CollectResult.error(f"collect failed: {e}", source=self.name)

        ok, msg = self.validate(data)
        if not ok:
            logger.warning(f"[{self.name}] validate failed: {msg}")
            return CollectResult.warning(msg, source=self.name)

        try:
            df = self.parse(data)
        except Exception as e:
            logger.error(f"[{self.name}] parse error: {e}")
            return CollectResult.error(f"parse failed: {e}", source=self.name)

        logger.info(f"[{self.name}] parse done: {len(df)} rows")

        if session is None:
            return CollectResult.success(
                len(df), source=self.name, message="ok (not saved)"
            )

        try:
            n = self.save(df, session)
        except Exception as e:
            logger.error(f"[{self.name}] save error: {e}")
            return CollectResult.error(f"save failed: {e}", source=self.name)

        logger.info(f"[{self.name}] save done: {n} rows written")
        return CollectResult.success(n, source=self.name)
