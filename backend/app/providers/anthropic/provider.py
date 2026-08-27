"""AnthropicProvider — the first production LLM provider for MarketMind AI.

AnthropicProvider calls the official Anthropic SDK's Messages API to
create messages and returns typed responses (models.py). It performs no
workflow logic and no reasoning of any kind — it is a thin, typed
translation layer between `MessageRequest`/`MessageResponse` and the
Anthropic SDK, nothing more.

BaseLLMProvider is defined here rather than in a shared `app/providers/llm/`
package: no LLM provider abstraction existed before this sprint, and this
sprint is explicitly scoped to touch only `app/providers/anthropic/`. A
future second LLM provider sprint may relocate it to a shared location;
until then this is the one and only implementation of it.

Retries: the Anthropic SDK has its own built-in retry mechanism, but it
retries at the HTTP-transport level — invisible to (and untestable through)
a mock of `client.messages.create()`. This provider therefore disables the
SDK's own retries (`max_retries=0` on the constructed client) and
implements one explicit, visible retry loop of its own around
`messages.create()`, retrying only the transient error categories
(timeout, rate limit, connection) and never the non-transient ones
(authentication failure, malformed/rejected response).

Error handling: every Anthropic SDK exception raised by `messages.create()`
is caught and converted into one of `app.providers.exceptions`' existing
provider-error types — no raw SDK exception, and no raw SDK response
object, ever leaves this module.
"""

from __future__ import annotations

import asyncio
import inspect
from abc import ABC, abstractmethod
from functools import cache
from typing import Any

import anthropic
from pydantic import ValidationError

from app.providers.anthropic.models import (
    AnthropicProviderConfig,
    MessageRequest,
    MessageResponse,
    TokenUsage,
)
from app.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)

__all__ = ["BaseLLMProvider", "AnthropicProvider"]

PROVIDER_ID = "anthropic"
PROVIDER_NAME = "Anthropic Claude"

_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_RETRY_BACKOFF_SECONDS = 1.0


@cache
def _create_message_accepts(param_name: str) -> bool:
    """Whether the installed Anthropic SDK's `AsyncMessages.create()` accepts `param_name`.

    The SDK has removed keyword parameters across major versions —
    `anthropic` 1.x dropped `temperature`/`top_p`/`top_k` from
    `messages.create()` entirely, so passing one raises a `TypeError` from
    the SDK call itself, before any request ever reaches the API. This
    introspects the real, installed signature (cached — it cannot change
    within a process) instead of assuming a fixed parameter list, so this
    provider stops blindly forwarding a parameter the installed SDK no
    longer declares, whatever version happens to be installed.
    """
    return param_name in inspect.signature(anthropic.resources.messages.messages.AsyncMessages.create).parameters


class BaseLLMProvider(ABC):
    """Abstract contract every LLM provider implementation must satisfy.

    Mirrors `BaseEmbeddingProvider`'s shape (app/providers/embedding/provider.py):
    a minimal abstract interface for calling an external AI API. No
    workflow logic, no reasoning, no orchestration belongs here or in any
    subclass — only message creation and typed response translation.
    """

    @abstractmethod
    async def create_message(self, request: MessageRequest) -> MessageResponse:
        """Send one message-creation request to the LLM and return a typed response.

        Raises:
            app.providers.exceptions.ProviderError (or a subclass): On any
                failure calling the underlying API — never a raw SDK
                exception.
        """
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether this provider is correctly configured and ready to use.

        Must not make a real API request.
        """
        raise NotImplementedError


class AnthropicProvider(BaseLLMProvider):
    """Calls Claude's Messages API. No workflow logic, no reasoning logic.

    No singleton, no global state: construct one instance per
    configuration and inject it wherever an LLM provider is needed.
    """

    def __init__(
        self,
        config: AnthropicProviderConfig,
        client: anthropic.AsyncAnthropic | None = None,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        retry_backoff_seconds: float = _DEFAULT_RETRY_BACKOFF_SECONDS,
    ) -> None:
        """Initialize with an already-resolved configuration.

        Args:
            config: This provider's configuration. Build one via
                `AnthropicProviderConfig.from_settings(configuration_service.anthropic)`.
            client: An already-constructed `anthropic.AsyncAnthropic` to
                use instead of building one from `config` — tests inject a
                mock here so no real SDK client (and no real network call)
                is ever created. When omitted, a real client is built from
                `config`, with the SDK's own retry mechanism disabled
                (`max_retries=0`) since this provider retries itself (see
                module docstring).
            max_attempts: Total attempts (including the first) for a
                transient failure before giving up. Not sourced from
                `ConfigurationService` — Sprint 36's required settings are
                exactly api_key/model/max_tokens/temperature/timeout; this
                is an implementation detail of this provider, not an
                external configuration knob.
            retry_backoff_seconds: Delay between retry attempts.
        """
        self._config = config
        self._client = (
            client
            if client is not None
            else anthropic.AsyncAnthropic(
                api_key=config.api_key.get_secret_value(),
                timeout=config.timeout,
                max_retries=0,
            )
        )
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds

    @property
    def config(self) -> AnthropicProviderConfig:
        """This provider's configuration."""
        return self._config

    async def create_message(self, request: MessageRequest) -> MessageResponse:
        """Create one message via Claude, retrying transient failures.

        Retries `ProviderTimeoutError`, `ProviderRateLimitError`, and
        `ProviderConnectionError` up to `max_attempts` times, with
        `retry_backoff_seconds` between attempts. `ProviderAuthenticationError`
        and `ProviderResponseError` are never retried — retrying an invalid
        API key or a malformed/rejected request would only fail identically.
        """
        last_error: ProviderError | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                return await self._create_message_once(request)
            except (ProviderTimeoutError, ProviderRateLimitError, ProviderConnectionError) as exc:
                last_error = exc
                if attempt < self._max_attempts:
                    await asyncio.sleep(self._retry_backoff_seconds)

        assert last_error is not None  # the loop above always sets it before exhausting attempts
        raise last_error

    async def health_check(self) -> bool:
        """Verify an API key is configured and the client exists. Makes no API request."""
        return bool(self._config.api_key.get_secret_value()) and self._client is not None

    async def _create_message_once(self, request: MessageRequest) -> MessageResponse:
        """One call to `messages.create()`: build the request, call, translate the result."""
        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": request.max_tokens if request.max_tokens is not None else self._config.max_tokens,
            "messages": self._build_messages(request),
        }
        if request.system_prompt is not None:
            kwargs["system"] = request.system_prompt

        # Only forward `temperature` when the installed SDK's `create()` still
        # declares it (see `_create_message_accepts`) — a removed parameter
        # must never be blindly passed through to the SDK call below.
        if _create_message_accepts("temperature"):
            kwargs["temperature"] = (
                request.temperature if request.temperature is not None else self._config.temperature
            )

        try:
            message = await self._client.messages.create(**kwargs)
        except anthropic.APITimeoutError as exc:
            raise ProviderTimeoutError(str(exc), provider_id=PROVIDER_ID) from exc
        except anthropic.AuthenticationError as exc:
            raise ProviderAuthenticationError(str(exc), provider_id=PROVIDER_ID) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderRateLimitError(str(exc), provider_id=PROVIDER_ID) from exc
        except anthropic.APIResponseValidationError as exc:
            raise ProviderResponseError(str(exc), provider_id=PROVIDER_ID) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderConnectionError(str(exc), provider_id=PROVIDER_ID) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderResponseError(str(exc), provider_id=PROVIDER_ID) from exc
        except anthropic.AnthropicError as exc:
            raise ProviderError(str(exc), provider_id=PROVIDER_ID) from exc

        return self._parse_response(message)

    def _build_messages(self, request: MessageRequest) -> list[dict[str, str]]:
        """Translate MessageRequest's typed history + prompt into the SDK's plain message dicts."""
        messages = [
            {"role": turn.role.value, "content": turn.content} for turn in request.conversation_history
        ]
        messages.append({"role": "user", "content": request.user_prompt})
        return messages

    def _parse_response(self, message: anthropic.types.Message) -> MessageResponse:
        """Translate the SDK's Message into this provider's own MessageResponse.

        Any failure extracting the expected shape (missing/renamed
        attribute, an unexpected content-block shape) is treated as a
        malformed response, not allowed to propagate as a raw AttributeError.
        """
        try:
            # `block.text` only runs after the `getattr(..., "type") == "text"`
            # guard, which is a real runtime discriminant over the SDK's own
            # 10+-member content-block union — but mypy cannot narrow a Union
            # from a `getattr` comparison the way it can from `isinstance`.
            # Already inside this method's own malformed-response handling
            # (see docstring): a genuinely wrong assumption here still raises
            # AttributeError, still caught below, never propagates raw.
            content = "".join(
                block.text  # type: ignore[union-attr]
                for block in message.content
                if getattr(block, "type", None) == "text"
            )
            return MessageResponse(
                content=content,
                usage=TokenUsage(
                    input_tokens=message.usage.input_tokens,
                    output_tokens=message.usage.output_tokens,
                ),
                model=message.model,
                stop_reason=message.stop_reason,
            )
        except (AttributeError, TypeError, ValidationError) as exc:
            raise ProviderResponseError(
                f"Malformed response from Anthropic API: {exc}", provider_id=PROVIDER_ID
            ) from exc
