"""Tests for PostgresWatchlistRepository.

Run against an in-memory SQLite database via aiosqlite (a dev-only test
dependency) rather than a live PostgreSQL server — the same pattern
`tests/repositories/knowledge/postgres/test_repository.py` already uses.
Exercises the repository's own CRUD/mutation/snapshot/health-check
behavior directly (not through WatchlistService) — no business rules
(duplicate-ticker prevention, size limits) are enforced at this layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.watchlist.postgres.models import Base
from app.repositories.watchlist.postgres.repository import PostgresWatchlistRepository
from app.watchlist.models import Watchlist, WatchlistItem

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


def _watchlist(watchlist_id: str = "wl-1", name: str = "AI") -> Watchlist:
    return Watchlist(id=watchlist_id, name=name, created_at=NOW, updated_at=NOW)


def _item(ticker: str = "NVDA", **overrides: object) -> WatchlistItem:
    defaults: dict[str, object] = {"ticker": ticker, "added_at": NOW}
    defaults.update(overrides)
    return WatchlistItem(**defaults)


# --- create_watchlist / get_watchlist -----------------------------------------------------------


async def test_create_watchlist_then_get_returns_it(repository: PostgresWatchlistRepository) -> None:
    await repository.create_watchlist(_watchlist())

    fetched = await repository.get_watchlist("wl-1")

    assert fetched is not None
    assert fetched.name == "AI"
    assert fetched.items == ()


async def test_get_watchlist_missing_returns_none(repository: PostgresWatchlistRepository) -> None:
    assert await repository.get_watchlist("does-not-exist") is None


async def test_create_watchlist_with_items_persists_them(
    repository: PostgresWatchlistRepository,
) -> None:
    watchlist = Watchlist(
        id="wl-1", name="AI", created_at=NOW, updated_at=NOW, items=(_item("NVDA"), _item("MSFT"))
    )

    await repository.create_watchlist(watchlist)

    fetched = await repository.get_watchlist("wl-1")
    assert fetched is not None
    assert {item.ticker for item in fetched.items} == {"NVDA", "MSFT"}


# --- list_watchlists -----------------------------------------------------------


async def test_list_watchlists_empty_initially(repository: PostgresWatchlistRepository) -> None:
    assert await repository.list_watchlists() == []


async def test_list_watchlists_returns_all(repository: PostgresWatchlistRepository) -> None:
    await repository.create_watchlist(_watchlist("wl-1", "AI"))
    await repository.create_watchlist(_watchlist("wl-2", "Energy"))

    watchlists = await repository.list_watchlists()

    assert {w.name for w in watchlists} == {"AI", "Energy"}


# --- delete_watchlist -----------------------------------------------------------


async def test_delete_watchlist_existing_returns_true(
    repository: PostgresWatchlistRepository,
) -> None:
    await repository.create_watchlist(_watchlist())

    result = await repository.delete_watchlist("wl-1")

    assert result is True
    assert await repository.get_watchlist("wl-1") is None


async def test_delete_watchlist_missing_returns_false(
    repository: PostgresWatchlistRepository,
) -> None:
    assert await repository.delete_watchlist("does-not-exist") is False


async def test_delete_watchlist_also_deletes_its_items(
    repository: PostgresWatchlistRepository,
) -> None:
    watchlist = Watchlist(id="wl-1", name="AI", created_at=NOW, updated_at=NOW, items=(_item("NVDA"),))
    await repository.create_watchlist(watchlist)

    await repository.delete_watchlist("wl-1")

    assert await repository.get_watchlist("wl-1") is None


# --- rename_watchlist -----------------------------------------------------------


async def test_rename_watchlist_existing(repository: PostgresWatchlistRepository) -> None:
    await repository.create_watchlist(_watchlist())

    result = await repository.rename_watchlist("wl-1", "Artificial Intelligence")

    assert result is not None
    assert result.name == "Artificial Intelligence"


async def test_rename_watchlist_missing_returns_none(
    repository: PostgresWatchlistRepository,
) -> None:
    assert await repository.rename_watchlist("does-not-exist", "New Name") is None


async def test_rename_watchlist_updates_updated_at(repository: PostgresWatchlistRepository) -> None:
    await repository.create_watchlist(_watchlist())

    result = await repository.rename_watchlist("wl-1", "New Name")

    assert result is not None
    assert result.updated_at >= NOW


# --- add_company -----------------------------------------------------------


async def test_add_company_to_existing_watchlist(repository: PostgresWatchlistRepository) -> None:
    await repository.create_watchlist(_watchlist())

    result = await repository.add_company("wl-1", _item("NVDA"))

    assert result is not None
    assert [item.ticker for item in result.items] == ["NVDA"]


async def test_add_company_to_missing_watchlist_returns_none(
    repository: PostgresWatchlistRepository,
) -> None:
    assert await repository.add_company("does-not-exist", _item("NVDA")) is None


async def test_database_rejects_duplicate_ticker_via_unique_constraint(
    repository: PostgresWatchlistRepository,
) -> None:
    """Defense in depth: even bypassing WatchlistService, the database's
    own UniqueConstraint((watchlist_id, ticker)) rejects a duplicate."""
    await repository.create_watchlist(_watchlist())
    await repository.add_company("wl-1", _item("NVDA"))

    with pytest.raises(Exception):  # noqa: B017,PT011 - IntegrityError subclass, driver-dependent
        await repository.add_company("wl-1", _item("NVDA"))


# --- remove_company -----------------------------------------------------------


async def test_remove_company_existing(repository: PostgresWatchlistRepository) -> None:
    await repository.create_watchlist(_watchlist())
    await repository.add_company("wl-1", _item("NVDA"))

    result = await repository.remove_company("wl-1", "NVDA")

    assert result is not None
    assert result.items == ()


async def test_remove_company_not_present_is_a_no_op(repository: PostgresWatchlistRepository) -> None:
    await repository.create_watchlist(_watchlist())

    result = await repository.remove_company("wl-1", "NVDA")

    assert result is not None
    assert result.items == ()


async def test_remove_company_from_missing_watchlist_returns_none(
    repository: PostgresWatchlistRepository,
) -> None:
    assert await repository.remove_company("does-not-exist", "NVDA") is None


# --- update_notes -----------------------------------------------------------


async def test_update_notes_existing_item(repository: PostgresWatchlistRepository) -> None:
    await repository.create_watchlist(_watchlist())
    await repository.add_company("wl-1", _item("NVDA"))

    result = await repository.update_notes("wl-1", "NVDA", "Watching earnings")

    assert result is not None
    assert result.items[0].notes == "Watching earnings"


async def test_update_notes_ticker_not_present_is_a_no_op(
    repository: PostgresWatchlistRepository,
) -> None:
    await repository.create_watchlist(_watchlist())

    result = await repository.update_notes("wl-1", "NVDA", "note")

    assert result is not None
    assert result.items == ()


async def test_update_notes_missing_watchlist_returns_none(
    repository: PostgresWatchlistRepository,
) -> None:
    assert await repository.update_notes("does-not-exist", "NVDA", "note") is None


# --- snapshot -----------------------------------------------------------


async def test_snapshot_of_existing_watchlist(repository: PostgresWatchlistRepository) -> None:
    await repository.create_watchlist(_watchlist())
    await repository.add_company("wl-1", _item("NVDA", confidence=0.8))

    snapshot = await repository.snapshot("wl-1")

    assert snapshot is not None
    assert snapshot.watchlist_id == "wl-1"
    assert snapshot.total_companies == 1
    assert snapshot.average_confidence == pytest.approx(0.8)


async def test_snapshot_of_missing_watchlist_returns_none(
    repository: PostgresWatchlistRepository,
) -> None:
    assert await repository.snapshot("does-not-exist") is None


# --- health_check -----------------------------------------------------------


async def test_health_check_true_against_reachable_database(
    repository: PostgresWatchlistRepository,
) -> None:
    assert await repository.health_check() is True


async def test_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresWatchlistRepository(session_factory)

    assert await repository.health_check() is False
