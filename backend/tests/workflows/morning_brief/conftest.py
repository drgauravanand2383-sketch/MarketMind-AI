"""Shared fixtures and doubles for MorningBriefWorkflow tests.

News Collector, the Composite Knowledge Repository, the Knowledge Hub, and
the Embedding Provider are mocked (avoiding RSS feeds, PostgreSQL,
ChromaDB, and a real embedding API). KnowledgeIngestionService,
EmbeddingService, MarketIntelligenceEngine, RelationshipEngine, and
EvidenceEngine are used as real instances — they are pure, in-memory, and
side-effect-free, so using them for real exercises genuine orchestration
logic rather than call-counting mocks. MorningBriefGenerator is real too,
writing only within pytest's `tmp_path`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

from app.agents.morning_brief_generator.generator import MorningBriefGenerator
from app.agents.news_collector.agent import NewsCollectorAgent
from app.agents.news_collector.models import NewsCollectionResult, NewsItem
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.knowledge.hub import KnowledgeHub
from app.providers.embedding.models import EmbeddingResult
from app.providers.embedding.provider import BaseEmbeddingProvider
from app.repositories.knowledge.composite.repository import CompositeKnowledgeRepository
from app.repositories.knowledge.models import KnowledgeRecord, SaveResult
from app.services.embedding.service import EmbeddingService
from app.services.evidence_engine.engine import EvidenceEngine
from app.services.knowledge_ingestion.service import KnowledgeIngestionService
from app.services.market_intelligence.engine import MarketIntelligenceEngine
from app.services.relationship_engine.engine import RelationshipEngine
from app.workflows.morning_brief.workflow import MorningBriefWorkflow


def context() -> ExecutionContext:
    return ExecutionContext(
        workflow_id="WF-MORNING-BRIEF",
        execution_id="exec-1",
        workflow_type="morning_brief",
        trigger=TriggerType.SCHEDULED,
        initiated_by="test",
        started_at=datetime.now(UTC),
        trace_id="trace-1",
        participating_agents=("AGT-003",),
        status=WorkflowStatus.RUNNING,
    )


def news_item(item_id: str, title: str, summary: str) -> NewsItem:
    return NewsItem(
        id=item_id,
        title=title,
        summary=summary,
        url=f"https://example.com/{item_id}",
        published_at="Mon, 03 Aug 2026 06:00:00 GMT",
        source_provider_id="rss",
    )


def news_collection_result(items: list[NewsItem]) -> NewsCollectionResult:
    return NewsCollectionResult(
        items=items, provider_summary=[], collected_at=datetime.now(UTC)
    )


def knowledge_record(record_id: str, title: str, text: str) -> KnowledgeRecord:
    return KnowledgeRecord(
        id=record_id,
        title=title,
        text=text,
        url=f"https://example.com/{record_id}",
        published_at="Mon, 03 Aug 2026 06:00:00 GMT",
        source_provider_id="rss",
        metadata={},
    )


def save_result(relational_count: int) -> SaveResult:
    return SaveResult(
        batch_id="batch-1",
        saved_at=datetime.now(UTC),
        vector_count=0,
        relational_count=relational_count,
        success=True,
    )


def embedding_result(total_succeeded: int) -> EmbeddingResult:
    return EmbeddingResult(
        batch_id="embed-batch-1",
        generated_at=datetime.now(UTC),
        model="test-model",
        chunk_results=[],
        success=True,
        total_requested=total_succeeded,
        total_succeeded=total_succeeded,
        total_failed=0,
    )


def mock_news_collector() -> AsyncMock:
    return AsyncMock(spec=NewsCollectorAgent)


def mock_knowledge_repository() -> AsyncMock:
    return AsyncMock(spec=CompositeKnowledgeRepository)


def mock_knowledge_hub() -> AsyncMock:
    return AsyncMock(spec=KnowledgeHub)


def mock_embedding_provider() -> AsyncMock:
    return AsyncMock(spec=BaseEmbeddingProvider)


def build_workflow(
    tmp_path: Path,
    news_collector: AsyncMock | None = None,
    knowledge_repository: AsyncMock | None = None,
    knowledge_hub: AsyncMock | None = None,
    embedding_provider: AsyncMock | None = None,
    report_generator: MorningBriefGenerator | None = None,
) -> MorningBriefWorkflow:
    return MorningBriefWorkflow(
        news_collector=news_collector or mock_news_collector(),
        ingestion_service=KnowledgeIngestionService(),
        embedding_service=EmbeddingService(),
        knowledge_repository=knowledge_repository or mock_knowledge_repository(),
        knowledge_hub=knowledge_hub or mock_knowledge_hub(),
        market_intelligence_engine=MarketIntelligenceEngine(),
        relationship_engine=RelationshipEngine(),
        evidence_engine=EvidenceEngine(),
        report_generator=report_generator or MorningBriefGenerator(output_dir=tmp_path),
        embedding_provider=embedding_provider,
    )
