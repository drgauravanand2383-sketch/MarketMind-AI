"""Typed request/response/metadata models for the Prompt Template Framework.

`PromptTemplate` itself lives in `template.py` (its own dedicated module,
alongside the placeholder-validation logic that defines it) — this module
holds the request/response/metadata shapes used across the framework:
`PromptRenderRequest`, `PromptRenderResult`, `PromptMetadata`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["PromptRenderRequest", "PromptRenderResult", "PromptMetadata"]


class PromptRenderRequest(BaseModel):
    """A request to `PromptRenderer.render()`.

    `version` is optional: omitted (`None`) means "the latest registered
    version of this template_id" (see `PromptRegistry.get()`).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str = Field(min_length=1)
    version: int | None = Field(default=None, ge=1)
    variables: dict[str, Any] = Field(default_factory=dict)


class PromptRenderResult(BaseModel):
    """The output of `PromptRenderer.render()` / `render_template()`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str
    version: int
    system_prompt: str
    user_prompt: str
    variables_used: tuple[str, ...] = Field(default_factory=tuple)


class PromptMetadata(BaseModel):
    """A lightweight, content-free summary of one `PromptTemplate`.

    What `PromptRegistry.list_templates()` returns, and what
    `PromptTemplate.metadata` exposes for a single template — never
    includes the actual `system_prompt`/`user_prompt` text.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str
    name: str
    version: int
    description: str
    required_variables: tuple[str, ...] = Field(default_factory=tuple)
