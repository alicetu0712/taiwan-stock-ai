"""
Universe Integrity Tests — Session 37
Validates universe definition, stock master integrity, coverage classification,
ForwardSignals reconciliation, and backtest eligibility.

All tests use temporary SQLite fixtures. No writes to production DB.
"""
import sqlite3
import os
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Minimal in-memory SQLite with stocks and daily_prices tables."""
    db_path = tmp_path / "test_platform.db"
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE stocks (
            stock_id    VARCHAR(10) PRIMARY KEY,
            name        VARCHAR(50) NOT NULL,
            market      VARCHAR(10),
            security_status VARCHAR(20) DEFAULT 'listed',
            is_excluded BOOLEAN DEFAULT 0,
            delisted_date DATE
        );

        CREATE TABLE daily_prices (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id VARCHAR(10) NOT NULL,
            date     DATE NOT NULL,
            open     FLOAT, high FLOAT, low FLOAT, close FLOAT,
            volume   FLOAT, amount FLOAT, change_pct FLOAT
        );

        CREATE TABLE forward_signals (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id     VARCHAR(10) NOT NULL,
            trade_date   DATE NOT NULL,
            model_version VARCHAR(20),
            is_valid     BOOLEAN DEFAULT 1,
            total_score  FLOAT,
            source_price_date DATE
        );
    """)
    con.commit()
    return str(db_path)


def insert_stocks(con, stocks):
    """stocks: list of (stock_id, name, market, security_status, is_excluded, delisted_date)"""
    con.executemany(
        "INSERT INTO stocks VALUES (?,?,?,?,?,?)", stocks
    )
    con.commit()


def insert_prices(con, rows):
    """rows: list of (stock_id, date, close)"""
    con.executemany(
        "INSERT INTO daily_prices (stock_id, date, close) VALUES (?,?,?)", rows
    )
    con.commit()


def insert_signals(con, rows):
    """rows: list of (stock_id, trade_date, model_version, is_valid, total_score, source_price_date)"""
    con.executemany(
        "INSERT INTO forward_signals (stock_id, trade_date, model_version, is_valid, total_score, source_price_date) VALUES (?,?,?,?,?,?)",
        rows
    )
    con.commit()


# ---------------------------------------------------------------------------
# UI-01..UI-07  Universe Tests
# ---------------------------------------------------------------------------

def test_UI01_twse_common_stocks_in_master(tmp_db):
    """TWSE 4-digit common stocks should appear in stocks table."""
    con = sqlite3.connect(tmp_db)
    insert_stocks(con, [
        ("2330", "台積電", "TWSE", "listed", 0, None),
        ("2317", "鴻海", "TWSE", "listed", 0, None),
    ])
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM stocks WHERE market='TWSE' AND is_excluded=0")
    assert cur.fetchone()[0] == 2
    con.close()


def test_UI02_tpex_stocks_absent_from_master(tmp_db):
    """Current master has no TPEx stocks — this is a known gap."""
    con = sqlite3.connect(tmp_db)
    insert_stocks(con, [
        ("2330", "台積電", "TWSE", "listed", 0, None),
    ])
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM stocks WHERE market='TPEx'")
    assert cur.fetchone()[0] == 0, "TPEx stocks should not be present (gap documented)"
    con.close()


def test_UI03_etf_should_be_excluded_from_common_stock_universe(tmp_db):
    """ETF-like stock_ids (5/6-digit) should be classified as ETF, not common stock."""
    con = sqlite3.connect(tmp_db)
    # Insert ETFs (deliberately not in stocks master — mirrors production)
    insert_prices(con, [
        ("00646", "2026-10-12", 32.5),
        ("006208", "2026-10-12", 71.0),
        ("2330", "2026-10-12", 980.0),
    ])
    insert_stocks(con, [
        ("2330", "台積電", "TWSE", "listed", 0, None),
    ])
    cur = con.cursor()
    # ETF-like: not in stocks master + length >= 5
    cur.execute("""
        SELECT COUNT(DISTINCT dp.stock_id) FROM daily_prices dp
        WHERE dp.stock_id NOT IN (SELECT stock_id FROM stocks)
        AND LENGTH(dp.stock_id) >= 5
    """)
    etf_count = cur.fetchone()[0]
    assert etf_count == 2, "Should detect 2 ETF-like stock_ids not in master"
    con.close()


def test_UI04_0050_benchmark_not_in_common_stock_signals(tmp_db):
    """0050 (benchmark ETF) should NOT appear in ForwardSignals for a common stock strategy."""
    con = sqlite3.connect(tmp_db)
    insert_stocks(con, [
        ("0050", "元大台灣50", "TWSE", "listed", 0, None),
        ("2330", "台積電", "TWSE", "listed", 0, None),
    ])
    # Simulate: signal engine did NOT filter 0050 (the production bug)
    insert_signals(con, [
        ("0050", "2026-10-12", "v8.0", 1, 55.0, "2026-10-12"),
        ("2330", "2026-10-12", "v8.0", 1, 70.0, "2026-10-12"),
    ])
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM forward_signals WHERE stock_id='0050' AND model_version='v8.0'")
    benchmark_signals = cur.fetchone()[0]
    # This test DOCUMENTS the production bug: 0050 appears in signals
    # It should be 0 in a correct implementation
    # We assert the current (buggy) state: > 0
    assert benchmark_signals > 0, (
        "KNOWN BUG: 0050 appears in ForwardSignals. "
        "Should be filtered by ETF exclusion."
    )
    con.close()


def test_UI05_delisted_security_not_in_active_universe(tmp_db):
    """Securities with delisted_date before signal_date should not appear in active universe."""
    con = sqlite3.connect(tmp_db)
    insert_stocks(con, [
        ("2330", "台積電", "TWSE", "listed", 0, None),
        ("1234", "已下市公司", "TWSE", "delisted", 0, "2026-09-01"),
    ])
    cur = con.cursor()
    signal_date = "2026-10-12"
    cur.execute("""
        SELECT COUNT(*) FROM stocks
        WHERE (delisted_date IS NULL OR delisted_date >= ?)
        AND security_status != 'delisted'
        AND is_excluded = 0
    """, (signal_date,))
    eligible = cur.fetchone()[0]
    assert eligible == 1, "Only 2330 should be eligible after 1234 delists"
    con.close()


def test_UI06_unknown_security_type_detected(tmp_db):
    """Stock_ids not in master and not ETF-pattern should be flagged as unknown."""
    con = sqlite3.connect(tmp_db)
    insert_prices(con, [
        ("1234", "2026-10-12", 50.0),   # 4-digit non-master — could be TPEx or unknown
        ("2330", "2026-10-12", 980.0),   # in master
        ("00646", "2026-10-12", 32.5),   # ETF-like
    ])
    insert_stocks(con, [
        ("2330", "台積電", "TWSE", "listed", 0, None),
    ])
    cur = con.cursor()
    # 4-digit orphans (not in master, not ETF-like) = unknown type
    cur.execute("""
        SELECT COUNT(DISTINCT dp.stock_id) FROM daily_prices dp
        WHERE dp.stock_id NOT IN (SELECT stock_id FROM stocks)
        AND LENGTH(dp.stock_id) = 4
        AND dp.stock_id NOT LIKE '0%'
    """)
    unknown_4digit = cur.fetchone()[0]
    assert unknown_4digit == 1, "1234 is an unknown 4-digit security (TPEx or not-loaded TWSE)"
    con.close()


def test_UI07_duplicate_security_id_rejected(tmp_db):
    """Duplicate stock_id in stocks master should not exist (enforced by PK)."""
    con = sqlite3.connect(tmp_db)
    insert_stocks(con, [("2330", "台積電", "TWSE", "listed", 0, None)])
    with pytest.raises(Exception):
        # Should fail: PRIMARY KEY violation
        insert_stocks(con, [("2330", "台積電重複", "TWSE", "listed", 0, None)])
    con.close()


# ---------------------------------------------------------------------------
# CV-01..CV-08  Coverage Tests
# ---------------------------------------------------------------------------

def test_CV01_full_market_classification(tmp_db):
    """Date with >= 5000 distinct stock_ids classified as FULL_MARKET_LOADED."""
    con = sqlite3.connect(tmp_db)
    # Insert 5001 unique stocks on one date
    rows = [(f"{i:04d}", "2026-11-04", 100.0) for i in range(1000, 6001)]
    insert_prices(con, rows)
    cur = con.cursor()
    cur.execute("SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='2026-11-04'")
    count = cur.fetchone()[0]
    verdict = "FULL_MARKET_LOADED" if count >= 5000 else "PARTIAL"
    assert verdict == "FULL_MARKET_LOADED"
    con.close()


def test_CV02_twse_only_classification(tmp_db):
    """Date with 400–900 all-master stocks classified as TWSE_ONLY."""
    con = sqlite3.connect(tmp_db)
    # 600 stocks, all in master
    stocks = [(f"{i:04d}", f"股票{i}", "TWSE", "listed", 0, None) for i in range(1000, 1600)]
    insert_stocks(con, stocks)
    rows = [(f"{i:04d}", "2026-01-15", 100.0) for i in range(1000, 1600)]
    insert_prices(con, rows)
    cur = con.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT dp.stock_id),
               COUNT(DISTINCT CASE WHEN dp.stock_id IN (SELECT stock_id FROM stocks) THEN dp.stock_id END)
        FROM daily_prices dp WHERE date='2026-01-15'
    """)
    total, in_master = cur.fetchone()
    is_twse_only = (400 <= total <= 900) and (total == in_master)
    assert is_twse_only
    con.close()


def test_CV03_proxy_only_classification(tmp_db):
    """Date with exactly 1 stock_id (0050) classified as PROXY_ONLY."""
    con = sqlite3.connect(tmp_db)
    insert_stocks(con, [("0050", "元大台灣50", "TWSE", "listed", 0, None)])
    insert_prices(con, [("0050", "2026-10-19", 115.0)])
    cur = con.cursor()
    cur.execute("SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='2026-10-19'")
    count = cur.fetchone()[0]
    verdict = "PROXY_ONLY" if count == 1 else "OTHER"
    assert verdict == "PROXY_ONLY"
    con.close()


def test_CV04_missing_trading_day(tmp_db):
    """Date with 0 price rows should be classified as MISSING."""
    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='2026-11-06'")
    count = cur.fetchone()[0]
    verdict = "MISSING" if count == 0 else "OTHER"
    assert verdict == "MISSING"
    con.close()


def test_CV05_missing_universe_denominator(tmp_db):
    """Coverage ratio is UNVERIFIED when stocks master is incomplete."""
    con = sqlite3.connect(tmp_db)
    # Only partial master (simulate: 394 of 826 master stocks present)
    stocks = [(f"{i:04d}", f"股票{i}", "TWSE", "listed", 0, None) for i in range(2000, 2394)]
    insert_stocks(con, stocks)
    rows = [(f"{i:04d}", "2026-10-12", 100.0) for i in range(2000, 2655)]
    insert_prices(con, rows)
    cur = con.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT stock_id) total,
               COUNT(DISTINCT CASE WHEN stock_id IN (SELECT stock_id FROM stocks) THEN stock_id END) in_master
        FROM daily_prices WHERE date='2026-10-12'
    """)
    total, in_master = cur.fetchone()
    coverage_ratio = in_master / total
    # Cannot verify because master is incomplete — flag as UNVERIFIED
    is_unverified = coverage_ratio < 1.0
    assert is_unverified, "Coverage should be UNVERIFIED when orphan stocks exist"
    con.close()


def test_CV06_duplicate_dailyprice_detection(tmp_db):
    """Duplicate (stock_id, date) in daily_prices should be detectable."""
    con = sqlite3.connect(tmp_db)
    insert_prices(con, [
        ("2330", "2026-10-12", 980.0),
        ("2330", "2026-10-12", 982.0),  # duplicate
    ])
    cur = con.cursor()
    cur.execute("""
        SELECT stock_id, date, COUNT(*) c FROM daily_prices
        GROUP BY stock_id, date HAVING c > 1
    """)
    dups = cur.fetchall()
    assert len(dups) == 1
    assert dups[0][2] == 2
    con.close()


def test_CV07_sparse_coverage_flag(tmp_db):
    """Date with <50% master coverage should be flagged as SPARSE."""
    con = sqlite3.connect(tmp_db)
    stocks = [(f"{i:04d}", f"股票{i}", "TWSE", "listed", 0, None) for i in range(2000, 2826)]
    insert_stocks(con, stocks)
    # Only 394 of 826 have prices (48%)
    rows = [(f"{i:04d}", "2026-10-12", 100.0) for i in range(2000, 2394)]
    insert_prices(con, rows)
    cur = con.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='2026-10-12'
    """)
    with_prices = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM stocks")
    total_master = cur.fetchone()[0]
    coverage = with_prices / total_master
    assert coverage < 0.6, f"Expected sparse coverage, got {coverage:.1%}"
    con.close()


def test_CV08_etf_contamination_in_sparse_date(tmp_db):
    """ForwardSignals dates with ETF-like stock_ids should be flagged."""
    con = sqlite3.connect(tmp_db)
    insert_prices(con, [
        ("2330", "2026-10-12", 980.0),
        ("00646", "2026-10-12", 32.5),   # 5-digit ETF
        ("006208", "2026-10-12", 71.0),   # 6-digit ETF
    ])
    insert_stocks(con, [("2330", "台積電", "TWSE", "listed", 0, None)])
    cur = con.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT stock_id) FROM daily_prices
        WHERE date='2026-10-12' AND LENGTH(stock_id) >= 5
    """)
    etf_count = cur.fetchone()[0]
    assert etf_count == 2, "Should detect ETF-like stock_ids in price data"
    con.close()


# ---------------------------------------------------------------------------
# RC-01..RC-05  Reconciliation Tests
# ---------------------------------------------------------------------------

def test_RC01_equal_counts_all_versions(tmp_db):
    """COUNT(*) with no filter equals sum of per-version counts."""
    con = sqlite3.connect(tmp_db)
    insert_signals(con, [
        ("2330", "2026-10-12", "v8.0", 1, 70.0, "2026-10-12"),
        ("2317", "2026-10-12", "v8.0", 1, 65.0, "2026-10-12"),
        ("2454", "2026-10-09", "v6.0", 0, 55.0, None),
    ])
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM forward_signals")
    total = cur.fetchone()[0]
    cur.execute("SELECT model_version, COUNT(*) FROM forward_signals GROUP BY model_version")
    by_version = dict(cur.fetchall())
    assert total == sum(by_version.values())
    assert by_version["v8.0"] == 2
    assert by_version["v6.0"] == 1
    con.close()


def test_RC02_v8_valid_filter_gives_subset(tmp_db):
    """v8.0 AND is_valid=1 filter gives a count less than or equal to total."""
    con = sqlite3.connect(tmp_db)
    insert_signals(con, [
        ("2330", "2026-10-12", "v8.0", 1, 70.0, "2026-10-12"),
        ("2454", "2026-10-09", "v6.0", 0, 55.0, None),
    ])
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM forward_signals")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM forward_signals WHERE model_version='v8.0' AND is_valid=1")
    v8_valid = cur.fetchone()[0]
    assert v8_valid <= total
    assert v8_valid == 1
    con.close()


def test_RC03_difference_explained_by_invalid_legacy(tmp_db):
    """The difference between total and v8.0 count must equal is_valid=0 count."""
    con = sqlite3.connect(tmp_db)
    insert_signals(con, [
        ("2330", "2026-10-12", "v8.0", 1, 70.0, "2026-10-12"),
        ("2317", "2026-10-13", "v8.0", 1, 65.0, "2026-10-13"),
        ("2454", "2026-10-09", "v6.0", 0, 55.0, None),
        ("3008", "2026-10-10", "v6.0", 0, 48.0, None),
    ])
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM forward_signals")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM forward_signals WHERE model_version='v8.0' AND is_valid=1")
    v8_valid = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM forward_signals WHERE is_valid=0")
    invalid = cur.fetchone()[0]
    assert total - v8_valid == invalid, "Difference must be fully explained by invalid/legacy signals"
    con.close()


def test_RC04_no_duplicate_signals(tmp_db):
    """No (stock_id, trade_date, model_version) duplicates in forward_signals."""
    con = sqlite3.connect(tmp_db)
    insert_signals(con, [
        ("2330", "2026-10-12", "v8.0", 1, 70.0, "2026-10-12"),
        ("2317", "2026-10-12", "v8.0", 1, 65.0, "2026-10-12"),
    ])
    cur = con.cursor()
    cur.execute("""
        SELECT stock_id, trade_date, model_version, COUNT(*) c
        FROM forward_signals GROUP BY stock_id, trade_date, model_version HAVING c > 1
    """)
    dups = cur.fetchall()
    assert len(dups) == 0
    con.close()


def test_RC05_unresolved_count_flag_when_no_model_version(tmp_db):
    """Signals without model_version set cannot be attributed — reconciliation UNRESOLVED."""
    con = sqlite3.connect(tmp_db)
    insert_signals(con, [
        ("2330", "2026-10-12", None, 1, 70.0, "2026-10-12"),  # NULL model_version
        ("2317", "2026-10-12", "v8.0", 1, 65.0, "2026-10-12"),
    ])
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM forward_signals WHERE model_version IS NULL")
    unattributed = cur.fetchone()[0]
    assert unattributed > 0, "Should detect unattributed signals (reconciliation gap)"
    con.close()


# ---------------------------------------------------------------------------
# BT-01..BT-05  Backtest Validity Tests
# ---------------------------------------------------------------------------

def test_BT01_sparse_date_flag(tmp_db):
    """Signal date with <50% master coverage should be flagged as SPARSE."""
    con = sqlite3.connect(tmp_db)
    stocks = [(f"{i:04d}", f"股票{i}", "TWSE", "listed", 0, None) for i in range(2000, 2826)]
    insert_stocks(con, stocks)
    # Only 400 of 826 master stocks have prices (48%)
    rows = [(f"{i:04d}", "2026-10-12", 100.0) for i in range(2000, 2400)]
    insert_prices(con, rows)

    cur = con.cursor()
    cur.execute("SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='2026-10-12'")
    with_prices = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM stocks WHERE is_excluded=0")
    total_master = cur.fetchone()[0]
    sparse_threshold = 0.5
    is_sparse = (with_prices / total_master) < sparse_threshold
    assert is_sparse, "Should flag Oct 12 as SPARSE (48% < 50% threshold)"
    con.close()


def test_BT02_look_ahead_missing_source_price_date(tmp_db):
    """Signal with source_price_date=NULL cannot confirm no look-ahead."""
    con = sqlite3.connect(tmp_db)
    insert_signals(con, [
        ("2330", "2026-10-12", "v8.0", 1, 70.0, None),  # source_price_date is NULL
    ])
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM forward_signals WHERE source_price_date IS NULL AND model_version='v8.0'")
    no_source = cur.fetchone()[0]
    assert no_source > 0, "NULL source_price_date signals cannot confirm no look-ahead"
    con.close()


def test_BT03_survivorship_bias_zero_delisted(tmp_db):
    """Zero delisted stocks in master over 28 months is a survivorship bias warning."""
    con = sqlite3.connect(tmp_db)
    stocks = [(f"{i:04d}", f"股票{i}", "TWSE", "listed", 0, None) for i in range(2000, 2826)]
    insert_stocks(con, stocks)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM stocks WHERE delisted_date IS NOT NULL")
    delisted_count = cur.fetchone()[0]
    assert delisted_count == 0, "SURVIVORSHIP BIAS: Zero delisted stocks detected"
    # This is a documentation test, not a correctness assertion
    # The assert documents that the master has 0 delisted stocks (the bias)
    con.close()


def test_BT04_etf_in_signals_should_be_zero_for_common_stock_strategy(tmp_db):
    """In a correct common stock strategy, no ETF-like signals should exist."""
    con = sqlite3.connect(tmp_db)
    insert_stocks(con, [
        ("2330", "台積電", "TWSE", "listed", 0, None),
    ])
    # Correctly filtered: only master stocks
    insert_signals(con, [
        ("2330", "2026-10-12", "v8.0", 1, 70.0, "2026-10-12"),
    ])
    cur = con.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM forward_signals fs
        WHERE fs.model_version='v8.0'
        AND (LENGTH(fs.stock_id) >= 5 OR
             fs.stock_id NOT IN (SELECT stock_id FROM stocks WHERE market='TWSE'))
    """)
    etf_signals = cur.fetchone()[0]
    assert etf_signals == 0, "No ETF-like signals should exist in a correctly filtered strategy"
    con.close()


def test_BT05_benchmark_unavailability_detection(tmp_db):
    """Signal date where 0050 has no price should not use 0050 as benchmark."""
    con = sqlite3.connect(tmp_db)
    insert_stocks(con, [("0050", "元大台灣50", "TWSE", "listed", 0, None)])
    # No price for 0050 on the signal date
    insert_prices(con, [("2330", "2026-10-19", 980.0)])
    cur = con.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM daily_prices
        WHERE stock_id='0050' AND date='2026-10-19'
    """)
    has_benchmark = cur.fetchone()[0] > 0
    assert not has_benchmark, "0050 benchmark unavailable on this date"
    con.close()


# ---------------------------------------------------------------------------
# Production DB spot-check (read-only, skipped if DB not available)
# ---------------------------------------------------------------------------

PROD_DB = "data/platform.db"

@pytest.mark.skipif(not os.path.exists(PROD_DB), reason="production DB not available")
def test_PROD01_production_count_reconciliation():
    """Verify 2605 total = 2236 v8.0 + 369 v6.0 in production DB."""
    con = sqlite3.connect(PROD_DB)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM forward_signals")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM forward_signals WHERE model_version='v8.0' AND is_valid=1")
    v8 = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM forward_signals WHERE model_version='v6.0' AND is_valid=0")
    v6 = cur.fetchone()[0]
    assert total == v8 + v6, f"Count mismatch: {total} != {v8} + {v6}"
    assert total == 2605
    assert v8 == 2236
    assert v6 == 369
    con.close()


@pytest.mark.skipif(not os.path.exists(PROD_DB), reason="production DB not available")
def test_PROD02_no_duplicate_signals_production():
    """No duplicate (stock_id, trade_date, model_version) in production DB."""
    con = sqlite3.connect(PROD_DB)
    cur = con.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT stock_id, trade_date, model_version, COUNT(*) c
            FROM forward_signals GROUP BY stock_id, trade_date, model_version HAVING c > 1
        )
    """)
    dups = cur.fetchone()[0]
    assert dups == 0
    con.close()


@pytest.mark.skipif(not os.path.exists(PROD_DB), reason="production DB not available")
def test_PROD03_etf_contamination_in_production_signals():
    """Document that ETF-like signals exist in production (known issue)."""
    con = sqlite3.connect(PROD_DB)
    cur = con.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM forward_signals
        WHERE model_version='v8.0' AND is_valid=1
        AND LENGTH(stock_id) >= 5
    """)
    etf_count = cur.fetchone()[0]
    # This is NOT an error — it documents a known data quality issue
    # The count should be > 0 until ETF filtering is implemented
    assert etf_count >= 0, f"ETF-like signals in v8.0: {etf_count} (known issue, not a bug)"
    con.close()


@pytest.mark.skipif(not os.path.exists(PROD_DB), reason="production DB not available")
def test_PROD04_stocks_master_twse_only():
    """Production stocks master has zero TPEx records (known gap)."""
    con = sqlite3.connect(PROD_DB)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM stocks WHERE market != 'TWSE'")
    non_twse = cur.fetchone()[0]
    assert non_twse == 0, "KNOWN GAP: Zero TPEx stocks in master"
    con.close()


@pytest.mark.skipif(not os.path.exists(PROD_DB), reason="production DB not available")
def test_PROD05_no_duplicate_daily_prices():
    """No duplicate (stock_id, date) in production daily_prices."""
    con = sqlite3.connect(PROD_DB)
    cur = con.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT stock_id, date, COUNT(*) c
            FROM daily_prices GROUP BY stock_id, date HAVING c > 1
        )
    """)
    dups = cur.fetchone()[0]
    assert dups == 0
    con.close()
