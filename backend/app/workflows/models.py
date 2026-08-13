"""Schemas for the Workflow Engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = ["WorkflowExecutionResult"]


class WorkflowExecutionResult(BaseModel):
    """Standardized result of one WorkflowEngine.execute() call.

    `output` carries whatever the workflow itself returned — this model
    does not interpret or reshape it. `error` is populated (and `output`
    left None) when the workflow raised instead of returning.
    """

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    execution_id: str
    started_at: datetime
    completed_at: datetime
    duration: float
    success: bool
    output: Any = None
    error: str | None = None
