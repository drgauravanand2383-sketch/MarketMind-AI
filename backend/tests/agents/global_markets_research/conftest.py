"""Shared test doubles for GlobalMarketsResearchAgent tests.

The LLM Service is always mocked (`mock_llm_service` below) — no real
Anthropic SDK or network call occurs anywhere in this package.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from app.agents.global_markets_research.models import GlobalMarketsResearchRequest
from app.agents.global_markets_research.prompts import register_global_markets_research_prompts
from app.core.runtime import AgentRuntime
from app.global_markets.models import (
    DataFreshnessStatus,
    DataProvenance,
    MarketSessionContext,
    NormalizedAssetSnapshot,
    ReportCategory,
)
from app.global_markets.ranked_asset import RankedAsset
from app.global_markets.ranking.models import FactorScore, RankingFactor
from app.prompts.registry import PromptRegistry
from app.services.llm.models import LLMHealthStatus, LLMResponse, TokenUsage
from app.services.llm.service import LLMService

_PROVENANCE = DataProvenance(
    source_timestamp=datetime(2026, 8, 31, tzinfo=UTC),
    retrieved_at=datetime(2026, 8, 31, tzinfo=UTC),
    provider="test-fixture",
    data_freshness_status=DataFreshnessStatus.LIVE,
)


class NoOpMemory:
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
    return AgentRuntime(
        logger=logging.getLogger("test.global_markets_research"),
        configuration=_StubConfiguration(),
        knowledge_hub=_StubKnowledgeHub(),
        memory=NoOpMemory(),
        tool_registry=_StubToolRegistry(),
        event_bus=_StubEventBus(),
    )


def build_prompt_registry() -> PromptRegistry:
    registry = PromptRegistry()
    register_global_markets_research_prompts(registry)
    return registry


def session_context(category: ReportCategory = ReportCategory.US_EQUITY) -> MarketSessionContext:
    from app.global_markets.models import REPORT_CATEGORY_DEFINITIONS

    return MarketSessionContext(
        market_region=REPORT_CATEGORY_DEFINITIONS[category].market_region,
        market_timezone="America/New_York",
        retrieved_at=datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
        as_of_timestamp=datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
        is_trading_now=True,
        is_holiday=False,
        market_session_date=date(2026, 8, 31),
        last_completed_session=None,
        data_freshness_status=DataFreshnessStatus.LIVE,
        freshness_cutoff=None,
    )


def ranked_asset(ticker: str, rank: int, **overrides: object) -> RankedAsset:
    defaults: dict[str, object] = {
        "run_id": "run-1",
        "category": ReportCategory.US_EQUITY,
        "rank": rank,
        "final_score": 100.0 - rank,
        "factor_scores": (
            FactorScore(factor=RankingFactor.PRICE_PERFORMANCE, value=80.0),
            FactorScore(factor=RankingFactor.MOMENTUM, value=70.0),
        ),
        "snapshot": NormalizedAssetSnapshot(
            ticker=ticker, report_category=ReportCategory.US_EQUITY, price=100.0, provenance=_PROVENANCE
        ),
    }
    defaults.update(overrides)
    return RankedAsset(**defaults)  # type: ignore[arg-type]


def request(
    category: ReportCategory = ReportCategory.US_EQUITY,
    ranked_assets: tuple[RankedAsset, ...] | None = None,
    run_id: str = "run-1",
) -> GlobalMarketsResearchRequest:
    return GlobalMarketsResearchRequest(
        run_id=run_id,
        category=category,
        market_session_context=session_context(category),
        ranked_assets=ranked_assets if ranked_assets is not None else (ranked_asset("AAPL", 1),),
    )


def narrative_json(
    overall_summary: str = "A quiet session overall.",
    asset_commentaries: list[dict[str, object]] | None = None,
    risk_note: str | None = None,
) -> str:
    return json.dumps(
        {
            "overall_summary": overall_summary,
            "asset_commentaries": (
                asset_commentaries
                if asset_commentaries is not None
                else [{"ticker": "AAPL", "rank": 1, "commentary": "Led the category."}]
            ),
            "risk_note": risk_note,
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


def mock_llm_service(content: str | None = None, error: Exception | None = None, ready: bool = True) -> MagicMock:
    service = MagicMock(spec=LLMService)
    if error is not None:
        service.generate.side_effect = error
    else:
        service.generate.return_value = llm_response(content)
    service.health_check.return_value = LLMHealthStatus(
        provider="anthropic", available=ready, model="claude-sonnet-5" if ready else None, ready=ready
    )
    return service
