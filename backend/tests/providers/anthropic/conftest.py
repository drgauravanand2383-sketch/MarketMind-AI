"""Shared doubles and factories for AnthropicProvider tests.

The Anthropic SDK is mocked throughout — `client.messages.create` is an
`AsyncMock` on a plain `MagicMock` client injected via
`AnthropicProvider(config, client=...)`. No real network call, and no
real `anthropic.AsyncAnthropic` instance, is ever created. SDK exceptions
are constructed for real (they need genuine `httpx.Request`/`httpx.Response`
objects to build), but never actually sent over the network.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import anthropic
import httpx
from anthropic.types import Message, TextBlock, Usage
from pydantic import SecretStr

from app.providers.anthropic.models import AnthropicProviderConfig


def provider_config(
    api_key: str = "sk-test-key",
    model: str = "claude-sonnet-5",
    max_tokens: int = 1024,
    temperature: float = 1.0,
    timeout: float = 30.0,
) -> AnthropicProviderConfig:
    return AnthropicProviderConfig(
        api_key=SecretStr(api_key),
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
    )


def mock_client() -> MagicMock:
    client = MagicMock()
    client.messages.create = AsyncMock()
    return client


def sdk_message(
    text: str = "Hello!",
    input_tokens: int = 10,
    output_tokens: int = 5,
    model: str = "claude-sonnet-5",
    stop_reason: str | None = "end_turn",
) -> Message:
    """A real anthropic.types.Message (not a bare mock) — the most faithful
    stand-in for what `client.messages.create()` actually returns."""
    return Message(
        id="msg_test",
        content=[TextBlock(text=text, type="text")],
        model=model,
        role="assistant",
        stop_reason=stop_reason,
        type="message",
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=_request())


def authentication_error(message: str = "invalid x-api-key") -> anthropic.AuthenticationError:
    return anthropic.AuthenticationError(message, response=_response(401), body=None)


def rate_limit_error(message: str = "rate limit exceeded") -> anthropic.RateLimitError:
    return anthropic.RateLimitError(message, response=_response(429), body=None)


def timeout_error() -> anthropic.APITimeoutError:
    return anthropic.APITimeoutError(request=_request())


def connection_error(message: str = "connection failed") -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(message=message, request=_request())


def internal_server_error(message: str = "internal server error") -> anthropic.InternalServerError:
    return anthropic.InternalServerError(message, response=_response(500), body=None)


def bad_request_error(message: str = "bad request") -> anthropic.BadRequestError:
    return anthropic.BadRequestError(message, response=_response(400), body=None)
