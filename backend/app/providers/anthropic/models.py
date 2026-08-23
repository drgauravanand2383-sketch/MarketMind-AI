"""Typed request/response models for AnthropicProvider.

No raw Anthropic SDK object (`anthropic.types.Message`, content blocks,
etc.) ever leaves this package — `MessageResponse` is this provider's own,
independent shape. `AnthropicProviderConfig` is a plain, already-resolved
configuration object; the provider itself never reads an environment
variable or touches `ConfigurationService` directly — `from_settings()` is
the one sanctioned bridge from `app.config.models.AnthropicSettings`
(which does the env/`.env` loading) to this config.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.config.models import AnthropicSettings

__all__ = [
    "ConversationRole",
    "ConversationMessage",
    "MessageRequest",
    "TokenUsage",
    "MessageResponse",
    "AnthropicProviderConfig",
]


class ConversationRole(StrEnum):
    """A single conversation turn's speaker, matching Anthropic's Messages API roles."""

    USER = "user"
    ASSISTANT = "assistant"


class ConversationMessage(BaseModel):
    """One turn of prior conversation history, supplied by the caller."""

    model_config = ConfigDict(extra="forbid")

    role: ConversationRole
    content: str = Field(min_length=1)


class MessageRequest(BaseModel):
    """A request to `AnthropicProvider.create_message()`.

    `max_tokens`/`temperature` are optional per-request overrides — when
    omitted, the provider falls back to its own configured defaults
    (`AnthropicProviderConfig.max_tokens`/`.temperature`) instead.
    `conversation_history` precedes `user_prompt` as prior turns; the
    provider appends `user_prompt` itself as the final user turn.
    """

    model_config = ConfigDict(extra="forbid")

    system_prompt: str | None = None
    user_prompt: str = Field(min_length=1)
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    max_tokens: int | None = Field(default=None, gt=0)
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)


class TokenUsage(BaseModel):
    """Token accounting for one completed request."""

    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class MessageResponse(BaseModel):
    """The output of `AnthropicProvider.create_message()`. No raw SDK object.

    `content` concatenates every text block in the SDK response. The
    Messages API can also return non-text content blocks (e.g. tool use);
    those are out of scope here — this sprint supports plain text messages
    only ("No workflow logic. No reasoning logic.").
    """

    model_config = ConfigDict(extra="forbid")

    content: str
    usage: TokenUsage
    model: str
    stop_reason: str | None


class AnthropicProviderConfig(BaseModel):
    """AnthropicProvider's own, already-resolved configuration.

    A plain `BaseModel`, not a `pydantic_settings.BaseSettings` — the
    provider never reads environment variables or `.env` itself. Use
    `from_settings()` to build one from `ConfigurationService.anthropic`
    (`app.config.models.AnthropicSettings`), which performs the actual env
    loading; this class only holds the resolved values.
    """

    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr
    model: str
    max_tokens: int = Field(gt=0)
    temperature: float = Field(ge=0.0, le=1.0)
    timeout: float = Field(gt=0)

    @classmethod
    def from_settings(cls, settings: AnthropicSettings) -> AnthropicProviderConfig:
        """Build from `ConfigurationService.anthropic` — the sanctioned source of these values."""
        return cls(
            api_key=settings.api_key,
            model=settings.model,
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
            timeout=settings.timeout,
        )
