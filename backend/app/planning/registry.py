"""PlanRegistry: an in-memory store of `PlanTemplate`s, keyed by objective.

Mirrors the registration pattern already used by `PromptRegistry` and
`AgentOrchestrator`'s agent registry: register/get/list, duplicates
rejected. No globals, no singleton — every `PlanRegistry` instance is
independent and must be constructed and injected by its caller.
"""

from __future__ import annotations

from app.planning.exceptions import PlanTemplateAlreadyRegisteredError, UnknownObjectiveError
from app.planning.models import PlanTemplate

__all__ = ["PlanRegistry"]


class PlanRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, PlanTemplate] = {}

    def register(self, template: PlanTemplate) -> None:
        """Register `template` under its own `objective`.

        Raises:
            PlanTemplateAlreadyRegisteredError: a template is already
                registered for this objective.
        """
        if template.objective in self._templates:
            raise PlanTemplateAlreadyRegisteredError(template.objective)
        self._templates[template.objective] = template

    def get(self, objective: str) -> PlanTemplate:
        """Return the template registered for `objective`.

        Raises:
            UnknownObjectiveError: no template is registered for this objective.
        """
        try:
            return self._templates[objective]
        except KeyError:
            raise UnknownObjectiveError(objective) from None

    def list_objectives(self) -> tuple[str, ...]:
        """Every registered objective, sorted."""
        return tuple(sorted(self._templates))
