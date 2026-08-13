"""Exception hierarchy for the Prompt Template Framework.

All framework errors derive from `PromptError`, giving calling code a
single type to catch broadly while still allowing specific handling for
template validation, registration, lookup, and rendering failures.
"""

from __future__ import annotations

__all__ = [
    "PromptError",
    "TemplateValidationError",
    "TemplateAlreadyRegisteredError",
    "TemplateNotFoundError",
    "MissingVariablesError",
]


class PromptError(Exception):
    """Base class for all Prompt Template Framework errors."""

    def __init__(self, message: str, *, template_id: str | None = None) -> None:
        self.template_id = template_id
        super().__init__(message)


class TemplateValidationError(PromptError):
    """Raised when a `PromptTemplate`'s own definition is invalid.

    E.g. an unsupported placeholder shape — only simple named variables
    like `{variable_name}` are supported (see `app.prompts.template`).
    """


class TemplateAlreadyRegisteredError(PromptError):
    """Raised when registering a (template_id, version) pair that's already registered."""

    def __init__(self, template_id: str, version: int) -> None:
        self.version = version
        super().__init__(
            f"Template {template_id!r} version {version} is already registered",
            template_id=template_id,
        )


class TemplateNotFoundError(PromptError):
    """Raised when retrieving an unknown template_id, or an unknown version of a known one."""

    def __init__(self, template_id: str, version: int | None = None) -> None:
        self.version = version
        message = (
            f"No template registered under id {template_id!r}"
            if version is None
            else f"Template {template_id!r} has no registered version {version}"
        )
        super().__init__(message, template_id=template_id)


class MissingVariablesError(PromptError):
    """Raised when rendering without all of a template's required variables."""

    def __init__(self, template_id: str, missing: frozenset[str] | set[str]) -> None:
        self.missing_variables = frozenset(missing)
        super().__init__(
            f"Template {template_id!r} is missing required variables: {sorted(missing)}",
            template_id=template_id,
        )
