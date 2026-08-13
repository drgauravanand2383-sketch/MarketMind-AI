"""Shared doubles and factories for Scheduler tests.

WorkflowEngine is mocked throughout (per Sprint 31's testing requirement)
— no real workflow, agent, or WorkflowEngine execution logic runs anywhere
in these tests. `MagicMock(spec=WorkflowEngine)` auto-detects that
`execute()` is a coroutine function and mocks it as an AsyncMock, while
`register_workflow`/`unregister_workflow`/`list_workflows` remain plain
(sync) mocks, matching WorkflowEngine's real method signatures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

from app.scheduler.models import Schedule, ScheduleTriggerType
from app.workflows.engine import WorkflowEngine
from app.workflows.models import WorkflowExecutionResult


def mock_workflow_engine() -> MagicMock:
    return MagicMock(spec=WorkflowEngine)


def workflow_execution_result(
    workflow_id: str = "morning_brief",
    execution_id: str = "exec-1",
    success: bool = True,
    output: Any = None,
    error: str | None = None,
) -> WorkflowExecutionResult:
    now = datetime.now(timezone.utc)
    return WorkflowExecutionResult(
        workflow_id=workflow_id,
        execution_id=execution_id,
        started_at=now,
        completed_at=now,
        duration=0.01,
        success=success,
        output=output,
        error=error,
    )


def interval_schedule(
    workflow_id: str = "morning_brief",
    enabled: bool = True,
    interval_seconds: float = 3600.0,
    initiated_by: str = "scheduler",
    metadata: dict[str, Any] | None = None,
) -> Schedule:
    return Schedule(
        workflow_id=workflow_id,
        enabled=enabled,
        trigger_type=ScheduleTriggerType.INTERVAL,
        interval_seconds=interval_seconds,
        initiated_by=initiated_by,
        metadata=metadata or {},
    )


def cron_schedule(
    workflow_id: str = "morning_brief",
    enabled: bool = True,
    cron_expression: str = "0 6 * * *",
    initiated_by: str = "scheduler",
    metadata: dict[str, Any] | None = None,
) -> Schedule:
    return Schedule(
        workflow_id=workflow_id,
        enabled=enabled,
        trigger_type=ScheduleTriggerType.CRON,
        cron_expression=cron_expression,
        initiated_by=initiated_by,
        metadata=metadata or {},
    )


def one_time_schedule(
    workflow_id: str = "morning_brief",
    enabled: bool = True,
    run_date: datetime | None = None,
    initiated_by: str = "scheduler",
) -> Schedule:
    """A one-time schedule (Sprint 35).

    Schedule (Sprint 31) has no ScheduleTriggerType.ONCE and must not be
    redesigned to add one — see app.scheduler.ap_scheduler's module
    docstring. A one-time run is represented as an INTERVAL schedule
    (satisfying Schedule's own validation) carrying a `run_date` in its
    existing `metadata` dict; APSchedulerService checks for that key and,
    if present, builds a DateTrigger instead of an IntervalTrigger.
    `interval_seconds` here is never actually used as an interval.
    """
    return interval_schedule(
        workflow_id=workflow_id,
        enabled=enabled,
        interval_seconds=1.0,
        initiated_by=initiated_by,
        metadata={"run_date": run_date or datetime.now(timezone.utc)},
    )
