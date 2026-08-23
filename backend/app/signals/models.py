"""Domain models for the Signal Detection Engine.

The engine detects and scores signals against normalized data from the
Market Data Abstraction Layer (Sprint 46) only — `MarketQuote`,
`CompanyProfile`, `FinancialRatios`, `Fundamentals` are imported and reused
as-is, never redefined or modified. No live provider connection, no trade
execution, no investment recommendation, no portfolio mutation, and no
alert generation exist anywhere in this package — detection and scoring
only.

Design note — `MarketDataSnapshot`: no single Market Data Abstraction
Layer model carries every field a signal might reference (a quote doesn't
carry P/E, a ratio snapshot doesn't carry volume). Evaluating "one company"
therefore needs a bundle of that company's already-fetched Market Data
records. `MarketDataSnapshot` is that bundle — additive, not part of the
sprint's literal Domain Models list, introduced because "evaluate one
company" is structurally meaningless without it. Flagged per the precedent
set by `Watchlist.items` (Sprint 44), `EarningsReport` (Sprint 46), and
every other additive-but-necessary model in this codebase.

Design note — dotted-path `SignalCondition.field`: with four source models
in play, several field names collide (`exchange` and `currency` both exist
on `MarketQuote` and `CompanyProfile`). A condition's `field` is therefore
`"<namespace>.<field_name>"` (e.g. `"quote.price"`, `"ratios.pe"`,
`"fundamentals.revenue"`, `"profile.sector"`) — unambiguous, and it also
makes a signal definition self-documenting about which Market Data record
it draws from. `value` is always a literal (mirrors
`app.screening.models.ScreenFilter.value` exactly) — this engine does not
support comparing one field against another field.

Design note — nested AND/OR groups: like `app.screening.models.LogicalGroup`
before it, "AND logic, OR logic, Nested evaluation" (this sprint's own
Evaluation Engine requirement) has no home in the literal Domain Models
list. `SignalConditionGroup` is added here, independently defined (never
imported from `app.screening` — Signal Detection and Screening are
sibling, independently evolving bounded contexts; importing one's internal
group model into the other would silently couple their futures). The
evaluation algorithm this shape enables is otherwise identical to
Screening's: one implicit AND root, `SignalCondition.group`/
`SignalConditionGroup.parent_group` pointing to `None` for "attached to
the root."
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.market_data.models import CompanyProfile, FinancialRatios, Fundamentals, MarketQuote

__all__ = [
    "SignalOperator",
    "SignalLogicType",
    "SignalCategory",
    "SignalPriority",
    "SignalConditionGroup",
    "SignalCondition",
    "SignalDefinition",
    "MarketDataSnapshot",
    "ConditionEvaluation",
    "SignalResult",
    "SignalBatchResult",
]


class SignalOperator(StrEnum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    GREATER_EQUAL = "GREATER_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_EQUAL = "LESS_EQUAL"
    BETWEEN = "BETWEEN"
    IN = "IN"
    NOT_IN = "NOT_IN"


class SignalLogicType(StrEnum):
    AND = "AND"
    OR = "OR"


class SignalCategory(StrEnum):
    TECHNICAL = "TECHNICAL"
    FUNDAMENTAL = "FUNDAMENTAL"
    VALUATION = "VALUATION"
    QUALITY = "QUALITY"
    MOMENTUM = "MOMENTUM"
    VOLUME = "VOLUME"
    VOLATILITY = "VOLATILITY"
    CUSTOM = "CUSTOM"


class SignalPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_FIELD_NAMESPACES: dict[str, frozenset[str]] = {
    "quote": frozenset(MarketQuote.model_fields.keys()),
    "profile": frozenset(CompanyProfile.model_fields.keys()),
    "fundamentals": frozenset(Fundamentals.model_fields.keys()),
    "ratios": frozenset(FinancialRatios.model_fields.keys()),
}

_LIST_LIKE_OPERATORS = frozenset({SignalOperator.IN, SignalOperator.NOT_IN})


class SignalConditionGroup(BaseModel):
    """A named AND/OR combinator. `parent_group` names the group (by id)
    this group is nested directly inside; `None` means it is a top-level
    group, a direct child of the definition's own implicit root."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    logic: SignalLogicType
    parent_group: str | None = None


class SignalCondition(BaseModel):
    """One signal condition: `field` `operator` `value`, evaluated against
    a `MarketDataSnapshot`. `field` is a dotted path `"<namespace>.<name>"`
    into one of the four Market Data Abstraction Layer models this engine
    consumes (`quote`, `profile`, `fundamentals`, `ratios`) — see the
    module docstring. `group` names the `SignalConditionGroup` (by id) this
    condition is a direct child of; `None` means it is a direct child of
    the definition's own implicit root.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    operator: SignalOperator
    value: Any = None
    weight: float = Field(default=1.0, gt=0)
    group: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def _validate_field_and_value(self) -> SignalCondition:
        namespace, _, field_name = self.field.partition(".")
        valid_fields = _FIELD_NAMESPACES.get(namespace)
        if valid_fields is None or not field_name or field_name not in valid_fields:
            raise ValueError(
                f"Condition {self.id!r} references unknown field {self.field!r}. "
                f"Expected '<namespace>.<field>' where namespace is one of "
                f"{sorted(_FIELD_NAMESPACES)!r}."
            )

        if self.operator == SignalOperator.BETWEEN:
            if not isinstance(self.value, (list, tuple)) or len(self.value) != 2:
                raise ValueError(
                    f"Condition {self.id!r}: BETWEEN requires a value of exactly [low, high]."
                )
            low, high = self.value
            if low is None or high is None:
                raise ValueError(f"Condition {self.id!r}: BETWEEN bounds must not be None.")
            if low > high:
                raise ValueError(
                    f"Condition {self.id!r}: BETWEEN low bound {low!r} exceeds high bound {high!r}."
                )
        elif self.operator in _LIST_LIKE_OPERATORS:
            if not isinstance(self.value, (list, tuple)) or len(self.value) == 0:
                raise ValueError(
                    f"Condition {self.id!r}: {self.operator.value} requires a non-empty list of values."
                )
        elif self.value is None:
            raise ValueError(f"Condition {self.id!r}: {self.operator.value} requires a value.")

        return self


class SignalDefinition(BaseModel):
    """A named, reusable, weighted signal: a set of conditions/groups,
    a category, a priority, and whether it is currently active."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    category: SignalCategory = SignalCategory.CUSTOM
    enabled: bool = True
    priority: SignalPriority = SignalPriority.MEDIUM
    conditions: tuple[SignalCondition, ...] = Field(default_factory=tuple)
    groups: tuple[SignalConditionGroup, ...] = Field(default_factory=tuple)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _validate_structure(self) -> SignalDefinition:
        seen_condition_ids: set[str] = set()
        for condition in self.conditions:
            if condition.id in seen_condition_ids:
                raise ValueError(f"Duplicate condition id {condition.id!r}.")
            seen_condition_ids.add(condition.id)

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

        for condition in self.conditions:
            if condition.group is not None and condition.group not in group_ids:
                raise ValueError(
                    f"Condition {condition.id!r} references unknown group {condition.group!r}."
                )

        _detect_group_cycle(self.groups)
        return self


def _detect_group_cycle(groups: tuple[SignalConditionGroup, ...]) -> None:
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


class MarketDataSnapshot(BaseModel):
    """One company's already-fetched Market Data Abstraction Layer
    records, bundled for evaluation. Every source is optional: a
    `SignalCondition` referencing a source that is `None` here is treated
    as "missing data" and fails that condition (see
    `app.signals.engine.SignalDetectionService`) — the same convention
    `app.screening.engine` uses for a missing `CompanyMetrics` field.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    company_name: str | None = None
    quote: MarketQuote | None = None
    profile: CompanyProfile | None = None
    fundamentals: Fundamentals | None = None
    ratios: FinancialRatios | None = None


class ConditionEvaluation(BaseModel):
    """The outcome of evaluating one `SignalCondition` against one
    company's `MarketDataSnapshot`.

    `actual_value`/`expected_value` (v1.2, Priority 1): the same values
    `app.signals.engine._apply_operator` already computes locally to build
    `reason`'s formatted string — surfaced here as structured fields too,
    additive and backward compatible, so a downstream consumer (e.g.
    `AlertExplanation`) can show "current value / threshold" without
    re-parsing a human-readable sentence. `None` for a condition that
    failed on missing data (no `actual_value` was ever read).
    """

    model_config = ConfigDict(extra="forbid")

    condition_id: str
    field: str
    operator: SignalOperator
    weight: float
    passed: bool
    reason: str | None = None
    actual_value: Any | None = None
    expected_value: Any | None = None


class SignalResult(BaseModel):
    """The outcome of evaluating one `SignalDefinition` against one
    company's `MarketDataSnapshot`."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    company_name: str | None = None
    signal_name: str
    category: SignalCategory
    triggered: bool
    confidence: float
    score: float
    priority: SignalPriority
    matched_conditions: tuple[ConditionEvaluation, ...] = Field(default_factory=tuple)
    failed_conditions: tuple[ConditionEvaluation, ...] = Field(default_factory=tuple)
    reason: str
    timestamp: datetime


class SignalBatchResult(BaseModel):
    """The aggregate outcome of one multi-company and/or multi-definition evaluation run."""

    model_config = ConfigDict(extra="forbid")

    signals: tuple[SignalResult, ...] = Field(default_factory=tuple)
    evaluated: int
    triggered: int
    average_score: float
    summary: str
