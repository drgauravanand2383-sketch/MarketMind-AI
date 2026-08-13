"""Exception hierarchy for the Signal Detection Engine's application layer.

Self-contained model constraints (unknown operator, unknown field, invalid
BETWEEN, empty IN/NOT_IN, missing value, non-positive weight, invalid
priority, duplicate condition/group id, an unknown group reference, a
group-hierarchy cycle) are enforced by `app.signals.models` itself and
raise a plain `pydantic.ValidationError` — see that module's docstring.
This hierarchy covers only what `SignalDetectionService` enforces: rules
that need injected, runtime-configurable state (a maximum condition count,
duplicate signal names) or that depend on existing repository state (not
found).
"""

from __future__ import annotations

__all__ = [
    "SignalError",
    "SignalDefinitionNotFoundError",
    "DuplicateSignalNameError",
    "MaxConditionsExceededError",
]


class SignalError(Exception):
    """Base class for every error raised by the Signal Detection Engine's application layer."""

    def __init__(self, message: str, *, signal_id: str | None = None) -> None:
        self.signal_id = signal_id
        super().__init__(message)


class SignalDefinitionNotFoundError(SignalError):
    """Raised when no signal definition exists for the given id."""

    def __init__(self, signal_id: str) -> None:
        super().__init__(f"No signal definition found with id {signal_id!r}.", signal_id=signal_id)


class DuplicateSignalNameError(SignalError):
    """Raised when creating/renaming/duplicating a definition to a name already in use.

    Only raised when `SignalDetectionService` was constructed with
    `enforce_unique_names=True` (the default).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A signal definition named {name!r} already exists.")


class MaxConditionsExceededError(SignalError):
    """Raised when a definition's condition count would exceed the configured maximum."""

    def __init__(self, signal_id: str | None, limit: int, actual: int) -> None:
        self.limit = limit
        self.actual = actual
        super().__init__(
            f"Signal definition has {actual} conditions, exceeding the configured maximum of {limit}.",
            signal_id=signal_id,
        )
