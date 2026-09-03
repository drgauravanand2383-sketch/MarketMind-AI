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
from datetime import UTC, datetime, timedelta

import pytest
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
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


def test_cron_schedule_with_timezone_creates_a_job_evaluated_in_that_timezone() -> None:
    """Global Market Intelligence (Phase 1): a `Schedule.timezone` must
    reach the real `CronTrigger`, not be silently dropped — the exact gap
    the Phase 0 audit found (a naive cron fires in the container's own
    local/system timezone, not the requested one)."""
    from app.scheduler.models import Schedule, ScheduleTriggerType

    service, scheduler = _build_service()
    schedule = Schedule(
        workflow_id="global_market_intelligence",
        trigger_type=ScheduleTriggerType.CRON,
        cron_expression="30 8 * * *",
        timezone="Asia/Kolkata",
        initiated_by="scheduler",
    )
    scheduler.register_schedule(schedule)

    service.register_schedule(schedule)

    job = service._ap_scheduler.get_job("global_market_intelligence")
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)
    assert str(job.trigger.timezone) == "Asia/Kolkata"


def test_cron_schedule_without_timezone_preserves_pre_existing_behavior() -> None:
    """A `Schedule` with no `timezone` set (every schedule registered
    before Global Market Intelligence) must behave exactly as before —
    `CronTrigger`'s own default (the local/system timezone), never a
    forced UTC or other implicit change."""
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
        scheduled_run_time=datetime.now(UTC),
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
        triggered_at=datetime.now(UTC),
        result=failed_result,
    )
    event = JobExecutionEvent(
        code=EVENT_JOB_EXECUTED,
        job_id="morning_brief",
        jobstore="default",
        scheduled_run_time=datetime.now(UTC),
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
        triggered_at=datetime.now(UTC),
        result=workflow_execution_result(success=True),
    )
    event = JobExecutionEvent(
        code=EVENT_JOB_EXECUTED,
        job_id="morning_brief",
        jobstore="default",
        scheduled_run_time=datetime.now(UTC),
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


# --- Liveness: canary + watchdog -----------------------------------------------------------


class _Clock:
    """A hand-advanced clock for driving canary/watchdog staleness deterministically."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


async def test_health_check_excludes_the_internal_canary_job() -> None:
    service, scheduler = _build_service()
    scheduler.register_schedule(interval_schedule("real_one", interval_seconds=3600))

    await service.start()
    try:
        # The canary job exists on the AsyncIOScheduler...
        assert service._ap_scheduler.get_job("__apscheduler_canary__") is not None
        # ...but never leaks into the reported counts.
        status = await service.health_check()
        assert status.registered_jobs == 1
    finally:
        await service.shutdown()


async def test_register_schedule_rejects_the_reserved_canary_id() -> None:
    service, _ = _build_service()
    from app.scheduler.models import Schedule, ScheduleTriggerType

    reserved = Schedule(
        workflow_id="__apscheduler_canary__",
        trigger_type=ScheduleTriggerType.INTERVAL,
        interval_seconds=60,
        initiated_by="scheduler",
    )
    with pytest.raises(ValueError, match="reserved"):
        service.register_schedule(reserved)


async def test_dispatching_is_true_immediately_after_start_within_grace() -> None:
    clock = _Clock()
    engine = mock_workflow_engine()
    service = APSchedulerService(Scheduler(engine), clock=clock, enable_watchdog=False)

    await service.start()
    try:
        status = await service.health_check()
        assert status.scheduler_running is True
        assert status.dispatching is True  # canary hasn't fired yet, but grace applies
        assert status.last_canary is None
    finally:
        await service.shutdown()


async def test_dispatching_goes_false_when_the_canary_is_silent_past_the_threshold() -> None:
    clock = _Clock()
    service = APSchedulerService(
        Scheduler(mock_workflow_engine()),
        clock=clock,
        watchdog_stale_after_seconds=300,
        enable_watchdog=False,
    )

    await service.start()
    try:
        clock.advance(301)  # past the grace window, and the canary never stamped
        status = await service.health_check()
        assert status.dispatching is False
    finally:
        await service.shutdown()


async def test_canary_stamp_restores_dispatching_and_is_reported() -> None:
    clock = _Clock()
    service = APSchedulerService(
        Scheduler(mock_workflow_engine()),
        clock=clock,
        watchdog_stale_after_seconds=300,
        enable_watchdog=False,
    )

    await service.start()
    try:
        clock.advance(301)
        assert (await service.health_check()).dispatching is False

        service._stamp_canary()  # what the real interval job does
        status = await service.health_check()
        assert status.dispatching is True
        assert status.last_canary == clock.now
    finally:
        await service.shutdown()


async def test_watchdog_restarts_the_scheduler_when_it_stops_dispatching() -> None:
    clock = _Clock()
    created: list[object] = []

    def factory() -> AsyncIOScheduler:
        sched = AsyncIOScheduler()
        created.append(sched)
        return sched

    service = APSchedulerService(
        Scheduler(mock_workflow_engine()),
        ap_scheduler_factory=factory,
        clock=clock,
        watchdog_check_interval_seconds=0.02,
        watchdog_stale_after_seconds=300,
        canary_interval_seconds=10_000,  # never fires during the test
    )

    await service.start()
    try:
        assert service._watchdog_recoveries == 0
        clock.advance(301)  # scheduler is now "stalled" from the watchdog's view

        recovered = await _wait_until(lambda: service._watchdog_recoveries >= 1, timeout=2.0)
        assert recovered, "watchdog should have restarted the stalled scheduler"

        # After restart the reference clock is 'now' again -> healthy, no runaway loop.
        assert (await service.health_check()).dispatching is True
        assert service._watchdog_recoveries == 1
        assert service._ap_scheduler.running is True
        assert len(created) == 2  # one at construction, one from the single recovery
    finally:
        await service.shutdown()


async def test_restart_rebuilds_a_fresh_scheduler_with_every_schedule_reregistered() -> None:
    service, scheduler = _build_service()
    scheduler.register_schedule(interval_schedule("alpha", interval_seconds=3600))
    scheduler.register_schedule(cron_schedule("beta"))

    await service.start()
    try:
        first = service._ap_scheduler
        await service.restart()

        assert service._ap_scheduler is not first  # genuinely a new instance
        assert service._ap_scheduler.running is True
        assert service._ap_scheduler.get_job("alpha") is not None
        assert service._ap_scheduler.get_job("beta") is not None
        assert service._ap_scheduler.get_job("__apscheduler_canary__") is not None
        assert service._watchdog_recoveries == 1
    finally:
        await service.shutdown()


async def test_shutdown_cancels_the_watchdog_task() -> None:
    service, _ = _build_service()
    await service.start()
    task = service._watchdog_task
    assert task is not None and not task.done()

    await service.shutdown()

    assert task.cancelled() or task.done()
    assert service._watchdog_task is None


async def test_the_real_canary_job_actually_stamps_via_the_timer() -> None:
    """End-to-end: a real (short-interval) canary really fires, proving the
    liveness signal is driven by the actual timer, not just settable by hand."""
    service = APSchedulerService(
        Scheduler(mock_workflow_engine()),
        canary_interval_seconds=0.05,
        enable_watchdog=False,
    )

    await service.start()
    try:
        stamped = await _wait_until(lambda: service._last_canary_at is not None, timeout=2.0)
        assert stamped, "the canary job should have stamped within the timeout"
        assert (await service.health_check()).last_canary is not None
    finally:
        await service.shutdown()
