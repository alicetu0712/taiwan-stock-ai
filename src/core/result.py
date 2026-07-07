"""
result.py — 統一回傳型別

取代散落各處的 return None / return {} / return []，
讓呼叫端（Dashboard / main.py）可以明確區分：
  Success  — 正常完成
  Warning  — 完成但有值得注意的狀況（資料缺失、部分失敗）
  Error    — 操作失敗，結果不可信

使用方式：
    result = PriceCollector().run(trade_date, session)
    if result.is_error:
        st.error(f"[{result.source}] {result.message}")
    elif result.is_warning:
        st.warning(result.message)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


# ── 基底 Result ───────────────────────────────────────────────


@dataclass
class Result(Generic[T]):
    """
    通用結果容器。

    Attributes:
        ok:      True = Success / Warning；False = Error
        level:   "success" | "warning" | "error"
        message: 人類可讀的說明（Dashboard 直接顯示）
        data:    成功時的回傳值（可為 None）
        source:  產生此結果的模組名稱（e.g. "price", "chip"）
        ts:      產生時間（自動填入）
    """

    ok: bool
    level: str  # "success" | "warning" | "error"
    message: str
    data: Optional[T] = None
    source: str = ""
    ts: datetime = field(default_factory=datetime.now)

    # ── 語意屬性 ──────────────────────────────────────────────

    @property
    def is_success(self) -> bool:
        return self.level == "success"

    @property
    def is_warning(self) -> bool:
        return self.level == "warning"

    @property
    def is_error(self) -> bool:
        return self.level == "error"

    # ── 工廠方法 ──────────────────────────────────────────────

    @classmethod
    def success(
        cls, data: T = None, *, source: str = "", message: str = "ok"
    ) -> Result[T]:
        return cls(ok=True, level="success", message=message, data=data, source=source)

    @classmethod
    def warning(cls, message: str, data: T = None, *, source: str = "") -> Result[T]:
        return cls(ok=True, level="warning", message=message, data=data, source=source)

    @classmethod
    def error(cls, message: str, *, source: str = "") -> Result[T]:
        return cls(ok=False, level="error", message=message, data=None, source=source)

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        return f"Result({self.level}, source={self.source!r}, msg={self.message!r})"


# ── Collector 專用 Result ─────────────────────────────────────


@dataclass
class CollectResult(Result[int]):
    """
    Collector.run() 的回傳型別。

    data = n_rows（成功儲存 / 處理的筆數）

    範例：
        result = PriceCollector().run(trade_date, session)
        if not result:
            logger.error(result.message)
        else:
            logger.info(f"saved {result.n_rows} rows")
    """

    @property
    def n_rows(self) -> int:
        return self.data or 0

    # ── 工廠（覆寫以指定 data 型別）─────────────────────────

    @classmethod
    def success(  # type: ignore[override]
        cls, n_rows: int, *, source: str = "", message: str = "ok"
    ) -> CollectResult:
        return cls(
            ok=True, level="success", message=message, data=n_rows, source=source
        )

    @classmethod
    def warning(  # type: ignore[override]
        cls, message: str, n_rows: int = 0, *, source: str = ""
    ) -> CollectResult:
        return cls(
            ok=True, level="warning", message=message, data=n_rows, source=source
        )

    @classmethod
    def error(cls, message: str, *, source: str = "") -> CollectResult:  # type: ignore[override]
        return cls(ok=False, level="error", message=message, data=0, source=source)
