"""PromptRegistry — owns every registered PromptTemplate.

No filesystem scanning: templates are registered explicitly via
`register()`, never discovered by scanning `app/prompts/templates/` or
anywhere else. That directory exists as a home for template *definition*
modules a future caller imports and registers explicitly — this module
never imports from it itself.
"""

from __future__ import annotations

from app.prompts.exceptions import TemplateAlreadyRegisteredError, TemplateNotFoundError
from app.prompts.models import PromptMetadata
from app.prompts.template import PromptTemplate

__all__ = ["PromptRegistry"]


class PromptRegistry:
    """Owns registered PromptTemplate definitions, keyed by (template_id, version).

    No singleton: construct one instance and inject it wherever templates
    need to be registered or retrieved (e.g. into `PromptRenderer`).
    """

    def __init__(self) -> None:
        self._templates: dict[str, dict[int, PromptTemplate]] = {}

    def register(self, template: PromptTemplate) -> None:
        """Register `template` under `(template.template_id, template.version)`.

        Raises:
            TemplateAlreadyRegisteredError: If this exact (template_id,
                version) pair is already registered. A *different*
                version of an already-known template_id is always
                allowed — that's how multiple versions coexist.
        """
        versions = self._templates.setdefault(template.template_id, {})
        if template.version in versions:
            raise TemplateAlreadyRegisteredError(template.template_id, template.version)
        versions[template.version] = template

    def get(self, template_id: str, version: int | None = None) -> PromptTemplate:
        """Retrieve a template by id, optionally pinned to a specific version.

        Args:
            template_id: The template to retrieve.
            version: A specific version, or `None` (default) for the
                latest (highest-numbered) registered version.

        Raises:
            TemplateNotFoundError: If `template_id` isn't registered at
                all, or `version` isn't a registered version of it.
        """
        versions = self._templates.get(template_id)
        if not versions:
            raise TemplateNotFoundError(template_id)
        if version is None:
            return versions[max(versions)]
        template = versions.get(version)
        if template is None:
            raise TemplateNotFoundError(template_id, version)
        return template

    def list_versions(self, template_id: str) -> tuple[int, ...]:
        """List every registered version number of `template_id`, ascending.

        Raises:
            TemplateNotFoundError: If `template_id` isn't registered.
        """
        versions = self._templates.get(template_id)
        if not versions:
            raise TemplateNotFoundError(template_id)
        return tuple(sorted(versions))

    def list_templates(self) -> tuple[PromptMetadata, ...]:
        """List metadata for the latest version of every registered template_id, sorted by id."""
        return tuple(self.get(template_id).metadata for template_id in sorted(self._templates))
