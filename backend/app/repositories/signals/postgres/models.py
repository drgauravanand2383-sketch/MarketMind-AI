"""SQLAlchemy ORM model for persisted signal definitions.

`conditions`/`groups` are stored as JSON columns rather than normalized
into separate relational tables — same rationale as
`app.repositories.screening.postgres.models.ScreeningProfileModel`:
`SignalCondition.value` is deliberately polymorphic (a scalar, a
`[low, high]` pair, or a list, depending on `operator`), and no
cross-definition querying of individual conditions is required.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "SignalDefinitionModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Signal Definition Repository's models."""


class SignalDefinitionModel(Base):
    """The PostgreSQL table backing a signal definition's stored definition."""

    __tablename__ = "signal_definitions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    category: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[str] = mapped_column(String, nullable=False)
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    groups: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
