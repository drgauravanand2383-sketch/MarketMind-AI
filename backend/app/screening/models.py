"""Domain models for the Screening Engine.

The Screening Engine is completely data-source agnostic: `CompanyMetrics`
represents normalized metrics some future market-data provider will
supply — nothing here fetches, computes, or caches real market data.

Design note — nesting and the profile's implicit root: `LogicalGroup` as
specified carries only `id`/`logic`. For "nested logical evaluation" to be
possible at all, groups must be able to nest inside other groups, and
`ScreeningProfile` needs a place to hold them — neither is in the sprint's
literal field list, so two additive fields are introduced here (flagged,
matching the precedent set by `Watchlist.items` in Sprint 44):
`LogicalGroup.parent_group` (`None` = a top-level group) and
`ScreeningProfile.groups`. Every `ScreenFilter.group` and every
`LogicalGroup.parent_group` either point at a `LogicalGroup.id` present in
`ScreeningProfile.groups`, or is `None`, meaning "attached directly to the
profile's own implicit root," which always combines its direct children
(top-level filters and top-level groups) with AND. See
`app.screening.engine` for the evaluation algorithm this shape enables.

Design note — validation split: everything a `ScreenFilter`/
`ScreeningProfile` can check about itself (unknown operator — via the enum
type; invalid BETWEEN; empty IN/NOT_IN; missing value; duplicate filter/
group id; a filter or group referencing an unknown group; a cycle in the
group hierarchy; an unknown `CompanyMetrics` field) is enforced by a
`model_validator` here, raising a plain `pydantic.ValidationError` —
mirrors `app.planning.models.PlanTemplate`'s own local validation. Rules
that need injected, runtime-configurable state (duplicate profile *names*,
a maximum filter count) cannot be pydantic field constraints and live in
`app.screening.engine.ScreeningEngine` instead, raising
`app.screening.exceptions.ScreeningError` subclasses.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "ScreenOperator",
    "LogicType",
    "ScreenFilter",
    "LogicalGroup",
    "ScreeningProfile",
    "FilterEvaluation",
    "ScreenResult",
    "CompanyMetrics",
]


class ScreenOperator(StrEnum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    GREATER_EQUAL = "GREATER_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_EQUAL = "LESS_EQUAL"
    BETWEEN = "BETWEEN"
    IN = "IN"
    NOT_IN = "NOT_IN"


class LogicType(StrEnum):
    AND = "AND"
    OR = "OR"


class CompanyMetrics(BaseModel):
    """Normalized company metrics, as a future market-data provider would
    supply them. No field beyond `ticker`/`company_name` is required."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    company_name: str = Field(min_length=1)

    country: str | None = None
    sector: str | None = None
    industry: str | None = None

    market_cap: float | None = None
    price: float | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    ev_ebitda: float | None = None

    revenue_growth: float | None = None
    earnings_growth: float | None = None
    eps_growth: float | None = None

    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None

    roe: float | None = None
    roa: float | None = None
    roic: float | None = None

    debt_to_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None

    free_cash_flow: float | None = None
    fcf_margin: float | None = None

    dividend_yield: float | None = None
    payout_ratio: float | None = None

    beta: float | None = None
    volatility: float | None = None

    analyst_rating: str | None = None
    analyst_target_upside: float | None = None

    insider_ownership: float | None = None
    institutional_ownership: float | None = None


_COMPANY_METRICS_FIELDS: frozenset[str] = frozenset(CompanyMetrics.model_fields.keys())

_LIST_LIKE_OPERATORS = frozenset({ScreenOperator.IN, ScreenOperator.NOT_IN})


class ScreenFilter(BaseModel):
    """One screening condition: `field` `operator` `value`, evaluated
    against a `CompanyMetrics` instance. `group` names the `LogicalGroup`
    (by id) this filter is a direct child of; `None` means it is a direct
    child of the profile's own implicit root."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    operator: ScreenOperator
    value: Any = None
    group: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def _validate_field_and_value(self) -> ScreenFilter:
        if self.field not in _COMPANY_METRICS_FIELDS:
            raise ValueError(
                f"Filter {self.id!r} references unknown CompanyMetrics field {self.field!r}."
            )

        if self.operator == ScreenOperator.BETWEEN:
            if not isinstance(self.value, (list, tuple)) or len(self.value) != 2:
                raise ValueError(
                    f"Filter {self.id!r}: BETWEEN requires a value of exactly [low, high]."
                )
            low, high = self.value
            if low is None or high is None:
                raise ValueError(f"Filter {self.id!r}: BETWEEN bounds must not be None.")
            if low > high:
                raise ValueError(
                    f"Filter {self.id!r}: BETWEEN low bound {low!r} exceeds high bound {high!r}."
                )
        elif self.operator in _LIST_LIKE_OPERATORS:
            if not isinstance(self.value, (list, tuple)) or len(self.value) == 0:
                raise ValueError(
                    f"Filter {self.id!r}: {self.operator.value} requires a non-empty list of values."
                )
        elif self.value is None:
            raise ValueError(f"Filter {self.id!r}: {self.operator.value} requires a value.")

        return self


class LogicalGroup(BaseModel):
    """A named AND/OR combinator. `parent_group` names the `LogicalGroup`
    (by id) this group is nested directly inside; `None` means it is a
    top-level group, a direct child of the profile's own implicit root."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    logic: LogicType
    parent_group: str | None = None


class ScreeningProfile(BaseModel):
    """A named, reusable set of screening filters/groups."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    created_at: datetime
    updated_at: datetime
    is_default: bool = False
    filters: tuple[ScreenFilter, ...] = Field(default_factory=tuple)
    groups: tuple[LogicalGroup, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_structure(self) -> ScreeningProfile:
        seen_filter_ids: set[str] = set()
        for screen_filter in self.filters:
            if screen_filter.id in seen_filter_ids:
                raise ValueError(f"Duplicate filter id {screen_filter.id!r}.")
            seen_filter_ids.add(screen_filter.id)

        group_ids = {group.id for group in self.groups}
        seen_group_ids: set[str] = set()
        for group in self.groups:
            if group.id in seen_group_ids:
                raise ValueError(f"Duplicate group id {group.id!r}.")
            seen_group_ids.add(group.id)
            if group.parent_group is not None and group.parent_group not in group_ids:
                raise ValueError(
                    f"Group {group.id!r} references unknown parent_group {group.parent_group!r}."
                )

        for screen_filter in self.filters:
            if screen_filter.group is not None and screen_filter.group not in group_ids:
                raise ValueError(
                    f"Filter {screen_filter.id!r} references unknown group {screen_filter.group!r}."
                )

        _detect_group_cycle(self.groups)
        return self


def _detect_group_cycle(groups: tuple[LogicalGroup, ...]) -> None:
    parent_of = {group.id: group.parent_group for group in groups}
    _WHITE, _GRAY, _BLACK = 0, 1, 2
    color: dict[str, int] = {group_id: _WHITE for group_id in parent_of}

    def _visit(group_id: str) -> None:
        color[group_id] = _GRAY
        parent = parent_of[group_id]
        if parent is not None:
            if color[parent] == _GRAY:
                raise ValueError(f"Cycle detected in group hierarchy involving group {group_id!r}.")
            if color[parent] == _WHITE:
                _visit(parent)
        color[group_id] = _BLACK

    for group_id in parent_of:
        if color[group_id] == _WHITE:
            _visit(group_id)


class FilterEvaluation(BaseModel):
    """The outcome of evaluating one `ScreenFilter` against one company's metrics."""

    model_config = ConfigDict(extra="forbid")

    filter_id: str
    field: str
    operator: ScreenOperator
    passed: bool
    reason: str | None = None


class ScreenResult(BaseModel):
    """The outcome of evaluating one `ScreeningProfile` against one company's metrics."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    company_name: str | None = None
    passed: bool
    matched_filters: tuple[FilterEvaluation, ...] = Field(default_factory=tuple)
    failed_filters: tuple[FilterEvaluation, ...] = Field(default_factory=tuple)
    score: float
    details: dict[str, Any] = Field(default_factory=dict)
