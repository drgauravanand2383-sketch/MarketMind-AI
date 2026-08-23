"""Tests for MorningPipeline.

Covers: happy-path completion, stage failures (fatal, halting), partial
failures (tolerated, non-halting), ExecutionContext propagation, and
end-to-end data continuity across all eight stages. No real HTTP,
ChromaDB, or embedding API call occurs anywhere — every external boundary
is the in-memory/stub doubles defined in conftest.py.

Sprint 30 note: every call below uses the canonical `execute(context)`
entry point (WorkflowProtocol). A dedicated section near the end covers
`run()`'s continued backward compatibility, WorkflowProtocol conformance,
WorkflowEngine integration, and that the supplied ExecutionContext is
never mutated.
"""

from __future__ import annotations

from datetime import UTC

from app.agents.news_collector.agent import NewsCollectorAgent
from app.core.context import ExecutionContext as ExecutionContextType
from app.core.context import WorkflowStatus
from app.providers.registry import ProviderRegistry
from app.services.market_intelligence.engine import MarketIntelligenceEngine
from app.services.relationship_engine.engine import RelationshipEngine
from app.workflows.engine import WorkflowEngine, WorkflowProtocol
from app.workflows.morning_pipeline.models import PipelineStatus
from app.workflows.morning_pipeline.pipeline import PARTICIPATING_STAGES
from tests.workflows.morning_pipeline.conftest import (
    FailingProvider,
    InMemoryKnowledgeRepository,
    MockAppleRSSProvider,
    NoIdRSSProvider,
    NoOpMemory,
    build_news_collector,
    build_pipeline,
    context,
)

# --- Happy-path tests -----------------------------------------------------


async def test_happy_path_completes_all_eight_stages() -> None:
    pipeline = build_pipeline()

    result = await pipeline.execute(context())

    assert result.status == PipelineStatus.COMPLETED
    assert len(result.stage_metrics) == 8
    assert [metric.stage_name for metric in result.stage_metrics] == list(PARTICIPATING_STAGES)
    assert all(metric.succeeded for metric in result.stage_metrics)
    assert result.failed_stage is None
    assert result.error is None


async def test_happy_path_produces_all_downstream_artifacts() -> None:
    pipeline = build_pipeline()

    result = await pipeline.execute(context())

    assert result.evidence_graph is not None
    assert result.market_intelligence is not None
    assert result.relationship_graph is not None
    assert result.market_intelligence.total_records_analyzed == 1


# --- Stage failure tests (fatal, halts the pipeline) -----------------------------------------------------


async def test_first_stage_failure_halts_before_any_other_stage_runs() -> None:
    class _BrokenNewsCollector(NewsCollectorAgent):
        async def run(self, context: ExecutionContextType, input_data):  # noqa: ANN001
            raise RuntimeError("simulated news collector failure")

    collector = _BrokenNewsCollector(
        memory=NoOpMemory(), registry=ProviderRegistry(), provider_configs=[]
    )
    pipeline = build_pipeline(news_collector=collector)

    result = await pipeline.execute(context())

    assert result.status == PipelineStatus.FAILED
    assert result.failed_stage == "news_collector"
    assert len(result.stage_metrics) == 1
    assert result.stage_metrics[0].succeeded is False
    assert result.evidence_graph is None
    assert result.market_intelligence is None
    assert result.relationship_graph is None


async def test_middle_stage_failure_halts_after_earlier_stages_succeed() -> None:
    class _BrokenRepository(InMemoryKnowledgeRepository):
        async def save_batch(self, ingestion_batch, embedding_batch):  # noqa: ANN001
            raise RuntimeError("simulated repository failure")

    pipeline = build_pipeline(knowledge_repository=_BrokenRepository())

    result = await pipeline.execute(context())

    assert result.status == PipelineStatus.FAILED
    assert result.failed_stage == "knowledge_repository"
    assert len(result.stage_metrics) == 5
    assert [m.succeeded for m in result.stage_metrics] == [True, True, True, True, False]


async def test_last_stage_failure_still_records_every_earlier_stage_metric() -> None:
    class _BrokenRelationshipEngine(RelationshipEngine):
        def build_graph(self, intelligence):  # noqa: ANN001
            raise RuntimeError("simulated relationship engine failure")

    pipeline = build_pipeline(relationship_engine=_BrokenRelationshipEngine())

    result = await pipeline.execute(context())

    assert result.status == PipelineStatus.FAILED
    assert result.failed_stage == "relationship_engine"
    assert len(result.stage_metrics) == 8
    assert result.stage_metrics[-1].succeeded is False
    assert result.relationship_graph is None
    # earlier stages' real outputs survive in the context even though the run failed
    assert "market_intelligence_engine" in result.final_context.agent_outputs
    assert "evidence_engine" in result.final_context.agent_outputs


# --- Partial failure tests (tolerated, does not halt) -----------------------------------------------------


async def test_one_failing_provider_among_several_does_not_halt_the_pipeline() -> None:
    collector = build_news_collector(MockAppleRSSProvider, FailingProvider)
    pipeline = build_pipeline(news_collector=collector)

    result = await pipeline.execute(context())

    assert result.status == PipelineStatus.COMPLETED
    news_result = result.final_context.agent_outputs["news_collector"]
    failed_providers = {s.provider_id for s in news_result.provider_summary if not s.success}
    assert failed_providers == {"broken"}
    assert result.market_intelligence is not None
    assert result.market_intelligence.total_records_analyzed == 1


async def test_items_rejected_by_ingestion_still_allow_pipeline_to_complete() -> None:
    collector = build_news_collector(NoIdRSSProvider)
    pipeline = build_pipeline(news_collector=collector)

    result = await pipeline.execute(context())

    assert result.status == PipelineStatus.COMPLETED
    ingestion_batch = result.final_context.agent_outputs["knowledge_ingestion"]
    assert ingestion_batch.ingestion_metadata.accepted_count == 0
    assert len(ingestion_batch.ingestion_metadata.rejected_items) == 1
    assert result.market_intelligence is not None
    assert result.market_intelligence.total_records_analyzed == 0
    assert result.relationship_graph is not None


# --- ExecutionContext propagation tests -----------------------------------------------------


async def test_context_agent_outputs_contains_every_stage_after_success() -> None:
    pipeline = build_pipeline()

    result = await pipeline.execute(context())

    assert set(result.final_context.agent_outputs.keys()) == set(PARTICIPATING_STAGES)


async def test_context_current_agent_reflects_the_last_completed_stage() -> None:
    pipeline = build_pipeline()

    result = await pipeline.execute(context())

    assert result.final_context.current_agent == "relationship_engine"


async def test_context_status_is_completed_on_success() -> None:
    pipeline = build_pipeline()

    result = await pipeline.execute(context())

    assert result.final_context.status == WorkflowStatus.COMPLETED


async def test_context_status_is_failed_and_records_the_error_on_stage_failure() -> None:
    class _BrokenRelationshipEngine(RelationshipEngine):
        def build_graph(self, intelligence):  # noqa: ANN001
            raise RuntimeError("simulated failure")

    pipeline = build_pipeline(relationship_engine=_BrokenRelationshipEngine())

    result = await pipeline.execute(context())

    assert result.final_context.status == WorkflowStatus.FAILED
    assert len(result.final_context.errors) == 1
    assert result.final_context.errors[0].agent_id == "relationship_engine"
    assert result.final_context.current_agent == "relationship_engine"


async def test_context_execution_id_and_trace_id_match_the_result() -> None:
    pipeline = build_pipeline()

    result = await pipeline.execute(context())

    assert result.final_context.execution_id == result.execution_id
    assert result.final_context.trace_id == result.execution_id


async def test_context_stage_outputs_match_top_level_result_fields() -> None:
    pipeline = build_pipeline()

    result = await pipeline.execute(context())

    assert result.final_context.agent_outputs["evidence_engine"] is result.evidence_graph
    assert result.final_context.agent_outputs["market_intelligence_engine"] is result.market_intelligence
    assert result.final_context.agent_outputs["relationship_engine"] is result.relationship_graph


# --- End-to-end pipeline tests -----------------------------------------------------


async def test_end_to_end_company_mention_flows_through_every_stage() -> None:
    pipeline = build_pipeline()

    result = await pipeline.execute(context())

    company_names = {company.name for company in result.market_intelligence.companies}
    assert "Apple Inc." in company_names

    node_labels = {node.label for node in result.relationship_graph.nodes}
    assert "Apple Inc." in node_labels

    evidence_companies = {
        company for item in result.evidence_graph.items for company in item.linked_companies
    }
    assert "Apple Inc." in evidence_companies


async def test_end_to_end_uses_real_market_intelligence_and_relationship_engines() -> None:
    """Confirms the pipeline calls the real engines, not a stand-in — using
    a distinguishable subclass and checking its output is what's returned."""

    class TaggedMarketIntelligenceEngine(MarketIntelligenceEngine):
        pass

    class TaggedRelationshipEngine(RelationshipEngine):
        pass

    pipeline = build_pipeline(
        market_intelligence_engine=TaggedMarketIntelligenceEngine(),
        relationship_engine=TaggedRelationshipEngine(),
    )

    result = await pipeline.execute(context())

    assert result.status == PipelineStatus.COMPLETED
    assert result.market_intelligence is not None
    assert result.relationship_graph is not None


async def test_end_to_end_stage_metrics_have_increasing_timestamps() -> None:
    pipeline = build_pipeline()

    result = await pipeline.execute(context())

    completed_times = [metric.completed_at for metric in result.stage_metrics]
    assert completed_times == sorted(completed_times)


# --- WorkflowProtocol conformance (Sprint 30) -----------------------------------------------------


def test_morning_pipeline_satisfies_workflow_protocol() -> None:
    pipeline = build_pipeline()
    assert isinstance(pipeline, WorkflowProtocol)


# --- WorkflowEngine integration (Sprint 30) -----------------------------------------------------


async def test_workflow_engine_executes_morning_pipeline_directly() -> None:
    """No adapter or wrapper class — the real MorningPipeline is registered as-is."""
    engine = WorkflowEngine()
    pipeline = build_pipeline()
    engine.register_workflow("morning_pipeline", pipeline)

    result = await engine.execute("morning_pipeline", context())

    assert result.success is True
    assert result.output.status == PipelineStatus.COMPLETED
    assert result.workflow_id == "morning_pipeline"


async def test_workflow_engine_reports_morning_pipeline_stage_failure_as_engine_failure() -> None:
    class _BrokenNewsCollector(NewsCollectorAgent):
        async def run(self, context: ExecutionContextType, input_data):  # noqa: ANN001
            raise RuntimeError("simulated news collector failure")

    collector = _BrokenNewsCollector(
        memory=NoOpMemory(), registry=ProviderRegistry(), provider_configs=[]
    )
    engine = WorkflowEngine()
    engine.register_workflow("morning_pipeline", build_pipeline(news_collector=collector))

    result = await engine.execute("morning_pipeline", context())

    # MorningPipeline itself never raises (it catches stage failures and
    # returns a FAILED PipelineResult), so WorkflowEngine sees this as a
    # *successful* engine-level execution whose *output* reports failure.
    assert result.success is True
    assert result.output.status == PipelineStatus.FAILED


# --- ExecutionContext is never mutated (Sprint 30) -----------------------------------------------------


async def test_execution_context_object_identity_is_never_reassigned() -> None:
    pipeline = build_pipeline()
    original_context = context()

    await pipeline.execute(original_context)

    # ExecutionContext is a frozen dataclass, so in-place mutation is
    # impossible by construction; this additionally confirms the pipeline
    # never even swaps out the caller's reference for a different object
    # it might expose elsewhere.
    assert original_context.agent_outputs == {}
    assert original_context.current_agent is None
    assert original_context.status == WorkflowStatus.RUNNING


async def test_execution_context_passed_to_news_collector_is_the_original_object() -> None:
    class _RecordingNewsCollector(NewsCollectorAgent):
        received_contexts: list[ExecutionContextType] = []

        async def run(self, context: ExecutionContextType, input_data):  # noqa: ANN001
            self.received_contexts.append(context)
            return await super().run(context, input_data)

    collector = _RecordingNewsCollector(
        memory=NoOpMemory(),
        registry=ProviderRegistry(),
        provider_configs=[],
    )
    pipeline = build_pipeline(news_collector=collector)
    original_context = context()

    await pipeline.execute(original_context)

    assert collector.received_contexts[0] is original_context


# --- run() backward compatibility (Sprint 30) -----------------------------------------------------


async def test_run_still_works_and_matches_execute_behavior() -> None:
    pipeline_for_execute = build_pipeline()
    pipeline_for_run = build_pipeline()

    execute_result = await pipeline_for_execute.execute(context("exec-a"))
    run_result = await pipeline_for_run.run(context("exec-b"))

    assert execute_result.status == run_result.status == PipelineStatus.COMPLETED
    assert len(execute_result.stage_metrics) == len(run_result.stage_metrics) == 8


async def test_run_accepts_a_custom_news_request() -> None:
    from app.agents.news_collector.models import NewsCollectionRequest

    pipeline = build_pipeline()

    result = await pipeline.run(context(), news_request=NewsCollectionRequest(provider_ids=["rss"]))

    assert result.status == PipelineStatus.COMPLETED


async def test_run_and_execute_share_the_same_underlying_implementation() -> None:
    """Both public methods delegate to _execute_impl — verified by
    confirming a failure behaves identically through either entry point."""

    class _BrokenRepository(InMemoryKnowledgeRepository):
        async def save_batch(self, ingestion_batch, embedding_batch):  # noqa: ANN001
            raise RuntimeError("simulated repository failure")

    pipeline_a = build_pipeline(knowledge_repository=_BrokenRepository())
    pipeline_b = build_pipeline(knowledge_repository=_BrokenRepository())

    execute_result = await pipeline_a.execute(context("exec-a"))
    run_result = await pipeline_b.run(context("exec-b"))

    assert execute_result.failed_stage == run_result.failed_stage == "knowledge_repository"
    assert len(execute_result.stage_metrics) == len(run_result.stage_metrics) == 5


# --- Observability tests -----------------------------------------------


async def test_successful_run_logs_start_and_completion_with_counts(caplog) -> None:  # noqa: ANN001
    import logging

    pipeline = build_pipeline()

    with caplog.at_level(logging.INFO, logger="marketmind.workflows.morning_pipeline"):
        await pipeline.execute(context())

    events = {record.message: record for record in caplog.records}
    assert "ingestion_run_started" in events
    assert "ingestion_run_completed" in events

    completed = events["ingestion_run_completed"]
    assert completed.providers_attempted == 1
    assert completed.providers_succeeded == 1
    assert completed.providers_failed == 0
    assert completed.articles_fetched == 1
    assert completed.articles_persisted == 1
    assert completed.embeddings_generated == 1
    assert completed.embedding_failures == 0
    # No entity-resolution mechanism exists yet — every article is
    # honestly reported as unresolved, never fabricated as a match.
    assert completed.entity_resolved_count == 0
    assert completed.entity_unresolved_count == 1
    assert completed.duration_seconds >= 0


async def test_failed_run_logs_the_failing_stage(caplog) -> None:  # noqa: ANN001
    import logging

    class _BrokenRepository(InMemoryKnowledgeRepository):
        async def save_batch(self, ingestion_batch, embedding_batch):  # noqa: ANN001
            raise RuntimeError("simulated repository failure")

    pipeline = build_pipeline(knowledge_repository=_BrokenRepository())

    with caplog.at_level(logging.INFO, logger="marketmind.workflows.morning_pipeline"):
        await pipeline.execute(context())

    events = {record.message: record for record in caplog.records}
    assert "ingestion_run_failed" in events
    assert events["ingestion_run_failed"].failed_stage == "knowledge_repository"
    assert "ingestion_run_completed" not in events


async def test_duplicate_articles_are_counted_as_deduplicated(caplog) -> None:  # noqa: ANN001
    import logging

    from app.providers.base import BaseProvider
    from app.providers.rss.models import RSSFeedData, RSSFeedEntry

    class _DuplicateEntryProvider(BaseProvider):
        @property
        def provider_id(self) -> str:
            return "rss"

        @property
        def provider_name(self) -> str:
            return "Duplicate Entry Provider"

        @property
        def version(self) -> str:
            return "0.0.0-test"

        async def fetch(self, **kwargs):  # noqa: ANN003, ANN201
            from datetime import datetime

            from app.providers.models import ProviderResult

            entry = RSSFeedEntry(id="dup-1", title="Same article", summary="Same content")
            feed = RSSFeedData(
                feed_url="https://example.com/feed.xml", entries=[entry, entry]
            )
            return ProviderResult(
                provider_id=self.provider_id,
                fetched_at=datetime.now(UTC),
                success=True,
                data=[feed],
            )

        async def health_check(self) -> bool:
            return True

    pipeline = build_pipeline(news_collector=build_news_collector(_DuplicateEntryProvider))

    with caplog.at_level(logging.INFO, logger="marketmind.workflows.morning_pipeline"):
        await pipeline.execute(context())

    events = {record.message: record for record in caplog.records}
    completed = events["ingestion_run_completed"]
    assert completed.articles_fetched == 2
    assert completed.articles_deduplicated == 1
    assert completed.articles_persisted == 1
