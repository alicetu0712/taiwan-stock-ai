"""
research/models.py — V2 Shadow Tables (append-only research data)

ISOLATION RULE: ResearchBase is a SEPARATE DeclarativeBase.
  - Never imported into src/database.py
  - Never passed to init_db()
  - Tables created only via scripts/migrate_entry_timing_v2.py (manual)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ResearchBase(DeclarativeBase):
    """Separate base — deliberately isolated from production Base."""
    pass


class V2ShadowSignal(ResearchBase):
    """
    One row per (trade_date, stock_id) capturing the V2 entry timing label
    alongside the v8.0 decision label for direct comparison.

    Append-only: never UPDATE existing rows.
    """

    __tablename__ = "v2_shadow_signals"
    __table_args__ = (
        UniqueConstraint(
            "trade_date", "stock_id", name="uq_v2ss_date_stock"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    stock_id: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # V8.0 (V1) signal snapshot — copied from ForwardSignal, never modified
    v1_decision_label: Mapped[Optional[str]] = mapped_column(String(30))
    v1_pt_score: Mapped[Optional[float]] = mapped_column(Float)
    v1_setup_type: Mapped[Optional[str]] = mapped_column(String(20))

    # V2 entry timing output
    entry_label: Mapped[Optional[str]] = mapped_column(String(30))
    dist_to_resistance_pct: Mapped[Optional[float]] = mapped_column(Float)
    ma20_gap_pct: Mapped[Optional[float]] = mapped_column(Float)
    rr_ratio: Mapped[Optional[float]] = mapped_column(Float)
    vol_ratio: Mapped[Optional[float]] = mapped_column(Float)
    prior_20d_high: Mapped[Optional[float]] = mapped_column(Float)
    stop_price: Mapped[Optional[float]] = mapped_column(Float)
    target_price: Mapped[Optional[float]] = mapped_column(Float)
    entry_price: Mapped[Optional[float]] = mapped_column(Float)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    data_bars: Mapped[Optional[int]] = mapped_column(Integer)
    reasons_json: Mapped[Optional[str]] = mapped_column(String(500))


class V2ShadowOutcome(ResearchBase):
    """
    Post-hoc outcome for a V2ShadowSignal.
    Linked to V2ShadowSignal via (trade_date, stock_id).

    Append-only: outcome rows are written once; never modifies the signal row.
    """

    __tablename__ = "v2_shadow_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "trade_date", "stock_id", name="uq_v2so_date_stock"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    stock_id: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # What actually happened
    fwd_return_20d: Mapped[Optional[float]] = mapped_column(Float)
    fwd_return_60d: Mapped[Optional[float]] = mapped_column(Float)
    max_drawdown_pct: Mapped[Optional[float]] = mapped_column(Float)   # max adverse excursion
    stop_hit: Mapped[Optional[bool]] = mapped_column(Boolean)
    target_hit: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Comparison context
    v1_fwd_return_20d: Mapped[Optional[float]] = mapped_column(Float)   # from ForwardSignal
    v1_fwd_return_60d: Mapped[Optional[float]] = mapped_column(Float)

    filled_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
