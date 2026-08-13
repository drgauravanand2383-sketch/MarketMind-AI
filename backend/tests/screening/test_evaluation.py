"""Tests for ScreeningEngine.evaluate_company()/evaluate_companies():
per-operator behavior, AND/OR/nested logic, disabled filters, scoring,
explainability, and edge cases. Constructed directly against
`ScreeningEngine.__new__` where no repository is needed (evaluation is
pure and synchronous) — profile-management tests live in
`test_engine_profiles.py`.
"""

from __future__ import annotations

import pytest

from app.screening.engine import ScreeningEngine
from app.screening.models import CompanyMetrics, LogicalGroup, LogicType, ScreenOperator
from tests.screening.conftest import make_filter, make_profile


@pytest.fixture
def engine() -> ScreeningEngine:
    return ScreeningEngine.__new__(ScreeningEngine)


def metrics(**overrides: object) -> CompanyMetrics:
    defaults: dict[str, object] = {"ticker": "AAPL", "company_name": "Apple"}
    defaults.update(overrides)
    return CompanyMetrics(**defaults)


# --- Each operator -----------------------------------------------------------


def test_equals_operator_pass_and_fail(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(field="sector", operator=ScreenOperator.EQUALS, value="Technology"),))
    assert engine.evaluate_company(profile, metrics(sector="Technology")).passed is True
    assert engine.evaluate_company(profile, metrics(sector="Energy")).passed is False


def test_not_equals_operator_pass_and_fail(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(field="sector", operator=ScreenOperator.NOT_EQUALS, value="Technology"),))
    assert engine.evaluate_company(profile, metrics(sector="Energy")).passed is True
    assert engine.evaluate_company(profile, metrics(sector="Technology")).passed is False


def test_greater_than_operator_pass_and_fail(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(operator=ScreenOperator.GREATER_THAN, value=10),))
    assert engine.evaluate_company(profile, metrics(pe_ratio=11)).passed is True
    assert engine.evaluate_company(profile, metrics(pe_ratio=10)).passed is False
    assert engine.evaluate_company(profile, metrics(pe_ratio=9)).passed is False


def test_greater_equal_operator_pass_and_fail(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(operator=ScreenOperator.GREATER_EQUAL, value=10),))
    assert engine.evaluate_company(profile, metrics(pe_ratio=10)).passed is True
    assert engine.evaluate_company(profile, metrics(pe_ratio=9)).passed is False


def test_less_than_operator_pass_and_fail(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(operator=ScreenOperator.LESS_THAN, value=10),))
    assert engine.evaluate_company(profile, metrics(pe_ratio=9)).passed is True
    assert engine.evaluate_company(profile, metrics(pe_ratio=10)).passed is False


def test_less_equal_operator_pass_and_fail(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(operator=ScreenOperator.LESS_EQUAL, value=10),))
    assert engine.evaluate_company(profile, metrics(pe_ratio=10)).passed is True
    assert engine.evaluate_company(profile, metrics(pe_ratio=11)).passed is False


def test_between_operator_pass_and_fail(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(operator=ScreenOperator.BETWEEN, value=[10, 20]),))
    assert engine.evaluate_company(profile, metrics(pe_ratio=15)).passed is True
    assert engine.evaluate_company(profile, metrics(pe_ratio=10)).passed is True
    assert engine.evaluate_company(profile, metrics(pe_ratio=20)).passed is True
    assert engine.evaluate_company(profile, metrics(pe_ratio=9)).passed is False
    assert engine.evaluate_company(profile, metrics(pe_ratio=21)).passed is False


def test_in_operator_pass_and_fail(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(field="country", operator=ScreenOperator.IN, value=["US", "Canada"]),))
    assert engine.evaluate_company(profile, metrics(country="US")).passed is True
    assert engine.evaluate_company(profile, metrics(country="Germany")).passed is False


def test_not_in_operator_pass_and_fail(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(field="country", operator=ScreenOperator.NOT_IN, value=["US", "Canada"]),))
    assert engine.evaluate_company(profile, metrics(country="Germany")).passed is True
    assert engine.evaluate_company(profile, metrics(country="US")).passed is False


def test_missing_metric_value_fails_the_filter(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20),))
    result = engine.evaluate_company(profile, metrics(pe_ratio=None))
    assert result.passed is False
    assert "missing" in result.failed_filters[0].reason


# --- AND logic -----------------------------------------------------------


def test_top_level_and_requires_all_filters_to_pass(engine: ScreeningEngine) -> None:
    profile = make_profile(
        filters=(
            make_filter("f1", field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20),
            make_filter("f2", field="roe", operator=ScreenOperator.GREATER_THAN, value=0.15),
        )
    )
    assert engine.evaluate_company(profile, metrics(pe_ratio=15, roe=0.2)).passed is True
    assert engine.evaluate_company(profile, metrics(pe_ratio=15, roe=0.1)).passed is False
    assert engine.evaluate_company(profile, metrics(pe_ratio=30, roe=0.2)).passed is False


def test_explicit_and_group(engine: ScreeningEngine) -> None:
    group = LogicalGroup(id="g1", logic=LogicType.AND)
    profile = make_profile(
        filters=(
            make_filter("f1", field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20, group="g1"),
            make_filter("f2", field="roe", operator=ScreenOperator.GREATER_THAN, value=0.15, group="g1"),
        ),
        groups=(group,),
    )
    assert engine.evaluate_company(profile, metrics(pe_ratio=15, roe=0.2)).passed is True
    assert engine.evaluate_company(profile, metrics(pe_ratio=30, roe=0.2)).passed is False


# --- OR logic -----------------------------------------------------------


def test_or_group_passes_if_any_child_passes(engine: ScreeningEngine) -> None:
    group = LogicalGroup(id="g1", logic=LogicType.OR)
    profile = make_profile(
        filters=(
            make_filter("f1", field="sector", operator=ScreenOperator.EQUALS, value="Technology", group="g1"),
            make_filter("f2", field="sector", operator=ScreenOperator.EQUALS, value="Energy", group="g1"),
        ),
        groups=(group,),
    )
    assert engine.evaluate_company(profile, metrics(sector="Technology")).passed is True
    assert engine.evaluate_company(profile, metrics(sector="Energy")).passed is True
    assert engine.evaluate_company(profile, metrics(sector="Materials")).passed is False


def test_or_group_combined_with_top_level_and(engine: ScreeningEngine) -> None:
    """market_cap > 1B AND (sector == Technology OR sector == Energy)."""
    group = LogicalGroup(id="g1", logic=LogicType.OR)
    profile = make_profile(
        filters=(
            make_filter("cap", field="market_cap", operator=ScreenOperator.GREATER_THAN, value=1_000_000_000),
            make_filter("tech", field="sector", operator=ScreenOperator.EQUALS, value="Technology", group="g1"),
            make_filter("energy", field="sector", operator=ScreenOperator.EQUALS, value="Energy", group="g1"),
        ),
        groups=(group,),
    )
    assert engine.evaluate_company(profile, metrics(market_cap=2e9, sector="Technology")).passed is True
    assert engine.evaluate_company(profile, metrics(market_cap=2e9, sector="Materials")).passed is False
    assert engine.evaluate_company(profile, metrics(market_cap=1e8, sector="Technology")).passed is False


# --- Nested logic -----------------------------------------------------------


def test_nested_group_three_levels(engine: ScreeningEngine) -> None:
    """Root AND: [market_cap > 1B] AND (outer OR: [sector==Tech] OR (inner AND: [pe<20, roe>0.1]))."""
    outer = LogicalGroup(id="outer", logic=LogicType.OR)
    inner = LogicalGroup(id="inner", logic=LogicType.AND, parent_group="outer")
    profile = make_profile(
        filters=(
            make_filter("cap", field="market_cap", operator=ScreenOperator.GREATER_THAN, value=1_000_000_000),
            make_filter("tech", field="sector", operator=ScreenOperator.EQUALS, value="Technology", group="outer"),
            make_filter("pe", field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20, group="inner"),
            make_filter("roe", field="roe", operator=ScreenOperator.GREATER_THAN, value=0.1, group="inner"),
        ),
        groups=(outer, inner),
    )

    # big cap + tech -> passes via outer's tech branch
    assert engine.evaluate_company(
        profile, metrics(market_cap=2e9, sector="Technology", pe_ratio=999, roe=0.0)
    ).passed is True
    # big cap + non-tech but inner AND satisfied -> passes via outer's inner-AND branch
    assert engine.evaluate_company(
        profile, metrics(market_cap=2e9, sector="Energy", pe_ratio=10, roe=0.2)
    ).passed is True
    # big cap + non-tech + inner AND fails (roe too low) -> fails
    assert engine.evaluate_company(
        profile, metrics(market_cap=2e9, sector="Energy", pe_ratio=10, roe=0.01)
    ).passed is False
    # small cap always fails, regardless of the OR branch
    assert engine.evaluate_company(
        profile, metrics(market_cap=1e8, sector="Technology", pe_ratio=10, roe=0.5)
    ).passed is False


def test_empty_group_and_is_vacuously_true(engine: ScreeningEngine) -> None:
    group = LogicalGroup(id="g1", logic=LogicType.AND)
    profile = make_profile(filters=(), groups=(group,))
    assert engine.evaluate_company(profile, metrics()).passed is True


def test_empty_group_or_is_vacuously_false() -> None:
    """An OR group with zero children never contributes a True to its
    parent -- verified indirectly via a top-level filter it's ANDed with,
    since an empty OR group standing completely alone would be
    unreachable/never evaluated (nothing points a filter at it)."""
    engine = ScreeningEngine.__new__(ScreeningEngine)
    or_group = LogicalGroup(id="g1", logic=LogicType.OR, parent_group=None)
    profile = make_profile(
        filters=(make_filter("f1", field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20),),
        groups=(or_group,),
    )
    # top-level AND: [pe<20] AND (empty OR group == vacuously False) -> overall False
    assert engine.evaluate_company(profile, metrics(pe_ratio=5)).passed is False


def test_profile_with_no_filters_passes_vacuously(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(), groups=())
    result = engine.evaluate_company(profile, metrics())
    assert result.passed is True
    assert result.score == 100.0


# --- Disabled filters -----------------------------------------------------------


def test_disabled_filter_is_ignored_entirely(engine: ScreeningEngine) -> None:
    profile = make_profile(
        filters=(
            make_filter("f1", field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=5, enabled=False),
            make_filter("f2", field="roe", operator=ScreenOperator.GREATER_THAN, value=0.1),
        )
    )
    result = engine.evaluate_company(profile, metrics(pe_ratio=999, roe=0.5))
    assert result.passed is True
    assert result.details["enabled_filters"] == 1
    assert result.details["disabled_filters"] == 1


def test_disabled_filter_does_not_appear_in_matched_or_failed() -> None:
    engine = ScreeningEngine.__new__(ScreeningEngine)
    profile = make_profile(filters=(make_filter("f1", enabled=False),))
    result = engine.evaluate_company(profile, metrics(pe_ratio=999))
    assert result.matched_filters == ()
    assert result.failed_filters == ()


def test_all_filters_disabled_passes_vacuously(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter("f1", enabled=False), make_filter("f2", enabled=False)))
    result = engine.evaluate_company(profile, metrics(pe_ratio=999))
    assert result.passed is True
    assert result.score == 100.0


# --- Scoring -----------------------------------------------------------


def test_score_is_percentage_of_matched_enabled_filters(engine: ScreeningEngine) -> None:
    profile = make_profile(
        filters=(
            make_filter("f1", field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20),
            make_filter("f2", field="roe", operator=ScreenOperator.GREATER_THAN, value=0.15),
            make_filter("f3", field="beta", operator=ScreenOperator.LESS_THAN, value=1.5),
            make_filter("f4", field="current_ratio", operator=ScreenOperator.GREATER_THAN, value=1),
        )
    )
    result = engine.evaluate_company(
        profile, metrics(pe_ratio=15, roe=0.2, beta=2.0, current_ratio=0.5)
    )
    assert result.score == 50.0  # 2 of 4 matched


def test_score_can_be_high_even_when_the_profile_fails_overall(engine: ScreeningEngine) -> None:
    """score reflects percentage matched across all enabled filters; passed
    reflects the strict AND/OR group structure -- these are two distinct
    signals and can diverge (e.g. a near-miss with one OR branch failing)."""
    group = LogicalGroup(id="g1", logic=LogicType.AND)
    profile = make_profile(
        filters=(
            make_filter("f1", field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20, group="g1"),
            make_filter("f2", field="roe", operator=ScreenOperator.GREATER_THAN, value=0.15, group="g1"),
            make_filter("f3", field="beta", operator=ScreenOperator.LESS_THAN, value=1.5, group="g1"),
            make_filter("f4", field="current_ratio", operator=ScreenOperator.GREATER_THAN, value=100, group="g1"),
        ),
        groups=(group,),
    )
    result = engine.evaluate_company(
        profile, metrics(pe_ratio=15, roe=0.2, beta=1.0, current_ratio=1)
    )
    assert result.passed is False  # the AND group fails on f4
    assert result.score == 75.0  # but 3 of 4 filters matched


def test_disabled_filters_are_excluded_from_the_score_denominator(engine: ScreeningEngine) -> None:
    profile = make_profile(
        filters=(
            make_filter("f1", field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20),
            make_filter("f2", field="roe", operator=ScreenOperator.GREATER_THAN, value=0.99, enabled=False),
        )
    )
    result = engine.evaluate_company(profile, metrics(pe_ratio=15, roe=0.0))
    assert result.score == 100.0  # only 1 enabled filter, and it matched


# --- Explainability -----------------------------------------------------------


def test_matched_filters_carry_no_reason(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(operator=ScreenOperator.LESS_THAN, value=20),))
    result = engine.evaluate_company(profile, metrics(pe_ratio=15))
    assert result.matched_filters[0].reason is None
    assert result.matched_filters[0].passed is True


def test_failed_filters_carry_a_specific_reason(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20),))
    result = engine.evaluate_company(profile, metrics(pe_ratio=30))
    assert result.failed_filters[0].reason is not None
    assert "pe_ratio" in result.failed_filters[0].reason
    assert "30" in result.failed_filters[0].reason


def test_each_failed_filter_gets_its_own_distinct_reason(engine: ScreeningEngine) -> None:
    profile = make_profile(
        filters=(
            make_filter("f1", field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20),
            make_filter("f2", field="roe", operator=ScreenOperator.GREATER_THAN, value=0.5),
        )
    )
    result = engine.evaluate_company(profile, metrics(pe_ratio=30, roe=0.1))
    reasons = {f.filter_id: f.reason for f in result.failed_filters}
    assert "pe_ratio" in reasons["f1"]
    assert "roe" in reasons["f2"]
    assert reasons["f1"] != reasons["f2"]


def test_result_details_report_filter_counts(engine: ScreeningEngine) -> None:
    profile = make_profile(
        filters=(make_filter("f1"), make_filter("f2", enabled=False), make_filter("f3"))
    )
    result = engine.evaluate_company(profile, metrics(pe_ratio=1))
    assert result.details["total_filters"] == 3
    assert result.details["enabled_filters"] == 2
    assert result.details["disabled_filters"] == 1


def test_result_carries_ticker_and_company_name(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(),))
    result = engine.evaluate_company(profile, metrics(pe_ratio=1, ticker="MSFT", company_name="Microsoft"))
    assert result.ticker == "MSFT"
    assert result.company_name == "Microsoft"


# --- evaluate_companies -----------------------------------------------------------


def test_evaluate_companies_returns_one_result_per_company(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(operator=ScreenOperator.LESS_THAN, value=20),))
    companies = [
        metrics(ticker="A", company_name="A", pe_ratio=10),
        metrics(ticker="B", company_name="B", pe_ratio=30),
    ]
    results = engine.evaluate_companies(profile, companies)
    assert [r.ticker for r in results] == ["A", "B"]
    assert results[0].passed is True
    assert results[1].passed is False


def test_evaluate_companies_with_empty_list_returns_empty_list(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(),))
    assert engine.evaluate_companies(profile, []) == []


# --- Edge cases / large screening sets -----------------------------------------------------------


def test_large_screening_set_many_filters(engine: ScreeningEngine) -> None:
    filters = tuple(
        make_filter(f"f{i}", field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=100)
        for i in range(300)
    )
    profile = make_profile(filters=filters)
    result = engine.evaluate_company(profile, metrics(pe_ratio=10))
    assert result.passed is True
    assert result.score == 100.0
    assert len(result.matched_filters) == 300


def test_large_screening_set_many_companies(engine: ScreeningEngine) -> None:
    profile = make_profile(filters=(make_filter(operator=ScreenOperator.LESS_THAN, value=20),))
    companies = [
        metrics(ticker=f"T{i}", company_name=f"Company {i}", pe_ratio=(i % 40))
        for i in range(1000)
    ]
    results = engine.evaluate_companies(profile, companies)
    assert len(results) == 1000
    assert sum(1 for r in results if r.passed) == sum(1 for i in range(1000) if (i % 40) < 20)


def test_deeply_nested_groups(engine: ScreeningEngine) -> None:
    """Five levels of alternating AND/OR nesting, all satisfied."""
    groups = tuple(
        LogicalGroup(
            id=f"g{level}",
            logic=LogicType.AND if level % 2 == 0 else LogicType.OR,
            parent_group=f"g{level - 1}" if level > 0 else None,
        )
        for level in range(5)
    )
    leaf_filter = make_filter(field="pe_ratio", operator=ScreenOperator.LESS_THAN, value=20, group="g4")
    profile = make_profile(filters=(leaf_filter,), groups=groups)
    assert engine.evaluate_company(profile, metrics(pe_ratio=10)).passed is True
    assert engine.evaluate_company(profile, metrics(pe_ratio=30)).passed is False
