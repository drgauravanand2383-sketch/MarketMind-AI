"""Shared test doubles and records for PortfolioIntelligenceAgent tests.

Reuses CompanyResearchAgent's own test doubles (`build_knowledge_hub`,
`build_prompt_registry`, `mock_llm_service`, `build_runtime`, `record`) so
PortfolioIntelligenceAgent is exercised against a real CompanyResearchAgent
instance, not a mock of it. Only LLMService is mocked (Sprint 40, one
instance per agent — CompanyResearchAgent's own LLM calls and
PortfolioIntelligenceAgent's own LLM call are independently mocked, since
they expect different JSON response shapes) — the Prompt Framework,
KnowledgeHub, and CompanyResearchAgent are all real. No real Anthropic SDK
or network call occurs anywhere in this package.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.portfolio_intelligence.agent import PortfolioIntelligenceAgent
from app.agents.portfolio_intelligence.prompts import register_portfolio_intelligence_prompts
from app.prompts.registry import PromptRegistry
from app.services.llm.models import LLMHealthStatus, LLMResponse, TokenUsage
from app.services.llm.service import LLMService
from tests.agents.company_research.conftest import (
    build_knowledge_hub,
    build_prompt_registry as build_company_research_prompt_registry,
    build_runtime,
    mock_llm_service as mock_company_research_llm_service,
    record,
)

APPLE_RECORD = record(
    id="rec-apple",
    title="Apple reports record iPhone sales",
    text="Apple Inc. posted strong quarterly earnings driven by new chip technology demand.",
    url="https://example.com/apple1",
    published_at="2026-08-01",
    source_provider_id="rss",
)
TESLA_RECORD = record(
    id="rec-tesla",
    title="Tesla unveils new EV chip technology",
    text="Tesla Inc. announced a new electric vehicle chip lineup and strong quarterly earnings this week.",
    url="https://example.com/tesla1",
    published_at="2026-08-02",
    source_provider_id="rss",
)
APPLE_TESLA_RECORD = record(
    id="rec-both",
    title="Apple and Tesla both surge on strong earnings",
    text="Shares of Apple and Tesla rallied after both reported strong quarterly earnings.",
    url="https://example.com/both",
    published_at="2026-08-03",
    source_provider_id="newsapi",
)


def build_portfolio_prompt_registry() -> PromptRegistry:
    """A PromptRegistry with the Portfolio Intelligence template registered
    (independent of CompanyResearchAgent's own registry/template)."""
    registry = PromptRegistry()
    register_portfolio_intelligence_prompts(registry)
    return registry


def portfolio_narrative_json(
    executive_summary: str = "Evidence-grounded portfolio summary.",
    concentration_observations: list[str] | None = None,
    relationship_observations: list[str] | None = None,
    notable_market_events: list[str] | None = None,
) -> str:
    """A well-formed PortfolioNarrative JSON payload, as an LLM response's `content` would contain."""
    return json.dumps(
        {
            "executive_summary": executive_summary,
            "concentration_observations": (
                concentration_observations if concentration_observations is not None else ["Observation."]
            ),
            "relationship_observations": (
                relationship_observations if relationship_observations is not None else []
            ),
            "notable_market_events": (
                notable_market_events if notable_market_events is not None else []
            ),
        }
    )


def mock_portfolio_llm_service(
    content: str | None = None,
    error: Exception | None = None,
    ready: bool = True,
) -> MagicMock:
    """A mocked LLMService for PortfolioIntelligenceAgent's own narrative call."""
    service = MagicMock(spec=LLMService)
    if error is not None:
        service.generate.side_effect = error
    else:
        service.generate.return_value = LLMResponse(
            content=content if content is not None else portfolio_narrative_json(),
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            provider="anthropic",
            model="claude-sonnet-5",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
        )
    service.health_check.return_value = LLMHealthStatus(
        provider="anthropic", available=ready, model="claude-sonnet-5" if ready else None, ready=ready
    )
    return service


def build_portfolio_agent(
    records: list,
    llm_content: str | None = None,
    llm_error: Exception | None = None,
    llm_ready: bool = True,
    prompt_registry: PromptRegistry | None = None,
) -> PortfolioIntelligenceAgent:
    """Build a PortfolioIntelligenceAgent wired to a real CompanyResearchAgent
    backed by an in-memory knowledge hub preloaded with `records`. Both
    agents share the same KnowledgeHub instance (as they would in
    production) but have independently-mocked LLMServices."""
    runtime = build_runtime()
    knowledge_hub = build_knowledge_hub(records)
    company_research_agent = CompanyResearchAgent(
        runtime=runtime,
        knowledge_hub=knowledge_hub,
        llm_service=mock_company_research_llm_service(),
        prompt_registry=build_company_research_prompt_registry(),
    )
    return PortfolioIntelligenceAgent(
        runtime=runtime,
        knowledge_hub=knowledge_hub,
        llm_service=mock_portfolio_llm_service(content=llm_content, error=llm_error, ready=llm_ready),
        prompt_registry=prompt_registry or build_portfolio_prompt_registry(),
        company_research_agent=company_research_agent,
    )
