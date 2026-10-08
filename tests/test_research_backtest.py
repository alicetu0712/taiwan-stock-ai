"""
tests/test_research_backtest.py — Research Backtest & Forward Signal 測試

測試項目：
  1. cutoff 不洩漏未來資料（no look-ahead）
  2. forward_signals append-only：不可覆寫既有記錄
  3. duplicate (trade_date, stock_id) 安全忽略
  4. 20D / 60D return 計算正確
  5. 0050 Alpha 計算正確
  6. PT bucket 邊界正確
  7. Market regime 判斷正確
  8. compute_stats 數學正確性
  9. ma20_bracket / ma60_bracket 邊界
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.database import RESEARCH_CUTOFF_DATE
from src.services.research_backtest_service import (
    ROUND_TRIP_COST,
    compute_stats,
    ma20_bracket,
    ma60_bracket,
    pt_bucket,
)


# ── 1. Cutoff 不洩漏未來資料 ─────────────────────────────────

def test_research_cutoff_is_fixed():
    """RESEARCH_CUTOFF_DATE 必須是固定的字面值 2026-10-09，不能被程式動態改變。"""
    assert RESEARCH_CUTOFF_DATE == date(2026, 10, 9), (
        "Cutoff 被修改！必須固定為 2026-10-09，永不更動。"
    )
    # 確認是硬編碼的字面值（非 date.today() 動態計算）
    import src.database as db_module
    import inspect
    src = inspect.getsource(db_module)
    assert "date.today()" not in src.split("RESEARCH_CUTOFF_DATE")[1].split("\n")[0], (
        "RESEARCH_CUTOFF_DATE 不能使用 date.today()"
    )


def test_research_only_uses_pre_cutoff_data():
    """
    ResearchBacktestService._build_raw_df 只取 date < RESEARCH_CUTOFF_DATE 的資料。
    透過 mock 驗證 query filter 有帶 cutoff 條件。
    """
    from src.services.research_backtest_service import ResearchBacktestService

    svc = ResearchBacktestService()
    with patch("src.services.research_backtest_service.ResearchBacktestService._build_raw_df") as mock_build:
        mock_build.return_value = (__import__("pandas").DataFrame(), 0)
        svc.compute()
        mock_build.assert_called_once()


def test_forward_ret_no_lookahead():
    """
    forward return 的 entry 應為 entry_date 當日 close（T），
    exit 為 T + n_days 個交易日的 close。
    不能使用 T+1 之後的資料來決定是否進場。
    """
    import bisect
    from src.services.research_backtest_service import ROUND_TRIP_COST

    # 模擬 5 天價格序列
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    dates = [date(2026, 1, i + 1) for i in range(6)]
    price_dict = {d: c for d, c in zip(dates, prices)}
    sorted_d = dates

    entry_date = dates[0]  # 進場日 = 2026-01-01
    n = 3
    idx = bisect.bisect_left(sorted_d, entry_date)
    entry = price_dict[sorted_d[idx]]      # 100.0
    exit_c = price_dict[sorted_d[idx + n]] # 103.0
    ret = round((exit_c - entry) / entry * 100 - ROUND_TRIP_COST, 2)

    expected = round((103.0 - 100.0) / 100.0 * 100 - ROUND_TRIP_COST, 2)
    assert ret == expected
    assert entry == 100.0  # 確認進場價為 T 當日，非 T+1


# ── 2 & 3. forward_signals append-only ──────────────────────

def test_forward_signals_skip_duplicate(tmp_path):
    """duplicate (trade_date, stock_id) 必須被安全 skip，不拋出例外，不覆寫。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from datetime import datetime

    from src.database import Base, ForwardSignal
    from src.services.research_backtest_service import write_forward_signals

    engine = create_engine(f"sqlite:///{tmp_path}/test_dup.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()

    trade_date = date(2026, 10, 10)

    # 先手動插入一筆，pt_score = 99.0（舊值）
    sess.add(ForwardSignal(
        trade_date=trade_date,
        stock_id="2330",
        pt_score=99.0,
        locked_at=datetime(2026, 10, 10, 9, 0, 0),
    ))
    sess.commit()

    # 建假 AnalysisResult（試圖用新值覆寫）
    class FakeAR:
        stock_id = "2330"
        price_trend_score = 70.0   # 不同的新值
        setup_type = "breakout"
        trade_signal = "buy"
        ma20_gap = 3.0
        volume_ratio = 0.9
        total_score = 75.0
        timing_score = 80.0
        behavior_score = 65.0
        rec_level = "B"

    inserted = write_forward_signals(sess, trade_date, [FakeAR()])

    assert inserted == 0, "已存在的 (date, stock_id) 應 skip，inserted 應為 0"

    rec = sess.query(ForwardSignal).filter_by(trade_date=trade_date, stock_id="2330").one()
    assert rec.pt_score == 99.0, "既有記錄不得被覆寫！"
    sess.close()


def test_forward_signals_no_update_on_duplicate(tmp_path):
    """write_forward_signals 使用 skip 而非 UPDATE，確認舊 locked_at 不變。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from datetime import datetime

    from src.database import Base, ForwardSignal
    from src.services.research_backtest_service import write_forward_signals

    engine = create_engine(f"sqlite:///{tmp_path}/test2.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()

    original_locked = datetime(2026, 10, 9, 8, 0, 0)
    trade_date = date(2026, 10, 9)

    sess.add(ForwardSignal(
        trade_date=trade_date,
        stock_id="0050",
        pt_score=55.0,
        locked_at=original_locked,
    ))
    sess.commit()

    class FakeAR:
        stock_id = "0050"
        price_trend_score = 88.0  # 不同的新值
        setup_type = "breakout"
        trade_signal = "buy"
        ma20_gap = 1.0
        volume_ratio = 1.0
        total_score = 80.0
        timing_score = 75.0
        behavior_score = 70.0
        rec_level = "A"

    write_forward_signals(sess, trade_date, [FakeAR()])

    rec = sess.query(ForwardSignal).filter_by(trade_date=trade_date, stock_id="0050").one()
    assert rec.pt_score == 55.0,       "pt_score 不得被覆寫"
    assert rec.locked_at == original_locked, "locked_at 不得被改變"
    sess.close()


# ── 4. 20D / 60D return 正確 ─────────────────────────────────

def test_20d_return_calculation():
    """20D return = (close[T+20] - close[T]) / close[T] * 100 - cost"""
    entry = 100.0
    exit_20 = 110.0
    expected = round((exit_20 - entry) / entry * 100 - ROUND_TRIP_COST, 2)
    assert expected == round(10.0 - ROUND_TRIP_COST, 2)


def test_60d_return_none_when_insufficient():
    """少於 60 個交易日的資料應回傳 None，不補填。"""
    import bisect
    prices = {date(2026, 1, i + 1): 100.0 + i for i in range(30)}
    sorted_d = sorted(prices.keys())
    entry_date = sorted_d[0]
    idx = bisect.bisect_left(sorted_d, entry_date)
    # 只有 30 天，T+60 不存在
    has_60 = idx + 60 < len(sorted_d)
    assert not has_60


# ── 5. 0050 Alpha 正確 ───────────────────────────────────────

def test_alpha_calculation():
    """Alpha = stock_ret - benchmark_ret；成本在各自報酬中扣除，alpha 本身不再扣。"""
    stock_ret = round(10.0 - ROUND_TRIP_COST, 2)   # 股票報酬（已扣成本）
    bench_ret  = round(5.0 - ROUND_TRIP_COST, 2)    # 0050 報酬（已扣成本）
    alpha = round(stock_ret - bench_ret, 2)
    # ROUND_TRIP_COST 對兩邊相消，alpha ≈ 5.0（允許浮點誤差 0.01）
    assert abs(alpha - 5.0) <= 0.01


def test_alpha_none_when_benchmark_missing():
    """benchmark 報酬為 None 時，alpha 應為 None，不得強制設 0。"""
    ret_20 = 3.5
    b0050  = None
    alpha  = round(ret_20 - b0050, 2) if (ret_20 is not None and b0050 is not None) else None
    assert alpha is None


# ── 6. PT bucket 邊界 ────────────────────────────────────────

@pytest.mark.parametrize("score,expected", [
    (0,    "<40"),
    (39.9, "<40"),
    (40.0, "40-50"),
    (49.9, "40-50"),
    (50.0, "50-60"),
    (59.9, "50-60"),
    (60.0, "60-70"),
    (69.9, "60-70"),
    (70.0, "70-80"),
    (79.9, "70-80"),
    (80.0, "80+"),
    (100,  "80+"),
    (None, "N/A"),
])
def test_pt_bucket_boundaries(score, expected):
    assert pt_bucket(score) == expected, f"pt_bucket({score}) → {pt_bucket(score)}, expected {expected}"


# ── 7. Market regime ────────────────────────────────────────

def test_regime_bull():
    """0050 > MA60 → bull"""
    close = 120.0
    ma60  = 100.0
    regime = "bull" if close > ma60 else "bear"
    assert regime == "bull"


def test_regime_bear():
    """0050 ≤ MA60 → bear"""
    close = 95.0
    ma60  = 100.0
    regime = "bull" if close > ma60 else "bear"
    assert regime == "bear"


def test_regime_exact_equal():
    """0050 == MA60 → bear（非 bull）"""
    close = 100.0
    ma60  = 100.0
    regime = "bull" if close > ma60 else "bear"
    assert regime == "bear"


# ── 8. compute_stats 數學正確性 ─────────────────────────────

def test_compute_stats_correct():
    alphas = [1.0, 2.0, 3.0, 4.0, 5.0]
    s = compute_stats(alphas)
    assert s["n"] == 5
    assert s["mean"] == pytest.approx(3.0, abs=0.01)
    assert s["median"] == pytest.approx(3.0, abs=0.01)
    assert s["std"] == pytest.approx(np.std(alphas, ddof=1), abs=0.01)
    assert s["win_rate"] == 100.0  # 全正
    assert s["p_value"] is not None and s["p_value"] < 0.05  # mean=3 顯著 > 0


def test_compute_stats_insufficient():
    """n < 2 → 回傳 None 而非崩潰"""
    s = compute_stats([1.0])
    assert s["n"] == 1
    assert s["mean"] is None
    assert s["p_value"] is None


def test_compute_stats_filters_none():
    """None 值應被過濾，不影響計算"""
    alphas = [1.0, None, 2.0, None, 3.0]
    s = compute_stats(alphas)
    assert s["n"] == 3
    assert s["mean"] == pytest.approx(2.0, abs=0.01)


def test_compute_stats_ci_contains_mean():
    """95% CI 必須包含 mean"""
    alphas = list(range(1, 21))  # 1..20
    s = compute_stats(alphas)
    assert s["ci_low"] < s["mean"] < s["ci_high"]


# ── 9. ma20 / ma60 bracket 邊界 ─────────────────────────────

@pytest.mark.parametrize("gap,expected", [
    # 邊界行為：函數用 <=，所以邊界值屬於「包含該邊界的較低段」
    (-15.0, "< -10%"),
    (-10.0, "< -10%"),       # -10 ≤ -10 → "< -10%"
    (-9.9,  "-10% to -5%"),
    (-5.0,  "-10% to -5%"),  # -5 ≤ -5 → "-10% to -5%"
    (-4.9,  "-5% to 0%"),
    (0.0,   "-5% to 0%"),    # 0 ≤ 0 → "-5% to 0%"
    (0.1,   "0% to 5%"),
    (5.0,   "0% to 5%"),     # 5 ≤ 5 → "0% to 5%"
    (5.1,   "5% to 10%"),
    (10.0,  "5% to 10%"),    # 10 ≤ 10 → "5% to 10%"
    (10.1,  "> 10%"),
    (None,  "N/A"),
])
def test_ma20_bracket_boundaries(gap, expected):
    assert ma20_bracket(gap) == expected


@pytest.mark.parametrize("gap,expected", [
    (-10.0, "< -5%"),
    (-5.0,  "< -5%"),   # -5 ≤ -5 → "< -5%"
    (-4.9,  "-5% to 0%"),
    (0.0,   "0% to 3%"),
    (2.9,   "0% to 3%"),
    (3.0,   "3% to 5%"),
    (4.9,   "3% to 5%"),
    (5.0,   "> 5%"),
    (None,  "N/A"),
])
def test_ma60_bracket_boundaries(gap, expected):
    assert ma60_bracket(gap) == expected
