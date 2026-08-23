"""Workflow Engine — the central execution layer for approved workflows.

WorkflowEngine coordinates workflow execution only: it registers already-
built workflow implementations (each satisfying WorkflowProtocol),
executes them by workflow_id, times each run, and returns a standardized
WorkflowExecutionResult. It implements no workflow-specific behavior of
its own, constructs no workflow, and holds no global or singleton state —
every workflow is registered externally by whoever assembles the engine.
No logging is implemented here; only the metadata (workflow id, execution
id, duration, success/failure) that a caller's own logging would need is
exposed on WorkflowExecutionResult.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from app.core.context import ExecutionContext
from app.workflows.models import WorkflowExecutionResult

__all__ = [
    "WorkflowProtocol",
    "WorkflowNotRegisteredError",
    "WorkflowAlreadyRegisteredError",
    "WorkflowEngine",
]


@runtime_checkable
class WorkflowProtocol(Protocol):
    """The contract every workflow registered with WorkflowEngine must satisfy."""

    async def execute(self, context: ExecutionContext) -> Any:
        """Run this workflow to completion, returning its own result shape."""
        ...


class WorkflowNotRegisteredError(Exception):
    """Raised when `execute()` is called with a workflow_id that isn't registered."""

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"No workflow registered under id {workflow_id!r}")


class WorkflowAlreadyRegisteredError(Exception):
    """Raised when `register_workflow()` is called with an id that's already registered."""

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"A workflow is already registered under id {workflow_id!r}")


class WorkflowEngine:
    """Registers and executes workflows by id, returning standardized results.

    WorkflowEngine holds no domain knowledge about any specific workflow —
    it only tracks a mapping of workflow_id to an injected WorkflowProtocol
    implementation, and wraps every execution with timing and error
    handling common to all workflows.
    """

    def __init__(self) -> None:
        self._workflows: dict[str, WorkflowProtocol] = {}

    def register_workflow(self, workflow_id: str, workflow: WorkflowProtocol) -> None:
        """Register `workflow` under `workflow_id`.

        Raises:
            WorkflowAlreadyRegisteredError: If `workflow_id` is already registered.
        """
        if workflow_id in self._workflows:
            raise WorkflowAlreadyRegisteredError(workflow_id)
        self._workflows[workflow_id] = workflow

    def unregister_workflow(self, workflow_id: str) -> None:
        """Remove a workflow registration, if present. A no-op if absent."""
        self._workflows.pop(workflow_id, None)

    def list_workflows(self) -> list[str]:
        """List all currently registered workflow IDs, sorted alphabetically."""
        return sorted(self._workflows)

    async def execute(
        self, workflow_id: str, context: ExecutionContext
    ) -> WorkflowExecutionResult:
        """Execute the workflow registered under `workflow_id`.

        Lifecycle: locate the workflow, record a start timestamp, execute
        it, record a completion timestamp, and return a
        WorkflowExecutionResult. A failure inside the workflow itself
        never propagates out of this method — it is caught and reported
        via `success=False` / `error`.

        Args:
            workflow_id: The id of a previously registered workflow.
            context: The ExecutionContext passed through unchanged to the
                workflow's own `execute()` method.

        Returns:
            A WorkflowExecutionResult.

        Raises:
            WorkflowNotRegisteredError: If `workflow_id` isn't registered —
                this is the one failure mode the engine does not catch,
                since it reflects a caller error, not a workflow failure.
        """
        workflow = self._workflows.get(workflow_id)
        if workflow is None:
            raise WorkflowNotRegisteredError(workflow_id)

        started_at = datetime.now(UTC)
        started_monotonic = time.monotonic()

        try:
            output = await workflow.execute(context)
        except Exception as exc:  # noqa: BLE001 - a workflow's failure must not crash the engine
            return WorkflowExecutionResult(
                workflow_id=workflow_id,
                execution_id=context.execution_id,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration=time.monotonic() - started_monotonic,
                success=False,
                output=None,
                error=str(exc),
            )

        return WorkflowExecutionResult(
            workflow_id=workflow_id,
            execution_id=context.execution_id,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration=time.monotonic() - started_monotonic,
            success=True,
            output=output,
            error=None,
        )
