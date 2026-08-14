"""Translates between RiskAssessmentRequest/RiskAssessment and their
PostgreSQL ORM models. Purely structural mapping in both directions — no
business logic, aside from the same naive-datetime-from-SQLite
normalization `app.repositories.alerts.postgres.mapper` established
(Sprint 48) — see `_ensure_aware` there for the full rationale; repeated
here since these are independent modules with no shared base to place it in.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.repositories.risk.postgres.models import RiskAssessmentModel, RiskAssessmentRequestModel
from app.risk.models import (
    MarketDataCoverage,
    MarketDataCoverageStatus,
    PortfolioExposure,
    RiskAssessment,
    RiskAssessmentRequest,
    RiskMetric,
)

__all__ = ["request_to_model", "model_to_request", "assessment_to_model", "model_to_assessment"]


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def request_to_model(request: RiskAssessmentRequest) -> RiskAssessmentRequestModel:
    """Map a `RiskAssessmentRequest` into a `RiskAssessmentRequestModel` ready to persist."""
    return RiskAssessmentRequestModel(
        id=request.id,
        request_name=request.request_name,
        portfolio_id=request.portfolio_id,
        strategy_evaluation_id=request.strategy_evaluation_id,
        recommendation_result_id=request.recommendation_result_id,
        created_at=request.created_at,
    )


def model_to_request(model: RiskAssessmentRequestModel) -> RiskAssessmentRequest:
    """Map a `RiskAssessmentRequestModel` row into a `RiskAssessmentRequest`."""
    return RiskAssessmentRequest(
        id=model.id,
        request_name=model.request_name,
        portfolio_id=model.portfolio_id,
        strategy_evaluation_id=model.strategy_evaluation_id,
        recommendation_result_id=model.recommendation_result_id,
        created_at=_ensure_aware(model.created_at),
    )


def assessment_to_model(assessment: RiskAssessment) -> RiskAssessmentModel:
    """Map a `RiskAssessment` into a `RiskAssessmentModel` ready to persist."""
    return RiskAssessmentModel(
        request_id=assessment.request_id,
        overall_risk_score=assessment.overall_risk_score,
        overall_severity=assessment.overall_severity.value,
        risk_metrics=[m.model_dump(mode="json") for m in assessment.risk_metrics],
        exposures=[e.model_dump(mode="json") for e in assessment.exposures],
        recommendations=list(assessment.recommendations),
        summary=assessment.summary,
        market_data_coverage=assessment.market_data_coverage.model_dump(mode="json"),
        generated_at=assessment.generated_at,
    )


def model_to_assessment(model: RiskAssessmentModel) -> RiskAssessment:
    """Map a `RiskAssessmentModel` row into a `RiskAssessment`. A `None`
    `market_data_coverage` (a row written before Milestone 14 added the
    column) maps to the same `NOT_EVALUATED` default the Pydantic model
    itself uses — never fabricated coverage data for an old row."""
    coverage = (
        MarketDataCoverage.model_validate(model.market_data_coverage)
        if model.market_data_coverage is not None
        else MarketDataCoverage(status=MarketDataCoverageStatus.NOT_EVALUATED)
    )
    return RiskAssessment(
        request_id=model.request_id,
        overall_risk_score=model.overall_risk_score,
        overall_severity=model.overall_severity,
        risk_metrics=tuple(RiskMetric.model_validate(m) for m in model.risk_metrics),
        exposures=tuple(PortfolioExposure.model_validate(e) for e in model.exposures),
        recommendations=tuple(model.recommendations),
        summary=model.summary,
        market_data_coverage=coverage,
        generated_at=_ensure_aware(model.generated_at),
    )
