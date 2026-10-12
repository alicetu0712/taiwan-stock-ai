"""
live_decision.py — 盤中即時進場狀態判斷

設計原則：
  - AI 原始訊號（trade_signal / decision_code）永遠固定，不被盤中價格覆蓋
  - 盤中只判斷「現在這個價格能不能執行昨日的 BUY 計畫」
  - 輸出為 LiveStatus，僅供 UI 顯示，不寫入 DB

狀態優先序（高 → 低）：
  CANCEL    > STOP_WARNING > IN_RANGE > ABOVE_RANGE > CHASING > BELOW_RANGE > NO_RANGE
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class LiveStatus(str, Enum):
    IN_RANGE      = "in_range"       # 🟢 位於理想進場區
    ABOVE_RANGE   = "above_range"    # 🟡 超出進場區，不追價
    CHASING       = "chasing"        # 🟠 明顯追高，等回測
    BELOW_RANGE   = "below_range"    # ⚪ 低於進場區，等止穩
    STOP_WARNING  = "stop_warning"   # 🔴 接近停損（距停損 < 2%）
    CANCEL        = "cancel"         # ❌ 跌破停損，訊號失效
    NO_RANGE      = "no_range"       # ⬜ 缺進場區間資料
    NON_BUY       = "non_buy"        # — 非 BUY 訊號，不適用


_STATUS_META = {
    LiveStatus.IN_RANGE:     {"icon": "🟢", "label": "可進場",   "color": "#00897b", "bg": "#e0f2f1"},
    LiveStatus.ABOVE_RANGE:  {"icon": "🟡", "label": "不追價",   "color": "#f57f17", "bg": "#fff8e1"},
    LiveStatus.CHASING:      {"icon": "🟠", "label": "明顯追高", "color": "#e65100", "bg": "#fff3e0"},
    LiveStatus.BELOW_RANGE:  {"icon": "⚪", "label": "等止穩",   "color": "#78909c", "bg": "#eceff1"},
    LiveStatus.STOP_WARNING: {"icon": "🔴", "label": "接近停損", "color": "#c62828", "bg": "#ffebee"},
    LiveStatus.CANCEL:       {"icon": "❌", "label": "訊號失效", "color": "#b71c1c", "bg": "#ffcdd2"},
    LiveStatus.NO_RANGE:     {"icon": "⬜", "label": "無區間",   "color": "#9e9e9e", "bg": "#f5f5f5"},
    LiveStatus.NON_BUY:      {"icon": "—",  "label": "不適用",   "color": "#bdbdbd", "bg": "#fafafa"},
}

# 超出進場上限多少 % 視為「明顯追高」
_CHASE_PCT = 3.0
# 距停損多少 % 內觸發警示
_STOP_WARN_PCT = 2.0


@dataclass
class LiveDecision:
    status:          LiveStatus
    icon:            str
    label:           str
    color:           str
    bg:              str
    reason:          str
    current_price:   Optional[float]
    signal_price:    Optional[float]   # 訊號時的參考收盤價
    pct_from_signal: Optional[float]   # 距訊號價的漲跌幅 %
    pct_from_entry:  Optional[float]   # 距進場中點的漲跌幅 %
    entry_low:       Optional[float]
    entry_high:      Optional[float]
    stop_price:      Optional[float]
    target1:         Optional[float]


def evaluate_entry_status(
    current_price: Optional[float],
    rec: dict,
) -> LiveDecision:
    """
    依據當前股價判斷是否符合 AI 訊號的進場條件。

    Args:
        current_price: 盤中最新價（None = 無報價）
        rec:           recommendation dict（來自 loaders，已經過 _sanitize_trading_plan）

    Returns:
        LiveDecision
    """
    trade_signal = rec.get("trade_signal") or "wait"
    signal_price = rec.get("price")          # 訊號時的收盤參考價
    entry_low    = rec.get("entry_low")
    entry_high   = rec.get("entry_high")
    stop_price   = rec.get("stop_price")
    target1      = rec.get("target1")

    def _make(status: LiveStatus, reason: str) -> LiveDecision:
        meta = _STATUS_META[status]
        pct_signal = (
            round((current_price - signal_price) / signal_price * 100, 2)
            if current_price and signal_price and signal_price > 0 else None
        )
        entry_mid = ((entry_low or 0) + (entry_high or 0)) / 2 if entry_low and entry_high else None
        pct_entry = (
            round((current_price - entry_mid) / entry_mid * 100, 2)
            if current_price and entry_mid and entry_mid > 0 else None
        )
        return LiveDecision(
            status=status, icon=meta["icon"], label=meta["label"],
            color=meta["color"], bg=meta["bg"], reason=reason,
            current_price=current_price, signal_price=signal_price,
            pct_from_signal=pct_signal, pct_from_entry=pct_entry,
            entry_low=entry_low, entry_high=entry_high,
            stop_price=stop_price, target1=target1,
        )

    # 非買進訊號不適用
    if trade_signal not in ("strong_buy", "buy"):
        return _make(LiveStatus.NON_BUY, "AI 訊號為非買進，盤中監控不適用")

    if current_price is None:
        return _make(LiveStatus.NO_RANGE, "目前無報價")

    # 停損觸發
    if stop_price and current_price <= stop_price:
        return _make(LiveStatus.CANCEL,
                     f"跌破停損 {stop_price:.1f}，AI 訊號失效，建議取消進場計畫")

    # 接近停損警示
    if stop_price and stop_price > 0:
        dist_pct = (current_price - stop_price) / stop_price * 100
        if dist_pct < _STOP_WARN_PCT:
            return _make(LiveStatus.STOP_WARNING,
                         f"距停損 {stop_price:.1f} 僅剩 {dist_pct:.1f}%，風險偏高")

    # 無進場區間 fallback
    if not entry_low or not entry_high:
        return _make(LiveStatus.NO_RANGE, "進場區間資料不完整，無法判斷")

    # 在理想進場區
    if entry_low <= current_price <= entry_high:
        return _make(LiveStatus.IN_RANGE,
                     f"位於理想進場區 {entry_low:.1f}–{entry_high:.1f}，可依計畫進場")

    # 超出進場上限
    if current_price > entry_high:
        pct_above = (current_price - entry_high) / entry_high * 100
        if pct_above >= _CHASE_PCT:
            return _make(LiveStatus.CHASING,
                         f"超出進場上限 {pct_above:.1f}%（>{_CHASE_PCT:.0f}%），明顯追高，等回測")
        return _make(LiveStatus.ABOVE_RANGE,
                     f"略超進場區上限 {entry_high:.1f}（{pct_above:.1f}%），不追價")

    # 低於進場下限
    pct_below = (entry_low - current_price) / entry_low * 100
    return _make(LiveStatus.BELOW_RANGE,
                 f"低於進場下限 {entry_low:.1f}（{pct_below:.1f}%），等待止穩確認")


def is_market_open() -> bool:
    """
    判斷台股是否在盤中（09:00–13:30 台灣時間，週一至週五）。
    """
    from datetime import datetime
    import zoneinfo
    tz  = zoneinfo.ZoneInfo("Asia/Taipei")
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return False
    t = now.time()
    from datetime import time as _t
    return _t(9, 0) <= t <= _t(13, 30)


def market_session_label() -> str:
    from datetime import datetime
    import zoneinfo
    tz  = zoneinfo.ZoneInfo("Asia/Taipei")
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return "休市（週末）"
    from datetime import time as _t
    t = now.time()
    if t < _t(9, 0):
        return "盤前"
    if t <= _t(13, 30):
        return "盤中"
    return "已收盤"
