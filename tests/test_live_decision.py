"""
test_live_decision.py — 盤中進場狀態機單元測試

覆蓋情境：
  1. 正常進場區間（無急跌）
  2. 急跌情境：有盤中低點資料
  3. 急跌情境：無盤中低點資料（fallback）
  4. 急跌情境：無即時成交但有低點（no current_price）
  5. ENTRY_RECONFIRMED：急跌後完整回復
  6. 停損觸發 / 接近停損警示
  7. 晶技（3042）真實案例重現

關鍵設計約束（測試即文件）：
  - 無盤中低點時，fallback 閾值必須與主邏輯一致（-2.5%），不能放寬
  - 報價不可靠（stale/無成交）時不應直接放行可進場
  - ENTRY_RECONFIRMED 是觀察訊號，不是正式 BUY 確認
  - RAPID_DROP / WATCHING_LOW / ENTRY_RECONFIRMED 都屬急跌衍生狀態
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.engines.live_decision import LiveStatus, evaluate_entry_status

# ── 共用測試 rec（以晶技 3042 真實數值為基礎） ─────────────────
_REC = {
    "trade_signal": "buy",
    "price":        204.5,   # 訊號價
    "entry_low":    193.9,
    "entry_high":   204.1,
    "stop_price":   165.1,
    "target1":      241.4,
}


# ─────────────────────────────────────────────────────────────────
# 正常情境：無急跌
# ─────────────────────────────────────────────────────────────────

def test_in_range_normal():
    """股價在進場區，低點正常（無急跌）→ IN_RANGE。"""
    ld = evaluate_entry_status(200.0, _REC, intraday_low=201.5)
    # intraday_drop_pct = (201.5-204.5)/204.5 = -1.5%，未達 -2.5% 閾值
    assert ld.status == LiveStatus.IN_RANGE


def test_above_range():
    ld = evaluate_entry_status(206.0, _REC, intraday_low=204.0)
    assert ld.status == LiveStatus.ABOVE_RANGE


def test_chasing():
    ld = evaluate_entry_status(212.0, _REC, intraday_low=208.0)
    # 超出進場上限 204.1 超過 3%
    assert ld.status == LiveStatus.CHASING


def test_below_range():
    ld = evaluate_entry_status(191.0, _REC, intraday_low=191.5)
    # 191.5 vs 204.5 → -6.4%，但 191.0 < entry_low 193.9
    # 急跌條件觸發（低點 -6.4%），但 bounce = (191-191.5)/191.5 < 0
    # → 仍在急跌中，應為 RAPID_DROP
    assert ld.status == LiveStatus.RAPID_DROP


def test_no_buy_signal():
    rec = dict(_REC, trade_signal="wait")
    ld = evaluate_entry_status(200.0, rec)
    assert ld.status == LiveStatus.NON_BUY


def test_no_price():
    """無報價且無低點 → NO_RANGE。"""
    ld = evaluate_entry_status(None, _REC, intraday_low=None)
    assert ld.status == LiveStatus.NO_RANGE


# ─────────────────────────────────────────────────────────────────
# 急跌情境：有盤中低點資料
# ─────────────────────────────────────────────────────────────────

def test_rapid_drop_with_low_no_bounce():
    """急跌，低點確認，尚未反彈 → RAPID_DROP。"""
    # signal=204.5, low=193.0 (-5.6%), current=194.0, bounce=(194-193)/193=0.5%
    ld = evaluate_entry_status(194.0, _REC, intraday_low=193.0)
    assert ld.status == LiveStatus.RAPID_DROP
    assert ld.drop_pct is not None and ld.drop_pct < -2.5
    assert ld.bounce_pct is not None and ld.bounce_pct < 0.8


def test_watching_low_bounce_partial():
    """急跌後輕微反彈（0.8%–3%）→ WATCHING_LOW。"""
    # 晶技 10:40 真實案例：signal=204.5, low=195, current=197.5
    # intraday_drop = (195-204.5)/204.5 = -4.6%，bounce = (197.5-195)/195 = 1.3%
    ld = evaluate_entry_status(197.5, _REC, intraday_low=195.0)
    assert ld.status == LiveStatus.WATCHING_LOW
    assert ld.bounce_pct is not None
    assert 0.8 <= ld.bounce_pct < 3.0


def test_watching_low_computes_rr():
    """WATCHING_LOW 應以現價計算 R/R，不用進場中點。"""
    ld = evaluate_entry_status(197.5, _REC, intraday_low=195.0)
    # R/R = (241.4-197.5) / (197.5-165.1)
    expected_rr = round((241.4 - 197.5) / (197.5 - 165.1), 2)
    assert ld.rr_current is not None
    assert abs(ld.rr_current - expected_rr) < 0.01


def test_entry_reconfirmed_full_recovery():
    """急跌後大幅反彈回進場區（bounce >= 3%）→ ENTRY_RECONFIRMED。"""
    # signal=204.5, low=195, current=204 → bounce=(204-195)/195=4.6%，且在進場區
    ld = evaluate_entry_status(204.0, _REC, intraday_low=195.0)
    assert ld.status == LiveStatus.ENTRY_RECONFIRMED
    assert ld.bounce_pct is not None and ld.bounce_pct >= 3.0
    assert ld.current_price >= _REC["entry_low"]


def test_entry_reconfirmed_not_triggered_below_entry():
    """反彈幅度夠但未回到進場區 → 仍為 WATCHING_LOW。"""
    # current=192 < entry_low=193.9，即使 bounce >= 3% 也不升為 RECONFIRMED
    # signal=204.5, low=185, current=192 → bounce=(192-185)/185=3.8%，但 192 < 193.9
    ld = evaluate_entry_status(192.0, _REC, intraday_low=185.0)
    assert ld.status == LiveStatus.WATCHING_LOW


# ─────────────────────────────────────────────────────────────────
# 關鍵回歸：無盤中低點時 fallback 閾值
# ─────────────────────────────────────────────────────────────────

def test_bug_regression_no_low_drop_3pct_should_not_be_in_range():
    """
    回歸測試：修正前（fallback=-4.0%），197.5（-3.4%）被誤判為 IN_RANGE。
    修正後（fallback=-2.5%），應為 RAPID_DROP。
    """
    ld = evaluate_entry_status(197.5, _REC, intraday_low=None)
    # drop_pct = (197.5-204.5)/204.5 = -3.42%，超過 -2.5% fallback 閾值
    assert ld.status == LiveStatus.RAPID_DROP, (
        f"期望 RAPID_DROP，實際 {ld.status}（drop_pct={ld.drop_pct}）。"
        "此為已知 bug 回歸測試，勿調整閾值讓測試通過。"
    )


def test_no_low_small_drop_stays_in_range():
    """跌幅 < 2.5%，無低點資料 → 正常進場區判斷（不誤觸 fallback）。"""
    # current=202, signal=204.5 → drop=-1.22%，未達 fallback 閾值
    ld = evaluate_entry_status(202.0, _REC, intraday_low=None)
    assert ld.status == LiveStatus.IN_RANGE


def test_no_low_large_drop_triggers_rapid():
    """跌幅 -5%，無低點資料 → fallback 觸發 RAPID_DROP。"""
    ld = evaluate_entry_status(194.3, _REC, intraday_low=None)
    assert ld.status == LiveStatus.RAPID_DROP


# ─────────────────────────────────────────────────────────────────
# 無即時成交但有低點
# ─────────────────────────────────────────────────────────────────

def test_no_current_price_with_drop_low():
    """無即時成交（best_price=None）但低點顯示急跌 → RAPID_DROP 警示。"""
    ld = evaluate_entry_status(None, _REC, intraday_low=195.0)
    assert ld.status == LiveStatus.RAPID_DROP
    assert "195" in ld.reason  # 應說明低點


def test_no_current_price_normal_low():
    """無即時成交，低點正常（無急跌）→ NO_RANGE。"""
    ld = evaluate_entry_status(None, _REC, intraday_low=202.0)
    # intraday_drop_pct = (202-204.5)/204.5 = -1.2%，未達閾值
    assert ld.status == LiveStatus.NO_RANGE


# ─────────────────────────────────────────────────────────────────
# 停損 / 接近停損
# ─────────────────────────────────────────────────────────────────

def test_cancel_at_stop():
    ld = evaluate_entry_status(165.1, _REC, intraday_low=164.0)
    assert ld.status == LiveStatus.CANCEL


def test_cancel_below_stop():
    ld = evaluate_entry_status(162.0, _REC, intraday_low=162.0)
    assert ld.status == LiveStatus.CANCEL


def test_stop_warning_near_stop():
    # distance = (167-165.1)/165.1 = 1.15%，< 2% → STOP_WARNING
    ld = evaluate_entry_status(167.0, _REC, intraday_low=165.5)
    assert ld.status == LiveStatus.STOP_WARNING


def test_stop_warning_takes_priority_over_rapid_drop():
    """接近停損的優先序高於急跌狀態。"""
    # 急跌（low=175, -14%），現價=167（接近停損）
    ld = evaluate_entry_status(167.0, _REC, intraday_low=175.0)
    assert ld.status == LiveStatus.STOP_WARNING


# ─────────────────────────────────────────────────────────────────
# R/R 計算
# ─────────────────────────────────────────────────────────────────

def test_rr_none_when_price_at_stop():
    ld = evaluate_entry_status(165.5, _REC)
    # 接近停損，R/R 可能很小但仍能計算
    # 但若 current <= stop，status=CANCEL，rr_current 計算前就返回
    ld2 = evaluate_entry_status(165.0, _REC)
    assert ld2.status == LiveStatus.CANCEL

def test_rr_computed_correctly_in_range():
    ld = evaluate_entry_status(200.0, _REC, intraday_low=201.0)
    expected = round((241.4 - 200.0) / (200.0 - 165.1), 2)
    assert ld.rr_current is not None
    assert abs(ld.rr_current - expected) < 0.01


# ─────────────────────────────────────────────────────────────────
# plain_text 生成
# ─────────────────────────────────────────────────────────────────

def test_plain_text_exists_for_drop_states():
    for price, low, expected_status in [
        (194.0, 193.0, LiveStatus.RAPID_DROP),
        (197.5, 195.0, LiveStatus.WATCHING_LOW),
        (204.0, 195.0, LiveStatus.ENTRY_RECONFIRMED),
    ]:
        ld = evaluate_entry_status(price, _REC, intraday_low=low)
        assert ld.status == expected_status
        assert len(ld.plain_text) > 20, f"{expected_status} 應有 plain_text"


def test_plain_text_empty_for_normal():
    ld = evaluate_entry_status(200.0, _REC, intraday_low=201.0)
    assert ld.plain_text == ""
