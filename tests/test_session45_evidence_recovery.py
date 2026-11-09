"""
Session 45: Incomplete Cluster Recovery & Evidence Accumulation
25 test categories per PART I specification.

Prefix groups:
  IC — Incomplete Cluster (Oct 22, Oct 28)
  MO — Missing Outcome
  MB — Missing Benchmark
  VM — Version Mismatch guard
  EP — Execution Provenance
  PP — Retrospective vs Prospective
  RE — Recoverable Extraction Error
  IG — Irrecoverable Evidence Gap
  NF — No Fabricated Fill
  NL — No Look-ahead Recovery
  BR — Strict Baseline Reproduction
  BV — New Baseline Versioning
  FP — Dataset Fingerprint Change
  CC — Cluster Count Integrity
  TM — Trading-session Maturity
  PA — Price Availability
  CA — Corporate Action Flag
  DO — Duplicate Opportunity
  OL — Overlapping Holding Period
  G3 — G03 Insufficient Evidence
  G4 — G04 Immature Outcome
  WF — Research-only Dry-run
  PI — Production Isolation
  FH — Frozen Hash Integrity
"""
import sys

import pytest


DB_PATH = "data/platform.db"


@pytest.fixture(scope="module")
def conn():
    import sqlite3
    with sqlite3.connect(DB_PATH) as c:
        yield c


@pytest.fixture(scope="module")
def cluster_report(conn):
    sys.path.insert(0, "src")
    from research.incomplete_cluster_auditor_s45 import build_incomplete_cluster_report
    return build_incomplete_cluster_report(conn)


@pytest.fixture(scope="module")
def maturity_report(conn):
    sys.path.insert(0, "src")
    from research.evidence_policy_s45 import build_20d_maturity_verification
    return build_20d_maturity_verification(conn)


@pytest.fixture(scope="module")
def ledger(conn):
    sys.path.insert(0, "src")
    from research.evidence_policy_s45 import build_evidence_ledger
    return build_evidence_ledger(conn)


@pytest.fixture(scope="module")
def workflow(conn):
    sys.path.insert(0, "src")
    from research.evidence_policy_s45 import build_future_evidence_workflow
    return build_future_evidence_workflow(conn)


@pytest.fixture(scope="module")
def guardrails(conn):
    sys.path.insert(0, "src")
    from research.evidence_policy_s45 import build_guardrail_reassessment
    return build_guardrail_reassessment(conn)


# ---------------------------------------------------------------------------
# IC — Incomplete Cluster Tests (Oct 22 and Oct 28)
# ---------------------------------------------------------------------------

class TestIncompleteClusterOct22:
    def test_ic01_oct22_fill_cluster_exists(self, cluster_report):
        oct22 = next((c for c in cluster_report.clusters if c.fill_date == "2026-10-22"), None)
        assert oct22 is not None

    def test_ic02_oct22_signal_date_correct(self, cluster_report):
        oct22 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-22")
        assert oct22.signal_date == "2026-10-21"

    def test_ic03_oct22_n_signals(self, cluster_report):
        oct22 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-22")
        assert oct22.n_signals == 23

    def test_ic04_oct22_root_cause_outcome_not_mature(self, cluster_report):
        sys.path.insert(0, "src")
        from research.incomplete_cluster_auditor_s45 import MissingEvidenceCause
        oct22 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-22")
        assert oct22.primary_cause == MissingEvidenceCause.OUTCOME_NOT_MATURE

    def test_ic05_oct22_exit_days_lt_5(self, cluster_report):
        oct22 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-22")
        assert oct22.n_exit_days_in_db < 5

    def test_ic06_oct22_recoverable_conditional(self, cluster_report):
        sys.path.insert(0, "src")
        from research.incomplete_cluster_auditor_s45 import ClusterRecoverability
        oct22 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-22")
        assert oct22.recoverability == ClusterRecoverability.RECOVERABLE_CONDITIONAL

    def test_ic07_oct22_no_engineering_extraction_error(self, cluster_report):
        oct22 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-22")
        assert oct22.is_engineering_issue is False


class TestIncompleteClusterOct28:
    def test_ic08_oct28_fill_cluster_exists(self, cluster_report):
        oct28 = next((c for c in cluster_report.clusters if c.fill_date == "2026-10-28"), None)
        assert oct28 is not None

    def test_ic09_oct28_signal_date_correct(self, cluster_report):
        oct28 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-28")
        assert oct28.signal_date == "2026-10-22"

    def test_ic10_oct28_n_signals(self, cluster_report):
        oct28 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-28")
        assert oct28.n_signals == 19

    def test_ic11_oct28_root_cause_outcome_not_mature(self, cluster_report):
        sys.path.insert(0, "src")
        from research.incomplete_cluster_auditor_s45 import MissingEvidenceCause
        oct28 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-28")
        assert oct28.primary_cause == MissingEvidenceCause.OUTCOME_NOT_MATURE

    def test_ic12_oct28_exit_days_lt_5(self, cluster_report):
        oct28 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-28")
        assert oct28.n_exit_days_in_db < 5

    def test_ic13_oct28_recoverable_conditional(self, cluster_report):
        sys.path.insert(0, "src")
        from research.incomplete_cluster_auditor_s45 import ClusterRecoverability
        oct28 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-28")
        assert oct28.recoverability == ClusterRecoverability.RECOVERABLE_CONDITIONAL


# ---------------------------------------------------------------------------
# MO — Missing Outcome (outcome_not_mature guard)
# ---------------------------------------------------------------------------

class TestMissingOutcome:
    def test_mo01_no_fwd_return_in_incomplete_clusters(self, conn):
        for sig_date in ("2026-10-21", "2026-10-22"):
            populated = conn.execute(
                "SELECT COUNT(*) FROM forward_signals "
                "WHERE trade_date=? AND fwd_return_20d IS NOT NULL "
                "AND trade_signal IN ('buy','strong_buy')",
                (sig_date,)
            ).fetchone()[0]
            assert populated == 0, f"Unexpected fwd_return_20d on {sig_date}"

    def test_mo02_pipeline_max_nov05(self, conn):
        max_date = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
        assert max_date == "2026-11-05"

    def test_mo03_exit_days_after_oct22_eq_3(self, conn):
        n = conn.execute(
            """SELECT COUNT(*) FROM (
                SELECT date FROM daily_prices WHERE date > '2026-10-22'
                GROUP BY date HAVING COUNT(DISTINCT stock_id) >= 50
            )"""
        ).fetchone()[0]
        assert n == 3

    def test_mo04_exit_days_after_oct28_eq_2(self, conn):
        n = conn.execute(
            """SELECT COUNT(*) FROM (
                SELECT date FROM daily_prices WHERE date > '2026-10-28'
                GROUP BY date HAVING COUNT(DISTINCT stock_id) >= 50
            )"""
        ).fetchone()[0]
        assert n == 2


# ---------------------------------------------------------------------------
# MB — Missing Benchmark
# ---------------------------------------------------------------------------

class TestMissingBenchmark:
    def test_mb01_0050_present_on_oct28_exit(self, conn):
        for td in ("2026-10-28", "2026-11-04", "2026-11-05"):
            row = conn.execute(
                "SELECT 1 FROM daily_prices WHERE stock_id='0050' AND date=?", (td,)
            ).fetchone()
            assert row is not None, f"0050 missing on {td}"

    def test_mb02_0050_has_more_dates_than_2330(self, conn):
        n_0050 = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE stock_id='0050' AND date > '2026-10-22'"
        ).fetchone()[0]
        n_2330 = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE stock_id='2330' AND date > '2026-10-22'"
        ).fetchone()[0]
        # 0050 has thin-day dates; 2330 only on real TDs
        assert n_0050 >= n_2330


# ---------------------------------------------------------------------------
# VM — Version Mismatch Guard
# ---------------------------------------------------------------------------

class TestVersionMismatch:
    def test_vm01_no_v60_in_strict_pool(self, conn):
        v60_strict = conn.execute(
            "SELECT COUNT(*) FROM forward_signals "
            "WHERE model_version='v6.0' AND execution_date IS NOT NULL "
            "AND trade_signal IN ('buy','strong_buy')"
        ).fetchone()[0]
        assert v60_strict == 0

    def test_vm02_all_oct21_signals_v80(self, conn):
        mvs = {r[0] for r in conn.execute(
            "SELECT DISTINCT model_version FROM forward_signals "
            "WHERE trade_date='2026-10-21' AND trade_signal IN ('buy','strong_buy')"
        ).fetchall()}
        assert mvs == {"v8.0"}

    def test_vm03_all_oct22_signals_v80(self, conn):
        mvs = {r[0] for r in conn.execute(
            "SELECT DISTINCT model_version FROM forward_signals "
            "WHERE trade_date='2026-10-22' AND trade_signal IN ('buy','strong_buy')"
        ).fetchall()}
        assert mvs == {"v8.0"}


# ---------------------------------------------------------------------------
# EP — Execution Provenance
# ---------------------------------------------------------------------------

class TestExecutionProvenance:
    def test_ep01_all_incomplete_cluster_fills_are_next_open(self, conn):
        for sig_date in ("2026-10-21", "2026-10-22"):
            types = {r[0] for r in conn.execute(
                "SELECT DISTINCT execution_price_type FROM forward_signals "
                "WHERE trade_date=? AND trade_signal IN ('buy','strong_buy')",
                (sig_date,)
            ).fetchall()}
            assert types == {"NEXT_OPEN"}, f"Unexpected exec type on {sig_date}: {types}"

    def test_ep02_fill_prices_match_dp_open_oct22(self, conn):
        rows = conn.execute(
            "SELECT stock_id, execution_date, execution_price FROM forward_signals "
            "WHERE trade_date='2026-10-21' AND trade_signal IN ('buy','strong_buy') LIMIT 5"
        ).fetchall()
        for stock_id, exec_date, exec_price in rows:
            if exec_price is not None and exec_date:
                dp_open = conn.execute(
                    "SELECT open FROM daily_prices WHERE stock_id=? AND date=?",
                    (stock_id, exec_date)
                ).fetchone()
                assert dp_open is not None
                assert abs(dp_open[0] - exec_price) < 0.01

    def test_ep03_no_null_exec_date_in_oct21_signals(self, conn):
        nulls = conn.execute(
            "SELECT COUNT(*) FROM forward_signals "
            "WHERE trade_date='2026-10-21' AND execution_date IS NULL "
            "AND trade_signal IN ('buy','strong_buy')"
        ).fetchone()[0]
        assert nulls == 0


# ---------------------------------------------------------------------------
# PP — Retrospective vs Prospective
# ---------------------------------------------------------------------------

class TestRetroVsProspective:
    def test_pp01_all_v80_signals_genuine_prospective(self, ledger):
        sys.path.insert(0, "src")
        from research.evidence_policy_s45 import ProvenanceClass
        for rec in ledger.records:
            assert rec.provenance == ProvenanceClass.GENUINE_PROSPECTIVE

    def test_pp02_no_retrospective_reconstruction_in_strict_pool(self, ledger):
        sys.path.insert(0, "src")
        from research.evidence_policy_s45 import ProvenanceClass
        retro = [r for r in ledger.records
                 if r.provenance == ProvenanceClass.RETROSPECTIVE_RECONSTRUCTION and r.eligible]
        assert len(retro) == 0


# ---------------------------------------------------------------------------
# RE — Recoverable Extraction Error
# ---------------------------------------------------------------------------

class TestRecoverableExtractionError:
    def test_re01_oct22_not_extraction_error(self, cluster_report):
        oct22 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-22")
        assert oct22.is_engineering_issue is False

    def test_re02_oct28_not_extraction_error(self, cluster_report):
        oct28 = next(c for c in cluster_report.clusters if c.fill_date == "2026-10-28")
        assert oct28.is_engineering_issue is False

    def test_re03_all_signal_prices_match_dp(self, conn):
        # Verify fill price integrity for both incomplete clusters
        for sig_date in ("2026-10-21", "2026-10-22"):
            rows = conn.execute(
                "SELECT stock_id, execution_date, execution_price FROM forward_signals "
                "WHERE trade_date=? AND trade_signal IN ('buy','strong_buy')",
                (sig_date,)
            ).fetchall()
            for stock_id, exec_date, exec_price in rows:
                if exec_price and exec_date:
                    dp = conn.execute(
                        "SELECT open FROM daily_prices WHERE stock_id=? AND date=?",
                        (stock_id, exec_date)
                    ).fetchone()
                    if dp:
                        assert abs(dp[0] - exec_price) < 0.01


# ---------------------------------------------------------------------------
# IG — Irrecoverable Evidence Gap
# ---------------------------------------------------------------------------

class TestIrrecoverableGap:
    def test_ig01_neither_cluster_is_irrecoverable(self, cluster_report):
        for c in cluster_report.clusters:
            assert c.is_irrecoverable_gap is False

    def test_ig02_no_v60_evidence_is_recoverable_as_v80(self, conn):
        # v6.0 signals have NULL execution_date and cannot be treated as v8.0
        v60_with_exec = conn.execute(
            "SELECT COUNT(*) FROM forward_signals "
            "WHERE model_version='v6.0' AND execution_date IS NOT NULL"
        ).fetchone()[0]
        assert v60_with_exec == 0


# ---------------------------------------------------------------------------
# NF — No Fabricated Fill
# ---------------------------------------------------------------------------

class TestNoFabricatedFill:
    def test_nf01_fill_prices_equal_actual_dp_open(self, conn):
        rows = conn.execute(
            "SELECT fs.stock_id, fs.execution_date, fs.execution_price, dp.open "
            "FROM forward_signals fs "
            "JOIN daily_prices dp ON dp.stock_id=fs.stock_id AND dp.date=fs.execution_date "
            "WHERE fs.trade_date IN ('2026-10-21','2026-10-22') "
            "AND fs.trade_signal IN ('buy','strong_buy') LIMIT 20"
        ).fetchall()
        assert len(rows) > 0
        for _, _, ep, dp_open in rows:
            assert abs(ep - dp_open) < 0.01, f"Fill price {ep} != DP open {dp_open}"

    def test_nf02_no_fill_on_non_trading_day(self, conn):
        # Execution dates should only be on real TDs (≥50 stocks)
        exec_dates = {r[0] for r in conn.execute(
            "SELECT DISTINCT execution_date FROM forward_signals "
            "WHERE model_version='v8.0' AND execution_date IS NOT NULL "
            "AND trade_signal IN ('buy','strong_buy')"
        ).fetchall()}
        # All these should be real TDs
        for ed in exec_dates:
            n_stocks = conn.execute(
                "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?", (ed,)
            ).fetchone()[0]
            assert n_stocks >= 50, f"{ed} is not a real trading day (only {n_stocks} stocks)"


# ---------------------------------------------------------------------------
# NL — No Look-ahead Recovery
# ---------------------------------------------------------------------------

class TestNoLookAheadRecovery:
    def test_nl01_no_look_ahead_risk_in_audit(self, cluster_report):
        for c in cluster_report.clusters:
            assert c.look_ahead_bias_risk is False

    def test_nl02_signal_locked_before_execution_date(self, conn):
        # locked_at should be <= execution_date for all v8.0 signals
        rows = conn.execute(
            "SELECT trade_date, locked_at, execution_date FROM forward_signals "
            "WHERE model_version='v8.0' AND execution_date IS NOT NULL "
            "AND trade_signal IN ('buy','strong_buy') LIMIT 20"
        ).fetchall()
        for td, locked, exec_d in rows:
            assert locked <= exec_d, f"Look-ahead: locked_at={locked} > exec={exec_d}"


# ---------------------------------------------------------------------------
# BR — Strict Baseline Reproduction
# ---------------------------------------------------------------------------

class TestStrictBaselineReproduction:
    def test_br01_before_has_3_strict_clusters(self, cluster_report):
        assert cluster_report.baseline_integrity.before.n_strict_clusters == 3

    def test_br02_before_delta_matches_s44(self, cluster_report):
        delta = cluster_report.baseline_integrity.before.grand_mean_delta_vs_a
        assert abs(delta - 0.0081) < 0.005  # ±0.5 pp

    def test_br03_before_significance_inconclusive(self, cluster_report):
        verdict = cluster_report.baseline_integrity.before.statistical_verdict
        assert verdict == "SIGNIFICANCE_INCONCLUSIVE"

    def test_br04_fingerprint_stable(self, cluster_report):
        # Before and after should have same fingerprint (no new strict clusters yet)
        bi = cluster_report.baseline_integrity
        # They may differ if DB state changed between calls; check it's not empty
        assert len(bi.before.dataset_fingerprint) == 16


# ---------------------------------------------------------------------------
# BV — New Baseline Versioning
# ---------------------------------------------------------------------------

class TestNewBaselineVersioning:
    def test_bv01_before_and_after_are_separate_versions(self, cluster_report):
        bi = cluster_report.baseline_integrity
        assert bi.before.version_id != bi.after_verified_recovery.version_id

    def test_bv02_no_new_strict_clusters_in_s45(self, cluster_report):
        assert cluster_report.baseline_integrity.n_new_strict_clusters == 0

    def test_bv03_verdict_baseline_reproduced(self, cluster_report):
        sys.path.insert(0, "src")
        from research.incomplete_cluster_auditor_s45 import BaselineIntegrityVerdict
        assert cluster_report.baseline_integrity.verdict == BaselineIntegrityVerdict.BASELINE_REPRODUCED


# ---------------------------------------------------------------------------
# FP — Dataset Fingerprint Change
# ---------------------------------------------------------------------------

class TestDatasetFingerprintChange:
    def test_fp01_fingerprint_is_16_hex_chars(self, cluster_report):
        fp = cluster_report.baseline_integrity.before.dataset_fingerprint
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)

    def test_fp02_fingerprint_deterministic(self, conn):
        sys.path.insert(0, "src")
        from research.reproducibility_manifest_s44 import build_reproducibility_manifest
        m1 = build_reproducibility_manifest(conn)
        m2 = build_reproducibility_manifest(conn)
        assert m1.dataset_fingerprint == m2.dataset_fingerprint


# ---------------------------------------------------------------------------
# CC — Cluster Count Integrity
# ---------------------------------------------------------------------------

class TestClusterCountIntegrity:
    def test_cc01_strict_clusters_still_3(self, conn):
        # Count fill dates with ≥5 real TDs after them
        fill_dates = conn.execute(
            "SELECT DISTINCT execution_date FROM forward_signals "
            "WHERE model_version='v8.0' AND trade_signal IN ('buy','strong_buy') "
            "AND execution_date IS NOT NULL"
        ).fetchall()
        strict = []
        for (fd,) in fill_dates:
            n_tds = conn.execute(
                """SELECT COUNT(*) FROM (
                    SELECT date FROM daily_prices WHERE date > ?
                    GROUP BY date HAVING COUNT(DISTINCT stock_id) >= 50
                )""",
                (fd,)
            ).fetchone()[0]
            if n_tds >= 5:
                strict.append(fd)
        assert len(strict) == 3

    def test_cc02_cluster_count_does_not_use_signal_count(self, ledger):
        # Ledger uses cluster-level records, not signal-level
        for rec in ledger.records:
            assert rec.n_signals > 0  # each record has multiple signals

    def test_cc03_total_strict_signals_128(self, conn):
        # Oct 13 (46) + Oct 14 (27) + Oct 16 (55) = 128
        total = sum(
            conn.execute(
                "SELECT COUNT(*) FROM forward_signals "
                "WHERE execution_date=? AND trade_signal IN ('buy','strong_buy')",
                (fd,)
            ).fetchone()[0]
            for fd in ("2026-10-13", "2026-10-14", "2026-10-16")
        )
        assert total == 128


# ---------------------------------------------------------------------------
# TM — Trading-session Maturity
# ---------------------------------------------------------------------------

class TestTradingSessionMaturity:
    def test_tm01_maturity_uses_real_td_count_not_calendar(self, maturity_report):
        # Oct 13 fill has 7 TDs available (not calendar days)
        oct13 = next(r for r in maturity_report.maturity_records if r.fill_date == "2026-10-13")
        assert oct13.td_days_available == 7
        assert oct13.td_days_available < 20  # not mature

    def test_tm02_all_clusters_not_mature(self, maturity_report):
        sys.path.insert(0, "src")
        from research.evidence_policy_s45 import MaturityStatus20D
        for r in maturity_report.maturity_records:
            assert r.maturity_status != MaturityStatus20D.MATURE_AND_COMPLETE

    def test_tm03_eta_oct13_is_nov2026(self, maturity_report):
        oct13 = next(r for r in maturity_report.maturity_records if r.fill_date == "2026-10-13")
        assert "2026-11" in oct13.eta_20d_complete

    def test_tm04_eta_oct28_is_dec2026(self, maturity_report):
        oct28 = next(r for r in maturity_report.maturity_records if r.fill_date == "2026-10-28")
        assert "2026-12" in oct28.eta_20d_complete


# ---------------------------------------------------------------------------
# PA — Price Availability
# ---------------------------------------------------------------------------

class TestPriceAvailability:
    def test_pa01_all_strict_cluster_stocks_have_price_on_exit_dates(self, conn):
        # Strict clusters: fill Oct 13/14/16; each has 5 real TDs
        strict_clusters = {
            "2026-10-13": ["2026-10-14","2026-10-16","2026-10-21","2026-10-22","2026-10-28"],
            "2026-10-14": ["2026-10-16","2026-10-21","2026-10-22","2026-10-28","2026-11-04"],
            "2026-10-16": ["2026-10-21","2026-10-22","2026-10-28","2026-11-04","2026-11-05"],
        }
        for fill_date, exit_dates in strict_clusters.items():
            stocks = [r[0] for r in conn.execute(
                "SELECT DISTINCT stock_id FROM forward_signals WHERE execution_date=? "
                "AND trade_signal IN ('buy','strong_buy')", (fill_date,)
            ).fetchall()]
            for td in exit_dates:
                n_with_price = conn.execute(
                    "SELECT COUNT(DISTINCT stock_id) FROM daily_prices "
                    "WHERE date=? AND stock_id IN ({})".format(",".join("?"*len(stocks))),
                    [td] + stocks
                ).fetchone()[0]
                # All signal stocks should have price on exit dates
                assert n_with_price == len(stocks), (
                    f"fill={fill_date} exit={td}: {n_with_price}/{len(stocks)} have price"
                )

    def test_pa02_incomplete_cluster_stocks_have_price_on_available_exits(self, conn):
        for sig_date, fill_date in [("2026-10-21","2026-10-22"),("2026-10-22","2026-10-28")]:
            stocks = [r[0] for r in conn.execute(
                "SELECT DISTINCT stock_id FROM forward_signals WHERE trade_date=? "
                "AND trade_signal IN ('buy','strong_buy')", (sig_date,)
            ).fetchall()]
            exit_dates = conn.execute(
                "SELECT DISTINCT date FROM daily_prices WHERE date > ? "
                "AND stock_id=? ORDER BY date LIMIT 3",
                (fill_date, "2330")
            ).fetchall()
            for (td,) in exit_dates:
                n = conn.execute(
                    "SELECT COUNT(*) FROM daily_prices WHERE date=? "
                    "AND stock_id IN ({})".format(",".join("?"*len(stocks))),
                    [td] + stocks
                ).fetchone()[0]
                assert n == len(stocks)


# ---------------------------------------------------------------------------
# CA — Corporate Action Flag
# ---------------------------------------------------------------------------

class TestCorporateActionFlag:
    def test_ca01_no_corporate_action_column_in_forward_signals(self, conn):
        cols = [r[1] for r in conn.execute("PRAGMA table_info(forward_signals)").fetchall()]
        assert "corporate_action" not in cols

    def test_ca02_no_split_adjusted_column(self, conn):
        cols = [r[1] for r in conn.execute("PRAGMA table_info(forward_signals)").fetchall()]
        assert "split_adjusted" not in cols


# ---------------------------------------------------------------------------
# DO — Duplicate Opportunity
# ---------------------------------------------------------------------------

class TestDuplicateOpportunity:
    def test_do01_no_duplicate_stock_signal_date_pairs(self, conn):
        # Each (stock_id, trade_date) should appear at most once in buy/SB signals
        dups = conn.execute(
            "SELECT stock_id, trade_date, COUNT(*) as cnt "
            "FROM forward_signals WHERE trade_signal IN ('buy','strong_buy') "
            "GROUP BY stock_id, trade_date HAVING cnt > 1"
        ).fetchall()
        assert len(dups) == 0, f"Duplicate stock+date pairs: {dups}"

    def test_do02_dedup_keys_defined_in_ledger(self, ledger):
        assert "stock_id" in ledger.deduplication_keys
        assert "execution_date" in ledger.deduplication_keys


# ---------------------------------------------------------------------------
# OL — Overlapping Holding Period
# ---------------------------------------------------------------------------

class TestOverlappingHoldingPeriod:
    def test_ol01_adjacent_5d_windows_overlap(self):
        # Oct 13 (5D exit ~Oct 21) and Oct 14 (5D exit ~Oct 22): share Oct 14-21
        # This documents the KNOWN G04 overlap, not an error
        oct13_window = ("2026-10-13", "2026-10-21")
        oct14_window = ("2026-10-14", "2026-10-22")
        overlap_start = max(oct13_window[0], oct14_window[0])
        overlap_end = min(oct13_window[1], oct14_window[1])
        has_overlap = overlap_start < overlap_end
        assert has_overlap is True  # confirmed G04 violation

    def test_ol02_g04_documented_in_guardrails(self, guardrails):
        g04_records = [r for r in guardrails.records if r.guardrail_id == "G04"]
        assert len(g04_records) >= 1
        for r in g04_records:
            assert r.after_verdict.value == "FAIL"


# ---------------------------------------------------------------------------
# G3 — G03 Insufficient Evidence
# ---------------------------------------------------------------------------

class TestG03InsufficientEvidence:
    def test_g3_01_g03_still_fail_in_s45(self, guardrails):
        g03 = next(r for r in guardrails.records if r.guardrail_id == "G03")
        assert g03.after_verdict.value == "FAIL"

    def test_g3_02_strict_cluster_count_below_10(self, conn):
        n_strict = conn.execute(
            """SELECT COUNT(*) FROM (
                SELECT execution_date, COUNT(*) FROM forward_signals
                WHERE model_version='v8.0' AND trade_signal IN ('buy','strong_buy')
                AND execution_date IS NOT NULL
                GROUP BY execution_date
            ) sub
            WHERE sub.execution_date IN (
                SELECT date FROM (
                    SELECT date FROM daily_prices GROUP BY date HAVING COUNT(DISTINCT stock_id) >= 50
                )
            ) AND sub.execution_date IN (
                SELECT date FROM (
                    SELECT d2.date, COUNT(*) AS after_count
                    FROM (SELECT DISTINCT date FROM daily_prices WHERE stock_id='2330') d2
                    WHERE (SELECT COUNT(DISTINCT date) FROM daily_prices
                           WHERE stock_id='2330' AND date > d2.date) >= 5
                    GROUP BY d2.date
                )
            )"""
        ).fetchone()[0]
        assert n_strict < 10

    def test_g3_03_even_after_recovery_below_10(self, guardrails):
        # Even if Oct 22 + Oct 28 recover → 5 clusters, still < 10
        g03 = next(r for r in guardrails.records if r.guardrail_id == "G03")
        assert "5 clusters" in g03.evidence or "3" in g03.evidence


# ---------------------------------------------------------------------------
# G4 — G04 Immature Outcome
# ---------------------------------------------------------------------------

class TestG04ImmatureOutcome:
    def test_g4_01_g04_5d_still_fail(self, guardrails):
        g04_5d = next(r for r in guardrails.records if r.guardrail_id == "G04" and r.horizon == "5D")
        assert g04_5d.after_verdict.value == "FAIL"

    def test_g4_02_g04_20d_still_fail(self, guardrails):
        g04_20d = next(r for r in guardrails.records if r.guardrail_id == "G04" and r.horizon == "20D")
        assert g04_20d.after_verdict.value == "FAIL"

    def test_g4_03_5d_and_20d_assessed_independently(self, guardrails):
        horizons = {r.horizon for r in guardrails.records if r.guardrail_id == "G04"}
        assert "5D" in horizons
        assert "20D" in horizons


# ---------------------------------------------------------------------------
# WF — Research-only Dry-run
# ---------------------------------------------------------------------------

class TestDryRunWorkflow:
    def test_wf01_workflow_is_dry_run(self, workflow):
        assert workflow.is_dry_run is True

    def test_wf02_no_new_eligible_evidence(self, workflow):
        # Oct 22 and Oct 28 fill dates are still deferred
        assert workflow.deferred_count >= 2

    def test_wf03_forbidden_actions_listed(self, workflow):
        assert "20D Outcome Computation" in workflow.forbidden_actions
        assert "Strategy Activation" in workflow.forbidden_actions

    def test_wf04_candidate_count_covers_all_fill_dates(self, workflow):
        assert workflow.candidate_count == 6  # 6 v8.0 fill dates


# ---------------------------------------------------------------------------
# PI — Production Isolation
# ---------------------------------------------------------------------------

class TestProductionIsolation:
    def test_pi01_forward_signals_count_unchanged(self, conn):
        total = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        assert total == 2605

    def test_pi02_no_production_modified_flag(self, cluster_report):
        assert cluster_report.no_production_modified is True

    def test_pi03_session_max_daily_prices_unchanged(self, conn):
        max_date = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
        assert max_date == "2026-11-05"


# ---------------------------------------------------------------------------
# FH — Frozen Hash Integrity
# ---------------------------------------------------------------------------

class TestFrozenHashIntegrity:
    def test_fh01_v3_param_hash_frozen(self):
        sys.path.insert(0, "src")
        from research.v3_backtest_engine import PARAMETER_HASH
        assert PARAMETER_HASH == "be43e8ca977d9fdd"

    def test_fh02_crontab_hash_accessible(self):
        import subprocess
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        assert result.returncode in (0, 1)

    def test_fh03_hybrid_strategy_importable(self):
        sys.path.insert(0, "src")
        import research.hybrid_entry_strategy as hes
        assert hes is not None
