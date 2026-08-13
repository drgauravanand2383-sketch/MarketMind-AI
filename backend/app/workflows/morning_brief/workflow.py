"""Morning Brief Workflow — orchestrates existing services to produce the Morning Brief.

MorningBriefWorkflow coordinates already-implemented components in a fixed
sequence: News Collector → Knowledge Ingestion → Embedding Service →
(optional) Embedding Provider → Composite Knowledge Repository →
Knowledge Hub → Market Intelligence Engine → Relationship Engine /
Evidence Engine → Morning Brief Generator. It performs no reasoning and
computes no new business facts of its own — every section of the final
brief comes directly from an existing engine's output, or is left empty
when no existing engine produces that kind of data (see
`_build_morning_intelligence`). It never touches a database or a provider
directly, only through the already-approved abstractions
(CompositeKnowledgeRepository, KnowledgeHub, NewsCollectorAgent's own
provider registry).

`execute(context)` is the canonical entry point (WorkflowProtocol, Sprint
29) — it and the retained `run(context, news_request=None)` are both thin
wrappers around one shared private implementation (`_execute_impl`), so
neither duplicates the orchestration logic. The ExecutionContext passed in
is never mutated or replaced: this workflow only reads it and forwards the
same object to NewsCollectorAgent (which requires one per its own
BaseAgent contract). Step-by-step progress is tracked in local variables
only.
"""

from __future__ import annotations

import time

from app.agents.morning_brief_generator.generator import MorningBriefGenerator
from app.agents.news_collector.agent import NewsCollectorAgent
from app.agents.news_collector.models import NewsCollectionRequest
from app.core.context import ExecutionContext
from app.knowledge.hub import KnowledgeHub
from app.providers.embedding.provider import BaseEmbeddingProvider
from app.repositories.knowledge.composite.repository import CompositeKnowledgeRepository
from app.repositories.knowledge.models import KnowledgeRecord
from app.repositories.knowledge.postgres.mapper import parse_published_at
from app.schemas.intelligence import Headline, MarketOverview, MorningIntelligence, SourceRef
from app.services.embedding.service import EmbeddingService
from app.services.evidence_engine.engine import EvidenceEngine
from app.services.evidence_engine.models import EvidenceGraph
from app.services.knowledge_ingestion.service import KnowledgeIngestionService
from app.services.market_intelligence.engine import MarketIntelligenceEngine
from app.services.market_intelligence.models import MarketIntelligence
from app.services.relationship_engine.engine import RelationshipEngine
from app.services.relationship_engine.models import RelationshipGraph
from app.workflows.morning_brief.models import MorningBriefWorkflowResult

__all__ = ["MorningBriefWorkflow"]

DEFAULT_KNOWLEDGE_QUERY = "market news"
DEFAULT_KNOWLEDGE_TOP_K = 50


class MorningBriefWorkflow:
    """Orchestrates existing services, in a fixed sequence, to produce the Morning Brief.

    Every dependency is injected; this class constructs nothing and holds
    no global or singleton state. It performs no reasoning, no
    summarization, and no computation of new business facts — it only
    calls existing components in order and passes their outputs forward.
    """

    def __init__(
        self,
        news_collector: NewsCollectorAgent,
        ingestion_service: KnowledgeIngestionService,
        embedding_service: EmbeddingService,
        knowledge_repository: CompositeKnowledgeRepository,
        knowledge_hub: KnowledgeHub,
        market_intelligence_engine: MarketIntelligenceEngine,
        relationship_engine: RelationshipEngine,
        evidence_engine: EvidenceEngine,
        report_generator: MorningBriefGenerator,
        embedding_provider: BaseEmbeddingProvider | None = None,
        knowledge_query: str = DEFAULT_KNOWLEDGE_QUERY,
        knowledge_top_k: int = DEFAULT_KNOWLEDGE_TOP_K,
    ) -> None:
        """Initialize the workflow with every stage's already-configured component.

        Args:
            news_collector: AGT-003, configured with whichever providers
                should run for this deployment.
            ingestion_service: Prepares normalized NewsItems for storage.
            embedding_service: Batches VectorDocuments into EmbeddingRequests.
            knowledge_repository: The composite (PostgreSQL + ChromaDB)
                repository this workflow persists through.
            knowledge_hub: The read interface this workflow retrieves
                knowledge through — never the repository directly for reads.
            market_intelligence_engine: Analyzes retrieved records deterministically.
            relationship_engine: Extracts relationships from that analysis.
            evidence_engine: Builds evidence references from retrieved records.
            report_generator: Renders and writes the final Markdown brief.
            embedding_provider: Optional. If None, embedding generation is
                skipped entirely — expected, not an error, since no
                concrete embedding provider implementation exists in every
                deployment.
            knowledge_query: The query text passed to `KnowledgeHub.query()`.
                There is no natural-language "give me everything recent"
                query on KnowledgeHub, so this is an injected, configurable
                value rather than a business decision made by this workflow.
            knowledge_top_k: How many records to retrieve via `KnowledgeHub.query()`.
        """
        self._news_collector = news_collector
        self._ingestion_service = ingestion_service
        self._embedding_service = embedding_service
        self._embedding_provider = embedding_provider
        self._knowledge_repository = knowledge_repository
        self._knowledge_hub = knowledge_hub
        self._market_intelligence_engine = market_intelligence_engine
        self._relationship_engine = relationship_engine
        self._evidence_engine = evidence_engine
        self._report_generator = report_generator
        self._knowledge_query = knowledge_query
        self._knowledge_top_k = knowledge_top_k

    async def execute(self, context: ExecutionContext) -> MorningBriefWorkflowResult:
        """The canonical WorkflowProtocol entry point (Sprint 29).

        Runs with the default (unfiltered) NewsCollectionRequest. Callers
        needing a customized request should use `run(context, news_request)`
        instead — the WorkflowProtocol's fixed single-argument signature
        has no room for it here.

        Args:
            context: The caller-provided ExecutionContext. Never mutated
                or replaced by this workflow — only read and forwarded to
                NewsCollectorAgent.

        Returns:
            A MorningBriefWorkflowResult. See `_execute_impl` for details.
        """
        return await self._execute_impl(context, news_request=None)

    async def run(
        self, context: ExecutionContext, news_request: NewsCollectionRequest | None = None
    ) -> MorningBriefWorkflowResult:
        """Retained for backward compatibility; prefer `execute(context)`.

        Delegates to the same private implementation `execute()` uses
        (`_execute_impl`) — no orchestration logic is duplicated between
        the two public methods. This exists only because `execute()`'s
        protocol-mandated signature cannot carry a customized
        `news_request`.

        Args:
            context: The caller-provided ExecutionContext. Never mutated
                or replaced by this workflow.
            news_request: The request to pass to the News Collector.
                Defaults to an unfiltered NewsCollectionRequest.

        Returns:
            A MorningBriefWorkflowResult. See `_execute_impl` for details.
        """
        return await self._execute_impl(context, news_request)

    async def _execute_impl(
        self, context: ExecutionContext, news_request: NewsCollectionRequest | None
    ) -> MorningBriefWorkflowResult:
        """The Morning Brief Workflow's single orchestration implementation.

        Both `execute()` and `run()` delegate here — this is the only
        place the nine-step sequence is implemented, so neither public
        method can drift out of sync with the other.

        Returns:
            A MorningBriefWorkflowResult. `success=False` if any step
            raised; every count reflects what was actually measured before
            that point, never reset to zero.
        """
        started_at = time.monotonic()
        request = news_request if news_request is not None else NewsCollectionRequest()

        articles_processed = 0
        articles_persisted = 0
        embeddings_generated = 0
        report_path: str | None = None

        try:
            # Step 1: Collect news
            collection_result = await self._news_collector.run(context, request)
            articles_processed = len(collection_result.items)

            # Step 2: Prepare ingestion batch
            ingestion_batch = self._ingestion_service.prepare_batch(collection_result)

            # Step 3: Prepare embedding batch
            embedding_batch = self._embedding_service.prepare_batch(
                ingestion_batch.vector_documents
            )

            # Step 4: Generate embeddings, only if a provider is configured
            if self._embedding_provider is not None:
                embedding_result = await self._embedding_provider.generate(embedding_batch)
                embeddings_generated = embedding_result.total_succeeded

            # Step 5: Persist through the Composite Knowledge Repository
            save_result = await self._knowledge_repository.save_batch(
                ingestion_batch, embedding_batch
            )
            articles_persisted = save_result.relational_count

            # Step 6: Retrieve latest knowledge through the Knowledge Hub
            records = await self._knowledge_hub.query(
                self._knowledge_query, top_k=self._knowledge_top_k
            )

            # Step 7: Generate MarketIntelligence, RelationshipGraph, EvidenceGraph
            market_intelligence = self._market_intelligence_engine.analyze(records)
            relationship_graph = self._relationship_engine.build_graph(market_intelligence)
            evidence_graph = self._evidence_engine.build_graph(records)

            # Step 8: Generate the Morning Brief Markdown and write the report
            morning_intelligence = self._build_morning_intelligence(
                context, records, market_intelligence, relationship_graph, evidence_graph
            )
            generated_path = self._report_generator.generate(morning_intelligence)
            report_path = str(generated_path)

        except Exception:  # noqa: BLE001 - stop immediately, report what was measured so far
            return MorningBriefWorkflowResult(
                report_path=report_path,
                articles_processed=articles_processed,
                articles_persisted=articles_persisted,
                embeddings_generated=embeddings_generated,
                execution_time=time.monotonic() - started_at,
                success=False,
            )

        return MorningBriefWorkflowResult(
            report_path=report_path,
            articles_processed=articles_processed,
            articles_persisted=articles_persisted,
            embeddings_generated=embeddings_generated,
            execution_time=time.monotonic() - started_at,
            success=True,
        )

    def _build_morning_intelligence(
        self,
        context: ExecutionContext,
        records: list[KnowledgeRecord],
        market_intelligence: MarketIntelligence,
        relationship_graph: RelationshipGraph,
        evidence_graph: EvidenceGraph,
    ) -> MorningIntelligence:
        """Translate existing engine outputs into MorningBriefGenerator's input shape.

        This is a pure structural adapter — no new facts are computed or
        inferred. MorningIntelligence (Sprint 8) was designed assuming
        numeric market data (stock price changes, sector performance
        percentages, global index values) and risk signals would be
        available; MarketIntelligenceEngine/RelationshipEngine/
        EvidenceEngine (Sprints 17-22) instead produce entity mention
        counts, co-occurrence relationships, and evidence references from
        news text — there is no numeric price/performance data or risk
        signal anywhere in this pipeline. `stocks_to_watch`, `sector_watch`,
        `global_markets`, and `risk_alerts` are therefore left empty
        rather than fabricated; MorningBriefGenerator already renders an
        honest "no data available" placeholder for each.
        """
        headlines = self._build_headlines(records)
        sources = self._build_sources(records)

        market_overview = MarketOverview(
            summary=(
                f"{len(records)} article(s) analyzed. "
                f"{len(market_intelligence.companies)} companies, "
                f"{len(market_intelligence.sectors)} sectors, and "
                f"{len(market_intelligence.countries)} countries detected. "
                f"{len(relationship_graph.edges)} relationships and "
                f"{len(evidence_graph.items)} evidence items identified."
            ),
            overall_sentiment=None,  # no sentiment analysis exists anywhere in this pipeline
            key_metrics={
                "companies_detected": float(len(market_intelligence.companies)),
                "sectors_detected": float(len(market_intelligence.sectors)),
                "countries_detected": float(len(market_intelligence.countries)),
                "relationships_detected": float(len(relationship_graph.edges)),
                "evidence_items": float(len(evidence_graph.items)),
            },
        )

        return MorningIntelligence(
            date=context.started_at.date(),
            title=None,
            market_overview=market_overview,
            headlines=headlines,
            stocks_to_watch=[],
            sector_watch=[],
            global_markets=[],
            risk_alerts=[],
            sources=sources,
        )

    def _build_headlines(self, records: list[KnowledgeRecord]) -> list[Headline]:
        """Map records with a title and a parseable published_at into Headlines.

        A record missing either is skipped rather than given a fabricated
        title or timestamp.
        """
        headlines: list[Headline] = []
        for record in records:
            if not record.title:
                continue
            published_at = parse_published_at(record.published_at)
            if published_at is None:
                continue
            headlines.append(
                Headline(
                    title=record.title,
                    source=SourceRef(name=self._resolve_source_name(record)),
                    published_at=published_at,
                    url=record.url,
                    summary=record.text,
                )
            )
        return headlines

    def _build_sources(self, records: list[KnowledgeRecord]) -> list[SourceRef]:
        """Deduplicated, sorted list of sources cited across `records`."""
        seen: dict[str, SourceRef] = {}
        for record in records:
            name = self._resolve_source_name(record)
            if name not in seen:
                seen[name] = SourceRef(name=name, url=record.url)
        return sorted(seen.values(), key=lambda source: source.name)

    def _resolve_source_name(self, record: KnowledgeRecord) -> str:
        return (
            record.metadata.get("feed_title")
            or record.metadata.get("source")
            or record.source_provider_id
            or "unknown"
        )
