"""SQLAlchemy ORM model for persisted knowledge records.

Maps RelationalRecord (from KnowledgeIngestionService) to a PostgreSQL
table. No business logic — a pure persistence mapping.

`published_at` preserves the original, unparsed provenance string exactly
(matching KnowledgeRecord's own "preserve, don't normalize" contract).
`published_at_parsed` and `source` are derived, indexed columns that exist
solely to make date-range and source search efficient — see mapper.py for
how they are derived.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "KnowledgeRecordModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Knowledge Repository's models."""


class KnowledgeRecordModel(Base):
    """The PostgreSQL table backing persisted knowledge records."""

    __tablename__ = "knowledge_records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at_parsed: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    source_provider_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
