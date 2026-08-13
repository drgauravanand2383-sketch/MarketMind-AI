"""HTTP-layer request schema for the Explainability API.

The response reuses `app.explainability.models.ExplainabilityResult`
directly. The request has no matching domain model —
`ExplainabilityService.create_request()` takes individual primitive
arguments — so it gets a dedicated schema here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["GenerateExplanationRequest"]


class GenerateExplanationRequest(BaseModel):
    """Request body for `POST /api/v1/explainability`."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, examples=["Explain AAPL recommendation"])
    recommendation_result_id: str = Field(min_length=1)
    strategy_evaluation_id: str | None = None
    risk_assessment_id: str | None = None
    backtest_run_id: str | None = None
