"""Metrics abstraction.

`BaseMetricsRecorder` is the interface every part of this codebase that
wants to record a counter or a duration depends on — never a concrete
monitoring vendor (no Prometheus client, no StatsD, no OpenTelemetry
exporter). `InMemoryMetricsRecorder` is the one concrete implementation
this sprint provides: it stores every recorded `MetricSample` in memory,
usable both by tests (assert on what was recorded) and as a genuine,
dependency-free default for a deployment that has not yet wired a real
monitoring backend — a future sprint can add a vendor-specific
`BaseMetricsRecorder` implementation without changing any caller.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Callable

from app.operations.metrics.models import MetricSample

__all__ = ["BaseMetricsRecorder", "InMemoryMetricsRecorder"]


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class BaseMetricsRecorder(ABC):
    """Abstract base class every metrics recorder implementation must inherit."""

    @abstractmethod
    def increment(self, name: str, *, value: float = 1.0, **labels: str) -> None:
        """Increment counter `name` by `value` (default 1)."""
        raise NotImplementedError

    @abstractmethod
    def record_duration(self, name: str, seconds: float, **labels: str) -> None:
        """Record a duration observation of `seconds` against `name`."""
        raise NotImplementedError


class InMemoryMetricsRecorder(BaseMetricsRecorder):
    def __init__(self, *, now_fn: Callable[[], datetime] = _default_now) -> None:
        self._now_fn = now_fn
        self._samples: list[MetricSample] = []

    def increment(self, name: str, *, value: float = 1.0, **labels: str) -> None:
        self._samples.append(MetricSample(name=name, value=value, labels=labels, recorded_at=self._now_fn()))

    def record_duration(self, name: str, seconds: float, **labels: str) -> None:
        self._samples.append(MetricSample(name=name, value=seconds, labels=labels, recorded_at=self._now_fn()))

    @property
    def samples(self) -> tuple[MetricSample, ...]:
        return tuple(self._samples)

    def total(self, name: str) -> float:
        """Sum of every recorded value for `name` (counters: total count; durations: total seconds)."""
        return sum(sample.value for sample in self._samples if sample.name == name)

    def count(self, name: str) -> int:
        """Number of times `name` was recorded, regardless of value."""
        return sum(1 for sample in self._samples if sample.name == name)
