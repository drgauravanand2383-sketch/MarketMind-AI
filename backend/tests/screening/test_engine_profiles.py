"""Tests for ScreeningEngine's profile management: create/update/delete/
list/get/duplicate, duplicate-name prevention, and the configurable
maximum filter count. Backed by a genuine `PostgresScreeningRepository`
running against an in-memory SQLite database (via aiosqlite) — the same
pattern used throughout this codebase's repository tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.screening.postgres.models import Base
from app.repositories.screening.postgres.repository import PostgresScreeningRepository
from app.screening.engine import ScreeningEngine
from app.screening.exceptions import (
    DuplicateProfileNameError,
    MaxFiltersExceededError,
    ScreeningProfileNotFoundError,
)
from tests.screening.conftest import make_filter


@pytest.fixture
async def repository() -> AsyncIterator[PostgresScreeningRepository]:
    engine_db = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine_db.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine_db, expire_on_commit=False)
    try:
        yield PostgresScreeningRepository(session_factory)
    finally:
        await engine_db.dispose()


@pytest.fixture
def engine(repository: PostgresScreeningRepository) -> ScreeningEngine:
    return ScreeningEngine(repository)


# --- create_profile -----------------------------------------------------------


async def test_create_profile_returns_a_profile_with_a_generated_id(engine: ScreeningEngine) -> None:
    profile = await engine.create_profile("Value Stocks")
    assert profile.id
    assert profile.name == "Value Stocks"
    assert profile.filters == ()


async def test_create_profile_and_get_profile_round_trip(engine: ScreeningEngine) -> None:
    created = await engine.create_profile(
        "Value Stocks", description="Cheap, profitable companies", filters=(make_filter(),)
    )

    fetched = await engine.get_profile(created.id)

    assert fetched.name == "Value Stocks"
    assert fetched.description == "Cheap, profitable companies"
    assert len(fetched.filters) == 1


async def test_create_profile_respects_max_filters(repository: PostgresScreeningRepository) -> None:
    engine = ScreeningEngine(repository, max_filters=2)
    filters = (make_filter("f1"), make_filter("f2"), make_filter("f3"))

    with pytest.raises(MaxFiltersExceededError):
        await engine.create_profile("Too Many", filters=filters)


async def test_create_profile_at_exactly_the_max_filters_succeeds(
    repository: PostgresScreeningRepository,
) -> None:
    engine = ScreeningEngine(repository, max_filters=2)
    filters = (make_filter("f1"), make_filter("f2"))

    profile = await engine.create_profile("Exactly Max", filters=filters)

    assert len(profile.filters) == 2


async def test_create_profile_duplicate_name_raises(engine: ScreeningEngine) -> None:
    await engine.create_profile("Value Stocks")

    with pytest.raises(DuplicateProfileNameError):
        await engine.create_profile("Value Stocks")


async def test_create_profile_duplicate_name_allowed_when_not_enforced(
    repository: PostgresScreeningRepository,
) -> None:
    engine = ScreeningEngine(repository, enforce_unique_names=False)
    await engine.create_profile("Value Stocks")

    second = await engine.create_profile("Value Stocks")  # must not raise

    assert second.name == "Value Stocks"


# --- update_profile -----------------------------------------------------------


async def test_update_profile_replaces_filters(engine: ScreeningEngine) -> None:
    profile = await engine.create_profile("Value Stocks", filters=(make_filter("f1"),))

    updated_profile = profile.model_copy(update={"filters": (make_filter("f1"), make_filter("f2"))})
    result = await engine.update_profile(updated_profile)

    assert len(result.filters) == 2


async def test_update_profile_unknown_id_raises(engine: ScreeningEngine) -> None:
    profile = await engine.create_profile("Value Stocks")
    await engine.delete_profile(profile.id)

    with pytest.raises(ScreeningProfileNotFoundError):
        await engine.update_profile(profile)


async def test_update_profile_respects_max_filters(repository: PostgresScreeningRepository) -> None:
    engine = ScreeningEngine(repository, max_filters=1)
    profile = await engine.create_profile("Value Stocks", filters=(make_filter("f1"),))

    too_many = profile.model_copy(update={"filters": (make_filter("f1"), make_filter("f2"))})
    with pytest.raises(MaxFiltersExceededError):
        await engine.update_profile(too_many)


async def test_update_profile_rejects_duplicate_name_from_a_different_profile(
    engine: ScreeningEngine,
) -> None:
    await engine.create_profile("AI Stocks")
    other = await engine.create_profile("Energy Stocks")

    renamed = other.model_copy(update={"name": "AI Stocks"})
    with pytest.raises(DuplicateProfileNameError):
        await engine.update_profile(renamed)


async def test_update_profile_keeping_its_own_name_does_not_raise(engine: ScreeningEngine) -> None:
    profile = await engine.create_profile("Value Stocks", description="v1")

    updated = profile.model_copy(update={"description": "v2"})
    result = await engine.update_profile(updated)  # must not raise DuplicateProfileNameError

    assert result.description == "v2"


# --- delete_profile -----------------------------------------------------------


async def test_delete_profile_removes_it(engine: ScreeningEngine) -> None:
    profile = await engine.create_profile("Value Stocks")

    await engine.delete_profile(profile.id)

    with pytest.raises(ScreeningProfileNotFoundError):
        await engine.get_profile(profile.id)


async def test_delete_profile_unknown_id_raises(engine: ScreeningEngine) -> None:
    with pytest.raises(ScreeningProfileNotFoundError):
        await engine.delete_profile("does-not-exist")


# --- list_profiles / get_profile -----------------------------------------------------------


async def test_list_profiles_empty_initially(engine: ScreeningEngine) -> None:
    assert await engine.list_profiles() == []


async def test_list_profiles_returns_every_created_profile(engine: ScreeningEngine) -> None:
    await engine.create_profile("Value Stocks")
    await engine.create_profile("Growth Stocks")

    names = {profile.name for profile in await engine.list_profiles()}

    assert names == {"Value Stocks", "Growth Stocks"}


async def test_get_profile_unknown_id_raises(engine: ScreeningEngine) -> None:
    with pytest.raises(ScreeningProfileNotFoundError):
        await engine.get_profile("does-not-exist")


# --- duplicate_profile -----------------------------------------------------------


async def test_duplicate_profile_copies_filters_under_a_new_id(engine: ScreeningEngine) -> None:
    original = await engine.create_profile("Value Stocks", filters=(make_filter("f1"), make_filter("f2")))

    duplicate = await engine.duplicate_profile(original.id, "Value Stocks Copy")

    assert duplicate.id != original.id
    assert duplicate.name == "Value Stocks Copy"
    assert [f.id for f in duplicate.filters] == ["f1", "f2"]


async def test_duplicate_profile_is_independent_of_the_original(engine: ScreeningEngine) -> None:
    original = await engine.create_profile("Value Stocks", filters=(make_filter("f1"),))

    duplicate = await engine.duplicate_profile(original.id, "Copy")
    await engine.delete_profile(duplicate.id)

    assert (await engine.get_profile(original.id)).id == original.id  # original unaffected


async def test_duplicate_profile_unknown_source_id_raises(engine: ScreeningEngine) -> None:
    with pytest.raises(ScreeningProfileNotFoundError):
        await engine.duplicate_profile("does-not-exist", "Copy")


async def test_duplicate_profile_duplicate_name_raises(engine: ScreeningEngine) -> None:
    original = await engine.create_profile("Value Stocks")
    await engine.create_profile("Already Taken")

    with pytest.raises(DuplicateProfileNameError):
        await engine.duplicate_profile(original.id, "Already Taken")


async def test_duplicate_profile_does_not_copy_is_default(engine: ScreeningEngine) -> None:
    original = await engine.create_profile("Value Stocks", is_default=True)

    duplicate = await engine.duplicate_profile(original.id, "Copy")

    assert duplicate.is_default is False
