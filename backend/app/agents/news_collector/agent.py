"""NewsCollectorAgent — AGT-003.

Loads enabled providers from a ProviderRegistry, executes them
concurrently, collects their ProviderResult objects, and normalizes them
into a common NewsItem schema. Performs no sentiment analysis, ranking,
deduplication across providers, storage, or Knowledge Hub writes.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from pydantic import BaseModel

from app.agents.base import AgentLayer, BaseAgent, MemoryInterface
from app.agents.news_collector.models import (
    NewsCollectionRequest,
    NewsCollectionResult,
    NewsItem,
    ProviderRunSummary,
)
from app.agents.news_collector.normalizer import normalize_provider_result
from app.core.context import ExecutionContext
from app.providers.models import ProviderConfig
from app.providers.registry import ProviderRegistry

__all__ = ["NewsCollectorAgent"]

AGENT_ID = "AGT-003"
AGENT_NAME = "News Collector"
AGENT_VERSION = "0.1.0"


class NewsCollectorAgent(BaseAgent):
    """Collects and normalizes news from all enabled configured providers."""

    def __init__(
        self,
        memory: MemoryInterface,
        registry: ProviderRegistry,
        provider_configs: list[ProviderConfig],
    ) -> None:
        """Initialize the agent.

        Args:
            memory: Injected memory interface, required by BaseAgent. This
                agent does not read or write memory.
            registry: The provider registry to resolve provider classes from.
            provider_configs: The full set of configured providers this
                agent may draw from; only those with `enabled=True` are used.
        """
        super().__init__(memory)
        self._registry = registry
        self._provider_configs = provider_configs

    @property
    def agent_id(self) -> str:
        return AGENT_ID

    @property
    def agent_name(self) -> str:
        return AGENT_NAME

    @property
    def version(self) -> str:
        return AGENT_VERSION

    @property
    def layer(self) -> AgentLayer:
        return AgentLayer.INGESTION

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"news_collection"})

    @property
    def input_schema(self) -> type[BaseModel]:
        return NewsCollectionRequest

    @property
    def output_schema(self) -> type[BaseModel]:
        return NewsCollectionResult

    async def validate_input(self, input_data: BaseModel) -> bool:
        return isinstance(input_data, NewsCollectionRequest)

    async def validate_output(self, output_data: BaseModel) -> bool:
        return isinstance(output_data, NewsCollectionResult)

    async def health_check(self) -> bool:
        """Report whether at least one configured provider is enabled."""
        return any(config.enabled for config in self._provider_configs)

    def _enabled_configs(self, input_data: NewsCollectionRequest) -> list[ProviderConfig]:
        """Select the configured providers this run should use.

        Applies the `enabled` flag first, then narrows to
        `input_data.provider_ids` if the caller requested a subset.
        """
        configs = [config for config in self._provider_configs if config.enabled]
        if input_data.provider_ids is not None:
            requested = set(input_data.provider_ids)
            configs = [config for config in configs if config.provider_id in requested]
        return configs

    async def run(self, context: ExecutionContext, input_data: BaseModel) -> NewsCollectionResult:
        """Load enabled providers, execute them concurrently, and normalize results.

        A provider that fails to construct or fetch does not abort the
        others — its failure is recorded in `provider_summary` and
        collection continues with whatever providers did succeed.

        Args:
            context: The shared Execution Context for the current workflow run.
            input_data: A NewsCollectionRequest.

        Returns:
            A NewsCollectionResult aggregating every provider's normalized
            items and a per-provider run summary.
        """
        assert isinstance(input_data, NewsCollectionRequest)
        configs = self._enabled_configs(input_data)

        provider_runs = await asyncio.gather(
            *(self._run_one_provider(config) for config in configs)
        )

        items: list[NewsItem] = []
        summaries: list[ProviderRunSummary] = []
        for summary, provider_items in provider_runs:
            summaries.append(summary)
            items.extend(provider_items)

        return NewsCollectionResult(
            items=items,
            provider_summary=summaries,
            collected_at=datetime.now(UTC),
        )

    async def _run_one_provider(
        self, config: ProviderConfig
    ) -> tuple[ProviderRunSummary, list[NewsItem]]:
        """Construct, execute, and normalize a single provider, isolating its failure."""
        try:
            provider = self._registry.create(config.provider_id, config)
            result = await provider.fetch()
        except Exception as exc:  # noqa: BLE001 - a provider failure must not abort the batch
            summary = ProviderRunSummary(
                provider_id=config.provider_id, success=False, item_count=0, error=str(exc)
            )
            return summary, []

        items = normalize_provider_result(result)
        summary = ProviderRunSummary(
            provider_id=config.provider_id,
            success=result.success,
            item_count=len(items),
            error=result.error,
        )
        return summary, items
