"""Tests for Scheduler.

WorkflowEngine is mocked throughout — no real workflow ever executes.
Every test instead verifies Scheduler's own responsibilities: owning
schedules, building an ExecutionContext, delegating to
`WorkflowEngine.execute()`, and reporting health without executing
anything.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta

import pytest

from app.core.context import TriggerType, WorkflowStatus
from app.scheduler.scheduler import (
    ScheduleAlreadyRegisteredError,
    ScheduleDisabledError,
    ScheduleNotRegisteredError,
    Scheduler,
)
from tests.scheduler.conftest import (
    cron_schedule,
    interval_schedule,
    mock_workflow_engine,
    workflow_execution_result,
)

# --- Schedule registration -----------------------------------------------------------


def test_register_schedule_appears_in_list_schedules() -> None:
    scheduler = Scheduler(mock_workflow_engine())
    schedule = interval_schedule("morning_brief")

    scheduler.register_schedule(schedule)

    assert scheduler.list_schedules() == [schedule]


def test_list_schedules_returns_sorted_by_workflow_id() -> None:
    scheduler = Scheduler(mock_workflow_engine())
    scheduler.register_schedule(interval_schedule("zeta"))
    scheduler.register_schedule(interval_schedule("alpha"))

    workflow_ids = [schedule.workflow_id for schedule in scheduler.list_schedules()]
    assert workflow_ids == ["alpha", "zeta"]


def test_list_schedules_empty_when_nothing_registered() -> None:
    scheduler = Scheduler(mock_workflow_engine())
    assert scheduler.list_schedules() == []


# --- Duplicate schedule registration -----------------------------------------------------------


def test_duplicate_registration_raises() -> None:
    scheduler = Scheduler(mock_workflow_engine())
    scheduler.register_schedule(interval_schedule("morning_brief"))

    with pytest.raises(ScheduleAlreadyRegisteredError):
        scheduler.register_schedule(interval_schedule("morning_brief"))


def test_duplicate_registration_does_not_replace_existing_schedule() -> None:
    scheduler = Scheduler(mock_workflow_engine())
    first = interval_schedule("morning_brief", interval_seconds=60.0)
    scheduler.register_schedule(first)

    with contextlib.suppress(ScheduleAlreadyRegisteredError):
        scheduler.register_schedule(interval_schedule("morning_brief", interval_seconds=999.0))

    assert scheduler.list_schedules() == [first]


# --- Schedule removal -----------------------------------------------------------


def test_remove_schedule_removes_it() -> None:
    scheduler = Scheduler(mock_workflow_engine())
    scheduler.register_schedule(interval_schedule("morning_brief"))

    scheduler.remove_schedule("morning_brief")

    assert scheduler.list_schedules() == []


def test_remove_unknown_schedule_is_a_no_op() -> None:
    scheduler = Scheduler(mock_workflow_engine())
    scheduler.remove_schedule("does-not-exist")  # must not raise
    assert scheduler.list_schedules() == []


# --- Disabled schedules -----------------------------------------------------------


async def test_run_schedule_on_disabled_schedule_raises() -> None:
    scheduler = Scheduler(mock_workflow_engine())
    scheduler.register_schedule(interval_schedule("morning_brief", enabled=False))

    with pytest.raises(ScheduleDisabledError):
        await scheduler.run_schedule("morning_brief")


async def test_run_all_due_skips_disabled_schedules() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief", enabled=False))

    records = await scheduler.run_all_due()

    assert records == []
    engine.execute.assert_not_awaited()


# --- ExecutionContext creation -----------------------------------------------------------


async def test_run_schedule_builds_execution_context_with_expected_fields() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief", initiated_by="cron-runner"))

    before = datetime.now(UTC)
    record = await scheduler.run_schedule("morning_brief")
    after = datetime.now(UTC)

    context = engine.execute.call_args.args[1]
    assert context.workflow_id == "morning_brief"
    assert context.execution_id == record.execution_id
    assert context.trigger == TriggerType.SCHEDULED
    assert context.initiated_by == "cron-runner"
    assert context.trace_id == context.execution_id
    assert context.status == WorkflowStatus.RUNNING
    assert before <= context.started_at <= after


async def test_run_schedule_builds_a_fresh_execution_id_each_call() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief"))

    first = await scheduler.run_schedule("morning_brief")
    second = await scheduler.run_schedule("morning_brief")

    assert first.execution_id != second.execution_id


# --- WorkflowEngine invocation -----------------------------------------------------------


async def test_run_schedule_invokes_workflow_engine_execute_with_workflow_id_and_context() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief"))

    await scheduler.run_schedule("morning_brief")

    engine.execute.assert_awaited_once()
    assert engine.execute.call_args.args[0] == "morning_brief"


async def test_run_schedule_never_calls_workflow_engine_registration_methods() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief"))

    await scheduler.run_schedule("morning_brief")

    engine.register_workflow.assert_not_called()
    engine.unregister_workflow.assert_not_called()


async def test_run_schedule_unregistered_workflow_id_raises() -> None:
    scheduler = Scheduler(mock_workflow_engine())
    with pytest.raises(ScheduleNotRegisteredError):
        await scheduler.run_schedule("does-not-exist")


# --- Failed workflow execution -----------------------------------------------------------


async def test_run_schedule_returns_record_wrapping_a_failed_result_without_raising() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result(
        success=False, error="simulated workflow failure"
    )
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief"))

    record = await scheduler.run_schedule("morning_brief")

    assert record.result.success is False
    assert record.result.error == "simulated workflow failure"


# --- run_all_due() -----------------------------------------------------------


async def test_run_all_due_runs_a_never_before_run_interval_schedule() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief", interval_seconds=3600.0))

    records = await scheduler.run_all_due()

    assert len(records) == 1
    assert records[0].workflow_id == "morning_brief"


async def test_run_all_due_skips_a_not_yet_due_interval_schedule() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief", interval_seconds=9999.0))

    await scheduler.run_schedule("morning_brief")  # establishes a very recent last-run
    engine.execute.reset_mock()

    records = await scheduler.run_all_due()

    assert records == []
    engine.execute.assert_not_awaited()


async def test_run_all_due_reruns_once_the_interval_has_elapsed() -> None:
    """Backdates the internal last-run timestamp instead of racing the wall
    clock with a near-zero interval — two back-to-back `datetime.now()`
    calls can land on the same instant under Windows' timer resolution,
    which would make "has elapsed" flaky rather than deterministic."""
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief", interval_seconds=60.0))

    first = await scheduler.run_all_due()
    assert len(first) == 1

    stale_record = scheduler._last_execution["morning_brief"].model_copy(
        update={"triggered_at": datetime.now(UTC) - timedelta(seconds=120)}
    )
    scheduler._last_execution["morning_brief"] = stale_record

    second = await scheduler.run_all_due()

    assert len(second) == 1


async def test_run_all_due_never_auto_triggers_cron_schedules() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(cron_schedule("morning_brief"))

    records = await scheduler.run_all_due()

    assert records == []
    engine.execute.assert_not_awaited()


async def test_run_all_due_returns_only_the_schedules_it_actually_ran() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("due-workflow", interval_seconds=3600.0))
    scheduler.register_schedule(interval_schedule("not-due-workflow", interval_seconds=9999.0))
    scheduler.register_schedule(cron_schedule("cron-workflow"))
    scheduler.register_schedule(
        interval_schedule("disabled-workflow", interval_seconds=1.0, enabled=False)
    )
    await scheduler.run_schedule("not-due-workflow")  # makes it recently-run, so not due again
    engine.execute.reset_mock()

    records = await scheduler.run_all_due()

    assert [record.workflow_id for record in records] == ["due-workflow"]


# --- health_check() -----------------------------------------------------------


def test_health_check_reports_registered_and_enabled_counts() -> None:
    scheduler = Scheduler(mock_workflow_engine())
    scheduler.register_schedule(interval_schedule("morning_brief"))
    scheduler.register_schedule(interval_schedule("morning_pipeline", enabled=False))

    status = scheduler.health_check()

    assert status.registered_schedules == 2
    assert status.enabled_schedules == 1
    assert status.scheduler_healthy is True
    assert status.workflow_engine_available is True


def test_health_check_on_empty_scheduler() -> None:
    scheduler = Scheduler(mock_workflow_engine())

    status = scheduler.health_check()

    assert status.registered_schedules == 0
    assert status.enabled_schedules == 0


async def test_health_check_does_not_call_workflow_engine_execute() -> None:
    engine = mock_workflow_engine()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief"))

    scheduler.health_check()

    engine.execute.assert_not_called()
