"""Domain models and named metric constants for the metrics abstraction.

`METRIC_*` are the six counters the sprint explicitly names: service
calls, repository calls, validation failures, startup duration, backtest
runs, and recommendation generation. Defined once here so every caller
(operational infrastructure and, eventually, the domain services that
choose to record against them) references the same literal name.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MetricSample",
    "METRIC_SERVICE_CALLS",
    "METRIC_REPOSITORY_CALLS",
    "METRIC_VALIDATION_FAILURES",
    "METRIC_STARTUP_DURATION_SECONDS",
    "METRIC_BACKTEST_RUNS",
    "METRIC_RECOMMENDATION_GENERATIONS",
]

METRIC_SERVICE_CALLS = "service_calls"
METRIC_REPOSITORY_CALLS = "repository_calls"
METRIC_VALIDATION_FAILURES = "validation_failures"
METRIC_STARTUP_DURATION_SECONDS = "startup_duration_seconds"
METRIC_BACKTEST_RUNS = "backtest_runs"
METRIC_RECOMMENDATION_GENERATIONS = "recommendation_generations"


class MetricSample(BaseModel):
    """One recorded metric observation — a counter increment or a
    recorded duration, depending on `name`."""

    model_config = ConfigDict(extra="forbid")

    name: str
    value: float
    labels: dict[str, str] = Field(default_factory=dict)
    recorded_at: datetime
