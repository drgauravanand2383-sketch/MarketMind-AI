"""Tests for ExplainabilityService's per-item explanation methods:
explain_recommendation, explain_strategy, explain_risk — contribution
aggregation, ranking, and reuse of already-computed data (never
recalculated)."""

from __future__ import annotations

from app.explainability.engine import ExplainabilityService
from app.explainability.models import AttributionCategory
from app.risk.models import PortfolioExposure, RiskCategory, RiskSeverity
from tests.explainability.conftest import (
    make_candidate,
    make_risk_assessment,
    make_risk_metric,
    make_rule_alignment,
    make_strategy_match,
)

# --- explain_recommendation -----------------------------------------------------------


def test_explain_recommendation_includes_every_present_component(service: ExplainabilityService) -> None:
    candidate = make_candidate(
        "AAPL", screening_score=80.0, planning_score=60.0, research_score=90.0, portfolio_score=50.0,
        signal_score=70.0, alert_score=40.0,
    )

    explanation = service.explain_recommendation(candidate)

    categories = {c.category for c in explanation.contributing_components}
    assert categories == {
        AttributionCategory.SCREENING, AttributionCategory.PLANNING, AttributionCategory.RESEARCH,
        AttributionCategory.PORTFOLIO_INTELLIGENCE, AttributionCategory.SIGNALS, AttributionCategory.ALERTS,
    }


def test_explain_recommendation_omits_absent_components(service: ExplainabilityService) -> None:
    candidate = make_candidate("AAPL", screening_score=80.0, planning_score=None, research_score=None)

    explanation = service.explain_recommendation(candidate)

    categories = {c.category for c in explanation.contributing_components}
    assert AttributionCategory.SCREENING in categories
    assert AttributionCategory.PLANNING not in categories
    assert AttributionCategory.RESEARCH not in categories


def test_explain_recommendation_contribution_percents_sum_to_configured_total(
    service: ExplainabilityService,
) -> None:
    candidate = make_candidate("AAPL", screening_score=80.0, planning_score=60.0, research_score=90.0)

    explanation = service.explain_recommendation(candidate)

    assert sum(c.contribution_percent for c in explanation.contributing_components) == 100.0


def test_explain_recommendation_top_positive_factors_are_highest_scoring(
    service: ExplainabilityService,
) -> None:
    candidate = make_candidate(
        "AAPL", screening_score=95.0, planning_score=10.0, research_score=80.0, portfolio_score=5.0,
    )

    explanation = service.explain_recommendation(candidate)

    positive_categories = [c.category for c in explanation.top_positive_factors]
    assert positive_categories[0] == AttributionCategory.SCREENING


def test_explain_recommendation_top_negative_factors_are_lowest_scoring(
    service: ExplainabilityService,
) -> None:
    candidate = make_candidate(
        "AAPL", screening_score=95.0, planning_score=10.0, research_score=80.0, portfolio_score=5.0,
    )

    explanation = service.explain_recommendation(candidate)

    negative_categories = [c.category for c in explanation.top_negative_factors]
    assert negative_categories[0] == AttributionCategory.PORTFOLIO_INTELLIGENCE


def test_explain_recommendation_with_no_components_produces_empty_breakdown(
    service: ExplainabilityService,
) -> None:
    candidate = make_candidate(
        "AAPL", screening_score=None, planning_score=None, research_score=None, portfolio_score=None,
        signal_score=None, alert_score=None,
    )

    explanation = service.explain_recommendation(candidate)

    assert explanation.contributing_components == ()
    assert explanation.top_positive_factors == ()
    assert explanation.top_negative_factors == ()


def test_explain_recommendation_reuses_reasoning_verbatim(service: ExplainabilityService) -> None:
    candidate = make_candidate("AAPL", reasoning="Strong fundamentals and momentum.")

    explanation = service.explain_recommendation(candidate)

    assert explanation.reasoning == "Strong fundamentals and momentum."


def test_explain_recommendation_carries_ticker_and_scores_through(service: ExplainabilityService) -> None:
    candidate = make_candidate("AAPL", overall_score=88.0, confidence=91.0)

    explanation = service.explain_recommendation(candidate)

    assert explanation.ticker == "AAPL"
    assert explanation.overall_score == 88.0
    assert explanation.confidence == 91.0


# --- explain_strategy -----------------------------------------------------------


def test_explain_strategy_carries_alignment_score_and_rules_through(service: ExplainabilityService) -> None:
    matched = make_rule_alignment("r1", weight=2.0, pass_rate=1.0)
    failed = make_rule_alignment("r2", weight=1.0, pass_rate=0.0)
    match = make_strategy_match("s1", "Value", 75.0, matched_rules=(matched,), failed_rules=(failed,))

    explanation = service.explain_strategy(match)

    assert explanation.strategy_name == "Value"
    assert explanation.alignment_score == 75.0
    assert explanation.matched_rules == (matched,)
    assert explanation.failed_rules == (failed,)


def test_explain_strategy_weight_breakdown_reflects_rule_weights(service: ExplainabilityService) -> None:
    matched = make_rule_alignment("r1", weight=3.0, pass_rate=1.0)
    failed = make_rule_alignment("r2", weight=1.0, pass_rate=0.0)
    match = make_strategy_match(matched_rules=(matched,), failed_rules=(failed,))

    explanation = service.explain_strategy(match)

    assert len(explanation.weight_breakdown) == 2
    heaviest = explanation.weight_breakdown[0]
    assert heaviest.contribution_percent == 75.0  # 3 / (3+1) * 100
    assert all(entry.category == AttributionCategory.STRATEGY for entry in explanation.weight_breakdown)


def test_explain_strategy_with_no_rules_produces_empty_weight_breakdown(service: ExplainabilityService) -> None:
    match = make_strategy_match(matched_rules=(), failed_rules=())

    explanation = service.explain_strategy(match)

    assert explanation.weight_breakdown == ()


# --- explain_risk -----------------------------------------------------------


def test_explain_risk_carries_overall_score_through(service: ExplainabilityService) -> None:
    assessment = make_risk_assessment("risk-1", overall_risk_score=45.0)

    explanation = service.explain_risk(assessment)

    assert explanation.overall_risk_score == 45.0


def test_explain_risk_category_breakdown_is_ranked_by_score_descending(service: ExplainabilityService) -> None:
    low = make_risk_metric("Low Metric", RiskCategory.LIQUIDITY, score=10.0, severity=RiskSeverity.LOW)
    high = make_risk_metric("High Metric", RiskCategory.CONCENTRATION, score=90.0, severity=RiskSeverity.CRITICAL)
    assessment = make_risk_assessment("risk-1", risk_metrics=(low, high))

    explanation = service.explain_risk(assessment)

    assert explanation.category_breakdown[0].metric_name == "High Metric"
    assert explanation.category_breakdown[1].metric_name == "Low Metric"


def test_explain_risk_category_breakdown_is_copied_verbatim_never_recalculated(
    service: ExplainabilityService,
) -> None:
    metric = make_risk_metric("X", RiskCategory.VOLATILITY, score=33.0, severity=RiskSeverity.MODERATE)
    assessment = make_risk_assessment("risk-1", risk_metrics=(metric,))

    explanation = service.explain_risk(assessment)

    assert explanation.category_breakdown == (metric,)


def test_explain_risk_severity_breakdown_counts_by_severity(service: ExplainabilityService) -> None:
    metrics = (
        make_risk_metric("A", severity=RiskSeverity.LOW),
        make_risk_metric("B", severity=RiskSeverity.LOW),
        make_risk_metric("C", severity=RiskSeverity.HIGH),
    )
    assessment = make_risk_assessment("risk-1", risk_metrics=metrics)

    explanation = service.explain_risk(assessment)

    assert explanation.severity_breakdown[RiskSeverity.LOW] == 2
    assert explanation.severity_breakdown[RiskSeverity.HIGH] == 1


def test_explain_risk_exposure_breakdown_is_copied_verbatim(service: ExplainabilityService) -> None:
    exposure = PortfolioExposure(sector="Tech", weight=0.5, holding_count=2)
    assessment = make_risk_assessment("risk-1", exposures=(exposure,))

    explanation = service.explain_risk(assessment)

    assert explanation.exposure_breakdown == (exposure,)


def test_explain_risk_with_no_metrics_produces_empty_breakdowns(service: ExplainabilityService) -> None:
    assessment = make_risk_assessment("risk-1")

    explanation = service.explain_risk(assessment)

    assert explanation.category_breakdown == ()
    assert explanation.severity_breakdown == {}
    assert explanation.exposure_breakdown == ()
