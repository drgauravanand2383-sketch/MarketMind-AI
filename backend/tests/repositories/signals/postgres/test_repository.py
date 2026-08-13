"""Tests for PostgresSignalDefinitionRepository.

Run against an in-memory SQLite database via aiosqlite, exercising the
repository's own CRUD/duplicate/health-check behavior directly (not
through SignalDetectionService) — no business rules (duplicate-name
prevention, max conditions) are enforced at this layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.signals.postgres.models import Base
from app.repositories.signals.postgres.repository import PostgresSignalDefinitionRepository
from app.signals.models import (
    SignalCategory,
    SignalCondition,
    SignalConditionGroup,
    SignalDefinition,
    SignalLogicType,
    SignalOperator,
    SignalPriority,
)

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


@pytest.fixture
async def repository() -> AsyncIterator[PostgresSignalDefinitionRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresSignalDefinitionRepository(session_factory)
    finally:
        await engine.dispose()


def _condition(condition_id: str = "c1") -> SignalCondition:
    return SignalCondition(id=condition_id, field="ratios.pe", operator=SignalOperator.LESS_THAN, value=20)


def _definition(definition_id: str = "d1", name: str = "Value", **overrides: object) -> SignalDefinition:
    defaults: dict[str, object] = {"id": definition_id, "name": name, "created_at": NOW, "updated_at": NOW}
    defaults.update(overrides)
    return SignalDefinition(**defaults)


# --- create_signal_definition / get_signal_definition -----------------------------------------------------------


async def test_create_then_get_returns_it(repository: PostgresSignalDefinitionRepository) -> None:
    await repository.create_signal_definition(_definition())

    fetched = await repository.get_signal_definition("d1")

    assert fetched is not None
    assert fetched.name == "Value"


async def test_get_missing_returns_none(repository: PostgresSignalDefinitionRepository) -> None:
    assert await repository.get_signal_definition("does-not-exist") is None


async def test_create_with_conditions_and_groups_persists_them(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    group = SignalConditionGroup(id="g1", logic=SignalLogicType.OR)
    definition = _definition(conditions=(_condition("c1"), _condition("c2")), groups=(group,))

    await repository.create_signal_definition(definition)

    fetched = await repository.get_signal_definition("d1")
    assert fetched is not None
    assert {c.id for c in fetched.conditions} == {"c1", "c2"}
    assert [g.id for g in fetched.groups] == ["g1"]


async def test_create_preserves_category_priority_and_weight(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    weighted_condition = SignalCondition(
        id="c1", field="ratios.pe", operator=SignalOperator.LESS_THAN, value=20, weight=3.5
    )
    definition = _definition(
        category=SignalCategory.MOMENTUM, priority=SignalPriority.CRITICAL, conditions=(weighted_condition,)
    )

    await repository.create_signal_definition(definition)

    fetched = await repository.get_signal_definition("d1")
    assert fetched is not None
    assert fetched.category == SignalCategory.MOMENTUM
    assert fetched.priority == SignalPriority.CRITICAL
    assert fetched.conditions[0].weight == 3.5


async def test_create_preserves_between_operator_value(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    between_condition = SignalCondition(id="c1", field="ratios.pe", operator=SignalOperator.BETWEEN, value=[10, 20])
    await repository.create_signal_definition(_definition(conditions=(between_condition,)))

    fetched = await repository.get_signal_definition("d1")

    assert fetched is not None
    assert fetched.conditions[0].value == [10, 20]


# --- list_signal_definitions -----------------------------------------------------------


async def test_list_signal_definitions_empty_initially(repository: PostgresSignalDefinitionRepository) -> None:
    assert await repository.list_signal_definitions() == []


async def test_list_signal_definitions_returns_all(repository: PostgresSignalDefinitionRepository) -> None:
    await repository.create_signal_definition(_definition("d1", "Value"))
    await repository.create_signal_definition(_definition("d2", "Growth"))

    definitions = await repository.list_signal_definitions()

    assert {d.name for d in definitions} == {"Value", "Growth"}


# --- update_signal_definition -----------------------------------------------------------


async def test_update_signal_definition_existing(repository: PostgresSignalDefinitionRepository) -> None:
    await repository.create_signal_definition(_definition(conditions=(_condition("c1"),)))

    updated = _definition(name="Value 2.0", conditions=(_condition("c1"), _condition("c2")))
    result = await repository.update_signal_definition(updated)

    assert result is not None
    assert result.name == "Value 2.0"
    assert len(result.conditions) == 2


async def test_update_signal_definition_missing_returns_none(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    assert await repository.update_signal_definition(_definition()) is None


# --- delete_signal_definition -----------------------------------------------------------


async def test_delete_signal_definition_existing_returns_true(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    await repository.create_signal_definition(_definition())

    result = await repository.delete_signal_definition("d1")

    assert result is True
    assert await repository.get_signal_definition("d1") is None


async def test_delete_signal_definition_missing_returns_false(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    assert await repository.delete_signal_definition("does-not-exist") is False


# --- duplicate_signal_definition -----------------------------------------------------------


async def test_duplicate_signal_definition_creates_an_independent_copy(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    await repository.create_signal_definition(_definition(conditions=(_condition("c1"),)))

    duplicate = await repository.duplicate_signal_definition("d1", "d2", "Value Copy")

    assert duplicate is not None
    assert duplicate.id == "d2"
    assert duplicate.name == "Value Copy"
    assert [c.id for c in duplicate.conditions] == ["c1"]
    assert await repository.get_signal_definition("d1") is not None  # original untouched


async def test_duplicate_signal_definition_missing_source_returns_none(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    assert await repository.duplicate_signal_definition("does-not-exist", "d2", "Copy") is None


async def test_duplicate_signal_definition_mutating_copy_does_not_affect_original(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    await repository.create_signal_definition(_definition(conditions=(_condition("c1"),)))
    await repository.duplicate_signal_definition("d1", "d2", "Copy")

    await repository.update_signal_definition(
        _definition("d2", "Copy", conditions=(_condition("c1"), _condition("c2")))
    )

    original = await repository.get_signal_definition("d1")
    assert original is not None
    assert len(original.conditions) == 1


# --- health_check -----------------------------------------------------------


async def test_health_check_true_against_reachable_database(
    repository: PostgresSignalDefinitionRepository,
) -> None:
    assert await repository.health_check() is True


async def test_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresSignalDefinitionRepository(session_factory)

    assert await repository.health_check() is False
