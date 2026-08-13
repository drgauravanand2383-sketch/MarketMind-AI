"""Shared test doubles for CompanyResearchAgent tests.

`SearchableInMemoryRepository`'s `save_batch`/`delete` raise
`NotImplementedError` by design: if `CompanyResearchAgent` ever called
either, these tests would fail loudly, directly proving it never writes.
The LLM Service is always mocked (`mock_llm_service` below) — no real
Anthropic SDK or network call occurs anywhere in this package.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import MagicMock

from app.agents.company_research.prompts import register_company_research_prompts
from app.core.runtime import AgentRuntime
from app.knowledge.hub import KnowledgeHub
from app.prompts.registry import PromptRegistry
from app.repositories.knowledge.models import (
    DeleteResult,
    KnowledgeRecord,
    SaveResult,
    SearchQuery,
    SearchResult,
)
from app.repositories.knowledge.repository import BaseKnowledgeRepository
from app.services.embedding.models import EmbeddingBatch
from app.services.knowledge_ingestion.models import IngestionBatch
from app.services.llm.models import LLMHealthStatus, LLMResponse, TokenUsage
from app.services.llm.service import LLMService


class NoOpMemory:
    """A minimal MemoryInterface stand-in; CompanyResearchAgent does not use memory."""

    async def read(self, key: str) -> object:
        raise NotImplementedError

    async def write(self, key: str, value: object) -> None:
        raise NotImplementedError


class _StubConfiguration:
    def get(self, key: str, default: object = None) -> object:
        return default


class _StubKnowledgeHub:
    async def query(self, query: str, top_k: int = 5) -> list[object]:
        return []


class _StubToolRegistry:
    def get_tool(self, name: str) -> object:
        raise KeyError(name)

    def list_tools(self) -> tuple[str, ...]:
        return ()


class _StubEventBus:
    async def publish(self, event_name: str, payload: object) -> None:
        return None

    def subscribe(self, event_name: str, handler: object) -> None:
        return None


def build_runtime() -> AgentRuntime:
    """Build a minimal, fully-stubbed AgentRuntime for tests."""
    return AgentRuntime(
        logger=logging.getLogger("test.company_research"),
        configuration=_StubConfiguration(),
        knowledge_hub=_StubKnowledgeHub(),
        memory=NoOpMemory(),
        tool_registry=_StubToolRegistry(),
        event_bus=_StubEventBus(),
    )


def record(**overrides: Any) -> KnowledgeRecord:
    defaults: dict[str, Any] = {
        "id": "rec-1",
        "title": None,
        "text": None,
        "url": None,
        "published_at": None,
        "source_provider_id": "rss",
        "metadata": {},
    }
    defaults.update(overrides)
    return KnowledgeRecord(**defaults)


class SearchableInMemoryRepository(BaseKnowledgeRepository):
    """A read-focused in-memory repository whose `search` does real
    case-insensitive substring matching, so CompanyResearchAgent's
    retrieval logic is exercised meaningfully rather than against a
    repository that returns everything or nothing regardless of query."""

    def __init__(self, records: list[KnowledgeRecord] | None = None) -> None:
        self._records: dict[str, KnowledgeRecord] = {r.id: r for r in (records or [])}

    async def save_batch(
        self, ingestion_batch: IngestionBatch, embedding_batch: EmbeddingBatch
    ) -> SaveResult:
        raise NotImplementedError("CompanyResearchAgent must never write to the repository")

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        query_text = (query.query_text or "").lower()
        results = []
        for stored in self._records.values():
            haystack = " ".join(part for part in (stored.title, stored.text) if part).lower()
            if query_text and query_text in haystack:
                results.append(
                    SearchResult(id=stored.id, score=1.0, text=stored.text, metadata=stored.metadata)
                )
        return results[: query.top_k]

    async def get(self, record_id: str) -> KnowledgeRecord | None:
        return self._records.get(record_id)

    async def delete(self, record_id: str) -> DeleteResult:
        raise NotImplementedError("CompanyResearchAgent must never delete from the repository")

    async def health_check(self) -> bool:
        return True


def build_knowledge_hub(records: list[KnowledgeRecord] | None = None) -> KnowledgeHub:
    """A real KnowledgeHub wrapping the in-memory repository double above.

    `KnowledgeHub` only ever calls `.search(SearchQuery)`/`.get(id)` on its
    injected repository — both of which `SearchableInMemoryRepository`
    implements — so it works here even though it's not literally a
    `CompositeKnowledgeRepository`.
    """
    return KnowledgeHub(SearchableInMemoryRepository(records))  # type: ignore[arg-type]


def build_prompt_registry() -> PromptRegistry:
    """A PromptRegistry with the Company Research template already registered."""
    registry = PromptRegistry()
    register_company_research_prompts(registry)
    return registry


def narrative_json(
    summary: str = "Evidence-grounded summary.",
    key_findings: list[str] | None = None,
    risk_commentary: str | None = "No material risks identified.",
) -> str:
    """A well-formed CompanyResearchNarrative JSON payload, as an LLM response's `content` would contain."""
    return json.dumps(
        {
            "summary": summary,
            "key_findings": key_findings if key_findings is not None else ["Finding one."],
            "risk_commentary": risk_commentary,
        }
    )


def llm_response(content: str | None = None) -> LLMResponse:
    return LLMResponse(
        content=content if content is not None else narrative_json(),
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        provider="anthropic",
        model="claude-sonnet-5",
        input_tokens=100,
        output_tokens=50,
        stop_reason="end_turn",
    )


def mock_llm_service(
    content: str | None = None,
    error: Exception | None = None,
    ready: bool = True,
) -> MagicMock:
    """A mocked LLMService — `generate()`/`health_check()` are AsyncMocks.

    `MagicMock(spec=LLMService)` auto-detects that both are coroutine
    functions and mocks them as AsyncMock, matching this project's
    established mocking convention (e.g. `MagicMock(spec=WorkflowEngine)`).
    """
    service = MagicMock(spec=LLMService)
    if error is not None:
        service.generate.side_effect = error
    else:
        service.generate.return_value = llm_response(content)
    service.health_check.return_value = LLMHealthStatus(
        provider="anthropic", available=ready, model="claude-sonnet-5" if ready else None, ready=ready
    )
    return service
