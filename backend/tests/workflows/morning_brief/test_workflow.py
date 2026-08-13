"""Tests for MorningBriefWorkflow.

Covers successful execution, no embedding provider configured, news
collection failure, repository failure, report generation failure, and
empty news collection. No PostgreSQL, ChromaDB, RSS feed, or embedding API
is required anywhere — only mocks and pytest's `tmp_path`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app.agents.morning_brief_generator.generator import MorningBriefGenerator
from app.workflows.engine import WorkflowEngine, WorkflowProtocol
from tests.workflows.morning_brief.conftest import (
    build_workflow,
    context,
    embedding_result,
    knowledge_record,
    mock_embedding_provider,
    mock_knowledge_hub,
    mock_knowledge_repository,
    mock_news_collector,
    news_collection_result,
    news_item,
    save_result,
)

# --- Successful execution -----------------------------------------------------------


async def test_successful_execution_writes_report_and_reports_all_counts(
    tmp_path: Path,
) -> None:
    collector = mock_news_collector()
    collector.run.return_value = news_collection_result(
        [
            news_item("item-1", "Apple reports record iPhone sales", "Apple Inc. earnings beat."),
            news_item("item-2", "Tesla unveils new EV model", "Tesla Inc. announced a new lineup."),
        ]
    )

    repository = mock_knowledge_repository()
    repository.save_batch.return_value = save_result(relational_count=2)

    hub = mock_knowledge_hub()
    hub.query.return_value = [
        knowledge_record("item-1", "Apple reports record iPhone sales", "Apple Inc. earnings beat."),
        knowledge_record("item-2", "Tesla unveils new EV model", "Tesla Inc. announced a new lineup."),
    ]

    provider = mock_embedding_provider()
    provider.generate.return_value = embedding_result(total_succeeded=2)

    workflow = build_workflow(
        tmp_path,
        news_collector=collector,
        knowledge_repository=repository,
        knowledge_hub=hub,
        embedding_provider=provider,
    )

    result = await workflow.run(context())

    assert result.success is True
    assert result.articles_processed == 2
    assert result.articles_persisted == 2
    assert result.embeddings_generated == 2
    assert result.execution_time >= 0
    assert result.report_path is not None
    assert Path(result.report_path).exists()
    assert Path(result.report_path).read_text(encoding="utf-8").startswith("#")


async def test_successful_execution_calls_repository_save_batch(tmp_path: Path) -> None:
    collector = mock_news_collector()
    collector.run.return_value = news_collection_result(
        [news_item("item-1", "Apple earnings", "Apple Inc. results.")]
    )
    repository = mock_knowledge_repository()
    repository.save_batch.return_value = save_result(relational_count=1)
    hub = mock_knowledge_hub()
    hub.query.return_value = []

    workflow = build_workflow(
        tmp_path, news_collector=collector, knowledge_repository=repository, knowledge_hub=hub
    )

    await workflow.run(context())

    repository.save_batch.assert_awaited_once()


# --- No embedding provider configured -----------------------------------------------------------


async def test_no_embedding_provider_configured_skips_embedding_step(tmp_path: Path) -> None:
    collector = mock_news_collector()
    collector.run.return_value = news_collection_result(
        [news_item("item-1", "Apple earnings", "Apple Inc. results.")]
    )
    repository = mock_knowledge_repository()
    repository.save_batch.return_value = save_result(relational_count=1)
    hub = mock_knowledge_hub()
    hub.query.return_value = []

    workflow = build_workflow(
        tmp_path,
        news_collector=collector,
        knowledge_repository=repository,
        knowledge_hub=hub,
        embedding_provider=None,
    )

    result = await workflow.run(context())

    assert result.success is True
    assert result.embeddings_generated == 0


# --- News collection failure -----------------------------------------------------------


async def test_news_collection_failure_stops_immediately(tmp_path: Path) -> None:
    collector = mock_news_collector()
    collector.run.side_effect = RuntimeError("simulated news collector failure")

    workflow = build_workflow(tmp_path, news_collector=collector)

    result = await workflow.run(context())

    assert result.success is False
    assert result.articles_processed == 0
    assert result.articles_persisted == 0
    assert result.report_path is None


async def test_news_collection_failure_does_not_call_repository(tmp_path: Path) -> None:
    collector = mock_news_collector()
    collector.run.side_effect = RuntimeError("simulated news collector failure")
    repository = mock_knowledge_repository()

    workflow = build_workflow(tmp_path, news_collector=collector, knowledge_repository=repository)

    await workflow.run(context())

    repository.save_batch.assert_not_awaited()


# --- Repository failure -----------------------------------------------------------


async def test_repository_failure_stops_after_collection_succeeds(tmp_path: Path) -> None:
    collector = mock_news_collector()
    collector.run.return_value = news_collection_result(
        [news_item("item-1", "Apple earnings", "Apple Inc. results.")]
    )
    repository = mock_knowledge_repository()
    repository.save_batch.side_effect = RuntimeError("simulated repository failure")

    workflow = build_workflow(tmp_path, news_collector=collector, knowledge_repository=repository)

    result = await workflow.run(context())

    assert result.success is False
    assert result.articles_processed == 1  # collection succeeded before the failure
    assert result.articles_persisted == 0  # persistence never completed
    assert result.report_path is None


async def test_repository_failure_does_not_query_knowledge_hub(tmp_path: Path) -> None:
    collector = mock_news_collector()
    collector.run.return_value = news_collection_result(
        [news_item("item-1", "Apple earnings", "Apple Inc. results.")]
    )
    repository = mock_knowledge_repository()
    repository.save_batch.side_effect = RuntimeError("simulated repository failure")
    hub = mock_knowledge_hub()

    workflow = build_workflow(
        tmp_path, news_collector=collector, knowledge_repository=repository, knowledge_hub=hub
    )

    await workflow.run(context())

    hub.query.assert_not_awaited()


# --- Report generation failure -----------------------------------------------------------


async def test_report_generation_failure_still_reports_earlier_counts(tmp_path: Path) -> None:
    collector = mock_news_collector()
    collector.run.return_value = news_collection_result(
        [news_item("item-1", "Apple earnings", "Apple Inc. results.")]
    )
    repository = mock_knowledge_repository()
    repository.save_batch.return_value = save_result(relational_count=1)
    hub = mock_knowledge_hub()
    hub.query.return_value = [knowledge_record("item-1", "Apple earnings", "Apple Inc. results.")]

    broken_generator = MagicMock(spec=MorningBriefGenerator)
    broken_generator.generate.side_effect = RuntimeError("simulated disk failure")

    workflow = build_workflow(
        tmp_path,
        news_collector=collector,
        knowledge_repository=repository,
        knowledge_hub=hub,
        report_generator=broken_generator,
    )

    result = await workflow.run(context())

    assert result.success is False
    assert result.articles_processed == 1
    assert result.articles_persisted == 1
    assert result.report_path is None


# --- Empty news collection -----------------------------------------------------------


async def test_empty_news_collection_still_completes_successfully(tmp_path: Path) -> None:
    collector = mock_news_collector()
    collector.run.return_value = news_collection_result([])
    repository = mock_knowledge_repository()
    repository.save_batch.return_value = save_result(relational_count=0)
    hub = mock_knowledge_hub()
    hub.query.return_value = []

    workflow = build_workflow(
        tmp_path, news_collector=collector, knowledge_repository=repository, knowledge_hub=hub
    )

    result = await workflow.run(context())

    assert result.success is True
    assert result.articles_processed == 0
    assert result.articles_persisted == 0
    assert result.report_path is not None
    assert Path(result.report_path).exists()


async def test_empty_news_collection_report_shows_no_data_placeholders(tmp_path: Path) -> None:
    collector = mock_news_collector()
    collector.run.return_value = news_collection_result([])
    repository = mock_knowledge_repository()
    repository.save_batch.return_value = save_result(relational_count=0)
    hub = mock_knowledge_hub()
    hub.query.return_value = []

    workflow = build_workflow(
        tmp_path, news_collector=collector, knowledge_repository=repository, knowledge_hub=hub
    )

    result = await workflow.run(context())

    report_text = Path(result.report_path).read_text(encoding="utf-8")
    assert "_No headlines available._" in report_text
    assert "_No stocks flagged._" in report_text


# --- ExecutionContext is never mutated -----------------------------------------------------------


async def test_execution_context_is_not_mutated(tmp_path: Path) -> None:
    collector = mock_news_collector()
    collector.run.return_value = news_collection_result([])
    repository = mock_knowledge_repository()
    repository.save_batch.return_value = save_result(relational_count=0)
    hub = mock_knowledge_hub()
    hub.query.return_value = []

    workflow = build_workflow(
        tmp_path, news_collector=collector, knowledge_repository=repository, knowledge_hub=hub
    )
    original_context = context()

    await workflow.run(original_context)

    # The same object is forwarded to NewsCollectorAgent.run(), never replaced or mutated.
    collector.run.assert_awaited_once()
    forwarded_context = collector.run.call_args.args[0]
    assert forwarded_context is original_context


# --- WorkflowProtocol conformance (Sprint 30) -----------------------------------------------------


def test_morning_brief_workflow_satisfies_workflow_protocol(tmp_path: Path) -> None:
    workflow = build_workflow(tmp_path)
    assert isinstance(workflow, WorkflowProtocol)


# --- WorkflowEngine integration (Sprint 30) -----------------------------------------------------


async def test_workflow_engine_executes_morning_brief_workflow_directly(tmp_path: Path) -> None:
    """No adapter or wrapper class — the real MorningBriefWorkflow is registered as-is."""
    collector = mock_news_collector()
    collector.run.return_value = news_collection_result([])
    repository = mock_knowledge_repository()
    repository.save_batch.return_value = save_result(relational_count=0)
    hub = mock_knowledge_hub()
    hub.query.return_value = []

    workflow = build_workflow(
        tmp_path, news_collector=collector, knowledge_repository=repository, knowledge_hub=hub
    )
    engine = WorkflowEngine()
    engine.register_workflow("morning_brief", workflow)

    result = await engine.execute("morning_brief", context())

    assert result.success is True
    assert result.output.success is True
    assert result.workflow_id == "morning_brief"


# --- run() backward compatibility (Sprint 30) -----------------------------------------------------


async def test_run_and_execute_produce_equivalent_results(tmp_path: Path) -> None:
    collector = mock_news_collector()
    collector.run.return_value = news_collection_result(
        [news_item("item-1", "Apple earnings", "Apple Inc. results.")]
    )
    repository = mock_knowledge_repository()
    repository.save_batch.return_value = save_result(relational_count=1)
    hub = mock_knowledge_hub()
    hub.query.return_value = [knowledge_record("item-1", "Apple earnings", "Apple Inc. results.")]

    workflow_for_run = build_workflow(
        tmp_path, news_collector=collector, knowledge_repository=repository, knowledge_hub=hub
    )

    collector_2 = mock_news_collector()
    collector_2.run.return_value = news_collection_result(
        [news_item("item-1", "Apple earnings", "Apple Inc. results.")]
    )
    repository_2 = mock_knowledge_repository()
    repository_2.save_batch.return_value = save_result(relational_count=1)
    hub_2 = mock_knowledge_hub()
    hub_2.query.return_value = [knowledge_record("item-1", "Apple earnings", "Apple Inc. results.")]

    workflow_for_execute = build_workflow(
        tmp_path, news_collector=collector_2, knowledge_repository=repository_2, knowledge_hub=hub_2
    )

    run_result = await workflow_for_run.run(context())
    execute_result = await workflow_for_execute.execute(context())

    assert run_result.success == execute_result.success is True
    assert run_result.articles_processed == execute_result.articles_processed == 1
    assert run_result.articles_persisted == execute_result.articles_persisted == 1


async def test_run_still_accepts_a_custom_news_request(tmp_path: Path) -> None:
    from app.agents.news_collector.models import NewsCollectionRequest

    collector = mock_news_collector()
    collector.run.return_value = news_collection_result([])
    repository = mock_knowledge_repository()
    repository.save_batch.return_value = save_result(relational_count=0)
    hub = mock_knowledge_hub()
    hub.query.return_value = []

    workflow = build_workflow(
        tmp_path, news_collector=collector, knowledge_repository=repository, knowledge_hub=hub
    )

    result = await workflow.run(context(), news_request=NewsCollectionRequest(provider_ids=["rss"]))

    assert result.success is True
