"""Tests for WorkflowEngine.

Covers registration, duplicate registration, unregistration, successful
and failed execution, unknown workflow lookup, execution metadata, and
duration calculation. Every "workflow" here is a hand-written stub
satisfying WorkflowProtocol — no filesystem, network, or database is
touched anywhere.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.workflows.engine import (
    WorkflowAlreadyRegisteredError,
    WorkflowEngine,
    WorkflowNotRegisteredError,
)


class _StubWorkflow:
    """A minimal WorkflowProtocol implementation with full call control."""

    def __init__(self, output: Any = None, error: Exception | None = None, delay: float = 0.0) -> None:
        self._output = output
        self._error = error
        self._delay = delay
        self.calls: list[ExecutionContext] = []

    async def execute(self, context: ExecutionContext) -> Any:
        self.calls.append(context)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error is not None:
            raise self._error
        return self._output


def _context(execution_id: str = "exec-1") -> ExecutionContext:
    return ExecutionContext(
        workflow_id="WF-TEST",
        execution_id=execution_id,
        workflow_type="test",
        trigger=TriggerType.USER_REQUEST,
        initiated_by="test",
        started_at=datetime.now(timezone.utc),
        trace_id=execution_id,
        participating_agents=(),
        status=WorkflowStatus.RUNNING,
    )


# --- Registration -----------------------------------------------------------


def test_register_workflow_appears_in_list_workflows() -> None:
    engine = WorkflowEngine()
    engine.register_workflow("morning_brief", _StubWorkflow())

    assert engine.list_workflows() == ["morning_brief"]


def test_list_workflows_returns_sorted_ids() -> None:
    engine = WorkflowEngine()
    engine.register_workflow("zeta", _StubWorkflow())
    engine.register_workflow("alpha", _StubWorkflow())

    assert engine.list_workflows() == ["alpha", "zeta"]


def test_list_workflows_empty_when_nothing_registered() -> None:
    engine = WorkflowEngine()
    assert engine.list_workflows() == []


# --- Duplicate registration -----------------------------------------------------------


def test_duplicate_registration_raises() -> None:
    engine = WorkflowEngine()
    engine.register_workflow("morning_brief", _StubWorkflow())

    with pytest.raises(WorkflowAlreadyRegisteredError):
        engine.register_workflow("morning_brief", _StubWorkflow())


def test_duplicate_registration_does_not_replace_existing_workflow() -> None:
    engine = WorkflowEngine()
    first = _StubWorkflow(output="first")
    engine.register_workflow("morning_brief", first)

    try:
        engine.register_workflow("morning_brief", _StubWorkflow(output="second"))
    except WorkflowAlreadyRegisteredError:
        pass

    assert engine.list_workflows() == ["morning_brief"]


# --- Unregister -----------------------------------------------------------


def test_unregister_removes_workflow() -> None:
    engine = WorkflowEngine()
    engine.register_workflow("morning_brief", _StubWorkflow())

    engine.unregister_workflow("morning_brief")

    assert engine.list_workflows() == []


def test_unregister_unknown_id_is_a_no_op() -> None:
    engine = WorkflowEngine()
    engine.unregister_workflow("does-not-exist")  # must not raise
    assert engine.list_workflows() == []


async def test_unregistered_workflow_can_no_longer_be_executed() -> None:
    engine = WorkflowEngine()
    engine.register_workflow("morning_brief", _StubWorkflow())
    engine.unregister_workflow("morning_brief")

    with pytest.raises(WorkflowNotRegisteredError):
        await engine.execute("morning_brief", _context())


# --- Successful execution -----------------------------------------------------------


async def test_execute_successful_workflow_returns_success_result() -> None:
    engine = WorkflowEngine()
    engine.register_workflow("morning_brief", _StubWorkflow(output={"report": "ok"}))

    result = await engine.execute("morning_brief", _context())

    assert result.success is True
    assert result.output == {"report": "ok"}
    assert result.error is None


async def test_execute_passes_the_same_context_to_the_workflow() -> None:
    engine = WorkflowEngine()
    workflow = _StubWorkflow()
    engine.register_workflow("morning_brief", workflow)
    context = _context()

    await engine.execute("morning_brief", context)

    assert len(workflow.calls) == 1
    assert workflow.calls[0] is context


# --- Failed execution -----------------------------------------------------------


async def test_execute_failed_workflow_returns_failure_result_not_raise() -> None:
    engine = WorkflowEngine()
    engine.register_workflow(
        "morning_brief", _StubWorkflow(error=RuntimeError("simulated workflow failure"))
    )

    result = await engine.execute("morning_brief", _context())

    assert result.success is False
    assert result.output is None
    assert result.error == "simulated workflow failure"


async def test_execute_failed_workflow_does_not_raise_out_of_execute() -> None:
    engine = WorkflowEngine()
    engine.register_workflow(
        "morning_brief", _StubWorkflow(error=ValueError("bad input"))
    )

    # Should complete normally, not propagate the ValueError.
    result = await engine.execute("morning_brief", _context())
    assert result.success is False


# --- Unknown workflow -----------------------------------------------------------


async def test_execute_unknown_workflow_raises_not_registered_error() -> None:
    engine = WorkflowEngine()

    with pytest.raises(WorkflowNotRegisteredError):
        await engine.execute("does-not-exist", _context())


async def test_unknown_workflow_error_carries_the_workflow_id() -> None:
    engine = WorkflowEngine()

    with pytest.raises(WorkflowNotRegisteredError) as excinfo:
        await engine.execute("does-not-exist", _context())

    assert excinfo.value.workflow_id == "does-not-exist"


# --- Execution metadata -----------------------------------------------------------


async def test_execution_result_includes_workflow_id() -> None:
    engine = WorkflowEngine()
    engine.register_workflow("morning_brief", _StubWorkflow())

    result = await engine.execute("morning_brief", _context())

    assert result.workflow_id == "morning_brief"


async def test_execution_result_execution_id_matches_context() -> None:
    engine = WorkflowEngine()
    engine.register_workflow("morning_brief", _StubWorkflow())

    result = await engine.execute("morning_brief", _context(execution_id="exec-42"))

    assert result.execution_id == "exec-42"


async def test_execution_result_includes_start_and_completion_timestamps() -> None:
    engine = WorkflowEngine()
    engine.register_workflow("morning_brief", _StubWorkflow())

    result = await engine.execute("morning_brief", _context())

    assert result.started_at is not None
    assert result.completed_at is not None
    assert result.completed_at >= result.started_at


async def test_execution_metadata_present_even_on_failure() -> None:
    engine = WorkflowEngine()
    engine.register_workflow(
        "morning_brief", _StubWorkflow(error=RuntimeError("simulated failure"))
    )

    result = await engine.execute("morning_brief", _context(execution_id="exec-99"))

    assert result.workflow_id == "morning_brief"
    assert result.execution_id == "exec-99"
    assert result.started_at is not None
    assert result.completed_at is not None


# --- Duration calculation -----------------------------------------------------------


async def test_execution_duration_is_non_negative() -> None:
    engine = WorkflowEngine()
    engine.register_workflow("morning_brief", _StubWorkflow())

    result = await engine.execute("morning_brief", _context())

    assert result.duration >= 0.0


async def test_execution_duration_reflects_actual_elapsed_time() -> None:
    """asyncio.sleep()'s contract is "at least N seconds," but platform
    timer resolution (notably on Windows) can occasionally return a hair
    early — so this asserts against a tolerance, not the exact delay."""
    engine = WorkflowEngine()
    engine.register_workflow("morning_brief", _StubWorkflow(delay=0.05))

    result = await engine.execute("morning_brief", _context())

    assert result.duration >= 0.04


async def test_execution_duration_measured_even_on_failure() -> None:
    engine = WorkflowEngine()
    engine.register_workflow(
        "morning_brief", _StubWorkflow(delay=0.05, error=RuntimeError("fail"))
    )

    result = await engine.execute("morning_brief", _context())

    assert result.duration >= 0.04
