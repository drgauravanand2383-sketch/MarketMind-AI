"""Unit tests for NewsCollectorAgent.

Covers: mock provider execution, multi-provider aggregation, partial
provider failure isolation, and empty-result collection.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.agents.news_collector.agent import NewsCollectorAgent
from app.agents.news_collector.models import NewsCollectionRequest, NewsItem
from app.agents.news_collector.normalizer import register_normalizer
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.providers.base import BaseProvider
from app.providers.models import ProviderConfig, ProviderResult
from app.providers.registry import ProviderRegistry
from app.providers.rss.models import RSSFeedData, RSSFeedEntry


class _MockRSSProvider(BaseProvider):
    """Mimics RSSProvider's shape (provider_id="rss") without real I/O."""

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
            title="Fed holds rates steady",
            link="https://example.com/fed",
            summary="The Federal Reserve left interest rates unchanged.",
            published="Mon, 03 Aug 2026 06:00:00 GMT",
            raw={"title": "Fed holds rates steady"},
        )
        feed = RSSFeedData(feed_url="https://example.com/feed.xml", entries=[entry])
        return ProviderResult(
            provider_id=self.provider_id,
            fetched_at=datetime.now(timezone.utc),
            success=True,
            data=[feed],
        )

    async def health_check(self) -> bool:
        return True


class _MockSecondaryProvider(BaseProvider):
    """A second, distinct provider type used to test multi-provider aggregation."""

    @property
    def provider_id(self) -> str:
        return "rss-secondary"

    @property
    def provider_name(self) -> str:
        return "Mock Secondary Provider"

    @property
    def version(self) -> str:
        return "0.0.0-test"

    async def fetch(self, **kwargs: object) -> ProviderResult:
        return ProviderResult(
            provider_id=self.provider_id,
            fetched_at=datetime.now(timezone.utc),
            success=True,
            data=[],
        )

    async def health_check(self) -> bool:
        return True


class _EmptyMockProvider(BaseProvider):
    """A provider that succeeds but returns zero items."""

    @property
    def provider_id(self) -> str:
        return "rss"

    @property
    def provider_name(self) -> str:
        return "Empty Mock Provider"

    @property
    def version(self) -> str:
        return "0.0.0-test"

    async def fetch(self, **kwargs: object) -> ProviderResult:
        return ProviderResult(
            provider_id=self.provider_id,
            fetched_at=datetime.now(timezone.utc),
            success=True,
            data=[],
        )

    async def health_check(self) -> bool:
        return True


class _FailingMockProvider(BaseProvider):
    """A provider that always raises during fetch, simulating an outage."""

    @property
    def provider_id(self) -> str:
        return "broken"

    @property
    def provider_name(self) -> str:
        return "Failing Mock Provider"

    @property
    def version(self) -> str:
        return "0.0.0-test"

    async def fetch(self, **kwargs: object) -> ProviderResult:
        raise RuntimeError("simulated provider failure")

    async def health_check(self) -> bool:
        return False


class _NoOpMemory:
    """A minimal MemoryInterface stand-in; NewsCollectorAgent does not use memory."""

    async def read(self, key: str) -> object:
        raise NotImplementedError

    async def write(self, key: str, value: object) -> None:
        raise NotImplementedError


def _context() -> ExecutionContext:
    return ExecutionContext(
        workflow_id="WF-002",
        execution_id="exec-1",
        workflow_type="news_ingestion",
        trigger=TriggerType.SCHEDULED,
        initiated_by="test",
        started_at=datetime.now(timezone.utc),
        trace_id="trace-1",
        participating_agents=("AGT-003",),
        status=WorkflowStatus.RUNNING,
    )


# --- Mock provider tests -----------------------------------------------


async def test_run_collects_and_normalizes_from_single_provider() -> None:
    registry = ProviderRegistry()
    registry.register("rss", _MockRSSProvider)
    configs = [ProviderConfig(provider_id="rss")]
    agent = NewsCollectorAgent(memory=_NoOpMemory(), registry=registry, provider_configs=configs)

    result = await agent.run(_context(), NewsCollectionRequest())

    assert len(result.items) == 1
    assert result.items[0].title == "Fed holds rates steady"
    assert result.items[0].source_provider_id == "rss"
    assert len(result.provider_summary) == 1
    assert result.provider_summary[0].success is True
    assert result.provider_summary[0].item_count == 1


async def test_run_skips_disabled_providers() -> None:
    registry = ProviderRegistry()
    registry.register("rss", _MockRSSProvider)
    configs = [ProviderConfig(provider_id="rss", enabled=False)]
    agent = NewsCollectorAgent(memory=_NoOpMemory(), registry=registry, provider_configs=configs)

    result = await agent.run(_context(), NewsCollectionRequest())

    assert result.items == []
    assert result.provider_summary == []


async def test_run_filters_by_requested_provider_ids() -> None:
    registry = ProviderRegistry()
    registry.register("rss", _MockRSSProvider)
    registry.register("broken", _FailingMockProvider)
    configs = [ProviderConfig(provider_id="rss"), ProviderConfig(provider_id="broken")]
    agent = NewsCollectorAgent(memory=_NoOpMemory(), registry=registry, provider_configs=configs)

    result = await agent.run(_context(), NewsCollectionRequest(provider_ids=["rss"]))

    assert len(result.provider_summary) == 1
    assert result.provider_summary[0].provider_id == "rss"


# --- Multi-provider tests -----------------------------------------------


async def test_run_aggregates_items_across_multiple_providers() -> None:
    def _secondary_normalizer(result: ProviderResult) -> list[NewsItem]:
        return [NewsItem(title="Secondary item", source_provider_id=result.provider_id)]

    registry = ProviderRegistry()
    registry.register("rss", _MockRSSProvider)
    registry.register("rss-secondary", _MockSecondaryProvider)
    register_normalizer("rss-secondary", _secondary_normalizer)

    configs = [ProviderConfig(provider_id="rss"), ProviderConfig(provider_id="rss-secondary")]
    agent = NewsCollectorAgent(memory=_NoOpMemory(), registry=registry, provider_configs=configs)

    result = await agent.run(_context(), NewsCollectionRequest())

    assert len(result.items) == 2
    titles = {item.title for item in result.items}
    assert titles == {"Fed holds rates steady", "Secondary item"}
    assert {summary.provider_id for summary in result.provider_summary} == {"rss", "rss-secondary"}


# --- Partial failure tests -----------------------------------------------


async def test_run_isolates_a_failing_provider() -> None:
    registry = ProviderRegistry()
    registry.register("rss", _MockRSSProvider)
    registry.register("broken", _FailingMockProvider)
    configs = [ProviderConfig(provider_id="rss"), ProviderConfig(provider_id="broken")]
    agent = NewsCollectorAgent(memory=_NoOpMemory(), registry=registry, provider_configs=configs)

    result = await agent.run(_context(), NewsCollectionRequest())

    assert len(result.items) == 1
    assert result.items[0].source_provider_id == "rss"

    summaries = {summary.provider_id: summary for summary in result.provider_summary}
    assert summaries["rss"].success is True
    assert summaries["broken"].success is False
    assert summaries["broken"].error is not None
    assert summaries["broken"].item_count == 0


async def test_run_reports_provider_reported_failure_without_raising() -> None:
    """A provider that returns success=False (rather than raising) is still surfaced, not swallowed."""

    class _SoftFailProvider(BaseProvider):
        @property
        def provider_id(self) -> str:
            return "rss"

        @property
        def provider_name(self) -> str:
            return "Soft Fail Provider"

        @property
        def version(self) -> str:
            return "0.0.0-test"

        async def fetch(self, **kwargs: object) -> ProviderResult:
            return ProviderResult(
                provider_id=self.provider_id,
                fetched_at=datetime.now(timezone.utc),
                success=False,
                data=[],
                error="upstream returned no data",
            )

        async def health_check(self) -> bool:
            return True

    registry = ProviderRegistry()
    registry.register("rss", _SoftFailProvider)
    configs = [ProviderConfig(provider_id="rss")]
    agent = NewsCollectorAgent(memory=_NoOpMemory(), registry=registry, provider_configs=configs)

    result = await agent.run(_context(), NewsCollectionRequest())

    assert result.items == []
    assert result.provider_summary[0].success is False
    assert result.provider_summary[0].error == "upstream returned no data"


# --- Empty result tests -----------------------------------------------


async def test_run_returns_empty_items_when_provider_yields_none() -> None:
    registry = ProviderRegistry()
    registry.register("rss", _EmptyMockProvider)
    configs = [ProviderConfig(provider_id="rss")]
    agent = NewsCollectorAgent(memory=_NoOpMemory(), registry=registry, provider_configs=configs)

    result = await agent.run(_context(), NewsCollectionRequest())

    assert result.items == []
    assert result.provider_summary[0].success is True
    assert result.provider_summary[0].item_count == 0


async def test_run_with_no_configured_providers_returns_empty_result() -> None:
    registry = ProviderRegistry()
    agent = NewsCollectorAgent(memory=_NoOpMemory(), registry=registry, provider_configs=[])

    result = await agent.run(_context(), NewsCollectionRequest())

    assert result.items == []
    assert result.provider_summary == []


# --- BaseAgent contract -----------------------------------------------


async def test_validate_input_accepts_correct_type() -> None:
    agent = NewsCollectorAgent(memory=_NoOpMemory(), registry=ProviderRegistry(), provider_configs=[])
    assert await agent.validate_input(NewsCollectionRequest()) is True


async def test_validate_output_accepts_correct_type() -> None:
    agent = NewsCollectorAgent(memory=_NoOpMemory(), registry=ProviderRegistry(), provider_configs=[])
    result = await agent.run(_context(), NewsCollectionRequest())
    assert await agent.validate_output(result) is True


async def test_health_check_true_when_any_provider_enabled() -> None:
    agent = NewsCollectorAgent(
        memory=_NoOpMemory(),
        registry=ProviderRegistry(),
        provider_configs=[ProviderConfig(provider_id="rss")],
    )
    assert await agent.health_check() is True


async def test_health_check_false_when_no_providers_enabled() -> None:
    agent = NewsCollectorAgent(
        memory=_NoOpMemory(),
        registry=ProviderRegistry(),
        provider_configs=[ProviderConfig(provider_id="rss", enabled=False)],
    )
    assert await agent.health_check() is False


def test_agent_identity() -> None:
    agent = NewsCollectorAgent(memory=_NoOpMemory(), registry=ProviderRegistry(), provider_configs=[])
    assert agent.agent_id == "AGT-003"
    assert agent.agent_name == "News Collector"
    assert agent.layer.value == "ingestion"
