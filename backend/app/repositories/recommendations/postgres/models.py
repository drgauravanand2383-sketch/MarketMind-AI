"""SQLAlchemy ORM models for persisted recommendation requests and results.

`recommendations`/`summary` (and the request's own id-list/context fields)
are stored as JSON columns rather than normalized into separate relational
tables — the same rationale as every other JSON-backed repository in this
codebase (Screening, Signals, Alerts): a `RecommendationCandidate` embeds
deeply nested subsystem outputs (`SignalResult`, `Alert`, `ScreenResult`,
`CompanyResearchReport`, `CompanySummary`), and no cross-request querying
of individual candidate fields is required this sprint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "RecommendationRequestModel", "RecommendationResultModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Recommendation Repository's models."""


class RecommendationRequestModel(Base):
    """The PostgreSQL table backing a recommendation request's stored definition."""

    __tablename__ = "recommendation_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_name: Mapped[str] = mapped_column(String, nullable=False)
    watchlist_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    screening_profile_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    signal_definition_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    alert_rule_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    planning_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    max_recommendations: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    minimum_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecommendationResultModel(Base):
    """The PostgreSQL table backing one generated recommendation result.
    Autoincrement primary key (not `request_id`) since a request may be
    re-run, producing more than one stored result over time."""

    __tablename__ = "recommendation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    total_candidates: Mapped[int] = mapped_column(Integer, nullable=False)
    recommendations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
