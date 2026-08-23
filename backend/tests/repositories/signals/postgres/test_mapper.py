"""Tests for the Signal Definition Postgres mapper: purely structural round-trips."""

from __future__ import annotations

from datetime import UTC, datetime

from app.repositories.signals.postgres.mapper import definition_to_model, model_to_definition
from app.signals.models import (
    SignalCategory,
    SignalCondition,
    SignalConditionGroup,
    SignalDefinition,
    SignalLogicType,
    SignalOperator,
    SignalPriority,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)


def test_definition_with_conditions_and_groups_round_trips() -> None:
    group = SignalConditionGroup(id="g1", logic=SignalLogicType.OR)
    definition = SignalDefinition(
        id="d1",
        name="Value",
        description="Cheap companies",
        category=SignalCategory.VALUATION,
        priority=SignalPriority.HIGH,
        enabled=True,
        conditions=(
            SignalCondition(id="c1", field="ratios.pe", operator=SignalOperator.LESS_THAN, value=20, weight=2.0, group="g1"),
            SignalCondition(id="c2", field="profile.sector", operator=SignalOperator.IN, value=["Tech", "Energy"]),
        ),
        groups=(group,),
        created_at=NOW,
        updated_at=NOW,
    )

    model = definition_to_model(definition)
    restored = model_to_definition(model)

    assert restored == definition


def test_definition_with_no_conditions_or_groups_round_trips() -> None:
    definition = SignalDefinition(id="d1", name="Empty", created_at=NOW, updated_at=NOW)

    model = definition_to_model(definition)
    restored = model_to_definition(model)

    assert restored.conditions == ()
    assert restored.groups == ()


def test_between_operator_value_round_trips_as_a_list() -> None:
    definition = SignalDefinition(
        id="d1",
        name="Value",
        created_at=NOW,
        updated_at=NOW,
        conditions=(SignalCondition(id="c1", field="ratios.pe", operator=SignalOperator.BETWEEN, value=[10, 20]),),
    )

    model = definition_to_model(definition)
    restored = model_to_definition(model)

    assert restored.conditions[0].value == [10, 20]


def test_nested_group_hierarchy_round_trips() -> None:
    definition = SignalDefinition(
        id="d1",
        name="Nested",
        created_at=NOW,
        updated_at=NOW,
        groups=(
            SignalConditionGroup(id="outer", logic=SignalLogicType.OR),
            SignalConditionGroup(id="inner", logic=SignalLogicType.AND, parent_group="outer"),
        ),
    )

    model = definition_to_model(definition)
    restored = model_to_definition(model)

    assert restored.groups[1].parent_group == "outer"


def test_condition_weight_round_trips() -> None:
    definition = SignalDefinition(
        id="d1",
        name="Weighted",
        created_at=NOW,
        updated_at=NOW,
        conditions=(SignalCondition(id="c1", field="ratios.pe", operator=SignalOperator.LESS_THAN, value=20, weight=4.25),),
    )

    model = definition_to_model(definition)
    restored = model_to_definition(model)

    assert restored.conditions[0].weight == 4.25
