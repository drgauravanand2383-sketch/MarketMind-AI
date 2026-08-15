"""Translates between InvestmentStrategy/StrategyEvaluationResult and
their PostgreSQL ORM models. Purely structural mapping in both directions
— no business logic, aside from the same naive-datetime-from-SQLite
normalization `app.repositories.alerts.postgres.mapper` established
(Sprint 48) — see `_ensure_aware` there for the full rationale; repeated
here since these are independent modules with no shared base to place it in.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.repositories.strategy.postgres.models import (
    InvestmentStrategyModel,
    StrategyEvaluationResultModel,
)
from app.strategy.models import (
    InvestmentStrategy,
    StrategyEvaluationResult,
    StrategyMatch,
    StrategyRule,
    StrategySummary,
    StrategyWeighting,
)

__all__ = ["strategy_to_model", "model_to_strategy", "evaluation_to_model", "model_to_evaluation"]


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def strategy_to_model(strategy: InvestmentStrategy) -> InvestmentStrategyModel:
    """Map an `InvestmentStrategy` into an `InvestmentStrategyModel` ready to persist."""
    return InvestmentStrategyModel(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        strategy_type=strategy.strategy_type.value,
        enabled=strategy.enabled,
        weightings=strategy.weightings.model_dump(mode="json"),
        rules=[r.model_dump(mode="json") for r in strategy.rules],
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
    )


def model_to_strategy(model: InvestmentStrategyModel) -> InvestmentStrategy:
    """Map an `InvestmentStrategyModel` row into an `InvestmentStrategy`."""
    return InvestmentStrategy(
        id=model.id,
        name=model.name,
        description=model.description,
        strategy_type=model.strategy_type,
        enabled=model.enabled,
        weightings=StrategyWeighting.model_validate(model.weightings),
        rules=tuple(StrategyRule.model_validate(r) for r in model.rules),
        created_at=_ensure_aware(model.created_at),
        updated_at=_ensure_aware(model.updated_at),
    )


def evaluation_to_model(result: StrategyEvaluationResult) -> StrategyEvaluationResultModel:
    """Map a `StrategyEvaluationResult` into a `StrategyEvaluationResultModel` ready to persist."""
    return StrategyEvaluationResultModel(
        request_id=result.request_id,
        evaluated_at=result.evaluated_at,
        overall_alignment=result.overall_alignment,
        best_strategy=result.best_strategy,
        strategy_matches=[m.model_dump(mode="json") for m in result.strategy_matches],
        summary=result.summary.model_dump(mode="json"),
        recommendation_result_id=result.recommendation_result_id,
    )


def model_to_evaluation(model: StrategyEvaluationResultModel) -> StrategyEvaluationResult:
    """Map a `StrategyEvaluationResultModel` row into a `StrategyEvaluationResult`."""
    return StrategyEvaluationResult(
        request_id=model.request_id,
        evaluated_at=_ensure_aware(model.evaluated_at),
        overall_alignment=model.overall_alignment,
        best_strategy=model.best_strategy,
        strategy_matches=tuple(StrategyMatch.model_validate(m) for m in model.strategy_matches),
        summary=StrategySummary.model_validate(model.summary),
        recommendation_result_id=model.recommendation_result_id,
    )
