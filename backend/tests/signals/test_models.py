"""Tests for the Signal Detection Engine's domain models: SignalCondition
(per-operator value validation, dotted-path field validation, positive
weight), SignalConditionGroup, SignalDefinition's structural validation,
and MarketDataSnapshot."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.market_data.models import CompanyProfile, FinancialRatios, Fundamentals, MarketQuote
from app.signals.models import (
    MarketDataSnapshot,
    SignalCategory,
    SignalCondition,
    SignalConditionGroup,
    SignalLogicType,
    SignalOperator,
    SignalPriority,
)
from tests.signals.conftest import make_condition, make_definition

# --- SignalCondition: operator/value validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "operator,value",
    [
        (SignalOperator.EQUALS, "Technology"),
        (SignalOperator.NOT_EQUALS, "Technology"),
        (SignalOperator.GREATER_THAN, 10),
        (SignalOperator.GREATER_EQUAL, 10),
        (SignalOperator.LESS_THAN, 10),
        (SignalOperator.LESS_EQUAL, 10),
        (SignalOperator.BETWEEN, [5, 10]),
        (SignalOperator.IN, ["US", "Canada"]),
        (SignalOperator.NOT_IN, ["US", "Canada"]),
    ],
)
def test_signal_condition_accepts_valid_value_for_each_operator(operator, value) -> None:  # noqa: ANN001
    condition = SignalCondition(id="c1", field="ratios.pe", operator=operator, value=value)
    assert condition.operator == operator


def test_signal_condition_rejects_unknown_operator() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="ratios.pe", operator="TOTALLY_MADE_UP", value=1)


def test_signal_condition_rejects_missing_value_for_scalar_operator() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="ratios.pe", operator=SignalOperator.GREATER_THAN, value=None)


def test_signal_condition_between_requires_two_element_list() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="ratios.pe", operator=SignalOperator.BETWEEN, value=[5])


def test_signal_condition_between_rejects_low_greater_than_high() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="ratios.pe", operator=SignalOperator.BETWEEN, value=[20, 5])


def test_signal_condition_between_accepts_equal_bounds() -> None:
    condition = SignalCondition(id="c1", field="ratios.pe", operator=SignalOperator.BETWEEN, value=[10, 10])
    assert condition.value == [10, 10]


def test_signal_condition_in_rejects_empty_list() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="profile.sector", operator=SignalOperator.IN, value=[])


def test_signal_condition_not_in_rejects_empty_list() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="profile.sector", operator=SignalOperator.NOT_IN, value=[])


def test_signal_condition_in_rejects_non_list_value() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="profile.sector", operator=SignalOperator.IN, value="Technology")


# --- SignalCondition: dotted-path field validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["quote.price", "quote.volume", "profile.sector", "profile.market_cap", "fundamentals.revenue", "ratios.pe"],
)
def test_signal_condition_accepts_valid_dotted_field(field: str) -> None:
    condition = SignalCondition(id="c1", field=field, operator=SignalOperator.GREATER_THAN, value=1)
    assert condition.field == field


def test_signal_condition_rejects_unknown_namespace() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="not_a_namespace.pe", operator=SignalOperator.GREATER_THAN, value=1)


def test_signal_condition_rejects_unknown_field_in_known_namespace() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="ratios.not_a_real_field", operator=SignalOperator.GREATER_THAN, value=1)


def test_signal_condition_rejects_field_with_no_dot() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="pe", operator=SignalOperator.GREATER_THAN, value=1)


def test_signal_condition_rejects_blank_field() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="", operator=SignalOperator.GREATER_THAN, value=1)


# --- SignalCondition: weight validation -----------------------------------------------------------


def test_signal_condition_requires_positive_weight() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="ratios.pe", operator=SignalOperator.GREATER_THAN, value=1, weight=0)
    with pytest.raises(ValidationError):
        SignalCondition(id="c1", field="ratios.pe", operator=SignalOperator.GREATER_THAN, value=1, weight=-1)


def test_signal_condition_weight_defaults_to_one() -> None:
    condition = make_condition()
    assert condition.weight == 1.0


def test_signal_condition_is_frozen() -> None:
    condition = make_condition()
    with pytest.raises(ValidationError):
        condition.value = 999


def test_signal_condition_defaults_to_enabled() -> None:
    assert make_condition().enabled is True


def test_signal_condition_requires_non_empty_id() -> None:
    with pytest.raises(ValidationError):
        SignalCondition(id="", field="ratios.pe", operator=SignalOperator.GREATER_THAN, value=1)


# --- SignalConditionGroup -----------------------------------------------------------


def test_signal_condition_group_defaults_to_no_parent() -> None:
    group = SignalConditionGroup(id="g1", logic=SignalLogicType.AND)
    assert group.parent_group is None


def test_signal_condition_group_rejects_unknown_logic() -> None:
    with pytest.raises(ValidationError):
        SignalConditionGroup(id="g1", logic="XOR")


# --- SignalDefinition: structural validation -----------------------------------------------------------


def test_signal_definition_requires_non_empty_name() -> None:
    with pytest.raises(ValidationError):
        make_definition(name="")


def test_signal_definition_accepts_valid_conditions_and_groups() -> None:
    group = SignalConditionGroup(id="g1", logic=SignalLogicType.OR)
    definition = make_definition(
        conditions=(make_condition("c1", group="g1"), make_condition("c2", group="g1")), groups=(group,)
    )
    assert len(definition.conditions) == 2


def test_signal_definition_rejects_duplicate_condition_id() -> None:
    with pytest.raises(ValidationError):
        make_definition(conditions=(make_condition("c1"), make_condition("c1")))


def test_signal_definition_rejects_duplicate_group_id() -> None:
    with pytest.raises(ValidationError):
        make_definition(
            groups=(
                SignalConditionGroup(id="g1", logic=SignalLogicType.AND),
                SignalConditionGroup(id="g1", logic=SignalLogicType.OR),
            )
        )


def test_signal_definition_rejects_condition_referencing_unknown_group() -> None:
    with pytest.raises(ValidationError):
        make_definition(conditions=(make_condition("c1", group="does-not-exist"),))


def test_signal_definition_rejects_group_referencing_unknown_parent() -> None:
    with pytest.raises(ValidationError):
        make_definition(
            groups=(SignalConditionGroup(id="g1", logic=SignalLogicType.AND, parent_group="does-not-exist"),)
        )


def test_signal_definition_rejects_two_group_cycle() -> None:
    with pytest.raises(ValidationError):
        make_definition(
            groups=(
                SignalConditionGroup(id="g1", logic=SignalLogicType.AND, parent_group="g2"),
                SignalConditionGroup(id="g2", logic=SignalLogicType.OR, parent_group="g1"),
            )
        )


def test_signal_definition_rejects_self_referencing_group() -> None:
    with pytest.raises(ValidationError):
        make_definition(groups=(SignalConditionGroup(id="g1", logic=SignalLogicType.AND, parent_group="g1"),))


def test_signal_definition_accepts_valid_nested_groups() -> None:
    definition = make_definition(
        groups=(
            SignalConditionGroup(id="outer", logic=SignalLogicType.OR),
            SignalConditionGroup(id="inner", logic=SignalLogicType.AND, parent_group="outer"),
        )
    )
    assert len(definition.groups) == 2


def test_signal_definition_defaults() -> None:
    definition = make_definition()
    assert definition.conditions == ()
    assert definition.groups == ()
    assert definition.enabled is True
    assert definition.category == SignalCategory.CUSTOM
    assert definition.priority == SignalPriority.MEDIUM


def test_signal_definition_is_frozen() -> None:
    definition = make_definition()
    with pytest.raises(ValidationError):
        definition.name = "Changed"


def test_signal_definition_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        make_definition(category="NOT_A_CATEGORY")


def test_signal_definition_rejects_unknown_priority() -> None:
    with pytest.raises(ValidationError):
        make_definition(priority="NOT_A_PRIORITY")


@pytest.mark.parametrize("category", list(SignalCategory))
def test_signal_definition_accepts_every_category(category: SignalCategory) -> None:
    definition = make_definition(category=category)
    assert definition.category == category


@pytest.mark.parametrize("priority", list(SignalPriority))
def test_signal_definition_accepts_every_priority(priority: SignalPriority) -> None:
    definition = make_definition(priority=priority)
    assert definition.priority == priority


# --- MarketDataSnapshot -----------------------------------------------------------


def test_market_data_snapshot_requires_ticker() -> None:
    with pytest.raises(ValidationError):
        MarketDataSnapshot(ticker="")


def test_market_data_snapshot_all_sources_optional() -> None:
    snapshot = MarketDataSnapshot(ticker="AAPL")
    assert snapshot.quote is None
    assert snapshot.profile is None
    assert snapshot.fundamentals is None
    assert snapshot.ratios is None


def test_market_data_snapshot_accepts_full_bundle() -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    snapshot = MarketDataSnapshot(
        ticker="AAPL",
        company_name="Apple",
        quote=MarketQuote(ticker="AAPL", price=100, timestamp=now),
        profile=CompanyProfile(ticker="AAPL", company_name="Apple"),
        fundamentals=Fundamentals(revenue=1e9),
        ratios=FinancialRatios(pe=25),
    )
    assert snapshot.quote is not None
    assert snapshot.ratios is not None
