"""Tests for the metrics abstraction."""

from __future__ import annotations

from app.operations.metrics.models import (
    METRIC_BACKTEST_RUNS,
    METRIC_RECOMMENDATION_GENERATIONS,
    METRIC_REPOSITORY_CALLS,
    METRIC_SERVICE_CALLS,
    METRIC_STARTUP_DURATION_SECONDS,
    METRIC_VALIDATION_FAILURES,
)
from app.operations.metrics.recorder import InMemoryMetricsRecorder


def test_increment_defaults_to_one() -> None:
    recorder = InMemoryMetricsRecorder()
    recorder.increment(METRIC_SERVICE_CALLS)

    assert recorder.total(METRIC_SERVICE_CALLS) == 1.0


def test_increment_accumulates_across_calls() -> None:
    recorder = InMemoryMetricsRecorder()
    recorder.increment(METRIC_REPOSITORY_CALLS)
    recorder.increment(METRIC_REPOSITORY_CALLS)
    recorder.increment(METRIC_REPOSITORY_CALLS, value=3.0)

    assert recorder.total(METRIC_REPOSITORY_CALLS) == 5.0
    assert recorder.count(METRIC_REPOSITORY_CALLS) == 3


def test_record_duration_stores_the_observed_seconds() -> None:
    recorder = InMemoryMetricsRecorder()
    recorder.record_duration(METRIC_STARTUP_DURATION_SECONDS, 1.25)

    assert recorder.total(METRIC_STARTUP_DURATION_SECONDS) == 1.25


def test_samples_carry_labels() -> None:
    recorder = InMemoryMetricsRecorder()
    recorder.increment(METRIC_BACKTEST_RUNS, status="completed")

    assert recorder.samples[0].labels == {"status": "completed"}


def test_different_metric_names_do_not_interfere() -> None:
    recorder = InMemoryMetricsRecorder()
    recorder.increment(METRIC_VALIDATION_FAILURES)
    recorder.increment(METRIC_RECOMMENDATION_GENERATIONS, value=2.0)

    assert recorder.total(METRIC_VALIDATION_FAILURES) == 1.0
    assert recorder.total(METRIC_RECOMMENDATION_GENERATIONS) == 2.0


def test_total_of_unrecorded_metric_is_zero() -> None:
    recorder = InMemoryMetricsRecorder()

    assert recorder.total("never_recorded") == 0.0
    assert recorder.count("never_recorded") == 0


def test_samples_is_immutable_snapshot() -> None:
    recorder = InMemoryMetricsRecorder()
    recorder.increment(METRIC_SERVICE_CALLS)
    snapshot = recorder.samples

    recorder.increment(METRIC_SERVICE_CALLS)

    assert len(snapshot) == 1
    assert len(recorder.samples) == 2
