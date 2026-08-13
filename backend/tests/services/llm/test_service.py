"""Tests for LLMService (app.services.llm.service).

Every provider is a hand-written FakeLLMProvider double (see conftest.py)
— no real AnthropicProvider, SDK, or network call anywhere in this file.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.providers.anthropic.models import MessageResponse, TokenUsage
from app.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.services.llm.models import ConversationMessage, ConversationRole, LLMRequest
from app.services.llm.service import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMService,
    LLMServiceError,
    LLMTimeoutError,
)
from tests.services.llm.conftest import ConfiglessLLMProvider, FakeLLMProvider, configuration_service

# --- Successful generation -----------------------------------------------------------


async def test_successful_generation_returns_typed_response() -> None:
    provider = FakeLLMProvider(
        model="fake-model",
        response=MessageResponse(
            content="Hello back!",
            usage=TokenUsage(input_tokens=7, output_tokens=3),
            model="fake-model",
            stop_reason="end_turn",
        ),
    )
    service = LLMService({"anthropic": provider}, configuration_service())

    response = await service.generate(LLMRequest(user_prompt="Hello"))

    assert response.content == "Hello back!"
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 3
    assert response.input_tokens == 7
    assert response.output_tokens == 3
    assert response.model == "fake-model"
    assert response.provider == "anthropic"
    assert response.stop_reason == "end_turn"


async def test_generate_translates_request_into_provider_request() -> None:
    provider = FakeLLMProvider()
    service = LLMService({"anthropic": provider}, configuration_service())

    await service.generate(
        LLMRequest(
            system_prompt="Be concise.",
            user_prompt="What is 2+2?",
            conversation_history=[
                ConversationMessage(role=ConversationRole.USER, content="Hi"),
                ConversationMessage(role=ConversationRole.ASSISTANT, content="Hello!"),
            ],
            temperature=0.2,
            max_tokens=100,
        )
    )

    assert len(provider.calls) == 1
    provider_request = provider.calls[0]
    assert provider_request.system_prompt == "Be concise."
    assert provider_request.user_prompt == "What is 2+2?"
    assert len(provider_request.conversation_history) == 2
    assert provider_request.temperature == 0.2
    assert provider_request.max_tokens == 100


# --- Invalid request -----------------------------------------------------------


def test_empty_user_prompt_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(user_prompt="")


def test_invalid_max_tokens_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(user_prompt="hi", max_tokens=0)


def test_invalid_temperature_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(user_prompt="hi", temperature=1.5)


def test_unknown_field_on_request_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(user_prompt="hi", unexpected_field="x")


# --- Provider unavailable -----------------------------------------------------------


async def test_provider_connection_error_raises_provider_unavailable() -> None:
    provider = FakeLLMProvider(error=ProviderConnectionError("connection failed", provider_id="anthropic"))
    service = LLMService({"anthropic": provider}, configuration_service())

    with pytest.raises(LLMProviderUnavailableError):
        await service.generate(LLMRequest(user_prompt="Hello"))


async def test_provider_response_error_raises_provider_unavailable() -> None:
    provider = FakeLLMProvider(error=ProviderResponseError("malformed", provider_id="anthropic"))
    service = LLMService({"anthropic": provider}, configuration_service())

    with pytest.raises(LLMProviderUnavailableError):
        await service.generate(LLMRequest(user_prompt="Hello"))


# --- Timeout -----------------------------------------------------------


async def test_provider_timeout_raises_llm_timeout_error() -> None:
    provider = FakeLLMProvider(error=ProviderTimeoutError("timed out", provider_id="anthropic"))
    service = LLMService({"anthropic": provider}, configuration_service())

    with pytest.raises(LLMTimeoutError):
        await service.generate(LLMRequest(user_prompt="Hello"))


# --- Authentication failure -----------------------------------------------------------


async def test_provider_authentication_failure_raises_llm_authentication_error() -> None:
    provider = FakeLLMProvider(
        error=ProviderAuthenticationError("bad api key", provider_id="anthropic")
    )
    service = LLMService({"anthropic": provider}, configuration_service())

    with pytest.raises(LLMAuthenticationError):
        await service.generate(LLMRequest(user_prompt="Hello"))


# --- Rate limiting -----------------------------------------------------------


async def test_provider_rate_limit_raises_llm_rate_limit_error() -> None:
    provider = FakeLLMProvider(error=ProviderRateLimitError("rate limited", provider_id="anthropic"))
    service = LLMService({"anthropic": provider}, configuration_service())

    with pytest.raises(LLMRateLimitError):
        await service.generate(LLMRequest(user_prompt="Hello"))


# --- Configuration errors -----------------------------------------------------------


async def test_provider_configuration_error_raises_llm_configuration_error() -> None:
    provider = FakeLLMProvider(
        error=ProviderConfigurationError("bad provider config", provider_id="anthropic")
    )
    service = LLMService({"anthropic": provider}, configuration_service())

    with pytest.raises(LLMConfigurationError):
        await service.generate(LLMRequest(user_prompt="Hello"))


async def test_unexpected_exception_is_wrapped_not_leaked() -> None:
    provider = FakeLLMProvider(error=RuntimeError("something broke"))
    service = LLMService({"anthropic": provider}, configuration_service())

    with pytest.raises(LLMServiceError) as excinfo:
        await service.generate(LLMRequest(user_prompt="Hello"))

    assert not isinstance(excinfo.value, RuntimeError)


# --- Retry propagation -----------------------------------------------------------


async def test_a_persistently_failing_provider_is_called_exactly_once() -> None:
    """LLMService never adds its own retry layer on top of the provider's
    (AnthropicProvider already retries transient failures internally,
    Sprint 36) — a failure the provider ultimately raises propagates
    straight through, with the provider called exactly once from
    LLMService's perspective."""
    provider = FakeLLMProvider(error=ProviderTimeoutError("timed out", provider_id="anthropic"))
    service = LLMService({"anthropic": provider}, configuration_service())

    with pytest.raises(LLMTimeoutError):
        await service.generate(LLMRequest(user_prompt="Hello"))

    assert len(provider.calls) == 1


async def test_a_provider_that_recovers_before_returning_still_succeeds() -> None:
    """Simulates a provider whose own internal retry already recovered —
    LLMService just returns whatever it gets, unaware any retry happened."""
    provider = FakeLLMProvider(
        response=MessageResponse(
            content="recovered",
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            model="fake-model",
            stop_reason="end_turn",
        )
    )
    service = LLMService({"anthropic": provider}, configuration_service())

    response = await service.generate(LLMRequest(user_prompt="Hello"))

    assert response.content == "recovered"


# --- Provider selection -----------------------------------------------------------


def test_llm_service_selects_the_configured_provider() -> None:
    anthropic_provider = FakeLLMProvider(model="anthropic-model")
    other_provider = FakeLLMProvider(model="other-model")
    service = LLMService(
        {"anthropic": anthropic_provider, "other": other_provider},
        configuration_service(provider="other"),
    )

    assert service._provider is other_provider


def test_missing_configured_provider_raises_at_construction() -> None:
    with pytest.raises(LLMConfigurationError):
        LLMService({"anthropic": FakeLLMProvider()}, configuration_service(provider="openai"))


def test_no_hardcoded_provider_selection_is_needed_by_callers() -> None:
    """A caller never names a provider anywhere — only ConfigurationService does."""
    provider = FakeLLMProvider()
    service = LLMService({"anthropic": provider}, configuration_service(provider="anthropic"))

    assert service._provider_id == "anthropic"


# --- Health check -----------------------------------------------------------


async def test_health_check_when_provider_available() -> None:
    provider = FakeLLMProvider(model="fake-model", healthy=True)
    service = LLMService({"anthropic": provider}, configuration_service())

    status = await service.health_check()

    assert status.provider == "anthropic"
    assert status.available is True
    assert status.model == "fake-model"
    assert status.ready is True


async def test_health_check_when_provider_unavailable() -> None:
    provider = FakeLLMProvider(healthy=False)
    service = LLMService({"anthropic": provider}, configuration_service())

    status = await service.health_check()

    assert status.available is False
    assert status.model is None
    assert status.ready is False


async def test_health_check_does_not_call_create_message() -> None:
    provider = FakeLLMProvider()
    service = LLMService({"anthropic": provider}, configuration_service())

    await service.health_check()

    assert provider.calls == []


async def test_health_check_model_defaults_to_none_for_a_configless_provider() -> None:
    provider = ConfiglessLLMProvider()
    service = LLMService({"anthropic": provider}, configuration_service())

    status = await service.health_check()

    assert status.available is True
    assert status.model is None


# --- Dependency injection / no singleton -----------------------------------------------------------


def test_two_services_constructed_independently_do_not_share_state() -> None:
    service_a = LLMService({"anthropic": FakeLLMProvider(model="a")}, configuration_service())
    service_b = LLMService({"anthropic": FakeLLMProvider(model="b")}, configuration_service())

    assert service_a is not service_b
    assert service_a._provider is not service_b._provider
