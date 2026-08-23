"""ScreeningEngine: the Screening Engine's Application layer.

Combines profile CRUD (delegated to an injected `BaseScreeningRepository`,
with business rules this sprint's spec does not give a separate service
class for — see the module docstring in `app.repositories.screening.repository`)
with the actual evaluation logic (pure, stateless, deterministic — no
network I/O, no market data, no AI). No globals, no singleton: every
dependency (`repository`, `max_filters`, `enforce_unique_names`) is
injected at construction time.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.screening.exceptions import (
    DuplicateProfileNameError,
    MaxFiltersExceededError,
    ScreeningProfileNotFoundError,
)
from app.screening.models import (
    CompanyMetrics,
    FilterEvaluation,
    LogicalGroup,
    LogicType,
    ScreenFilter,
    ScreeningProfile,
    ScreenOperator,
    ScreenResult,
)

if TYPE_CHECKING:
    from app.repositories.screening.repository import BaseScreeningRepository

__all__ = ["ScreeningEngine"]

DEFAULT_MAX_FILTERS = 100


class ScreeningEngine:
    def __init__(
        self,
        repository: BaseScreeningRepository,
        *,
        max_filters: int = DEFAULT_MAX_FILTERS,
        enforce_unique_names: bool = True,
    ) -> None:
        self._repository = repository
        self._max_filters = max_filters
        self._enforce_unique_names = enforce_unique_names

    # --- Profile management -----------------------------------------------------------

    async def create_profile(
        self,
        name: str,
        *,
        description: str = "",
        is_default: bool = False,
        filters: tuple[ScreenFilter, ...] = (),
        groups: tuple[LogicalGroup, ...] = (),
    ) -> ScreeningProfile:
        """Create a new screening profile.

        Raises:
            MaxFiltersExceededError: `len(filters)` exceeds the configured maximum.
            DuplicateProfileNameError: `name` is already in use (only when
                `enforce_unique_names=True`, the default).
        """
        self._check_filter_count(None, filters)
        await self._check_unique_name(name)

        now = datetime.now(UTC)
        profile = ScreeningProfile(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
            is_default=is_default,
            filters=filters,
            groups=groups,
        )
        return await self._repository.create_profile(profile)

    async def update_profile(self, profile: ScreeningProfile) -> ScreeningProfile:
        """Replace an existing profile's stored state with `profile` (same id).

        Raises:
            ScreeningProfileNotFoundError: no profile exists for `profile.id`.
            MaxFiltersExceededError: `len(profile.filters)` exceeds the configured maximum.
            DuplicateProfileNameError: `profile.name` is already in use by a
                *different* profile (only when `enforce_unique_names=True`).
        """
        self._check_filter_count(profile.id, profile.filters)
        await self._check_unique_name(profile.name, ignore_profile_id=profile.id)

        updated = profile.model_copy(update={"updated_at": datetime.now(UTC)})
        result = await self._repository.update_profile(updated)
        if result is None:
            raise ScreeningProfileNotFoundError(profile.id)
        return result

    async def delete_profile(self, profile_id: str) -> None:
        """Raises `ScreeningProfileNotFoundError` if no profile exists for `profile_id`."""
        deleted = await self._repository.delete_profile(profile_id)
        if not deleted:
            raise ScreeningProfileNotFoundError(profile_id)

    async def list_profiles(self) -> list[ScreeningProfile]:
        return await self._repository.list_profiles()

    async def get_profile(self, profile_id: str) -> ScreeningProfile:
        """Raises `ScreeningProfileNotFoundError` if no profile exists for `profile_id`."""
        profile = await self._repository.get_profile(profile_id)
        if profile is None:
            raise ScreeningProfileNotFoundError(profile_id)
        return profile

    async def duplicate_profile(self, profile_id: str, new_name: str) -> ScreeningProfile:
        """Copy an existing profile's filters/groups into a new profile.

        Raises:
            ScreeningProfileNotFoundError: no profile exists for `profile_id`.
            DuplicateProfileNameError: `new_name` is already in use (only
                when `enforce_unique_names=True`).
        """
        await self._check_unique_name(new_name)
        result = await self._repository.duplicate_profile(profile_id, str(uuid.uuid4()), new_name)
        if result is None:
            raise ScreeningProfileNotFoundError(profile_id)
        return result

    def _check_filter_count(
        self, profile_id: str | None, filters: tuple[ScreenFilter, ...]
    ) -> None:
        if len(filters) > self._max_filters:
            raise MaxFiltersExceededError(profile_id, limit=self._max_filters, actual=len(filters))

    async def _check_unique_name(self, name: str, *, ignore_profile_id: str | None = None) -> None:
        if not self._enforce_unique_names:
            return
        for existing in await self._repository.list_profiles():
            if existing.name == name and existing.id != ignore_profile_id:
                raise DuplicateProfileNameError(name)

    # --- Evaluation -----------------------------------------------------------

    def evaluate_company(self, profile: ScreeningProfile, metrics: CompanyMetrics) -> ScreenResult:
        """Evaluate one company's metrics against `profile`. Pure and
        synchronous — no I/O, no market data, no AI reasoning."""
        enabled_filters = [f for f in profile.filters if f.enabled]
        evaluations = {f.id: _evaluate_filter(f, metrics) for f in enabled_filters}

        passed = _evaluate_root(profile.groups, enabled_filters, evaluations)

        matched = tuple(evaluations[f.id] for f in enabled_filters if evaluations[f.id].passed)
        failed = tuple(evaluations[f.id] for f in enabled_filters if not evaluations[f.id].passed)
        score = 100.0 if not enabled_filters else round(len(matched) / len(enabled_filters) * 100, 2)

        return ScreenResult(
            ticker=metrics.ticker,
            company_name=metrics.company_name,
            passed=passed,
            matched_filters=matched,
            failed_filters=failed,
            score=score,
            details={
                "total_filters": len(profile.filters),
                "enabled_filters": len(enabled_filters),
                "disabled_filters": len(profile.filters) - len(enabled_filters),
            },
        )

    def evaluate_companies(
        self, profile: ScreeningProfile, metrics_list: list[CompanyMetrics]
    ) -> list[ScreenResult]:
        return [self.evaluate_company(profile, metrics) for metrics in metrics_list]


def _evaluate_filter(screen_filter: ScreenFilter, metrics: CompanyMetrics) -> FilterEvaluation:
    actual = getattr(metrics, screen_filter.field, None)
    if actual is None:
        return FilterEvaluation(
            filter_id=screen_filter.id,
            field=screen_filter.field,
            operator=screen_filter.operator,
            passed=False,
            reason=f"{screen_filter.field} is missing from the supplied metrics.",
        )

    passed, reason = _apply_operator(screen_filter.operator, screen_filter.field, actual, screen_filter.value)
    return FilterEvaluation(
        filter_id=screen_filter.id,
        field=screen_filter.field,
        operator=screen_filter.operator,
        passed=passed,
        reason=None if passed else reason,
    )


def _apply_operator(operator: ScreenOperator, field: str, actual: Any, expected: Any) -> tuple[bool, str]:
    if operator == ScreenOperator.EQUALS:
        passed = actual == expected
        reason = f"{field} ({actual!r}) does not equal {expected!r}."
    elif operator == ScreenOperator.NOT_EQUALS:
        passed = actual != expected
        reason = f"{field} ({actual!r}) equals {expected!r}."
    elif operator == ScreenOperator.GREATER_THAN:
        passed = actual > expected
        reason = f"{field} ({actual!r}) is not greater than {expected!r}."
    elif operator == ScreenOperator.GREATER_EQUAL:
        passed = actual >= expected
        reason = f"{field} ({actual!r}) is not greater than or equal to {expected!r}."
    elif operator == ScreenOperator.LESS_THAN:
        passed = actual < expected
        reason = f"{field} ({actual!r}) is not less than {expected!r}."
    elif operator == ScreenOperator.LESS_EQUAL:
        passed = actual <= expected
        reason = f"{field} ({actual!r}) is not less than or equal to {expected!r}."
    elif operator == ScreenOperator.BETWEEN:
        low, high = expected
        passed = low <= actual <= high
        reason = f"{field} ({actual!r}) is not between {low!r} and {high!r}."
    elif operator == ScreenOperator.IN:
        passed = actual in expected
        reason = f"{field} ({actual!r}) is not in {list(expected)!r}."
    else:  # ScreenOperator.NOT_IN
        passed = actual not in expected
        reason = f"{field} ({actual!r}) is in {list(expected)!r}."
    return passed, reason


def _evaluate_root(
    groups: tuple[LogicalGroup, ...],
    enabled_filters: list[ScreenFilter],
    evaluations: dict[str, FilterEvaluation],
) -> bool:
    """Recursively evaluate `profile`'s implicit root (AND of its direct
    filter/group children), descending into nested groups. Trusts
    `ScreeningProfile`'s own validation that the group hierarchy is acyclic
    and every reference resolves — no cycle guard is needed here.
    """
    filters_by_group: dict[str | None, list[ScreenFilter]] = defaultdict(list)
    for f in enabled_filters:
        filters_by_group[f.group].append(f)
    children_by_parent: dict[str | None, list[LogicalGroup]] = defaultdict(list)
    for g in groups:
        children_by_parent[g.parent_group].append(g)
    groups_by_id = {g.id: g for g in groups}

    def _eval(node_id: str | None) -> bool:
        results = [evaluations[f.id].passed for f in filters_by_group.get(node_id, [])]
        results.extend(_eval(child.id) for child in children_by_parent.get(node_id, []))

        logic = LogicType.AND if node_id is None else groups_by_id[node_id].logic
        if not results:
            return logic == LogicType.AND  # vacuous: AND of nothing is True, OR of nothing is False
        return all(results) if logic == LogicType.AND else any(results)

    return _eval(None)
