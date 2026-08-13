"""Tests for the Anthropic provider's typed models (app.providers.anthropic.models)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.providers.anthropic.models import (
    AnthropicProviderConfig,
    ConversationMessage,
    ConversationRole,
    MessageRequest,
    MessageResponse,
    TokenUsage,
)


def test_message_request_requires_a_non_empty_user_prompt() -> None:
    with pytest.raises(ValidationError):
        MessageRequest(user_prompt="")


def test_message_request_defaults() -> None:
    request = MessageRequest(user_prompt="Hello")
    assert request.system_prompt is None
    assert request.conversation_history == []
    assert request.max_tokens is None
    assert request.temperature is None


def test_message_request_max_tokens_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        MessageRequest(user_prompt="Hello", max_tokens=0)


def test_message_request_temperature_out_of_range_raises() -> None:
    with pytest.raises(ValidationError):
        MessageRequest(user_prompt="Hello", temperature=1.5)


def test_conversation_message_requires_non_empty_content() -> None:
    with pytest.raises(ValidationError):
        ConversationMessage(role=ConversationRole.USER, content="")


def test_message_response_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        MessageResponse(
            content="hi",
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            model="claude-sonnet-5",
            stop_reason="end_turn",
            unexpected_field="x",
        )


def test_token_usage_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        TokenUsage(input_tokens=-1, output_tokens=0)


def test_anthropic_provider_config_requires_positive_max_tokens() -> None:
    with pytest.raises(ValidationError):
        AnthropicProviderConfig(
            api_key=SecretStr("sk-test"), model="claude-sonnet-5", max_tokens=0, temperature=1.0, timeout=30.0
        )


def test_anthropic_provider_config_temperature_range() -> None:
    with pytest.raises(ValidationError):
        AnthropicProviderConfig(
            api_key=SecretStr("sk-test"),
            model="claude-sonnet-5",
            max_tokens=1024,
            temperature=2.0,
            timeout=30.0,
        )


def test_anthropic_provider_config_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        AnthropicProviderConfig(
            api_key=SecretStr("sk-test"),
            model="claude-sonnet-5",
            max_tokens=1024,
            temperature=1.0,
            timeout=30.0,
            unexpected_field="x",
        )
