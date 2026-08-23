"""SQLAlchemy async ORM implementation of BaseWatchlistRepository.

PostgresWatchlistRepository persists watchlists, their items, and their
snapshot history into PostgreSQL and retrieves/mutates them through
SQLAlchemy's async ORM. It contains no business logic (duplicate-ticker
prevention, size limits — see `app.watchlist.service.WatchlistService`)
— only translation between domain models and SQL operations, via the
mapper. Written against SQLAlchemy's database-agnostic async engine, the
same shape already used by `PostgresKnowledgeRepository`: a real
PostgreSQL server in production, an in-memory SQLite database (via
aiosqlite) in tests — see `tests/repositories/watchlist/postgres/test_repository.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.repositories.watchlist.postgres.mapper import (
    model_to_snapshot,
    model_to_watchlist,
    watchlist_item_to_model,
    watchlist_to_model,
)
from app.repositories.watchlist.postgres.models import (
    WatchlistModel,
    WatchlistSnapshotModel,
)
from app.repositories.watchlist.repository import BaseWatchlistRepository
from app.watchlist.models import Watchlist, WatchlistItem, WatchlistSnapshot

__all__ = ["PostgresWatchlistRepository"]

_ITEMS = selectinload(WatchlistModel.items)


def _build_summary(name: str, total_companies: int, average_confidence: float | None) -> str:
    """A short, deterministic, rule-based summary — no AI, no market scanning."""
    if total_companies == 0:
        return f"Watchlist {name!r} currently tracks no companies."
    if average_confidence is None:
        return f"Watchlist {name!r} tracks {total_companies} companies with no confidence data recorded."
    return (
        f"Watchlist {name!r} tracks {total_companies} companies "
        f"with an average confidence of {average_confidence:.2f}."
    )


class PostgresWatchlistRepository(BaseWatchlistRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def create_watchlist(self, watchlist: Watchlist) -> Watchlist:
        async with self._session_factory() as session:
            session.add(watchlist_to_model(watchlist))
            await session.commit()
        return watchlist

    async def delete_watchlist(self, watchlist_id: str) -> bool:
        async with self._session_factory() as session:
            model = await session.get(WatchlistModel, watchlist_id)
            existed = model is not None
            if model is not None:
                await session.delete(model)
                await session.commit()
        return existed

    async def rename_watchlist(self, watchlist_id: str, name: str) -> Watchlist | None:
        async with self._session_factory() as session:
            model = await session.get(WatchlistModel, watchlist_id, options=[_ITEMS])
            if model is None:
                return None
            model.name = name
            model.updated_at = datetime.now(UTC)
            await session.commit()
            return model_to_watchlist(model)

    async def list_watchlists(self) -> list[Watchlist]:
        async with self._session_factory() as session:
            stmt = select(WatchlistModel).options(_ITEMS)
            result = await session.execute(stmt)
            models = result.scalars().all()
        return [model_to_watchlist(model) for model in models]

    async def add_company(self, watchlist_id: str, item: WatchlistItem) -> Watchlist | None:
        async with self._session_factory() as session:
            model = await session.get(WatchlistModel, watchlist_id, options=[_ITEMS])
            if model is None:
                return None
            model.items.append(watchlist_item_to_model(item, watchlist_id))
            model.updated_at = datetime.now(UTC)
            await session.commit()
            return model_to_watchlist(model)

    async def remove_company(self, watchlist_id: str, ticker: str) -> Watchlist | None:
        async with self._session_factory() as session:
            model = await session.get(WatchlistModel, watchlist_id, options=[_ITEMS])
            if model is None:
                return None
            model.items = [current for current in model.items if current.ticker != ticker]
            model.updated_at = datetime.now(UTC)
            await session.commit()
            return model_to_watchlist(model)

    async def update_notes(self, watchlist_id: str, ticker: str, notes: str) -> Watchlist | None:
        async with self._session_factory() as session:
            model = await session.get(WatchlistModel, watchlist_id, options=[_ITEMS])
            if model is None:
                return None
            for item_model in model.items:
                if item_model.ticker == ticker:
                    item_model.notes = notes
                    break
            model.updated_at = datetime.now(UTC)
            await session.commit()
            return model_to_watchlist(model)

    async def get_watchlist(self, watchlist_id: str) -> Watchlist | None:
        async with self._session_factory() as session:
            model = await session.get(WatchlistModel, watchlist_id, options=[_ITEMS])
        return model_to_watchlist(model) if model is not None else None

    async def snapshot(self, watchlist_id: str) -> WatchlistSnapshot | None:
        async with self._session_factory() as session:
            model = await session.get(WatchlistModel, watchlist_id, options=[_ITEMS])
            if model is None:
                return None

            confidences = [item.confidence for item in model.items if item.confidence is not None]
            average_confidence = sum(confidences) / len(confidences) if confidences else None
            total_companies = len(model.items)

            snapshot_model = WatchlistSnapshotModel(
                watchlist_id=watchlist_id,
                snapshot_time=datetime.now(UTC),
                total_companies=total_companies,
                average_confidence=average_confidence,
                summary=_build_summary(model.name, total_companies, average_confidence),
            )
            session.add(snapshot_model)
            await session.commit()
            return model_to_snapshot(snapshot_model)

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
