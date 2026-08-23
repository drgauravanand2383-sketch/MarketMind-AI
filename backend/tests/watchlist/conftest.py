"""Shared fixtures for Watchlist Intelligence Engine service-layer tests.

`service` is wired to a genuine `PostgresWatchlistRepository` running
against an in-memory SQLite database (via aiosqlite) — the same pattern
`tests/repositories/knowledge/postgres/test_repository.py` already uses —
so these tests exercise real persistence, not a hand-rolled fake.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.watchlist.postgres.models import Base
from app.repositories.watchlist.postgres.repository import PostgresWatchlistRepository
from app.watchlist.models import WatchlistItem
from app.watchlist.service import WatchlistService

NOW = datetime(2026, 8, 6, tzinfo=UTC)


@pytest.fixture
async def repository() -> AsyncIterator[PostgresWatchlistRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresWatchlistRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def service(repository: PostgresWatchlistRepository) -> WatchlistService:
    return WatchlistService(repository)


def make_item(ticker: str = "AAPL", **overrides: object) -> WatchlistItem:
    defaults: dict[str, object] = {"ticker": ticker, "added_at": NOW}
    defaults.update(overrides)
    return WatchlistItem(**defaults)
