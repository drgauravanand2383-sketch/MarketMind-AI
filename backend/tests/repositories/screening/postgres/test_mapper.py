"""Tests for the Screening Postgres mapper: purely structural round-trips."""

from __future__ import annotations

from datetime import datetime, timezone

from app.repositories.screening.postgres.mapper import model_to_profile, profile_to_model
from app.screening.models import LogicalGroup, LogicType, ScreenFilter, ScreeningProfile, ScreenOperator

NOW = datetime(2026, 8, 6, tzinfo=timezone.utc)


def test_profile_with_filters_and_groups_round_trips() -> None:
    group = LogicalGroup(id="g1", logic=LogicType.OR)
    profile = ScreeningProfile(
        id="p1",
        name="Value",
        description="Cheap companies",
        created_at=NOW,
        updated_at=NOW,
        is_default=True,
        filters=(
            ScreenFilter(id="f1", field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20, group="g1"),
            ScreenFilter(id="f2", field="sector", operator=ScreenOperator.IN, value=["Tech", "Energy"]),
        ),
        groups=(group,),
    )

    model = profile_to_model(profile)
    restored = model_to_profile(model)

    assert restored == profile


def test_profile_with_no_filters_or_groups_round_trips() -> None:
    profile = ScreeningProfile(id="p1", name="Empty", created_at=NOW, updated_at=NOW)

    model = profile_to_model(profile)
    restored = model_to_profile(model)

    assert restored.filters == ()
    assert restored.groups == ()


def test_between_operator_value_round_trips_as_a_list() -> None:
    profile = ScreeningProfile(
        id="p1",
        name="Value",
        created_at=NOW,
        updated_at=NOW,
        filters=(ScreenFilter(id="f1", field="pe_ratio", operator=ScreenOperator.BETWEEN, value=[10, 20]),),
    )

    model = profile_to_model(profile)
    restored = model_to_profile(model)

    assert restored.filters[0].value == [10, 20]


def test_nested_group_hierarchy_round_trips() -> None:
    profile = ScreeningProfile(
        id="p1",
        name="Nested",
        created_at=NOW,
        updated_at=NOW,
        groups=(
            LogicalGroup(id="outer", logic=LogicType.OR),
            LogicalGroup(id="inner", logic=LogicType.AND, parent_group="outer"),
        ),
    )

    model = profile_to_model(profile)
    restored = model_to_profile(model)

    assert restored.groups[1].parent_group == "outer"
