"""Tests for APSchedulerService (app.scheduler.ap_scheduler).

WorkflowEngine is mocked throughout — no real workflow ever executes. A
real `AsyncIOScheduler` is used (constructing/registering jobs against it
is fast and synchronous); only a small number of tests actually `start()`
it and wait for a real timer tick, using a short interval plus bounded
polling rather than a fixed sleep, to avoid the timing flakiness this
project has hit before with fixed-delay assertions.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import pytest
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.context import ExecutionContext, TriggerType
from app.scheduler.ap_scheduler import APSchedulerService
from app.scheduler.models import ScheduleExecutionRecord
from app.scheduler.scheduler import Scheduler
from tests.scheduler.conftest import (
    cron_schedule,
    interval_schedule,
    mock_workflow_engine,
    one_time_schedule,
    workflow_execution_result,
)


async def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.02) -> bool:
    """Poll `predicate` up to `timeout` seconds instead of a fixed sleep."""
    elapsed = 0.0
    while elapsed < timeout:
        if predicate():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return False


def _build_service(engine=None) -> tuple[APSchedulerService, Scheduler]:
    engine = engine if engine is not None else mock_workflow_engine()
    scheduler = Scheduler(engine)
    return APSchedulerService(scheduler), scheduler


# --- Scheduler starts / stops -----------------------------------------------------------


async def test_start_marks_scheduler_running() -> None:
    service, _ = _build_service()
    await service.start()
    try:
        status = await service.health_check()
        assert status.scheduler_running is True
    finally:
        await service.shutdown()


async def test_shutdown_marks_scheduler_stopped() -> None:
    service, _ = _build_service()
    await service.start()

    await service.shutdown()

    status = await service.health_check()
    assert status.scheduler_running is False


# --- Registration: cron / interval / one-time -----------------------------------------------------------


def test_cron_schedule_creates_a_job_with_cron_trigger() -> None:
    service, scheduler = _build_service()
    schedule = cron_schedule("morning_brief")
    scheduler.register_schedule(schedule)

    service.register_schedule(schedule)

    job = service._ap_scheduler.get_job("morning_brief")
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)


def test_interval_schedule_creates_a_job_with_interval_trigger() -> None:
    service, scheduler = _build_service()
    schedule = interval_schedule("morning_brief", interval_seconds=120.0)
    scheduler.register_schedule(schedule)

    service.register_schedule(schedule)

    job = service._ap_scheduler.get_job("morning_brief")
    assert job is not None
    assert isinstance(job.trigger, IntervalTrigger)


def test_one_time_schedule_creates_a_job_with_date_trigger() -> None:
    service, scheduler = _build_service()
    schedule = one_time_schedule("morning_brief")
    scheduler.register_schedule(schedule)

    service.register_schedule(schedule)

    job = service._ap_scheduler.get_job("morning_brief")
    assert job is not None
    assert isinstance(job.trigger, DateTrigger)


def test_register_all_creates_a_job_for_every_scheduler_schedule() -> None:
    service, scheduler = _build_service()
    scheduler.register_schedule(interval_schedule("a"))
    scheduler.register_schedule(cron_schedule("b"))

    service.register_all()

    assert {job.id for job in service._ap_scheduler.get_jobs()} == {"a", "b"}


def test_disabled_schedule_gets_no_job() -> None:
    service, scheduler = _build_service()
    schedule = interval_schedule("morning_brief", enabled=False)
    scheduler.register_schedule(schedule)

    service.register_schedule(schedule)

    assert service._ap_scheduler.get_job("morning_brief") is None


def test_disabling_a_previously_registered_schedule_removes_its_job() -> None:
    service, scheduler = _build_service()
    enabled_schedule = interval_schedule("morning_brief", enabled=True)
    scheduler.register_schedule(enabled_schedule)
    service.register_schedule(enabled_schedule)
    assert service._ap_scheduler.get_job("morning_brief") is not None

    disabled_schedule = interval_schedule("morning_brief", enabled=False)
    service.register_schedule(disabled_schedule)

    assert service._ap_scheduler.get_job("morning_brief") is None


# --- Duplicate protection -----------------------------------------------------------


def test_registering_the_same_schedule_twice_does_not_duplicate_the_job() -> None:
    service, scheduler = _build_service()
    schedule = interval_schedule("morning_brief")
    scheduler.register_schedule(schedule)

    service.register_schedule(schedule)
    service.register_schedule(schedule)

    assert len(service._ap_scheduler.get_jobs()) == 1


def test_calling_register_all_twice_does_not_duplicate_jobs() -> None:
    service, scheduler = _build_service()
    scheduler.register_schedule(interval_schedule("a"))
    scheduler.register_schedule(cron_schedule("b"))

    service.register_all()
    service.register_all()

    assert len(service._ap_scheduler.get_jobs()) == 2


# --- Execution -----------------------------------------------------------


async def test_registered_job_target_is_scheduler_run_schedule() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    service, scheduler = _build_service(engine)
    schedule = interval_schedule("morning_brief")
    scheduler.register_schedule(schedule)
    service.register_schedule(schedule)

    job = service._ap_scheduler.get_job("morning_brief")
    assert job.func == scheduler.run_schedule
    assert job.args == ("morning_brief",)


async def test_execution_context_is_created_when_the_job_fires() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    service, scheduler = _build_service(engine)
    schedule = interval_schedule("morning_brief", initiated_by="apscheduler")
    scheduler.register_schedule(schedule)
    service.register_schedule(schedule)
    job = service._ap_scheduler.get_job("morning_brief")

    await job.func(*job.args)

    context = engine.execute.call_args.args[1]
    assert isinstance(context, ExecutionContext)
    assert context.workflow_id == "morning_brief"
    assert context.trigger == TriggerType.SCHEDULED
    assert context.initiated_by == "apscheduler"


async def test_workflow_engine_execute_is_invoked_when_the_job_fires() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    service, scheduler = _build_service(engine)
    schedule = interval_schedule("morning_brief")
    scheduler.register_schedule(schedule)
    service.register_schedule(schedule)
    job = service._ap_scheduler.get_job("morning_brief")

    await job.func(*job.args)

    engine.execute.assert_awaited_once()
    assert engine.execute.call_args.args[0] == "morning_brief"


async def test_workflow_actually_executes_via_a_real_apscheduler_timer() -> None:
    """End-to-end: register through APSchedulerService.start(), let a real
    (short) interval elapse, and confirm the job really fired — not just
    that it's wired correctly (the tests above already cover the wiring
    deterministically). Uses bounded polling, not a fixed sleep."""
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief", interval_seconds=0.05))
    service = APSchedulerService(scheduler)

    await service.start()
    try:
        fired = await _wait_until(lambda: engine.execute.await_count >= 1)
        assert fired, "expected the scheduled workflow to fire within the timeout"
    finally:
        await service.shutdown()


# --- Failure handling -----------------------------------------------------------


def test_raised_exception_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    service, _ = _build_service()
    event = JobExecutionEvent(
        code=EVENT_JOB_ERROR,
        job_id="morning_brief",
        jobstore="default",
        scheduled_run_time=datetime.now(timezone.utc),
        exception=RuntimeError("boom"),
    )

    with caplog.at_level(logging.ERROR, logger="marketmind.scheduler.apscheduler"):
        service._on_job_event(event)

    assert any("scheduled_workflow_errored" in record.message for record in caplog.records)


def test_workflow_level_failure_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    service, _ = _build_service()
    failed_result = workflow_execution_result(success=False, error="simulated failure")
    record = ScheduleExecutionRecord(
        workflow_id="morning_brief",
        execution_id="exec-1",
        trace_id="exec-1",
        triggered_at=datetime.now(timezone.utc),
        result=failed_result,
    )
    event = JobExecutionEvent(
        code=EVENT_JOB_EXECUTED,
        job_id="morning_brief",
        jobstore="default",
        scheduled_run_time=datetime.now(timezone.utc),
        retval=record,
    )

    with caplog.at_level(logging.ERROR, logger="marketmind.scheduler.apscheduler"):
        service._on_job_event(event)

    assert any("scheduled_workflow_failed" in record.message for record in caplog.records)


def test_successful_execution_is_not_logged_as_an_error(caplog: pytest.LogCaptureFixture) -> None:
    service, _ = _build_service()
    record = ScheduleExecutionRecord(
        workflow_id="morning_brief",
        execution_id="exec-1",
        trace_id="exec-1",
        triggered_at=datetime.now(timezone.utc),
        result=workflow_execution_result(success=True),
    )
    event = JobExecutionEvent(
        code=EVENT_JOB_EXECUTED,
        job_id="morning_brief",
        jobstore="default",
        scheduled_run_time=datetime.now(timezone.utc),
        retval=record,
    )

    with caplog.at_level(logging.ERROR, logger="marketmind.scheduler.apscheduler"):
        service._on_job_event(event)

    assert caplog.records == []


async def test_scheduler_remains_running_after_a_job_failure() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result(success=False, error="simulated failure")
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief", interval_seconds=0.05))
    service = APSchedulerService(scheduler)

    await service.start()
    try:
        fired = await _wait_until(lambda: engine.execute.await_count >= 1)
        assert fired
        status = await service.health_check()
        assert status.scheduler_running is True
    finally:
        await service.shutdown()


async def test_a_raising_job_does_not_stop_other_jobs_from_firing() -> None:
    engine = mock_workflow_engine()

    async def _execute(workflow_id: str, context: ExecutionContext):
        if workflow_id == "broken":
            raise RuntimeError("simulated infra failure")
        return workflow_execution_result(workflow_id=workflow_id)

    engine.execute.side_effect = _execute
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("broken", interval_seconds=0.05))
    scheduler.register_schedule(interval_schedule("healthy", interval_seconds=0.05))
    service = APSchedulerService(scheduler)

    await service.start()
    try:
        fired = await _wait_until(lambda: engine.execute.await_count >= 2)
        assert fired
        status = await service.health_check()
        assert status.scheduler_running is True
    finally:
        await service.shutdown()


# --- Health -----------------------------------------------------------


async def test_health_before_start_reports_not_running() -> None:
    service, _ = _build_service()
    status = await service.health_check()
    assert status.scheduler_running is False
    assert status.registered_jobs == 0
    assert status.last_execution is None
    assert status.next_execution is None


async def test_health_registered_jobs_reflects_job_count() -> None:
    service, scheduler = _build_service()
    scheduler.register_schedule(interval_schedule("a"))
    scheduler.register_schedule(interval_schedule("b"))
    service.register_all()

    status = await service.health_check()

    assert status.registered_jobs == 2


async def test_health_next_execution_reflects_the_soonest_job() -> None:
    """A job's `next_run_time` is only computed once the scheduler has
    actually been started — a still-pending (never-started) job legitimately
    has no known next_execution yet, which is why this starts the scheduler
    before asserting."""
    service, scheduler = _build_service()
    scheduler.register_schedule(interval_schedule("a", interval_seconds=3600.0))

    await service.start()
    try:
        status = await service.health_check()
        assert status.next_execution is not None
    finally:
        await service.shutdown()


async def test_health_next_execution_is_none_before_the_scheduler_has_started() -> None:
    service, scheduler = _build_service()
    scheduler.register_schedule(interval_schedule("a", interval_seconds=3600.0))
    service.register_all()

    status = await service.health_check()

    assert status.next_execution is None


async def test_health_last_execution_updates_after_a_job_fires() -> None:
    engine = mock_workflow_engine()
    engine.execute.return_value = workflow_execution_result()
    scheduler = Scheduler(engine)
    scheduler.register_schedule(interval_schedule("morning_brief", interval_seconds=0.05))
    service = APSchedulerService(scheduler)

    before = await service.health_check()
    assert before.last_execution is None

    await service.start()
    try:
        fired = await _wait_until(lambda: engine.execute.await_count >= 1)
        assert fired
        after = await service.health_check()
        assert after.last_execution is not None
    finally:
        await service.shutdown()


async def test_health_includes_base_scheduler_registration_counts() -> None:
    service, scheduler = _build_service()
    scheduler.register_schedule(interval_schedule("a", enabled=True))
    scheduler.register_schedule(interval_schedule("b", enabled=False))

    status = await service.health_check()

    assert status.registered_schedules == 2
    assert status.enabled_schedules == 1
