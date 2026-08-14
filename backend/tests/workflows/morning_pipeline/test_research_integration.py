"""Integration test: MorningPipeline's write side and CompanyResearchAgent's
read side, through the same real ChromaKnowledgeRepository instance.

This is the actual product requirement Milestone 11 exists to satisfy —
"Research automatically benefits from newly ingested knowledge records,
without any change to the Research engine itself." Every other test in
this package (and in `tests/agents/company_research/`) exercises each
side in isolation against its own fake/stub repository; this file is the
one place that proves the two sides are actually compatible with each
other through the real repository contract, not just individually
correct against test doubles that might silently disagree with it.

Uses a real, in-memory `chromadb.EphemeralClient()` (not a fake
`ChromaCollection` stand-in) with an injected no-op embedding function —
this is still fully network-free and fast (no ONNX model, no disk
persistence), matching this milestone's "no live internet access in
automated tests" constraint, while exercising the real ChromaDB
add/upsert/query code paths `ChromaKnowledgeRepository` actually calls.
"""

from __future__ import annotations

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.company_research.models import CompanyResearchRequest
from app.repositories.knowledge.chroma.repository import ChromaKnowledgeRepository
from app.knowledge.hub import KnowledgeHub
from tests.agents.company_research.conftest import build_prompt_registry, build_runtime, mock_llm_service
from tests.workflows.morning_pipeline.conftest import (
    MockAppleRSSProvider,
    StubEmbeddingProvider,
    build_news_collector,
    build_pipeline,
    context,
)


class _NoOpEmbeddingFunction(EmbeddingFunction):
    """A fixed-vector ChromaDB embedding function — no ML model, no
    network. Every document maps to the same vector, which is fine here:
    this test only needs `query_texts=["Apple"]` to find the one document
    actually stored, and ChromaDB's own text-substring-agnostic vector
    search still returns whatever's in a single-document collection."""

    def __init__(self) -> None:
        pass

    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002 - chromadb's own parameter name
        return [[0.1, 0.2, 0.3] for _ in input]

    @staticmethod
    def name() -> str:
        return "test-no-op"


def _real_chroma_repository() -> ChromaKnowledgeRepository:
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(
        name="test_knowledge", embedding_function=_NoOpEmbeddingFunction()
    )
    return ChromaKnowledgeRepository(collection)


async def test_research_returns_no_evidence_before_ingestion() -> None:
    """Baseline: an empty repository behaves exactly like the live
    acceptance diagnosis found — Research reports an unmatched company,
    not an error."""
    repository = _real_chroma_repository()
    agent = CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=KnowledgeHub(repository),
        llm_service=mock_llm_service(),
        prompt_registry=build_prompt_registry(),
    )

    report = await agent.run(context(), CompanyResearchRequest(company_name="Apple"))

    assert report.company_overview.matched is False
    assert report.narrative is None


async def test_research_returns_real_evidence_after_pipeline_ingestion() -> None:
    """The actual Milestone 11 requirement: run MorningPipeline against a
    real repository, then confirm CompanyResearchAgent — constructed
    completely independently, knowing nothing about the pipeline — finds
    what was just ingested, through nothing but the shared repository."""
    repository = _real_chroma_repository()
    pipeline = build_pipeline(
        news_collector=build_news_collector(MockAppleRSSProvider),
        embedding_provider=StubEmbeddingProvider(
            _stub_embedding_config(),
        ),
        knowledge_repository=repository,
    )

    pipeline_result = await pipeline.execute(context("ingest-run"))
    assert pipeline_result.status.value == "completed"

    agent = CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=KnowledgeHub(repository),
        llm_service=mock_llm_service(),
        prompt_registry=build_prompt_registry(),
    )

    report = await agent.run(context("research-run"), CompanyResearchRequest(company_name="Apple"))

    assert report.company_overview.matched is True
    assert len(report.supporting_evidence) > 0
    assert len(report.latest_news) > 0
    assert any("Apple" in (item.title or "") for item in report.latest_news)
    # No "NO_DATA" risk flag once a real record matched.
    assert not any(flag.code == "NO_DATA" for flag in report.key_risks)


def _stub_embedding_config():  # noqa: ANN202
    from app.providers.embedding.models import EmbeddingProviderConfig

    return EmbeddingProviderConfig(provider_id="stub", model="stub-model", retry_backoff_seconds=0.0)
