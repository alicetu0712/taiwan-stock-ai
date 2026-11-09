"""
PART C: Research Observation Unit Auditor — Session 42.

Reconstructs correct clustering by fill_date instead of signal_date.
Key insight: signals generated on non-trading days (Oct 09, 10, 11) all fill
on Oct 12 → these 3 dates form a single fill-date cluster.

Result: 5 fill-date clusters (not 7 signal-date clusters as used in S41).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class FillDateCluster:
    fill_date: str
    signal_dates: tuple[str, ...]    # signal trade_dates that map here
    n_signals: int
    contains_non_trading_day_signals: bool
    # 5D window
    window_start: str
    window_end: str
    # Overlap with adjacent clusters
    overlaps_next: bool
    overlap_days_next: int


@dataclass(frozen=True)
class ObservationUnitAuditReport:
    session: int
    s41_cluster_method: str         # "signal_date — 7 clusters"
    s42_cluster_method: str         # "fill_date — 5 clusters"
    clusters: tuple[FillDateCluster, ...]
    n_clusters_signal_date: int     # 7 (S41)
    n_clusters_fill_date: int       # 5 (S42 corrected)
    n_signals_non_trading_absorbed: int  # 107 absorbed into cluster 1
    n_overlapping_cluster_pairs: int
    effective_independent_n: int    # pessimistic (accounting for overlap)
    observation_unit_verdict: str


def _get_nth_trading_day(start_date: str, n: int, trading_days: list[str]) -> str:
    after = [d for d in trading_days if d > start_date]
    if len(after) >= n:
        return after[n - 1]
    return after[-1] if after else start_date


def _count_overlap_days(start1: str, end1: str, start2: str, end2: str) -> int:
    from datetime import date as date_cls
    s1, e1 = date_cls.fromisoformat(start1), date_cls.fromisoformat(end1)
    s2, e2 = date_cls.fromisoformat(start2), date_cls.fromisoformat(end2)
    overlap_start = max(s1, s2)
    overlap_end = min(e1, e2)
    if overlap_end < overlap_start:
        return 0
    return (overlap_end - overlap_start).days + 1


def build_observation_unit_audit_report(
    conn: sqlite3.Connection,
    comparison_start: str = "2026-10-09",
    comparison_end: str = "2026-10-16",
) -> ObservationUnitAuditReport:
    """
    Reconstruct fill-date clusters for the V3ComparisonEngine CONDITIONAL window.

    Uses execution_date from forward_signals when available (accurate fill date).
    For non-trading-day signals where execution_date IS NULL, falls back to
    the next available trading day from daily_prices.

    Default date range: Oct 09-16 (274 signals, the CONDITIONAL comparison window).
    """
    trading_days = sorted(
        r[0] for r in conn.execute(
            "SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN '2026-10-01' AND '2026-11-30'"
        ).fetchall()
    )
    td_set = set(trading_days)

    def next_td(d: str) -> str:
        for td in trading_days:
            if td > d:
                return td
        return d

    # Get execution_date per (trade_date, signal) for comparison window
    q = """
        SELECT fs.trade_date, fs.execution_date, COUNT(*) as n
        FROM forward_signals fs
        WHERE fs.trade_date BETWEEN ? AND ?
          AND fs.trade_signal IN ('buy','strong_buy')
        GROUP BY fs.trade_date, fs.execution_date
        ORDER BY fs.trade_date
    """
    rows = conn.execute(q, (comparison_start, comparison_end)).fetchall()

    # Build fill_date -> (signal_dates, n, has_non_td)
    fill_groups: dict[str, list] = {}
    date_counts: dict[str, int] = {}
    for trade_date, exec_date, n in rows:
        date_counts[trade_date] = date_counts.get(trade_date, 0) + n
        # Use execution_date if set, else next trading day from daily_prices
        fd = exec_date if exec_date else next_td(trade_date)
        if fd not in fill_groups:
            fill_groups[fd] = {"signal_dates": [], "n": 0, "has_non_td": False}
        if trade_date not in fill_groups[fd]["signal_dates"]:
            fill_groups[fd]["signal_dates"].append(trade_date)
        fill_groups[fd]["n"] += n
        if trade_date not in td_set:
            fill_groups[fd]["has_non_td"] = True

    sorted_fills = sorted(fill_groups.keys())

    # Compute 5D windows for each cluster (fill_date + 4 trading days)
    cluster_windows: list[tuple[str, str]] = []
    for fd in sorted_fills:
        # 5D window: [fill_date, fill_date + 4 more trading days]
        after_fill = [d for d in trading_days if d >= fd]
        window_end = after_fill[4] if len(after_fill) >= 5 else after_fill[-1]
        cluster_windows.append((fd, window_end))

    # Build clusters with overlap info
    clusters = []
    for i, fd in enumerate(sorted_fills):
        g = fill_groups[fd]
        ws, we = cluster_windows[i]
        # overlap with next
        if i + 1 < len(sorted_fills):
            ns, ne = cluster_windows[i + 1]
            ovlp = _count_overlap_days(ws, we, ns, ne)
            overlaps_next = ovlp > 0
        else:
            ovlp = 0
            overlaps_next = False

        clusters.append(FillDateCluster(
            fill_date=fd,
            signal_dates=tuple(sorted(g["signal_dates"])),
            n_signals=g["n"],
            contains_non_trading_day_signals=g["has_non_td"],
            window_start=ws,
            window_end=we,
            overlaps_next=overlaps_next,
            overlap_days_next=ovlp,
        ))

    n_overlapping_pairs = sum(1 for c in clusters if c.overlaps_next)
    # Non-trading day signals absorbed
    n_non_td_absorbed = sum(c.n_signals for c in clusters if c.contains_non_trading_day_signals)

    # Effective N: 5 clusters, but adjacent windows overlap. Pessimistically 3-4.
    effective_n = len(clusters) - n_overlapping_pairs if n_overlapping_pairs < len(clusters) else max(1, len(clusters) // 2)

    return ObservationUnitAuditReport(
        session=42,
        s41_cluster_method="signal_date — 7 clusters (S41)",
        s42_cluster_method="fill_date — 5 clusters (S42 corrected)",
        clusters=tuple(clusters),
        n_clusters_signal_date=7,
        n_clusters_fill_date=len(clusters),
        n_signals_non_trading_absorbed=n_non_td_absorbed,
        n_overlapping_cluster_pairs=n_overlapping_pairs,
        effective_independent_n=effective_n,
        observation_unit_verdict=(
            "OBSERVATION_UNIT_CORRECTED"
            if len(clusters) < 7
            else "OBSERVATION_UNIT_UNCHANGED"
        ),
    )
