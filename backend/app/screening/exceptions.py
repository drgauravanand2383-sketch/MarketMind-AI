"""Exception hierarchy for the Screening Engine's application layer.

Self-contained model constraints (unknown operator, invalid BETWEEN, empty
IN/NOT_IN, missing value, duplicate filter/group id, an unknown group
reference, a group-hierarchy cycle, an unknown `CompanyMetrics` field) are
enforced by `app.screening.models` itself and raise a plain
`pydantic.ValidationError` — see that module's docstring. This hierarchy
covers only what `ScreeningEngine` enforces: rules that need injected,
runtime-configurable state (a maximum filter count, duplicate profile
names) or that depend on existing repository state (not found).
"""

from __future__ import annotations

__all__ = [
    "ScreeningError",
    "ScreeningProfileNotFoundError",
    "DuplicateProfileNameError",
    "MaxFiltersExceededError",
]


class ScreeningError(Exception):
    """Base class for every error raised by the Screening Engine's application layer."""

    def __init__(self, message: str, *, profile_id: str | None = None) -> None:
        self.profile_id = profile_id
        super().__init__(message)


class ScreeningProfileNotFoundError(ScreeningError):
    """Raised when no screening profile exists for the given id."""

    def __init__(self, profile_id: str) -> None:
        super().__init__(f"No screening profile found with id {profile_id!r}.", profile_id=profile_id)


class DuplicateProfileNameError(ScreeningError):
    """Raised when creating/renaming/duplicating a profile to a name already in use.

    Only raised when `ScreeningEngine` was constructed with
    `enforce_unique_names=True` (the default) — see its docstring.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A screening profile named {name!r} already exists.")


class MaxFiltersExceededError(ScreeningError):
    """Raised when a profile's filter count would exceed the configured maximum."""

    def __init__(self, profile_id: str | None, limit: int, actual: int) -> None:
        self.limit = limit
        self.actual = actual
        super().__init__(
            f"Profile has {actual} filters, exceeding the configured maximum of {limit}.",
            profile_id=profile_id,
        )
