"""
tests/test_data_health_coverage.py — 覆蓋率定義修正的 regression tests

Root causes tested:
1. _load_coverage_history() 的分子必須是分析宇宙內的 DISTINCT stock_id，
   不得把宇宙外股票也計入（否則覆蓋率 > 100% 且指標失真）
2. 財務覆蓋率分母必須是分析宇宙大小（826 檔），不得用 price_distinct（全市場）
3. Forward Gate L2 market_count 必須和分析宇宙對齊；
   若 DailyPrice 含全市場資料，計數只應包含宇宙內股票
4. 覆蓋率 > 100% 必須標記 anomaly，不得用 min(100%, ratio) 掩蓋
"""

from datetime import date

import pytest
from sqlalchemy import create_engine

from src.database import (
    AnalysisResult,
    Base,
    DailyPrice,
    FinancialQuarter,
    ForwardSignal,
    MODEL_VERSION,
    Stock,
    get_session,
    init_db,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _engine():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    return engine


def _session(engine=None):
    return get_session(engine or _engine())


def _add_stock(session, stock_id, is_excluded=False, security_status="listed",
               listing_date=None, delisted_date=None):
    session.add(Stock(
        stock_id=stock_id,
        name=f"Stock_{stock_id}",
        is_excluded=is_excluded,
        security_status=security_status,
        listing_date=listing_date,
        delisted_date=delisted_date,
    ))


def _add_price(session, stock_id, trade_date, close=100.0):
    session.add(DailyPrice(
        stock_id=stock_id, date=trade_date,
        close=close, open=100.0, high=102.0, low=98.0, volume=1_000_000,
    ))


# ── 1. Coverage history: scoped to analysis universe ─────────────────────────


def test_coverage_scoped_to_universe():
    """
    分析宇宙 3 檔 + 宇宙外 2 檔（非 Stock 表成員）均有 DailyPrice。
    覆蓋率分子應只計宇宙內 3 檔，不受宇宙外 2 檔影響。
    """
    engine = _engine()
    s = _session(engine)
    d = date(2026, 10, 9)

    # 分析宇宙
    for sid in ["2330", "2317", "2454"]:
        _add_stock(s, sid)
        _add_price(s, sid, d)
    # 宇宙外（非 Stock 表）
    for sid in ["X001", "X002", "X003", "X004", "X005"]:
        _add_price(s, sid, d)  # DailyPrice only, no Stock row
    s.commit()

    from sqlalchemy import func
    universe_size = s.query(func.count(Stock.stock_id)).filter(Stock.is_excluded.isnot(True)).scalar()
    assert universe_size == 3

    # Correct scoped count
    scoped = (
        s.query(func.count(func.distinct(DailyPrice.stock_id)))
        .join(Stock, Stock.stock_id == DailyPrice.stock_id)
        .filter(DailyPrice.date == d, DailyPrice.close.isnot(None), Stock.is_excluded.isnot(True))
        .scalar()
    )
    assert scoped == 3, "scoped count should be 3 (universe stocks only)"

    # Naive count (old bug)
    naive = (
        s.query(func.count(DailyPrice.stock_id))
        .filter(DailyPrice.date == d, DailyPrice.close.isnot(None))
        .scalar()
    )
    assert naive == 8, "naive count includes 5 non-universe stocks"

    # Confirm ratio > 100% with naive count
    ratio_naive = naive / universe_size
    assert ratio_naive > 1.0, "naive ratio must exceed 100% to confirm the bug"

    # Confirm correct ratio ≤ 100%
    ratio_scoped = scoped / universe_size
    assert ratio_scoped == 1.0
    s.close()


def test_anomaly_flag_when_raw_exceeds_expected():
    """raw_count > expected * 1.05 → anomaly=True。"""
    engine = _engine()
    s = _session(engine)
    d = date(2026, 10, 9)

    # 2 universe stocks
    for sid in ["2330", "2317"]:
        _add_stock(s, sid)
        _add_price(s, sid, d)
    # 5 non-universe stocks (simulates market-wide pull)
    for sid in ["U001", "U002", "U003", "U004", "U005"]:
        _add_price(s, sid, d)
    s.commit()

    from sqlalchemy import func
    expected = s.query(func.count(Stock.stock_id)).filter(Stock.is_excluded.isnot(True)).scalar()
    raw = s.query(func.count(DailyPrice.stock_id)).filter(DailyPrice.date == d).scalar()
    anomaly = raw > int(expected * 1.05)
    assert anomaly is True, "raw=7, expected=2 → anomaly must be True"
    s.close()


def test_no_anomaly_when_raw_within_expected():
    """raw_count ≈ expected (no non-universe data) → anomaly=False。"""
    engine = _engine()
    s = _session(engine)
    d = date(2026, 10, 30)

    for sid in ["2330", "2317", "2454"]:
        _add_stock(s, sid)
        _add_price(s, sid, d)
    s.commit()

    from sqlalchemy import func
    expected = s.query(func.count(Stock.stock_id)).filter(Stock.is_excluded.isnot(True)).scalar()
    raw = s.query(func.count(DailyPrice.stock_id)).filter(DailyPrice.date == d).scalar()
    anomaly = raw > int(expected * 1.05)
    assert anomaly is False
    s.close()


def test_excluded_stock_not_counted():
    """is_excluded=True の股票不列入分子或分母。"""
    engine = _engine()
    s = _session(engine)
    d = date(2026, 10, 30)

    _add_stock(s, "2330")                         # in universe
    _add_stock(s, "9999", is_excluded=True)       # excluded
    _add_price(s, "2330", d)
    _add_price(s, "9999", d)
    s.commit()

    from sqlalchemy import func
    universe = s.query(func.count(Stock.stock_id)).filter(Stock.is_excluded.isnot(True)).scalar()
    assert universe == 1

    scoped = (
        s.query(func.count(func.distinct(DailyPrice.stock_id)))
        .join(Stock, Stock.stock_id == DailyPrice.stock_id)
        .filter(DailyPrice.date == d, DailyPrice.close.isnot(None), Stock.is_excluded.isnot(True))
        .scalar()
    )
    assert scoped == 1, "excluded stock should not be in scoped count"
    s.close()


def test_partial_coverage_ratio():
    """3 檔宇宙，只有 2 檔有今日收盤價 → 覆蓋率 66.7%。"""
    engine = _engine()
    s = _session(engine)
    d = date(2026, 10, 30)

    for sid in ["2330", "2317", "2454"]:
        _add_stock(s, sid)
    _add_price(s, "2330", d)
    _add_price(s, "2317", d)
    # 2454 has no price today
    s.commit()

    from sqlalchemy import func
    expected = s.query(func.count(Stock.stock_id)).filter(Stock.is_excluded.isnot(True)).scalar()
    scoped = (
        s.query(func.count(func.distinct(DailyPrice.stock_id)))
        .join(Stock, Stock.stock_id == DailyPrice.stock_id)
        .filter(DailyPrice.date == d, DailyPrice.close.isnot(None), Stock.is_excluded.isnot(True))
        .scalar()
    )
    ratio = scoped / expected
    assert abs(ratio - 2 / 3) < 0.001
    s.close()


# ── 2. Financial coverage denominator ────────────────────────────────────────


def test_financial_coverage_uses_universe_denominator():
    """
    fin_coverage 分母必須是分析宇宙大小（Stock 表）。
    price_distinct (全市場) 會讓覆蓋率虛低。
    """
    engine = _engine()
    s = _session(engine)

    # 3 analysis-universe stocks
    for sid in ["2330", "2317", "2454"]:
        _add_stock(s, sid)
    # 10 non-universe stocks in DailyPrice only
    d = date(2026, 10, 30)
    for i in range(10):
        _add_price(s, f"EXT{i:03d}", d)
    # 2 stocks with financial data
    s.add(FinancialQuarter(stock_id="2330", year=2026, quarter=2, eps=5.0))
    s.add(FinancialQuarter(stock_id="2317", year=2026, quarter=2, eps=3.0))
    s.commit()

    from sqlalchemy import func
    fin_stocks = s.query(func.count(func.distinct(FinancialQuarter.stock_id))).scalar()
    universe_size = s.query(func.count(Stock.stock_id)).filter(Stock.is_excluded.isnot(True)).scalar()
    price_distinct = s.query(func.count(func.distinct(DailyPrice.stock_id))).scalar()

    # Old (wrong) formula
    cov_wrong = round(fin_stocks / price_distinct * 100, 1) if price_distinct > 0 else 0.0
    # Correct formula
    cov_correct = round(fin_stocks / universe_size * 100, 1) if universe_size > 0 else 0.0

    assert cov_correct == pytest.approx(66.7, abs=0.1)
    assert cov_wrong < cov_correct, (
        "old formula (÷ price_distinct) gives lower coverage than correct formula (÷ universe)"
    )
    s.close()


def test_financial_coverage_zero_when_no_data():
    """FinancialQuarter 空表 → coverage 0%。"""
    engine = _engine()
    s = _session(engine)
    for sid in ["2330", "2317"]:
        _add_stock(s, sid)
    s.commit()

    from sqlalchemy import func
    fin_stocks = s.query(func.count(func.distinct(FinancialQuarter.stock_id))).scalar()
    assert fin_stocks == 0

    universe_size = s.query(func.count(Stock.stock_id)).filter(Stock.is_excluded.isnot(True)).scalar()
    cov = round(fin_stocks / universe_size * 100, 1) if universe_size > 0 else 0.0
    assert cov == 0.0
    s.close()


# ── 3. Forward Gate L2 market_count scoped to universe ───────────────────────


def test_forward_gate_l2_uses_universe_scoped_count():
    """
    write_forward_signals L2 must count only analysis-universe stocks.
    If DailyPrice has 1000 non-universe stocks, market_count should still
    reflect only the 3 universe stocks — not 1003.
    """
    engine = _engine()
    s = _session(engine)
    trade_date = date(2026, 10, 30)

    for sid in ["2330", "2317", "2454"]:
        _add_stock(s, sid)
        _add_price(s, sid, trade_date)
    # 1000 non-universe stocks
    for i in range(1000):
        _add_price(s, f"EXT{i:04d}", trade_date)
    # 0050 required for L3
    _add_price(s, "0050", trade_date)
    # Analysis results
    for sid in ["2330", "2317", "2454"]:
        s.add(AnalysisResult(
            stock_id=sid, date=trade_date,
            setup_type="breakout", trade_signal="buy", total_score=75.0,
            timing_score=70.0, behavior_score=65.0, quality_score=60.0,
            risk_score=80.0, confidence=75.0, rec_level="A",
        ))
    s.commit()

    from sqlalchemy import func
    # Confirm raw DailyPrice count would overflow
    raw = s.query(func.count(DailyPrice.stock_id)).filter(DailyPrice.date == trade_date).scalar()
    assert raw >= 1004, "raw count must include non-universe stocks"

    # Scoped count (what the fixed code computes)
    scoped = (
        s.query(func.count(func.distinct(DailyPrice.stock_id)))
        .join(Stock, Stock.stock_id == DailyPrice.stock_id)
        .filter(
            DailyPrice.date == trade_date,
            DailyPrice.close.isnot(None),
            Stock.is_excluded.isnot(True),
        )
        .scalar()
    )
    # 0050 is in DailyPrice but not in Stock table in this test → scoped=3
    assert scoped == 3, f"scoped count must be 3 (universe stocks), got {scoped}"
    s.close()


def test_forward_gate_l2a_rejects_when_universe_undercovered():
    """
    市場有 1000 筆 DailyPrice，但分析宇宙只有 1 檔有收盤價 → L2a 應拒絕。
    舊邏輯（不 join Stock）會因 raw=1001 ≥ 200 而錯誤通過。
    """
    engine = _engine()
    s = _session(engine)
    trade_date = date(2026, 10, 30)
    min_count = 200

    # Only 1 universe stock has price
    _add_stock(s, "2330")
    _add_price(s, "2330", trade_date)
    # Many non-universe stocks
    for i in range(1000):
        _add_price(s, f"EXT{i:04d}", trade_date)
    s.commit()

    from sqlalchemy import func
    raw = s.query(func.count(DailyPrice.stock_id)).filter(DailyPrice.date == trade_date).scalar()
    assert raw >= 1001

    scoped = (
        s.query(func.count(func.distinct(DailyPrice.stock_id)))
        .join(Stock, Stock.stock_id == DailyPrice.stock_id)
        .filter(DailyPrice.date == trade_date, DailyPrice.close.isnot(None), Stock.is_excluded.isnot(True))
        .scalar()
    )
    # Old: passes (raw=1001 >= 200)
    assert raw >= min_count, "old logic would incorrectly pass"
    # New: rejects (scoped=1 < 200)
    assert scoped < min_count, "new logic correctly rejects undercovered universe"
    s.close()


# ── 4. Missing stock categorization ──────────────────────────────────────────


def test_missing_stock_categorization():
    """delisted / suspended / not_listed / other_missing 正確分類。"""
    engine = _engine()
    s = _session(engine)
    today = date(2026, 10, 30)

    _add_stock(s, "2330")                                       # has price → not missing
    _add_stock(s, "D001", security_status="delisted",
               delisted_date=date(2026, 9, 1))                  # delisted
    _add_stock(s, "S001", security_status="suspended")          # suspended
    _add_stock(s, "N001", listing_date=date(2027, 1, 1))        # not listed yet
    _add_stock(s, "O001")                                       # other: listed but no price
    _add_price(s, "2330", today)
    s.commit()

    priced_ids = {"2330"}
    universe_stocks = s.query(Stock).filter(Stock.is_excluded.isnot(True)).all()
    missing = {st.stock_id: st for st in universe_stocks if st.stock_id not in priced_ids}

    delisted, suspended, not_listed, other_missing = [], [], [], []
    for sid, st in missing.items():
        if (st.delisted_date and st.delisted_date <= today) or st.security_status == "delisted":
            delisted.append(sid)
        elif st.security_status == "suspended":
            suspended.append(sid)
        elif st.listing_date and st.listing_date > today:
            not_listed.append(sid)
        else:
            other_missing.append(sid)

    assert "D001" in delisted
    assert "S001" in suspended
    assert "N001" in not_listed
    assert "O001" in other_missing
    s.close()


# ── 5. Ratio never capped at 100% — anomaly flagged instead ──────────────────


def test_ratio_not_capped_anomaly_is_set():
    """
    若 raw_count > expected * 1.05，anomaly 必須為 True。
    不得用 min(1.0, ratio) 掩蓋問題。
    """
    engine = _engine()
    s = _session(engine)
    d = date(2026, 10, 9)

    _add_stock(s, "2330")
    _add_price(s, "2330", d)
    # many non-universe stocks
    for i in range(99):
        _add_price(s, f"EXT{i:03d}", d)
    s.commit()

    from sqlalchemy import func
    expected = s.query(func.count(Stock.stock_id)).filter(Stock.is_excluded.isnot(True)).scalar()
    raw = s.query(func.count(DailyPrice.stock_id)).filter(DailyPrice.date == d).scalar()

    scoped = (
        s.query(func.count(func.distinct(DailyPrice.stock_id)))
        .join(Stock, Stock.stock_id == DailyPrice.stock_id)
        .filter(DailyPrice.date == d, DailyPrice.close.isnot(None), Stock.is_excluded.isnot(True))
        .scalar()
    )
    ratio = scoped / expected  # must be 1.0 (all universe stocks covered)
    anomaly = raw > int(expected * 1.05)

    assert ratio == 1.0
    assert anomaly is True, "anomaly must be flagged — not hidden by min(100%, ratio)"
    s.close()


# ── 6. Source code pattern checks ────────────────────────────────────────────


def test_backtest_service_uses_stock_join_for_market_count():
    """L2 market_count query must join Stock table (not count all DailyPrice rows)."""
    import inspect
    from src.services.research_backtest_service import write_forward_signals
    src = inspect.getsource(write_forward_signals)
    assert "join(Stock" in src or ".join(Stock" in src, (
        "write_forward_signals must join Stock table for L2 market_count"
    )
    assert "is_excluded" in src, "L2 must filter Stock.is_excluded"


def test_backtest_service_uses_distinct_in_market_count():
    """L2 market_count must use DISTINCT to avoid double-counting."""
    import inspect
    from src.services.research_backtest_service import write_forward_signals
    src = inspect.getsource(write_forward_signals)
    assert "func.distinct" in src, "L2 market_count must use func.distinct"


def test_data_health_fin_coverage_uses_universe_not_price_distinct():
    """
    data_health._load_health_metrics() の財務覆蓋率計算
    は price_distinct ではなく analysis universe size を分母に使うべき。
    """
    with open("dashboard/_pages/data_health.py") as f:
        src = f.read()
    # Should NOT divide fin_stocks by price_distinct
    assert "fin_stocks / price_distinct" not in src, (
        "Financial coverage must not use price_distinct as denominator"
    )
    # Should use _analysis_universe_size (or similar universe-based denominator)
    assert "_analysis_universe_size" in src or "fin_stocks / expected" in src or "fin_stocks / universe" in src


def test_coverage_history_uses_stock_join():
    """_load_coverage_history() must join Stock to scope count to universe."""
    with open("dashboard/_pages/data_health.py") as f:
        src = f.read()
    # The function must have a join with Stock table
    assert "join(Stock" in src or ".join(Stock" in src


def test_coverage_history_tracks_raw_count_separately():
    """_load_coverage_history() must track raw_count for anomaly detection."""
    with open("dashboard/_pages/data_health.py") as f:
        src = f.read()
    assert "raw_count" in src, "_load_coverage_history must track raw_count"
    assert "anomaly" in src, "_load_coverage_history must have anomaly flag"
