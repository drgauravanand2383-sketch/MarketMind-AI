"""FastAPI dependency provider for the Company Research API's result
cache. `get_company_research_agent` is reused directly from
`app.api.intelligence.dependencies` rather than duplicated.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.agents.company_research.models import CompanyResearchReport
from app.api.v1.schemas.result_store import InMemoryResultStore

__all__ = ["get_research_report_store"]


def get_research_report_store(request: Request) -> InMemoryResultStore[CompanyResearchReport]:
    store = getattr(request.app.state, "research_report_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The research report store is not configured on this application instance.",
        )
    return store
