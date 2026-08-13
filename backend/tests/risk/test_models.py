"""Tests for the Risk Analytics Engine's domain models: RiskWeighting
(positive weights), RiskThresholds (strictly ascending, classify()),
RiskAssessmentRequest, PortfolioExposure, RiskMetric, and RiskAssessment."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.risk.models import (
    PortfolioExposure,
    RiskAssessment,
    RiskAssessmentRequest,
    RiskCategory,
    RiskMetric,
    RiskSeverity,
    RiskThresholds,
    RiskWeighting,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)

# --- RiskWeighting -----------------------------------------------------------


def test_risk_weighting_defaults_are_all_positive() -> None:
    weighting = RiskWeighting()
    assert weighting.diversification > 0
    assert weighting.concentration > 0
    assert weighting.sector > 0
    assert weighting.geographic > 0
    assert weighting.market_cap > 0
    assert weighting.volatility > 0
    assert weighting.liquidity > 0


@pytest.mark.parametrize(
    "field", ["diversification", "concentration", "sector", "geographic", "market_cap", "volatility", "liquidity"]
)
def test_risk_weighting_rejects_zero(field: str) -> None:
    with pytest.raises(ValidationError):
        RiskWeighting(**{field: 0})


@pytest.mark.parametrize(
    "field", ["diversification", "concentration", "sector", "geographic", "market_cap", "volatility", "liquidity"]
)
def test_risk_weighting_rejects_negative(field: str) -> None:
    with pytest.raises(ValidationError):
        RiskWeighting(**{field: -1})


def test_risk_weighting_is_frozen() -> None:
    weighting = RiskWeighting()
    with pytest.raises(ValidationError):
        weighting.diversification = 5.0


# --- RiskThresholds -----------------------------------------------------------


def test_risk_thresholds_defaults() -> None:
    thresholds = RiskThresholds()
    assert thresholds.moderate_min == 25.0
    assert thresholds.high_min == 50.0
    assert thresholds.critical_min == 75.0


def test_risk_thresholds_rejects_non_ascending_order() -> None:
    with pytest.raises(ValidationError):
        RiskThresholds(moderate_min=60, high_min=50, critical_min=75)


def test_risk_thresholds_rejects_equal_adjacent_bounds() -> None:
    with pytest.raises(ValidationError):
        RiskThresholds(moderate_min=50, high_min=50, critical_min=75)


def test_risk_thresholds_accepts_valid_custom_ordering() -> None:
    thresholds = RiskThresholds(moderate_min=10, high_min=40, critical_min=80)
    assert thresholds.moderate_min == 10


@pytest.mark.parametrize("field", ["moderate_min", "high_min", "critical_min"])
def test_risk_thresholds_rejects_out_of_range(field: str) -> None:
    with pytest.raises(ValidationError):
        RiskThresholds(**{field: 150})
    with pytest.raises(ValidationError):
        RiskThresholds(**{field: -1})


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, RiskSeverity.LOW),
        (24.99, RiskSeverity.LOW),
        (25, RiskSeverity.MODERATE),
        (49.99, RiskSeverity.MODERATE),
        (50, RiskSeverity.HIGH),
        (74.99, RiskSeverity.HIGH),
        (75, RiskSeverity.CRITICAL),
        (100, RiskSeverity.CRITICAL),
    ],
)
def test_classify_default_thresholds(score: float, expected: RiskSeverity) -> None:
    assert RiskThresholds().classify(score) == expected


def test_classify_with_custom_thresholds() -> None:
    thresholds = RiskThresholds(moderate_min=10, high_min=40, critical_min=80)
    assert thresholds.classify(10) == RiskSeverity.MODERATE
    assert thresholds.classify(9.99) == RiskSeverity.LOW
    assert thresholds.classify(80) == RiskSeverity.CRITICAL


def test_no_overlap_every_score_maps_to_exactly_one_severity() -> None:
    thresholds = RiskThresholds()
    for score in range(0, 101):
        result = thresholds.classify(score)
        assert result in RiskSeverity


# --- RiskAssessmentRequest -----------------------------------------------------------


def test_risk_assessment_request_requires_name() -> None:
    with pytest.raises(ValidationError):
        RiskAssessmentRequest(
            id="r1", request_name="", portfolio_id="p1", recommendation_result_id="rec-1", created_at=NOW
        )


def test_risk_assessment_request_requires_portfolio_id() -> None:
    with pytest.raises(ValidationError):
        RiskAssessmentRequest(
            id="r1", request_name="X", portfolio_id="", recommendation_result_id="rec-1", created_at=NOW
        )


def test_risk_assessment_request_requires_recommendation_result_id() -> None:
    with pytest.raises(ValidationError):
        RiskAssessmentRequest(
            id="r1", request_name="X", portfolio_id="p1", recommendation_result_id="", created_at=NOW
        )


def test_risk_assessment_request_strategy_evaluation_id_is_optional() -> None:
    request = RiskAssessmentRequest(
        id="r1", request_name="X", portfolio_id="p1", recommendation_result_id="rec-1", created_at=NOW
    )
    assert request.strategy_evaluation_id is None


def test_risk_assessment_request_is_frozen() -> None:
    request = RiskAssessmentRequest(
        id="r1", request_name="X", portfolio_id="p1", recommendation_result_id="rec-1", created_at=NOW
    )
    with pytest.raises(ValidationError):
        request.request_name = "Y"


# --- PortfolioExposure -----------------------------------------------------------


def test_portfolio_exposure_weight_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        PortfolioExposure(sector="Tech", weight=1.5, holding_count=1)
    with pytest.raises(ValidationError):
        PortfolioExposure(sector="Tech", weight=-0.1, holding_count=1)


def test_portfolio_exposure_holding_count_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        PortfolioExposure(sector="Tech", weight=0.5, holding_count=-1)


def test_portfolio_exposure_allows_only_one_dimension_populated() -> None:
    exposure = PortfolioExposure(sector="Tech", weight=1.0, holding_count=1)
    assert exposure.country is None
    assert exposure.industry is None


# --- RiskMetric -----------------------------------------------------------


def test_risk_metric_score_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        RiskMetric(
            metric_name="X", category=RiskCategory.CONCENTRATION, value=1.0, score=101,
            severity=RiskSeverity.LOW, description="x",
        )
    with pytest.raises(ValidationError):
        RiskMetric(
            metric_name="X", category=RiskCategory.CONCENTRATION, value=1.0, score=-1,
            severity=RiskSeverity.LOW, description="x",
        )


def test_risk_metric_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        RiskMetric(
            metric_name="X", category="NOT_A_CATEGORY", value=1.0, score=50,
            severity=RiskSeverity.LOW, description="x",
        )


@pytest.mark.parametrize("category", list(RiskCategory))
def test_risk_metric_accepts_every_category(category: RiskCategory) -> None:
    metric = RiskMetric(
        metric_name="X", category=category, value=1.0, score=50, severity=RiskSeverity.LOW, description="x"
    )
    assert metric.category == category


# --- RiskAssessment -----------------------------------------------------------


def test_risk_assessment_overall_risk_score_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        RiskAssessment(
            request_id="r1", overall_risk_score=150, overall_severity=RiskSeverity.LOW,
            summary="x", generated_at=NOW,
        )


def test_risk_assessment_defaults() -> None:
    assessment = RiskAssessment(
        request_id="r1", overall_risk_score=50.0, overall_severity=RiskSeverity.HIGH,
        summary="x", generated_at=NOW,
    )
    assert assessment.risk_metrics == ()
    assert assessment.exposures == ()
    assert assessment.recommendations == ()
