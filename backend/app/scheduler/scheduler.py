"""Scheduler — the infrastructure layer that decides when a workflow should run.

Scheduler owns Schedule registrations and, for each triggered execution,
builds a fresh ExecutionContext and hands it to the already-approved
WorkflowEngine to actually run. Scheduler contains no workflow logic,
constructs no reports, and calls no agent directly — every execution is
delegated to `WorkflowEngine.execute()`.

This sprint implements only the scheduling abstraction and execution
coordinator: no timer, background thread, or cron library is used
anywhere in this module. `run_all_due()` must be invoked by an external
caller (a future sprint's timer, cron job, or manual trigger) for
interval-based schedules to actually fire on their interval — this module
does not schedule itself.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.scheduler.models import (
    Schedule,
    ScheduleExecutionRecord,
    SchedulerHealthStatus,
    ScheduleTriggerType,
)
from app.workflows.engine import WorkflowEngine

__all__ = [
    "ScheduleAlreadyRegisteredError",
    "ScheduleNotRegisteredError",
    "ScheduleDisabledError",
    "Scheduler",
]


class ScheduleAlreadyRegisteredError(Exception):
    """Raised when `register_schedule()` is called with a workflow_id already registered."""

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"A schedule is already registered for workflow_id {workflow_id!r}")


class ScheduleNotRegisteredError(Exception):
    """Raised when `run_schedule()` is called with a workflow_id that isn't registered."""

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"No schedule registered for workflow_id {workflow_id!r}")


class ScheduleDisabledError(Exception):
    """Raised when `run_schedule()` is called on a schedule with enabled=False.

    `enabled` gates all execution of a schedule, not only automatic
    triggering via `run_all_due()` — a disabled schedule must not run
    through either path.
    """

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"Schedule for workflow_id {workflow_id!r} is disabled")


class Scheduler:
    """Owns workflow schedules and triggers their execution through WorkflowEngine.

    Scheduler holds no domain knowledge about any workflow's behavior — it
    only tracks *when* a registered workflow should run and delegates the
    *how* entirely to the injected WorkflowEngine. It performs no
    reasoning, builds no reports, and never calls an agent directly.
    """

    def __init__(self, workflow_engine: WorkflowEngine) -> None:
        """Initialize the Scheduler with the WorkflowEngine it will delegate execution to.

        Args:
            workflow_engine: The already-configured WorkflowEngine that
                owns actual workflow execution. Scheduler never constructs,
                replaces, or bypasses this.
        """
        self._workflow_engine = workflow_engine
        self._schedules: dict[str, Schedule] = {}
        self._last_execution: dict[str, ScheduleExecutionRecord] = {}

    def register_schedule(self, schedule: Schedule) -> None:
        """Register `schedule` under its own `workflow_id`.

        Raises:
            ScheduleAlreadyRegisteredError: If a schedule is already
                registered for this workflow_id.
        """
        if schedule.workflow_id in self._schedules:
            raise ScheduleAlreadyRegisteredError(schedule.workflow_id)
        self._schedules[schedule.workflow_id] = schedule

    def remove_schedule(self, workflow_id: str) -> None:
        """Remove a schedule registration, if present. A no-op if absent."""
        self._schedules.pop(workflow_id, None)
        self._last_execution.pop(workflow_id, None)

    def list_schedules(self) -> list[Schedule]:
        """List all currently registered schedules, sorted by workflow_id."""
        return [self._schedules[workflow_id] for workflow_id in sorted(self._schedules)]

    async def run_schedule(self, workflow_id: str) -> ScheduleExecutionRecord:
        """Trigger the schedule registered for `workflow_id` immediately.

        Builds a fresh ExecutionContext for this execution and delegates
        to `WorkflowEngine.execute()` — this method contains no workflow
        logic of its own. Runs regardless of whether the schedule is
        currently "due"; due-ness only gates `run_all_due()`.

        Args:
            workflow_id: The id of a previously registered schedule. This
                is also the id the workflow itself is registered under in
                WorkflowEngine.

        Returns:
            A ScheduleExecutionRecord describing this execution.

        Raises:
            ScheduleNotRegisteredError: If no schedule is registered for
                `workflow_id`.
            ScheduleDisabledError: If the schedule is registered but
                `enabled` is False.
        """
        schedule = self._schedules.get(workflow_id)
        if schedule is None:
            raise ScheduleNotRegisteredError(workflow_id)
        if not schedule.enabled:
            raise ScheduleDisabledError(workflow_id)

        record = await self._execute(schedule)
        self._last_execution[workflow_id] = record
        return record

    async def run_all_due(self) -> list[ScheduleExecutionRecord]:
        """Trigger every enabled, due INTERVAL schedule and return their execution records.

        Only INTERVAL schedules are ever automatically triggered by this
        method: a CRON schedule requires evaluating a cron expression
        against the current time, which this sprint deliberately does not
        implement (see module docstring). CRON schedules registered today
        are still runnable directly via `run_schedule()`, and remain in
        place for a future sprint to wire real cron evaluation into this
        method.

        An INTERVAL schedule is due if it has never been run by this
        Scheduler instance, or if at least `interval_seconds` have elapsed
        since its last run.
        """
        due_records: list[ScheduleExecutionRecord] = []
        for workflow_id in sorted(self._schedules):
            schedule = self._schedules[workflow_id]
            if not schedule.enabled:
                continue
            if schedule.trigger_type is not ScheduleTriggerType.INTERVAL:
                continue
            if not self._is_due(schedule):
                continue

            record = await self._execute(schedule)
            self._last_execution[workflow_id] = record
            due_records.append(record)
        return due_records

    def health_check(self) -> SchedulerHealthStatus:
        """Report Scheduler state without executing any workflow.

        `workflow_engine_available` reflects only that a WorkflowEngine
        instance was injected at construction — WorkflowEngine exposes no
        health probe of its own, and probing it by actually running a
        workflow would violate this method's "no execution" contract.
        """
        enabled_count = sum(1 for schedule in self._schedules.values() if schedule.enabled)
        return SchedulerHealthStatus(
            scheduler_healthy=True,
            workflow_engine_available=self._workflow_engine is not None,
            registered_schedules=len(self._schedules),
            enabled_schedules=enabled_count,
        )

    def _is_due(self, schedule: Schedule) -> bool:
        """Whether an INTERVAL schedule's interval has elapsed since its last run."""
        last_record = self._last_execution.get(schedule.workflow_id)
        if last_record is None:
            return True
        assert schedule.interval_seconds is not None  # guaranteed by Schedule's own validation
        elapsed = (datetime.now(UTC) - last_record.triggered_at).total_seconds()
        return elapsed >= schedule.interval_seconds

    async def _execute(self, schedule: Schedule) -> ScheduleExecutionRecord:
        """Build a fresh ExecutionContext and delegate execution to WorkflowEngine.

        Note: `workflow_type` and `participating_agents` have no source on
        Schedule (per Sprint 31's schedule model, which does not carry
        either). `workflow_type` is set to `schedule.workflow_id`, the only
        identifier Scheduler has for the workflow; `participating_agents`
        is left empty, since Scheduler has no knowledge of which agents a
        workflow it does not inspect will invoke.
        """
        execution_id = str(uuid.uuid4())
        triggered_at = datetime.now(UTC)
        context = ExecutionContext(
            workflow_id=schedule.workflow_id,
            execution_id=execution_id,
            workflow_type=schedule.workflow_id,
            trigger=TriggerType.SCHEDULED,
            initiated_by=schedule.initiated_by,
            started_at=triggered_at,
            trace_id=execution_id,
            participating_agents=(),
            status=WorkflowStatus.RUNNING,
        )
        result = await self._workflow_engine.execute(schedule.workflow_id, context)
        return ScheduleExecutionRecord(
            workflow_id=schedule.workflow_id,
            execution_id=execution_id,
            trace_id=execution_id,
            triggered_at=triggered_at,
            result=result,
        )
