"""SQLAlchemy ORM model for persisted screening profiles.

`filters`/`groups` are stored as JSON columns rather than normalized into
separate relational tables — `ScreenFilter.value` is deliberately
polymorphic (a scalar, a `[low, high]` pair, or a list, depending on
`operator`), and no cross-profile querying of individual filters is
required. This mirrors the same "structured JSON for flexible, nested
data" pattern `KnowledgeRecordModel.source_metadata`/`.raw` already use in
this codebase — not a new technology.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "ScreeningProfileModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Screening Repository's models."""


class ScreeningProfileModel(Base):
    """The PostgreSQL table backing a screening profile's stored definition."""

    __tablename__ = "screening_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    filters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    groups: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
