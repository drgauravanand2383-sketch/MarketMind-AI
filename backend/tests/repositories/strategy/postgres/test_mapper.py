"""Tests for the Strategy Postgres mapper: purely structural round-trips,
plus the naive-datetime normalization `_ensure_aware` performs (mirrors
the Alert/Recommendation Postgres mappers' own regression tests)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.repositories.strategy.postgres.mapper import (
    evaluation_to_model,
    model_to_evaluation,
    model_to_strategy,
    strategy_to_model,
)
from app.repositories.strategy.postgres.models import (
    InvestmentStrategyModel,
    StrategyEvaluationResultModel,
)
from app.strategy.models import (
    InvestmentStrategy,
    StrategyEvaluationResult,
    StrategyMatch,
    StrategyOperator,
    StrategyRule,
    StrategySummary,
    StrategyType,
    StrategyWeighting,
)

NOW = datetime(2026, 8, 10, tzinfo=UTC)


def test_strategy_with_rules_and_weightings_round_trips() -> None:
    strategy = InvestmentStrategy(
        id="s1",
        name="Value",
        description="Cheap companies",
        strategy_type=StrategyType.VALUE,
        enabled=True,
        weightings=StrategyWeighting(overall_score=2.0, screening_score=3.0),
        rules=(
            StrategyRule(id="r1", field="overall_score", operator=StrategyOperator.GREATER_THAN, value=50, weight=2.0),
            StrategyRule(id="r2", field="sector", operator=StrategyOperator.IN, value=["Tech", "Energy"]),
        ),
        created_at=NOW,
        updated_at=NOW,
    )

    model = strategy_to_model(strategy)
    restored = model_to_strategy(model)

    assert restored == strategy


def test_strategy_with_no_rules_round_trips() -> None:
    strategy = InvestmentStrategy(id="s1", name="Empty", created_at=NOW, updated_at=NOW)

    model = strategy_to_model(strategy)
    restored = model_to_strategy(model)

    assert restored.rules == ()
    assert restored.weightings == StrategyWeighting()


def test_between_operator_value_round_trips_as_a_list() -> None:
    strategy = InvestmentStrategy(
        id="s1", name="Value", created_at=NOW, updated_at=NOW,
        rules=(StrategyRule(id="r1", field="overall_score", operator=StrategyOperator.BETWEEN, value=[10, 20]),),
    )

    model = strategy_to_model(strategy)
    restored = model_to_strategy(model)

    assert restored.rules[0].value == [10, 20]


def test_evaluation_with_matches_round_trips() -> None:
    match = StrategyMatch(strategy_id="s1", strategy_name="Value", alignment_score=80.0, confidence=90.0, reasoning="x")
    result = StrategyEvaluationResult(
        request_id="req-1",
        evaluated_at=NOW,
        overall_alignment=80.0,
        best_strategy="s1",
        strategy_matches=(match,),
        summary=StrategySummary(total_strategies=1, best_alignment=80.0, average_alignment=80.0, highest_confidence=90.0),
    )

    model = evaluation_to_model(result)
    restored = model_to_evaluation(model)

    assert restored == result


def test_evaluation_with_no_matches_round_trips() -> None:
    result = StrategyEvaluationResult(
        request_id="req-1", evaluated_at=NOW, overall_alignment=0.0, summary=StrategySummary()
    )

    model = evaluation_to_model(result)
    restored = model_to_evaluation(model)

    assert restored.strategy_matches == ()
    assert restored.best_strategy is None


def test_model_to_strategy_normalizes_naive_datetime_to_utc() -> None:
    model = InvestmentStrategyModel(
        id="s1", name="X", description="", strategy_type="CUSTOM", enabled=True,
        weightings={}, rules=[],
        created_at=datetime(2026, 1, 1),  # naive, as SQLite round-trips it
        updated_at=datetime(2026, 1, 1),
    )

    restored = model_to_strategy(model)

    assert restored.created_at.tzinfo is not None
    assert restored.updated_at.tzinfo is not None


def test_model_to_evaluation_normalizes_naive_datetime_to_utc() -> None:
    model = StrategyEvaluationResultModel(
        request_id="req-1", overall_alignment=0.0, strategy_matches=[], summary={},
        evaluated_at=datetime(2026, 1, 1),  # naive
    )

    restored = model_to_evaluation(model)

    assert restored.evaluated_at.tzinfo is not None
