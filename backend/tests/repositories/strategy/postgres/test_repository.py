"""Tests for PostgresStrategyRepository.

Run against an in-memory SQLite database via aiosqlite, exercising the
repository's own CRUD/duplicate/health-check behavior directly (not
through StrategyEvaluationService) — no business rules (duplicate-name
prevention, max strategies/rules) are enforced at this layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.strategy.postgres.models import Base
from app.repositories.strategy.postgres.repository import PostgresStrategyRepository
from app.strategy.models import (
    InvestmentStrategy,
    StrategyEvaluationResult,
    StrategyOperator,
    StrategyRule,
    StrategySummary,
    StrategyType,
    StrategyWeighting,
)

NOW = datetime(2026, 8, 10, tzinfo=UTC)


@pytest.fixture
async def repository() -> AsyncIterator[PostgresStrategyRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresStrategyRepository(session_factory)
    finally:
        await engine.dispose()


def _rule(rule_id: str = "r1") -> StrategyRule:
    return StrategyRule(id=rule_id, field="overall_score", operator=StrategyOperator.GREATER_THAN, value=50)


def _strategy(strategy_id: str = "s1", name: str = "Value", **overrides: object) -> InvestmentStrategy:
    defaults: dict[str, object] = {"id": strategy_id, "name": name, "created_at": NOW, "updated_at": NOW}
    defaults.update(overrides)
    return InvestmentStrategy(**defaults)


def _evaluation(request_id: str = "req-1", evaluated_at: datetime = NOW, **overrides: object) -> StrategyEvaluationResult:
    defaults: dict[str, object] = {
        "request_id": request_id,
        "evaluated_at": evaluated_at,
        "overall_alignment": 0.0,
        "summary": StrategySummary(),
    }
    defaults.update(overrides)
    return StrategyEvaluationResult(**defaults)


# --- create_strategy / get_strategy -----------------------------------------------------------


async def test_create_strategy_then_get_returns_it(repository: PostgresStrategyRepository) -> None:
    await repository.create_strategy(_strategy())

    fetched = await repository.get_strategy("s1")

    assert fetched is not None
    assert fetched.name == "Value"


async def test_get_strategy_missing_returns_none(repository: PostgresStrategyRepository) -> None:
    assert await repository.get_strategy("does-not-exist") is None


async def test_create_strategy_persists_weightings_and_rules(
    repository: PostgresStrategyRepository,
) -> None:
    strategy = _strategy(
        strategy_type=StrategyType.GROWTH,
        weightings=StrategyWeighting(overall_score=3.0),
        rules=(_rule("r1"), _rule("r2")),
    )

    await repository.create_strategy(strategy)

    fetched = await repository.get_strategy("s1")
    assert fetched is not None
    assert fetched.strategy_type == StrategyType.GROWTH
    assert fetched.weightings.overall_score == 3.0
    assert {r.id for r in fetched.rules} == {"r1", "r2"}


async def test_create_strategy_preserves_between_operator_value(
    repository: PostgresStrategyRepository,
) -> None:
    between_rule = StrategyRule(id="r1", field="overall_score", operator=StrategyOperator.BETWEEN, value=[10, 20])
    await repository.create_strategy(_strategy(rules=(between_rule,)))

    fetched = await repository.get_strategy("s1")

    assert fetched is not None
    assert fetched.rules[0].value == [10, 20]


# --- list_strategies -----------------------------------------------------------


async def test_list_strategies_empty_initially(repository: PostgresStrategyRepository) -> None:
    assert await repository.list_strategies() == []


async def test_list_strategies_returns_all(repository: PostgresStrategyRepository) -> None:
    await repository.create_strategy(_strategy("s1", "Value"))
    await repository.create_strategy(_strategy("s2", "Growth"))

    strategies = await repository.list_strategies()

    assert {s.name for s in strategies} == {"Value", "Growth"}


# --- update_strategy -----------------------------------------------------------


async def test_update_strategy_existing(repository: PostgresStrategyRepository) -> None:
    await repository.create_strategy(_strategy(rules=(_rule("r1"),)))

    updated = _strategy(name="Value 2.0", rules=(_rule("r1"), _rule("r2")))
    result = await repository.update_strategy(updated)

    assert result is not None
    assert result.name == "Value 2.0"
    assert len(result.rules) == 2


async def test_update_strategy_missing_returns_none(repository: PostgresStrategyRepository) -> None:
    assert await repository.update_strategy(_strategy()) is None


# --- delete_strategy -----------------------------------------------------------


async def test_delete_strategy_existing_returns_true(repository: PostgresStrategyRepository) -> None:
    await repository.create_strategy(_strategy())

    result = await repository.delete_strategy("s1")

    assert result is True
    assert await repository.get_strategy("s1") is None


async def test_delete_strategy_missing_returns_false(repository: PostgresStrategyRepository) -> None:
    assert await repository.delete_strategy("does-not-exist") is False


# --- duplicate_strategy -----------------------------------------------------------


async def test_duplicate_strategy_creates_an_independent_copy(
    repository: PostgresStrategyRepository,
) -> None:
    await repository.create_strategy(_strategy(rules=(_rule("r1"),)))

    duplicate = await repository.duplicate_strategy("s1", "s2", "Value Copy")

    assert duplicate is not None
    assert duplicate.id == "s2"
    assert duplicate.name == "Value Copy"
    assert [r.id for r in duplicate.rules] == ["r1"]
    assert await repository.get_strategy("s1") is not None  # original untouched


async def test_duplicate_strategy_missing_source_returns_none(repository: PostgresStrategyRepository) -> None:
    assert await repository.duplicate_strategy("does-not-exist", "s2", "Copy") is None


async def test_duplicate_strategy_mutating_copy_does_not_affect_original(
    repository: PostgresStrategyRepository,
) -> None:
    await repository.create_strategy(_strategy(rules=(_rule("r1"),)))
    await repository.duplicate_strategy("s1", "s2", "Copy")

    await repository.update_strategy(_strategy("s2", "Copy", rules=(_rule("r1"), _rule("r2"))))

    original = await repository.get_strategy("s1")
    assert original is not None
    assert len(original.rules) == 1


# --- store_evaluation / get_evaluation -----------------------------------------------------------


async def test_store_evaluation_then_get_returns_it(repository: PostgresStrategyRepository) -> None:
    await repository.store_evaluation(_evaluation())

    fetched = await repository.get_evaluation("req-1")

    assert fetched is not None
    assert fetched.request_id == "req-1"


async def test_get_evaluation_missing_returns_none(repository: PostgresStrategyRepository) -> None:
    assert await repository.get_evaluation("does-not-exist") is None


async def test_get_evaluation_returns_most_recent_when_multiple_stored(
    repository: PostgresStrategyRepository,
) -> None:
    await repository.store_evaluation(_evaluation(evaluated_at=NOW, overall_alignment=10.0))
    await repository.store_evaluation(_evaluation(evaluated_at=NOW + timedelta(minutes=5), overall_alignment=90.0))

    latest = await repository.get_evaluation("req-1")

    assert latest is not None
    assert latest.overall_alignment == 90.0


async def test_store_evaluation_persists_strategy_matches_and_summary(
    repository: PostgresStrategyRepository,
) -> None:
    from app.strategy.models import StrategyMatch

    match = StrategyMatch(strategy_id="s1", strategy_name="Value", alignment_score=80.0, confidence=90.0, reasoning="x")
    result = _evaluation(
        overall_alignment=80.0,
        best_strategy="s1",
        strategy_matches=(match,),
        summary=StrategySummary(total_strategies=1, best_alignment=80.0, average_alignment=80.0, highest_confidence=90.0),
    )

    await repository.store_evaluation(result)

    fetched = await repository.get_evaluation("req-1")
    assert fetched is not None
    assert fetched.strategy_matches[0].strategy_name == "Value"
    assert fetched.summary.total_strategies == 1


# --- list_evaluations -----------------------------------------------------------


async def test_list_evaluations_empty_initially(repository: PostgresStrategyRepository) -> None:
    assert await repository.list_evaluations() == []


async def test_list_evaluations_returns_all_across_requests(repository: PostgresStrategyRepository) -> None:
    await repository.store_evaluation(_evaluation("req-1"))
    await repository.store_evaluation(_evaluation("req-2"))

    evaluations = await repository.list_evaluations()

    assert {e.request_id for e in evaluations} == {"req-1", "req-2"}


# --- health_check -----------------------------------------------------------


async def test_health_check_true_against_reachable_database(repository: PostgresStrategyRepository) -> None:
    assert await repository.health_check() is True


async def test_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresStrategyRepository(session_factory)

    assert await repository.health_check() is False
