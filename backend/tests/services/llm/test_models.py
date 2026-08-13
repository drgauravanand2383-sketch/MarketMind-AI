"""Tests for the LLM Service's typed models (app.services.llm.models)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.llm.models import (
    ConversationMessage,
    ConversationRole,
    LLMHealthStatus,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)

# --- LLMRequest -----------------------------------------------------------


def test_llm_request_requires_non_empty_user_prompt() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(user_prompt="")


def test_llm_request_defaults() -> None:
    request = LLMRequest(user_prompt="Hello")
    assert request.system_prompt is None
    assert request.conversation_history == []
    assert request.temperature is None
    assert request.max_tokens is None
    assert request.metadata == {}


def test_llm_request_max_tokens_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(user_prompt="Hello", max_tokens=0)


def test_llm_request_temperature_out_of_range_raises() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(user_prompt="Hello", temperature=-0.1)


def test_llm_request_accepts_metadata() -> None:
    request = LLMRequest(user_prompt="Hello", metadata={"trace_id": "abc-123"})
    assert request.metadata == {"trace_id": "abc-123"}


def test_llm_request_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(user_prompt="Hello", unexpected_field="x")


def test_conversation_message_requires_non_empty_content() -> None:
    with pytest.raises(ValidationError):
        ConversationMessage(role=ConversationRole.USER, content="")


# --- LLMResponse -----------------------------------------------------------


def test_llm_response_holds_all_required_fields() -> None:
    response = LLMResponse(
        content="hi",
        usage=TokenUsage(input_tokens=1, output_tokens=2),
        provider="anthropic",
        model="claude-sonnet-5",
        input_tokens=1,
        output_tokens=2,
        stop_reason="end_turn",
    )
    assert response.content == "hi"
    assert response.usage.input_tokens == 1
    assert response.input_tokens == 1
    assert response.output_tokens == 2
    assert response.provider == "anthropic"
    assert response.stop_reason == "end_turn"


def test_llm_response_stop_reason_may_be_none() -> None:
    response = LLMResponse(
        content="hi",
        usage=TokenUsage(input_tokens=1, output_tokens=2),
        provider="anthropic",
        model="claude-sonnet-5",
        input_tokens=1,
        output_tokens=2,
        stop_reason=None,
    )
    assert response.stop_reason is None


def test_token_usage_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        TokenUsage(input_tokens=-1, output_tokens=0)


# --- LLMHealthStatus -----------------------------------------------------------


def test_llm_health_status_holds_all_fields() -> None:
    status = LLMHealthStatus(provider="anthropic", available=True, model="claude-sonnet-5", ready=True)
    assert status.provider == "anthropic"
    assert status.available is True
    assert status.model == "claude-sonnet-5"
    assert status.ready is True


def test_llm_health_status_model_may_be_none() -> None:
    status = LLMHealthStatus(provider="anthropic", available=False, model=None, ready=False)
    assert status.model is None
