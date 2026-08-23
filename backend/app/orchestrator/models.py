"""Typed models for the Multi-Agent Orchestrator.

`ExecutionPlan` is intentionally a single, general shape — a dependency
graph of `AgentTask`s — rather than three separate model classes for
sequential/parallel/mixed execution. `ExecutionPlan.sequential()`/
`.parallel()`/`.mixed()` are three named, ergonomic ways to *build* one
(chaining every task to the previous one; leaving every task independent;
or using each task's own `depends_on` as given), but the orchestrator
itself (orchestrator.py) runs all three through exactly one algorithm:
execute every task whose dependencies have already resolved, wave by
wave. Sequential and parallel are just the two degenerate cases of that
one general algorithm — one task per wave, or one wave with every task.

No reasoning, no AI routing, and no planning logic live here — this
module only describes data shapes and validates their internal structural
consistency (no duplicate task ids, no unknown or self dependency, no
dependency cycle).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.orchestrator.exceptions import InvalidExecutionPlanError

__all__ = [
    "ExecutionStatus",
    "AgentTask",
    "AgentExecutionResult",
    "ExecutionPlan",
    "ExecutionNode",
    "ExecutionGraph",
    "ExecutionSummary",
    "OrchestratorHealthStatus",
]


class ExecutionStatus(StrEnum):
    """The terminal state of one task's execution."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentTask(BaseModel):
    """One unit of work: which agent to run, with what input, and after which other tasks."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    task_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    input_data: BaseModel
    depends_on: tuple[str, ...] = Field(default_factory=tuple)


class AgentExecutionResult(BaseModel):
    """The recorded outcome of one executed (or skipped) `AgentTask`."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    execution_id: str
    task_id: str
    agent_id: str
    status: ExecutionStatus
    output: BaseModel | None = None
    error: str | None = None
    start_time: datetime
    finish_time: datetime
    duration: float
    dependencies: tuple[str, ...] = Field(default_factory=tuple)


def _validate_dag(tasks: tuple[AgentTask, ...]) -> None:
    """Raise `InvalidExecutionPlanError` for a duplicate/unknown/self/cyclic dependency."""
    seen_ids: set[str] = set()
    for task in tasks:
        if task.task_id in seen_ids:
            raise InvalidExecutionPlanError(f"Duplicate task_id {task.task_id!r} in ExecutionPlan.")
        seen_ids.add(task.task_id)

    graph: dict[str, tuple[str, ...]] = {task.task_id: task.depends_on for task in tasks}
    for task in tasks:
        for dependency in task.depends_on:
            if dependency == task.task_id:
                raise InvalidExecutionPlanError(f"Task {task.task_id!r} cannot depend on itself.")
            if dependency not in graph:
                raise InvalidExecutionPlanError(
                    f"Task {task.task_id!r} depends on unknown task_id {dependency!r}."
                )

    _WHITE, _GRAY, _BLACK = 0, 1, 2
    color: dict[str, int] = {task_id: _WHITE for task_id in graph}

    def _visit(task_id: str) -> None:
        color[task_id] = _GRAY
        for dependency in graph[task_id]:
            if color[dependency] == _GRAY:
                raise InvalidExecutionPlanError(
                    f"Dependency cycle detected involving task_id {task_id!r}."
                )
            if color[dependency] == _WHITE:
                _visit(dependency)
        color[task_id] = _BLACK

    for task_id in graph:
        if color[task_id] == _WHITE:
            _visit(task_id)


class ExecutionPlan(BaseModel):
    """A dependency graph of `AgentTask`s. Validated to be acyclic and
    internally consistent at construction time — never discovered mid-execution.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tasks: tuple[AgentTask, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate(self) -> ExecutionPlan:
        _validate_dag(self.tasks)
        return self

    @classmethod
    def sequential(cls, tasks: list[AgentTask]) -> ExecutionPlan:
        """Chain every task to run strictly after the previous one, in the given order."""
        chained: list[AgentTask] = []
        previous_id: str | None = None
        for task in tasks:
            depends_on = (previous_id,) if previous_id is not None else ()
            chained.append(task.model_copy(update={"depends_on": depends_on}))
            previous_id = task.task_id
        return cls(tasks=tuple(chained))

    @classmethod
    def parallel(cls, tasks: list[AgentTask]) -> ExecutionPlan:
        """Every task is independent — all run concurrently in a single wave."""
        return cls(tasks=tuple(task.model_copy(update={"depends_on": ()}) for task in tasks))

    @classmethod
    def mixed(cls, tasks: list[AgentTask]) -> ExecutionPlan:
        """`tasks` already carry their own `depends_on` — an explicit, self-documenting
        alias for `ExecutionPlan(tasks=tasks)`, for a general dependency graph."""
        return cls(tasks=tuple(tasks))


class ExecutionNode(BaseModel):
    """One node in an `ExecutionGraph` — a task's identity, dependencies,
    and (once executed) its status."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    agent_id: str
    depends_on: tuple[str, ...] = Field(default_factory=tuple)
    status: ExecutionStatus | None = None


class ExecutionGraph(BaseModel):
    """The structure of one `ExecutionPlan` — before execution (every
    `status` is `None`) or after (each node's final status)."""

    model_config = ConfigDict(extra="forbid")

    nodes: tuple[ExecutionNode, ...] = Field(default_factory=tuple)


class ExecutionSummary(BaseModel):
    """The outcome of `AgentOrchestrator.execute()`: every task's result, plus the final graph."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str
    started_at: datetime
    completed_at: datetime
    duration: float
    results: tuple[AgentExecutionResult, ...] = Field(default_factory=tuple)
    graph: ExecutionGraph
    success_count: int
    failed_count: int
    skipped_count: int
    overall_success: bool


class OrchestratorHealthStatus(BaseModel):
    """`AgentOrchestrator.health_check()`'s result. No agent is executed to produce this."""

    model_config = ConfigDict(extra="forbid")

    healthy_agents: tuple[str, ...] = Field(default_factory=tuple)
    unhealthy_agents: tuple[str, ...] = Field(default_factory=tuple)
    ready: bool
