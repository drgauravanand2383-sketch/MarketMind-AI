"""Tests for the Screening Engine's domain models: CompanyMetrics,
ScreenFilter (per-operator value validation), LogicalGroup, and
ScreeningProfile's structural validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.screening.models import (
    CompanyMetrics,
    LogicalGroup,
    LogicType,
    ScreenFilter,
    ScreenOperator,
)
from tests.screening.conftest import make_filter, make_profile

# --- CompanyMetrics -----------------------------------------------------------


def test_company_metrics_requires_ticker_and_company_name() -> None:
    with pytest.raises(ValidationError):
        CompanyMetrics(ticker="", company_name="Apple")
    with pytest.raises(ValidationError):
        CompanyMetrics(ticker="AAPL", company_name="")


def test_company_metrics_all_other_fields_default_to_none() -> None:
    metrics = CompanyMetrics(ticker="AAPL", company_name="Apple")
    assert metrics.pe_ratio is None
    assert metrics.sector is None
    assert metrics.market_cap is None
    assert metrics.analyst_rating is None


def test_company_metrics_accepts_full_metric_set() -> None:
    metrics = CompanyMetrics(
        ticker="AAPL",
        company_name="Apple",
        country="US",
        sector="Technology",
        industry="Consumer Electronics",
        market_cap=3e12,
        pe_ratio=30.5,
        roe=1.5,
        debt_to_equity=1.8,
        dividend_yield=0.005,
        beta=1.2,
        analyst_rating="Buy",
    )
    assert metrics.sector == "Technology"
    assert metrics.analyst_rating == "Buy"


# --- ScreenFilter: operator/value validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "operator,value",
    [
        (ScreenOperator.EQUALS, "Technology"),
        (ScreenOperator.NOT_EQUALS, "Technology"),
        (ScreenOperator.GREATER_THAN, 10),
        (ScreenOperator.GREATER_EQUAL, 10),
        (ScreenOperator.LESS_THAN, 10),
        (ScreenOperator.LESS_EQUAL, 10),
        (ScreenOperator.BETWEEN, [5, 10]),
        (ScreenOperator.IN, ["US", "Canada"]),
        (ScreenOperator.NOT_IN, ["US", "Canada"]),
    ],
)
def test_screen_filter_accepts_valid_value_for_each_operator(operator, value) -> None:  # noqa: ANN001
    screen_filter = ScreenFilter(id="f1", field="pe_ratio", operator=operator, value=value)
    assert screen_filter.operator == operator


def test_screen_filter_rejects_unknown_operator() -> None:
    with pytest.raises(ValidationError):
        ScreenFilter(id="f1", field="pe_ratio", operator="TOTALLY_MADE_UP", value=1)


def test_screen_filter_rejects_missing_value_for_scalar_operator() -> None:
    with pytest.raises(ValidationError):
        ScreenFilter(id="f1", field="pe_ratio", operator=ScreenOperator.GREATER_THAN, value=None)


def test_screen_filter_between_requires_two_element_list() -> None:
    with pytest.raises(ValidationError):
        ScreenFilter(id="f1", field="pe_ratio", operator=ScreenOperator.BETWEEN, value=[5])


def test_screen_filter_between_rejects_low_greater_than_high() -> None:
    with pytest.raises(ValidationError):
        ScreenFilter(id="f1", field="pe_ratio", operator=ScreenOperator.BETWEEN, value=[20, 5])


def test_screen_filter_between_rejects_non_list_value() -> None:
    with pytest.raises(ValidationError):
        ScreenFilter(id="f1", field="pe_ratio", operator=ScreenOperator.BETWEEN, value=20)


def test_screen_filter_between_accepts_equal_bounds() -> None:
    screen_filter = ScreenFilter(id="f1", field="pe_ratio", operator=ScreenOperator.BETWEEN, value=[10, 10])
    assert screen_filter.value == [10, 10]


def test_screen_filter_in_rejects_empty_list() -> None:
    with pytest.raises(ValidationError):
        ScreenFilter(id="f1", field="sector", operator=ScreenOperator.IN, value=[])


def test_screen_filter_not_in_rejects_empty_list() -> None:
    with pytest.raises(ValidationError):
        ScreenFilter(id="f1", field="sector", operator=ScreenOperator.NOT_IN, value=[])


def test_screen_filter_in_rejects_non_list_value() -> None:
    with pytest.raises(ValidationError):
        ScreenFilter(id="f1", field="sector", operator=ScreenOperator.IN, value="Technology")


def test_screen_filter_rejects_unknown_company_metrics_field() -> None:
    with pytest.raises(ValidationError):
        ScreenFilter(id="f1", field="not_a_real_field", operator=ScreenOperator.EQUALS, value=1)


def test_screen_filter_requires_non_empty_id() -> None:
    with pytest.raises(ValidationError):
        ScreenFilter(id="", field="pe_ratio", operator=ScreenOperator.GREATER_THAN, value=1)


def test_screen_filter_is_frozen() -> None:
    screen_filter = make_filter()
    with pytest.raises(ValidationError):
        screen_filter.value = 999


def test_screen_filter_defaults_to_enabled() -> None:
    screen_filter = make_filter()
    assert screen_filter.enabled is True


# --- LogicalGroup -----------------------------------------------------------


def test_logical_group_defaults_to_no_parent() -> None:
    group = LogicalGroup(id="g1", logic=LogicType.AND)
    assert group.parent_group is None


def test_logical_group_rejects_unknown_logic() -> None:
    with pytest.raises(ValidationError):
        LogicalGroup(id="g1", logic="XOR")


# --- ScreeningProfile: structural validation -----------------------------------------------------------


def test_screening_profile_requires_non_empty_name() -> None:
    with pytest.raises(ValidationError):
        make_profile(name="")


def test_screening_profile_accepts_valid_filters_and_groups() -> None:
    group = LogicalGroup(id="g1", logic=LogicType.OR)
    profile = make_profile(
        filters=(make_filter("f1", group="g1"), make_filter("f2", group="g1")), groups=(group,)
    )
    assert len(profile.filters) == 2


def test_screening_profile_rejects_duplicate_filter_id() -> None:
    with pytest.raises(ValidationError):
        make_profile(filters=(make_filter("f1"), make_filter("f1")))


def test_screening_profile_rejects_duplicate_group_id() -> None:
    with pytest.raises(ValidationError):
        make_profile(
            groups=(LogicalGroup(id="g1", logic=LogicType.AND), LogicalGroup(id="g1", logic=LogicType.OR))
        )


def test_screening_profile_rejects_filter_referencing_unknown_group() -> None:
    with pytest.raises(ValidationError):
        make_profile(filters=(make_filter("f1", group="does-not-exist"),))


def test_screening_profile_rejects_group_referencing_unknown_parent() -> None:
    with pytest.raises(ValidationError):
        make_profile(groups=(LogicalGroup(id="g1", logic=LogicType.AND, parent_group="does-not-exist"),))


def test_screening_profile_rejects_two_group_cycle() -> None:
    with pytest.raises(ValidationError):
        make_profile(
            groups=(
                LogicalGroup(id="g1", logic=LogicType.AND, parent_group="g2"),
                LogicalGroup(id="g2", logic=LogicType.OR, parent_group="g1"),
            )
        )


def test_screening_profile_rejects_self_referencing_group() -> None:
    with pytest.raises(ValidationError):
        make_profile(groups=(LogicalGroup(id="g1", logic=LogicType.AND, parent_group="g1"),))


def test_screening_profile_accepts_valid_nested_groups() -> None:
    profile = make_profile(
        groups=(
            LogicalGroup(id="outer", logic=LogicType.OR),
            LogicalGroup(id="inner", logic=LogicType.AND, parent_group="outer"),
        )
    )
    assert len(profile.groups) == 2


def test_screening_profile_defaults_to_no_filters_and_no_groups() -> None:
    profile = make_profile()
    assert profile.filters == ()
    assert profile.groups == ()


def test_screening_profile_is_frozen() -> None:
    profile = make_profile()
    with pytest.raises(ValidationError):
        profile.name = "Changed"


def test_screening_profile_defaults_is_default_to_false() -> None:
    profile = make_profile()
    assert profile.is_default is False
