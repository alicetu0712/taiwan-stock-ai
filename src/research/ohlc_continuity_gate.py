"""
ohlc_continuity_gate.py — OHLC Historical Continuity Gate

Checks whether the last N expected trading days (per TaiwanTradingCalendar)
have actual price data in the local SQLite DB.

Purpose: Prevent MA20/MA60 calculations from silently using data from
non-consecutive trading days when market data has gaps, which corrupts
MA values and produces misleading signals.

DESIGN NOTE ON CALENDAR DISCREPANCIES (e.g. 2026-10-09):
  TaiwanTradingCalendar lists date(2026, 10, 9) as 國慶日補假.
  However the DB contains 7,586 stocks + 0050 data for that date,
  proving the exchange DID trade. The calendar entry is a suspected error.
  Such dates are classified UNKNOWN — they do NOT block the gate since
  empirical data confirms the market was open. Missing expected dates
  (calendar says trading day, DB has no data) DO block.

Gate results:
  PASS                        All required expected trading days have data
  BLOCKED_MISSING_OHLC        One or more expected trading days lack market data
  BLOCKED_INSUFFICIENT_HISTORY Fewer than MIN_HIST_BARS stock closes in DB
  BLOCKED_STALE_DATA          Last available date exceeds stale tolerance
  UNKNOWN_CALENDAR            All present but calendar discrepancies detected
  NOT_APPLICABLE              Trade date is not a trading day per calendar
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from src.core.trading_calendar import TaiwanTradingCalendar

# ── Constants ─────────────────────────────────────────────────────────────────

MA20_BARS = 20
MA20_SLOPE_EXTRA_BARS = 10          # MA20_SLOPE_BARS from effectiveness_analyzer
TOTAL_SLOPE_BARS = 30               # MA20 + slope lookback = 20 + 10
REGIME_BARS = 30                    # 0050 regime window (see _regime_on_date)
CONTINUITY_WINDOW = 30              # max(TOTAL_SLOPE_BARS, REGIME_BARS)
MIN_HIST_BARS = 70                  # minimum total closes required
STALE_TOLERANCE_DAYS = 7            # max calendar days between last_data_date and trade_date


# ── Enums ─────────────────────────────────────────────────────────────────────

class DateStatus(str, Enum):
    DATA_AVAILABLE        = "DATA_AVAILABLE"
    MARKET_CLOSED         = "MARKET_CLOSED"           # weekend or confirmed holiday (no data)
    EXPECTED_DATA_MISSING = "EXPECTED_DATA_MISSING"   # expected td, no data in DB
    UNKNOWN               = "UNKNOWN"                  # calendar says holiday but data exists


class GateResult(str, Enum):
    PASS                        = "PASS"
    BLOCKED_MISSING_OHLC        = "BLOCKED_MISSING_OHLC"
    BLOCKED_INSUFFICIENT_HISTORY = "BLOCKED_INSUFFICIENT_HISTORY"
    BLOCKED_STALE_DATA          = "BLOCKED_STALE_DATA"
    UNKNOWN_CALENDAR            = "UNKNOWN_CALENDAR"  # warning only — no block
    NOT_APPLICABLE              = "NOT_APPLICABLE"


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class MissingSession:
    date: date
    status: DateStatus


@dataclass
class FeatureAudit:
    feature_name: str
    required_lookback_bars: int
    available_bars: int
    missing_expected_sessions: int
    unknown_sessions: int
    first_available_date: Optional[date]
    last_available_date: Optional[date]
    gate_result: GateResult


@dataclass
class MarketContinuityReport:
    trade_date: date
    gate_result: GateResult
    continuity_window: int
    present_sessions: int
    missing_sessions: int
    unknown_sessions: int
    missing_dates: List[date]
    unknown_dates: List[date]
    checked_at: datetime
    feature_audits: List[FeatureAudit] = field(default_factory=list)


@dataclass
class StockContinuityReport:
    stock_id: str
    trade_date: date
    gate_result: GateResult
    market_open_dates_checked: int
    stock_present: int
    stock_missing: int
    first_available_date: Optional[date]
    last_available_date: Optional[date]
    total_bars_in_db: int


# ── Gate ──────────────────────────────────────────────────────────────────────

class OHLCContinuityGate:
    """
    Validates OHLC continuity for Hybrid Forward Shadow decisions.

    Usage:
        gate = OHLCContinuityGate()
        market = gate.check_market(conn, date(2026, 11, 5))
        if market.gate_result != GateResult.PASS:
            # block all decisions for this date
    """

    def __init__(self, calendar: Optional[TaiwanTradingCalendar] = None):
        self._cal = calendar or TaiwanTradingCalendar()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_expected_trading_days(self, trade_date: date, n: int) -> List[date]:
        """Return the last n expected trading days ending on trade_date (inclusive).
        Sorted chronologically (oldest first).
        """
        result: List[date] = []
        d = trade_date
        while len(result) < n:
            if self._cal.is_trading_day(d):
                result.append(d)
            d -= timedelta(days=1)
            if d < date(2020, 1, 1):
                break
        result.reverse()
        return result

    def _get_dates_with_data(
        self, conn: sqlite3.Connection, stock_id: str, start: date, end: date
    ) -> Set[date]:
        rows = conn.execute(
            "SELECT DISTINCT date FROM daily_prices WHERE stock_id=? AND date >= ? AND date <= ?",
            (stock_id, str(start), str(end)),
        ).fetchall()
        return {date.fromisoformat(r[0]) for r in rows}

    def _classify_date(self, d: date, has_0050_data: bool) -> DateStatus:
        """Classify one date using calendar + 0050 DB state."""
        is_expected_td = self._cal.is_trading_day(d)
        if is_expected_td:
            return DateStatus.DATA_AVAILABLE if has_0050_data else DateStatus.EXPECTED_DATA_MISSING
        # Calendar says not a trading day
        if has_0050_data:
            return DateStatus.UNKNOWN  # empirical data contradicts calendar
        return DateStatus.MARKET_CLOSED

    def _build_feature_audit(
        self,
        feature_name: str,
        required_bars: int,
        expected_days: List[date],
        db_dates: Set[date],
    ) -> FeatureAudit:
        window = expected_days[-required_bars:] if len(expected_days) >= required_bars else expected_days
        present = [d for d in window if d in db_dates]
        missing_count = sum(
            1 for d in window
            if d not in db_dates and self._cal.is_trading_day(d)
        )
        unknown_count = sum(
            1 for d in window
            if d not in db_dates and not self._cal.is_trading_day(d)
            # (This path shouldn't trigger since window comes from expected_tds)
        )
        result = GateResult.PASS if missing_count == 0 else GateResult.BLOCKED_MISSING_OHLC
        return FeatureAudit(
            feature_name=feature_name,
            required_lookback_bars=required_bars,
            available_bars=len(present),
            missing_expected_sessions=missing_count,
            unknown_sessions=unknown_count,
            first_available_date=min(present) if present else None,
            last_available_date=max(present) if present else None,
            gate_result=result,
        )

    # ── Market-level gate ─────────────────────────────────────────────────────

    def check_market(
        self, conn: sqlite3.Connection, trade_date: date
    ) -> MarketContinuityReport:
        """
        Market-level gate: check 0050 continuity in the CONTINUITY_WINDOW.

        Returns PASS only if ALL expected trading days (per TaiwanTradingCalendar)
        in the last CONTINUITY_WINDOW (30) days have 0050 data.

        UNKNOWN days (calendar error, data present) do not block.
        """
        now = datetime.now(timezone.utc)

        if not self._cal.is_trading_day(trade_date):
            return MarketContinuityReport(
                trade_date=trade_date,
                gate_result=GateResult.NOT_APPLICABLE,
                continuity_window=CONTINUITY_WINDOW,
                present_sessions=0,
                missing_sessions=0,
                unknown_sessions=0,
                missing_dates=[],
                unknown_dates=[],
                checked_at=now,
            )

        # Stale data check
        last_data = self._last_0050_date(conn)
        if last_data is None or (trade_date - last_data).days > STALE_TOLERANCE_DAYS:
            return MarketContinuityReport(
                trade_date=trade_date,
                gate_result=GateResult.BLOCKED_STALE_DATA,
                continuity_window=CONTINUITY_WINDOW,
                present_sessions=0 if last_data is None else 1,
                missing_sessions=0,
                unknown_sessions=0,
                missing_dates=[],
                unknown_dates=[],
                checked_at=now,
            )

        expected = self._get_expected_trading_days(trade_date, CONTINUITY_WINDOW)
        if not expected:
            return MarketContinuityReport(
                trade_date=trade_date,
                gate_result=GateResult.BLOCKED_INSUFFICIENT_HISTORY,
                continuity_window=CONTINUITY_WINDOW,
                present_sessions=0,
                missing_sessions=0,
                unknown_sessions=0,
                missing_dates=[],
                unknown_dates=[],
                checked_at=now,
            )

        start = expected[0]
        # Also check a wider window for UNKNOWN detection (calendar days before expected window)
        # Include some calendar-holiday days to detect unknowns
        wider_start = start - timedelta(days=10)
        db_dates_0050 = self._get_dates_with_data(conn, "0050", wider_start, trade_date)

        present_sessions = 0
        missing_dates: List[date] = []
        unknown_dates: List[date] = []

        for d in expected:
            has_data = d in db_dates_0050
            status = self._classify_date(d, has_data)
            if status == DateStatus.DATA_AVAILABLE:
                present_sessions += 1
            elif status == DateStatus.EXPECTED_DATA_MISSING:
                missing_dates.append(d)
            # UNKNOWN can't happen for expected (calendar says td, so is_trading_day=True)
            # but check anyway for robustness

        # Also scan for UNKNOWN dates (calendar=holiday, DB=present) in the window range
        # These are dates NOT in expected but have 0050 data
        expected_set = set(expected)
        for db_d in sorted(db_dates_0050):
            if db_d < start or db_d > trade_date:
                continue
            if db_d not in expected_set and not self._cal.is_trading_day(db_d):
                unknown_dates.append(db_d)

        missing_count = len(missing_dates)
        unknown_count = len(unknown_dates)

        # Feature audits
        feature_audits = [
            self._build_feature_audit("MA20", MA20_BARS, expected, db_dates_0050),
            self._build_feature_audit("MA20_SLOPE", TOTAL_SLOPE_BARS, expected, db_dates_0050),
            self._build_feature_audit("REGIME_MA30", REGIME_BARS, expected, db_dates_0050),
        ]

        if missing_count > 0:
            gate = GateResult.BLOCKED_MISSING_OHLC
        elif unknown_count > 0:
            gate = GateResult.UNKNOWN_CALENDAR
        else:
            gate = GateResult.PASS

        return MarketContinuityReport(
            trade_date=trade_date,
            gate_result=gate,
            continuity_window=len(expected),
            present_sessions=present_sessions,
            missing_sessions=missing_count,
            unknown_sessions=unknown_count,
            missing_dates=sorted(missing_dates),
            unknown_dates=sorted(unknown_dates),
            checked_at=now,
            feature_audits=feature_audits,
        )

    # ── Stock-level gate ──────────────────────────────────────────────────────

    def check_stock(
        self,
        conn: sqlite3.Connection,
        stock_id: str,
        trade_date: date,
        market_open_dates: Optional[List[date]] = None,
    ) -> StockContinuityReport:
        """
        Stock-level gate: given the last MA20_BARS dates where 0050 had data
        (up to trade_date), does this stock also have data on all of them?

        market_open_dates: pre-computed list of dates where 0050 had data
                           (optimization to avoid re-querying 0050 for each stock).
        """
        if market_open_dates is None:
            # Build the last MA20_BARS dates with 0050 data
            rows = conn.execute(
                "SELECT DISTINCT date FROM daily_prices WHERE stock_id='0050' AND date <= ? "
                "ORDER BY date DESC LIMIT ?",
                (str(trade_date), MA20_BARS),
            ).fetchall()
            market_open_dates = [date.fromisoformat(r[0]) for r in rows]

        if not market_open_dates:
            return StockContinuityReport(
                stock_id=stock_id,
                trade_date=trade_date,
                gate_result=GateResult.BLOCKED_STALE_DATA,
                market_open_dates_checked=0,
                stock_present=0,
                stock_missing=0,
                first_available_date=None,
                last_available_date=None,
                total_bars_in_db=0,
            )

        start = min(market_open_dates)
        end = max(market_open_dates)
        stock_dates = self._get_dates_with_data(conn, stock_id, start, end)

        present = [d for d in market_open_dates if d in stock_dates]
        missing = [d for d in market_open_dates if d not in stock_dates]

        total_bars = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE stock_id=? AND date <= ?",
            (stock_id, str(trade_date)),
        ).fetchone()[0]

        if total_bars < MIN_HIST_BARS:
            gate = GateResult.BLOCKED_INSUFFICIENT_HISTORY
        elif missing:
            gate = GateResult.BLOCKED_MISSING_OHLC
        else:
            gate = GateResult.PASS

        return StockContinuityReport(
            stock_id=stock_id,
            trade_date=trade_date,
            gate_result=gate,
            market_open_dates_checked=len(market_open_dates),
            stock_present=len(present),
            stock_missing=len(missing),
            first_available_date=min(stock_dates) if stock_dates else None,
            last_available_date=max(stock_dates) if stock_dates else None,
            total_bars_in_db=total_bars,
        )

    # ── Combined check ────────────────────────────────────────────────────────

    def check_all(
        self, conn: sqlite3.Connection, stocks: List[str], trade_date: date
    ) -> Tuple[MarketContinuityReport, Dict[str, StockContinuityReport]]:
        """
        Check market gate first; if blocked, return NOT_APPLICABLE for all stocks.
        Returns (market_report, {stock_id: StockContinuityReport}).
        """
        market = self.check_market(conn, trade_date)
        if market.gate_result in (
            GateResult.BLOCKED_MISSING_OHLC,
            GateResult.BLOCKED_STALE_DATA,
            GateResult.NOT_APPLICABLE,
        ):
            # No point checking individual stocks — market is blocked
            stock_reports: Dict[str, StockContinuityReport] = {}
            for sid in stocks:
                stock_reports[sid] = StockContinuityReport(
                    stock_id=sid,
                    trade_date=trade_date,
                    gate_result=GateResult.NOT_APPLICABLE,
                    market_open_dates_checked=0,
                    stock_present=0,
                    stock_missing=0,
                    first_available_date=None,
                    last_available_date=None,
                    total_bars_in_db=0,
                )
            return market, stock_reports

        # Build market_open_dates once for efficiency
        rows = conn.execute(
            "SELECT DISTINCT date FROM daily_prices WHERE stock_id='0050' AND date <= ? "
            "ORDER BY date DESC LIMIT ?",
            (str(trade_date), MA20_BARS),
        ).fetchall()
        market_open_dates = [date.fromisoformat(r[0]) for r in rows]

        stock_reports = {
            sid: self.check_stock(conn, sid, trade_date, market_open_dates)
            for sid in stocks
        }
        return market, stock_reports

    # ── Summary helpers ───────────────────────────────────────────────────────

    def summarize_stocks(
        self, stock_reports: Dict[str, StockContinuityReport]
    ) -> dict:
        """Return a count summary of stock-level gate results."""
        pass_count = sum(1 for r in stock_reports.values() if r.gate_result == GateResult.PASS)
        blocked_ohlc = sum(1 for r in stock_reports.values() if r.gate_result == GateResult.BLOCKED_MISSING_OHLC)
        blocked_hist = sum(1 for r in stock_reports.values() if r.gate_result == GateResult.BLOCKED_INSUFFICIENT_HISTORY)
        na_count = sum(1 for r in stock_reports.values() if r.gate_result == GateResult.NOT_APPLICABLE)
        return {
            "total": len(stock_reports),
            "pass": pass_count,
            "blocked_missing_ohlc": blocked_ohlc,
            "blocked_insufficient_history": blocked_hist,
            "not_applicable": na_count,
        }

    # ── Utility ───────────────────────────────────────────────────────────────

    def _last_0050_date(self, conn: sqlite3.Connection) -> Optional[date]:
        row = conn.execute(
            "SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'"
        ).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None
