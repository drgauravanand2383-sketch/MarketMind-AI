"""Tests for the Schedule model's validation rules.

Covers the "exactly one of interval_seconds / cron_expression, matching
trigger_type" contract, and basic field defaults/constraints.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.scheduler.models import Schedule, ScheduleTriggerType

# --- Valid construction -----------------------------------------------------------


def test_interval_schedule_constructs_successfully() -> None:
    schedule = Schedule(
        workflow_id="morning_brief",
        trigger_type=ScheduleTriggerType.INTERVAL,
        interval_seconds=3600.0,
        initiated_by="scheduler",
    )
    assert schedule.interval_seconds == 3600.0
    assert schedule.cron_expression is None


def test_cron_schedule_constructs_successfully() -> None:
    schedule = Schedule(
        workflow_id="morning_brief",
        trigger_type=ScheduleTriggerType.CRON,
        cron_expression="0 6 * * *",
        initiated_by="scheduler",
    )
    assert schedule.cron_expression == "0 6 * * *"
    assert schedule.interval_seconds is None


def test_cron_schedule_accepts_an_explicit_timezone() -> None:
    schedule = Schedule(
        workflow_id="global_market_intelligence",
        trigger_type=ScheduleTriggerType.CRON,
        cron_expression="30 8 * * *",
        timezone="Asia/Kolkata",
        initiated_by="scheduler",
    )
    assert schedule.timezone == "Asia/Kolkata"


def test_timezone_defaults_to_none() -> None:
    schedule = Schedule(
        workflow_id="morning_brief",
        trigger_type=ScheduleTriggerType.CRON,
        cron_expression="0 6 * * *",
        initiated_by="scheduler",
    )
    assert schedule.timezone is None


def test_enabled_defaults_to_true() -> None:
    schedule = Schedule(
        workflow_id="morning_brief",
        trigger_type=ScheduleTriggerType.INTERVAL,
        interval_seconds=60.0,
        initiated_by="scheduler",
    )
    assert schedule.enabled is True


def test_metadata_defaults_to_empty_dict() -> None:
    schedule = Schedule(
        workflow_id="morning_brief",
        trigger_type=ScheduleTriggerType.INTERVAL,
        interval_seconds=60.0,
        initiated_by="scheduler",
    )
    assert schedule.metadata == {}


# --- Exactly-one-of validation -----------------------------------------------------------


def test_interval_schedule_without_interval_seconds_raises() -> None:
    with pytest.raises(ValidationError):
        Schedule(
            workflow_id="morning_brief",
            trigger_type=ScheduleTriggerType.INTERVAL,
            initiated_by="scheduler",
        )


def test_interval_schedule_with_cron_expression_also_set_raises() -> None:
    with pytest.raises(ValidationError):
        Schedule(
            workflow_id="morning_brief",
            trigger_type=ScheduleTriggerType.INTERVAL,
            interval_seconds=60.0,
            cron_expression="0 6 * * *",
            initiated_by="scheduler",
        )


def test_cron_schedule_without_cron_expression_raises() -> None:
    with pytest.raises(ValidationError):
        Schedule(
            workflow_id="morning_brief",
            trigger_type=ScheduleTriggerType.CRON,
            initiated_by="scheduler",
        )


def test_cron_schedule_with_interval_seconds_also_set_raises() -> None:
    with pytest.raises(ValidationError):
        Schedule(
            workflow_id="morning_brief",
            trigger_type=ScheduleTriggerType.CRON,
            cron_expression="0 6 * * *",
            interval_seconds=60.0,
            initiated_by="scheduler",
        )


def test_neither_interval_nor_cron_set_raises() -> None:
    with pytest.raises(ValidationError):
        Schedule(
            workflow_id="morning_brief",
            trigger_type=ScheduleTriggerType.INTERVAL,
            initiated_by="scheduler",
        )


# --- Field constraints -----------------------------------------------------------


def test_interval_seconds_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Schedule(
            workflow_id="morning_brief",
            trigger_type=ScheduleTriggerType.INTERVAL,
            interval_seconds=0.0,
            initiated_by="scheduler",
        )


def test_cron_expression_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        Schedule(
            workflow_id="morning_brief",
            trigger_type=ScheduleTriggerType.CRON,
            cron_expression="",
            initiated_by="scheduler",
        )


def test_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Schedule(
            workflow_id="morning_brief",
            trigger_type=ScheduleTriggerType.INTERVAL,
            interval_seconds=60.0,
            initiated_by="scheduler",
            unexpected_field="x",
        )
