"""SQLAlchemy ORM models for persisted risk assessment requests and results.

`risk_metrics`/`exposures`/`recommendations` are stored as JSON columns
rather than normalized into separate relational tables — the same
rationale as every other JSON-backed repository in this codebase
(Screening, Signals, Alerts, Recommendations, Strategy): no cross-request
querying of individual metrics/exposures is required this sprint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "RiskAssessmentRequestModel", "RiskAssessmentModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Risk Analytics Repository's models."""


class RiskAssessmentRequestModel(Base):
    """The PostgreSQL table backing a risk assessment request's stored definition."""

    __tablename__ = "risk_assessment_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_name: Mapped[str] = mapped_column(String, nullable=False)
    portfolio_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    strategy_evaluation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    recommendation_result_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RiskAssessmentModel(Base):
    """The PostgreSQL table backing one generated risk assessment.
    Autoincrement primary key (not `request_id`) since a request may be
    re-assessed, producing more than one stored assessment over time."""

    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    overall_risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    overall_severity: Mapped[str] = mapped_column(String, nullable=False)
    risk_metrics: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    exposures: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    recommendations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
