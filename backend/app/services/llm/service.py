"""LLMService — the single entry point every AI-powered agent uses to generate completions.

LLMService hides provider-specific implementations (`AnthropicProvider`
today, additional `BaseLLMProvider` implementations later) behind one
interface. It receives typed requests, selects the provider configured via
`ConfigurationService`, invokes it through `BaseLLMProvider`'s interface
only (never a concrete provider class, never an SDK), and returns typed
responses. No reasoning, no prompt engineering, and no workflow logic is
implemented here — this is a pure service-layer translation and dispatch
boundary.

`BaseLLMProvider`/`MessageRequest`/`MessageResponse` currently live in
`app.providers.anthropic` (Sprint 36 built the first, and so far only, LLM
provider there, with no shared `app/providers/llm/` package yet to hold a
provider-agnostic home for them). This sprint is scoped to
`app/services/llm/` only, so that location is used as-is rather than
relocated — a future sprint adding a second provider is the natural time
to move it.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.config.service import ConfigurationService
from app.providers.anthropic.models import ConversationMessage as ProviderConversationMessage
from app.providers.anthropic.models import ConversationRole as ProviderConversationRole
from app.providers.anthropic.models import MessageRequest, MessageResponse
from app.providers.anthropic.provider import BaseLLMProvider
from app.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.services.llm.models import LLMHealthStatus, LLMRequest, LLMResponse, TokenUsage

__all__ = [
    "LLMServiceError",
    "LLMConfigurationError",
    "LLMProviderUnavailableError",
    "LLMTimeoutError",
    "LLMAuthenticationError",
    "LLMRateLimitError",
    "LLMService",
]


class LLMServiceError(Exception):
    """Base class for all LLM Service errors. Never a raw SDK or provider exception."""

    def __init__(self, message: str, *, provider: str | None = None) -> None:
        self.provider = provider
        super().__init__(message)


class LLMConfigurationError(LLMServiceError):
    """Raised when the LLM Service itself is misconfigured.

    Covers both: the configured provider id isn't registered in this
    service's provider mapping ("missing provider"), and a provider
    reporting its own configuration is invalid
    (`app.providers.exceptions.ProviderConfigurationError`).
    """


class LLMProviderUnavailableError(LLMServiceError):
    """Raised when the selected provider cannot be reached or returns an unusable response."""


class LLMTimeoutError(LLMServiceError):
    """Raised when the selected provider's request exceeds its timeout."""


class LLMAuthenticationError(LLMServiceError):
    """Raised when the selected provider fails to authenticate."""


class LLMRateLimitError(LLMServiceError):
    """Raised when the selected provider is rate-limited."""


class LLMService:
    """Typed entry point for generating LLM completions.

    No reasoning, no prompt engineering, no workflow logic — only request
    validation, provider selection, dispatch, and response translation.
    No singleton: construct one instance and inject it wherever an agent
    needs LLM access.
    """

    def __init__(
        self,
        providers: Mapping[str, BaseLLMProvider],
        configuration: ConfigurationService,
    ) -> None:
        """Initialize with every available provider and the configuration that selects one.

        Args:
            providers: Every `BaseLLMProvider` implementation available to
                this service, keyed by provider id (e.g. `"anthropic"`).
                `LLMService` never constructs a provider itself — every
                entry arrives fully formed via dependency injection.
            configuration: Supplies `configuration.llm.provider` — the id
                selecting which entry in `providers` this service uses.
                Provider selection is entirely config-driven; nothing here
                or in any caller hardcodes which provider is used.

        Raises:
            LLMConfigurationError: If the configured provider id isn't a
                key in `providers` — checked eagerly here (fail fast), so
                a misconfiguration is caught at wiring time rather than on
                the first `generate()` call.
        """
        self._providers = dict(providers)
        self._configuration = configuration
        self._provider_id = configuration.llm.provider

        provider = self._providers.get(self._provider_id)
        if provider is None:
            raise LLMConfigurationError(
                f"No provider registered for configured provider id {self._provider_id!r}; "
                f"available: {sorted(self._providers)}",
                provider=self._provider_id,
            )
        self._provider: BaseLLMProvider = provider

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate one completion via the configured provider.

        `request` is already validated by the time this is called —
        `LLMRequest`'s own fields (non-empty `user_prompt`, positive
        `max_tokens`, in-range `temperature`) are pydantic-enforced at
        construction, before `generate()` ever sees it.

        Raises:
            LLMTimeoutError: The provider's request timed out.
            LLMAuthenticationError: The provider failed to authenticate.
            LLMRateLimitError: The provider is rate-limited.
            LLMConfigurationError: The provider itself is misconfigured.
            LLMProviderUnavailableError: The provider could not be reached,
                or returned an unusable response.
            LLMServiceError: Any other provider failure — never a raw SDK
                or `app.providers.exceptions.ProviderError` instance.
        """
        provider_request = self._to_provider_request(request)

        try:
            provider_response = await self._provider.create_message(provider_request)
        except ProviderTimeoutError as exc:
            raise LLMTimeoutError(str(exc), provider=self._provider_id) from exc
        except ProviderAuthenticationError as exc:
            raise LLMAuthenticationError(str(exc), provider=self._provider_id) from exc
        except ProviderRateLimitError as exc:
            raise LLMRateLimitError(str(exc), provider=self._provider_id) from exc
        except ProviderConfigurationError as exc:
            raise LLMConfigurationError(str(exc), provider=self._provider_id) from exc
        except (ProviderConnectionError, ProviderResponseError) as exc:
            raise LLMProviderUnavailableError(str(exc), provider=self._provider_id) from exc
        except ProviderError as exc:
            raise LLMServiceError(str(exc), provider=self._provider_id) from exc
        except Exception as exc:  # noqa: BLE001 - never leak an unexpected exception either
            raise LLMServiceError(str(exc), provider=self._provider_id) from exc

        return self._to_llm_response(provider_response)

    async def health_check(self) -> LLMHealthStatus:
        """Report the configured provider, its availability, model, and readiness.

        Delegates availability to the provider's own `health_check()` —
        for `AnthropicProvider` that makes no real API request (Sprint 36),
        and `LLMService` adds none of its own either.
        """
        available = await self._provider.health_check()
        model = self._resolve_model() if available else None
        return LLMHealthStatus(
            provider=self._provider_id,
            available=available,
            model=model,
            ready=available,
        )

    def _resolve_model(self) -> str | None:
        """Best-effort model name for health reporting.

        `BaseLLMProvider`'s abstract contract only guarantees
        `create_message`/`health_check` ("only communicate through
        provider interfaces") — it does not guarantee a `.config.model`
        attribute. This reads it defensively so a future provider lacking
        one degrades to `None` instead of raising.
        """
        config = getattr(self._provider, "config", None)
        return getattr(config, "model", None)

    def _to_provider_request(self, request: LLMRequest) -> MessageRequest:
        """Translate LLMService's own request shape into BaseLLMProvider's."""
        return MessageRequest(
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            conversation_history=[
                ProviderConversationMessage(
                    role=ProviderConversationRole(turn.role.value), content=turn.content
                )
                for turn in request.conversation_history
            ],
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )

    def _to_llm_response(self, response: MessageResponse) -> LLMResponse:
        """Translate BaseLLMProvider's response shape into LLMService's own."""
        return LLMResponse(
            content=response.content,
            usage=TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
            provider=self._provider_id,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )
