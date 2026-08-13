"""Translates between ExplainabilityRequest/ExplainabilityResult and their
PostgreSQL ORM models. Purely structural mapping in both directions — no
business logic, aside from the same naive-datetime-from-SQLite
normalization `app.repositories.alerts.postgres.mapper` established
(Sprint 48) — see `_ensure_aware` there for the full rationale; repeated
here since these are independent modules with no shared base to place it in.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.explainability.models import (
    ExplainabilityRequest,
    ExplainabilityResult,
    PerformanceAttribution,
    RecommendationExplanation,
    RiskExplanation,
    StrategyExplanation,
)
from app.repositories.explainability.postgres.models import (
    ExplainabilityRequestModel,
    ExplainabilityResultModel,
)

__all__ = ["request_to_model", "model_to_request", "result_to_model", "model_to_result"]


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def request_to_model(request: ExplainabilityRequest) -> ExplainabilityRequestModel:
    """Map an `ExplainabilityRequest` into an `ExplainabilityRequestModel` ready to persist."""
    return ExplainabilityRequestModel(
        id=request.id,
        name=request.name,
        recommendation_result_id=request.recommendation_result_id,
        strategy_evaluation_id=request.strategy_evaluation_id,
        risk_assessment_id=request.risk_assessment_id,
        backtest_run_id=request.backtest_run_id,
        created_at=request.created_at,
    )


def model_to_request(model: ExplainabilityRequestModel) -> ExplainabilityRequest:
    """Map an `ExplainabilityRequestModel` row into an `ExplainabilityRequest`."""
    return ExplainabilityRequest(
        id=model.id,
        name=model.name,
        recommendation_result_id=model.recommendation_result_id,
        strategy_evaluation_id=model.strategy_evaluation_id,
        risk_assessment_id=model.risk_assessment_id,
        backtest_run_id=model.backtest_run_id,
        created_at=_ensure_aware(model.created_at),
    )


def result_to_model(result: ExplainabilityResult) -> ExplainabilityResultModel:
    """Map an `ExplainabilityResult` into an `ExplainabilityResultModel` ready to persist."""
    return ExplainabilityResultModel(
        request_id=result.request_id,
        recommendation_explanations=[e.model_dump(mode="json") for e in result.recommendation_explanations],
        strategy_explanations=[e.model_dump(mode="json") for e in result.strategy_explanations],
        risk_explanation=result.risk_explanation.model_dump(mode="json") if result.risk_explanation else None,
        performance_attribution=(
            result.performance_attribution.model_dump(mode="json") if result.performance_attribution else None
        ),
        overall_summary=result.overall_summary,
        generated_at=result.generated_at,
    )


def model_to_result(model: ExplainabilityResultModel) -> ExplainabilityResult:
    """Map an `ExplainabilityResultModel` row into an `ExplainabilityResult`."""
    return ExplainabilityResult(
        request_id=model.request_id,
        generated_at=_ensure_aware(model.generated_at),
        recommendation_explanations=tuple(
            RecommendationExplanation.model_validate(e) for e in model.recommendation_explanations
        ),
        strategy_explanations=tuple(StrategyExplanation.model_validate(e) for e in model.strategy_explanations),
        risk_explanation=(
            RiskExplanation.model_validate(model.risk_explanation) if model.risk_explanation is not None else None
        ),
        performance_attribution=(
            PerformanceAttribution.model_validate(model.performance_attribution)
            if model.performance_attribution is not None
            else None
        ),
        overall_summary=model.overall_summary,
    )
