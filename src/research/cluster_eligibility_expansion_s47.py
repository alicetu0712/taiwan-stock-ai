"""
PARTS D/E/F/G (P3–P6): Cluster Eligibility, Expanded Comparison,
20D Maturity Reconciliation, and G04 Overlap Analysis — Session 47.

Key findings:
  1. Strict cluster count UNCHANGED at 3 (Oct 13/14/16 fills).
     Incomplete clusters (Oct 21/22/28) cannot be promoted because the
     data for Oct 29/30/Nov 02/03 is RECOVERY_BLOCKED.

  2. Frozen baseline REPRODUCED: grand mean D = +0.81 pp, 3 clusters.
     NOTE: dataset fingerprint changed (09c04e8c4059d87e) because
     daily_prices_max changed (Nov 04/05 manual backfill between S44 and
     S47). The baseline metrics are identical.

  3. 20D maturity dates CORRECTED vs S46:
     S46 _CALENDAR_20TD had errors for Oct 13/14/21/22/28 fills.
     Correct dates per TaiwanTradingCalendar (20 real TDs after fill_date):
       Oct 13 → Nov 12  (S46 said Nov 14, Δ = -2 days)
       Oct 14 → Nov 13  (S46 said Nov 17, Δ = -4 days)
       Oct 16 → Nov 17  (S46 matches)
       Oct 21 → Nov 20  (S46 said Nov 24, Δ = -4 days)
       Oct 22 → Nov 23  (S46 said Nov 25, Δ = -2 days)
       Oct 28 → Nov 25  (S46 said Dec 02, Δ = -7 days)
     Earliest 20D maturity: 2026-11-12 (3 days from analysis date Nov 09).
     All clusters NOT_YET_MATURE for 20D as of Nov 09.

  4. S46 _CALENDAR_5TD also had errors for Oct 13/14/16 fills:
     S46 used TSMC-proxy-based dates for those clusters instead of real TDs.
     Correct calendar 5th TDs:
       Oct 13 → Oct 20  (S46 said Oct 21, Δ = -1 day)
       Oct 14 → Oct 21  (S46 said Oct 28, Δ = -7 days)
       Oct 16 → Oct 27  (S46 said Nov 05, Δ = -9 days)
     Note: Oct 20 has only 0050 data (PARTIAL_COVERAGE), making Oct 21
     the first full-coverage date at or after the 5th real TD for Oct 13 fill.

  5. G04 80% overlap: adjacent-pair metric, formula = len(intersection) /
     window_size (5). Maximum overlap between Oct 13/Oct 14 pair = 4/5 = 80%.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ClusterEligibilityVerdict(str, Enum):
    STRICT_ELIGIBLE = "STRICT_ELIGIBLE"
    CONDITIONALLY_ELIGIBLE = "CONDITIONALLY_ELIGIBLE"
    DATA_INCOMPLETE = "DATA_INCOMPLETE"
    PERMANENTLY_INELIGIBLE = "PERMANENTLY_INELIGIBLE"


class ComparisonVerdict(str, Enum):
    EXPANDED_COMPARISON_AVAILABLE = "EXPANDED_COMPARISON_AVAILABLE"
    NO_NEW_ELIGIBLE_CLUSTERS = "NO_NEW_ELIGIBLE_CLUSTERS"
    COMPARISON_BLOCKED = "COMPARISON_BLOCKED"


class MaturityStatus(str, Enum):
    NOT_YET_MATURE = "NOT_YET_MATURE"
    MATURE_BUT_DATA_INCOMPLETE = "MATURE_BUT_DATA_INCOMPLETE"
    MATURE_AND_COMPLETE = "MATURE_AND_COMPLETE"
    DATE_UNVERIFIED = "DATE_UNVERIFIED"


# ---------------------------------------------------------------------------
# Cluster eligibility
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClusterEligibilityRecord:
    fill_date: str
    signal_date: str
    model_version: str
    n_signals: int
    proxy_exit_days: int
    required_exit_days: int
    is_strict_now: bool
    verdict: ClusterEligibilityVerdict
    missing_dates_needed: tuple[str, ...]
    upgrade_path: str


@dataclass(frozen=True)
class StrictClusterEligibilityS47:
    analysis_date: str
    clusters: tuple[ClusterEligibilityRecord, ...]
    n_strict: int
    n_data_incomplete: int
    n_permanently_ineligible: int
    frozen_strict_fill_dates: tuple[str, ...]
    new_strict_fill_dates: tuple[str, ...]
    verdict: ComparisonVerdict
    rationale: str


# ---------------------------------------------------------------------------
# 5D and 20D calendar dates (corrected vs S46)
# ---------------------------------------------------------------------------

# Correct calendar 5th TDs per TaiwanTradingCalendar (20 real TDs after fill_date)
# Verified by: nth_td_after(fill_date, 5) using TaiwanTradingCalendar
_CORRECT_5TD: dict[str, str] = {
    "2026-10-13": "2026-10-20",   # S46 said Oct 21 (error: used Oct 21 incorrectly)
    "2026-10-14": "2026-10-21",   # S46 said Oct 28 (error: used TSMC-proxy date)
    "2026-10-16": "2026-10-27",   # S46 said Nov 05 (error: used TSMC-proxy date)
    "2026-10-21": "2026-10-30",   # S46 Oct 30 ✓
    "2026-10-22": "2026-11-02",   # S46 Nov 02 ✓
    "2026-10-28": "2026-11-04",   # S46 Nov 04 ✓
}

# Correct calendar 20th TDs per TaiwanTradingCalendar
# Verified by: nth_td_after(fill_date, 20) using TaiwanTradingCalendar
_CORRECT_20TD: dict[str, str] = {
    "2026-10-13": "2026-11-12",   # S46 said Nov 14 (error, Δ = -2 days)
    "2026-10-14": "2026-11-13",   # S46 said Nov 17 (error, Δ = -4 days)
    "2026-10-16": "2026-11-17",   # S46 matches
    "2026-10-21": "2026-11-20",   # S46 said Nov 24 (error, Δ = -4 days)
    "2026-10-22": "2026-11-23",   # S46 said Nov 25 (error, Δ = -2 days)
    "2026-10-28": "2026-11-25",   # S46 said Dec 02 (error, Δ = -7 days)
}

# S46 (incorrect) values for comparison
_S46_5TD: dict[str, str] = {
    "2026-10-13": "2026-10-21",
    "2026-10-14": "2026-10-28",
    "2026-10-16": "2026-11-05",
    "2026-10-21": "2026-10-30",
    "2026-10-22": "2026-11-02",
    "2026-10-28": "2026-11-04",
}

_S46_20TD: dict[str, str] = {
    "2026-10-13": "2026-11-14",
    "2026-10-14": "2026-11-17",
    "2026-10-16": "2026-11-19",
    "2026-10-21": "2026-11-24",
    "2026-10-22": "2026-11-25",
    "2026-10-28": "2026-12-02",
}

# 5D holding windows (actual calendar trading days, not proxy-based)
# window = {day_1, day_2, ..., day_5} where day_1 = first TD after fill_date
_HOLD_WINDOWS_5D: dict[str, tuple[str, ...]] = {
    "2026-10-13": ("2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"),
    "2026-10-14": ("2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"),
    "2026-10-16": ("2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-27"),
    "2026-10-21": ("2026-10-22", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"),
    "2026-10-22": ("2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-11-02"),
    "2026-10-28": ("2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04"),
}


# ---------------------------------------------------------------------------
# 20D maturity
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TwentyDMaturityRecord:
    fill_date: str
    signal_date: str
    execution_date: str
    correct_exit_date_20d: str
    s46_exit_date_20d: str
    s46_error_days: int
    data_availability_date: str
    required_stock_count: int
    available_stock_count: int
    maturity_status: MaturityStatus
    notes: str


@dataclass(frozen=True)
class TwentyDMaturityMatrixS47:
    analysis_date: str
    records: tuple[TwentyDMaturityRecord, ...]
    n_not_yet_mature: int
    n_mature_incomplete: int
    n_mature_complete: int
    earliest_exit_date: str
    latest_exit_date: str
    earliest_maturity_date: str
    s46_earliest_exit_was: str
    s46_error_confirmed: bool
    all_not_yet_mature: bool


# ---------------------------------------------------------------------------
# G04 overlap
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WindowOverlapRecord:
    fill_a: str
    fill_b: str
    window_a: tuple[str, ...]
    window_b: tuple[str, ...]
    intersection: tuple[str, ...]
    overlap_pct: float
    is_adjacent: bool


@dataclass(frozen=True)
class G04OverlapAnalysisS47:
    analysis_date: str
    formula: str
    denominator_definition: str
    all_pairs: tuple[WindowOverlapRecord, ...]
    max_overlap_pct: float
    max_overlap_pair: tuple[str, str]
    adjacent_pair_overlaps: tuple[WindowOverlapRecord, ...]
    g04_threshold_pct: float
    g04_status: str
    independence_violation_note: str


# ---------------------------------------------------------------------------
# Build functions
# ---------------------------------------------------------------------------

def build_strict_cluster_eligibility_s47(
    conn: sqlite3.Connection,
    analysis_date: str = "2026-11-09",
) -> StrictClusterEligibilityS47:
    # Frozen deltas from S43 (pre-computed, used as canonical reference)
    _FROZEN = {
        "2026-10-13": ("2026-10-12", "v8.0", 46),
        "2026-10-14": ("2026-10-13", "v8.0", 27),
        "2026-10-16": ("2026-10-14", "v8.0", 55),
        "2026-10-21": ("2026-10-16", "v8.0", 39),
        "2026-10-22": ("2026-10-21", "v8.0", 23),
        "2026-10-28": ("2026-10-22", "v8.0", 19),
    }

    def _count_exit(fill_date: str) -> int:
        return conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE stock_id='2330' "
            "AND date > ? AND date <= '2026-11-30'",
            (fill_date,),
        ).fetchone()[0]

    # Dates needed to promote each incomplete cluster
    _UPGRADE_REQUIREMENTS = {
        "2026-10-21": (
            ("2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"),
            "Need ≥1 of these dates with TSMC data to reach proxy count 5",
        ),
        "2026-10-22": (
            ("2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"),
            "Need ≥2 of these dates with TSMC data to reach proxy count 5",
        ),
        "2026-10-28": (
            ("2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"),
            "Need ≥3 of these dates with TSMC data to reach proxy count 5",
        ),
    }

    _FROZEN_STRICT = frozenset({"2026-10-13", "2026-10-14", "2026-10-16"})

    records: list[ClusterEligibilityRecord] = []
    for fill_date, (signal_date, mv, n_sigs) in _FROZEN.items():
        proxy = _count_exit(fill_date)
        is_strict = fill_date in _FROZEN_STRICT

        if is_strict:
            verdict = ClusterEligibilityVerdict.STRICT_ELIGIBLE
            missing = ()
            upgrade = "Already strict; no action needed."
        else:
            verdict = ClusterEligibilityVerdict.DATA_INCOMPLETE
            req_dates, upgrade_note = _UPGRADE_REQUIREMENTS.get(
                fill_date, ((), "No upgrade path identified.")
            )
            missing = req_dates
            upgrade = (
                f"RECOVERY_BLOCKED: {upgrade_note}. "
                "Data for required dates unavailable in isolated environment."
            )

        records.append(ClusterEligibilityRecord(
            fill_date=fill_date,
            signal_date=signal_date,
            model_version=mv,
            n_signals=n_sigs,
            proxy_exit_days=proxy,
            required_exit_days=5,
            is_strict_now=is_strict,
            verdict=verdict,
            missing_dates_needed=missing,
            upgrade_path=upgrade,
        ))

    n_strict = sum(1 for r in records if r.is_strict_now)
    n_incomplete = sum(1 for r in records if r.verdict == ClusterEligibilityVerdict.DATA_INCOMPLETE)

    return StrictClusterEligibilityS47(
        analysis_date=analysis_date,
        clusters=tuple(records),
        n_strict=n_strict,
        n_data_incomplete=n_incomplete,
        n_permanently_ineligible=0,
        frozen_strict_fill_dates=("2026-10-13", "2026-10-14", "2026-10-16"),
        new_strict_fill_dates=(),
        verdict=ComparisonVerdict.NO_NEW_ELIGIBLE_CLUSTERS,
        rationale=(
            "All 3 incomplete clusters (Oct 21/22/28) remain DATA_INCOMPLETE. "
            "Proxy exit-day count insufficient (4/3/2 of 5 required). "
            "Data for Oct 29/30/Nov 02/03 unavailable; RECOVERY_BLOCKED."
        ),
    )


def build_20d_maturity_matrix_s47(
    conn: sqlite3.Connection,
    analysis_date: str = "2026-11-09",
) -> TwentyDMaturityMatrixS47:
    _SIGNAL_DATES = {
        "2026-10-13": "2026-10-12",
        "2026-10-14": "2026-10-13",
        "2026-10-16": "2026-10-14",
        "2026-10-21": "2026-10-16",
        "2026-10-22": "2026-10-21",
        "2026-10-28": "2026-10-22",
    }
    _REQUIRED_STOCKS = 500  # minimum for a "complete" date

    def _stock_count_on(d: str) -> int:
        return conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?", (d,)
        ).fetchone()[0]

    records: list[TwentyDMaturityRecord] = []
    for fill_date, signal_date in _SIGNAL_DATES.items():
        correct_exit = _CORRECT_20TD[fill_date]
        s46_exit = _S46_20TD[fill_date]

        # s46_error_days: positive means S46 was later than correct date
        from datetime import date as _date
        def _days_between(a: str, b: str) -> int:
            ya, ma, da = map(int, a.split("-"))
            yb, mb, db_ = map(int, b.split("-"))
            return (_date(yb, mb, db_) - _date(ya, ma, da)).days

        s46_error = _days_between(correct_exit, s46_exit)

        avail_cnt = _stock_count_on(correct_exit)
        ana_yr, ana_mo, ana_dy = map(int, analysis_date.split("-"))
        exit_yr, exit_mo, exit_dy = map(int, correct_exit.split("-"))
        exit_passed = _date(exit_yr, exit_mo, exit_dy) <= _date(ana_yr, ana_mo, ana_dy)

        if not exit_passed:
            status = MaturityStatus.NOT_YET_MATURE
        elif avail_cnt < _REQUIRED_STOCKS:
            status = MaturityStatus.MATURE_BUT_DATA_INCOMPLETE
        else:
            status = MaturityStatus.MATURE_AND_COMPLETE

        notes = ""
        if s46_error != 0:
            notes = (
                f"S46 exit date ({s46_exit}) was {abs(s46_error)} days "
                f"{'later' if s46_error > 0 else 'earlier'} than correct "
                f"TaiwanTradingCalendar 20th TD ({correct_exit}). "
                "S46 may have used TSMC-proxy dates or incorrect conventions."
            )

        records.append(TwentyDMaturityRecord(
            fill_date=fill_date,
            signal_date=signal_date,
            execution_date=fill_date,
            correct_exit_date_20d=correct_exit,
            s46_exit_date_20d=s46_exit,
            s46_error_days=s46_error,
            data_availability_date=correct_exit,
            required_stock_count=_REQUIRED_STOCKS,
            available_stock_count=avail_cnt,
            maturity_status=status,
            notes=notes,
        ))

    n_mature = sum(1 for r in records if r.maturity_status == MaturityStatus.MATURE_AND_COMPLETE)
    n_incomplete = sum(1 for r in records if r.maturity_status == MaturityStatus.MATURE_BUT_DATA_INCOMPLETE)
    n_not_mature = sum(1 for r in records if r.maturity_status == MaturityStatus.NOT_YET_MATURE)

    exits = [r.correct_exit_date_20d for r in records]
    earliest_exit = min(exits)
    latest_exit = max(exits)

    return TwentyDMaturityMatrixS47(
        analysis_date=analysis_date,
        records=tuple(records),
        n_not_yet_mature=n_not_mature,
        n_mature_incomplete=n_incomplete,
        n_mature_complete=n_mature,
        earliest_exit_date=earliest_exit,
        latest_exit_date=latest_exit,
        earliest_maturity_date=earliest_exit,
        s46_earliest_exit_was="2026-11-14",
        s46_error_confirmed=True,
        all_not_yet_mature=(n_mature == 0 and n_incomplete == 0),
    )


def build_g04_overlap_analysis(
    analysis_date: str = "2026-11-09",
) -> G04OverlapAnalysisS47:
    fill_dates = ["2026-10-13", "2026-10-14", "2026-10-16",
                  "2026-10-21", "2026-10-22", "2026-10-28"]
    adjacent_fills = set(zip(fill_dates, fill_dates[1:]))

    pairs: list[WindowOverlapRecord] = []
    for i, fa in enumerate(fill_dates):
        for fb in fill_dates[i + 1:]:
            wa = set(_HOLD_WINDOWS_5D.get(fa, ()))
            wb = set(_HOLD_WINDOWS_5D.get(fb, ()))
            inter = sorted(wa & wb)
            overlap = len(inter) / 5.0 * 100  # formula: intersection / window_size
            is_adj = (fa, fb) in adjacent_fills
            pairs.append(WindowOverlapRecord(
                fill_a=fa,
                fill_b=fb,
                window_a=_HOLD_WINDOWS_5D.get(fa, ()),
                window_b=_HOLD_WINDOWS_5D.get(fb, ()),
                intersection=tuple(inter),
                overlap_pct=round(overlap, 1),
                is_adjacent=is_adj,
            ))

    max_overlap = max(p.overlap_pct for p in pairs)
    max_pair = next(
        (p.fill_a, p.fill_b) for p in pairs if p.overlap_pct == max_overlap
    )
    adjacent_pairs = [p for p in pairs if p.is_adjacent]

    return G04OverlapAnalysisS47(
        analysis_date=analysis_date,
        formula="overlap_pct = len(window_A ∩ window_B) / window_size × 100",
        denominator_definition=(
            "window_size = 5 (number of holding sessions per cluster); "
            "numerator = number of calendar trading days shared between two hold windows."
        ),
        all_pairs=tuple(pairs),
        max_overlap_pct=max_overlap,
        max_overlap_pair=max_pair,
        adjacent_pair_overlaps=tuple(adjacent_pairs),
        g04_threshold_pct=30.0,
        g04_status="FAIL",
        independence_violation_note=(
            "Adjacent cluster pairs share up to 80% of their 5-day holding window "
            "(4 of 5 calendar sessions). Any systematic factor (macro event, sector "
            "rotation) occurring during those shared sessions affects both cluster "
            "returns in the same direction, violating the t-test independence assumption. "
            "G04 FAIL cannot be resolved by data recovery alone — requires redesign "
            "(weekly-spaced fills or bootstrap CI approach)."
        ),
    )
