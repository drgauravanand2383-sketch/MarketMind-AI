"""Tests for SignalDetectionService's definition management: create/
update/delete/list/get/duplicate, duplicate-name prevention, and the
configurable maximum condition count. Backed by a genuine
`PostgresSignalDefinitionRepository` running against an in-memory SQLite
database (via aiosqlite) — the same pattern used throughout this
codebase's repository tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.signals.postgres.models import Base
from app.repositories.signals.postgres.repository import PostgresSignalDefinitionRepository
from app.signals.engine import SignalDetectionService
from app.signals.exceptions import (
    DuplicateSignalNameError,
    MaxConditionsExceededError,
    SignalDefinitionNotFoundError,
)
from app.signals.models import SignalCategory, SignalPriority
from tests.signals.conftest import make_condition


@pytest.fixture
async def repository() -> AsyncIterator[PostgresSignalDefinitionRepository]:
    engine_db = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine_db.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine_db, expire_on_commit=False)
    try:
        yield PostgresSignalDefinitionRepository(session_factory)
    finally:
        await engine_db.dispose()


@pytest.fixture
def engine(repository: PostgresSignalDefinitionRepository) -> SignalDetectionService:
    return SignalDetectionService(repository)


# --- create_signal_definition -----------------------------------------------------------


async def test_create_signal_definition_returns_a_definition_with_a_generated_id(
    engine: SignalDetectionService,
) -> None:
    definition = await engine.create_signal_definition("Value Signal")
    assert definition.id
    assert definition.name == "Value Signal"
    assert definition.conditions == ()


async def test_create_signal_definition_and_get_round_trip(engine: SignalDetectionService) -> None:
    created = await engine.create_signal_definition(
        "Value Signal",
        description="Cheap, profitable companies",
        category=SignalCategory.VALUATION,
        priority=SignalPriority.HIGH,
        conditions=(make_condition(),),
    )

    fetched = await engine.get_signal_definition(created.id)

    assert fetched.name == "Value Signal"
    assert fetched.description == "Cheap, profitable companies"
    assert fetched.category == SignalCategory.VALUATION
    assert fetched.priority == SignalPriority.HIGH
    assert len(fetched.conditions) == 1


async def test_create_signal_definition_respects_max_conditions(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    engine = SignalDetectionService(repository, max_conditions=2)
    conditions = (make_condition("c1"), make_condition("c2"), make_condition("c3"))

    with pytest.raises(MaxConditionsExceededError):
        await engine.create_signal_definition("Too Many", conditions=conditions)


async def test_create_signal_definition_at_exactly_the_max_conditions_succeeds(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    engine = SignalDetectionService(repository, max_conditions=2)
    conditions = (make_condition("c1"), make_condition("c2"))

    definition = await engine.create_signal_definition("Exactly Max", conditions=conditions)

    assert len(definition.conditions) == 2


async def test_create_signal_definition_duplicate_name_raises(engine: SignalDetectionService) -> None:
    await engine.create_signal_definition("Value Signal")

    with pytest.raises(DuplicateSignalNameError):
        await engine.create_signal_definition("Value Signal")


async def test_create_signal_definition_duplicate_name_allowed_when_not_enforced(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    engine = SignalDetectionService(repository, enforce_unique_names=False)
    await engine.create_signal_definition("Value Signal")

    second = await engine.create_signal_definition("Value Signal")  # must not raise

    assert second.name == "Value Signal"


# --- update_signal_definition -----------------------------------------------------------


async def test_update_signal_definition_replaces_conditions(engine: SignalDetectionService) -> None:
    definition = await engine.create_signal_definition("Value Signal", conditions=(make_condition("c1"),))

    updated = definition.model_copy(update={"conditions": (make_condition("c1"), make_condition("c2"))})
    result = await engine.update_signal_definition(updated)

    assert len(result.conditions) == 2


async def test_update_signal_definition_unknown_id_raises(engine: SignalDetectionService) -> None:
    definition = await engine.create_signal_definition("Value Signal")
    await engine.delete_signal_definition(definition.id)

    with pytest.raises(SignalDefinitionNotFoundError):
        await engine.update_signal_definition(definition)


async def test_update_signal_definition_respects_max_conditions(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    engine = SignalDetectionService(repository, max_conditions=1)
    definition = await engine.create_signal_definition("Value Signal", conditions=(make_condition("c1"),))

    too_many = definition.model_copy(update={"conditions": (make_condition("c1"), make_condition("c2"))})
    with pytest.raises(MaxConditionsExceededError):
        await engine.update_signal_definition(too_many)


async def test_update_signal_definition_rejects_duplicate_name_from_a_different_definition(
    engine: SignalDetectionService,
) -> None:
    await engine.create_signal_definition("Momentum Signal")
    other = await engine.create_signal_definition("Value Signal")

    renamed = other.model_copy(update={"name": "Momentum Signal"})
    with pytest.raises(DuplicateSignalNameError):
        await engine.update_signal_definition(renamed)


async def test_update_signal_definition_keeping_its_own_name_does_not_raise(
    engine: SignalDetectionService,
) -> None:
    definition = await engine.create_signal_definition("Value Signal", description="v1")

    updated = definition.model_copy(update={"description": "v2"})
    result = await engine.update_signal_definition(updated)  # must not raise DuplicateSignalNameError

    assert result.description == "v2"


# --- delete_signal_definition -----------------------------------------------------------


async def test_delete_signal_definition_removes_it(engine: SignalDetectionService) -> None:
    definition = await engine.create_signal_definition("Value Signal")

    await engine.delete_signal_definition(definition.id)

    with pytest.raises(SignalDefinitionNotFoundError):
        await engine.get_signal_definition(definition.id)


async def test_delete_signal_definition_unknown_id_raises(engine: SignalDetectionService) -> None:
    with pytest.raises(SignalDefinitionNotFoundError):
        await engine.delete_signal_definition("does-not-exist")


# --- list_signal_definitions / get_signal_definition -----------------------------------------------------------


async def test_list_signal_definitions_empty_initially(engine: SignalDetectionService) -> None:
    assert await engine.list_signal_definitions() == []


async def test_list_signal_definitions_returns_every_created_definition(
    engine: SignalDetectionService,
) -> None:
    await engine.create_signal_definition("Value Signal")
    await engine.create_signal_definition("Growth Signal")

    names = {definition.name for definition in await engine.list_signal_definitions()}

    assert names == {"Value Signal", "Growth Signal"}


async def test_get_signal_definition_unknown_id_raises(engine: SignalDetectionService) -> None:
    with pytest.raises(SignalDefinitionNotFoundError):
        await engine.get_signal_definition("does-not-exist")


# --- duplicate_signal_definition -----------------------------------------------------------


async def test_duplicate_signal_definition_copies_conditions_under_a_new_id(
    engine: SignalDetectionService,
) -> None:
    original = await engine.create_signal_definition(
        "Value Signal", conditions=(make_condition("c1"), make_condition("c2"))
    )

    duplicate = await engine.duplicate_signal_definition(original.id, "Value Signal Copy")

    assert duplicate.id != original.id
    assert duplicate.name == "Value Signal Copy"
    assert [c.id for c in duplicate.conditions] == ["c1", "c2"]


async def test_duplicate_signal_definition_is_independent_of_the_original(
    engine: SignalDetectionService,
) -> None:
    original = await engine.create_signal_definition("Value Signal", conditions=(make_condition("c1"),))

    duplicate = await engine.duplicate_signal_definition(original.id, "Copy")
    await engine.delete_signal_definition(duplicate.id)

    assert (await engine.get_signal_definition(original.id)).id == original.id  # original unaffected


async def test_duplicate_signal_definition_unknown_source_id_raises(
    engine: SignalDetectionService,
) -> None:
    with pytest.raises(SignalDefinitionNotFoundError):
        await engine.duplicate_signal_definition("does-not-exist", "Copy")


async def test_duplicate_signal_definition_duplicate_name_raises(
    engine: SignalDetectionService,
) -> None:
    original = await engine.create_signal_definition("Value Signal")
    await engine.create_signal_definition("Already Taken")

    with pytest.raises(DuplicateSignalNameError):
        await engine.duplicate_signal_definition(original.id, "Already Taken")


async def test_duplicate_signal_definition_preserves_category_and_priority(
    engine: SignalDetectionService,
) -> None:
    original = await engine.create_signal_definition(
        "Value Signal", category=SignalCategory.MOMENTUM, priority=SignalPriority.CRITICAL
    )

    duplicate = await engine.duplicate_signal_definition(original.id, "Copy")

    assert duplicate.category == SignalCategory.MOMENTUM
    assert duplicate.priority == SignalPriority.CRITICAL
