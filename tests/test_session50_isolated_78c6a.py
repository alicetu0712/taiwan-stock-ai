"""
S78C.6A Phase D — Isolated session50 test migration (20 tests).

Covers TC03/TC05/TC06/TC08/TC10/TC11 logic from test_session50_market_sources.py
using ci_safe_conn / source_matrix_safe / backfill_safe fixtures from conftest.

These are the TC variants not already covered by test_ci_infra_poc_78c5.py (P01–P22).
All use :memory: SQLite — no production DB access.

Data note: verified_records and provider_verdicts are HARDCODED constants in
market_source_verification_s50.py. These tests assert that hardcoded evidence
is correctly encoded, not production-data integrity.
"""

from __future__ import annotations

from src.research.market_source_verification_s50 import BackfillAction

# ---------------------------------------------------------------------------
# M01–M02: TC03 — Nov 06 upgrade attributes (not covered by P05)
# ---------------------------------------------------------------------------


class TestM01_Nov06UpgradeAttributes:

    def test_nov06_twse_single_stock_available(self, source_matrix_safe):
        nov06 = next(
            s for s in source_matrix_safe.date_summaries if s.date == "2026-11-06"
        )
        assert nov06.twse_single_stock_available is True

    def test_non_upgraded_dates_have_no_upgrade_note(self, source_matrix_safe):
        upgraded_dates = {"2026-11-06", "2026-11-09"}
        for ds in source_matrix_safe.date_summaries:
            if ds.date not in upgraded_dates:
                assert (
                    ds.upgrade_from_prior is None
                ), f"{ds.date} should not have upgrade note"


# ---------------------------------------------------------------------------
# M03–M04: TC05 — Oct 29 aggregate OHLC (not covered by P13 single-stock tests)
# ---------------------------------------------------------------------------


class TestM03_Oct29AggregateOHLC:

    def test_oct29_records_present(self, source_matrix_safe):
        oct29 = [
            r for r in source_matrix_safe.verified_records if r.date == "2026-10-29"
        ]
        assert len(oct29) >= 6

    def test_oct29_ohlc_valid_records(self, source_matrix_safe):
        oct29 = [
            r for r in source_matrix_safe.verified_records if r.date == "2026-10-29"
        ]
        ohlc_valid = [r for r in oct29 if r.ohlc_valid is True]
        assert len(ohlc_valid) >= 6


# ---------------------------------------------------------------------------
# M05–M08: TC06 — Provider verdicts (not covered by POC)
# ---------------------------------------------------------------------------


class TestM05_ProviderVerdicts:

    def test_twse_single_stock_verdict(self, source_matrix_safe):
        v = source_matrix_safe.provider_verdicts["TWSE_SINGLE_STOCK"]
        assert "SOURCE_VERIFIED_PARTIAL" in v

    def test_twse_bulk_unavailable(self, source_matrix_safe):
        v = source_matrix_safe.provider_verdicts["TWSE_BULK_HISTORICAL"]
        assert "SOURCE_UNAVAILABLE" in v

    def test_tpex_bulk_unavailable(self, source_matrix_safe):
        v = source_matrix_safe.provider_verdicts["TPEX_BULK_HISTORICAL"]
        assert "SOURCE_UNAVAILABLE" in v

    def test_bulk_http200_does_not_mean_historical(self, source_matrix_safe):
        v = source_matrix_safe.provider_verdicts["TWSE_BULK_HISTORICAL"]
        assert "HTTP 200" in v or "current date" in v.lower()


# ---------------------------------------------------------------------------
# M09–M12: TC08 — Critical finding text (not covered by POC)
# ---------------------------------------------------------------------------


class TestM09_CriticalFinding:

    def test_finding_mentions_upgrade(self, source_matrix_safe):
        cf = source_matrix_safe.critical_finding
        assert "Nov 06" in cf or "Nov 06/09" in cf

    def test_finding_mentions_twse_single_stock(self, source_matrix_safe):
        assert "TWSE" in source_matrix_safe.critical_finding

    def test_finding_mentions_bulk_unavailable(self, source_matrix_safe):
        assert "SOURCE_UNAVAILABLE" in source_matrix_safe.critical_finding

    def test_retrieval_timestamp_is_s50_date(self, source_matrix_safe):
        assert "2026-11-10" in source_matrix_safe.retrieval_timestamp


# ---------------------------------------------------------------------------
# M13–M16: TC10 — Backfill manifest detail (not covered by P20)
# ---------------------------------------------------------------------------


class TestM13_BackfillManifestDetail:

    def test_candidates_present(self, backfill_safe):
        assert len(backfill_safe.candidates) > 0

    def test_dry_run_fingerprint_prefix(self, backfill_safe):
        assert backfill_safe.dry_run_fingerprint.startswith("DRYRUN-")

    def test_transaction_plan_present(self, backfill_safe):
        assert "INSERT" in backfill_safe.transaction_plan

    def test_rollback_plan_present(self, backfill_safe):
        assert "ROLLBACK" in backfill_safe.rollback_plan


# ---------------------------------------------------------------------------
# M17–M20: TC11 — Manifest action categories (not covered by POC)
# ---------------------------------------------------------------------------


class TestM17_ManifestActionCategories:

    def test_total_adds_up(self, backfill_safe):
        total = (
            backfill_safe.n_insert_candidate
            + backfill_safe.n_skip_existing
            + backfill_safe.n_conflict_review
            + backfill_safe.n_source_missing
            + backfill_safe.n_validation_failed
        )
        assert total == len(backfill_safe.candidates)

    def test_no_negative_counts(self, backfill_safe):
        assert backfill_safe.n_insert_candidate >= 0
        assert backfill_safe.n_skip_existing >= 0
        assert backfill_safe.n_conflict_review >= 0

    def test_all_candidates_have_valid_action(self, backfill_safe):
        valid_actions = set(BackfillAction)
        for c in backfill_safe.candidates:
            assert c.proposed_action in valid_actions

    def test_coverage_improvement_note_present(self, backfill_safe):
        assert len(backfill_safe.expected_coverage_improvement) > 10
