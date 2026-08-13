"""Tests for Explainability & Performance Attribution domain models:
validation rules and structural defaults."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.explainability.models import (
    AttributionCategory,
    ContributionBreakdown,
    ExplainabilityRequest,
    ExplainabilityResult,
    ExplainabilityWeighting,
    PerformanceAttribution,
    RecommendationExplanation,
    RiskExplanation,
    StrategyExplanation,
)
from app.risk.models import RiskSeverity

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


def _request(**overrides: object) -> ExplainabilityRequest:
    defaults: dict[str, object] = {
        "id": "r1", "name": "Explain", "recommendation_result_id": "rec-1", "created_at": NOW,
    }
    defaults.update(overrides)
    return ExplainabilityRequest(**defaults)


# --- AttributionCategory -----------------------------------------------------------


def test_attribution_category_supports_all_twelve_categories() -> None:
    assert {c.value for c in AttributionCategory} == {
        "PLANNING", "SCREENING", "SIGNALS", "ALERTS", "RESEARCH", "PORTFOLIO_INTELLIGENCE",
        "STRATEGY", "RISK", "SECTOR", "COUNTRY", "INDUSTRY", "CUSTOM",
    }


# --- ExplainabilityWeighting -----------------------------------------------------------


def test_weighting_defaults_to_one_for_every_category() -> None:
    weighting = ExplainabilityWeighting()
    assert weighting.planning == weighting.screening == weighting.risk == 1.0


def test_weighting_rejects_non_positive_weight() -> None:
    with pytest.raises(ValidationError):
        ExplainabilityWeighting(planning=0.0)
    with pytest.raises(ValidationError):
        ExplainabilityWeighting(risk=-1.0)


def test_weighting_is_frozen() -> None:
    weighting = ExplainabilityWeighting()
    with pytest.raises(ValidationError):
        weighting.planning = 5.0  # type: ignore[misc]


# --- ExplainabilityRequest -----------------------------------------------------------


def test_request_accepts_minimal_fields() -> None:
    request = _request()
    assert request.strategy_evaluation_id is None
    assert request.risk_assessment_id is None
    assert request.backtest_run_id is None


def test_request_accepts_all_optional_references() -> None:
    request = _request(strategy_evaluation_id="s1", risk_assessment_id="k1", backtest_run_id="b1")
    assert request.strategy_evaluation_id == "s1"
    assert request.risk_assessment_id == "k1"
    assert request.backtest_run_id == "b1"


def test_request_rejects_blank_recommendation_result_id() -> None:
    with pytest.raises(ValidationError):
        _request(recommendation_result_id="")


def test_request_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        _request(name="")


def test_request_rejects_blank_id() -> None:
    with pytest.raises(ValidationError):
        _request(id="")


def test_request_is_frozen() -> None:
    request = _request()
    with pytest.raises(ValidationError):
        request.name = "New"  # type: ignore[misc]


def test_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _request(unexpected="x")


# --- ContributionBreakdown -----------------------------------------------------------


def test_contribution_breakdown_accepts_valid_fields() -> None:
    entry = ContributionBreakdown(
        source="AAPL", category=AttributionCategory.SCREENING, weight=1.0, contribution_percent=25.0,
        description="x",
    )
    assert entry.category == AttributionCategory.SCREENING


# --- RecommendationExplanation -----------------------------------------------------------


def test_recommendation_explanation_defaults_to_empty_tuples() -> None:
    explanation = RecommendationExplanation(
        ticker="AAPL", overall_score=70.0, confidence=80.0, reasoning="x", summary="x",
    )
    assert explanation.contributing_components == ()
    assert explanation.top_positive_factors == ()
    assert explanation.top_negative_factors == ()
    assert explanation.company_name is None


# --- StrategyExplanation -----------------------------------------------------------


def test_strategy_explanation_defaults_to_empty_tuples() -> None:
    explanation = StrategyExplanation(strategy_name="Value", alignment_score=70.0, summary="x")
    assert explanation.matched_rules == ()
    assert explanation.failed_rules == ()
    assert explanation.weight_breakdown == ()


# --- RiskExplanation -----------------------------------------------------------


def test_risk_explanation_defaults_to_empty_collections() -> None:
    explanation = RiskExplanation(overall_risk_score=20.0, summary="x")
    assert explanation.category_breakdown == ()
    assert explanation.severity_breakdown == {}
    assert explanation.exposure_breakdown == ()


def test_risk_explanation_accepts_severity_breakdown() -> None:
    explanation = RiskExplanation(
        overall_risk_score=20.0, severity_breakdown={RiskSeverity.LOW: 3, RiskSeverity.HIGH: 1}, summary="x"
    )
    assert explanation.severity_breakdown[RiskSeverity.LOW] == 3


# --- PerformanceAttribution -----------------------------------------------------------


def test_performance_attribution_accepts_valid_fields() -> None:
    attribution = PerformanceAttribution(
        period="2026-01-01 to 2026-01-31", portfolio_return=5.0, benchmark_return=3.0, excess_return=2.0,
        summary="x",
    )
    assert attribution.contribution_breakdown == ()


def test_performance_attribution_allows_negative_returns() -> None:
    attribution = PerformanceAttribution(
        period="x", portfolio_return=-5.0, benchmark_return=-2.0, excess_return=-3.0, summary="x"
    )
    assert attribution.portfolio_return == -5.0


# --- ExplainabilityResult -----------------------------------------------------------


def test_result_defaults_to_empty_and_none() -> None:
    result = ExplainabilityResult(request_id="r1", generated_at=NOW, overall_summary="x")
    assert result.recommendation_explanations == ()
    assert result.strategy_explanations == ()
    assert result.risk_explanation is None
    assert result.performance_attribution is None
