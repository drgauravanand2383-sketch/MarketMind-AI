"""Tests for the Risk Analytics Postgres mapper: purely structural
round-trips, plus the naive-datetime normalization `_ensure_aware`
performs (mirrors the Alert/Recommendation/Strategy Postgres mappers'
own regression tests)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.repositories.risk.postgres.mapper import (
    assessment_to_model,
    model_to_assessment,
    model_to_request,
    request_to_model,
)
from app.repositories.risk.postgres.models import RiskAssessmentModel, RiskAssessmentRequestModel
from app.risk.models import (
    PortfolioExposure,
    RiskAssessment,
    RiskAssessmentRequest,
    RiskCategory,
    RiskMetric,
    RiskSeverity,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def test_request_round_trips() -> None:
    request = RiskAssessmentRequest(
        id="r1", request_name="Value", portfolio_id="p1", strategy_evaluation_id="strat-1",
        recommendation_result_id="rec-1", created_at=NOW,
    )

    model = request_to_model(request)
    restored = model_to_request(model)

    assert restored == request


def test_request_with_no_strategy_evaluation_id_round_trips() -> None:
    request = RiskAssessmentRequest(
        id="r1", request_name="Value", portfolio_id="p1", recommendation_result_id="rec-1", created_at=NOW
    )

    model = request_to_model(request)
    restored = model_to_request(model)

    assert restored.strategy_evaluation_id is None


def test_assessment_with_metrics_and_exposures_round_trips() -> None:
    metric = RiskMetric(
        metric_name="Holding Concentration", category=RiskCategory.CONCENTRATION, value=0.5,
        score=50.0, severity=RiskSeverity.HIGH, description="x",
    )
    exposure = PortfolioExposure(sector="Tech", weight=1.0, holding_count=2)
    assessment = RiskAssessment(
        request_id="r1", overall_risk_score=50.0, overall_severity=RiskSeverity.HIGH,
        risk_metrics=(metric,), exposures=(exposure,), recommendations=("Reduce concentration",),
        summary="x", generated_at=NOW,
    )

    model = assessment_to_model(assessment)
    restored = model_to_assessment(model)

    assert restored == assessment


def test_assessment_with_no_metrics_or_exposures_round_trips() -> None:
    assessment = RiskAssessment(
        request_id="r1", overall_risk_score=0.0, overall_severity=RiskSeverity.LOW, summary="x", generated_at=NOW
    )

    model = assessment_to_model(assessment)
    restored = model_to_assessment(model)

    assert restored.risk_metrics == ()
    assert restored.exposures == ()
    assert restored.recommendations == ()


def test_model_to_request_normalizes_naive_datetime_to_utc() -> None:
    model = RiskAssessmentRequestModel(
        id="r1", request_name="X", portfolio_id="p1", strategy_evaluation_id=None,
        recommendation_result_id="rec-1",
        created_at=datetime(2026, 1, 1),  # naive, as SQLite round-trips it
    )

    restored = model_to_request(model)

    assert restored.created_at.tzinfo is not None


def test_model_to_assessment_normalizes_naive_datetime_to_utc() -> None:
    model = RiskAssessmentModel(
        request_id="r1", overall_risk_score=0.0, overall_severity="LOW",
        risk_metrics=[], exposures=[], recommendations=[], summary="x",
        generated_at=datetime(2026, 1, 1),  # naive
    )

    restored = model_to_assessment(model)

    assert restored.generated_at.tzinfo is not None
