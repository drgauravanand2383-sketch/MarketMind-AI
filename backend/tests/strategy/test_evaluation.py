"""Tests for StrategyEvaluationService.evaluate_strategy(): per-operator
population pass rates, weighted component scoring, alignment blending,
confidence (coverage) calculation, explainability, and edge cases.
Constructed directly against `StrategyEvaluationService.__new__` where no
repository is needed (`evaluate_strategy` is pure and synchronous) —
strategy management and multi-strategy ranking tests live in
`test_engine_strategies.py`.
"""

from __future__ import annotations

import pytest

from app.strategy.engine import StrategyEvaluationService
from app.strategy.models import StrategyOperator, StrategyWeighting
from tests.strategy.conftest import make_candidate, make_recommendation_result, make_rule, make_strategy


@pytest.fixture
def service() -> StrategyEvaluationService:
    return StrategyEvaluationService.__new__(StrategyEvaluationService)


# --- Each operator (population pass rate) -----------------------------------------------------------


def test_equals_operator_population_pass_rate(service: StrategyEvaluationService) -> None:
    rule = make_rule(field="ticker", operator=StrategyOperator.EQUALS, value="AAPL")
    strategy = make_strategy(rules=(rule,))
    result = make_recommendation_result((make_candidate("AAPL"), make_candidate("MSFT")))

    match = service.evaluate_strategy(result, strategy)

    assert match.matched_rules[0].pass_rate == 0.5


def test_not_equals_operator_population_pass_rate(service: StrategyEvaluationService) -> None:
    rule = make_rule(field="ticker", operator=StrategyOperator.NOT_EQUALS, value="AAPL")
    strategy = make_strategy(rules=(rule,))
    result = make_recommendation_result((make_candidate("AAPL"), make_candidate("MSFT")))

    match = service.evaluate_strategy(result, strategy)
    rule_result = match.matched_rules[0] if match.matched_rules else match.failed_rules[0]

    assert rule_result.pass_rate == 0.5


def test_greater_than_operator(service: StrategyEvaluationService) -> None:
    rule = make_rule(operator=StrategyOperator.GREATER_THAN, value=50)
    strategy = make_strategy(rules=(rule,))
    result = make_recommendation_result((make_candidate("A", overall_score=60), make_candidate("B", overall_score=40)))

    match = service.evaluate_strategy(result, strategy)

    assert (match.matched_rules + match.failed_rules)[0].pass_rate == 0.5


def test_between_operator(service: StrategyEvaluationService) -> None:
    rule = make_rule(operator=StrategyOperator.BETWEEN, value=[40, 60])
    strategy = make_strategy(rules=(rule,))
    result = make_recommendation_result(
        (make_candidate("A", overall_score=50), make_candidate("B", overall_score=90))
    )

    match = service.evaluate_strategy(result, strategy)

    assert (match.matched_rules + match.failed_rules)[0].pass_rate == 0.5


def test_in_operator(service: StrategyEvaluationService) -> None:
    rule = make_rule(field="sector", operator=StrategyOperator.IN, value=["Technology", "Energy"])
    strategy = make_strategy(rules=(rule,))
    result = make_recommendation_result(
        (make_candidate("A", sector="Technology"), make_candidate("B", sector="Healthcare"))
    )

    match = service.evaluate_strategy(result, strategy)

    assert (match.matched_rules + match.failed_rules)[0].pass_rate == 0.5


def test_not_in_operator(service: StrategyEvaluationService) -> None:
    rule = make_rule(field="sector", operator=StrategyOperator.NOT_IN, value=["Technology"])
    strategy = make_strategy(rules=(rule,))
    result = make_recommendation_result(
        (make_candidate("A", sector="Technology"), make_candidate("B", sector="Healthcare"))
    )

    match = service.evaluate_strategy(result, strategy)

    assert (match.matched_rules + match.failed_rules)[0].pass_rate == 0.5


def test_all_candidates_pass_gives_pass_rate_one(service: StrategyEvaluationService) -> None:
    rule = make_rule(operator=StrategyOperator.GREATER_THAN, value=10)
    strategy = make_strategy(rules=(rule,))
    result = make_recommendation_result((make_candidate("A", overall_score=50), make_candidate("B", overall_score=60)))

    match = service.evaluate_strategy(result, strategy)

    assert match.matched_rules[0].pass_rate == 1.0


def test_no_candidates_pass_gives_pass_rate_zero(service: StrategyEvaluationService) -> None:
    rule = make_rule(operator=StrategyOperator.GREATER_THAN, value=1000)
    strategy = make_strategy(rules=(rule,))
    result = make_recommendation_result((make_candidate("A", overall_score=50),))

    match = service.evaluate_strategy(result, strategy)

    assert match.failed_rules[0].pass_rate == 0.0


# --- Missing field handling -----------------------------------------------------------


def test_field_missing_on_a_candidate_excludes_it_from_the_rule_denominator(
    service: StrategyEvaluationService,
) -> None:
    rule = make_rule(field="screening_score", operator=StrategyOperator.GREATER_THAN, value=50)
    strategy = make_strategy(rules=(rule,))
    result = make_recommendation_result(
        (make_candidate("A", screening_score=80), make_candidate("B", screening_score=None))
    )

    match = service.evaluate_strategy(result, strategy)
    rule_result = (match.matched_rules + match.failed_rules)[0]

    assert rule_result.evaluated_candidate_count == 1  # only A had the field
    assert rule_result.pass_rate == 1.0


def test_field_missing_on_every_candidate_yields_zero_pass_rate(service: StrategyEvaluationService) -> None:
    rule = make_rule(field="screening_score", operator=StrategyOperator.GREATER_THAN, value=50)
    strategy = make_strategy(rules=(rule,))
    result = make_recommendation_result((make_candidate("A", screening_score=None),))

    match = service.evaluate_strategy(result, strategy)

    assert match.failed_rules[0].pass_rate == 0.0
    assert match.failed_rules[0].evaluated_candidate_count == 0


# --- Disabled rules -----------------------------------------------------------


def test_disabled_rule_is_ignored_entirely(service: StrategyEvaluationService) -> None:
    strategy = make_strategy(
        rules=(
            make_rule("r1", operator=StrategyOperator.GREATER_THAN, value=999, enabled=False),
            make_rule("r2", field="screening_score", operator=StrategyOperator.GREATER_THAN, value=1),
        )
    )
    result = make_recommendation_result((make_candidate("A", overall_score=50, screening_score=90),))

    match = service.evaluate_strategy(result, strategy)

    assert len(match.matched_rules) + len(match.failed_rules) == 1  # only r2 evaluated


def test_strategy_with_no_rules_uses_component_score_only(service: StrategyEvaluationService) -> None:
    strategy = make_strategy(rules=())
    result = make_recommendation_result((make_candidate("A", overall_score=80),))

    match = service.evaluate_strategy(result, strategy)

    assert match.alignment_score == 80.0  # equals the component score alone
    assert match.matched_rules == ()
    assert match.failed_rules == ()


# --- Weighted component scoring -----------------------------------------------------------


def test_component_score_uses_only_overall_score_when_others_absent(
    service: StrategyEvaluationService,
) -> None:
    strategy = make_strategy(rules=())
    result = make_recommendation_result((make_candidate("A", overall_score=70),))

    match = service.evaluate_strategy(result, strategy)

    assert match.alignment_score == 70.0


def test_component_score_blends_available_fields(service: StrategyEvaluationService) -> None:
    strategy = make_strategy(rules=(), weightings=StrategyWeighting())
    result = make_recommendation_result(
        (make_candidate("A", overall_score=100, screening_score=0),)
    )

    match = service.evaluate_strategy(result, strategy)

    assert match.alignment_score == 50.0  # equal weights, (100+0)/2


def test_custom_weighting_changes_component_score() -> None:
    instance = StrategyEvaluationService.__new__(StrategyEvaluationService)
    strategy = make_strategy(
        rules=(),
        weightings=StrategyWeighting(
            overall_score=9.0,
            screening_score=1.0,
            planning_score=1.0,
            research_score=1.0,
            portfolio_score=1.0,
            signal_score=1.0,
            alert_score=1.0,
        ),
    )
    result = make_recommendation_result((make_candidate("A", overall_score=100, screening_score=0),))

    match = instance.evaluate_strategy(result, strategy)

    assert match.alignment_score == 90.0  # (9*100 + 1*0) / 10


def test_component_score_averaged_across_population(service: StrategyEvaluationService) -> None:
    strategy = make_strategy(rules=())
    result = make_recommendation_result(
        (make_candidate("A", overall_score=100), make_candidate("B", overall_score=0))
    )

    match = service.evaluate_strategy(result, strategy)

    assert match.alignment_score == 50.0


# --- Blending component score with rule score -----------------------------------------------------------


def test_alignment_blends_component_and_rule_scores_equally(service: StrategyEvaluationService) -> None:
    # always fails -> rule_score 0
    strategy = make_strategy(rules=(make_rule(operator=StrategyOperator.GREATER_THAN, value=1000),))
    result = make_recommendation_result((make_candidate("A", overall_score=100),))  # component_score=100

    match = service.evaluate_strategy(result, strategy)

    assert match.alignment_score == 50.0  # (100 + 0) / 2


def test_alignment_with_empty_recommendation_result(service: StrategyEvaluationService) -> None:
    strategy = make_strategy(rules=(make_rule(),))
    result = make_recommendation_result(())

    match = service.evaluate_strategy(result, strategy)

    assert match.alignment_score == 0.0
    assert match.confidence == 0.0


# --- Confidence (coverage) calculation -----------------------------------------------------------


def test_confidence_reflects_data_coverage_not_score_quality(service: StrategyEvaluationService) -> None:
    """A candidate with only overall_score present has lower confidence
    than one with every field present, even at an identical score."""
    strategy = make_strategy(rules=())
    sparse = make_recommendation_result((make_candidate("A", overall_score=50),))
    rich = make_recommendation_result(
        (
            make_candidate(
                "A", overall_score=50, screening_score=50, planning_score=50, research_score=50,
                portfolio_score=50, signal_score=50, alert_score=50,
            ),
        )
    )

    sparse_match = service.evaluate_strategy(sparse, strategy)
    rich_match = service.evaluate_strategy(rich, strategy)

    assert sparse_match.alignment_score == rich_match.alignment_score == 50.0
    assert sparse_match.confidence < rich_match.confidence


def test_confidence_is_zero_with_no_candidates_and_no_rules(service: StrategyEvaluationService) -> None:
    strategy = make_strategy(rules=())
    result = make_recommendation_result(())

    match = service.evaluate_strategy(result, strategy)

    assert match.confidence == 0.0


# --- Explainability -----------------------------------------------------------


def test_reasoning_mentions_alignment_and_confidence(service: StrategyEvaluationService) -> None:
    strategy = make_strategy(rules=())
    result = make_recommendation_result((make_candidate("A", overall_score=80),))

    match = service.evaluate_strategy(result, strategy)

    assert "Alignment" in match.reasoning
    assert str(match.alignment_score) in match.reasoning
    assert str(match.confidence) in match.reasoning


def test_rule_alignment_reason_names_the_field_and_operator(service: StrategyEvaluationService) -> None:
    rule = make_rule(field="overall_score", operator=StrategyOperator.GREATER_THAN, value=50)
    strategy = make_strategy(rules=(rule,))
    result = make_recommendation_result((make_candidate("A", overall_score=80),))

    match = service.evaluate_strategy(result, strategy)
    rule_result = match.matched_rules[0]

    assert "overall_score" in rule_result.reason
    assert "GREATER_THAN" in rule_result.reason


def test_match_carries_strategy_identity(service: StrategyEvaluationService) -> None:
    strategy = make_strategy(strategy_id="s1", name="My Strategy", rules=())
    result = make_recommendation_result((make_candidate("A"),))

    match = service.evaluate_strategy(result, strategy)

    assert match.strategy_id == "s1"
    assert match.strategy_name == "My Strategy"


# --- Deterministic outputs -----------------------------------------------------------


def test_evaluation_is_deterministic_for_identical_inputs(service: StrategyEvaluationService) -> None:
    strategy = make_strategy(rules=(make_rule(operator=StrategyOperator.GREATER_THAN, value=50),))
    result = make_recommendation_result(
        (make_candidate("A", overall_score=60), make_candidate("B", overall_score=30))
    )

    first = service.evaluate_strategy(result, strategy)
    second = service.evaluate_strategy(result, strategy)

    assert first.alignment_score == second.alignment_score
    assert first.confidence == second.confidence
    assert first.matched_rules == second.matched_rules
    assert first.failed_rules == second.failed_rules


# --- Edge cases / large strategy sets -----------------------------------------------------------


def test_large_candidate_population(service: StrategyEvaluationService) -> None:
    strategy = make_strategy(rules=(make_rule(operator=StrategyOperator.GREATER_THAN, value=50),))
    candidates = tuple(make_candidate(f"T{i}", overall_score=(i % 101)) for i in range(1000))
    result = make_recommendation_result(candidates)

    match = service.evaluate_strategy(result, strategy)

    expected_pass = sum(1 for i in range(1000) if (i % 101) > 50)
    rule_result = (match.matched_rules + match.failed_rules)[0]
    assert rule_result.evaluated_candidate_count == 1000
    assert rule_result.pass_rate == round(expected_pass / 1000, 4)


def test_large_rule_set(service: StrategyEvaluationService) -> None:
    rules = tuple(make_rule(f"r{i}", operator=StrategyOperator.GREATER_THAN, value=10) for i in range(100))
    strategy = make_strategy(rules=rules)
    result = make_recommendation_result((make_candidate("A", overall_score=50),))

    match = service.evaluate_strategy(result, strategy)

    assert len(match.matched_rules) == 100
