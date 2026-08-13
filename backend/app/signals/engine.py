"""SignalDetectionService: the Signal Detection Engine's Application layer.

Combines signal-definition CRUD (delegated to an injected
`BaseSignalDefinitionRepository`) with the actual evaluation logic (pure,
stateless, deterministic — no network I/O, no market data fetching, no AI).
Consumes only `app.market_data.models` (via `MarketDataSnapshot`) — no live
provider connection, no trade execution, no investment recommendation, no
portfolio mutation, and no alert generation happen here. No globals, no
singleton: every dependency is injected at construction time.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.signals.exceptions import (
    DuplicateSignalNameError,
    MaxConditionsExceededError,
    SignalDefinitionNotFoundError,
)
from app.signals.models import (
    ConditionEvaluation,
    MarketDataSnapshot,
    SignalBatchResult,
    SignalCondition,
    SignalConditionGroup,
    SignalDefinition,
    SignalLogicType,
    SignalOperator,
    SignalPriority,
    SignalResult,
)

if TYPE_CHECKING:
    from app.repositories.signals.repository import BaseSignalDefinitionRepository

__all__ = ["SignalDetectionService"]

DEFAULT_MAX_CONDITIONS = 100

_PRIORITY_MULTIPLIER: dict[SignalPriority, float] = {
    SignalPriority.LOW: 0.85,
    SignalPriority.MEDIUM: 1.0,
    SignalPriority.HIGH: 1.15,
    SignalPriority.CRITICAL: 1.3,
}

_PRIORITY_RANK: dict[SignalPriority, int] = {
    SignalPriority.CRITICAL: 0,
    SignalPriority.HIGH: 1,
    SignalPriority.MEDIUM: 2,
    SignalPriority.LOW: 3,
}


class SignalDetectionService:
    def __init__(
        self,
        repository: BaseSignalDefinitionRepository,
        *,
        max_conditions: int = DEFAULT_MAX_CONDITIONS,
        enforce_unique_names: bool = True,
    ) -> None:
        self._repository = repository
        self._max_conditions = max_conditions
        self._enforce_unique_names = enforce_unique_names

    # --- Definition management -----------------------------------------------------------

    async def create_signal_definition(
        self,
        name: str,
        *,
        description: str = "",
        category: str = "CUSTOM",
        priority: str = "MEDIUM",
        enabled: bool = True,
        conditions: tuple[SignalCondition, ...] = (),
        groups: tuple[SignalConditionGroup, ...] = (),
    ) -> SignalDefinition:
        """Create a new signal definition.

        Raises:
            MaxConditionsExceededError: `len(conditions)` exceeds the configured maximum.
            DuplicateSignalNameError: `name` is already in use (only when
                `enforce_unique_names=True`, the default).
        """
        self._check_condition_count(None, conditions)
        await self._check_unique_name(name)

        now = datetime.now(timezone.utc)
        definition = SignalDefinition(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            category=category,
            priority=priority,
            enabled=enabled,
            conditions=conditions,
            groups=groups,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_signal_definition(definition)

    async def update_signal_definition(self, definition: SignalDefinition) -> SignalDefinition:
        """Replace an existing definition's stored state with `definition` (same id).

        Raises:
            SignalDefinitionNotFoundError: no definition exists for `definition.id`.
            MaxConditionsExceededError: `len(definition.conditions)` exceeds the configured maximum.
            DuplicateSignalNameError: `definition.name` is already in use by
                a *different* definition (only when `enforce_unique_names=True`).
        """
        self._check_condition_count(definition.id, definition.conditions)
        await self._check_unique_name(definition.name, ignore_signal_id=definition.id)

        updated = definition.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        result = await self._repository.update_signal_definition(updated)
        if result is None:
            raise SignalDefinitionNotFoundError(definition.id)
        return result

    async def delete_signal_definition(self, signal_id: str) -> None:
        """Raises `SignalDefinitionNotFoundError` if no definition exists for `signal_id`."""
        deleted = await self._repository.delete_signal_definition(signal_id)
        if not deleted:
            raise SignalDefinitionNotFoundError(signal_id)

    async def list_signal_definitions(self) -> list[SignalDefinition]:
        return await self._repository.list_signal_definitions()

    async def get_signal_definition(self, signal_id: str) -> SignalDefinition:
        """Raises `SignalDefinitionNotFoundError` if no definition exists for `signal_id`."""
        definition = await self._repository.get_signal_definition(signal_id)
        if definition is None:
            raise SignalDefinitionNotFoundError(signal_id)
        return definition

    async def duplicate_signal_definition(self, signal_id: str, new_name: str) -> SignalDefinition:
        """Copy an existing definition's conditions/groups into a new definition.

        Raises:
            SignalDefinitionNotFoundError: no definition exists for `signal_id`.
            DuplicateSignalNameError: `new_name` is already in use (only
                when `enforce_unique_names=True`).
        """
        await self._check_unique_name(new_name)
        result = await self._repository.duplicate_signal_definition(
            signal_id, str(uuid.uuid4()), new_name
        )
        if result is None:
            raise SignalDefinitionNotFoundError(signal_id)
        return result

    def _check_condition_count(
        self, signal_id: str | None, conditions: tuple[SignalCondition, ...]
    ) -> None:
        if len(conditions) > self._max_conditions:
            raise MaxConditionsExceededError(signal_id, limit=self._max_conditions, actual=len(conditions))

    async def _check_unique_name(self, name: str, *, ignore_signal_id: str | None = None) -> None:
        if not self._enforce_unique_names:
            return
        for existing in await self._repository.list_signal_definitions():
            if existing.name == name and existing.id != ignore_signal_id:
                raise DuplicateSignalNameError(name)

    # --- Evaluation -----------------------------------------------------------

    def evaluate_company(
        self, snapshot: MarketDataSnapshot, definition: SignalDefinition
    ) -> SignalResult:
        """Evaluate one company's `MarketDataSnapshot` against one
        `SignalDefinition`. Pure and synchronous — no I/O, no market data
        fetching, no AI reasoning.
        """
        enabled_conditions = [c for c in definition.conditions if c.enabled]
        evaluations = {c.id: _evaluate_condition(c, snapshot) for c in enabled_conditions}

        triggered = _evaluate_root(definition.groups, enabled_conditions, evaluations)

        matched = tuple(evaluations[c.id] for c in enabled_conditions if evaluations[c.id].passed)
        failed = tuple(evaluations[c.id] for c in enabled_conditions if not evaluations[c.id].passed)
        score = _weighted_score(enabled_conditions, evaluations)
        confidence = _confidence(score, definition.priority)

        return SignalResult(
            ticker=snapshot.ticker,
            company_name=snapshot.company_name,
            signal_name=definition.name,
            category=definition.category,
            triggered=triggered,
            confidence=confidence,
            score=score,
            priority=definition.priority,
            matched_conditions=matched,
            failed_conditions=failed,
            reason=_build_reason(triggered, matched, failed, enabled_conditions, score),
            timestamp=datetime.now(timezone.utc),
        )

    def evaluate_companies(
        self, snapshots: list[MarketDataSnapshot], definition: SignalDefinition
    ) -> SignalBatchResult:
        """Evaluate multiple companies against one signal definition."""
        results = [self.evaluate_company(snapshot, definition) for snapshot in snapshots]
        return _build_batch_result(results)

    def evaluate_definitions(
        self, snapshot: MarketDataSnapshot, definitions: list[SignalDefinition]
    ) -> SignalBatchResult:
        """Evaluate one company against multiple signal definitions,
        ordered by priority (CRITICAL first), then score descending."""
        results = [self.evaluate_company(snapshot, definition) for definition in definitions]
        return _build_batch_result(_sort_by_priority(results))

    def evaluate_batch(
        self, snapshots: list[MarketDataSnapshot], definitions: list[SignalDefinition]
    ) -> SignalBatchResult:
        """Evaluate multiple companies against multiple signal definitions
        (the full cross product), ordered by priority (CRITICAL first),
        then score descending."""
        results = [
            self.evaluate_company(snapshot, definition)
            for definition in definitions
            for snapshot in snapshots
        ]
        return _build_batch_result(_sort_by_priority(results))


def _evaluate_condition(condition: SignalCondition, snapshot: MarketDataSnapshot) -> ConditionEvaluation:
    namespace, _, field_name = condition.field.partition(".")
    source = getattr(snapshot, namespace, None)
    actual = getattr(source, field_name, None) if source is not None else None

    if actual is None:
        return ConditionEvaluation(
            condition_id=condition.id,
            field=condition.field,
            operator=condition.operator,
            weight=condition.weight,
            passed=False,
            reason=f"{condition.field} is missing from the supplied market data snapshot.",
        )

    passed, reason = _apply_operator(condition.operator, condition.field, actual, condition.value)
    return ConditionEvaluation(
        condition_id=condition.id,
        field=condition.field,
        operator=condition.operator,
        weight=condition.weight,
        passed=passed,
        reason=None if passed else reason,
    )


def _apply_operator(operator: SignalOperator, field: str, actual: Any, expected: Any) -> tuple[bool, str]:
    if operator == SignalOperator.EQUALS:
        passed = actual == expected
        reason = f"{field} ({actual!r}) does not equal {expected!r}."
    elif operator == SignalOperator.NOT_EQUALS:
        passed = actual != expected
        reason = f"{field} ({actual!r}) equals {expected!r}."
    elif operator == SignalOperator.GREATER_THAN:
        passed = actual > expected
        reason = f"{field} ({actual!r}) is not greater than {expected!r}."
    elif operator == SignalOperator.GREATER_EQUAL:
        passed = actual >= expected
        reason = f"{field} ({actual!r}) is not greater than or equal to {expected!r}."
    elif operator == SignalOperator.LESS_THAN:
        passed = actual < expected
        reason = f"{field} ({actual!r}) is not less than {expected!r}."
    elif operator == SignalOperator.LESS_EQUAL:
        passed = actual <= expected
        reason = f"{field} ({actual!r}) is not less than or equal to {expected!r}."
    elif operator == SignalOperator.BETWEEN:
        low, high = expected
        passed = low <= actual <= high
        reason = f"{field} ({actual!r}) is not between {low!r} and {high!r}."
    elif operator == SignalOperator.IN:
        passed = actual in expected
        reason = f"{field} ({actual!r}) is not in {list(expected)!r}."
    else:  # SignalOperator.NOT_IN
        passed = actual not in expected
        reason = f"{field} ({actual!r}) is in {list(expected)!r}."
    return passed, reason


def _evaluate_root(
    groups: tuple[SignalConditionGroup, ...],
    enabled_conditions: list[SignalCondition],
    evaluations: dict[str, ConditionEvaluation],
) -> bool:
    """Recursively evaluate the definition's implicit root (AND of its
    direct condition/group children), descending into nested groups.
    Trusts `SignalDefinition`'s own validation that the group hierarchy is
    acyclic and every reference resolves — no cycle guard is needed here.
    """
    conditions_by_group: dict[str | None, list[SignalCondition]] = defaultdict(list)
    for c in enabled_conditions:
        conditions_by_group[c.group].append(c)
    children_by_parent: dict[str | None, list[SignalConditionGroup]] = defaultdict(list)
    for g in groups:
        children_by_parent[g.parent_group].append(g)
    groups_by_id = {g.id: g for g in groups}

    def _eval(node_id: str | None) -> bool:
        results = [evaluations[c.id].passed for c in conditions_by_group.get(node_id, [])]
        results.extend(_eval(child.id) for child in children_by_parent.get(node_id, []))

        logic = SignalLogicType.AND if node_id is None else groups_by_id[node_id].logic
        if not results:
            return logic == SignalLogicType.AND  # vacuous: AND of nothing is True, OR of nothing is False
        return all(results) if logic == SignalLogicType.AND else any(results)

    return _eval(None)


def _weighted_score(
    enabled_conditions: list[SignalCondition], evaluations: dict[str, ConditionEvaluation]
) -> float:
    """The percentage of total condition *weight* that matched — not a
    plain count. A definition with one weight=10 condition and three
    weight=1 conditions is dominated by whether that first condition
    passed, not by "1 of 4."
    """
    if not enabled_conditions:
        return 100.0
    total_weight = sum(c.weight for c in enabled_conditions)
    matched_weight = sum(c.weight for c in enabled_conditions if evaluations[c.id].passed)
    return round(matched_weight / total_weight * 100, 2)


def _confidence(score: float, priority: SignalPriority) -> float:
    """Confidence combines the weighted match percentage (`score`) with
    the definition's own declared `priority`: a CRITICAL-priority signal
    is reported with proportionally higher confidence than an otherwise
    identical LOW-priority one, capped at 100. No exact formula is given
    by the sprint spec; this multiplier table is a documented, flagged
    judgment call (see the module's own design-note conventions elsewhere
    in this codebase) — not derived from any external source.
    """
    return round(min(100.0, score * _PRIORITY_MULTIPLIER[priority]), 2)


def _build_reason(
    triggered: bool,
    matched: tuple[ConditionEvaluation, ...],
    failed: tuple[ConditionEvaluation, ...],
    enabled_conditions: list[SignalCondition],
    score: float,
) -> str:
    if not enabled_conditions:
        return "No enabled conditions to evaluate; vacuously triggered."
    if triggered:
        return f"Triggered: {len(matched)} of {len(enabled_conditions)} conditions matched (weighted score {score}%)."
    return f"Not triggered: {len(failed)} of {len(enabled_conditions)} conditions failed (weighted score {score}%)."


def _sort_by_priority(results: list[SignalResult]) -> list[SignalResult]:
    """CRITICAL first, then HIGH/MEDIUM/LOW; ties broken by score
    descending, then ticker, then signal_name — fully deterministic
    regardless of input order."""
    return sorted(
        results,
        key=lambda r: (_PRIORITY_RANK[r.priority], -r.score, r.ticker, r.signal_name),
    )


def _build_batch_result(results: list[SignalResult]) -> SignalBatchResult:
    evaluated = len(results)
    triggered = sum(1 for r in results if r.triggered)
    average_score = round(sum(r.score for r in results) / evaluated, 2) if evaluated else 0.0
    summary = (
        f"Evaluated {evaluated} signal(s); {triggered} triggered; average score {average_score}%."
        if evaluated
        else "No signals evaluated."
    )
    return SignalBatchResult(
        signals=tuple(results),
        evaluated=evaluated,
        triggered=triggered,
        average_score=average_score,
        summary=summary,
    )
