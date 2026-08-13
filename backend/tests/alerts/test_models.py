"""Tests for the Alert & Notification Engine's domain models:
AlertCondition (per-operator value validation, field validation),
AlertRule's structural validation, and Alert/AlertBatch construction."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.alerts.models import (
    Alert,
    AlertBatch,
    AlertCondition,
    AlertOperator,
    AlertPriority,
    AlertRule,
    AlertStatus,
    NotificationChannel,
)
from tests.alerts.conftest import NOW, make_condition, make_rule

# --- AlertCondition: operator/value validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "operator,value",
    [
        (AlertOperator.EQUALS, "AAPL"),
        (AlertOperator.NOT_EQUALS, "AAPL"),
        (AlertOperator.GREATER_THAN, 10),
        (AlertOperator.GREATER_EQUAL, 10),
        (AlertOperator.LESS_THAN, 10),
        (AlertOperator.LESS_EQUAL, 10),
        (AlertOperator.BETWEEN, [5, 10]),
        (AlertOperator.IN, ["AAPL", "MSFT"]),
        (AlertOperator.NOT_IN, ["AAPL", "MSFT"]),
    ],
)
def test_alert_condition_accepts_valid_value_for_each_operator(operator, value) -> None:  # noqa: ANN001
    condition = AlertCondition(id="c1", field="score", operator=operator, value=value)
    assert condition.operator == operator


def test_alert_condition_rejects_unknown_operator() -> None:
    with pytest.raises(ValidationError):
        AlertCondition(id="c1", field="score", operator="TOTALLY_MADE_UP", value=1)


def test_alert_condition_rejects_missing_value_for_scalar_operator() -> None:
    with pytest.raises(ValidationError):
        AlertCondition(id="c1", field="score", operator=AlertOperator.GREATER_THAN, value=None)


def test_alert_condition_between_requires_two_element_list() -> None:
    with pytest.raises(ValidationError):
        AlertCondition(id="c1", field="score", operator=AlertOperator.BETWEEN, value=[5])


def test_alert_condition_between_rejects_low_greater_than_high() -> None:
    with pytest.raises(ValidationError):
        AlertCondition(id="c1", field="score", operator=AlertOperator.BETWEEN, value=[20, 5])


def test_alert_condition_between_accepts_equal_bounds() -> None:
    condition = AlertCondition(id="c1", field="score", operator=AlertOperator.BETWEEN, value=[10, 10])
    assert condition.value == [10, 10]


def test_alert_condition_in_rejects_empty_list() -> None:
    with pytest.raises(ValidationError):
        AlertCondition(id="c1", field="ticker", operator=AlertOperator.IN, value=[])


def test_alert_condition_not_in_rejects_empty_list() -> None:
    with pytest.raises(ValidationError):
        AlertCondition(id="c1", field="ticker", operator=AlertOperator.NOT_IN, value=[])


def test_alert_condition_in_rejects_non_list_value() -> None:
    with pytest.raises(ValidationError):
        AlertCondition(id="c1", field="ticker", operator=AlertOperator.IN, value="AAPL")


# --- AlertCondition: field validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["ticker", "company_name", "signal_name", "category", "triggered", "confidence", "score", "priority", "reason", "timestamp"],
)
def test_alert_condition_accepts_every_valid_signal_result_field(field: str) -> None:
    condition = AlertCondition(id="c1", field=field, operator=AlertOperator.EQUALS, value="x")
    assert condition.field == field


def test_alert_condition_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        AlertCondition(id="c1", field="not_a_real_field", operator=AlertOperator.EQUALS, value=1)


def test_alert_condition_rejects_tuple_typed_signal_result_fields() -> None:
    with pytest.raises(ValidationError):
        AlertCondition(id="c1", field="matched_conditions", operator=AlertOperator.EQUALS, value=1)
    with pytest.raises(ValidationError):
        AlertCondition(id="c1", field="failed_conditions", operator=AlertOperator.EQUALS, value=1)


def test_alert_condition_rejects_blank_field() -> None:
    with pytest.raises(ValidationError):
        AlertCondition(id="c1", field="", operator=AlertOperator.EQUALS, value=1)


def test_alert_condition_is_frozen() -> None:
    condition = make_condition()
    with pytest.raises(ValidationError):
        condition.value = 999


def test_alert_condition_defaults_to_enabled() -> None:
    assert make_condition().enabled is True


def test_alert_condition_requires_non_empty_id() -> None:
    with pytest.raises(ValidationError):
        AlertCondition(id="", field="score", operator=AlertOperator.EQUALS, value=1)


# --- AlertRule: structural validation -----------------------------------------------------------


def test_alert_rule_requires_non_empty_name() -> None:
    with pytest.raises(ValidationError):
        make_rule(name="")


def test_alert_rule_rejects_negative_cooldown() -> None:
    with pytest.raises(ValidationError):
        make_rule(cooldown_minutes=-1)


def test_alert_rule_accepts_zero_cooldown() -> None:
    rule = make_rule(cooldown_minutes=0)
    assert rule.cooldown_minutes == 0


def test_alert_rule_rejects_unknown_channel() -> None:
    with pytest.raises(ValidationError):
        make_rule(channels=("NOT_A_CHANNEL",))


@pytest.mark.parametrize("channel", list(NotificationChannel))
def test_alert_rule_accepts_every_notification_channel(channel: NotificationChannel) -> None:
    rule = make_rule(channels=(channel,))
    assert rule.channels == (channel,)


def test_alert_rule_rejects_unknown_priority() -> None:
    with pytest.raises(ValidationError):
        make_rule(priority="NOT_A_PRIORITY")


@pytest.mark.parametrize("priority", list(AlertPriority))
def test_alert_rule_accepts_every_priority(priority: AlertPriority) -> None:
    rule = make_rule(priority=priority)
    assert rule.priority == priority


def test_alert_rule_rejects_duplicate_condition_id() -> None:
    with pytest.raises(ValidationError):
        make_rule(conditions=(make_condition("c1"), make_condition("c1")))


def test_alert_rule_accepts_unique_condition_ids() -> None:
    rule = make_rule(conditions=(make_condition("c1"), make_condition("c2")))
    assert len(rule.conditions) == 2


def test_alert_rule_defaults() -> None:
    rule = make_rule()
    assert rule.enabled is True
    assert rule.priority == AlertPriority.MEDIUM
    assert rule.cooldown_minutes == 0
    assert rule.repeat_allowed is True
    assert rule.channels == ()
    assert rule.conditions == ()


def test_alert_rule_is_frozen() -> None:
    rule = make_rule()
    with pytest.raises(ValidationError):
        rule.name = "Changed"


def test_alert_rule_rejects_naive_created_at() -> None:
    from datetime import datetime

    with pytest.raises(ValidationError):
        AlertRule(id="r1", name="Bad", created_at=datetime(2026, 1, 1), updated_at=NOW)


def test_alert_rule_rejects_naive_updated_at() -> None:
    from datetime import datetime

    with pytest.raises(ValidationError):
        AlertRule(id="r1", name="Bad", created_at=NOW, updated_at=datetime(2026, 1, 1))


# --- Alert -----------------------------------------------------------


def test_alert_requires_ticker_and_rule_id() -> None:
    with pytest.raises(ValidationError):
        Alert(
            id="a1", rule_id="", ticker="AAPL", signal_name="X", priority=AlertPriority.LOW,
            status=AlertStatus.GENERATED, reason="x", confidence=1, score=1, created_at=NOW,
        )
    with pytest.raises(ValidationError):
        Alert(
            id="a1", rule_id="r1", ticker="", signal_name="X", priority=AlertPriority.LOW,
            status=AlertStatus.GENERATED, reason="x", confidence=1, score=1, created_at=NOW,
        )


def test_alert_rejects_naive_created_at() -> None:
    from datetime import datetime

    with pytest.raises(ValidationError):
        Alert(
            id="a1", rule_id="r1", ticker="AAPL", signal_name="X", priority=AlertPriority.LOW,
            status=AlertStatus.GENERATED, reason="x", confidence=1, score=1, created_at=datetime(2026, 1, 1),
        )


def test_alert_defaults_alert_type_to_signal_triggered() -> None:
    alert = Alert(
        id="a1", rule_id="r1", ticker="AAPL", signal_name="X", priority=AlertPriority.LOW,
        status=AlertStatus.GENERATED, reason="x", confidence=1, score=1, created_at=NOW,
    )
    assert alert.alert_type == "SIGNAL_TRIGGERED"


def test_alert_defaults_eligible_channels_to_empty() -> None:
    alert = Alert(
        id="a1", rule_id="r1", ticker="AAPL", signal_name="X", priority=AlertPriority.LOW,
        status=AlertStatus.GENERATED, reason="x", confidence=1, score=1, created_at=NOW,
    )
    assert alert.eligible_channels == ()


@pytest.mark.parametrize("status", list(AlertStatus))
def test_alert_accepts_every_status(status: AlertStatus) -> None:
    alert = Alert(
        id="a1", rule_id="r1", ticker="AAPL", signal_name="X", priority=AlertPriority.LOW,
        status=status, reason="x", confidence=1, score=1, created_at=NOW,
    )
    assert alert.status == status


# --- AlertBatch -----------------------------------------------------------


def test_alert_batch_defaults_to_empty() -> None:
    batch = AlertBatch(generated=0, suppressed=0, summary="none")
    assert batch.alerts == ()
