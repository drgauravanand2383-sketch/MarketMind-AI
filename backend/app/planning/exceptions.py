"""Exception hierarchy for the Agent Planning Engine.

Mirrors the established codebase pattern (see `app.orchestrator.exceptions`,
`app.prompts.exceptions`): a single base carrying an optional identifying
field, with concrete subclasses for each distinct failure mode.
"""

from __future__ import annotations

__all__ = [
    "PlanningError",
    "PlanTemplateAlreadyRegisteredError",
    "UnknownObjectiveError",
    "InvalidPlanError",
]


class PlanningError(Exception):
    """Base class for every error raised by the Planning Engine."""

    def __init__(self, message: str, *, objective: str | None = None) -> None:
        self.objective = objective
        super().__init__(message)


class PlanTemplateAlreadyRegisteredError(PlanningError):
    """Raised when a `PlanTemplate` is registered for an objective that already has one."""

    def __init__(self, objective: str) -> None:
        super().__init__(
            f"A plan template is already registered for objective {objective!r}.",
            objective=objective,
        )


class UnknownObjectiveError(PlanningError):
    """Raised when no `PlanTemplate` is registered for the requested (or referenced) objective."""

    def __init__(self, objective: str) -> None:
        super().__init__(
            f"No plan template registered for objective {objective!r}.",
            objective=objective,
        )


class InvalidPlanError(PlanningError):
    """Raised for a structurally invalid plan: a duplicate step id, a
    dependency on a missing step, or a dependency cycle — whether detected
    within a single template's own steps or in the fully expanded plan."""
