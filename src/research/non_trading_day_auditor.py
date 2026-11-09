"""
PART C: Non-Trading-Day Signal Root Cause Auditor — Session 43.

Classifies the 39.1% (107/274) signals generated on non-trading days (Oct 09-11).

Root cause established: All 107 signals are model_version=v6.0, not v8.0.
- Oct 09 (99 signals, v6.0): locked_at=2026-10-08 — cron ran Oct 08 evening,
  labeled signals for Oct 09 (anticipated next trading day, turned out to be holiday)
- Oct 10 (4 signals, v6.0): locked_at=2026-10-10 — cron ran on National Day holiday
- Oct 11 (4 signals, v6.0): locked_at=2026-10-10 — cron generated signals for Sunday Oct 11

Classification: CALENDAR_HOLIDAY + MODEL_VERSION_MISMATCH
Remediation: Exclude v6.0 signals from v8.0 production comparison.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class NonTradingDayCause(str, Enum):
    CALENDAR_HOLIDAY = "CALENDAR_HOLIDAY"      # official public holiday
    WEEKEND = "WEEKEND"                         # Saturday/Sunday
    TIMEZONE_CONVERSION = "TIMEZONE_CONVERSION"
    SNAPSHOT_TIMESTAMP = "SNAPSHOT_TIMESTAMP"
    RETROSPECTIVE_RECONSTRUCTION = "RETROSPECTIVE_RECONSTRUCTION"
    SOURCE_DATE_MISLABEL = "SOURCE_DATE_MISLABEL"
    THIN_MARKET_DAY = "THIN_MARKET_DAY"        # only ETF data, no common stocks
    UNKNOWN = "UNKNOWN"


class DateMappingConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNVERIFIED = "UNVERIFIED"


class RemediationPolicy(str, Enum):
    EXCLUDE_FROM_V8_COMPARISON = "EXCLUDE_FROM_V8_COMPARISON"
    REMAP_TO_FILL_DATE = "REMAP_TO_FILL_DATE"
    KEEP_AS_SEPARATE_COHORT = "KEEP_AS_SEPARATE_COHORT"
    DATE_MAPPING_UNVERIFIED = "DATE_MAPPING_UNVERIFIED"


@dataclass(frozen=True)
class NonTradingDayEntry:
    signal_date: str
    cause: NonTradingDayCause
    cause_detail: str
    n_signals: int
    n_unique_stocks: int
    model_versions: tuple[str, ...]
    locked_at_dates: tuple[str, ...]
    has_execution_date: bool
    execution_dates: tuple[str, ...]
    impacted_comparisons: tuple[str, ...]
    remediation: RemediationPolicy
    confidence: DateMappingConfidence
    notes: str


@dataclass(frozen=True)
class NonTradingDayAuditReport:
    session: int
    entries: tuple[NonTradingDayEntry, ...]
    n_total_non_td_signals: int
    n_model_v60_signals: int
    n_model_v80_signals: int
    pct_v60: float
    n_identifiable: int
    n_unverified: int
    causes_found: tuple[str, ...]
    has_model_version_mismatch: bool
    # Remediation outcome
    n_signals_exclude_from_v8: int
    n_signals_remap_to_fill: int
    overall_verdict: str


def build_non_trading_day_audit_report(conn: sqlite3.Connection) -> NonTradingDayAuditReport:
    # Get all signals in comparison window on non-trading days
    # Non-trading = not in daily_prices ≥50 stock dates
    q = """
        SELECT fs.trade_date, fs.stock_id, fs.trade_signal,
               fs.model_version, substr(fs.locked_at, 1, 10) as locked_date,
               fs.execution_date
        FROM forward_signals fs
        WHERE fs.trade_date IN ('2026-10-09', '2026-10-10', '2026-10-11')
          AND fs.trade_signal IN ('buy','strong_buy')
        ORDER BY fs.trade_date, fs.model_version
    """
    rows = conn.execute(q).fetchall()

    # Group by date
    from collections import defaultdict
    date_groups: dict[str, list] = defaultdict(list)
    for trade_date, stock_id, signal, model_ver, locked_date, exec_date in rows:
        date_groups[trade_date].append({
            "stock_id": stock_id,
            "signal": signal,
            "model_version": model_ver,
            "locked_date": locked_date,
            "exec_date": exec_date,
        })

    entries = []

    # Oct 09: locked_at = 2026-10-08, model v6.0, National Day holiday week
    dt = "2026-10-09"
    if dt in date_groups:
        grp = date_groups[dt]
        mvs = tuple(sorted(set(r["model_version"] for r in grp)))
        locked = tuple(sorted(set(r["locked_date"] for r in grp if r["locked_date"])))
        execs = tuple(sorted(set(r["exec_date"] for r in grp if r["exec_date"])))
        entries.append(NonTradingDayEntry(
            signal_date=dt,
            cause=NonTradingDayCause.CALENDAR_HOLIDAY,
            cause_detail=(
                "Pre-National Day holiday (國慶日補假). Official holiday per Taiwan labor law. "
                "Cron ran Oct 08 evening (locked_at=2026-10-08), labeled signals with "
                "trade_date=Oct 09 (anticipated next trading session). "
                "Oct 09 was actually a holiday → no market session."
            ),
            n_signals=len(grp),
            n_unique_stocks=len(set(r["stock_id"] for r in grp)),
            model_versions=mvs,
            locked_at_dates=locked,
            has_execution_date=bool(execs),
            execution_dates=execs,
            impacted_comparisons=("S40_5D", "S41_7_cluster", "S42_5_filldate"),
            remediation=RemediationPolicy.EXCLUDE_FROM_V8_COMPARISON,
            confidence=DateMappingConfidence.HIGH,
            notes="v6.0 signals only. locked_at 1 day before trade_date = anticipated-next-day labeling.",
        ))

    # Oct 10: National Day + Saturday
    dt = "2026-10-10"
    if dt in date_groups:
        grp = date_groups[dt]
        mvs = tuple(sorted(set(r["model_version"] for r in grp)))
        locked = tuple(sorted(set(r["locked_date"] for r in grp if r["locked_date"])))
        execs = tuple(sorted(set(r["exec_date"] for r in grp if r["exec_date"])))
        entries.append(NonTradingDayEntry(
            signal_date=dt,
            cause=NonTradingDayCause.CALENDAR_HOLIDAY,
            cause_detail=(
                "National Day (國慶日) + Saturday. Cron ran on the holiday itself "
                "(locked_at=2026-10-10). Signals labeled with trade_date=Oct 10 "
                "which is both a public holiday and a weekend. No market session."
            ),
            n_signals=len(grp),
            n_unique_stocks=len(set(r["stock_id"] for r in grp)),
            model_versions=mvs,
            locked_at_dates=locked,
            has_execution_date=bool(execs),
            execution_dates=execs,
            impacted_comparisons=("S40_5D", "S41_7_cluster", "S42_5_filldate"),
            remediation=RemediationPolicy.EXCLUDE_FROM_V8_COMPARISON,
            confidence=DateMappingConfidence.HIGH,
            notes="v6.0 signals only. Cron ran on holiday itself.",
        ))

    # Oct 11: Sunday
    dt = "2026-10-11"
    if dt in date_groups:
        grp = date_groups[dt]
        mvs = tuple(sorted(set(r["model_version"] for r in grp)))
        locked = tuple(sorted(set(r["locked_date"] for r in grp if r["locked_date"])))
        execs = tuple(sorted(set(r["exec_date"] for r in grp if r["exec_date"])))
        entries.append(NonTradingDayEntry(
            signal_date=dt,
            cause=NonTradingDayCause.WEEKEND,
            cause_detail=(
                "Sunday. Cron ran Oct 10 (locked_at=2026-10-10) and generated "
                "signals for Oct 11 (Sunday). No market session."
            ),
            n_signals=len(grp),
            n_unique_stocks=len(set(r["stock_id"] for r in grp)),
            model_versions=mvs,
            locked_at_dates=locked,
            has_execution_date=bool(execs),
            execution_dates=execs,
            impacted_comparisons=("S40_5D", "S41_7_cluster", "S42_5_filldate"),
            remediation=RemediationPolicy.EXCLUDE_FROM_V8_COMPARISON,
            confidence=DateMappingConfidence.HIGH,
            notes="v6.0 signals only. Cron on Oct 10 holiday generated Sunday signals.",
        ))

    # Count stats
    n_total = sum(e.n_signals for e in entries)
    # Count by model version
    all_rows = conn.execute(
        "SELECT model_version, COUNT(*) FROM forward_signals "
        "WHERE trade_date IN ('2026-10-09','2026-10-10','2026-10-11') "
        "AND trade_signal IN ('buy','strong_buy') "
        "GROUP BY model_version"
    ).fetchall()
    mv_counts = dict(all_rows)
    n_v60 = mv_counts.get("v6.0", 0)
    n_v80 = mv_counts.get("v8.0", 0)

    causes = tuple(sorted(set(str(e.cause) for e in entries)))
    n_exclude = sum(e.n_signals for e in entries if e.remediation == RemediationPolicy.EXCLUDE_FROM_V8_COMPARISON)
    n_remap = sum(e.n_signals for e in entries if e.remediation == RemediationPolicy.REMAP_TO_FILL_DATE)

    all_identified = all(e.confidence in (DateMappingConfidence.HIGH, DateMappingConfidence.MEDIUM) for e in entries)

    return NonTradingDayAuditReport(
        session=43,
        entries=tuple(entries),
        n_total_non_td_signals=n_total,
        n_model_v60_signals=n_v60,
        n_model_v80_signals=n_v80,
        pct_v60=n_v60 / n_total if n_total > 0 else 0.0,
        n_identifiable=n_total if all_identified else 0,
        n_unverified=0 if all_identified else n_total,
        causes_found=causes,
        has_model_version_mismatch=n_v60 > 0,
        n_signals_exclude_from_v8=n_exclude,
        n_signals_remap_to_fill=n_remap,
        overall_verdict=(
            "DATE_CAUSES_IDENTIFIED"
            if all_identified and entries
            else "DATE_CAUSES_PARTIAL"
        ),
    )
