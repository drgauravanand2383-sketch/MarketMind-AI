"""Domain model for the performance profiling abstraction."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

__all__ = ["ProfileSample"]


class ProfileSample(BaseModel):
    """One recorded timing observation for a repository operation,
    service execution, or pipeline execution."""

    model_config = ConfigDict(extra="forbid")

    operation: str
    duration_seconds: float
    recorded_at: datetime
