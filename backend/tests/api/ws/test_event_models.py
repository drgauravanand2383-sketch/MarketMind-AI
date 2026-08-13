"""Tests for the fully-typed event models — construction, `extra="forbid"`
validation, and `EventEnvelope` serialization round-tripping."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.alerts.models import Alert, AlertPriority, AlertStatus
from app.api.ws.event_models.base import EventMetadata
from app.api.ws.event_models.event_type import EventType
from app.api.ws.event_models.events import AlertEvent, BacktestEvent, EventEnvelope, HealthEvent
from app.backtesting.models import BacktestRun, BacktestStatus
from app.operations.health.models import ApplicationHealth, HealthState

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def _alert() -> Alert:
    return Alert(
        id="a1", rule_id="r1", ticker="AAPL", signal_name="x", priority=AlertPriority.HIGH,
        status=AlertStatus.GENERATED, reason="matched", confidence=90.0, score=80.0, created_at=NOW,
    )


def test_alert_event_has_expected_fields_and_default_event_type() -> None:
    event = AlertEvent(event_id="e1", timestamp=NOW, correlation_id="a1", payload=_alert())

    assert event.event_id == "e1"
    assert event.event_type == EventType.ALERT_GENERATED
    assert event.timestamp == NOW
    assert event.correlation_id == "a1"
    assert event.payload.ticker == "AAPL"


def test_event_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AlertEvent(event_id="e1", timestamp=NOW, payload=_alert(), bogus="x")


def test_event_id_must_be_non_blank() -> None:
    with pytest.raises(ValidationError):
        AlertEvent(event_id="", timestamp=NOW, payload=_alert())


def test_backtest_event_accepts_either_started_or_completed_type() -> None:
    run = BacktestRun(request_id="b1", started_at=NOW, status=BacktestStatus.PENDING)
    event = BacktestEvent(event_id="e1", timestamp=NOW, correlation_id="b1", event_type=EventType.BACKTEST_STARTED, payload=run)
    assert event.event_type == EventType.BACKTEST_STARTED


def test_backtest_event_rejects_an_unrelated_event_type() -> None:
    run = BacktestRun(request_id="b1", started_at=NOW, status=BacktestStatus.PENDING)
    with pytest.raises(ValidationError):
        BacktestEvent(event_id="e1", timestamp=NOW, event_type=EventType.ALERT_GENERATED, payload=run)


def test_health_event_correlation_id_defaults_to_none() -> None:
    health = ApplicationHealth(state=HealthState.HEALTHY, checked_at=NOW, summary="all systems healthy")
    event = HealthEvent(event_id="e1", timestamp=NOW, payload=health)
    assert event.correlation_id is None
    assert event.event_type == EventType.HEALTH_STATUS_CHANGED


def test_event_envelope_round_trips_through_json() -> None:
    event = AlertEvent(event_id="e1", timestamp=NOW, correlation_id="a1", payload=_alert())
    envelope = EventEnvelope(
        metadata=EventMetadata(connection_id="c1", delivered_at=NOW), event=event
    )

    dumped = envelope.model_dump_json()
    parsed = EventEnvelope.model_validate_json(dumped)

    assert parsed.type == "event"
    assert parsed.metadata.connection_id == "c1"
    assert parsed.event.event_id == "e1"
    assert parsed.event.payload.ticker == "AAPL"


def test_event_envelope_rejects_unknown_fields() -> None:
    event = AlertEvent(event_id="e1", timestamp=NOW, payload=_alert())
    with pytest.raises(ValidationError):
        EventEnvelope(metadata=EventMetadata(connection_id="c1", delivered_at=NOW), event=event, bogus="x")
