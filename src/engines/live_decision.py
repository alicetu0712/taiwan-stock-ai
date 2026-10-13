"""
live_decision.py — 盤中即時進場狀態判斷

設計原則：
  - AI 原始訊號（trade_signal / decision_code）永遠固定，不被盤中價格覆蓋
  - 盤中只判斷「現在這個價格能不能執行昨日的 BUY 計畫」
  - BUY ≠ Good Entry：前者是模型對 Setup 的評分，後者是現價的 R/R
  - 輸出為 LiveStatus，僅供 UI 顯示，不寫入 DB

狀態優先序（高 → 低）：
  CANCEL > STOP_WARNING > RAPID_DROP/WATCHING_LOW > IN_RANGE > ABOVE_RANGE > CHASING > BELOW_RANGE > NO_RANGE
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LiveStatus(str, Enum):
    IN_RANGE           = "in_range"           # 🟢 位於理想進場區（無急跌）
    ABOVE_RANGE        = "above_range"        # 🟡 超出進場區，不追價
    CHASING            = "chasing"            # 🟠 明顯追高，等回測
    BELOW_RANGE        = "below_range"        # ⚪ 低於進場區，等止穩
    RAPID_DROP         = "rapid_drop"         # 🟡 急跌暫緩，等待止跌確認
    WATCHING_LOW       = "watching_low"       # 🔵 急跌後反彈，觀察低點守穩
    ENTRY_RECONFIRMED  = "entry_reconfirmed"  # 🔄 急跌後回復進場區，轉強觀察訊號
    STOP_WARNING       = "stop_warning"       # 🔴 接近停損（距停損 < 2%）
    CANCEL             = "cancel"             # ❌ 跌破停損，訊號失效
    NO_RANGE           = "no_range"           # ⬜ 缺進場區間資料
    NON_BUY            = "non_buy"            # — 非 BUY 訊號，不適用


_STATUS_META = {
    LiveStatus.IN_RANGE:          {"icon": "🟢", "label": "可進場",       "color": "#00897b", "bg": "#e0f2f1"},
    LiveStatus.ABOVE_RANGE:       {"icon": "🟡", "label": "不追價",       "color": "#f57f17", "bg": "#fff8e1"},
    LiveStatus.CHASING:           {"icon": "🟠", "label": "明顯追高",     "color": "#e65100", "bg": "#fff3e0"},
    LiveStatus.BELOW_RANGE:       {"icon": "⚪", "label": "等止穩",       "color": "#78909c", "bg": "#eceff1"},
    LiveStatus.RAPID_DROP:        {"icon": "🟡", "label": "等待止跌確認", "color": "#f57f17", "bg": "#fff8e1"},
    LiveStatus.WATCHING_LOW:      {"icon": "🔵", "label": "觀察低點守穩", "color": "#1565c0", "bg": "#e3f2fd"},
    LiveStatus.ENTRY_RECONFIRMED: {"icon": "🔄", "label": "轉強觀察訊號", "color": "#558b2f", "bg": "#f1f8e9"},
    LiveStatus.STOP_WARNING:      {"icon": "🔴", "label": "接近停損",     "color": "#c62828", "bg": "#ffebee"},
    LiveStatus.CANCEL:            {"icon": "❌", "label": "訊號失效",     "color": "#b71c1c", "bg": "#ffcdd2"},
    LiveStatus.NO_RANGE:          {"icon": "⬜", "label": "無區間",       "color": "#9e9e9e", "bg": "#f5f5f5"},
    LiveStatus.NON_BUY:           {"icon": "—",  "label": "不適用",       "color": "#bdbdbd", "bg": "#fafafa"},
}

# 以今日盤中低點（quote.low）偵測急跌：低點較訊號價跌幅超過此值
# 用低點而非現價判斷，避免正常震盪誤觸（e.g. 現價在進場區但低點確實急跌過）
_INTRADAY_DROP_PCT  = -2.5
# 無低點資料時的 fallback：使用相同標準，缺資料不能放寬保護
_FALLBACK_DROP_PCT  = -2.5
# 急跌後反彈：較今日低點回升超過此值，視為止跌觀察（Stage 2）
_BOUNCE_CONFIRM_PCT  = 0.8
# 急跌後轉強：反彈超過此值 + 回到進場區，升為轉強觀察訊號（Stage 3）
_RECONFIRM_BOUNCE_PCT = 3.0
# 距停損多少 % 內觸發警示
_STOP_WARN_PCT      = 2.0
# 超出進場上限多少 % 視為明顯追高
_CHASE_PCT          = 3.0


@dataclass
class LiveDecision:
    status:           LiveStatus
    icon:             str
    label:            str
    color:            str
    bg:               str
    reason:           str
    current_price:    Optional[float]
    signal_price:     Optional[float]   # 訊號時的參考收盤價
    pct_from_signal:  Optional[float]   # 距訊號價的漲跌幅 %
    pct_from_entry:   Optional[float]   # 距進場中點的漲跌幅 %
    entry_low:        Optional[float]
    entry_high:       Optional[float]
    stop_price:       Optional[float]
    target1:          Optional[float]
    # 盤中動態欄位（急跌情境專用）
    intraday_low:     Optional[float] = field(default=None)   # 今日盤中觀察低點
    rr_current:       Optional[float] = field(default=None)   # 以現價計算的 R/R
    drop_pct:         Optional[float] = field(default=None)   # 現價 vs 訊號價 %（同 pct_from_signal，方便語意）
    bounce_pct:       Optional[float] = field(default=None)   # 現價 vs 今日低點 %
    plain_text:       str             = field(default="")     # 白話情境解釋


def evaluate_entry_status(
    current_price: Optional[float],
    rec: dict,
    intraday_low: Optional[float] = None,
) -> "LiveDecision":
    """
    依據當前股價與今日盤中低點，判斷是否符合 AI 訊號的進場條件。

    Args:
        current_price: 盤中最新價（None = 無報價）
        rec:           recommendation dict（來自 loaders，已經過 _sanitize_trading_plan）
        intraday_low:  今日盤中最低（quote.low），None 表示無資料

    Returns:
        LiveDecision
    """
    trade_signal = rec.get("trade_signal") or "wait"
    signal_price = rec.get("price")
    entry_low    = rec.get("entry_low")
    entry_high   = rec.get("entry_high")
    stop_price   = rec.get("stop_price")
    target1      = rec.get("target1")

    # ── 預計算動態指標 ────────────────────────────────────────────
    drop_pct: Optional[float] = None
    if current_price and signal_price and signal_price > 0:
        drop_pct = round((current_price - signal_price) / signal_price * 100, 2)

    # 今日盤中低點較訊號價的跌幅（偵測用），獨立於現價
    intraday_drop_pct: Optional[float] = None
    if intraday_low and signal_price and signal_price > 0:
        intraday_drop_pct = round((intraday_low - signal_price) / signal_price * 100, 2)

    bounce_pct: Optional[float] = None
    if current_price and intraday_low and intraday_low > 0 and current_price >= intraday_low:
        bounce_pct = round((current_price - intraday_low) / intraday_low * 100, 2)

    rr_current: Optional[float] = None
    if current_price and stop_price and target1 and current_price > stop_price:
        rr_current = round((target1 - current_price) / (current_price - stop_price), 2)

    # 判斷今天是否發生過急跌：優先用低點，無低點才 fallback 到現價
    _rapid_drop_triggered = (
        (intraday_drop_pct is not None and intraday_drop_pct <= _INTRADAY_DROP_PCT)
        or (intraday_drop_pct is None and drop_pct is not None and drop_pct <= _FALLBACK_DROP_PCT)
    )

    def _make(status: LiveStatus, reason: str, plain_text: str = "") -> LiveDecision:
        meta      = _STATUS_META[status]
        entry_mid = ((entry_low or 0) + (entry_high or 0)) / 2 if entry_low and entry_high else None
        pct_entry = (
            round((current_price - entry_mid) / entry_mid * 100, 2)
            if current_price and entry_mid and entry_mid > 0 else None
        )
        return LiveDecision(
            status=status, icon=meta["icon"], label=meta["label"],
            color=meta["color"], bg=meta["bg"], reason=reason,
            current_price=current_price, signal_price=signal_price,
            pct_from_signal=drop_pct, pct_from_entry=pct_entry,
            entry_low=entry_low, entry_high=entry_high,
            stop_price=stop_price, target1=target1,
            intraday_low=intraday_low,
            rr_current=rr_current,
            drop_pct=drop_pct,
            bounce_pct=bounce_pct,
            plain_text=plain_text,
        )

    # ── 非買進訊號不適用 ──────────────────────────────────────────
    if trade_signal not in ("strong_buy", "buy"):
        return _make(LiveStatus.NON_BUY, "AI 訊號為非買進，盤中監控不適用")

    if current_price is None:
        # 即使沒有現價，只要低點顯示急跌就要警示
        if _rapid_drop_triggered:
            ilow_str  = f"{intraday_low:.1f}" if intraday_low else "未知"
            show_drop = abs(intraday_drop_pct) if intraday_drop_pct is not None else 0
            return _make(LiveStatus.RAPID_DROP,
                         f"無即時成交，但盤中低點 {ilow_str} 顯示急跌約 {show_drop:.1f}%，暫緩進場")
        return _make(LiveStatus.NO_RANGE, "目前無即時成交報價，無法判斷")

    # ── 停損觸發（最高優先） ──────────────────────────────────────
    if stop_price and current_price <= stop_price:
        return _make(LiveStatus.CANCEL,
                     f"跌破停損 {stop_price:.1f}，AI 訊號失效，建議取消進場計畫")

    # ── 接近停損警示 ──────────────────────────────────────────────
    if stop_price and stop_price > 0:
        dist_pct = (current_price - stop_price) / stop_price * 100
        if dist_pct < _STOP_WARN_PCT:
            return _make(LiveStatus.STOP_WARNING,
                         f"距停損 {stop_price:.1f} 僅剩 {dist_pct:.1f}%，風險偏高")

    # ── 急跌情境偵測（優先於區間邏輯） ───────────────────────────
    if _rapid_drop_triggered:
        ilow_str    = f"{intraday_low:.1f}" if intraday_low else "今日低點"
        sig_str     = f"{signal_price:.1f}" if signal_price else "訊號價"
        # 顯示的跌幅：優先用低點跌幅，次用現價跌幅
        show_drop   = abs(intraday_drop_pct) if intraday_drop_pct is not None else (abs(drop_pct) if drop_pct is not None else 0)

        if bounce_pct is not None and bounce_pct >= _RECONFIRM_BOUNCE_PCT and entry_low and current_price >= entry_low:
            # Stage 3：反彈幅度足夠 + 回到進場區 → 轉強觀察訊號
            # 這是「觀察訊號」，不是直接進場確認；歷史驗證完成前不作為正式 BUY 依據
            plain = (
                f"急跌後大幅反彈（從低點 {ilow_str} 回升 {bounce_pct:.1f}%），"
                "股價已回到進場區間。"
                "此為轉強觀察訊號——進場條件改善，但今日仍發生過急跌，"
                "建議留意量能是否支撐、低點是否確立，不宜倉促追入。"
            )
            return _make(
                LiveStatus.ENTRY_RECONFIRMED,
                f"急跌後回到進場區（低點 +{bounce_pct:.1f}%），轉強觀察，非直接進場確認",
                plain_text=plain,
            )
        elif bounce_pct is not None and bounce_pct >= _BOUNCE_CONFIRM_PCT:
            plain = (
                f"急跌後出現反彈（從低點 {ilow_str} 回升 {bounce_pct:.1f}%）。"
                "今日低點能否守穩，是進場前的關鍵觀察點。"
                "守穩 → 觀察回升強度；再破今日低點 → 進場計畫暫停。"
            )
            return _make(
                LiveStatus.WATCHING_LOW,
                f"急跌後反彈（低點 +{bounce_pct:.1f}%），觀察低點 {ilow_str} 是否守穩",
                plain_text=plain,
            )
        else:
            plain = (
                f"今天股價從訊號價 {sig_str} 急跌約 {show_drop:.1f}%"
                + (f"（盤中低點 {ilow_str}）" if intraday_low else "")
                + "，模型昨日訊號仍然有效，但不宜在急跌過程中直接進場。"
                "等賣壓停止、低點止穩後，再重新評估。"
            )
            return _make(
                LiveStatus.RAPID_DROP,
                f"盤中急跌約 {show_drop:.1f}%（低點 {ilow_str}），暫緩進場，等待低點止穩",
                plain_text=plain,
            )

    # ── 無進場區間 fallback ───────────────────────────────────────
    if not entry_low or not entry_high:
        return _make(LiveStatus.NO_RANGE, "進場區間資料不完整，無法判斷")

    # ── 正常區間邏輯 ──────────────────────────────────────────────
    if entry_low <= current_price <= entry_high:
        return _make(LiveStatus.IN_RANGE,
                     f"位於理想進場區 {entry_low:.1f}–{entry_high:.1f}，可依計畫進場")

    if current_price > entry_high:
        pct_above = (current_price - entry_high) / entry_high * 100
        if pct_above >= _CHASE_PCT:
            return _make(LiveStatus.CHASING,
                         f"超出進場上限 {pct_above:.1f}%（>{_CHASE_PCT:.0f}%），明顯追高，等回測")
        return _make(LiveStatus.ABOVE_RANGE,
                     f"略超進場區上限 {entry_high:.1f}（{pct_above:.1f}%），不追價")

    pct_below = (entry_low - current_price) / entry_low * 100
    return _make(LiveStatus.BELOW_RANGE,
                 f"低於進場下限 {entry_low:.1f}（{pct_below:.1f}%），等待止穩確認")


def is_market_open() -> bool:
    """判斷台股是否在盤中（09:00–13:30 台灣時間，週一至週五）。"""
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
