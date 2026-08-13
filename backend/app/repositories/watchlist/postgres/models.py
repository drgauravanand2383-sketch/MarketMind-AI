"""SQLAlchemy ORM models for persisted watchlists.

Maps `Watchlist`/`WatchlistItem`/`WatchlistSnapshot` to PostgreSQL tables.
No business logic — a pure persistence mapping. `(watchlist_id, ticker)` is
database-uniqueness-constrained as defense in depth alongside the service
layer's own duplicate-ticker check.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

__all__ = ["Base", "WatchlistModel", "WatchlistItemModel", "WatchlistSnapshotModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Watchlist Repository's models."""


class WatchlistModel(Base):
    """The PostgreSQL table backing a watchlist's own metadata."""

    __tablename__ = "watchlists"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items: Mapped[list[WatchlistItemModel]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan", order_by="WatchlistItemModel.added_at"
    )


class WatchlistItemModel(Base):
    """The PostgreSQL table backing one tracked company within a watchlist."""

    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "ticker", name="uq_watchlist_item_ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[str] = mapped_column(
        String, ForeignKey("watchlists.id"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String, nullable=False, index=True)
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    sector: Mapped[str | None] = mapped_column(String, nullable=True)
    theme: Mapped[str | None] = mapped_column(String, nullable=True)
    source_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    watchlist: Mapped[WatchlistModel] = relationship(back_populates="items")


class WatchlistSnapshotModel(Base):
    """The PostgreSQL table backing a watchlist's append-only snapshot history."""

    __tablename__ = "watchlist_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[str] = mapped_column(
        String, ForeignKey("watchlists.id"), nullable=False, index=True
    )
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_companies: Mapped[int] = mapped_column(Integer, nullable=False)
    average_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str] = mapped_column(String, nullable=False)
