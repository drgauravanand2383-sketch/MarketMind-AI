"""FastAPI dependency provider for the Company Research API's result
cache. `get_company_research_agent` is reused directly from
`app.api.intelligence.dependencies` rather than duplicated.
"""

from __future__ import annotations

from fastapi import Request

from app.agents.company_research.models import CompanyResearchReport
from app.api.dependencies.state import resolve_app_state
from app.api.v1.schemas.result_store import InMemoryResultStore

__all__ = ["get_research_report_store"]


def get_research_report_store(request: Request) -> InMemoryResultStore[CompanyResearchReport]:
    return resolve_app_state(
        request, "research_report_store", InMemoryResultStore[CompanyResearchReport], label="The research report store"
    )
