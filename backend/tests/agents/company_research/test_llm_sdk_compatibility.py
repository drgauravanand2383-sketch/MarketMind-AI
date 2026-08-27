"""Regression test for the production bug reported against MarketMind AI
v1.2.3: `AsyncMessages.create() got an unexpected keyword argument
'temperature'`.

Every other test in this package mocks `LLMService` directly (see
`conftest.py`), which never exercises `AnthropicProvider` or the Anthropic
SDK call itself — the layer where the real bug lived. This file instead
wires the *real* failure chain from the bug report end to end:

    POST /api/v1/research/company
    -> CompanyResearchAgent.run()
    -> CompanyResearchAgent._generate_narrative()
    -> LLMService.generate()               (real)
    -> AnthropicProvider.create_message()  (real)
    -> AsyncMessages.create()              (a strict fake standing in for the SDK)

Only the outermost SDK boundary is a test double, and it is deliberately
narrow-signatured — reproducing exactly the `anthropic` 1.x
`AsyncMessages.create()` shape (no `temperature`/`top_p`/`top_k`) — so this
test would fail with the same `TypeError` as production if
`AnthropicProvider` ever again blindly forwarded `temperature`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from anthropic.types import Message, TextBlock, Usage
from pydantic import SecretStr

from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.company_research.models import CompanyResearchRequest
from app.config.models import AnthropicSettings, AppConfig, LLMSettings
from app.config.service import ConfigurationService
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.providers.anthropic import provider as provider_module
from app.providers.anthropic.models import AnthropicProviderConfig
from app.providers.anthropic.provider import AnthropicProvider
from app.services.llm.service import LLMService
from tests.agents.company_research.conftest import (
    build_knowledge_hub,
    build_prompt_registry,
    build_runtime,
    narrative_json,
    record,
)

APPLE_RECORD = record(
    id="rec-apple-1",
    title="Apple reports record iPhone sales",
    text="Apple Inc. posted strong quarterly earnings driven by iPhone demand.",
    url="https://example.com/apple1",
    published_at="2026-08-01",
    source_provider_id="rss",
)


def _context() -> ExecutionContext:
    return ExecutionContext(
        workflow_id="WF-COMPANY-RESEARCH",
        execution_id="exec-sdk-compat",
        workflow_type="company_research",
        trigger=TriggerType.USER_REQUEST,
        initiated_by="test",
        started_at=datetime.now(UTC),
        trace_id="trace-sdk-compat",
        participating_agents=("AGT-004",),
        status=WorkflowStatus.RUNNING,
    )


class _PermissiveAsyncMessagesClient:
    """Stands in for `anthropic.AsyncAnthropic` with the real, currently
    installed SDK's `messages.create()` shape — `temperature` included —
    matching what `_create_message_accepts("temperature")` actually
    reports for the pinned (`anthropic<1.0.0`) dependency this project
    installs today."""

    def __init__(self, content: str) -> None:
        self._content = content
        self.messages = MagicMock()
        self.messages.create = self._create

    async def _create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list,
        system: str | None = None,
        temperature: float | None = None,
    ) -> Message:
        return Message(
            id="msg_sdk_compat_test",
            content=[TextBlock(text=self._content, type="text")],
            model=model,
            role="assistant",
            stop_reason="end_turn",
            type="message",
            usage=Usage(input_tokens=100, output_tokens=50),
        )


class _StrictAsyncMessagesClient:
    """Stands in for `anthropic.AsyncAnthropic` with the exact narrow
    `messages.create()` shape `anthropic` 1.x actually exposes — no
    `temperature`/`top_p`/`top_k` parameter at all. Calling it with any of
    those raises a real `TypeError`, exactly like the production SDK."""

    def __init__(self, content: str) -> None:
        self._content = content
        self.messages = MagicMock()
        self.messages.create = self._create

    async def _create(
        self, *, model: str, max_tokens: int, messages: list, system: str | None = None
    ) -> Message:
        return Message(
            id="msg_sdk_compat_test",
            content=[TextBlock(text=self._content, type="text")],
            model=model,
            role="assistant",
            stop_reason="end_turn",
            type="message",
            usage=Usage(input_tokens=100, output_tokens=50),
        )


def _real_agent(content: str, client: object) -> CompanyResearchAgent:
    """Build a CompanyResearchAgent wired to the real LLMService and the
    real AnthropicProvider — only `AsyncMessages.create` is a double."""
    provider = AnthropicProvider(
        AnthropicProviderConfig(
            api_key=SecretStr("sk-test-key"),
            model="claude-sonnet-5",
            max_tokens=1024,
            temperature=1.0,
            timeout=30.0,
        ),
        client=client,  # type: ignore[arg-type]
    )
    configuration = ConfigurationService(
        AppConfig(
            anthropic=AnthropicSettings(_env_file=None, api_key=SecretStr("sk-test-key")),
            llm=LLMSettings(_env_file=None, provider="anthropic"),
        )
    )
    llm_service = LLMService(providers={"anthropic": provider}, configuration=configuration)

    return CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=build_knowledge_hub([APPLE_RECORD]),
        llm_service=llm_service,
        prompt_registry=build_prompt_registry(),
    )


async def test_company_research_produces_a_narrative_through_the_real_llm_and_provider_layers() -> None:
    """End-to-end (SDK-boundary-only-mocked) proof that the real production
    failure chain — router -> agent -> LLMService -> AnthropicProvider ->
    SDK — completes today, against the currently pinned/installed SDK
    shape (which still accepts `temperature`)."""
    content = narrative_json(summary="Apple Inc. evidence-grounded summary.")
    agent = _real_agent(content, _PermissiveAsyncMessagesClient(content))

    report = await agent.run(
        _context(), CompanyResearchRequest(company_name="Apple Inc.", ticker="AAPL")
    )

    assert report.narrative is not None
    assert report.narrative.summary == "Apple Inc. evidence-grounded summary."


async def test_company_research_still_succeeds_when_installed_sdk_rejects_temperature_kwarg(
    monkeypatch,
) -> None:
    """Regression test for the exact production bug: forces the "installed
    SDK dropped temperature" branch (`_create_message_accepts` -> False,
    matching `anthropic` 1.x) *and* pairs it with `_StrictAsyncMessagesClient`
    — a fake with that same narrow, real Python signature (no
    `temperature`). Before the fix, this reproduces the exact production
    `TypeError: ...create() got an unexpected keyword argument
    'temperature'`, all the way from `CompanyResearchAgent.run()`."""
    monkeypatch.setattr(provider_module, "_create_message_accepts", lambda _param: False)
    content = narrative_json(summary="Apple Inc. evidence-grounded summary.")
    agent = _real_agent(content, _StrictAsyncMessagesClient(content))

    report = await agent.run(
        _context(), CompanyResearchRequest(company_name="Apple Inc.", ticker="AAPL")
    )

    assert report.narrative is not None
    assert report.narrative.summary == "Apple Inc. evidence-grounded summary."
