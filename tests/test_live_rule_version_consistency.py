"""
tests/test_live_rule_version_consistency.py — LIVE_RULE_VERSION Single Source of Truth

保護：
  1. from src.engines.live_decision import LIVE_RULE_VERSION 必須成功（不 ImportError）
  2. live_execution_service.LIVE_RULE_VERSION 與 canonical 相同（top-level import 正確）
  3. record_if_transition() 執行時不發生 ImportError
  4. 寫入 LiveExecutionEvent 的 live_rule_version 等於 canonical 值
  5. Background Service 執行時使用的版本與 canonical 一致

Root cause history：
  原始 bug：record_if_transition() 內有 lazy import `from src.engines.live_decision import
  LIVE_RULE_VERSION`。Streamlit 的 sys.modules 快取了無此名稱的舊版 live_decision 模組，
  導致每次呼叫 record_if_transition() 時 ImportError。
  修正：改為 live_execution_service.py 頂層 `from src.engines.live_decision import LIVE_RULE_VERSION`。
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import Base, LiveExecutionEvent
from src.engines.live_decision import LiveDecision, LiveStatus, _STATUS_META


# ── Helpers ───────────────────────────────────────────────────────────────────

STOCK = "3042"
SDATE = date(2026, 10, 13)

_REC = {
    "price": 204.5,
    "entry_low": 193.9,
    "entry_high": 204.1,
    "stop_price": 165.1,
    "target1": 241.4,
}


def _make_ld(status: LiveStatus) -> LiveDecision:
    meta = _STATUS_META[status]
    return LiveDecision(
        status=status, icon=meta["icon"], label=meta["label"],
        color=meta["color"], bg=meta["bg"], reason="test",
        current_price=200.0, signal_price=204.5,
        pct_from_signal=-2.2, pct_from_entry=None,
        entry_low=193.9, entry_high=204.1,
        stop_price=165.1, target1=241.4,
        intraday_low=199.0, rr_current=1.5,
        drop_pct=-1.0, bounce_pct=0.0, plain_text="",
    )


@pytest.fixture
def patched_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def _sess(engine=None):
        return factory()

    with patch("src.database.get_session", side_effect=_sess):
        yield factory


# ─────────────────────────────────────────────────────────────────────────────
# 1. Import 一致性
# ─────────────────────────────────────────────────────────────────────────────

class TestImportConsistency:

    def test_canonical_import_succeeds(self):
        """from src.engines.live_decision import LIVE_RULE_VERSION 必須成功。"""
        try:
            from src.engines.live_decision import LIVE_RULE_VERSION
        except ImportError as e:
            pytest.fail(f"ImportError from canonical source: {e}")
        assert isinstance(LIVE_RULE_VERSION, str)
        assert len(LIVE_RULE_VERSION) > 0

    def test_service_exports_live_rule_version(self):
        """live_execution_service 必須 re-export LIVE_RULE_VERSION（top-level import）。"""
        try:
            from src.services.live_execution_service import LIVE_RULE_VERSION
        except ImportError as e:
            pytest.fail(f"ImportError from service: {e}")

    def test_service_version_equals_canonical(self):
        """live_execution_service.LIVE_RULE_VERSION 必須與 live_decision 的值相同。"""
        from src.engines.live_decision import LIVE_RULE_VERSION as canonical
        from src.services.live_execution_service import LIVE_RULE_VERSION as from_service
        assert from_service == canonical, (
            f"Version mismatch: live_decision={canonical!r}, "
            f"live_execution_service={from_service!r}"
        )

    def test_no_hardcoded_duplicate_in_service(self):
        """live_execution_service.py 不應再有獨立的 hardcoded LIVE_RULE_VERSION 字串定義。
        驗證方法：直接讀 source，確認沒有 'LIVE_RULE_VERSION = ' 賦值行。"""
        import inspect
        import src.services.live_execution_service as svc
        src_text = inspect.getsource(svc)
        # The only way LIVE_RULE_VERSION appears should be via the import line
        # not as an assignment like `LIVE_RULE_VERSION = "v1.0"`
        assignment_lines = [
            line.strip() for line in src_text.splitlines()
            if line.strip().startswith("LIVE_RULE_VERSION =")
        ]
        assert len(assignment_lines) == 0, (
            f"Found hardcoded LIVE_RULE_VERSION in live_execution_service: {assignment_lines}"
        )

    def test_version_value_matches_db(self):
        """canonical LIVE_RULE_VERSION 必須與 DB 中已存在的值相容（v1.0）。"""
        from src.engines.live_decision import LIVE_RULE_VERSION
        assert LIVE_RULE_VERSION == "v1.0", (
            f"Version changed from v1.0 to {LIVE_RULE_VERSION!r} — "
            "DB already contains v1.0 records; changing breaks existing data"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. record_if_transition() — 無 ImportError
# ─────────────────────────────────────────────────────────────────────────────

class TestRecordIfTransitionNoImportError:

    def test_no_import_error_on_call(self, patched_db):
        """record_if_transition() 必須能執行，不得因 LIVE_RULE_VERSION ImportError 失敗。"""
        from src.services.live_execution_service import record_if_transition
        try:
            result = record_if_transition(
                stock_id=STOCK, signal_date=SDATE,
                ld=_make_ld(LiveStatus.IN_RANGE), rec=_REC,
                quote_trade_date="20261013", quote_quality="valid",
            )
        except ImportError as e:
            pytest.fail(f"record_if_transition() raised ImportError: {e}")
        assert result is True

    def test_written_live_rule_version_is_canonical(self, patched_db):
        """寫入 LiveExecutionEvent 的 live_rule_version 必須等於 canonical LIVE_RULE_VERSION。"""
        from src.engines.live_decision import LIVE_RULE_VERSION
        from src.services.live_execution_service import record_if_transition

        record_if_transition(
            stock_id=STOCK, signal_date=SDATE,
            ld=_make_ld(LiveStatus.IN_RANGE), rec=_REC,
            quote_trade_date="20261013", quote_quality="valid",
        )

        s = patched_db()
        row = (
            s.query(LiveExecutionEvent)
            .filter(LiveExecutionEvent.stock_id == STOCK)
            .first()
        )
        s.close()

        assert row is not None, "record_if_transition() wrote nothing"
        assert row.live_rule_version == LIVE_RULE_VERSION, (
            f"DB live_rule_version={row.live_rule_version!r} != canonical={LIVE_RULE_VERSION!r}"
        )

    def test_no_import_error_on_multiple_calls(self, patched_db):
        """連續呼叫多次也不應有 ImportError（非第一次呼叫時 sys.modules 快取測試）。"""
        from src.services.live_execution_service import record_if_transition

        statuses = [LiveStatus.IN_RANGE, LiveStatus.ABOVE_RANGE, LiveStatus.STOP_WARNING]
        for status in statuses:
            try:
                record_if_transition(
                    stock_id=STOCK, signal_date=SDATE,
                    ld=_make_ld(status), rec=_REC,
                    quote_trade_date="20261013", quote_quality="valid",
                )
            except ImportError as e:
                pytest.fail(f"ImportError on call with {status}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Background Collector 版本一致性
# ─────────────────────────────────────────────────────────────────────────────

class TestBackgroundServiceVersionConsistency:

    def test_background_service_imports_live_execution_service(self):
        """live_background_service 透過 live_execution_service 間接使用 canonical 版本。"""
        import src.services.live_background_service as bg
        # Background service 不直接使用 LIVE_RULE_VERSION；
        # 透過 record_if_transition 間接使用，此 test 確認 import chain 無問題。
        assert hasattr(bg, "run_once")
        assert hasattr(bg, "record_if_transition") is False  # 正確：只在 run_once 內部 import

    def test_import_chain_live_decision_to_background(self):
        """完整 import chain 無 ImportError：live_decision → live_execution_service → 可調用。"""
        try:
            from src.engines.live_decision import LIVE_RULE_VERSION, evaluate_entry_status
            from src.services.live_execution_service import record_if_transition
        except ImportError as e:
            pytest.fail(f"Import chain broken: {e}")
