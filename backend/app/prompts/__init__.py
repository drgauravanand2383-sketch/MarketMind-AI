"""Prompt Template Framework — the single source of truth for every prompt
used by AI-powered agents.

`PromptTemplate` (template.py) is a pure, versioned, immutable prompt
definition. `PromptRegistry` (registry.py) owns explicitly-registered
templates, keyed by (template_id, version) — no filesystem scanning.
`PromptRenderer` (renderer.py) substitutes variables into a template and
returns a typed `PromptRenderResult` — pure string rendering only: no AI
calls, no reasoning, no workflow logic.

This sprint introduces the framework itself, with no concrete templates
registered — see `app/prompts/templates/` for where a future sprint's
template definitions belong.
"""

from app.prompts.exceptions import (
    MissingVariablesError,
    PromptError,
    TemplateAlreadyRegisteredError,
    TemplateNotFoundError,
    TemplateValidationError,
)
from app.prompts.models import PromptMetadata, PromptRenderRequest, PromptRenderResult
from app.prompts.registry import PromptRegistry
from app.prompts.renderer import PromptRenderer
from app.prompts.template import PromptTemplate

__all__ = [
    "PromptTemplate",
    "PromptRenderRequest",
    "PromptRenderResult",
    "PromptMetadata",
    "PromptRegistry",
    "PromptRenderer",
    "PromptError",
    "TemplateValidationError",
    "TemplateAlreadyRegisteredError",
    "TemplateNotFoundError",
    "MissingVariablesError",
]
