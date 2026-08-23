"""Tests for the Strategy Evaluation Engine's domain models:
StrategyWeighting (positive weights), StrategyRule (per-operator value
validation, field validation), InvestmentStrategy's structural validation,
and the result/summary models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.strategy.models import (
    StrategyEvaluationRequest,
    StrategyEvaluationResult,
    StrategyMatch,
    StrategyOperator,
    StrategyRule,
    StrategySummary,
    StrategyType,
    StrategyWeighting,
)
from tests.strategy.conftest import NOW, make_rule, make_strategy

# --- StrategyWeighting -----------------------------------------------------------


def test_strategy_weighting_defaults_are_all_positive() -> None:
    weighting = StrategyWeighting()
    assert weighting.overall_score > 0
    assert weighting.screening_score > 0
    assert weighting.planning_score > 0
    assert weighting.research_score > 0
    assert weighting.portfolio_score > 0
    assert weighting.signal_score > 0
    assert weighting.alert_score > 0


@pytest.mark.parametrize(
    "field",
    ["overall_score", "screening_score", "planning_score", "research_score", "portfolio_score", "signal_score", "alert_score"],
)
def test_strategy_weighting_rejects_zero(field: str) -> None:
    with pytest.raises(ValidationError):
        StrategyWeighting(**{field: 0})


@pytest.mark.parametrize(
    "field",
    ["overall_score", "screening_score", "planning_score", "research_score", "portfolio_score", "signal_score", "alert_score"],
)
def test_strategy_weighting_rejects_negative(field: str) -> None:
    with pytest.raises(ValidationError):
        StrategyWeighting(**{field: -1})


def test_strategy_weighting_is_frozen() -> None:
    weighting = StrategyWeighting()
    with pytest.raises(ValidationError):
        weighting.overall_score = 5.0


# --- StrategyRule: operator/value validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "operator,value",
    [
        (StrategyOperator.EQUALS, "Technology"),
        (StrategyOperator.NOT_EQUALS, "Technology"),
        (StrategyOperator.GREATER_THAN, 10),
        (StrategyOperator.GREATER_EQUAL, 10),
        (StrategyOperator.LESS_THAN, 10),
        (StrategyOperator.LESS_EQUAL, 10),
        (StrategyOperator.BETWEEN, [5, 10]),
        (StrategyOperator.IN, ["US", "Canada"]),
        (StrategyOperator.NOT_IN, ["US", "Canada"]),
    ],
)
def test_strategy_rule_accepts_valid_value_for_each_operator(operator, value) -> None:  # noqa: ANN001
    rule = StrategyRule(id="r1", field="overall_score", operator=operator, value=value)
    assert rule.operator == operator


def test_strategy_rule_rejects_unknown_operator() -> None:
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="overall_score", operator="TOTALLY_MADE_UP", value=1)


def test_strategy_rule_rejects_missing_value_for_scalar_operator() -> None:
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="overall_score", operator=StrategyOperator.GREATER_THAN, value=None)


def test_strategy_rule_between_requires_two_element_list() -> None:
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="overall_score", operator=StrategyOperator.BETWEEN, value=[5])


def test_strategy_rule_between_rejects_low_greater_than_high() -> None:
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="overall_score", operator=StrategyOperator.BETWEEN, value=[20, 5])


def test_strategy_rule_in_rejects_empty_list() -> None:
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="sector", operator=StrategyOperator.IN, value=[])


def test_strategy_rule_not_in_rejects_empty_list() -> None:
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="sector", operator=StrategyOperator.NOT_IN, value=[])


def test_strategy_rule_in_rejects_non_list_value() -> None:
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="sector", operator=StrategyOperator.IN, value="Technology")


# --- StrategyRule: field validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "ticker", "company_name", "country", "sector", "industry", "overall_score", "confidence",
        "recommendation", "reasoning", "screening_score", "planning_score", "research_score",
        "portfolio_score", "signal_score", "alert_score", "created_at",
    ],
)
def test_strategy_rule_accepts_every_valid_recommendation_candidate_field(field: str) -> None:
    rule = StrategyRule(id="r1", field=field, operator=StrategyOperator.EQUALS, value="x")
    assert rule.field == field


def test_strategy_rule_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="not_a_real_field", operator=StrategyOperator.EQUALS, value=1)


def test_strategy_rule_rejects_tuple_typed_candidate_fields() -> None:
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="supporting_signals", operator=StrategyOperator.EQUALS, value=1)
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="supporting_alerts", operator=StrategyOperator.EQUALS, value=1)


def test_strategy_rule_rejects_nested_market_snapshot_field() -> None:
    """Milestone 14: market_snapshot is a nested object, not comparable by
    a single operator/value pair — excluded exactly like the tuple-typed
    fields above."""
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="market_snapshot", operator=StrategyOperator.EQUALS, value=1)


@pytest.mark.parametrize("field", ["market_price", "market_change_percent", "market_freshness", "market_contribution"])
def test_strategy_rule_accepts_market_scalar_fields(field: str) -> None:
    """Milestone 14's flat scalar fields on RecommendationCandidate are
    usable in strategy rules with zero engine changes, exactly like every
    pre-existing scalar field."""
    rule = StrategyRule(id="r1", field=field, operator=StrategyOperator.EQUALS, value="x")
    assert rule.field == field


def test_strategy_rule_rejects_blank_field() -> None:
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="", operator=StrategyOperator.EQUALS, value=1)


# --- StrategyRule: weight validation -----------------------------------------------------------


def test_strategy_rule_requires_positive_weight() -> None:
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="overall_score", operator=StrategyOperator.GREATER_THAN, value=1, weight=0)
    with pytest.raises(ValidationError):
        StrategyRule(id="r1", field="overall_score", operator=StrategyOperator.GREATER_THAN, value=1, weight=-1)


def test_strategy_rule_weight_defaults_to_one() -> None:
    assert make_rule().weight == 1.0


def test_strategy_rule_is_frozen() -> None:
    rule = make_rule()
    with pytest.raises(ValidationError):
        rule.value = 999


def test_strategy_rule_defaults_to_enabled() -> None:
    assert make_rule().enabled is True


def test_strategy_rule_requires_non_empty_id() -> None:
    with pytest.raises(ValidationError):
        StrategyRule(id="", field="overall_score", operator=StrategyOperator.GREATER_THAN, value=1)


# --- InvestmentStrategy -----------------------------------------------------------


def test_investment_strategy_requires_non_empty_name() -> None:
    with pytest.raises(ValidationError):
        make_strategy(name="")


def test_investment_strategy_rejects_duplicate_rule_id() -> None:
    with pytest.raises(ValidationError):
        make_strategy(rules=(make_rule("r1"), make_rule("r1")))


def test_investment_strategy_accepts_unique_rule_ids() -> None:
    strategy = make_strategy(rules=(make_rule("r1"), make_rule("r2")))
    assert len(strategy.rules) == 2


def test_investment_strategy_defaults() -> None:
    strategy = make_strategy()
    assert strategy.enabled is True
    assert strategy.strategy_type == StrategyType.CUSTOM
    assert strategy.rules == ()
    assert strategy.weightings == StrategyWeighting()


def test_investment_strategy_is_frozen() -> None:
    strategy = make_strategy()
    with pytest.raises(ValidationError):
        strategy.name = "Changed"


def test_investment_strategy_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        make_strategy(strategy_type="NOT_A_TYPE")


@pytest.mark.parametrize("strategy_type", list(StrategyType))
def test_investment_strategy_accepts_every_type(strategy_type: StrategyType) -> None:
    strategy = make_strategy(strategy_type=strategy_type)
    assert strategy.strategy_type == strategy_type


# --- StrategyEvaluationRequest -----------------------------------------------------------


def test_strategy_evaluation_request_requires_recommendation_result_id() -> None:
    with pytest.raises(ValidationError):
        StrategyEvaluationRequest(id="req-1", recommendation_result_id="", created_at=NOW)


def test_strategy_evaluation_request_defaults() -> None:
    request = StrategyEvaluationRequest(id="req-1", recommendation_result_id="rec-1", created_at=NOW)
    assert request.strategy_ids == ()


# --- StrategyMatch / StrategySummary / StrategyEvaluationResult -----------------------------------------------------------


def test_strategy_match_alignment_and_confidence_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        StrategyMatch(strategy_id="s1", strategy_name="X", alignment_score=101, confidence=50, reasoning="x")
    with pytest.raises(ValidationError):
        StrategyMatch(strategy_id="s1", strategy_name="X", alignment_score=50, confidence=-1, reasoning="x")


def test_strategy_summary_defaults_to_zero() -> None:
    summary = StrategySummary()
    assert summary.total_strategies == 0
    assert summary.best_alignment == 0.0


def test_strategy_evaluation_result_overall_alignment_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        StrategyEvaluationResult(
            request_id="req-1", evaluated_at=NOW, overall_alignment=150, summary=StrategySummary()
        )


def test_strategy_evaluation_result_construction() -> None:
    result = StrategyEvaluationResult(
        request_id="req-1", evaluated_at=NOW, overall_alignment=50.0, summary=StrategySummary()
    )
    assert result.strategy_matches == ()
    assert result.best_strategy is None
