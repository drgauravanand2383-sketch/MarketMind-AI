"""SQLAlchemy ORM models for persisted alert rules and alerts.

`conditions`/`channels` are stored as JSON columns rather than normalized
into separate relational tables — same rationale as
`app.repositories.screening.postgres.models.ScreeningProfileModel`:
`AlertCondition.value` is deliberately polymorphic, and no cross-rule
querying of individual conditions is required.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "AlertRuleModel", "AlertModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Alert Rule / Alert Repositories' models."""


class AlertRuleModel(Base):
    """The PostgreSQL table backing an alert rule's stored definition."""

    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[str] = mapped_column(String, nullable=False)
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repeat_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    channels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AlertModel(Base):
    """The PostgreSQL table backing one generated or suppressed alert."""

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    rule_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False, index=True)
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    signal_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    eligible_channels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
