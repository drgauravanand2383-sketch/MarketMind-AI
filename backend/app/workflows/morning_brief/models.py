"""Schemas for the Morning Brief Workflow."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["MorningBriefWorkflowResult"]


class MorningBriefWorkflowResult(BaseModel):
    """The output of MorningBriefWorkflow.run().

    Every count reflects what was actually measured up to the point of
    failure (if any) — `success=False` does not reset earlier steps'
    already-known counts back to zero.
    """

    model_config = ConfigDict(extra="forbid")

    report_path: str | None
    articles_processed: int
    articles_persisted: int
    embeddings_generated: int
    execution_time: float
    success: bool
