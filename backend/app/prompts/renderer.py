"""PromptRenderer — substitutes variables into a PromptTemplate. No AI calls, no reasoning.

PromptRenderer performs pure string substitution only: given a
PromptTemplate (resolved directly, or looked up from an injected
PromptRegistry by template_id), it validates every required variable is
supplied and substitutes them into `system_prompt`/`user_prompt`. It never
calls an LLM, never reasons about content, and never decides which
template to use — that decision is expressed only as a `template_id` by
whatever calls `render()` (a future agent), which never needs to know how
templates are stored.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.prompts.exceptions import MissingVariablesError
from app.prompts.models import PromptRenderRequest, PromptRenderResult
from app.prompts.registry import PromptRegistry
from app.prompts.template import PromptTemplate

__all__ = ["PromptRenderer"]


class PromptRenderer:
    """Renders PromptTemplates into PromptRenderResults.

    No singleton: construct one instance per injected PromptRegistry and
    pass it wherever rendering is needed.
    """

    def __init__(self, registry: PromptRegistry) -> None:
        """Initialize with the registry to resolve `template_id`s through.

        Args:
            registry: Supplies templates for `render(template_id=...)`.
                Never constructed here — injected, per Dependency Injection.
        """
        self._registry = registry

    def render(
        self,
        template_id: str,
        variables: Mapping[str, Any] | None = None,
        version: int | None = None,
    ) -> PromptRenderResult:
        """Resolve `template_id` (optionally a specific `version`) via the
        injected registry, then render it with `variables`.

        This is the shape a future agent calls:
        `renderer.render(template_id="company_research", variables={...})`
        — it never needs to know how or where templates are stored.

        Raises:
            TemplateNotFoundError: `template_id`/`version` isn't registered.
            MissingVariablesError: `variables` doesn't cover every
                required variable.
        """
        request = PromptRenderRequest(
            template_id=template_id, version=version, variables=dict(variables or {})
        )
        template = self._registry.get(request.template_id, request.version)
        return self.render_template(template, request.variables)

    def render_template(
        self, template: PromptTemplate, variables: Mapping[str, Any]
    ) -> PromptRenderResult:
        """Render an already-resolved PromptTemplate directly, bypassing the registry.

        Raises:
            MissingVariablesError: If `variables` doesn't supply every
                name in `template.required_variables`. Extra, unused
                variables in `variables` are never an error — they're
                simply not referenced by the rendered output.
        """
        required = template.required_variables
        missing = required - variables.keys()
        if missing:
            raise MissingVariablesError(template.template_id, missing)

        return PromptRenderResult(
            template_id=template.template_id,
            version=template.version,
            system_prompt=template.system_prompt.format_map(variables),
            user_prompt=template.user_prompt.format_map(variables),
            variables_used=tuple(sorted(required)),
        )
