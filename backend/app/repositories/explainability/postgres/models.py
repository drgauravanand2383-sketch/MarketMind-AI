"""SQLAlchemy ORM models for persisted explainability requests and results.

`recommendation_explanations`/`strategy_explanations`/`risk_explanation`/
`performance_attribution` are stored as JSON columns rather than
normalized into separate relational tables — the same rationale as every
other JSON-backed repository in this codebase (Screening, Signals,
Alerts, Recommendations, Strategy, Risk, Backtesting): no cross-request
querying of individual explanations is required this sprint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "ExplainabilityRequestModel", "ExplainabilityResultModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Explainability Repository's models."""


class ExplainabilityRequestModel(Base):
    """The PostgreSQL table backing an explainability request's stored definition."""

    __tablename__ = "explainability_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    recommendation_result_id: Mapped[str] = mapped_column(String, nullable=False)
    strategy_evaluation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    risk_assessment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    backtest_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExplainabilityResultModel(Base):
    """The PostgreSQL table backing one generated explainability result.
    Autoincrement primary key (not `request_id`) since a request may be
    re-explained, producing more than one stored result over time."""

    __tablename__ = "explainability_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    recommendation_explanations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    strategy_explanations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    risk_explanation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    performance_attribution: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    overall_summary: Mapped[str] = mapped_column(String, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
