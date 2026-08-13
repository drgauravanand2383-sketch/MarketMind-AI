"""Tests for the Multi-Agent Orchestrator's typed models (app.orchestrator.models)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.orchestrator.exceptions import InvalidExecutionPlanError
from app.orchestrator.models import AgentTask, ExecutionPlan
from tests.orchestrator.conftest import TaskInput


def _task(task_id: str, agent_id: str = "agent-a", depends_on: tuple[str, ...] = ()) -> AgentTask:
    return AgentTask(task_id=task_id, agent_id=agent_id, input_data=TaskInput(), depends_on=depends_on)


# --- AgentTask -----------------------------------------------------------


def test_agent_task_requires_non_empty_task_id() -> None:
    with pytest.raises(PydanticValidationError):
        AgentTask(task_id="", agent_id="a", input_data=TaskInput())


def test_agent_task_is_frozen() -> None:
    task = _task("t1")
    with pytest.raises(PydanticValidationError):
        task.task_id = "changed"


def test_agent_task_defaults_to_no_dependencies() -> None:
    task = _task("t1")
    assert task.depends_on == ()


# --- ExecutionPlan construction -----------------------------------------------------------


def test_sequential_chains_each_task_to_the_previous() -> None:
    plan = ExecutionPlan.sequential([_task("a"), _task("b"), _task("c")])
    assert [t.depends_on for t in plan.tasks] == [(), ("a",), ("b",)]


def test_parallel_leaves_every_task_independent() -> None:
    plan = ExecutionPlan.parallel([_task("a", depends_on=()), _task("b"), _task("c")])
    assert all(t.depends_on == () for t in plan.tasks)


def test_mixed_preserves_each_tasks_own_dependencies() -> None:
    plan = ExecutionPlan.mixed([_task("a"), _task("b", depends_on=("a",)), _task("c", depends_on=("a",))])
    assert plan.tasks[1].depends_on == ("a",)
    assert plan.tasks[2].depends_on == ("a",)


def test_empty_plan_is_valid() -> None:
    plan = ExecutionPlan(tasks=())
    assert plan.tasks == ()


# --- ExecutionPlan validation -----------------------------------------------------------


def test_duplicate_task_id_is_rejected() -> None:
    with pytest.raises(InvalidExecutionPlanError):
        ExecutionPlan(tasks=(_task("a"), _task("a")))


def test_unknown_dependency_is_rejected() -> None:
    with pytest.raises(InvalidExecutionPlanError):
        ExecutionPlan(tasks=(_task("a", depends_on=("does-not-exist",)),))


def test_self_dependency_is_rejected() -> None:
    with pytest.raises(InvalidExecutionPlanError):
        ExecutionPlan(tasks=(_task("a", depends_on=("a",)),))


def test_two_node_cycle_is_rejected() -> None:
    with pytest.raises(InvalidExecutionPlanError):
        ExecutionPlan(
            tasks=(_task("a", depends_on=("b",)), _task("b", depends_on=("a",)))
        )


def test_three_node_cycle_is_rejected() -> None:
    with pytest.raises(InvalidExecutionPlanError):
        ExecutionPlan(
            tasks=(
                _task("a", depends_on=("c",)),
                _task("b", depends_on=("a",)),
                _task("c", depends_on=("b",)),
            )
        )


def test_valid_diamond_dependency_graph_is_accepted() -> None:
    plan = ExecutionPlan(
        tasks=(
            _task("a"),
            _task("b", depends_on=("a",)),
            _task("c", depends_on=("a",)),
            _task("d", depends_on=("b", "c")),
        )
    )
    assert len(plan.tasks) == 4
