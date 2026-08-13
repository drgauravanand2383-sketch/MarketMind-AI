"""Exception hierarchy for the Guardrails Framework.

All framework errors derive from `GuardrailError`. Note: `ValidationError`
here is this framework's own type, distinct from `pydantic.ValidationError`
— import one or both with an alias if a module needs both (this
framework's own `validator.py` does exactly that internally).

None of these are raised for ordinary malformed LLM output — that's
reported through `GuardrailResult.validation_errors` (typed
`ValidationIssue` objects), not exceptions. They're only raised when a
caller explicitly opts into "strict" mode (see `OutputValidator`), or
(for `RepairError`) when the repair step itself fails unexpectedly.
"""

from __future__ import annotations

__all__ = ["GuardrailError", "ParsingError", "ValidationError", "RepairError"]


class GuardrailError(Exception):
    """Base class for all Guardrails Framework errors."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        self.field = field
        super().__init__(message)


class ParsingError(GuardrailError):
    """Raised (only in strict mode) when raw text cannot be parsed as JSON, even after repair."""


class ValidationError(GuardrailError):
    """Raised (only in strict mode) when parsed data fails schema validation."""


class RepairError(GuardrailError):
    """Raised when the repair step itself fails unexpectedly (e.g. non-string input).

    Never raised for ordinary malformed LLM output — repair simply leaves
    that as-is and lets parsing/validation report it normally.
    """
