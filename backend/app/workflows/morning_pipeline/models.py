"""Schemas for the Morning Intelligence Pipeline orchestration.

PipelineResult is the terminal output of one pipeline run — coordination
metadata and downstream artifacts only. No business logic, reasoning, or
report content is modeled here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.core.context import ExecutionContext
from app.services.evidence_engine.models import EvidenceGraph
from app.services.market_intelligence.models import MarketIntelligence
from app.services.relationship_engine.models import RelationshipGraph

__all__ = ["PipelineStatus", "StageMetric", "PipelineResult"]


class PipelineStatus(str, Enum):
    """The terminal state of one pipeline run."""

    COMPLETED = "completed"
    FAILED = "failed"


class StageMetric(BaseModel):
    """Execution metrics for a single pipeline stage."""

    model_config = ConfigDict(extra="forbid")

    stage_name: str
    started_at: datetime
    completed_at: datetime
    succeeded: bool
    error: str | None = None


class PipelineResult(BaseModel):
    """The output of MorningPipeline.run().

    `final_context` is the ExecutionContext as of the last stage
    attempted — present whether the run completed or failed, so a failed
    run's partial progress remains inspectable.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    status: PipelineStatus
    execution_id: str
    started_at: datetime
    completed_at: datetime
    stage_metrics: list[StageMetric] = Field(default_factory=list)
    final_context: ExecutionContext
    evidence_graph: EvidenceGraph | None = None
    market_intelligence: MarketIntelligence | None = None
    relationship_graph: RelationshipGraph | None = None
    failed_stage: str | None = None
    error: str | None = None
