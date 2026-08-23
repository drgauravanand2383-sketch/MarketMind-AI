"""Morning Intelligence Pipeline — the first end-to-end orchestration workflow.

MorningPipeline coordinates the full chain of already-implemented
components: News Collector → Knowledge Ingestion → Embedding Service →
Embedding Provider → Knowledge Repository → Evidence Engine → Market
Intelligence Engine → Relationship Engine. It contains no business logic
and duplicates no component's internal behavior — it only sequences calls
in the documented order, threads each stage's output into the next,
preserves an ExecutionContext across the run, collects per-stage metrics,
and stops on the first fatal (exception-raising) stage failure.

The RSS Provider stage in the pipeline diagram is not a separate call made
by this orchestrator: NewsCollectorAgent resolves and invokes its
configured providers (including RSSProvider) internally, via its own
injected ProviderRegistry, per its existing contract (Sprint 11). Wiring
RSSProvider into that registry is the caller's responsibility when
constructing the NewsCollectorAgent passed into this pipeline.

`execute(context)` is the canonical entry point (WorkflowProtocol, Sprint
29). Prior to that standardization this pipeline built its own
ExecutionContext internally (a fresh execution_id per run); it now
requires the caller to supply one, read-only, and derives
`execution_id`/`trace_id` from it instead. The `context` parameter itself
is never reassigned — a separate local variable (`working_context`) holds
each `dataclasses.replace()`-derived snapshot used to build the returned
result's `final_context`, exactly as before this refactor. `run()` is
retained for backward compatibility and delegates to the same private
implementation `execute()` uses.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime
from types import MappingProxyType

from pydantic import BaseModel

from app.agents.news_collector.agent import NewsCollectorAgent
from app.agents.news_collector.models import NewsCollectionRequest, NewsCollectionResult
from app.core.context import ExecutionContext, ExecutionError, WorkflowStatus
from app.providers.embedding.models import EmbeddingResult
from app.providers.embedding.provider import BaseEmbeddingProvider
from app.repositories.knowledge.models import KnowledgeRecord, SaveResult
from app.repositories.knowledge.repository import BaseKnowledgeRepository
from app.services.embedding.service import EmbeddingService
from app.services.evidence_engine.engine import EvidenceEngine
from app.services.knowledge_ingestion.models import IngestionBatch, RejectionReason
from app.services.knowledge_ingestion.service import KnowledgeIngestionService
from app.services.market_intelligence.engine import MarketIntelligenceEngine
from app.services.relationship_engine.engine import RelationshipEngine
from app.workflows.morning_pipeline.models import PipelineResult, PipelineStatus, StageMetric

__all__ = ["MorningPipeline"]

_logger = logging.getLogger("marketmind.workflows.morning_pipeline")

# Retained as a reference constant (naming the eight stages this pipeline
# advances through `agent_outputs`) even though, since this pipeline no
# longer constructs its own ExecutionContext, nothing in this module uses
# it to build one anymore. Existing tests still import it for assertions.
PARTICIPATING_STAGES = (
    "news_collector",
    "knowledge_ingestion",
    "embedding_service",
    "embedding_provider",
    "knowledge_repository",
    "evidence_engine",
    "market_intelligence_engine",
    "relationship_engine",
)


class MorningPipeline:
    """Coordinates the end-to-end Morning Intelligence Pipeline.

    Every component is injected; this class constructs none of them and
    performs no reasoning, no LLM calls, and no report generation of its
    own — it only sequences the calls already documented on each
    component's own contract.
    """

    def __init__(
        self,
        news_collector: NewsCollectorAgent,
        ingestion_service: KnowledgeIngestionService,
        embedding_service: EmbeddingService,
        embedding_provider: BaseEmbeddingProvider,
        knowledge_repository: BaseKnowledgeRepository,
        evidence_engine: EvidenceEngine,
        market_intelligence_engine: MarketIntelligenceEngine,
        relationship_engine: RelationshipEngine,
    ) -> None:
        """Initialize the pipeline with every stage's already-configured component.

        Args:
            news_collector: AGT-003, configured with whichever providers
                (e.g. RSSProvider) should run for this deployment.
            ingestion_service: Prepares normalized NewsItems for storage.
            embedding_service: Batches VectorDocuments into EmbeddingRequests.
            embedding_provider: Generates embeddings for those requests.
            knowledge_repository: Persists and retrieves knowledge records.
            evidence_engine: Builds evidence references from stored records.
            market_intelligence_engine: Analyzes stored records deterministically.
            relationship_engine: Extracts relationships from that analysis.
        """
        self._news_collector = news_collector
        self._ingestion_service = ingestion_service
        self._embedding_service = embedding_service
        self._embedding_provider = embedding_provider
        self._knowledge_repository = knowledge_repository
        self._evidence_engine = evidence_engine
        self._market_intelligence_engine = market_intelligence_engine
        self._relationship_engine = relationship_engine

    async def execute(self, context: ExecutionContext) -> PipelineResult:
        """The canonical WorkflowProtocol entry point (Sprint 29).

        Runs with the default (unfiltered) NewsCollectionRequest. Callers
        needing a customized request should use `run(context, news_request)`
        instead — the WorkflowProtocol's fixed single-argument signature
        has no room for it here.

        Args:
            context: The caller-provided ExecutionContext. Read-only:
                never mutated or reassigned by this pipeline.

        Returns:
            A PipelineResult. See `_execute_impl` for details.
        """
        return await self._execute_impl(context, news_request=None)

    async def run(
        self, context: ExecutionContext, news_request: NewsCollectionRequest | None = None
    ) -> PipelineResult:
        """Retained for backward compatibility; prefer `execute(context)`.

        Delegates to the same private implementation `execute()` uses
        (`_execute_impl`) — no orchestration logic is duplicated between
        the two public methods.

        Note: prior to Sprint 30's interface standardization, `run()` took
        `trigger`/`initiated_by` and built its own ExecutionContext
        internally. Every workflow must now accept an externally-supplied,
        read-only ExecutionContext instead (WorkflowProtocol), so `run()`
        now also requires `context` and no longer constructs one. This is
        the one unavoidable signature change this refactor required; the
        eight-stage orchestration logic itself is unchanged.

        Args:
            context: The caller-provided ExecutionContext. Read-only.
            news_request: The request to pass to the News Collector.
                Defaults to an unfiltered NewsCollectionRequest.

        Returns:
            A PipelineResult. See `_execute_impl` for details.
        """
        return await self._execute_impl(context, news_request)

    async def _execute_impl(
        self, context: ExecutionContext, news_request: NewsCollectionRequest | None
    ) -> PipelineResult:
        """The pipeline's single orchestration implementation.

        Both `execute()` and `run()` delegate here. `context` (the
        parameter) is never reassigned; `working_context` holds each
        `dataclasses.replace()`-derived snapshot used to build the
        returned result's `final_context` — the same context-advancing
        pattern this pipeline used before Sprint 30, just built on top of
        a caller-supplied starting point instead of a self-generated one.

        Returns:
            A PipelineResult: COMPLETED with every stage's downstream
            artifacts, or FAILED at the first stage that raised an
            exception, with everything produced up to that point preserved
            in `stage_metrics` and `final_context`.
        """
        started_at = datetime.now(UTC)
        execution_id = context.execution_id
        working_context = context
        stage_metrics: list[StageMetric] = []
        request = news_request if news_request is not None else NewsCollectionRequest()

        _logger.info("ingestion_run_started", extra={"execution_id": execution_id})

        # Stage 1: News Collector (internally invokes RSS Provider, and any
        # other registered providers, via its own ProviderRegistry).
        stage_started = datetime.now(UTC)
        try:
            collection_result = await self._news_collector.run(working_context, request)
        except Exception as exc:  # noqa: BLE001 - a fatal stage failure, recorded and halted
            return self._halt(
                execution_id, started_at, stage_metrics, working_context, "news_collector", stage_started, exc
            )
        stage_metrics.append(self._metric("news_collector", stage_started, True))
        working_context = self._advance(working_context, "news_collector", collection_result)

        # Stage 2: Knowledge Ingestion
        stage_started = datetime.now(UTC)
        try:
            ingestion_batch = self._ingestion_service.prepare_batch(collection_result)
        except Exception as exc:  # noqa: BLE001
            return self._halt(
                execution_id, started_at, stage_metrics, working_context, "knowledge_ingestion", stage_started, exc
            )
        stage_metrics.append(self._metric("knowledge_ingestion", stage_started, True))
        working_context = self._advance(working_context, "knowledge_ingestion", ingestion_batch)

        # Stage 3: Embedding Service
        stage_started = datetime.now(UTC)
        try:
            embedding_batch = self._embedding_service.prepare_batch(ingestion_batch.vector_documents)
        except Exception as exc:  # noqa: BLE001
            return self._halt(
                execution_id, started_at, stage_metrics, working_context, "embedding_service", stage_started, exc
            )
        stage_metrics.append(self._metric("embedding_service", stage_started, True))
        working_context = self._advance(working_context, "embedding_service", embedding_batch)

        # Stage 4: Embedding Provider
        stage_started = datetime.now(UTC)
        try:
            embedding_result = await self._embedding_provider.generate(embedding_batch)
        except Exception as exc:  # noqa: BLE001
            return self._halt(
                execution_id, started_at, stage_metrics, working_context, "embedding_provider", stage_started, exc
            )
        stage_metrics.append(self._metric("embedding_provider", stage_started, True))
        working_context = self._advance(working_context, "embedding_provider", embedding_result)

        # Stage 5: Knowledge Repository (save this run's batch, then read
        # back the records it just persisted, for the stages that follow).
        stage_started = datetime.now(UTC)
        try:
            save_result = await self._knowledge_repository.save_batch(ingestion_batch, embedding_batch)
            records = await self._fetch_saved_records(ingestion_batch)
        except Exception as exc:  # noqa: BLE001
            return self._halt(
                execution_id, started_at, stage_metrics, working_context, "knowledge_repository", stage_started, exc
            )
        stage_metrics.append(self._metric("knowledge_repository", stage_started, True))
        working_context = self._advance(working_context, "knowledge_repository", save_result)

        # Stage 6: Evidence Engine
        stage_started = datetime.now(UTC)
        try:
            evidence_graph = self._evidence_engine.build_graph(records)
        except Exception as exc:  # noqa: BLE001
            return self._halt(
                execution_id, started_at, stage_metrics, working_context, "evidence_engine", stage_started, exc
            )
        stage_metrics.append(self._metric("evidence_engine", stage_started, True))
        working_context = self._advance(working_context, "evidence_engine", evidence_graph)

        # Stage 7: Market Intelligence Engine
        stage_started = datetime.now(UTC)
        try:
            market_intelligence = self._market_intelligence_engine.analyze(records)
        except Exception as exc:  # noqa: BLE001
            return self._halt(
                execution_id,
                started_at,
                stage_metrics,
                working_context,
                "market_intelligence_engine",
                stage_started,
                exc,
            )
        stage_metrics.append(self._metric("market_intelligence_engine", stage_started, True))
        working_context = self._advance(working_context, "market_intelligence_engine", market_intelligence)

        # Stage 8: Relationship Engine
        stage_started = datetime.now(UTC)
        try:
            relationship_graph = self._relationship_engine.build_graph(market_intelligence)
        except Exception as exc:  # noqa: BLE001
            return self._halt(
                execution_id, started_at, stage_metrics, working_context, "relationship_engine", stage_started, exc
            )
        stage_metrics.append(self._metric("relationship_engine", stage_started, True))
        working_context = self._advance(working_context, "relationship_engine", relationship_graph)
        working_context = replace(working_context, status=WorkflowStatus.COMPLETED)

        self._log_run_completed(
            execution_id, started_at, collection_result, ingestion_batch, embedding_result, save_result
        )

        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            execution_id=execution_id,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            stage_metrics=stage_metrics,
            final_context=working_context,
            evidence_graph=evidence_graph,
            market_intelligence=market_intelligence,
            relationship_graph=relationship_graph,
        )

    def _log_run_completed(
        self,
        execution_id: str,
        started_at: datetime,
        collection_result: NewsCollectionResult,
        ingestion_batch: IngestionBatch,
        embedding_result: EmbeddingResult,
        save_result: SaveResult,
    ) -> None:
        """One structured summary line per successful run — covers every
        count this milestone's observability requirements ask for
        (articles fetched, deduplicated, persisted, embedded, and how many
        resolved to a known entity — currently always zero, since no
        entity-resolution mechanism exists yet; recorded honestly rather
        than omitted, see `KnowledgeIngestionService`).

        `providers_*` counts summarize at the *provider* level
        (`NewsCollectionResult.provider_summary` — one entry per
        configured news source, e.g. "rss"), the only granularity
        `NewsCollectorAgent` exposes upward; per-individual-feed-URL
        success/failure is logged separately, at the point it's actually
        known, as `rss_feed_fetched`/`rss_feed_fetch_failed`
        (`app.providers.rss.provider`)."""
        deduplicated = sum(
            1 for item in ingestion_batch.ingestion_metadata.rejected_items
            if item.reason == RejectionReason.DUPLICATE_ID
        )
        entity_resolved = sum(
            1 for doc in ingestion_batch.vector_documents
            if doc.metadata.get("entity_resolved") is True
        )
        duration_seconds = (datetime.now(UTC) - started_at).total_seconds()
        provider_summary = collection_result.provider_summary

        _logger.info(
            "ingestion_run_completed",
            extra={
                "execution_id": execution_id,
                "providers_attempted": len(provider_summary),
                "providers_succeeded": sum(1 for s in provider_summary if s.success),
                "providers_failed": sum(1 for s in provider_summary if not s.success),
                "articles_fetched": len(collection_result.items),
                "articles_deduplicated": deduplicated,
                "articles_rejected_total": len(ingestion_batch.ingestion_metadata.rejected_items),
                "articles_persisted": save_result.vector_count,
                "embeddings_generated": embedding_result.total_succeeded,
                "embedding_failures": embedding_result.total_failed,
                "entity_resolved_count": entity_resolved,
                "entity_unresolved_count": len(ingestion_batch.vector_documents) - entity_resolved,
                "duration_seconds": duration_seconds,
            },
        )

    async def _fetch_saved_records(self, ingestion_batch: IngestionBatch) -> list[KnowledgeRecord]:
        """Read back every record this run just saved, skipping any that weren't found."""
        records: list[KnowledgeRecord] = []
        for relational_record in ingestion_batch.relational_records:
            record = await self._knowledge_repository.get(relational_record.id)
            if record is not None:
                records.append(record)
        return records

    def _metric(
        self, stage_name: str, started_at: datetime, succeeded: bool, error: str | None = None
    ) -> StageMetric:
        return StageMetric(
            stage_name=stage_name,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            succeeded=succeeded,
            error=error,
        )

    def _advance(self, context: ExecutionContext, stage_name: str, output: BaseModel) -> ExecutionContext:
        """Advance the ExecutionContext to reflect one completed stage."""
        updated_outputs = dict(context.agent_outputs)
        updated_outputs[stage_name] = output
        return replace(
            context,
            current_agent=stage_name,
            agent_outputs=MappingProxyType(updated_outputs),
        )

    def _halt(
        self,
        execution_id: str,
        started_at: datetime,
        stage_metrics: list[StageMetric],
        context: ExecutionContext,
        stage_name: str,
        stage_started: datetime,
        error: Exception,
    ) -> PipelineResult:
        """Record a fatal stage failure and produce the terminal FAILED PipelineResult."""
        _logger.error(
            "ingestion_run_failed",
            extra={"execution_id": execution_id, "failed_stage": stage_name, "error": str(error)},
        )
        stage_metrics.append(self._metric(stage_name, stage_started, False, str(error)))
        execution_error = ExecutionError(
            agent_id=stage_name,
            error_type=type(error).__name__,
            error_message=str(error),
            occurred_at=datetime.now(UTC),
        )
        context = replace(
            context,
            current_agent=stage_name,
            errors=(*context.errors, execution_error),
            status=WorkflowStatus.FAILED,
        )
        return PipelineResult(
            status=PipelineStatus.FAILED,
            execution_id=execution_id,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            stage_metrics=stage_metrics,
            final_context=context,
            failed_stage=stage_name,
            error=str(error),
        )
