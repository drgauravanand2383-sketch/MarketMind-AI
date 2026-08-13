"""Typed request/response models for LLMService.

`LLMRequest`/`LLMResponse` are LLMService's own shapes — independent of
any specific provider's request/response types
(`app.providers.anthropic.models.MessageRequest`/`MessageResponse`) and
independent of any SDK model. `LLMService` (service.py) translates
between the two internally; callers of `LLMService` never see a
provider-specific or SDK type.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ConversationRole",
    "ConversationMessage",
    "LLMRequest",
    "TokenUsage",
    "LLMResponse",
    "LLMHealthStatus",
]


class ConversationRole(str, Enum):
    """A single conversation turn's speaker."""

    USER = "user"
    ASSISTANT = "assistant"


class ConversationMessage(BaseModel):
    """One turn of prior conversation history, supplied by the caller."""

    model_config = ConfigDict(extra="forbid")

    role: ConversationRole
    content: str = Field(min_length=1)


class LLMRequest(BaseModel):
    """A request to `LLMService.generate()`.

    `temperature`/`max_tokens` are optional — when omitted, the selected
    provider's own configured defaults apply. `metadata` is caller-supplied
    context (e.g. a tracing id); `LLMService` neither inspects nor acts on
    it — carrying it through is not reasoning or prompt engineering, so
    it's intentionally out of scope for this service to interpret.
    """

    model_config = ConfigDict(extra="forbid")

    system_prompt: str | None = None
    user_prompt: str = Field(min_length=1)
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    """Token accounting for one completed request."""

    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class LLMResponse(BaseModel):
    """The output of `LLMService.generate()`. No SDK model, no provider-specific model.

    `input_tokens`/`output_tokens` intentionally duplicate `usage`'s own
    fields at the top level — both are explicitly required fields per this
    sprint's spec, so both are populated rather than picking one.
    """

    model_config = ConfigDict(extra="forbid")

    content: str
    usage: TokenUsage
    provider: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    stop_reason: str | None


class LLMHealthStatus(BaseModel):
    """`LLMService.health_check()`'s result."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    available: bool
    model: str | None
    ready: bool
