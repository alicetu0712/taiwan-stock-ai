"""
actual_position_service.py — ACTUAL 持倉輔助服務（唯讀）

此模組只做計算與查詢，不寫入資料（寫入全透過 trade_service）。
重用 daily_prices 表取得最新可用股價；不建立額外行情抓取流程。
"""

from datetime import date
from decimal import Decimal

_STALE_THRESHOLD_DAYS = 5  # 超過此天數視為股價資料過期（含週末）


def get_latest_price(session, stock_id: str):
    """
    從 daily_prices 取得指定股票最新收盤價。
    回傳 (close: float | None, price_date: date | None, age_days: int | None)

    age_days 為 None 表示完全無資料。
    age_days > _STALE_THRESHOLD_DAYS 表示資料可能過期，呼叫方應警示。
    """
    from src.database import DailyPrice

    row = (
        session.query(DailyPrice)
        .filter_by(stock_id=stock_id)
        .order_by(DailyPrice.date.desc())
        .first()
    )
    if row is None:
        return None, None, None
    age = (date.today() - row.date).days
    return row.close, row.date, age


def calc_unrealized_pnl(
    avg_cost_per_share: Decimal,
    remaining_shares: int,
    current_price: float,
) -> Decimal:
    """
    未實現損益 = (current_price − avg_cost_per_share) × remaining_shares
    """
    if remaining_shares <= 0:
        return Decimal("0")
    cp = Decimal(str(current_price))
    return (cp - avg_cost_per_share) * remaining_shares


def enrich_positions(session, positions) -> list:
    """
    給定 ActualPosition list，加入最新股價、未實現損益與資料新鮮度。
    回傳 list of dict（純 Python 型別，可供 st.cache_data 序列化）。

    price_stale=True：age_days > _STALE_THRESHOLD_DAYS，
      此時 unrealized_pnl 僅供參考，不應視為即時市值。
    price_stale=None：完全無資料。
    """
    result = []
    for pos in positions:
        price, price_date, age_days = get_latest_price(session, pos.stock_id)

        unrealized_pnl = None
        unrealized_pct = None
        if price is not None and pos.remaining_shares > 0:
            raw_pnl = calc_unrealized_pnl(
                pos.avg_cost_per_share, pos.remaining_shares, price
            )
            unrealized_pnl = float(raw_pnl)
            avg = float(pos.avg_cost_per_share)
            if avg > 0:
                unrealized_pct = (price - avg) / avg * 100

        # None = no data at all; True/False = data exists, stale or fresh
        if age_days is None:
            price_stale = None
        else:
            price_stale = age_days > _STALE_THRESHOLD_DAYS

        result.append(
            {
                # identity
                "id": pos.id,
                "stock_id": pos.stock_id,
                "stock_name": pos.stock_name or pos.stock_id,
                "signal_source": pos.signal_source,
                "forward_signal_id": pos.forward_signal_id,
                "original_plan_snapshot": pos.original_plan_snapshot,
                # lifecycle
                "status": pos.status,
                "open_date": str(pos.open_date) if pos.open_date else None,
                "close_date": str(pos.close_date) if pos.close_date else None,
                # cost & shares
                "remaining_shares": pos.remaining_shares,
                "avg_cost": float(pos.avg_cost_per_share),
                "total_cost_basis": float(pos.total_cost_basis),
                "realized_pnl": float(pos.realized_pnl),
                # plan
                "target_price": float(pos.target_price) if pos.target_price else None,
                "stop_price": float(pos.stop_price) if pos.stop_price else None,
                "notes": pos.notes or "",
                # market data
                "current_price": price,
                "price_date": str(price_date) if price_date else None,
                "price_age_days": age_days,
                "price_stale": price_stale,
                # P&L
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pct": unrealized_pct,
            }
        )
    return result
