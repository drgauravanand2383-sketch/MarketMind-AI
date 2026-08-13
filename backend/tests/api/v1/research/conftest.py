"""Shared fixtures for `/api/v1/research` tests.

`CompanyResearchAgent` would call the real Claude API, so it is replaced
via `app.dependency_overrides` with `StubCompanyResearchAgent` — the same
test-substitution mechanism Sprint 57 used for `PortfolioIntelligenceAgent`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.company_research.models import (
    CompanyOverview,
    CompanyResearchReport,
    CompanyResearchRequest,
    ConfidenceSummary,
    MarketIntelligenceSummary,
)
from app.api.intelligence.dependencies import get_company_research_agent
from app.api.v1.exception_handlers import register_exception_handlers
from app.api.v1.research import router as research_router
from app.api.v1.schemas.result_store import InMemoryResultStore
from app.auth.middleware import AuthenticationMiddleware
from app.auth.policies import PolicyEvaluator
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService
from tests.api.v1._auth_fixtures import (  # noqa: F401 - re-exported as fixtures
    auth_repository,
    auth_service,
    authorization_service,
    make_authenticated_headers,
)

ALL_RESEARCH_PERMISSIONS = ("research:run", "research:read")


class StubCompanyResearchAgent:
    """A fast stand-in for `CompanyResearchAgent` — never calls Claude."""

    agent_id = "company-research-stub"

    async def run(self, context: object, input_data: CompanyResearchRequest) -> CompanyResearchReport:
        return CompanyResearchReport(
            request=input_data,
            generated_at=datetime.now(timezone.utc),
            company_overview=CompanyOverview(
                company_name=input_data.company_name, ticker=input_data.ticker,
                matched=True, entity_recognized=True, mention_count=1,
            ),
            market_intelligence=MarketIntelligenceSummary(mention_count=1),
            confidence_summary=ConfidenceSummary(overall_confidence=80.0, supporting_record_count=1, basis="stub"),
        )


@pytest.fixture
def app(
    auth_service: AuthenticationService,
    authorization_service: AuthorizationService,
) -> FastAPI:
    application = FastAPI()
    application.state.authentication_service = auth_service
    application.state.authorization_service = authorization_service
    application.state.policy_evaluator = PolicyEvaluator()
    application.state.research_report_store = InMemoryResultStore("research report")
    application.add_middleware(AuthenticationMiddleware)
    application.include_router(research_router, prefix="/api/v1")
    application.dependency_overrides[get_company_research_agent] = lambda: StubCompanyResearchAgent()
    register_exception_handlers(application)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def auth_headers(auth_repository, auth_service) -> dict[str, str]:
    return await make_authenticated_headers(auth_repository, auth_service, permissions=ALL_RESEARCH_PERMISSIONS)
