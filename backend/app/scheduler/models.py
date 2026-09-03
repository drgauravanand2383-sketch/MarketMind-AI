"""Schemas for the Scheduler service.

`Schedule` is a typed, validated description of when a registered workflow
should run. `ScheduleExecutionRecord` and `SchedulerHealthStatus` describe
the outcome of triggering one, and the state of the Scheduler as a whole,
respectively. None of these models contain scheduling or execution logic
themselves — that lives in scheduler.py.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.workflows.models import WorkflowExecutionResult

__all__ = [
    "ScheduleTriggerType",
    "Schedule",
    "ScheduleExecutionRecord",
    "SchedulerHealthStatus",
]


class ScheduleTriggerType(StrEnum):
    """How a Schedule determines when its workflow is due to run.

    Distinct from `app.core.context.TriggerType`, which records how one
    *execution* was initiated — every execution the Scheduler triggers
    uses `TriggerType.SCHEDULED` there, regardless of which kind of
    Schedule triggered it.
    """

    INTERVAL = "interval"
    CRON = "cron"


class Schedule(BaseModel):
    """A registered, typed description of when one workflow should run.

    `trigger_type` is the discriminator for exactly one of
    `interval_seconds` / `cron_expression`: INTERVAL schedules require
    `interval_seconds` and forbid `cron_expression`; CRON schedules
    require `cron_expression` and forbid `interval_seconds`.

    Cron scheduling is represented here (Sprint 31) but not evaluated —
    `Scheduler.run_all_due()` only ever auto-triggers INTERVAL schedules,
    since evaluating a cron expression against the current time would
    require a cron library, which this sprint is explicitly scoped to
    exclude. CRON schedules can still be registered, listed, and triggered
    directly via `Scheduler.run_schedule()`; this field exists so a future
    sprint can wire real cron evaluation into `run_all_due()` without a
    model change.
    """

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    enabled: bool = True
    trigger_type: ScheduleTriggerType
    interval_seconds: float | None = Field(default=None, gt=0)
    cron_expression: str | None = Field(default=None, min_length=1)
    timezone: str | None = Field(default=None, min_length=1)
    """IANA timezone name (e.g. `"Asia/Kolkata"`) a CRON schedule's
    `cron_expression` is evaluated in. `None` (the default, unchanged
    behavior for every pre-existing schedule) means the process's own
    local/system timezone — `APSchedulerService._build_trigger` passes
    this straight to `CronTrigger.from_crontab(cron_expression,
    timezone=...)`. Ignored for INTERVAL schedules (interval firing has
    no timezone-dependent "time of day" to anchor)."""
    initiated_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_trigger_fields(self) -> Schedule:
        if self.trigger_type is ScheduleTriggerType.INTERVAL:
            if self.interval_seconds is None:
                raise ValueError("interval_seconds is required when trigger_type is INTERVAL")
            if self.cron_expression is not None:
                raise ValueError("cron_expression must not be set when trigger_type is INTERVAL")
        else:  # ScheduleTriggerType.CRON
            if self.cron_expression is None:
                raise ValueError("cron_expression is required when trigger_type is CRON")
            if self.interval_seconds is not None:
                raise ValueError("interval_seconds must not be set when trigger_type is CRON")
        return self


class ScheduleExecutionRecord(BaseModel):
    """The outcome of one Scheduler-triggered execution, with scheduling metadata attached.

    Wraps a `WorkflowExecutionResult` (WorkflowEngine's own standardized
    result) with metadata specific to *why* this execution happened —
    which workflow's schedule triggered it, and when.
    """

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    execution_id: str
    trace_id: str
    triggered_at: datetime
    result: WorkflowExecutionResult


class SchedulerHealthStatus(BaseModel):
    """Health snapshot for the scheduling subsystem. No workflow is executed to produce this.

    The first four fields are Scheduler's own (Sprint 31): what's
    registered, independent of any timer. `scheduler_running` /
    `registered_jobs` / `last_execution` / `next_execution` describe the
    APScheduler integration (Sprint 35). `dispatching` / `last_canary` /
    `watchdog_recoveries` (added later) distinguish a scheduler that is
    genuinely *ticking* from one that reports `scheduler_running=True` but
    has silently stopped firing jobs — see `APSchedulerService`'s canary
    and watchdog. Every APScheduler-derived field defaults to the "no
    timer wired up" value so `Scheduler.health_check()` still produces a
    valid status on its own; `APSchedulerService.health_check()`
    (ap_scheduler.py) populates them from the real AsyncIOScheduler.
    """

    model_config = ConfigDict(extra="forbid")

    scheduler_healthy: bool
    workflow_engine_available: bool
    registered_schedules: int
    enabled_schedules: int
    scheduler_running: bool = False
    registered_jobs: int = 0
    last_execution: datetime | None = None
    next_execution: datetime | None = None
    #: Whether the timer loop is confirmed alive — the internal canary job
    #: fired within the staleness threshold (or startup grace still
    #: applies). `False` while `scheduler_running` is `True` is exactly
    #: the silent-failure mode the watchdog exists to catch.
    dispatching: bool = True
    #: When the internal canary job last ran (`None` before its first
    #: tick, or when no APScheduler timer is wired up).
    last_canary: datetime | None = None
    #: How many times the watchdog has torn down and recreated the
    #: AsyncIOScheduler after detecting it had stopped dispatching.
    watchdog_recoveries: int = 0
