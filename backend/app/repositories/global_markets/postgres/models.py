"""SQLAlchemy ORM model for a persisted Global Market Intelligence run.

`category_outcomes` is stored as a JSON column, not normalized into a
separate table — the same rationale as every other JSON-backed repository
in this codebase (Risk's `risk_metrics`/`exposures`, Screening, Signals,
Alerts, Recommendations, Strategy): Phase 1 needs no cross-run querying
of individual category outcomes, only "what happened in run X."
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "GlobalMarketIntelligenceRunModel", "RankedAssetModel", "IntelligenceReportModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Global Market Intelligence Run Repository's models."""


class GlobalMarketIntelligenceRunModel(Base):
    """The PostgreSQL table backing one Global Market Intelligence run.

    `UniqueConstraint("run_date")` is the database-level enforcement of
    "no duplicate report for the same run/date" — a second `create_run`
    for an already-used `run_date` fails at the database, not merely by
    application-level convention.
    """

    __tablename__ = "global_market_intelligence_runs"
    __table_args__ = (UniqueConstraint("run_date", name="uq_global_market_run_date"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    category_outcomes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    triggered_by: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)


class RankedAssetModel(Base):
    """The PostgreSQL table backing one persisted `RankedAsset` row.

    `id` is deterministically derived as `"{run_id}:{category}:{ticker}"`
    (see `app.repositories.global_markets.postgres.mapper.ranked_asset_id`)
    rather than a generated UUID — this makes the primary key itself the
    uniqueness constraint for "(run, category, ticker)" with no separate
    `UniqueConstraint` needed, and makes `replace_ranked_assets`'s
    delete-then-insert semantics trivially collision-free.
    """

    __tablename__ = "global_market_ranked_assets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    factor_scores: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    performance_windows: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    risk_classification: Mapped[str | None] = mapped_column(String, nullable=True, default=None)


class IntelligenceReportModel(Base):
    """The PostgreSQL table backing one persisted `CategoryIntelligenceReport` row.

    `id` is deterministically derived as `"{run_id}:{category}"` (see
    `app.repositories.global_markets.postgres.mapper.intelligence_report_id`)
    — one report per category per run, the same composite-string-as-PK
    approach `RankedAssetModel` already uses for the same reason: the
    primary key itself is the uniqueness constraint, and `save_report`'s
    upsert semantics are collision-free by construction.
    """

    __tablename__ = "global_market_intelligence_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    overall_summary: Mapped[str] = mapped_column(String, nullable=False)
    asset_commentaries: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    risk_note: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
