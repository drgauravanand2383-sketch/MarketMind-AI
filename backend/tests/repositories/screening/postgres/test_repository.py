"""Tests for PostgresScreeningRepository.

Run against an in-memory SQLite database via aiosqlite, exercising the
repository's own CRUD/duplicate/health-check behavior directly (not
through ScreeningEngine) — no business rules (duplicate-name prevention,
max filters) are enforced at this layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.screening.postgres.models import Base
from app.repositories.screening.postgres.repository import PostgresScreeningRepository
from app.screening.models import LogicalGroup, LogicType, ScreenFilter, ScreeningProfile, ScreenOperator

NOW = datetime(2026, 8, 6, tzinfo=timezone.utc)


@pytest.fixture
async def repository() -> AsyncIterator[PostgresScreeningRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresScreeningRepository(session_factory)
    finally:
        await engine.dispose()


def _filter(filter_id: str = "f1") -> ScreenFilter:
    return ScreenFilter(id=filter_id, field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20)


def _profile(profile_id: str = "p1", name: str = "Value", **overrides: object) -> ScreeningProfile:
    defaults: dict[str, object] = {"id": profile_id, "name": name, "created_at": NOW, "updated_at": NOW}
    defaults.update(overrides)
    return ScreeningProfile(**defaults)


# --- create_profile / get_profile -----------------------------------------------------------


async def test_create_profile_then_get_returns_it(repository: PostgresScreeningRepository) -> None:
    await repository.create_profile(_profile())

    fetched = await repository.get_profile("p1")

    assert fetched is not None
    assert fetched.name == "Value"


async def test_get_profile_missing_returns_none(repository: PostgresScreeningRepository) -> None:
    assert await repository.get_profile("does-not-exist") is None


async def test_create_profile_with_filters_and_groups_persists_them(
    repository: PostgresScreeningRepository,
) -> None:
    group = LogicalGroup(id="g1", logic=LogicType.OR)
    profile = _profile(filters=(_filter("f1"), _filter("f2")), groups=(group,))

    await repository.create_profile(profile)

    fetched = await repository.get_profile("p1")
    assert fetched is not None
    assert {f.id for f in fetched.filters} == {"f1", "f2"}
    assert [g.id for g in fetched.groups] == ["g1"]


async def test_create_profile_preserves_between_operator_value(
    repository: PostgresScreeningRepository,
) -> None:
    between_filter = ScreenFilter(id="f1", field="pe_ratio", operator=ScreenOperator.BETWEEN, value=[10, 20])
    await repository.create_profile(_profile(filters=(between_filter,)))

    fetched = await repository.get_profile("p1")

    assert fetched is not None
    assert fetched.filters[0].value == [10, 20]


# --- list_profiles -----------------------------------------------------------


async def test_list_profiles_empty_initially(repository: PostgresScreeningRepository) -> None:
    assert await repository.list_profiles() == []


async def test_list_profiles_returns_all(repository: PostgresScreeningRepository) -> None:
    await repository.create_profile(_profile("p1", "Value"))
    await repository.create_profile(_profile("p2", "Growth"))

    profiles = await repository.list_profiles()

    assert {p.name for p in profiles} == {"Value", "Growth"}


# --- update_profile -----------------------------------------------------------


async def test_update_profile_existing(repository: PostgresScreeningRepository) -> None:
    await repository.create_profile(_profile(filters=(_filter("f1"),)))

    updated = _profile(name="Value 2.0", filters=(_filter("f1"), _filter("f2")))
    result = await repository.update_profile(updated)

    assert result is not None
    assert result.name == "Value 2.0"
    assert len(result.filters) == 2


async def test_update_profile_missing_returns_none(repository: PostgresScreeningRepository) -> None:
    assert await repository.update_profile(_profile()) is None


# --- delete_profile -----------------------------------------------------------


async def test_delete_profile_existing_returns_true(repository: PostgresScreeningRepository) -> None:
    await repository.create_profile(_profile())

    result = await repository.delete_profile("p1")

    assert result is True
    assert await repository.get_profile("p1") is None


async def test_delete_profile_missing_returns_false(repository: PostgresScreeningRepository) -> None:
    assert await repository.delete_profile("does-not-exist") is False


# --- duplicate_profile -----------------------------------------------------------


async def test_duplicate_profile_creates_an_independent_copy(
    repository: PostgresScreeningRepository,
) -> None:
    await repository.create_profile(_profile(filters=(_filter("f1"),)))

    duplicate = await repository.duplicate_profile("p1", "p2", "Value Copy")

    assert duplicate is not None
    assert duplicate.id == "p2"
    assert duplicate.name == "Value Copy"
    assert [f.id for f in duplicate.filters] == ["f1"]
    assert await repository.get_profile("p1") is not None  # original untouched


async def test_duplicate_profile_missing_source_returns_none(
    repository: PostgresScreeningRepository,
) -> None:
    assert await repository.duplicate_profile("does-not-exist", "p2", "Copy") is None


async def test_duplicate_profile_mutating_copy_does_not_affect_original(
    repository: PostgresScreeningRepository,
) -> None:
    await repository.create_profile(_profile(filters=(_filter("f1"),)))
    await repository.duplicate_profile("p1", "p2", "Copy")

    await repository.update_profile(_profile("p2", "Copy", filters=(_filter("f1"), _filter("f2"))))

    original = await repository.get_profile("p1")
    assert original is not None
    assert len(original.filters) == 1


# --- health_check -----------------------------------------------------------


async def test_health_check_true_against_reachable_database(
    repository: PostgresScreeningRepository,
) -> None:
    assert await repository.health_check() is True


async def test_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresScreeningRepository(session_factory)

    assert await repository.health_check() is False
