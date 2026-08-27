"""Tests for AnthropicProvider (app.providers.anthropic.provider).

The Anthropic SDK client is always mocked — see conftest.py. No real
network call is made anywhere in this file.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.config.models import AnthropicSettings
from app.providers.anthropic.models import (
    AnthropicProviderConfig,
    ConversationMessage,
    ConversationRole,
    MessageRequest,
)
from app.providers.anthropic.provider import AnthropicProvider, BaseLLMProvider
from app.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from tests.providers.anthropic.conftest import (
    authentication_error,
    bad_request_error,
    mock_client,
    provider_config,
    rate_limit_error,
    sdk_message,
    timeout_error,
)

# --- BaseLLMProvider -----------------------------------------------------------


def test_base_llm_provider_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseLLMProvider()  # type: ignore[abstract]


# --- Successful request -----------------------------------------------------------


async def test_successful_request_returns_typed_response() -> None:
    client = mock_client()
    client.messages.create.return_value = sdk_message(
        text="Hi there!", input_tokens=12, output_tokens=8, stop_reason="end_turn"
    )
    provider = AnthropicProvider(provider_config(), client=client)

    response = await provider.create_message(MessageRequest(user_prompt="Hello"))

    assert response.content == "Hi there!"
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 8
    assert response.model == "claude-sonnet-5"
    assert response.stop_reason == "end_turn"


async def test_successful_request_calls_sdk_with_config_defaults() -> None:
    client = mock_client()
    client.messages.create.return_value = sdk_message()
    provider = AnthropicProvider(
        provider_config(model="claude-opus-5", max_tokens=2048, temperature=0.3), client=client
    )

    await provider.create_message(MessageRequest(user_prompt="Hello"))

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5"
    assert kwargs["max_tokens"] == 2048
    assert kwargs["temperature"] == 0.3
    assert kwargs["messages"] == [{"role": "user", "content": "Hello"}]
    assert "system" not in kwargs


async def test_request_level_max_tokens_and_temperature_override_config_defaults() -> None:
    client = mock_client()
    client.messages.create.return_value = sdk_message()
    provider = AnthropicProvider(provider_config(max_tokens=1024, temperature=1.0), client=client)

    await provider.create_message(
        MessageRequest(user_prompt="Hello", max_tokens=500, temperature=0.0)
    )

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["max_tokens"] == 500
    assert kwargs["temperature"] == 0.0


async def test_system_prompt_is_passed_through_when_provided() -> None:
    client = mock_client()
    client.messages.create.return_value = sdk_message()
    provider = AnthropicProvider(provider_config(), client=client)

    await provider.create_message(
        MessageRequest(system_prompt="You are a helpful assistant.", user_prompt="Hello")
    )

    assert client.messages.create.call_args.kwargs["system"] == "You are a helpful assistant."


# --- SDK parameter compatibility (temperature removed on anthropic 1.x) --------------------


def test_create_message_accepts_reflects_the_installed_sdk_signature() -> None:
    """Direct unit test of the introspection helper against the real,
    installed `anthropic` SDK (not a mock) — proves it actually reflects
    the installed signature rather than a hardcoded parameter list."""
    from app.providers.anthropic.provider import _create_message_accepts

    assert _create_message_accepts("temperature") is True
    assert _create_message_accepts("model") is True
    assert _create_message_accepts("max_tokens") is True
    assert _create_message_accepts("definitely_not_a_real_sdk_parameter") is False


async def test_temperature_omitted_when_installed_sdk_does_not_accept_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.providers.anthropic import provider as provider_module

    monkeypatch.setattr(provider_module, "_create_message_accepts", lambda _param: False)
    client = mock_client()
    client.messages.create.return_value = sdk_message()
    provider = AnthropicProvider(provider_config(temperature=0.3), client=client)

    await provider.create_message(MessageRequest(user_prompt="Hello"))

    kwargs = client.messages.create.call_args.kwargs
    assert "temperature" not in kwargs
    # Supported parameters are still preserved.
    assert kwargs["model"] == "claude-sonnet-5"
    assert kwargs["max_tokens"] == 1024
    assert kwargs["messages"] == [{"role": "user", "content": "Hello"}]


async def test_temperature_included_when_installed_sdk_accepts_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.providers.anthropic import provider as provider_module

    monkeypatch.setattr(provider_module, "_create_message_accepts", lambda _param: True)
    client = mock_client()
    client.messages.create.return_value = sdk_message()
    provider = AnthropicProvider(provider_config(temperature=0.42), client=client)

    await provider.create_message(MessageRequest(user_prompt="Hello"))

    assert client.messages.create.call_args.kwargs["temperature"] == 0.42


async def test_create_message_succeeds_against_an_sdk_that_rejects_the_temperature_kwarg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for the production bug: `anthropic` 1.x's
    `AsyncMessages.create()` has no `temperature` parameter at all, so
    passing it raises `TypeError: create() got an unexpected keyword
    argument 'temperature'` — not an API-level rejection. `strict_create`
    below has that same narrow, real Python signature (no `temperature`),
    so if the provider ever blindly forwarded `temperature` this test would
    fail with the exact production `TypeError` instead of a mock silently
    accepting the extra kwarg.
    """
    from app.providers.anthropic import provider as provider_module

    async def strict_create(*, model: str, max_tokens: int, messages: list, system: str | None = None):
        return sdk_message()

    monkeypatch.setattr(provider_module, "_create_message_accepts", lambda _param: False)
    client = mock_client()
    client.messages.create = strict_create
    provider = AnthropicProvider(provider_config(temperature=0.9), client=client)

    response = await provider.create_message(MessageRequest(user_prompt="Hello"))

    assert response.content == "Hello!"


async def test_conversation_history_precedes_the_user_prompt() -> None:
    client = mock_client()
    client.messages.create.return_value = sdk_message()
    provider = AnthropicProvider(provider_config(), client=client)

    await provider.create_message(
        MessageRequest(
            user_prompt="And then?",
            conversation_history=[
                ConversationMessage(role=ConversationRole.USER, content="Tell me a story."),
                ConversationMessage(role=ConversationRole.ASSISTANT, content="Once upon a time..."),
            ],
        )
    )

    messages = client.messages.create.call_args.kwargs["messages"]
    assert messages == [
        {"role": "user", "content": "Tell me a story."},
        {"role": "assistant", "content": "Once upon a time..."},
        {"role": "user", "content": "And then?"},
    ]


# --- Timeout -----------------------------------------------------------


async def test_timeout_raises_provider_timeout_error() -> None:
    client = mock_client()
    client.messages.create.side_effect = timeout_error()
    provider = AnthropicProvider(provider_config(), client=client, max_attempts=1)

    with pytest.raises(ProviderTimeoutError):
        await provider.create_message(MessageRequest(user_prompt="Hello"))


# --- Authentication failure -----------------------------------------------------------


async def test_authentication_failure_raises_provider_authentication_error() -> None:
    client = mock_client()
    client.messages.create.side_effect = authentication_error()
    provider = AnthropicProvider(provider_config(), client=client)

    with pytest.raises(ProviderAuthenticationError):
        await provider.create_message(MessageRequest(user_prompt="Hello"))


async def test_authentication_failure_is_not_retried() -> None:
    client = mock_client()
    client.messages.create.side_effect = authentication_error()
    provider = AnthropicProvider(provider_config(), client=client, max_attempts=3, retry_backoff_seconds=0.0)

    with pytest.raises(ProviderAuthenticationError):
        await provider.create_message(MessageRequest(user_prompt="Hello"))

    assert client.messages.create.await_count == 1


# --- Rate limiting -----------------------------------------------------------


async def test_rate_limit_raises_provider_rate_limit_error_after_exhausting_retries() -> None:
    client = mock_client()
    client.messages.create.side_effect = rate_limit_error()
    provider = AnthropicProvider(provider_config(), client=client, max_attempts=2, retry_backoff_seconds=0.0)

    with pytest.raises(ProviderRateLimitError):
        await provider.create_message(MessageRequest(user_prompt="Hello"))

    assert client.messages.create.await_count == 2


# --- Malformed response -----------------------------------------------------------


async def test_malformed_response_raises_provider_response_error() -> None:
    client = mock_client()
    broken_message = sdk_message()
    broken_message.content = None  # simulate an unparseable shape
    client.messages.create.return_value = broken_message
    provider = AnthropicProvider(provider_config(), client=client)

    with pytest.raises(ProviderResponseError):
        await provider.create_message(MessageRequest(user_prompt="Hello"))


async def test_bad_request_error_raises_provider_response_error() -> None:
    """A 4xx APIStatusError not otherwise categorized (auth/rate-limit) is
    treated as a response problem, not a transient/retryable one."""
    client = mock_client()
    client.messages.create.side_effect = bad_request_error()
    provider = AnthropicProvider(provider_config(), client=client, max_attempts=3, retry_backoff_seconds=0.0)

    with pytest.raises(ProviderResponseError):
        await provider.create_message(MessageRequest(user_prompt="Hello"))

    assert client.messages.create.await_count == 1  # not retried


# --- Retry behaviour -----------------------------------------------------------


async def test_transient_failure_is_retried_then_succeeds() -> None:
    client = mock_client()
    client.messages.create.side_effect = [timeout_error(), sdk_message(text="recovered")]
    provider = AnthropicProvider(provider_config(), client=client, max_attempts=3, retry_backoff_seconds=0.0)

    response = await provider.create_message(MessageRequest(user_prompt="Hello"))

    assert response.content == "recovered"
    assert client.messages.create.await_count == 2


async def test_retries_are_capped_at_max_attempts() -> None:
    client = mock_client()
    client.messages.create.side_effect = rate_limit_error()
    provider = AnthropicProvider(provider_config(), client=client, max_attempts=4, retry_backoff_seconds=0.0)

    with pytest.raises(ProviderRateLimitError):
        await provider.create_message(MessageRequest(user_prompt="Hello"))

    assert client.messages.create.await_count == 4


# --- Health check -----------------------------------------------------------


async def test_health_check_true_when_api_key_configured() -> None:
    provider = AnthropicProvider(provider_config(api_key="sk-real-key"), client=mock_client())
    assert await provider.health_check() is True


async def test_health_check_false_when_api_key_empty() -> None:
    provider = AnthropicProvider(provider_config(api_key=""), client=mock_client())
    assert await provider.health_check() is False


async def test_health_check_does_not_call_the_sdk() -> None:
    client = mock_client()
    provider = AnthropicProvider(provider_config(), client=client)

    await provider.health_check()

    client.messages.create.assert_not_awaited()


# --- Configuration loading -----------------------------------------------------------


def test_provider_config_builds_from_configuration_service_settings() -> None:
    # AnthropicSettings.model has validation_alias="CLAUDE_MODEL" (Sprint 32,
    # preserving a previously-documented env var name) — that alias is also
    # the required constructor kwarg name, not "model".
    settings = AnthropicSettings(
        _env_file=None,
        api_key=SecretStr("sk-from-settings"),
        CLAUDE_MODEL="claude-opus-5",
        max_tokens=4096,
        temperature=0.7,
        timeout=45.0,
    )

    config = AnthropicProviderConfig.from_settings(settings)

    assert config.api_key.get_secret_value() == "sk-from-settings"
    assert config.model == "claude-opus-5"
    assert config.max_tokens == 4096
    assert config.temperature == 0.7
    assert config.timeout == 45.0


def test_provider_constructs_from_configuration_service_derived_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: ConfigurationService -> AnthropicProviderConfig -> AnthropicProvider,
    with no env var read directly by the provider itself."""
    from app.config.service import ConfigurationService

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-service-key")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    configuration_service = ConfigurationService()
    config = AnthropicProviderConfig.from_settings(configuration_service.anthropic)
    provider = AnthropicProvider(config, client=mock_client())

    assert provider.config.api_key.get_secret_value() == "sk-service-key"


# --- Dependency injection / no singleton -----------------------------------------------------------


def test_two_providers_constructed_independently_do_not_share_state() -> None:
    provider_a = AnthropicProvider(provider_config(api_key="key-a"), client=mock_client())
    provider_b = AnthropicProvider(provider_config(api_key="key-b"), client=mock_client())

    assert provider_a.config.api_key.get_secret_value() == "key-a"
    assert provider_b.config.api_key.get_secret_value() == "key-b"
    assert provider_a is not provider_b


def test_anthropic_provider_satisfies_base_llm_provider() -> None:
    provider = AnthropicProvider(provider_config(), client=mock_client())
    assert isinstance(provider, BaseLLMProvider)
