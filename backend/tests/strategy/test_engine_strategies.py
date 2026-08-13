"""Tests for StrategyEvaluationService's strategy management (create/
update/delete/list/get/duplicate, duplicate-name prevention, configurable
maximum strategy/rule counts) and `evaluate_recommendations` (multi-
strategy ranking, best-strategy selection, deterministic ordering,
persistence). Backed by a genuine `PostgresStrategyRepository` running
against an in-memory SQLite database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.strategy.postgres.models import Base
from app.repositories.strategy.postgres.repository import PostgresStrategyRepository
from app.strategy.engine import StrategyEvaluationService
from app.strategy.exceptions import (
    DuplicateStrategyNameError,
    MaxStrategiesExceededError,
    MaxStrategyRulesExceededError,
    StrategyEvaluationNotFoundError,
    StrategyNotFoundError,
)
from app.strategy.models import StrategyEvaluationRequest, StrategyOperator, StrategyType
from tests.strategy.conftest import NOW, make_candidate, make_recommendation_result, make_rule


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


@pytest.fixture
def service(repository: PostgresStrategyRepository) -> StrategyEvaluationService:
    return StrategyEvaluationService(repository, now_fn=lambda: NOW)


# --- create_strategy -----------------------------------------------------------


async def test_create_strategy_returns_a_strategy_with_a_generated_id(
    service: StrategyEvaluationService,
) -> None:
    strategy = await service.create_strategy("Value Strategy")
    assert strategy.id
    assert strategy.name == "Value Strategy"


async def test_create_strategy_and_get_round_trip(service: StrategyEvaluationService) -> None:
    created = await service.create_strategy(
        "Value Strategy",
        description="Cheap companies",
        strategy_type=StrategyType.VALUE,
        rules=(make_rule(),),
    )

    fetched = await service.get_strategy(created.id)

    assert fetched.name == "Value Strategy"
    assert fetched.description == "Cheap companies"
    assert fetched.strategy_type == StrategyType.VALUE
    assert len(fetched.rules) == 1


async def test_create_strategy_respects_max_strategies(
    repository: PostgresStrategyRepository,
) -> None:
    limited_service = StrategyEvaluationService(repository, max_strategies=2, now_fn=lambda: NOW)
    await limited_service.create_strategy("Strategy 1")
    await limited_service.create_strategy("Strategy 2")

    with pytest.raises(MaxStrategiesExceededError):
        await limited_service.create_strategy("Strategy 3")


async def test_create_strategy_respects_max_rules(repository: PostgresStrategyRepository) -> None:
    limited_service = StrategyEvaluationService(repository, max_rules=1, now_fn=lambda: NOW)

    with pytest.raises(MaxStrategyRulesExceededError):
        await limited_service.create_strategy("R", rules=(make_rule("r1"), make_rule("r2")))


async def test_create_strategy_duplicate_name_raises(service: StrategyEvaluationService) -> None:
    await service.create_strategy("Value Strategy")

    with pytest.raises(DuplicateStrategyNameError):
        await service.create_strategy("Value Strategy")


async def test_create_strategy_duplicate_name_allowed_when_not_enforced(
    repository: PostgresStrategyRepository,
) -> None:
    lenient_service = StrategyEvaluationService(repository, enforce_unique_names=False, now_fn=lambda: NOW)
    await lenient_service.create_strategy("Value Strategy")

    second = await lenient_service.create_strategy("Value Strategy")  # must not raise

    assert second.name == "Value Strategy"


# --- update_strategy -----------------------------------------------------------


async def test_update_strategy_replaces_rules(service: StrategyEvaluationService) -> None:
    strategy = await service.create_strategy("Value Strategy", rules=(make_rule("r1"),))

    updated = strategy.model_copy(update={"rules": (make_rule("r1"), make_rule("r2"))})
    result = await service.update_strategy(updated)

    assert len(result.rules) == 2


async def test_update_strategy_unknown_id_raises(service: StrategyEvaluationService) -> None:
    strategy = await service.create_strategy("Value Strategy")
    await service.delete_strategy(strategy.id)

    with pytest.raises(StrategyNotFoundError):
        await service.update_strategy(strategy)


async def test_update_strategy_respects_max_rules(repository: PostgresStrategyRepository) -> None:
    limited_service = StrategyEvaluationService(repository, max_rules=1, now_fn=lambda: NOW)
    strategy = await limited_service.create_strategy("R", rules=(make_rule("r1"),))

    too_many = strategy.model_copy(update={"rules": (make_rule("r1"), make_rule("r2"))})
    with pytest.raises(MaxStrategyRulesExceededError):
        await limited_service.update_strategy(too_many)


async def test_update_strategy_rejects_duplicate_name_from_a_different_strategy(
    service: StrategyEvaluationService,
) -> None:
    await service.create_strategy("Momentum Strategy")
    other = await service.create_strategy("Value Strategy")

    renamed = other.model_copy(update={"name": "Momentum Strategy"})
    with pytest.raises(DuplicateStrategyNameError):
        await service.update_strategy(renamed)


async def test_update_strategy_keeping_its_own_name_does_not_raise(
    service: StrategyEvaluationService,
) -> None:
    strategy = await service.create_strategy("Value Strategy", description="v1")

    updated = strategy.model_copy(update={"description": "v2"})
    result = await service.update_strategy(updated)  # must not raise DuplicateStrategyNameError

    assert result.description == "v2"


# --- delete_strategy -----------------------------------------------------------


async def test_delete_strategy_removes_it(service: StrategyEvaluationService) -> None:
    strategy = await service.create_strategy("Value Strategy")

    await service.delete_strategy(strategy.id)

    with pytest.raises(StrategyNotFoundError):
        await service.get_strategy(strategy.id)


async def test_delete_strategy_unknown_id_raises(service: StrategyEvaluationService) -> None:
    with pytest.raises(StrategyNotFoundError):
        await service.delete_strategy("does-not-exist")


# --- list_strategies / get_strategy -----------------------------------------------------------


async def test_list_strategies_empty_initially(service: StrategyEvaluationService) -> None:
    assert await service.list_strategies() == []


async def test_list_strategies_returns_every_created_strategy(service: StrategyEvaluationService) -> None:
    await service.create_strategy("A")
    await service.create_strategy("B")
    names = {s.name for s in await service.list_strategies()}
    assert names == {"A", "B"}


async def test_get_strategy_unknown_id_raises(service: StrategyEvaluationService) -> None:
    with pytest.raises(StrategyNotFoundError):
        await service.get_strategy("does-not-exist")


# --- duplicate_strategy -----------------------------------------------------------


async def test_duplicate_strategy_copies_rules_under_a_new_id(service: StrategyEvaluationService) -> None:
    original = await service.create_strategy("Value Strategy", rules=(make_rule("r1"), make_rule("r2")))

    duplicate = await service.duplicate_strategy(original.id, "Value Strategy Copy")

    assert duplicate.id != original.id
    assert duplicate.name == "Value Strategy Copy"
    assert [r.id for r in duplicate.rules] == ["r1", "r2"]


async def test_duplicate_strategy_unknown_source_id_raises(service: StrategyEvaluationService) -> None:
    with pytest.raises(StrategyNotFoundError):
        await service.duplicate_strategy("does-not-exist", "Copy")


async def test_duplicate_strategy_duplicate_name_raises(service: StrategyEvaluationService) -> None:
    original = await service.create_strategy("Value Strategy")
    await service.create_strategy("Already Taken")

    with pytest.raises(DuplicateStrategyNameError):
        await service.duplicate_strategy(original.id, "Already Taken")


async def test_duplicate_strategy_preserves_type_and_weightings(service: StrategyEvaluationService) -> None:
    original = await service.create_strategy("Value Strategy", strategy_type=StrategyType.MOMENTUM)

    duplicate = await service.duplicate_strategy(original.id, "Copy")

    assert duplicate.strategy_type == StrategyType.MOMENTUM


# --- evaluate_recommendations: multi-strategy ranking -----------------------------------------------------------


async def test_evaluate_recommendations_ranks_by_alignment_descending(
    service: StrategyEvaluationService,
) -> None:
    low_rule = make_rule(operator=StrategyOperator.GREATER_THAN, value=1000)  # never passes
    high_strategy = await service.create_strategy("High", rules=())  # component-score only
    low_strategy = await service.create_strategy("Low", rules=(low_rule,))

    result = make_recommendation_result((make_candidate("A", overall_score=90),))
    request = StrategyEvaluationRequest(id="req-1", recommendation_result_id="rec-1", created_at=NOW)

    evaluation = await service.evaluate_recommendations(request, result, [high_strategy, low_strategy])

    assert evaluation.strategy_matches[0].strategy_name == "High"
    assert evaluation.strategy_matches[-1].strategy_name == "Low"


async def test_evaluate_recommendations_deterministic_tiebreak_by_strategy_name(
    service: StrategyEvaluationService,
) -> None:
    strategy_zebra = await service.create_strategy("Zebra", rules=())
    strategy_alpha = await service.create_strategy("Alpha", rules=())

    result = make_recommendation_result((make_candidate("A", overall_score=50),))
    request = StrategyEvaluationRequest(id="req-1", recommendation_result_id="rec-1", created_at=NOW)

    evaluation = await service.evaluate_recommendations(request, result, [strategy_zebra, strategy_alpha])

    assert [m.strategy_name for m in evaluation.strategy_matches] == ["Alpha", "Zebra"]


async def test_evaluate_recommendations_excludes_disabled_strategies(
    service: StrategyEvaluationService,
) -> None:
    enabled = await service.create_strategy("Enabled", rules=())
    disabled = await service.create_strategy("Disabled", rules=(), enabled=False)

    result = make_recommendation_result((make_candidate("A"),))
    request = StrategyEvaluationRequest(id="req-1", recommendation_result_id="rec-1", created_at=NOW)

    evaluation = await service.evaluate_recommendations(request, result, [enabled, disabled])

    assert len(evaluation.strategy_matches) == 1
    assert evaluation.strategy_matches[0].strategy_name == "Enabled"


async def test_evaluate_recommendations_selects_best_strategy(service: StrategyEvaluationService) -> None:
    good_strategy = await service.create_strategy("Good", rules=())
    bad_strategy = await service.create_strategy(
        "Bad", rules=(make_rule(operator=StrategyOperator.GREATER_THAN, value=100000),)
    )

    result = make_recommendation_result((make_candidate("A", overall_score=90),))
    request = StrategyEvaluationRequest(id="req-1", recommendation_result_id="rec-1", created_at=NOW)

    evaluation = await service.evaluate_recommendations(request, result, [good_strategy, bad_strategy])

    assert evaluation.best_strategy == good_strategy.id
    assert evaluation.overall_alignment == evaluation.strategy_matches[0].alignment_score


async def test_evaluate_recommendations_with_no_strategies(service: StrategyEvaluationService) -> None:
    result = make_recommendation_result((make_candidate("A"),))
    request = StrategyEvaluationRequest(id="req-1", recommendation_result_id="rec-1", created_at=NOW)

    evaluation = await service.evaluate_recommendations(request, result, [])

    assert evaluation.strategy_matches == ()
    assert evaluation.best_strategy is None
    assert evaluation.overall_alignment == 0.0


async def test_evaluate_recommendations_summary_aggregates_correctly(
    service: StrategyEvaluationService,
) -> None:
    strategy_a = await service.create_strategy("A", rules=())
    strategy_b = await service.create_strategy("B", rules=())

    result = make_recommendation_result((make_candidate("X", overall_score=100), make_candidate("Y", overall_score=0)))
    request = StrategyEvaluationRequest(id="req-1", recommendation_result_id="rec-1", created_at=NOW)

    evaluation = await service.evaluate_recommendations(request, result, [strategy_a, strategy_b])

    assert evaluation.summary.total_strategies == 2
    assert evaluation.summary.average_alignment == 50.0


# --- store_evaluation / get_evaluation / list_evaluations -----------------------------------------------------------


async def test_evaluate_recommendations_persists_the_result(service: StrategyEvaluationService) -> None:
    strategy = await service.create_strategy("A", rules=())
    result = make_recommendation_result((make_candidate("X"),))
    request = StrategyEvaluationRequest(id="req-1", recommendation_result_id="rec-1", created_at=NOW)

    await service.evaluate_recommendations(request, result, [strategy])
    fetched = await service.get_evaluation(request.id)

    assert fetched.request_id == request.id


async def test_get_evaluation_unknown_request_id_raises(service: StrategyEvaluationService) -> None:
    with pytest.raises(StrategyEvaluationNotFoundError):
        await service.get_evaluation("does-not-exist")


async def test_get_evaluation_returns_most_recent_of_multiple_runs(
    repository: PostgresStrategyRepository,
) -> None:
    clock = {"t": NOW}
    service_with_clock = StrategyEvaluationService(repository, now_fn=lambda: clock["t"])
    strategy_low = await service_with_clock.create_strategy("Low", rules=())
    request = StrategyEvaluationRequest(id="req-1", recommendation_result_id="rec-1", created_at=NOW)

    result_low = make_recommendation_result((make_candidate("A", overall_score=10),))
    await service_with_clock.evaluate_recommendations(request, result_low, [strategy_low])

    clock["t"] = NOW + timedelta(minutes=5)
    result_high = make_recommendation_result((make_candidate("A", overall_score=90),))
    await service_with_clock.evaluate_recommendations(request, result_high, [strategy_low])

    latest = await service_with_clock.get_evaluation(request.id)
    assert latest.overall_alignment == 90.0


async def test_list_evaluations_returns_every_stored_result(service: StrategyEvaluationService) -> None:
    strategy = await service.create_strategy("A", rules=())
    request_a = StrategyEvaluationRequest(id="req-a", recommendation_result_id="rec-a", created_at=NOW)
    request_b = StrategyEvaluationRequest(id="req-b", recommendation_result_id="rec-b", created_at=NOW)

    await service.evaluate_recommendations(request_a, make_recommendation_result(()), [strategy])
    await service.evaluate_recommendations(request_b, make_recommendation_result(()), [strategy])

    evaluations = await service.list_evaluations()

    assert {e.request_id for e in evaluations} == {"req-a", "req-b"}


async def test_list_evaluations_empty_initially(service: StrategyEvaluationService) -> None:
    assert await service.list_evaluations() == []
