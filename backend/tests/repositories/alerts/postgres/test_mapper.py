"""Tests for the Alert Postgres mapper: purely structural round-trips,
plus the naive-datetime normalization `_ensure_aware` performs."""

from __future__ import annotations

from datetime import UTC, datetime

from app.alerts.models import (
    Alert,
    AlertCondition,
    AlertOperator,
    AlertPriority,
    AlertRule,
    AlertStatus,
    NotificationChannel,
)
from app.repositories.alerts.postgres.mapper import (
    alert_to_model,
    model_to_alert,
    model_to_rule,
    rule_to_model,
)
from app.repositories.alerts.postgres.models import AlertModel, AlertRuleModel

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def test_rule_with_conditions_and_channels_round_trips() -> None:
    rule = AlertRule(
        id="r1",
        name="Value",
        description="Cheap companies",
        enabled=True,
        priority=AlertPriority.HIGH,
        conditions=(
            AlertCondition(id="c1", field="score", operator=AlertOperator.GREATER_THAN, value=50),
            AlertCondition(id="c2", field="ticker", operator=AlertOperator.IN, value=["AAPL", "MSFT"]),
        ),
        cooldown_minutes=15,
        repeat_allowed=False,
        channels=(NotificationChannel.EMAIL, NotificationChannel.SMS),
        created_at=NOW,
        updated_at=NOW,
    )

    model = rule_to_model(rule)
    restored = model_to_rule(model)

    assert restored == rule


def test_rule_with_no_conditions_or_channels_round_trips() -> None:
    rule = AlertRule(id="r1", name="Empty", created_at=NOW, updated_at=NOW)

    model = rule_to_model(rule)
    restored = model_to_rule(model)

    assert restored.conditions == ()
    assert restored.channels == ()


def test_rule_between_operator_value_round_trips_as_a_list() -> None:
    rule = AlertRule(
        id="r1",
        name="Value",
        created_at=NOW,
        updated_at=NOW,
        conditions=(AlertCondition(id="c1", field="score", operator=AlertOperator.BETWEEN, value=[10, 20]),),
    )

    model = rule_to_model(rule)
    restored = model_to_rule(model)

    assert restored.conditions[0].value == [10, 20]


def test_alert_round_trips() -> None:
    alert = Alert(
        id="a1",
        rule_id="r1",
        ticker="AAPL",
        company_name="Apple",
        signal_name="Value Signal",
        priority=AlertPriority.CRITICAL,
        status=AlertStatus.GENERATED,
        reason="matched",
        confidence=90.0,
        score=80.0,
        eligible_channels=(NotificationChannel.EMAIL, NotificationChannel.IN_APP),
        created_at=NOW,
    )

    model = alert_to_model(alert)
    restored = model_to_alert(model)

    assert restored == alert


def test_alert_with_no_eligible_channels_round_trips() -> None:
    alert = Alert(
        id="a1", rule_id="r1", ticker="AAPL", signal_name="X", priority=AlertPriority.LOW,
        status=AlertStatus.SUPPRESSED, reason="dup", confidence=1, score=1, created_at=NOW,
    )

    model = alert_to_model(alert)
    restored = model_to_alert(model)

    assert restored.eligible_channels == ()


def test_model_to_rule_normalizes_naive_datetime_to_utc() -> None:
    model = AlertRuleModel(
        id="r1", name="X", description="", enabled=True, priority="MEDIUM",
        conditions=[], cooldown_minutes=0, repeat_allowed=True, channels=[],
        created_at=datetime(2026, 1, 1),  # naive, as SQLite round-trips it
        updated_at=datetime(2026, 1, 1),
    )

    restored = model_to_rule(model)

    assert restored.created_at.tzinfo is not None
    assert restored.updated_at.tzinfo is not None


def test_model_to_alert_normalizes_naive_datetime_to_utc() -> None:
    model = AlertModel(
        id="a1", rule_id="r1", ticker="AAPL", signal_name="X", alert_type="SIGNAL_TRIGGERED",
        priority="LOW", status="GENERATED", reason="x", confidence=1.0, score=1.0, eligible_channels=[],
        created_at=datetime(2026, 1, 1),  # naive
    )

    restored = model_to_alert(model)

    assert restored.created_at.tzinfo is not None
