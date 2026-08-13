"""Company Research API (`/api/v1/research`, Sprint 58): exposes
`app.agents.company_research.agent.CompanyResearchAgent` — every endpoint
delegates directly to its `run()` method; no business logic is duplicated.
A thin in-process cache (see `app.api.v1.schemas.result_store`) backs
`GET /{request_id}`, since the agent itself has no persistence."""

from app.api.v1.research.router import router

__all__ = ["router"]
