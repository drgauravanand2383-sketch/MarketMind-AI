"""Tests for SignalDetectionService's evaluation methods: per-operator
behavior, AND/OR/nested logic, disabled conditions, weighted scoring,
confidence, priority ordering, explainability, and edge cases. Constructed
directly against `SignalDetectionService.__new__` where no repository is
needed (evaluation is pure and synchronous) — definition-management tests
live in `test_engine_definitions.py`.
"""

from __future__ import annotations

import pytest

from app.market_data.models import CompanyProfile, FinancialRatios, MarketQuote
from app.signals.engine import SignalDetectionService
from app.signals.models import (
    MarketDataSnapshot,
    SignalCategory,
    SignalConditionGroup,
    SignalLogicType,
    SignalOperator,
    SignalPriority,
)
from tests.signals.conftest import NOW, make_condition, make_definition


@pytest.fixture
def engine() -> SignalDetectionService:
    return SignalDetectionService.__new__(SignalDetectionService)


def snapshot(**overrides: object) -> MarketDataSnapshot:
    defaults: dict[str, object] = {"ticker": "AAPL", "company_name": "Apple"}
    defaults.update(overrides)
    return MarketDataSnapshot(**defaults)


def ratios(**kwargs: object) -> FinancialRatios:
    return FinancialRatios(**kwargs)


def profile(**kwargs: object) -> CompanyProfile:
    defaults = {"ticker": "AAPL", "company_name": "Apple"}
    defaults.update(kwargs)
    return CompanyProfile(**defaults)


def quote(**kwargs: object) -> MarketQuote:
    defaults = {"ticker": "AAPL", "price": 100.0, "timestamp": NOW}
    defaults.update(kwargs)
    return MarketQuote(**defaults)


# --- Each operator -----------------------------------------------------------


def test_equals_operator_pass_and_fail(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(make_condition(field="profile.sector", operator=SignalOperator.EQUALS, value="Technology"),)
    )
    assert engine.evaluate_company(snapshot(profile=profile(sector="Technology")), definition).triggered is True
    assert engine.evaluate_company(snapshot(profile=profile(sector="Energy")), definition).triggered is False


def test_not_equals_operator_pass_and_fail(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(make_condition(field="profile.sector", operator=SignalOperator.NOT_EQUALS, value="Technology"),)
    )
    assert engine.evaluate_company(snapshot(profile=profile(sector="Energy")), definition).triggered is True
    assert engine.evaluate_company(snapshot(profile=profile(sector="Technology")), definition).triggered is False


def test_greater_than_operator_pass_and_fail(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(operator=SignalOperator.GREATER_THAN, value=10),))
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=11)), definition).triggered is True
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=10)), definition).triggered is False


def test_greater_equal_operator_pass_and_fail(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(operator=SignalOperator.GREATER_EQUAL, value=10),))
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=10)), definition).triggered is True
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=9)), definition).triggered is False


def test_less_than_operator_pass_and_fail(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(operator=SignalOperator.LESS_THAN, value=10),))
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=9)), definition).triggered is True
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=10)), definition).triggered is False


def test_less_equal_operator_pass_and_fail(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(operator=SignalOperator.LESS_EQUAL, value=10),))
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=10)), definition).triggered is True
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=11)), definition).triggered is False


def test_between_operator_pass_and_fail(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(operator=SignalOperator.BETWEEN, value=[10, 20]),))
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=15)), definition).triggered is True
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=9)), definition).triggered is False
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=21)), definition).triggered is False


def test_in_operator_pass_and_fail(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(make_condition(field="profile.country", operator=SignalOperator.IN, value=["US", "Canada"]),)
    )
    assert engine.evaluate_company(snapshot(profile=profile(country="US")), definition).triggered is True
    assert engine.evaluate_company(snapshot(profile=profile(country="Germany")), definition).triggered is False


def test_not_in_operator_pass_and_fail(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(make_condition(field="profile.country", operator=SignalOperator.NOT_IN, value=["US", "Canada"]),)
    )
    assert engine.evaluate_company(snapshot(profile=profile(country="Germany")), definition).triggered is True
    assert engine.evaluate_company(snapshot(profile=profile(country="US")), definition).triggered is False


def test_missing_source_model_fails_the_condition(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(),))
    result = engine.evaluate_company(snapshot(), definition)  # no ratios at all
    assert result.triggered is False
    assert "missing" in result.failed_conditions[0].reason


def test_missing_field_within_present_source_fails_the_condition(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(make_condition(field="ratios.roe", operator=SignalOperator.GREATER_THAN, value=0.1),)
    )
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=10)), definition)  # ratios present, roe absent
    assert result.triggered is False


# --- AND logic -----------------------------------------------------------


def test_top_level_and_requires_all_conditions_to_pass(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(
            make_condition("c1", operator=SignalOperator.LESS_THAN, value=20),
            make_condition("c2", field="ratios.roe", operator=SignalOperator.GREATER_THAN, value=0.15),
        )
    )
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=15, roe=0.2)), definition).triggered is True
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=15, roe=0.1)), definition).triggered is False
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=30, roe=0.2)), definition).triggered is False


def test_explicit_and_group(engine: SignalDetectionService) -> None:
    group = SignalConditionGroup(id="g1", logic=SignalLogicType.AND)
    definition = make_definition(
        conditions=(
            make_condition("c1", operator=SignalOperator.LESS_THAN, value=20, group="g1"),
            make_condition("c2", field="ratios.roe", operator=SignalOperator.GREATER_THAN, value=0.15, group="g1"),
        ),
        groups=(group,),
    )
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=15, roe=0.2)), definition).triggered is True
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=30, roe=0.2)), definition).triggered is False


# --- OR logic -----------------------------------------------------------


def test_or_group_passes_if_any_child_passes(engine: SignalDetectionService) -> None:
    group = SignalConditionGroup(id="g1", logic=SignalLogicType.OR)
    definition = make_definition(
        conditions=(
            make_condition(
                "c1", field="profile.sector", operator=SignalOperator.EQUALS, value="Technology", group="g1"
            ),
            make_condition("c2", field="profile.sector", operator=SignalOperator.EQUALS, value="Energy", group="g1"),
        ),
        groups=(group,),
    )
    assert engine.evaluate_company(snapshot(profile=profile(sector="Technology")), definition).triggered is True
    assert engine.evaluate_company(snapshot(profile=profile(sector="Energy")), definition).triggered is True
    assert engine.evaluate_company(snapshot(profile=profile(sector="Materials")), definition).triggered is False


# --- Nested evaluation -----------------------------------------------------------


def test_nested_group_three_levels(engine: SignalDetectionService) -> None:
    """Root AND: [quote.volume > 1000] AND (outer OR: [sector==Tech] OR (inner AND: [pe<20, roe>0.1]))."""
    outer = SignalConditionGroup(id="outer", logic=SignalLogicType.OR)
    inner = SignalConditionGroup(id="inner", logic=SignalLogicType.AND, parent_group="outer")
    definition = make_definition(
        conditions=(
            make_condition("vol", field="quote.volume", operator=SignalOperator.GREATER_THAN, value=1000),
            make_condition(
                "tech", field="profile.sector", operator=SignalOperator.EQUALS, value="Technology", group="outer"
            ),
            make_condition("pe", field="ratios.pe", operator=SignalOperator.LESS_THAN, value=20, group="inner"),
            make_condition("roe", field="ratios.roe", operator=SignalOperator.GREATER_THAN, value=0.1, group="inner"),
        ),
        groups=(outer, inner),
    )

    s1 = snapshot(quote=quote(volume=2000), profile=profile(sector="Technology"), ratios=ratios(pe=999, roe=0))
    assert engine.evaluate_company(s1, definition).triggered is True  # via tech branch

    s2 = snapshot(quote=quote(volume=2000), profile=profile(sector="Energy"), ratios=ratios(pe=10, roe=0.2))
    assert engine.evaluate_company(s2, definition).triggered is True  # via inner-AND branch

    s3 = snapshot(quote=quote(volume=2000), profile=profile(sector="Energy"), ratios=ratios(pe=10, roe=0.01))
    assert engine.evaluate_company(s3, definition).triggered is False  # inner AND fails, not tech

    s4 = snapshot(quote=quote(volume=500), profile=profile(sector="Technology"), ratios=ratios(pe=10, roe=0.5))
    assert engine.evaluate_company(s4, definition).triggered is False  # low volume always fails


def test_empty_group_and_is_vacuously_true(engine: SignalDetectionService) -> None:
    group = SignalConditionGroup(id="g1", logic=SignalLogicType.AND)
    definition = make_definition(conditions=(), groups=(group,))
    assert engine.evaluate_company(snapshot(), definition).triggered is True


def test_definition_with_no_conditions_triggers_vacuously(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(), groups=())
    result = engine.evaluate_company(snapshot(), definition)
    assert result.triggered is True
    assert result.score == 100.0


# --- Disabled conditions -----------------------------------------------------------


def test_disabled_condition_is_ignored_entirely(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(
            make_condition("c1", operator=SignalOperator.LESS_THAN, value=5, enabled=False),
            make_condition("c2", field="ratios.roe", operator=SignalOperator.GREATER_THAN, value=0.1),
        )
    )
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=999, roe=0.5)), definition)
    assert result.triggered is True


def test_disabled_condition_does_not_appear_in_matched_or_failed(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition("c1", enabled=False),))
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=999)), definition)
    assert result.matched_conditions == ()
    assert result.failed_conditions == ()


def test_all_conditions_disabled_triggers_vacuously(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition("c1", enabled=False), make_condition("c2", enabled=False)))
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=999)), definition)
    assert result.triggered is True
    assert result.score == 100.0


# --- Weighted scoring -----------------------------------------------------------


def test_score_is_plain_percentage_when_weights_are_equal(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(
            make_condition("c1", operator=SignalOperator.LESS_THAN, value=20),
            make_condition("c2", field="ratios.roe", operator=SignalOperator.GREATER_THAN, value=0.15),
            make_condition("c3", field="ratios.pb", operator=SignalOperator.LESS_THAN, value=10),
            make_condition("c4", field="ratios.current_ratio", operator=SignalOperator.GREATER_THAN, value=1),
        )
    )
    result = engine.evaluate_company(
        snapshot(ratios=ratios(pe=15, roe=0.2, pb=20, current_ratio=0.5)), definition
    )
    assert result.score == 50.0  # 2 of 4 matched, equal weight


def test_weighted_score_dominated_by_high_weight_condition(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(
            make_condition("c1", operator=SignalOperator.LESS_THAN, value=5, weight=3.0),  # will fail
            # will pass
            make_condition("c2", field="ratios.roe", operator=SignalOperator.GREATER_THAN, value=0.01, weight=1.0),
        )
    )
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=50, roe=0.5)), definition)
    assert result.score == 25.0  # 1 / (3+1) = 25%


def test_disabled_conditions_excluded_from_score_denominator(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(
            make_condition("c1", operator=SignalOperator.LESS_THAN, value=20),
            make_condition(
                "c2", field="ratios.roe", operator=SignalOperator.GREATER_THAN, value=0.99, enabled=False, weight=100.0
            ),
        )
    )
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=15, roe=0.0)), definition)
    assert result.score == 100.0


def test_score_can_be_high_even_when_not_triggered(engine: SignalDetectionService) -> None:
    group = SignalConditionGroup(id="g1", logic=SignalLogicType.AND)
    definition = make_definition(
        conditions=(
            make_condition("c1", operator=SignalOperator.LESS_THAN, value=20, group="g1"),
            make_condition("c2", field="ratios.roe", operator=SignalOperator.GREATER_THAN, value=0.15, group="g1"),
            make_condition("c3", field="ratios.pb", operator=SignalOperator.LESS_THAN, value=1.5, group="g1"),
            make_condition(
                "c4", field="ratios.current_ratio", operator=SignalOperator.GREATER_THAN, value=100, group="g1"
            ),
        ),
        groups=(group,),
    )
    result = engine.evaluate_company(
        snapshot(ratios=ratios(pe=15, roe=0.2, pb=1.0, current_ratio=1)), definition
    )
    assert result.triggered is False  # AND group fails on c4
    assert result.score == 75.0  # but 3 of 4 matched


# --- Confidence calculation -----------------------------------------------------------


def test_confidence_at_medium_priority_equals_score(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(make_condition(operator=SignalOperator.LESS_THAN, value=20),), priority=SignalPriority.MEDIUM
    )
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=15)), definition)
    assert result.confidence == result.score


def test_confidence_at_critical_priority_exceeds_score(engine: SignalDetectionService) -> None:
    conditions = (
        make_condition("c1", operator=SignalOperator.LESS_THAN, value=5, weight=3.0),
        make_condition("c2", field="ratios.roe", operator=SignalOperator.GREATER_THAN, value=0.01, weight=1.0),
    )
    medium = make_definition(conditions=conditions, priority=SignalPriority.MEDIUM)
    critical = medium.model_copy(update={"priority": SignalPriority.CRITICAL})

    snap = snapshot(ratios=ratios(pe=50, roe=0.5))
    medium_result = engine.evaluate_company(snap, medium)
    critical_result = engine.evaluate_company(snap, critical)

    assert medium_result.score == critical_result.score  # score unaffected by priority
    assert critical_result.confidence > medium_result.confidence


def test_confidence_at_low_priority_is_less_than_score(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(make_condition(operator=SignalOperator.LESS_THAN, value=20),), priority=SignalPriority.LOW
    )
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=15)), definition)
    assert result.confidence < result.score


def test_confidence_is_capped_at_100(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(make_condition(operator=SignalOperator.LESS_THAN, value=100),), priority=SignalPriority.CRITICAL
    )
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=1)), definition)
    assert result.score == 100.0
    assert result.confidence == 100.0


# --- Priority ordering -----------------------------------------------------------


def test_evaluate_definitions_orders_by_priority_critical_first(engine: SignalDetectionService) -> None:
    conditions = (make_condition(operator=SignalOperator.LESS_THAN, value=20),)
    low = make_definition("d1", "Low", conditions=conditions, priority=SignalPriority.LOW)
    critical = make_definition("d2", "Critical", conditions=conditions, priority=SignalPriority.CRITICAL)
    medium = make_definition("d3", "Medium", conditions=conditions, priority=SignalPriority.MEDIUM)
    high = make_definition("d4", "High", conditions=conditions, priority=SignalPriority.HIGH)

    batch = engine.evaluate_definitions(snapshot(ratios=ratios(pe=15)), [low, critical, medium, high])

    assert [r.priority for r in batch.signals] == [
        SignalPriority.CRITICAL, SignalPriority.HIGH, SignalPriority.MEDIUM, SignalPriority.LOW,
    ]


def test_evaluate_batch_orders_by_priority_regardless_of_input_order(engine: SignalDetectionService) -> None:
    conditions = (make_condition(operator=SignalOperator.LESS_THAN, value=20),)
    low = make_definition("d1", "Low", conditions=conditions, priority=SignalPriority.LOW)
    critical = make_definition("d2", "Critical", conditions=conditions, priority=SignalPriority.CRITICAL)

    batch = engine.evaluate_batch(
        [snapshot(ticker="A", ratios=ratios(pe=15)), snapshot(ticker="B", ratios=ratios(pe=15))],
        [low, critical],
    )

    assert batch.signals[0].priority == SignalPriority.CRITICAL
    assert batch.signals[-1].priority == SignalPriority.LOW


# --- Explainability -----------------------------------------------------------


def test_matched_conditions_carry_no_reason(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(operator=SignalOperator.LESS_THAN, value=20),))
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=15)), definition)
    assert result.matched_conditions[0].reason is None
    assert result.matched_conditions[0].passed is True


def test_failed_conditions_carry_a_specific_reason(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(operator=SignalOperator.LESS_THAN, value=20),))
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=30)), definition)
    assert result.failed_conditions[0].reason is not None
    assert "ratios.pe" in result.failed_conditions[0].reason


def test_reason_summarizes_triggered_result(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(operator=SignalOperator.LESS_THAN, value=20),))
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=15)), definition)
    assert "Triggered" in result.reason
    assert "1 of 1" in result.reason


def test_reason_summarizes_not_triggered_result(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(operator=SignalOperator.LESS_THAN, value=5),))
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=30)), definition)
    assert "Not triggered" in result.reason


def test_result_carries_ticker_company_name_signal_name_category(engine: SignalDetectionService) -> None:
    definition = make_definition(
        conditions=(make_condition(),), category=SignalCategory.VALUATION, name="P/E Screen"
    )
    result = engine.evaluate_company(
        snapshot(ticker="MSFT", company_name="Microsoft", ratios=ratios(pe=15)), definition
    )
    assert result.ticker == "MSFT"
    assert result.company_name == "Microsoft"
    assert result.signal_name == "P/E Screen"
    assert result.category == SignalCategory.VALUATION


# --- Batch evaluation (evaluate_companies / evaluate_definitions / evaluate_batch) ------------------


def test_evaluate_companies_returns_one_result_per_company(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(operator=SignalOperator.LESS_THAN, value=20),))
    snapshots = [snapshot(ticker="A", ratios=ratios(pe=10)), snapshot(ticker="B", ratios=ratios(pe=30))]
    batch = engine.evaluate_companies(snapshots, definition)
    assert batch.evaluated == 2
    assert batch.triggered == 1
    assert batch.average_score == 50.0


def test_evaluate_companies_with_empty_list(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(),))
    batch = engine.evaluate_companies([], definition)
    assert batch.evaluated == 0
    assert batch.average_score == 0.0
    assert batch.summary == "No signals evaluated."


def test_evaluate_batch_cross_product_count(engine: SignalDetectionService) -> None:
    conditions = (make_condition(operator=SignalOperator.LESS_THAN, value=20),)
    definitions = [make_definition("d1", "A", conditions=conditions), make_definition("d2", "B", conditions=conditions)]
    snapshots = [
        snapshot(ticker="X", ratios=ratios(pe=10)),
        snapshot(ticker="Y", ratios=ratios(pe=10)),
        snapshot(ticker="Z", ratios=ratios(pe=10)),
    ]
    batch = engine.evaluate_batch(snapshots, definitions)
    assert batch.evaluated == 6  # 2 definitions x 3 companies


# --- Edge cases / large evaluation batches -----------------------------------------------------------


def test_large_condition_set(engine: SignalDetectionService) -> None:
    conditions = tuple(
        make_condition(f"c{i}", operator=SignalOperator.LESS_THAN, value=100) for i in range(300)
    )
    definition = make_definition(conditions=conditions)
    result = engine.evaluate_company(snapshot(ratios=ratios(pe=10)), definition)
    assert result.triggered is True
    assert result.score == 100.0
    assert len(result.matched_conditions) == 300


def test_large_company_batch(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(operator=SignalOperator.LESS_THAN, value=20),))
    snapshots = [snapshot(ticker=f"T{i}", ratios=ratios(pe=(i % 40))) for i in range(1000)]
    batch = engine.evaluate_companies(snapshots, definition)
    assert batch.evaluated == 1000
    assert batch.triggered == sum(1 for i in range(1000) if (i % 40) < 20)


def test_deeply_nested_groups(engine: SignalDetectionService) -> None:
    groups = tuple(
        SignalConditionGroup(
            id=f"g{level}",
            logic=SignalLogicType.AND if level % 2 == 0 else SignalLogicType.OR,
            parent_group=f"g{level - 1}" if level > 0 else None,
        )
        for level in range(5)
    )
    leaf = make_condition(field="ratios.pe", operator=SignalOperator.LESS_THAN, value=20, group="g4")
    definition = make_definition(conditions=(leaf,), groups=groups)
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=10)), definition).triggered is True
    assert engine.evaluate_company(snapshot(ratios=ratios(pe=30)), definition).triggered is False


# --- Deterministic outputs -----------------------------------------------------------


def test_evaluation_is_deterministic_across_calls(engine: SignalDetectionService) -> None:
    definition = make_definition(conditions=(make_condition(operator=SignalOperator.LESS_THAN, value=20),))
    snap = snapshot(ratios=ratios(pe=15))
    first = engine.evaluate_company(snap, definition)
    second = engine.evaluate_company(snap, definition)
    assert first.triggered == second.triggered
    assert first.score == second.score
    assert first.confidence == second.confidence
    assert first.matched_conditions == second.matched_conditions
