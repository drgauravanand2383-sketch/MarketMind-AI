"""Tests for AgentOrchestrator's execution: single/parallel/sequential/mixed
plans, dependency ordering, failure isolation, and execution metadata."""

from __future__ import annotations

import time

import pytest

from app.orchestrator.exceptions import OrchestratorError
from app.orchestrator.models import AgentTask, ExecutionPlan, ExecutionStatus
from app.orchestrator.orchestrator import AgentOrchestrator
from tests.orchestrator.conftest import FakeAgent, TaskInput


def _task(task_id: str, agent_id: str, value: int = 1, depends_on: tuple[str, ...] = ()) -> AgentTask:
    return AgentTask(
        task_id=task_id, agent_id=agent_id, input_data=TaskInput(value=value), depends_on=depends_on
    )


# --- Single execution -----------------------------------------------------------


async def test_execute_one_returns_a_successful_result() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a", multiplier=3))

    result = await orchestrator.execute_one("a", TaskInput(value=4))

    assert result.status == ExecutionStatus.SUCCESS
    assert result.output.result == 12
    assert result.agent_id == "a"


async def test_execute_with_a_single_task_plan() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a", multiplier=2))
    plan = ExecutionPlan(tasks=(_task("t1", "a", value=5),))

    summary = await orchestrator.execute(plan)

    assert summary.success_count == 1
    assert summary.results[0].output.result == 10


# --- Parallel execution -----------------------------------------------------------


async def test_parallel_execution_runs_tasks_concurrently() -> None:
    orchestrator = AgentOrchestrator()
    for i in range(3):
        orchestrator.register_agent(f"agent-{i}", FakeAgent(agent_id=f"agent-{i}", delay=0.1))
    plan = ExecutionPlan.parallel([_task(f"t{i}", f"agent-{i}") for i in range(3)])

    start = time.monotonic()
    summary = await orchestrator.execute(plan)
    elapsed = time.monotonic() - start

    assert summary.success_count == 3
    assert elapsed < 0.25  # well under 3 * 0.1s if these ran sequentially


async def test_parallel_execution_all_tasks_have_no_dependencies() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a"))
    orchestrator.register_agent("b", FakeAgent(agent_id="b"))
    plan = ExecutionPlan.parallel([_task("t1", "a"), _task("t2", "b")])

    summary = await orchestrator.execute(plan)

    assert all(result.dependencies == () for result in summary.results)
    assert summary.success_count == 2


# --- Sequential execution -----------------------------------------------------------


async def test_sequential_execution_runs_in_order() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a"))
    orchestrator.register_agent("b", FakeAgent(agent_id="b"))
    orchestrator.register_agent("c", FakeAgent(agent_id="c"))
    plan = ExecutionPlan.sequential([_task("t1", "a"), _task("t2", "b"), _task("t3", "c")])

    summary = await orchestrator.execute(plan)

    by_id = {result.task_id: result for result in summary.results}
    assert by_id["t1"].finish_time <= by_id["t2"].start_time
    assert by_id["t2"].finish_time <= by_id["t3"].start_time
    assert summary.success_count == 3


async def test_sequential_execution_chains_dependencies() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a"))
    orchestrator.register_agent("b", FakeAgent(agent_id="b"))
    plan = ExecutionPlan.sequential([_task("t1", "a"), _task("t2", "b")])

    summary = await orchestrator.execute(plan)

    by_id = {result.task_id: result for result in summary.results}
    assert by_id["t2"].dependencies == ("t1",)


# --- Mixed execution -----------------------------------------------------------


async def test_mixed_execution_diamond_dependency() -> None:
    """a -> (b, c) -> d: b and c run only after a; d only after both b and c."""
    orchestrator = AgentOrchestrator()
    for agent_id in ("a", "b", "c", "d"):
        orchestrator.register_agent(agent_id, FakeAgent(agent_id=agent_id))
    plan = ExecutionPlan.mixed(
        [
            _task("a", "a"),
            _task("b", "b", depends_on=("a",)),
            _task("c", "c", depends_on=("a",)),
            _task("d", "d", depends_on=("b", "c")),
        ]
    )

    summary = await orchestrator.execute(plan)

    by_id = {result.task_id: result for result in summary.results}
    assert summary.success_count == 4
    assert by_id["a"].finish_time <= by_id["b"].start_time
    assert by_id["a"].finish_time <= by_id["c"].start_time
    assert by_id["b"].finish_time <= by_id["d"].start_time
    assert by_id["c"].finish_time <= by_id["d"].start_time


async def test_mixed_execution_independent_branch_alongside_dependent_chain() -> None:
    orchestrator = AgentOrchestrator()
    for agent_id in ("a", "b", "independent"):
        orchestrator.register_agent(agent_id, FakeAgent(agent_id=agent_id))
    plan = ExecutionPlan.mixed(
        [
            _task("a", "a"),
            _task("b", "b", depends_on=("a",)),
            _task("solo", "independent"),
        ]
    )

    summary = await orchestrator.execute(plan)

    assert summary.success_count == 3


# --- Dependency ordering -----------------------------------------------------------


async def test_dependency_ordering_is_respected_for_a_wide_fan_in() -> None:
    orchestrator = AgentOrchestrator()
    for agent_id in ("a", "b", "c", "sink"):
        orchestrator.register_agent(agent_id, FakeAgent(agent_id=agent_id))
    plan = ExecutionPlan.mixed(
        [
            _task("a", "a"),
            _task("b", "b"),
            _task("c", "c"),
            _task("sink", "sink", depends_on=("a", "b", "c")),
        ]
    )

    summary = await orchestrator.execute(plan)

    by_id = {result.task_id: result for result in summary.results}
    for upstream in ("a", "b", "c"):
        assert by_id[upstream].finish_time <= by_id["sink"].start_time


# --- Failure isolation -----------------------------------------------------------


async def test_one_failed_task_does_not_crash_the_orchestrator() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("bad", FakeAgent(agent_id="bad", error=RuntimeError("boom")))
    plan = ExecutionPlan(tasks=(_task("t1", "bad"),))

    summary = await orchestrator.execute(plan)  # must not raise

    assert summary.results[0].status == ExecutionStatus.FAILED
    assert summary.results[0].error == "boom"
    assert summary.overall_success is False


async def test_failed_task_does_not_stop_an_independent_branch() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("bad", FakeAgent(agent_id="bad", error=RuntimeError("boom")))
    orchestrator.register_agent("good", FakeAgent(agent_id="good"))
    plan = ExecutionPlan.parallel([_task("bad_task", "bad"), _task("good_task", "good")])

    summary = await orchestrator.execute(plan)

    by_id = {result.task_id: result for result in summary.results}
    assert by_id["bad_task"].status == ExecutionStatus.FAILED
    assert by_id["good_task"].status == ExecutionStatus.SUCCESS


async def test_a_task_depending_on_a_failed_task_is_skipped() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("bad", FakeAgent(agent_id="bad", error=RuntimeError("boom")))
    orchestrator.register_agent("dependent", FakeAgent(agent_id="dependent"))
    plan = ExecutionPlan.mixed(
        [_task("bad_task", "bad"), _task("dependent_task", "dependent", depends_on=("bad_task",))]
    )

    summary = await orchestrator.execute(plan)

    by_id = {result.task_id: result for result in summary.results}
    assert by_id["dependent_task"].status == ExecutionStatus.SKIPPED
    assert summary.skipped_count == 1
    assert summary.failed_count == 1


async def test_skipped_task_never_actually_calls_its_agent() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("bad", FakeAgent(agent_id="bad", error=RuntimeError("boom")))
    dependent_agent = FakeAgent(agent_id="dependent")
    orchestrator.register_agent("dependent", dependent_agent)
    plan = ExecutionPlan.mixed(
        [_task("bad_task", "bad"), _task("dependent_task", "dependent", depends_on=("bad_task",))]
    )

    await orchestrator.execute(plan)

    assert dependent_agent.calls == []


async def test_task_referencing_an_unregistered_agent_is_a_failed_task_not_a_crash() -> None:
    orchestrator = AgentOrchestrator()
    plan = ExecutionPlan(tasks=(_task("t1", "never-registered"),))

    summary = await orchestrator.execute(plan)  # must not raise

    assert summary.results[0].status == ExecutionStatus.FAILED


async def test_multiple_independent_failures_are_each_isolated() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("bad1", FakeAgent(agent_id="bad1", error=ValueError("one")))
    orchestrator.register_agent("bad2", FakeAgent(agent_id="bad2", error=ValueError("two")))
    orchestrator.register_agent("good", FakeAgent(agent_id="good"))
    plan = ExecutionPlan.parallel(
        [_task("t1", "bad1"), _task("t2", "bad2"), _task("t3", "good")]
    )

    summary = await orchestrator.execute(plan)

    assert summary.failed_count == 2
    assert summary.success_count == 1


# --- Metadata -----------------------------------------------------------


async def test_execution_summary_metadata_is_consistent() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a"))
    plan = ExecutionPlan(tasks=(_task("t1", "a"),))

    summary = await orchestrator.execute(plan)

    assert summary.execution_id
    assert summary.started_at <= summary.completed_at
    assert summary.duration >= 0.0
    assert len(summary.results) == 1


async def test_every_result_shares_the_same_execution_id() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a"))
    orchestrator.register_agent("b", FakeAgent(agent_id="b"))
    plan = ExecutionPlan.parallel([_task("t1", "a"), _task("t2", "b")])

    summary = await orchestrator.execute(plan)

    execution_ids = {result.execution_id for result in summary.results}
    assert execution_ids == {summary.execution_id}


async def test_result_captures_agent_id_status_and_timing() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a"))
    plan = ExecutionPlan(tasks=(_task("t1", "a"),))

    summary = await orchestrator.execute(plan)
    result = summary.results[0]

    assert result.agent_id == "a"
    assert result.status == ExecutionStatus.SUCCESS
    assert result.start_time <= result.finish_time
    assert result.duration >= 0.0
    assert result.dependencies == ()


async def test_result_captures_the_exception_message_on_failure() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("bad", FakeAgent(agent_id="bad", error=RuntimeError("specific message")))
    plan = ExecutionPlan(tasks=(_task("t1", "bad"),))

    summary = await orchestrator.execute(plan)

    assert summary.results[0].error == "specific message"


async def test_execution_graph_reflects_final_statuses() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a"))
    orchestrator.register_agent("bad", FakeAgent(agent_id="bad", error=RuntimeError("boom")))
    plan = ExecutionPlan.parallel([_task("t1", "a"), _task("t2", "bad")])

    summary = await orchestrator.execute(plan)

    statuses = {node.task_id: node.status for node in summary.graph.nodes}
    assert statuses["t1"] == ExecutionStatus.SUCCESS
    assert statuses["t2"] == ExecutionStatus.FAILED


def test_build_graph_before_execution_has_no_statuses() -> None:
    orchestrator = AgentOrchestrator()
    plan = ExecutionPlan.sequential([_task("t1", "a"), _task("t2", "b")])

    graph = orchestrator.build_graph(plan)

    assert all(node.status is None for node in graph.nodes)
    assert graph.nodes[1].depends_on == ("t1",)
