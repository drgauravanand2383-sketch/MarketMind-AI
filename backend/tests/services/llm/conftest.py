"""Shared doubles and factories for LLMService tests.

Every provider used here is a hand-written `FakeLLMProvider` test double —
no real `AnthropicProvider`, no Anthropic SDK, and no network call is ever
involved in this package.
"""

from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr

from app.config.models import AnthropicSettings, AppConfig, LLMSettings
from app.config.service import ConfigurationService
from app.providers.anthropic.models import MessageRequest, MessageResponse, TokenUsage
from app.providers.anthropic.provider import BaseLLMProvider


class FakeLLMProvider(BaseLLMProvider):
    """A BaseLLMProvider test double with full call control.

    Records every request it receives; returns a fixed `MessageResponse`
    (or raises a fixed exception, simulating a provider that has already
    exhausted its own internal retries — see the "retry propagation"
    tests, which check LLMService doesn't add a second retry layer).
    """

    def __init__(
        self,
        model: str = "fake-model",
        response: MessageResponse | None = None,
        error: Exception | None = None,
        healthy: bool = True,
        expose_config: bool = True,
    ) -> None:
        self._model = model
        self._response = response
        self._error = error
        self._healthy = healthy
        self._expose_config = expose_config
        self.calls: list[MessageRequest] = []

    @property
    def config(self) -> object:
        # SimpleNamespace, not AnthropicProviderConfig — demonstrates
        # LLMService only relies on duck-typed `.config.model`, per
        # BaseLLMProvider's actual (narrower) abstract contract.
        return SimpleNamespace(model=self._model)

    async def create_message(self, request: MessageRequest) -> MessageResponse:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return self._response or MessageResponse(
            content="ok",
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            model=self._model,
            stop_reason="end_turn",
        )

    async def health_check(self) -> bool:
        return self._healthy


class ConfiglessLLMProvider(BaseLLMProvider):
    """A minimal BaseLLMProvider with no `.config` attribute at all —
    exercises `LLMService._resolve_model()`'s defensive fallback to None."""

    async def create_message(self, request: MessageRequest) -> MessageResponse:
        return MessageResponse(
            content="ok",
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            model="configless-model",
            stop_reason="end_turn",
        )

    async def health_check(self) -> bool:
        return True


def configuration_service(provider: str = "anthropic") -> ConfigurationService:
    return ConfigurationService(
        AppConfig(
            anthropic=AnthropicSettings(_env_file=None, api_key=SecretStr("sk-test-key")),
            llm=LLMSettings(_env_file=None, provider=provider),
        )
    )
