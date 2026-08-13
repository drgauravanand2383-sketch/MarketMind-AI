"""Shared fixtures for Intelligence Query API tests.

Builds real FastAPI apps mounting the Intelligence Query router, wired
either to in-memory test doubles (via `app.dependency_overrides`, the
standard FastAPI testing pattern) or left completely unconfigured to
exercise the 503 "not configured" path. No real HTTP, database, or
embedding API call occurs anywhere.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.portfolio_intelligence.agent import PortfolioIntelligenceAgent
from app.api.intelligence.dependencies import (
    get_company_research_agent,
    get_morning_pipeline,
    get_portfolio_intelligence_agent,
)
from app.api.intelligence.router import router
from tests.agents.company_research.conftest import (
    build_knowledge_hub,
    build_prompt_registry,
    build_runtime,
    mock_llm_service,
    record,
)
from tests.agents.portfolio_intelligence.conftest import (
    build_portfolio_prompt_registry,
    mock_portfolio_llm_service,
)
from tests.workflows.morning_pipeline.conftest import build_pipeline

APPLE_RECORD = record(
    id="rec-apple",
    title="Apple reports record iPhone sales",
    text="Apple Inc. posted strong quarterly earnings driven by iPhone demand.",
    url="https://example.com/apple1",
    published_at="2026-08-01",
    source_provider_id="rss",
)


def build_configured_app() -> FastAPI:
    """A FastAPI app with every dependency overridden by an in-memory test double."""
    app = FastAPI()
    app.include_router(router)

    runtime = build_runtime()
    knowledge_hub = build_knowledge_hub([APPLE_RECORD])
    company_research_agent = CompanyResearchAgent(
        runtime=runtime,
        knowledge_hub=knowledge_hub,
        llm_service=mock_llm_service(),
        prompt_registry=build_prompt_registry(),
    )
    portfolio_agent = PortfolioIntelligenceAgent(
        runtime=runtime,
        knowledge_hub=knowledge_hub,
        llm_service=mock_portfolio_llm_service(),
        prompt_registry=build_portfolio_prompt_registry(),
        company_research_agent=company_research_agent,
    )

    app.dependency_overrides[get_company_research_agent] = lambda: company_research_agent
    app.dependency_overrides[get_portfolio_intelligence_agent] = lambda: portfolio_agent
    app.dependency_overrides[get_morning_pipeline] = lambda: build_pipeline()

    return app


def build_unconfigured_app() -> FastAPI:
    """A FastAPI app with no dependency overrides and no app.state configured —
    exercises the 503 'not configured' path for every non-/health endpoint."""
    app = FastAPI()
    app.include_router(router)
    return app


def build_client() -> TestClient:
    return TestClient(build_configured_app())


def build_unconfigured_client() -> TestClient:
    return TestClient(build_unconfigured_app())
