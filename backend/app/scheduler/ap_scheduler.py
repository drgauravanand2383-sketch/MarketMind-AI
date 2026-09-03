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

Liveness — canary + watchdog
============================
`AsyncIOScheduler.start()` reports `running=True` synchronously, but the
scheduler only actually fires jobs if its captured event loop keeps being
driven. A rare startup race (observed in production) left the scheduler
reporting `running=True` while never dispatching a single job for ~20h —
completely silent, because nothing checked whether the *timer* was alive,
only whether `.start()` had been called.

Two additions close that gap:
  - **Canary job** (`_CANARY_JOB_ID`) — an internal interval job whose only
    effect is stamping `_last_canary_at`. A recent stamp is positive proof
    the timer loop is running; its absence past a grace window is proof it
    is not. Excluded from every externally-meaningful count in
    `health_check()`.
  - **Watchdog** (`_watchdog_loop`) — an independent `asyncio.Task` (NOT an
    APScheduler job: a dead scheduler could never run its own watchdog).
    When the canary goes stale it logs CRITICAL and calls `restart()`,
    which tears down the AsyncIOScheduler and builds a fresh one on the
    *current* (definitely-running) event loop, re-registering every
    schedule.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
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

#: Job id of the internal liveness canary — reserved, never a real
#: `workflow_id`, and filtered out of every count `health_check()` reports.
_CANARY_JOB_ID = "__apscheduler_canary__"

_DEFAULT_CANARY_INTERVAL_SECONDS = 60.0
_DEFAULT_WATCHDOG_CHECK_INTERVAL_SECONDS = 120.0
#: The scheduler is considered stalled once the canary hasn't stamped
#: (nor, before the first stamp, has the scheduler been up) for this long.
#: 5x the default canary interval — several consecutive missed ticks, not
#: one slow one.
_DEFAULT_WATCHDOG_STALE_AFTER_SECONDS = 300.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


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

    def __init__(
        self,
        scheduler: Scheduler,
        ap_scheduler: AsyncIOScheduler | None = None,
        *,
        ap_scheduler_factory: Callable[[], AsyncIOScheduler] = AsyncIOScheduler,
        clock: Callable[[], datetime] = _utc_now,
        canary_interval_seconds: float = _DEFAULT_CANARY_INTERVAL_SECONDS,
        watchdog_check_interval_seconds: float = _DEFAULT_WATCHDOG_CHECK_INTERVAL_SECONDS,
        watchdog_stale_after_seconds: float = _DEFAULT_WATCHDOG_STALE_AFTER_SECONDS,
        enable_watchdog: bool = True,
    ) -> None:
        """Initialize with the Scheduler to fire and (optionally) an injected AsyncIOScheduler.

        Args:
            scheduler: The Scheduler owning schedule definitions and
                execution (Sprint 31). Never replaced or bypassed.
            ap_scheduler: The AsyncIOScheduler instance to drive. Defaults
                to a fresh one; tests may inject their own for isolation.
            ap_scheduler_factory: How `restart()` builds a replacement
                AsyncIOScheduler. Defaults to the class itself; tests that
                need to inspect the post-restart instance inject a factory.
            clock: Injectable "now" — tests drive canary staleness with it.
            canary_interval_seconds: How often the internal liveness canary
                job stamps `_last_canary_at`.
            watchdog_check_interval_seconds: How often the watchdog task
                checks whether the scheduler is still dispatching.
            watchdog_stale_after_seconds: How long without a canary stamp
                (or, before the first stamp, since start) before the
                watchdog declares the scheduler stalled and restarts it.
            enable_watchdog: Set `False` to skip spawning the watchdog task
                (tests that only exercise registration/health).
        """
        self._scheduler = scheduler
        self._ap_scheduler_factory = ap_scheduler_factory
        self._ap_scheduler = ap_scheduler if ap_scheduler is not None else ap_scheduler_factory()
        self._clock = clock
        self._canary_interval_seconds = canary_interval_seconds
        self._watchdog_check_interval_seconds = watchdog_check_interval_seconds
        self._watchdog_stale_after_seconds = watchdog_stale_after_seconds
        self._enable_watchdog = enable_watchdog
        self._last_execution_at: datetime | None = None
        self._last_canary_at: datetime | None = None
        self._brought_up_at: datetime | None = None
        self._watchdog_recoveries = 0
        self._watchdog_task: asyncio.Task[None] | None = None
        self._attach_listener()

    # --- registration -----------------------------------------------------------

    def _attach_listener(self) -> None:
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
        if schedule.workflow_id == _CANARY_JOB_ID:
            raise ValueError(f"{_CANARY_JOB_ID!r} is reserved for the internal liveness canary.")

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

    def _register_canary(self) -> None:
        """(Re)register the internal liveness canary job."""
        if self._ap_scheduler.get_job(_CANARY_JOB_ID) is not None:
            self._ap_scheduler.remove_job(_CANARY_JOB_ID)
        self._ap_scheduler.add_job(
            self._stamp_canary,
            trigger=IntervalTrigger(seconds=self._canary_interval_seconds),
            id=_CANARY_JOB_ID,
        )

    def _stamp_canary(self) -> None:
        self._last_canary_at = self._clock()

    # --- lifecycle -----------------------------------------------------------

    def _bring_up(self) -> None:
        """Register every schedule + the canary, then start the AsyncIOScheduler."""
        self.register_all()
        self._register_canary()
        self._ap_scheduler.start()
        self._brought_up_at = self._clock()

    async def start(self) -> None:
        """Register every currently-known schedule, start firing jobs, and arm the watchdog."""
        self._bring_up()
        if self._enable_watchdog and (self._watchdog_task is None or self._watchdog_task.done()):
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def restart(self) -> None:
        """Tear down the AsyncIOScheduler and build a fresh one on the current event loop.

        Recovery path for a scheduler that reports `running=True` but has
        stopped dispatching (its captured event loop is no longer the one
        being driven — the exact silent failure the watchdog detects). A
        brand-new `AsyncIOScheduler` re-captures `asyncio.get_running_loop()`
        at its own `start()`; since `restart()` is only ever called from
        the watchdog task, that is guaranteed to be the live serving loop.

        Never raises: teardown of a possibly-wedged scheduler is
        best-effort, and a failure here must not kill the watchdog.
        """
        with contextlib.suppress(Exception):
            if self._ap_scheduler.running:
                self._ap_scheduler.shutdown(wait=False)

        self._ap_scheduler = self._ap_scheduler_factory()
        self._attach_listener()
        self._last_canary_at = None
        self._bring_up()
        self._watchdog_recoveries += 1
        _logger.critical(
            "apscheduler_watchdog_restarted",
            extra={"total_recoveries": self._watchdog_recoveries},
        )

    async def shutdown(self) -> None:
        """Gracefully stop: cancel the watchdog, wait for any in-flight job, then release resources.

        `AsyncIOScheduler.shutdown()` defers its actual state change to a
        `call_soon_threadsafe` callback rather than applying it inline, so
        without yielding back to the event loop at least once afterward,
        `self._ap_scheduler.running` would still (misleadingly) read True
        immediately after this call returns. The `sleep(0)` below is that
        one required yield — not a real delay, and not a polling loop.
        """
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog_task
            self._watchdog_task = None
        with contextlib.suppress(Exception):
            self._ap_scheduler.shutdown(wait=True)
        await asyncio.sleep(0)

    # --- liveness -----------------------------------------------------------

    def _is_dispatching(self, now: datetime | None = None) -> bool:
        """Whether the timer loop is confirmed alive.

        `True` if the canary stamped within the staleness window; before
        the first stamp, `True` only while still inside the startup grace
        window (equal to the same staleness threshold, measured from
        `_bring_up`). `False` once the scheduler is stopped, or the canary
        has been silent past that window.
        """
        now = now or self._clock()
        if not self._ap_scheduler.running:
            return False
        reference = self._last_canary_at or self._brought_up_at
        if reference is None:
            return True  # never brought up — `scheduler_running` already conveys that
        return (now - reference).total_seconds() <= self._watchdog_stale_after_seconds

    async def _watchdog_loop(self) -> None:
        """Periodically verify the scheduler is dispatching; restart it if not.

        An independent task, never an APScheduler job — a scheduler that
        has stopped firing jobs could never run a job that checks whether
        it has stopped firing jobs. Never dies on a transient error;
        only `CancelledError` (from `shutdown()`) ends it.
        """
        while True:
            try:
                await asyncio.sleep(self._watchdog_check_interval_seconds)
                if self._is_dispatching():
                    continue
                _logger.critical(
                    "apscheduler_not_dispatching",
                    extra={
                        "scheduler_running": self._ap_scheduler.running,
                        "last_canary_at": self._last_canary_at.isoformat() if self._last_canary_at else None,
                        "brought_up_at": self._brought_up_at.isoformat() if self._brought_up_at else None,
                        "prior_recoveries": self._watchdog_recoveries,
                    },
                )
                await self.restart()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - the watchdog must outlive any transient error
                _logger.error("apscheduler_watchdog_error", extra={"error": str(exc)})

    async def health_check(self) -> SchedulerHealthStatus:
        """Report combined Scheduler + APScheduler state. No workflow is executed to produce this.

        A job's `next_run_time` attribute raises `AttributeError` while
        the job is still "pending" (added before the scheduler has ever
        been started) — `getattr(..., None)` treats that the same as "not
        yet known" rather than crashing the health check. The internal
        canary job is excluded from `registered_jobs` and `next_execution`
        — it is not a schedule anyone registered or should see.
        """
        base = self._scheduler.health_check()
        jobs = [job for job in self._ap_scheduler.get_jobs() if job.id != _CANARY_JOB_ID]
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
            dispatching=self._is_dispatching(),
            last_canary=self._last_canary_at,
            watchdog_recoveries=self._watchdog_recoveries,
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

        The internal canary job is intentionally not treated as an
        "execution" — it does no work worth recording, and letting it
        advance `_last_execution_at` would mask a real workflow backlog.
        """
        if event.job_id == _CANARY_JOB_ID:
            return
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
