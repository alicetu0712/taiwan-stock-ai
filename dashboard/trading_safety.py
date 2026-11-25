"""
dashboard/trading_safety.py — Centralized Trading Safety Gate.

Determines whether it is safe to present trading recommendations based on:
  1. Data freshness (price data vs. expected latest trading day)
  2. Signal freshness (age of the most recent forward signal trade_date vs. expected)
  3. Coverage state (UNKNOWN until security_master is built — see coverage_policy design)

STATUS HIERARCHY (fail-closed; ordered most-to-least restrictive):
  PASS     All required conditions met. Currently unachievable: coverage is always UNKNOWN
           until security_master exists.  Included for forward compatibility.
  DEGRADED Coverage verified as degraded (90–98%). Currently unreachable.
           NOT equivalent to "coverage unknown."
  BLOCKED  Price data stale (>0 TD behind expected) OR signal stale (>0 TD behind expected).
  UNKNOWN  Cannot determine status: DB error, no data, missing inputs, or coverage
           state cannot be verified (includes "coverage unknown").

FRESHNESS POLICY (S78C.2):
  - price_lag > 0 TD  → BLOCKED (any price staleness prohibits current trade recs)
  - signal_lag > 0 TD → BLOCKED (signal must match the same expected trading date)
  - Both price and signal are compared to the same expected_latest_price_date.
  - Threshold calibration deferred to strategy research; this is the conservative default.
  - Coverage UNKNOWN → UNKNOWN (never promoted to DEGRADED; unverified ≠ degraded-but-ok).

DESIGN CONSTRAINTS:
- Pure computation module: no Streamlit calls, no mutations of forward_signals or
  recommendations, no inference of historical dates from API calls.
- Fail-closed: any unhandled exception returns UNKNOWN, never PASS.
- Uses TaiwanTradingCalendar for all trading-day calculations.
- Data publication lag: TWSE/TPEx publish ~2–3 h after close (13:30 Taiwan).
  Conservative cutoff: before 17:00 Taipei the previous trading day is the expected
  latest.  Callers may override via reference_time.
- Original signal values (BUY/STRONG_BUY) are NEVER modified.
"""

from __future__ import annotations

import zoneinfo
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional

_TAIPEI_TZ = zoneinfo.ZoneInfo("Asia/Taipei")

# Conservative data-publication cutoff (hour in Taipei time).
# Before this hour on a trading day → prior trading day is the expected latest.
_DATA_PUBLISH_HOUR = 17

# Legacy reference constant — no longer used as the active threshold.
# Active policy (S78C.2): signal_lag > 0 TD → BLOCKED.
MAX_SIGNAL_AGE_TRADING_DAYS = 5

# 1700 diagnostic floor (from coverage policy design — not a PASS threshold).
DIAGNOSTIC_FLOOR_NON_BENCHMARK = 1_700


class TradingGateStatus(str, Enum):
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class CoverageState(str, Enum):
    PASS = "PASS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FreshnessDetail:
    """Freshness information for display."""

    latest_price_date: Optional[date]  # max(daily_prices.date) in active DB
    expected_price_date: Optional[date]  # what we should have by reference_time
    price_lag_trading_days: int  # 0 = fresh, >0 = stale
    latest_signal_date: Optional[date]  # max(trade_date) in forward_signals
    signal_lag_trading_days: int  # trading days since last signal
    reference_datetime: Optional[datetime]  # time the check was computed
    data_source: str  # 'neon' | 'sqlite' | 'unknown'
    latest_successful_update: Optional[date]  # from execution_log if available


@dataclass(frozen=True)
class TradingGateResult:
    """
    Result of the Trading Safety Gate computation.

    Original signals (BUY/STRONG_BUY) are never modified.
    Use `is_actionable` to gate display of executable recommendations.
    Use `freshness` for display of the data freshness panel.
    """

    status: TradingGateStatus
    reasons: list = field(default_factory=list)  # human-readable reason codes
    freshness: Optional[FreshnessDetail] = None
    coverage: CoverageState = CoverageState.UNKNOWN
    diagnostic_floor_met: bool = False  # non_0050_count >= 1700

    @property
    def is_actionable(self) -> bool:
        """True only when PASS. Currently always False (coverage UNKNOWN)."""
        return self.status == TradingGateStatus.PASS

    @property
    def allow_research_display(self) -> bool:
        """Historical signals may always be shown for research; never suppressed."""
        return True

    @property
    def status_label_zh(self) -> str:
        labels = {
            TradingGateStatus.PASS: "資料完整，可參考交易建議",
            TradingGateStatus.DEGRADED: "資料部分可用，僅供研究",
            TradingGateStatus.BLOCKED: "資料尚未更新，暫停交易建議",
            TradingGateStatus.UNKNOWN: "無法確認資料狀態",
        }
        return labels.get(self.status, str(self.status))

    @property
    def reason_text_zh(self) -> str:
        code_map = {
            "PRICE_STALE": "股價資料未更新至預期交易日",
            "SIGNAL_STALE": "最新訊號未更新至預期交易日",
            "NO_PRICE_DATA": "無法取得股價資料",
            "NO_SIGNAL_DATA": "無法取得交易訊號",
            "COVERAGE_UNKNOWN": "市場涵蓋率尚未驗證（Security Master 建置中）",
            "DB_ERROR": "資料庫查詢失敗",
        }
        mapped = [code_map.get(r, r) for r in self.reasons]
        return "；".join(mapped) if mapped else ""


def _prev_trading_day(d: date, cal) -> date:
    """Return the latest trading day strictly before d."""
    candidate = d - timedelta(days=1)
    for _ in range(14):  # safety bound
        if cal.is_trading_day(candidate):
            return candidate
        candidate -= timedelta(days=1)
    return candidate


def _count_trading_days_between(start: date, end: date, cal) -> int:
    """
    Count trading days in (start, end] — i.e. the number of trading days
    strictly after start up to and including end.
    Returns 0 if start >= end.
    """
    if start >= end:
        return 0
    count = 0
    d = start + timedelta(days=1)
    while d <= end:
        if cal.is_trading_day(d):
            count += 1
        d += timedelta(days=1)
    return count


def expected_latest_price_date(reference_time: Optional[datetime] = None) -> date:
    """
    Latest trading date for which TWSE/TPEx price data should be available.

    Rules (Asia/Taipei):
    - If today is not a trading day → most recent past trading day.
    - If today is a trading day but reference_time.hour < _DATA_PUBLISH_HOUR (17:00)
      → previous trading day (data not yet published).
    - If today is a trading day and reference_time.hour >= _DATA_PUBLISH_HOUR
      → today.

    NOTE: Does NOT query any API.  Returns a conservative estimate only.
    """
    try:
        from src.core.trading_calendar import TaiwanTradingCalendar

        cal = TaiwanTradingCalendar()
    except Exception:
        # Fallback: simple weekday check
        now_taipei = reference_time or datetime.now(_TAIPEI_TZ)
        d = now_taipei.date()
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d

    if reference_time is None:
        reference_time = datetime.now(_TAIPEI_TZ)
    elif reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=_TAIPEI_TZ)

    today = reference_time.astimezone(_TAIPEI_TZ).date()
    hour = reference_time.astimezone(_TAIPEI_TZ).hour

    if cal.is_trading_day(today) and hour >= _DATA_PUBLISH_HOUR:
        return today
    return _prev_trading_day(today, cal)


def _query_freshness(conn) -> tuple:
    """
    Query price and signal dates from an open DB connection.
    Returns (max_price_date, max_signal_date, latest_success_date).
    All may be None on failure.
    """
    max_price = max_signal = latest_success = None
    try:
        row = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()
        if row and row[0]:
            max_price = date.fromisoformat(str(row[0])[:10])
    except Exception:
        pass

    try:
        row = conn.execute("SELECT MAX(trade_date) FROM forward_signals").fetchone()
        if row and row[0]:
            max_signal = date.fromisoformat(str(row[0])[:10])
    except Exception:
        # forward_signals may use a different column; try recommendations table
        try:
            row = conn.execute(
                "SELECT MAX(date) FROM recommendations WHERE trade_signal IN ('buy','strong_buy')"
            ).fetchone()
            if row and row[0]:
                max_signal = date.fromisoformat(str(row[0])[:10])
        except Exception:
            pass

    try:
        row = conn.execute(
            "SELECT MAX(date) FROM execution_log WHERE status='success'"
        ).fetchone()
        if row and row[0]:
            latest_success = date.fromisoformat(str(row[0])[:10])
    except Exception:
        pass

    return max_price, max_signal, latest_success


def compute_trading_gate(
    reference_time: Optional[datetime] = None,
    _test_max_price: Optional[date] = None,
    _test_max_signal: Optional[date] = None,
    _test_expected: Optional[date] = None,
    _test_non0050_count: Optional[int] = None,
) -> TradingGateResult:
    """
    Compute the centralized Trading Safety Gate result.

    Uses the active database (Neon or SQLite per config.DATABASE_URL).
    Test overrides (_test_*) allow isolated testing without a real DB.

    Returns TradingGateResult with UNKNOWN on any unhandled exception.
    """
    try:
        return _compute_gate_inner(
            reference_time=reference_time,
            _test_max_price=_test_max_price,
            _test_max_signal=_test_max_signal,
            _test_expected=_test_expected,
            _test_non0050_count=_test_non0050_count,
        )
    except Exception:
        return TradingGateResult(
            status=TradingGateStatus.UNKNOWN,
            reasons=["DB_ERROR"],
        )


def _compute_gate_inner(
    reference_time,
    _test_max_price,
    _test_max_signal,
    _test_expected,
    _test_non0050_count,
) -> TradingGateResult:
    try:
        from src.core.trading_calendar import TaiwanTradingCalendar

        cal = TaiwanTradingCalendar()
    except Exception:
        return TradingGateResult(
            status=TradingGateStatus.UNKNOWN,
            reasons=["DB_ERROR"],
        )

    if reference_time is None:
        reference_time = datetime.now(_TAIPEI_TZ)

    expected = _test_expected or expected_latest_price_date(reference_time)

    # ── DB queries (skipped when test overrides are provided) ──────────────
    max_price = _test_max_price
    max_signal = _test_max_signal
    latest_success = None
    data_source = "mock"
    non0050_count = _test_non0050_count

    if _test_max_price is None or _test_max_signal is None:
        try:
            import sqlite3

            from config import DB_PATH

            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            data_source = "sqlite"
            q_price, q_signal, q_success = _query_freshness(conn)
            if _test_max_price is None:
                max_price = q_price
            if _test_max_signal is None:
                max_signal = q_signal
            latest_success = q_success

            if non0050_count is None and expected is not None:
                try:
                    row = conn.execute(
                        "SELECT COUNT(DISTINCT stock_id) FROM daily_prices "
                        "WHERE date=? AND stock_id!='0050'",
                        (str(expected),),
                    ).fetchone()
                    non0050_count = row[0] if row else 0
                except Exception:
                    non0050_count = None
            conn.close()
        except Exception:
            # Try to continue with None values — may still produce UNKNOWN gracefully
            data_source = "unknown"

    # ── Price freshness ────────────────────────────────────────────────────
    reasons: list = []
    if max_price is None:
        price_lag = -1
        reasons.append("NO_PRICE_DATA")
    else:
        price_lag = _count_trading_days_between(max_price, expected, cal)

    # ── Signal freshness ───────────────────────────────────────────────────
    # Compare signal against the same expected date as price (S78C.2 policy).
    if max_signal is None:
        signal_lag = -1
        reasons.append("NO_SIGNAL_DATA")
    else:
        signal_lag = _count_trading_days_between(max_signal, expected, cal)

    # ── Coverage (always UNKNOWN until security_master built) ──────────────
    coverage = CoverageState.UNKNOWN
    reasons.append("COVERAGE_UNKNOWN")

    # ── Diagnostic floor ──────────────────────────────────────────────────
    diagnostic_floor_met = (
        non0050_count is not None and non0050_count >= DIAGNOSTIC_FLOOR_NON_BENCHMARK
    )

    # ── Freshness detail ──────────────────────────────────────────────────
    freshness = FreshnessDetail(
        latest_price_date=max_price,
        expected_price_date=expected,
        price_lag_trading_days=max(price_lag, 0),
        latest_signal_date=max_signal,
        signal_lag_trading_days=max(signal_lag, 0),
        reference_datetime=reference_time,
        data_source=data_source,
        latest_successful_update=latest_success,
    )

    # ── Status determination (fail-closed) ────────────────────────────────
    # BLOCKED conditions (highest priority):
    if max_price is None or price_lag < 0:
        return TradingGateResult(
            status=TradingGateStatus.UNKNOWN,
            reasons=reasons,
            freshness=freshness,
            coverage=coverage,
            diagnostic_floor_met=diagnostic_floor_met,
        )

    # S78C.2 policy: any price staleness vs. expected date → BLOCKED
    if price_lag > 0:
        reasons.append("PRICE_STALE")

    # S78C.2 policy: signal must match the same expected date as price
    if max_signal is None or signal_lag < 0:
        pass  # NO_SIGNAL_DATA already appended above
    elif signal_lag > 0:
        reasons.append("SIGNAL_STALE")

    blocked_reasons = {"PRICE_STALE", "SIGNAL_STALE", "NO_PRICE_DATA", "NO_SIGNAL_DATA"}
    if any(r in blocked_reasons for r in reasons):
        return TradingGateResult(
            status=TradingGateStatus.BLOCKED,
            reasons=reasons,
            freshness=freshness,
            coverage=coverage,
            diagnostic_floor_met=diagnostic_floor_met,
        )

    # Coverage UNKNOWN → UNKNOWN (not DEGRADED; unverified ≠ degraded-but-ok).
    # DEGRADED is reserved for "coverage verified as 90-98%", which requires
    # security_master to exist. Until then, all non-BLOCKED results are UNKNOWN.
    if coverage == CoverageState.UNKNOWN:
        return TradingGateResult(
            status=TradingGateStatus.UNKNOWN,
            reasons=reasons,
            freshness=freshness,
            coverage=coverage,
            diagnostic_floor_met=diagnostic_floor_met,
        )

    # DEGRADED: price fresh, signal recent, coverage verified as partial
    return TradingGateResult(
        status=TradingGateStatus.DEGRADED,
        reasons=reasons,
        freshness=freshness,
        coverage=coverage,
        diagnostic_floor_met=diagnostic_floor_met,
    )
