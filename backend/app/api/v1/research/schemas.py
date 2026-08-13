"""HTTP-layer schemas for the Company Research API.

`CompanyResearchAgent` has no persistence of its own (its own module
docstring: "this agent still never writes to knowledge storage — it only
reads") and `CompanyResearchReport` has no `id` field, so
`GET /research/{request_id}` has nothing to look up without new
persistence. By explicit product decision, a thin in-process,
HTTP-layer-only cache (`app.api.v1.schemas.result_store.InMemoryResultStore`)
fills this gap — the router generates an id when storing a freshly
computed report; no business logic is added.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.agents.company_research.models import CompanyResearchReport, CompanyResearchRequest

__all__ = ["BatchCompanyResearchRequest", "CompanyResearchReportEnvelope"]


class BatchCompanyResearchRequest(BaseModel):
    """Request body for `POST /api/v1/research/batch`."""

    model_config = ConfigDict(extra="forbid")

    companies: list[CompanyResearchRequest] = Field(
        min_length=1, examples=[[{"company_name": "Apple Inc.", "ticker": "AAPL"}]]
    )


class CompanyResearchReportEnvelope(BaseModel):
    """A `CompanyResearchReport` plus the id it was cached under —
    returned by both the create endpoints and `GET /research/{request_id}`."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(examples=["9c1e2b1a-3f4d-4a5e-8b6c-7d8e9f0a1b2c"])
    report: CompanyResearchReport
