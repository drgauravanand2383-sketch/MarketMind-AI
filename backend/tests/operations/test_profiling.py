"""Tests for the performance profiling abstraction."""

from __future__ import annotations

import asyncio
import time

from app.operations.profiling.profiler import InMemoryProfiler


def test_record_stores_a_sample() -> None:
    profiler = InMemoryProfiler()
    profiler.record("repository.get", 0.05)

    assert len(profiler.samples) == 1
    assert profiler.samples[0].operation == "repository.get"
    assert profiler.samples[0].duration_seconds == 0.05


def test_sync_measure_records_elapsed_time() -> None:
    profiler = InMemoryProfiler()

    with profiler.measure("pipeline.run"):
        time.sleep(0.01)

    assert profiler.count("pipeline.run") == 1
    assert profiler.samples[0].duration_seconds >= 0.01


async def test_async_measure_records_elapsed_time() -> None:
    profiler = InMemoryProfiler()

    async with profiler.measure("service.call"):
        await asyncio.sleep(0.01)

    assert profiler.count("service.call") == 1
    assert profiler.samples[0].duration_seconds >= 0.01


async def test_async_measure_records_even_when_the_body_raises() -> None:
    profiler = InMemoryProfiler()

    try:
        async with profiler.measure("failing_op"):
            raise ValueError("boom")
    except ValueError:
        pass

    assert profiler.count("failing_op") == 1


def test_average_duration_across_multiple_samples() -> None:
    profiler = InMemoryProfiler()
    profiler.record("op", 1.0)
    profiler.record("op", 3.0)

    assert profiler.average_duration("op") == 2.0


def test_average_duration_of_unrecorded_operation_is_none() -> None:
    profiler = InMemoryProfiler()

    assert profiler.average_duration("never_recorded") is None


def test_different_operations_tracked_independently() -> None:
    profiler = InMemoryProfiler()
    profiler.record("a", 1.0)
    profiler.record("b", 5.0)

    assert profiler.count("a") == 1
    assert profiler.count("b") == 1
    assert profiler.average_duration("a") == 1.0
