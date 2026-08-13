"""Metrics abstraction: counters and durations for service calls,
repository calls, validation failures, startup duration, backtest runs,
and recommendation generation — via `BaseMetricsRecorder`, never a
concrete monitoring vendor."""

from app.operations.metrics.models import (
    METRIC_BACKTEST_RUNS,
    METRIC_RECOMMENDATION_GENERATIONS,
    METRIC_REPOSITORY_CALLS,
    METRIC_SERVICE_CALLS,
    METRIC_STARTUP_DURATION_SECONDS,
    METRIC_VALIDATION_FAILURES,
    MetricSample,
)
from app.operations.metrics.recorder import BaseMetricsRecorder, InMemoryMetricsRecorder

__all__ = [
    "BaseMetricsRecorder",
    "InMemoryMetricsRecorder",
    "MetricSample",
    "METRIC_SERVICE_CALLS",
    "METRIC_REPOSITORY_CALLS",
    "METRIC_VALIDATION_FAILURES",
    "METRIC_STARTUP_DURATION_SECONDS",
    "METRIC_BACKTEST_RUNS",
    "METRIC_RECOMMENDATION_GENERATIONS",
]
