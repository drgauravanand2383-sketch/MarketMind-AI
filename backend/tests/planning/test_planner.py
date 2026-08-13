"""Tests for PlanningEngine.plan(): template lookup, dependency validation,
circular dependency detection, execution plan generation, and sub-plan
expansion."""

from __future__ import annotations

import pytest

from app.orchestrator.models import ExecutionPlan
from app.planning.exceptions import InvalidPlanError, UnknownObjectiveError
from app.planning.models import PlanDependency, PlanningRequest, PlanStep, PlanTemplate
from app.planning.planner import PlanningEngine
from app.planning.registry import PlanRegistry


def _step(
    step_id: str,
    agent_id: str | None = None,
    sub_plan: str | None = None,
    depends_on: tuple[str, ...] = (),
    input_data: dict | None = None,
) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        agent_id=agent_id,
        sub_plan=sub_plan,
        input_data=input_data or {},
        depends_on=tuple(PlanDependency(step_id=d) for d in depends_on),
    )


def _registry_with(*templates: PlanTemplate) -> PlanRegistry:
    registry = PlanRegistry()
    for template in templates:
        registry.register(template)
    return registry


# --- Unknown objective -----------------------------------------------------------


def test_unknown_objective_raises() -> None:
    engine = PlanningEngine(PlanRegistry())
    with pytest.raises(UnknownObjectiveError):
        engine.plan(PlanningRequest(objective="does-not-exist"))


# --- Simple plan -----------------------------------------------------------


def test_simple_single_step_plan() -> None:
    registry = _registry_with(
        PlanTemplate(template_id="t1", objective="market overview", steps=(_step("fetch", "news-collector"),))
    )
    engine = PlanningEngine(registry)

    result = engine.plan(PlanningRequest(objective="market overview"))

    assert result.objective == "market overview"
    assert result.template_id == "t1"
    assert result.step_count == 1
    assert isinstance(result.execution_plan, ExecutionPlan)
    assert result.execution_plan.tasks[0].task_id == "fetch"
    assert result.execution_plan.tasks[0].agent_id == "news-collector"


def test_simple_plan_chains_dependencies_in_the_execution_plan() -> None:
    registry = _registry_with(
        PlanTemplate(
            template_id="t1",
            objective="company research",
            steps=(
                _step("fetch", "news-collector"),
                _step("analyze", "company-research", depends_on=("fetch",)),
            ),
        )
    )
    engine = PlanningEngine(registry)

    result = engine.plan(PlanningRequest(objective="company research"))

    by_id = {task.task_id: task for task in result.execution_plan.tasks}
    assert by_id["analyze"].depends_on == ("fetch",)


def test_request_parameters_are_merged_into_every_tasks_input() -> None:
    registry = _registry_with(
        PlanTemplate(
            template_id="t1",
            objective="portfolio analysis",
            steps=(_step("analyze", "portfolio-intelligence", input_data={"default_flag": True}),),
        )
    )
    engine = PlanningEngine(registry)

    result = engine.plan(
        PlanningRequest(objective="portfolio analysis", parameters={"holdings": ["AAA", "BBB"]})
    )

    payload = result.execution_plan.tasks[0].input_data
    assert payload.parameters == {"default_flag": True, "holdings": ["AAA", "BBB"]}


def test_request_parameters_override_step_defaults_on_key_collision() -> None:
    registry = _registry_with(
        PlanTemplate(
            template_id="t1",
            objective="market overview",
            steps=(_step("fetch", "news-collector", input_data={"limit": 10}),),
        )
    )
    engine = PlanningEngine(registry)

    result = engine.plan(PlanningRequest(objective="market overview", parameters={"limit": 50}))

    assert result.execution_plan.tasks[0].input_data.parameters == {"limit": 50}


# --- Dependency validation / circular dependency -----------------------------------------------------------


def test_dependency_cycle_across_a_diamond_still_validates_via_execution_plan() -> None:
    registry = _registry_with(
        PlanTemplate(
            template_id="t1",
            objective="obj",
            steps=(
                _step("a", "agent-a"),
                _step("b", "agent-b", depends_on=("a",)),
                _step("c", "agent-c", depends_on=("a",)),
                _step("d", "agent-d", depends_on=("b", "c")),
            ),
        )
    )
    engine = PlanningEngine(registry)

    result = engine.plan(PlanningRequest(objective="obj"))

    assert result.step_count == 4


def test_build_execution_plan_translates_missing_dependency_into_invalid_plan_error() -> None:
    """`PlanTemplate`'s own validator (see test_models.py) already rejects a
    dangling dependency within one template's own steps, and sub-plan
    expansion's substitution never produces a dangling reference by
    construction (see the app.planning.models module docstring) -- so this
    exercises `_build_execution_plan`'s translation of the orchestrator's
    `InvalidExecutionPlanError` directly, with a hand-built step list that
    bypasses those guarantees, proving planning callers only ever see
    `InvalidPlanError`, never an orchestrator-layer exception."""
    engine = PlanningEngine(PlanRegistry())
    steps = [_step("a", "agent-a", depends_on=("does-not-exist",))]

    with pytest.raises(InvalidPlanError):
        engine._build_execution_plan(steps, {})


def test_build_execution_plan_translates_duplicate_step_id_into_invalid_plan_error() -> None:
    engine = PlanningEngine(PlanRegistry())
    steps = [_step("a", "agent-a"), _step("a", "agent-b")]

    with pytest.raises(InvalidPlanError):
        engine._build_execution_plan(steps, {})


# --- Sub-plan expansion -----------------------------------------------------------


def test_sub_plan_steps_are_namespaced_and_inlined() -> None:
    registry = _registry_with(
        PlanTemplate(
            template_id="sub",
            objective="deep research",
            steps=(
                _step("fetch", "news-collector"),
                _step("analyze", "company-research", depends_on=("fetch",)),
            ),
        ),
        PlanTemplate(
            template_id="outer",
            objective="morning brief",
            steps=(
                _step("research", sub_plan="deep research"),
                _step("summarize", "morning-brief-generator", depends_on=("research",)),
            ),
        ),
    )
    engine = PlanningEngine(registry)

    result = engine.plan(PlanningRequest(objective="morning brief"))

    by_id = {task.task_id: task for task in result.execution_plan.tasks}
    assert set(by_id) == {"research::fetch", "research::analyze", "summarize"}
    assert by_id["research::analyze"].depends_on == ("research::fetch",)
    assert by_id["summarize"].depends_on == ("research::analyze",)


def test_step_depending_on_sub_plan_waits_for_all_its_exit_steps() -> None:
    """A sub-plan with two independent (parallel) internal steps has two
    exit points; a step depending on the sub-plan must depend on both."""
    registry = _registry_with(
        PlanTemplate(
            template_id="sub",
            objective="dual research",
            steps=(_step("a", "agent-a"), _step("b", "agent-b")),
        ),
        PlanTemplate(
            template_id="outer",
            objective="combined brief",
            steps=(
                _step("research", sub_plan="dual research"),
                _step("summarize", "summarizer", depends_on=("research",)),
            ),
        ),
    )
    engine = PlanningEngine(registry)

    result = engine.plan(PlanningRequest(objective="combined brief"))

    by_id = {task.task_id: task for task in result.execution_plan.tasks}
    assert set(by_id["summarize"].depends_on) == {"research::a", "research::b"}


def test_sub_plan_entry_points_inherit_the_outer_steps_own_dependencies() -> None:
    registry = _registry_with(
        PlanTemplate(
            template_id="sub",
            objective="sub-obj",
            steps=(_step("s1", "agent-a"), _step("s2", "agent-b", depends_on=("s1",))),
        ),
        PlanTemplate(
            template_id="outer",
            objective="outer-obj",
            steps=(
                _step("pre", "agent-p"),
                _step("mid", sub_plan="sub-obj", depends_on=("pre",)),
                _step("post", "agent-q", depends_on=("mid",)),
            ),
        ),
    )
    engine = PlanningEngine(registry)

    result = engine.plan(PlanningRequest(objective="outer-obj"))

    by_id = {task.task_id: task for task in result.execution_plan.tasks}
    assert by_id["mid::s1"].depends_on == ("pre",)
    assert by_id["mid::s2"].depends_on == ("mid::s1",)
    assert by_id["post"].depends_on == ("mid::s2",)


def test_circular_sub_plan_reference_is_rejected() -> None:
    registry = _registry_with(
        PlanTemplate(template_id="a", objective="a-obj", steps=(_step("s", sub_plan="b-obj"),)),
        PlanTemplate(template_id="b", objective="b-obj", steps=(_step("s", sub_plan="a-obj"),)),
    )
    engine = PlanningEngine(registry)

    with pytest.raises(InvalidPlanError):
        engine.plan(PlanningRequest(objective="a-obj"))


def test_sub_plan_referencing_unknown_objective_raises_unknown_objective() -> None:
    registry = _registry_with(
        PlanTemplate(template_id="x", objective="x-obj", steps=(_step("s", sub_plan="missing-obj"),))
    )
    engine = PlanningEngine(registry)

    with pytest.raises(UnknownObjectiveError):
        engine.plan(PlanningRequest(objective="x-obj"))


def test_same_sub_plan_reused_by_two_sibling_steps_is_not_a_false_cycle() -> None:
    registry = _registry_with(
        PlanTemplate(template_id="sub", objective="shared-sub", steps=(_step("s1", "agent-a"),)),
        PlanTemplate(
            template_id="outer",
            objective="outer-obj",
            steps=(
                _step("left", sub_plan="shared-sub"),
                _step("right", sub_plan="shared-sub"),
            ),
        ),
    )
    engine = PlanningEngine(registry)

    result = engine.plan(PlanningRequest(objective="outer-obj"))

    assert result.step_count == 2
    assert {task.task_id for task in result.execution_plan.tasks} == {"left::s1", "right::s1"}
