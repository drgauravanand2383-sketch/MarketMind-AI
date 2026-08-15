"""SQLAlchemy ORM models for persisted strategies and strategy evaluation results.

`weightings`/`rules` and `strategy_matches`/`summary` are stored as JSON
columns rather than normalized into separate relational tables — the same
rationale as every other JSON-backed repository in this codebase
(Screening, Signals, Alerts, Recommendations): `StrategyRule.value` is
deliberately polymorphic, and no cross-strategy querying of individual
rules is required this sprint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "InvestmentStrategyModel", "StrategyEvaluationResultModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Strategy Repository's models."""


class InvestmentStrategyModel(Base):
    """The PostgreSQL table backing a strategy's stored definition."""

    __tablename__ = "investment_strategies"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    strategy_type: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    weightings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StrategyEvaluationResultModel(Base):
    """The PostgreSQL table backing one generated strategy evaluation
    result. Autoincrement primary key (not `request_id`) since a request
    may be re-evaluated, producing more than one stored result over time."""

    __tablename__ = "strategy_evaluation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    overall_alignment: Mapped[float] = mapped_column(Float, nullable=False)
    best_strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    strategy_matches: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # Milestone 16 §12: nullable/additive, same shape and rationale as
    # `RiskAssessmentModel.market_data_coverage` (Milestone 14 §5) — see
    # `app.strategy.models.StrategyEvaluationResult.recommendation_result_id`.
    recommendation_result_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
