"""APScheduler integration — the production job-firing mechanism for Scheduler.

Scheduler (scheduler.py, Sprint 31) owns Schedule definitions and knows how
to trigger one workflow execution (`run_schedule`), but has no timer of its
own — Sprint 31 deliberately excluded timers, background threads, and cron
libraries, leaving external code to decide *when* to call `run_schedule()`.
This module is that external caller: `APSchedulerService` wraps one
`apscheduler.schedulers.asyncio.AsyncIOScheduler`, translates each
registered Schedule into one APScheduler job, and lets APScheduler's own
timer loop fire jobs. Every job's target is `Scheduler.run_schedule`
itself — no scheduling or workflow logic is duplicated here; this module
only decides *when* APScheduler calls it. Scheduler remains the owner of
schedule definitions; APScheduler only executes them.

Trigger translation (Schedule -> APScheduler trigger), see `_build_trigger`:
    - CRON schedules -> CronTrigger, parsed from `Schedule.cron_expression`
      via `CronTrigger.from_crontab()` (standard 5-field crontab syntax),
      evaluated in `Schedule.timezone` when set (Global Market
      Intelligence, Phase 1) — `None` (every pre-existing schedule)
      preserves the original behavior of evaluating in the process's own
      local/system timezone, unchanged.
    - INTERVAL schedules -> IntervalTrigger, built from
      `Schedule.interval_seconds`.
    - One-time schedules -> DateTrigger. `Schedule` (Sprint 31) has no
      `ScheduleTriggerType.ONCE`, and this sprint must not redesign it, so
      a one-time run is represented as an INTERVAL schedule (satisfying
      Schedule's own validation, which requires `interval_seconds` to be
      set whenever `trigger_type` is INTERVAL) carrying a `run_date` key
      in its existing, already-freeform `metadata` dict. `_build_trigger()`
      checks for that key first and, if present, uses DateTrigger instead
      of IntervalTrigger — Schedule itself is unchanged, byte for byte.

Every job is registered under `id=schedule.workflow_id` with
`replace_existing=True`, so registering the same schedule twice replaces
the existing APScheduler job instead of creating a duplicate.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.scheduler.models import (
    Schedule,
    ScheduleExecutionRecord,
    SchedulerHealthStatus,
    ScheduleTriggerType,
)
from app.scheduler.scheduler import Scheduler

__all__ = ["APSchedulerService"]

_logger = logging.getLogger("marketmind.scheduler.apscheduler")


def _build_trigger(schedule: Schedule) -> BaseTrigger:
    """Translate a Schedule into the APScheduler trigger that fires it. See module docstring."""
    run_date = schedule.metadata.get("run_date")
    if run_date is not None:
        return DateTrigger(run_date=run_date)
    if schedule.trigger_type is ScheduleTriggerType.CRON:
        assert schedule.cron_expression is not None  # guaranteed by Schedule's own validation
        return CronTrigger.from_crontab(schedule.cron_expression, timezone=schedule.timezone)
    assert schedule.interval_seconds is not None  # guaranteed by Schedule's own validation
    return IntervalTrigger(seconds=schedule.interval_seconds)


class APSchedulerService:
    """Owns one AsyncIOScheduler and fires already-registered Scheduler schedules.

    Scheduler remains the sole owner of *what* schedules exist and *what*
    happens when one fires (`run_schedule` builds the ExecutionContext,
    invokes `WorkflowEngine.execute()`, and records the outcome — all
    Sprint 31 behavior, unchanged). APSchedulerService only owns *when*:
    each APScheduler job it creates calls `Scheduler.run_schedule(workflow_id)`
    and nothing else — no workflow-specific logic lives here.

    No singleton: construct one instance per application (see bootstrap.py).
    """

    def __init__(self, scheduler: Scheduler, ap_scheduler: AsyncIOScheduler | None = None) -> None:
        """Initialize with the Scheduler to fire and (optionally) an injected AsyncIOScheduler.

        Args:
            scheduler: The Scheduler owning schedule definitions and
                execution (Sprint 31). Never replaced or bypassed.
            ap_scheduler: The AsyncIOScheduler instance to drive. Defaults
                to a fresh one; tests may inject their own for isolation.
        """
        self._scheduler = scheduler
        self._ap_scheduler = ap_scheduler if ap_scheduler is not None else AsyncIOScheduler()
        self._last_execution_at: datetime | None = None
        self._ap_scheduler.add_listener(self._on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    def register_schedule(self, schedule: Schedule) -> None:
        """Create (or replace) the APScheduler job that fires `schedule`.

        Uses `schedule.workflow_id` as the APScheduler job id, so calling
        this twice for the same workflow_id replaces the existing job
        rather than creating a duplicate (Duplicate Protection).

        A disabled schedule (`schedule.enabled is False`) is never given a
        job — if one already exists (e.g. the schedule was enabled at the
        last registration and has since been disabled), it's removed, so
        a disabled schedule can never fire through APScheduler either.

        Note: a job added before `AsyncIOScheduler.start()` is held
        "pending" rather than placed in the live jobstore, and
        `add_job(..., replace_existing=True)`'s dedup check only looks at
        the live jobstore — so re-registering the same workflow_id while
        still pending would otherwise create a second pending job with the
        same id. Explicitly removing any existing job (pending or live)
        first, via `get_job`/`remove_job` (both of which do see pending
        jobs), makes duplicate protection hold regardless of whether the
        scheduler has been started yet.
        """
        if self._ap_scheduler.get_job(schedule.workflow_id) is not None:
            self._ap_scheduler.remove_job(schedule.workflow_id)

        if not schedule.enabled:
            return

        trigger = _build_trigger(schedule)
        self._ap_scheduler.add_job(
            self._scheduler.run_schedule,
            trigger=trigger,
            id=schedule.workflow_id,
            args=[schedule.workflow_id],
        )

    def register_all(self) -> None:
        """Register an APScheduler job for every schedule currently in Scheduler."""
        for schedule in self._scheduler.list_schedules():
            self.register_schedule(schedule)

    async def start(self) -> None:
        """Register every currently-known schedule, then start firing jobs."""
        self.register_all()
        self._ap_scheduler.start()

    async def shutdown(self) -> None:
        """Gracefully stop: wait for any in-flight job, then release resources.

        `AsyncIOScheduler.shutdown()` defers its actual state change to a
        `call_soon_threadsafe` callback rather than applying it inline, so
        without yielding back to the event loop at least once afterward,
        `self._ap_scheduler.running` would still (misleadingly) read True
        immediately after this call returns. The `sleep(0)` below is that
        one required yield — not a real delay, and not a polling loop.
        """
        self._ap_scheduler.shutdown(wait=True)
        await asyncio.sleep(0)

    async def health_check(self) -> SchedulerHealthStatus:
        """Report combined Scheduler + APScheduler state. No workflow is executed to produce this.

        A job's `next_run_time` attribute raises `AttributeError` while
        the job is still "pending" (added before the scheduler has ever
        been started) — `getattr(..., None)` treats that the same as "not
        yet known" rather than crashing the health check.
        """
        base = self._scheduler.health_check()
        jobs = self._ap_scheduler.get_jobs()
        upcoming = [
            next_run_time
            for job in jobs
            if (next_run_time := getattr(job, "next_run_time", None)) is not None
        ]
        return SchedulerHealthStatus(
            scheduler_healthy=base.scheduler_healthy,
            workflow_engine_available=base.workflow_engine_available,
            registered_schedules=base.registered_schedules,
            enabled_schedules=base.enabled_schedules,
            scheduler_running=self._ap_scheduler.running,
            registered_jobs=len(jobs),
            last_execution=self._last_execution_at,
            next_execution=min(upcoming) if upcoming else None,
        )

    def _on_job_event(self, event: JobExecutionEvent) -> None:
        """Record + log every job firing — success, workflow-level failure, or a raised exception.

        Failure Handling: neither branch below re-raises. A raised
        exception here would not stop APScheduler's own loop regardless
        (job exceptions are already isolated by APScheduler's executor,
        and this listener itself runs outside the job's own try/except),
        but the point stands either way: one workflow failing — whether by
        raising or by returning success=False — never affects any other
        scheduled job, and the scheduler keeps running.
        """
        self._last_execution_at = datetime.now(UTC)
        if event.exception is not None:
            _logger.error(
                "scheduled_workflow_errored",
                extra={"workflow_id": event.job_id, "error": str(event.exception)},
            )
            return
        record: Any = event.retval
        if isinstance(record, ScheduleExecutionRecord) and not record.result.success:
            _logger.error(
                "scheduled_workflow_failed",
                extra={"workflow_id": event.job_id, "error": record.result.error},
            )
