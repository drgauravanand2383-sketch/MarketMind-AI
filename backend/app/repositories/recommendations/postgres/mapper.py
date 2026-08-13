"""Translates between RecommendationRequest/RecommendationResult and their
PostgreSQL ORM models. Purely structural mapping in both directions — no
business logic, aside from the same naive-datetime-from-SQLite
normalization `app.repositories.alerts.postgres.mapper` already
established (Sprint 48) — see `_ensure_aware` there for the full
rationale; repeated here since these are two independent modules with no
shared base to place it in.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.recommendations.models import (
    RecommendationCandidate,
    RecommendationRequest,
    RecommendationResult,
    RecommendationSummary,
)
from app.repositories.recommendations.postgres.models import (
    RecommendationRequestModel,
    RecommendationResultModel,
)

__all__ = ["request_to_model", "model_to_request", "result_to_model", "model_to_result"]


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def request_to_model(request: RecommendationRequest) -> RecommendationRequestModel:
    """Map a `RecommendationRequest` into a `RecommendationRequestModel` ready to persist."""
    return RecommendationRequestModel(
        id=request.id,
        request_name=request.request_name,
        watchlist_ids=list(request.watchlist_ids),
        screening_profile_ids=list(request.screening_profile_ids),
        signal_definition_ids=list(request.signal_definition_ids),
        alert_rule_ids=list(request.alert_rule_ids),
        planning_context=dict(request.planning_context),
        max_recommendations=request.max_recommendations,
        minimum_score=request.minimum_score,
        created_at=request.created_at,
    )


def model_to_request(model: RecommendationRequestModel) -> RecommendationRequest:
    """Map a `RecommendationRequestModel` row into a `RecommendationRequest`."""
    return RecommendationRequest(
        id=model.id,
        request_name=model.request_name,
        watchlist_ids=tuple(model.watchlist_ids),
        screening_profile_ids=tuple(model.screening_profile_ids),
        signal_definition_ids=tuple(model.signal_definition_ids),
        alert_rule_ids=tuple(model.alert_rule_ids),
        planning_context=dict(model.planning_context),
        max_recommendations=model.max_recommendations,
        minimum_score=model.minimum_score,
        created_at=_ensure_aware(model.created_at),
    )


def result_to_model(result: RecommendationResult) -> RecommendationResultModel:
    """Map a `RecommendationResult` into a `RecommendationResultModel` ready to persist."""
    return RecommendationResultModel(
        request_id=result.request_id,
        generated_at=result.generated_at,
        total_candidates=result.total_candidates,
        recommendations=[c.model_dump(mode="json") for c in result.recommendations],
        summary=result.summary.model_dump(mode="json"),
    )


def model_to_result(model: RecommendationResultModel) -> RecommendationResult:
    """Map a `RecommendationResultModel` row into a `RecommendationResult`."""
    return RecommendationResult(
        request_id=model.request_id,
        generated_at=_ensure_aware(model.generated_at),
        total_candidates=model.total_candidates,
        recommendations=tuple(RecommendationCandidate.model_validate(c) for c in model.recommendations),
        summary=RecommendationSummary.model_validate(model.summary),
    )
