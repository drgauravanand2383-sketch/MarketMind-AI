"""Performance profiling abstraction.

`BaseProfiler` is the interface every part of this codebase that wants to
time a repository operation, service execution, or pipeline execution
depends on — plain wall-clock timing via `time.perf_counter()`, never a
sampling profiler and never external tooling (no `py-spy`, no `cProfile`
integration). `measure()` returns a context manager usable both as
`with profiler.measure("op"):` and `async with profiler.measure("op"):` —
every timed operation in this codebase (repository calls, service
methods) is async, so the async form is the one actually exercised in
production; the sync form exists for convenience and for tests.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType

from app.operations.profiling.models import ProfileSample

__all__ = ["BaseProfiler", "InMemoryProfiler"]


def _default_now() -> datetime:
    return datetime.now(UTC)


class BaseProfiler(ABC):
    """Abstract base class every profiler implementation must inherit."""

    @abstractmethod
    def record(self, operation: str, duration_seconds: float) -> None:
        """Record one timing observation for `operation`."""
        raise NotImplementedError

    def measure(self, operation: str) -> _Measurement:
        """Return a context manager (sync or async) timing `operation`."""
        return _Measurement(self, operation)


class _Measurement:
    """A single timed span, usable as either a sync or an async context manager."""

    def __init__(self, profiler: BaseProfiler, operation: str) -> None:
        self._profiler = profiler
        self._operation = operation
        self._start = 0.0

    def __enter__(self) -> _Measurement:
        self._start = time.perf_counter()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._profiler.record(self._operation, time.perf_counter() - self._start)

    async def __aenter__(self) -> _Measurement:
        self._start = time.perf_counter()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._profiler.record(self._operation, time.perf_counter() - self._start)


class InMemoryProfiler(BaseProfiler):
    def __init__(self, *, now_fn: Callable[[], datetime] = _default_now) -> None:
        self._now_fn = now_fn
        self._samples: list[ProfileSample] = []

    def record(self, operation: str, duration_seconds: float) -> None:
        self._samples.append(
            ProfileSample(operation=operation, duration_seconds=duration_seconds, recorded_at=self._now_fn())
        )

    @property
    def samples(self) -> tuple[ProfileSample, ...]:
        return tuple(self._samples)

    def average_duration(self, operation: str) -> float | None:
        matching = [sample.duration_seconds for sample in self._samples if sample.operation == operation]
        return (sum(matching) / len(matching)) if matching else None

    def count(self, operation: str) -> int:
        return sum(1 for sample in self._samples if sample.operation == operation)
