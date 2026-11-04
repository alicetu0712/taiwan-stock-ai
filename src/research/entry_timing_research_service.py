"""
entry_timing_research_service.py — Orchestrates V2 shadow signal persistence.

FORBIDDEN: Never modifies ForwardSignal, v8.0 decisions, BUY thresholds,
           ACTUAL/PAPER positions, or any production data.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Tuple

logger = logging.getLogger(__name__)


class EntryTimingResearchService:
    """
    For each (trade_date, stock_id) already in ForwardSignal (v8.0),
    compute the V2 entry timing label and persist to V2ShadowSignal.

    Idempotent: existing rows are skipped (upsert by skip).
    """

    def run_for_date(
        self, trade_date: date, dry_run: bool = False
    ) -> Tuple[int, int, int]:
        """
        Returns (processed, skipped, errors).
        """
        from sqlalchemy.exc import IntegrityError

        from src.analyzers.entry_timing import EntryTimingAnalyzer
        from src.database import ForwardSignal, get_session
        from src.research.models import V2ShadowSignal

        session = get_session()
        analyzer = EntryTimingAnalyzer()
        processed = skipped = errors = 0

        try:
            signals = (
                session.query(ForwardSignal)
                .filter(ForwardSignal.trade_date == trade_date)
                .filter(ForwardSignal.decision_label.isnot(None))
                .all()
            )

            for fs in signals:
                # Skip if already computed
                exists = (
                    session.query(V2ShadowSignal)
                    .filter(
                        V2ShadowSignal.trade_date == trade_date,
                        V2ShadowSignal.stock_id == fs.stock_id,
                    )
                    .first()
                )
                if exists:
                    skipped += 1
                    continue

                history = self._load_history(session, fs.stock_id, trade_date)
                if history is None or len(history) < 21:
                    errors += 1
                    logger.debug(f"{fs.stock_id} @{trade_date}: 歷史資料不足，跳過")
                    continue

                result = analyzer.analyze(fs.stock_id, history)

                if not dry_run:
                    shadow = V2ShadowSignal(
                        trade_date=trade_date,
                        stock_id=fs.stock_id,
                        v1_decision_label=fs.decision_label,
                        v1_pt_score=fs.pt_score,
                        v1_setup_type=fs.setup_type,
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
                        reasons_json=json.dumps(result.reasons, ensure_ascii=False)[
                            :500
                        ],
                    )
                    try:
                        session.add(shadow)
                        session.commit()
                        processed += 1
                    except IntegrityError:
                        session.rollback()
                        skipped += 1
                else:
                    processed += 1
                    logger.debug(
                        f"[dry] {fs.stock_id} @{trade_date}: {result.entry_label}"
                    )

        finally:
            session.close()

        return processed, skipped, errors

    def _load_history(self, session, stock_id: str, as_of: date, lookback: int = 90):
        """Load up to `lookback` bars of OHLCV ending on (and including) as_of."""
        import pandas as pd
        from sqlalchemy import asc

        from src.database import DailyPrice

        rows = (
            session.query(DailyPrice)
            .filter(DailyPrice.stock_id == stock_id)
            .filter(DailyPrice.date <= as_of)
            .order_by(asc(DailyPrice.date))
            .limit(lookback)
            .all()
        )
        if not rows:
            return None
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
