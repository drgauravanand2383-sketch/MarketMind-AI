"""Shared test doubles and pipeline-assembly helper for Morning Pipeline tests.

No real HTTP, ChromaDB, or embedding API calls occur anywhere in this
module — every external boundary is a lightweight, in-memory stub.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.agents.news_collector.agent import NewsCollectorAgent
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.providers.base import BaseProvider
from app.providers.embedding.models import EmbeddingProviderConfig
from app.providers.embedding.provider import BaseEmbeddingProvider
from app.providers.models import ProviderConfig, ProviderResult
from app.providers.registry import ProviderRegistry
from app.providers.rss.models import RSSFeedData, RSSFeedEntry
from app.repositories.knowledge.models import (
    DeleteResult,
    KnowledgeRecord,
    SaveResult,
    SearchQuery,
    SearchResult,
)
from app.repositories.knowledge.repository import BaseKnowledgeRepository
from app.services.embedding.models import EmbeddingBatch, EmbeddingRequest
from app.services.embedding.service import EmbeddingService
from app.services.evidence_engine.engine import EvidenceEngine
from app.services.knowledge_ingestion.models import IngestionBatch
from app.services.knowledge_ingestion.service import KnowledgeIngestionService
from app.services.market_intelligence.engine import MarketIntelligenceEngine
from app.services.relationship_engine.engine import RelationshipEngine
from app.workflows.morning_pipeline.pipeline import MorningPipeline


class NoOpMemory:
    """A minimal MemoryInterface stand-in; NewsCollectorAgent does not use memory."""

    async def read(self, key: str) -> object:
        raise NotImplementedError

    async def write(self, key: str, value: object) -> None:
        raise NotImplementedError


class MockAppleRSSProvider(BaseProvider):
    """A provider double returning one canned entry mentioning Apple Inc."""

    @property
    def provider_id(self) -> str:
        return "rss"

    @property
    def provider_name(self) -> str:
        return "Mock RSS Provider"

    @property
    def version(self) -> str:
        return "0.0.0-test"

    async def fetch(self, **kwargs: object) -> ProviderResult:
        entry = RSSFeedEntry(
            id="entry-1",
            title="Apple reports record iPhone sales",
            link="https://example.com/apple",
            summary="Apple Inc. posted strong quarterly earnings driven by iPhone demand.",
            published="Mon, 03 Aug 2026 06:00:00 GMT",
            raw={"title": "Apple reports record iPhone sales"},
        )
        feed = RSSFeedData(feed_url="https://example.com/feed.xml", entries=[entry])
        return ProviderResult(
            provider_id=self.provider_id,
            fetched_at=datetime.now(UTC),
            success=True,
            data=[feed],
        )

    async def health_check(self) -> bool:
        return True


class NoIdRSSProvider(BaseProvider):
    """A provider double returning one entry with no id and no content."""

    @property
    def provider_id(self) -> str:
        return "rss"

    @property
    def provider_name(self) -> str:
        return "No-Id Provider"

    @property
    def version(self) -> str:
        return "0.0.0-test"

    async def fetch(self, **kwargs: object) -> ProviderResult:
        entry = RSSFeedEntry(id=None, title=None, summary=None, link=None, published=None, raw={})
        feed = RSSFeedData(feed_url="https://example.com/feed.xml", entries=[entry])
        return ProviderResult(
            provider_id=self.provider_id,
            fetched_at=datetime.now(UTC),
            success=True,
            data=[feed],
        )

    async def health_check(self) -> bool:
        return True


class FailingProvider(BaseProvider):
    """A provider double that always raises during fetch, simulating an outage."""

    @property
    def provider_id(self) -> str:
        return "broken"

    @property
    def provider_name(self) -> str:
        return "Failing Provider"

    @property
    def version(self) -> str:
        return "0.0.0-test"

    async def fetch(self, **kwargs: object) -> ProviderResult:
        raise RuntimeError("simulated provider failure")

    async def health_check(self) -> bool:
        return False


class StubEmbeddingProvider(BaseEmbeddingProvider):
    """An embedding provider double that always succeeds with a fixed vector."""

    async def embed_one(self, request: EmbeddingRequest) -> list[float]:
        return [0.1, 0.2, 0.3]

    async def health_check(self) -> bool:
        return True


class InMemoryKnowledgeRepository(BaseKnowledgeRepository):
    """A minimal, test-only in-memory repository implementation."""

    def __init__(self) -> None:
        self._records: dict[str, KnowledgeRecord] = {}

    async def save_batch(
        self, ingestion_batch: IngestionBatch, embedding_batch: EmbeddingBatch
    ) -> SaveResult:
        for record in ingestion_batch.relational_records:
            self._records[record.id] = KnowledgeRecord(
                id=record.id,
                title=record.title,
                text=record.summary,
                url=record.url,
                published_at=record.published_at,
                source_provider_id=record.source_provider_id,
                metadata=record.source_metadata,
            )
        return SaveResult(
            batch_id=ingestion_batch.ingestion_metadata.batch_id,
            saved_at=datetime.now(UTC),
            vector_count=len(embedding_batch.chunks),
            relational_count=len(ingestion_batch.relational_records),
            success=True,
        )

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        return []

    async def get(self, record_id: str) -> KnowledgeRecord | None:
        return self._records.get(record_id)

    async def delete(self, record_id: str) -> DeleteResult:
        existed = record_id in self._records
        self._records.pop(record_id, None)
        return DeleteResult(id=record_id, deleted=existed)

    async def health_check(self) -> bool:
        return True


def build_news_collector(*provider_classes: type[BaseProvider]) -> NewsCollectorAgent:
    """Build a NewsCollectorAgent with each given provider class registered.

    Each provider double in this module exposes a fixed, config-independent
    provider_id; a throwaway instance is constructed only to read that id
    for registration, avoiding hardcoding the id in two places.
    """
    registry = ProviderRegistry()
    provider_configs: list[ProviderConfig] = []
    probe_config = ProviderConfig(provider_id="_probe")
    for provider_class in provider_classes:
        provider_id = provider_class(probe_config).provider_id
        registry.register(provider_id, provider_class)
        provider_configs.append(ProviderConfig(provider_id=provider_id))
    return NewsCollectorAgent(
        memory=NoOpMemory(), registry=registry, provider_configs=provider_configs
    )


def context(execution_id: str = "exec-1") -> ExecutionContext:
    """Build a caller-supplied ExecutionContext, since MorningPipeline no
    longer constructs its own (Sprint 30)."""
    return ExecutionContext(
        workflow_id="WF-MORNING-PIPELINE",
        execution_id=execution_id,
        workflow_type="morning_intelligence_pipeline",
        trigger=TriggerType.SCHEDULED,
        initiated_by="test",
        started_at=datetime.now(UTC),
        trace_id=execution_id,
        participating_agents=(),
        status=WorkflowStatus.RUNNING,
    )


def build_pipeline(
    news_collector: NewsCollectorAgent | None = None,
    ingestion_service: KnowledgeIngestionService | None = None,
    embedding_service: EmbeddingService | None = None,
    embedding_provider: BaseEmbeddingProvider | None = None,
    knowledge_repository: BaseKnowledgeRepository | None = None,
    evidence_engine: EvidenceEngine | None = None,
    market_intelligence_engine: MarketIntelligenceEngine | None = None,
    relationship_engine: RelationshipEngine | None = None,
) -> MorningPipeline:
    """Assemble a fully-wired MorningPipeline, defaulting every component to a
    working real-or-stub instance; pass overrides to inject failures."""
    return MorningPipeline(
        news_collector=news_collector or build_news_collector(MockAppleRSSProvider),
        ingestion_service=ingestion_service or KnowledgeIngestionService(),
        embedding_service=embedding_service or EmbeddingService(),
        embedding_provider=embedding_provider
        or StubEmbeddingProvider(
            EmbeddingProviderConfig(provider_id="stub", model="stub-model", retry_backoff_seconds=0.0)
        ),
        knowledge_repository=knowledge_repository or InMemoryKnowledgeRepository(),
        evidence_engine=evidence_engine or EvidenceEngine(),
        market_intelligence_engine=market_intelligence_engine or MarketIntelligenceEngine(),
        relationship_engine=relationship_engine or RelationshipEngine(),
    )
