"""Pure data object carrying shared state through a single workflow execution.

ExecutionContext implements the design approved for the multi-agent
orchestration model: a frozen, strongly typed record that flows between
agents during one workflow run. It contains no business logic and no
orchestration logic — advancing `current_agent`, changing `status`,
recording an agent's output, appending an error, or registering a memory
reference is performed by external code constructing a new ExecutionContext
via `dataclasses.replace()`. This module defines no method to perform that
replacement itself; that responsibility belongs to the Orchestrator.

This satisfies the forward reference to `app.core.context.ExecutionContext`
used by `app.agents.base.BaseAgent`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from pydantic import BaseModel

__all__ = [
    "TriggerType",
    "WorkflowStatus",
    "ExecutionError",
    "ExecutionContext",
]


class TriggerType(str, Enum):
    """How a workflow execution was initiated."""

    SCHEDULED = "scheduled"
    USER_REQUEST = "user_request"
    UPSTREAM_WORKFLOW = "upstream_workflow"


class WorkflowStatus(str, Enum):
    """The lifecycle state of a workflow execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True)
class ExecutionError:
    """A single recorded failure occurring during a workflow execution."""

    agent_id: str
    error_type: str
    error_message: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Shared state for one workflow execution, passed between agents.

    ExecutionContext is immutable: every field is fixed at construction, and
    the collection fields (`shared_inputs`, `agent_outputs`,
    `memory_references`) are wrapped in read-only mappings that reject
    in-place mutation. Progressing a workflow is done by constructing a new
    ExecutionContext with `dataclasses.replace(context, **changes)` — for
    example, appending an agent output requires passing a new mapping for
    `agent_outputs`, not mutating the existing one.

    Attributes:
        workflow_id: The definition ID of the workflow being run (e.g. "WF-007").
        execution_id: The unique identifier for this specific run.
        workflow_type: The approved workflow type this run corresponds to.
        trigger: What initiated this run.
        initiated_by: The user or system source that triggered the run.
        started_at: The timestamp this execution began.
        trace_id: The correlation ID linking all logs for this run.
        participating_agents: The declared agents involved in this run.
        shared_inputs: Immutable inputs provided at workflow start, available
            to all agents.
        current_agent: The agent presently executing, if any.
        agent_outputs: Accumulated results keyed by agent_id.
        memory_references: Pointers into the Memory Layer relevant to this
            run — references only, never raw memory content.
        errors: Collected error records from any agent that failed during
            this run.
        status: The current lifecycle state of the workflow.
    """

    workflow_id: str
    execution_id: str
    workflow_type: str
    trigger: TriggerType
    initiated_by: str
    started_at: datetime
    trace_id: str
    participating_agents: tuple[str, ...]
    shared_inputs: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    current_agent: str | None = None
    agent_outputs: Mapping[str, BaseModel] = field(default_factory=lambda: MappingProxyType({}))
    memory_references: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    errors: tuple[ExecutionError, ...] = field(default_factory=tuple)
    status: WorkflowStatus = WorkflowStatus.PENDING
