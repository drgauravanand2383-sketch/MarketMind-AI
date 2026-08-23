"""Tests for the Explainability Postgres mapper: purely structural
round-trips, plus the naive-datetime normalization `_ensure_aware`
performs (mirrors the Alert/Recommendation/Strategy/Risk/Backtesting
Postgres mappers' own regression tests)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.explainability.models import (
    AttributionCategory,
    ContributionBreakdown,
    ExplainabilityRequest,
    ExplainabilityResult,
    PerformanceAttribution,
    RecommendationExplanation,
    RiskExplanation,
    StrategyExplanation,
)
from app.repositories.explainability.postgres.mapper import (
    model_to_request,
    model_to_result,
    request_to_model,
    result_to_model,
)
from app.repositories.explainability.postgres.models import (
    ExplainabilityRequestModel,
    ExplainabilityResultModel,
)
from app.risk.models import PortfolioExposure, RiskCategory, RiskMetric, RiskSeverity
from app.strategy.models import RuleAlignment, StrategyOperator

NOW = datetime(2026, 8, 7, tzinfo=UTC)


def test_request_round_trips() -> None:
    request = ExplainabilityRequest(
        id="r1", name="Explain", recommendation_result_id="rec-1", strategy_evaluation_id="strat-1",
        risk_assessment_id="risk-1", backtest_run_id="bt-1", created_at=NOW,
    )

    model = request_to_model(request)
    restored = model_to_request(model)

    assert restored == request


def test_request_with_no_optional_references_round_trips() -> None:
    request = ExplainabilityRequest(id="r1", name="Explain", recommendation_result_id="rec-1", created_at=NOW)

    model = request_to_model(request)
    restored = model_to_request(model)

    assert restored.strategy_evaluation_id is None
    assert restored.risk_assessment_id is None
    assert restored.backtest_run_id is None


def test_result_with_every_explanation_type_round_trips() -> None:
    contribution = ContributionBreakdown(
        source="AAPL", category=AttributionCategory.SCREENING, weight=1.0, contribution_percent=50.0,
        description="x",
    )
    recommendation_explanation = RecommendationExplanation(
        ticker="AAPL", overall_score=70.0, confidence=80.0, contributing_components=(contribution,),
        top_positive_factors=(contribution,), reasoning="x", summary="x",
    )
    rule = RuleAlignment(
        rule_id="r1", field="overall_score", operator=StrategyOperator.GREATER_THAN, weight=1.0,
        pass_rate=1.0, evaluated_candidate_count=1, reason="x",
    )
    strategy_explanation = StrategyExplanation(
        strategy_name="Value", alignment_score=70.0, matched_rules=(rule,), weight_breakdown=(contribution,),
        summary="x",
    )
    metric = RiskMetric(
        metric_name="X", category=RiskCategory.CONCENTRATION, value=0.5, score=50.0, severity=RiskSeverity.MODERATE,
        description="x",
    )
    exposure = PortfolioExposure(sector="Tech", weight=0.5, holding_count=1)
    risk_explanation = RiskExplanation(
        overall_risk_score=50.0, category_breakdown=(metric,), severity_breakdown={RiskSeverity.MODERATE: 1},
        exposure_breakdown=(exposure,), summary="x",
    )
    attribution = PerformanceAttribution(
        period="x", portfolio_return=5.0, benchmark_return=3.0, excess_return=2.0,
        contribution_breakdown=(contribution,), summary="x",
    )
    result = ExplainabilityResult(
        request_id="r1", generated_at=NOW, recommendation_explanations=(recommendation_explanation,),
        strategy_explanations=(strategy_explanation,), risk_explanation=risk_explanation,
        performance_attribution=attribution, overall_summary="x",
    )

    model = result_to_model(result)
    restored = model_to_result(model)

    assert restored == result


def test_result_with_no_optional_explanations_round_trips() -> None:
    result = ExplainabilityResult(request_id="r1", generated_at=NOW, overall_summary="x")

    model = result_to_model(result)
    restored = model_to_result(model)

    assert restored.recommendation_explanations == ()
    assert restored.strategy_explanations == ()
    assert restored.risk_explanation is None
    assert restored.performance_attribution is None


def test_model_to_request_normalizes_naive_datetime_to_utc() -> None:
    model = ExplainabilityRequestModel(
        id="r1", name="X", recommendation_result_id="rec-1", strategy_evaluation_id=None,
        risk_assessment_id=None, backtest_run_id=None,
        created_at=datetime(2026, 1, 1),  # naive, as SQLite round-trips it
    )

    restored = model_to_request(model)

    assert restored.created_at.tzinfo is not None


def test_model_to_result_normalizes_naive_datetime_to_utc() -> None:
    model = ExplainabilityResultModel(
        request_id="r1", recommendation_explanations=[], strategy_explanations=[], risk_explanation=None,
        performance_attribution=None, overall_summary="x",
        generated_at=datetime(2026, 1, 1),  # naive
    )

    restored = model_to_result(model)

    assert restored.generated_at.tzinfo is not None
