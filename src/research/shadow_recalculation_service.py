"""
shadow_recalculation_service.py — Recalculate entry timing labels with fixed _load_history.

SAFETY:
  - Writes ONLY to v2_shadow_signals (research schema).
  - Reads DailyPrice from production via prod_session (read-only intent).
  - Never writes to ForwardSignal, ActualPosition, or any production table.
  - New rows tagged research_version='v2_research_v2', is_legacy=False.

Usage:
  svc = ShadowRecalculationService()
  report = svc.recalculate(
      research_session=<session on research DB>,
      prod_session=<read-only session on production DB>,
      from_date=date(2026, 1, 1),
      to_date=date(2026, 10, 31),
      dry_run=False,
  )
  print(report.summary())
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

RESEARCH_V2 = "v2_research_v2"


@dataclass
class LabelChange:
    trade_date: date
    stock_id: str
    v1_label: Optional[str]      # entry_label from v2_research_v1
    v2_label: Optional[str]      # entry_label from new v2_research_v2 row
    v1_data_bars: Optional[int]
    v2_data_bars: Optional[int]


@dataclass
class RecalcReport:
    processed: int = 0
    skipped: int = 0        # already have v2_research_v2 row
    errors: int = 0         # insufficient history (< 21 bars)
    label_changes: List[LabelChange] = field(default_factory=list)
    missing_data: List[str] = field(default_factory=list)   # "{date}/{stock_id}: reason"
    input_data_cutoff: Optional[date] = None
    calculation_ts: Optional[datetime] = None
    dry_run: bool = False

    def summary(self) -> str:
        changed = len(self.label_changes)
        lines = [
            f"ShadowRecalc v2_research_v2 {'[DRY RUN]' if self.dry_run else ''}",
            f"  processed={self.processed} skipped={self.skipped} errors={self.errors}",
            f"  label_changes={changed}",
            f"  input_cutoff={self.input_data_cutoff}  calc_ts={self.calculation_ts}",
        ]
        for c in self.label_changes[:10]:
            lines.append(f"    {c.trade_date}/{c.stock_id}: {c.v1_label!r} → {c.v2_label!r}")
        if changed > 10:
            lines.append(f"    ... +{changed - 10} more")
        return "\n".join(lines)


class ShadowRecalculationService:
    """
    Re-runs entry timing analysis for all v2_research_v1 rows in [from_date, to_date],
    writing new v2_research_v2 rows with the corrected _load_history logic.
    """

    def recalculate(
        self,
        research_session,
        prod_session,
        from_date: date,
        to_date: date,
        dry_run: bool = False,
    ) -> RecalcReport:
        """
        research_session: writable session on the research database (V2ShadowSignal lives here).
        prod_session:     read-only session on the production database (DailyPrice lives here).
        """
        from sqlalchemy.exc import IntegrityError

        from src.analyzers.entry_timing import EntryTimingAnalyzer
        from src.database import DailyPrice
        from src.research.models import V2ShadowSignal

        report = RecalcReport(
            input_data_cutoff=to_date,
            calculation_ts=datetime.utcnow(),
            dry_run=dry_run,
        )
        analyzer = EntryTimingAnalyzer()

        # Fetch all v2_research_v1 rows in range
        v1_rows = (
            research_session.query(V2ShadowSignal)
            .filter(
                V2ShadowSignal.research_version == "v2_research_v1",
                V2ShadowSignal.trade_date >= from_date,
                V2ShadowSignal.trade_date <= to_date,
            )
            .order_by(V2ShadowSignal.trade_date, V2ShadowSignal.stock_id)
            .all()
        )

        for v1 in v1_rows:
            # Skip if v2_research_v2 row already exists (idempotent)
            already = (
                research_session.query(V2ShadowSignal)
                .filter(
                    V2ShadowSignal.trade_date == v1.trade_date,
                    V2ShadowSignal.stock_id == v1.stock_id,
                    V2ShadowSignal.research_version == RESEARCH_V2,
                )
                .first()
            )
            if already:
                report.skipped += 1
                continue

            # Load corrected history from production DB
            history = self._load_history(prod_session, v1.stock_id, v1.trade_date)
            if history is None or len(history) < 21:
                report.errors += 1
                reason = "no_data" if history is None else f"only_{len(history)}_bars"
                report.missing_data.append(
                    f"{v1.trade_date}/{v1.stock_id}: {reason}"
                )
                continue

            result = analyzer.analyze(v1.stock_id, history)

            if not dry_run:
                v2_row = V2ShadowSignal(
                    trade_date=v1.trade_date,
                    stock_id=v1.stock_id,
                    research_version=RESEARCH_V2,
                    is_legacy=False,
                    v1_decision_label=v1.v1_decision_label,
                    v1_pt_score=v1.v1_pt_score,
                    v1_setup_type=v1.v1_setup_type,
                    entry_label=result.entry_label,
                    dist_to_resistance_pct=result.dist_to_resistance_pct,
                    ma20_gap_pct=result.ma20_gap_pct,
                    rr_ratio=result.rr_ratio,
                    vol_ratio=result.vol_ratio,
                    prior_20d_high=result.prior_20d_high,
                    stop_price=result.stop_price,
                    target_price=result.target_price,
                    entry_price=result.entry_price,
                    data_bars=result.data_bars,
                    reasons_json=json.dumps(result.reasons, ensure_ascii=False)[:500],
                )
                try:
                    research_session.add(v2_row)
                    research_session.commit()
                    report.processed += 1
                except IntegrityError:
                    research_session.rollback()
                    report.skipped += 1
                    continue
            else:
                report.processed += 1

            # Track if entry_label changed
            if result.entry_label != v1.entry_label:
                report.label_changes.append(
                    LabelChange(
                        trade_date=v1.trade_date,
                        stock_id=v1.stock_id,
                        v1_label=v1.entry_label,
                        v2_label=result.entry_label,
                        v1_data_bars=v1.data_bars,
                        v2_data_bars=result.data_bars,
                    )
                )

        return report

    def _load_history(self, prod_session, stock_id: str, as_of: date, lookback: int = 90):
        """
        Load the most-recent `lookback` bars ending on as_of from production DailyPrice.
        Uses DESC+LIMIT to get the NEWEST rows, then reverses to chronological order.
        This is the fixed version; v2_research_v1 used ASC+LIMIT (bug — got oldest bars).
        """
        import pandas as pd
        from sqlalchemy import desc

        from src.database import DailyPrice

        rows = (
            prod_session.query(DailyPrice)
            .filter(DailyPrice.stock_id == stock_id)
            .filter(DailyPrice.date <= as_of)
            .order_by(desc(DailyPrice.date))
            .limit(lookback)
            .all()
        )
        if not rows:
            return None
        rows = list(reversed(rows))
        return pd.DataFrame(
            [
                {
                    "date": r.date,
                    "close": r.close,
                    "high": r.high if r.high else r.close,
                    "low": r.low if r.low else r.close,
                    "volume": r.volume if r.volume else 0,
                }
                for r in rows
            ]
        )
