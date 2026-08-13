"""Proves `PlanningEngine.plan()` returns an `ExecutionPlan` the real,
unmodified `AgentOrchestrator` can execute -- not just a structurally
similar lookalike. Only agent execution is faked (`FakeAgent`); the
orchestrator and the planning engine are both the genuine production
classes."""

from __future__ import annotations

from app.orchestrator.models import ExecutionStatus
from app.orchestrator.orchestrator import AgentOrchestrator
from app.planning.models import PlanDependency, PlanningRequest, PlanStep, PlanTemplate
from app.planning.planner import PlanningEngine
from app.planning.registry import PlanRegistry
from tests.planning.conftest import FakeAgent


def _step(step_id: str, agent_id: str, depends_on: tuple[str, ...] = ()) -> PlanStep:
    return PlanStep(
        step_id=step_id, agent_id=agent_id, depends_on=tuple(PlanDependency(step_id=d) for d in depends_on)
    )


async def test_a_planned_execution_plan_runs_successfully_on_the_real_orchestrator() -> None:
    registry = PlanRegistry()
    registry.register(
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
    result = engine.plan(PlanningRequest(objective="company research", parameters={"company": "Acme"}))

    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("news-collector", FakeAgent(agent_id="news-collector"))
    orchestrator.register_agent("company-research", FakeAgent(agent_id="company-research"))

    summary = await orchestrator.execute(result.execution_plan)

    assert summary.overall_success is True
    assert summary.success_count == 2
    by_id = {r.task_id: r for r in summary.results}
    assert by_id["fetch"].status == ExecutionStatus.SUCCESS
    assert by_id["analyze"].status == ExecutionStatus.SUCCESS


async def test_a_planned_execution_plan_with_an_unregistered_agent_fails_in_isolation() -> None:
    """The orchestrator, not the planner, is responsible for what happens
    when a planned agent_id was never registered -- the plan itself is
    still structurally valid and executes without crashing."""
    registry = PlanRegistry()
    registry.register(
        PlanTemplate(template_id="t1", objective="market overview", steps=(_step("fetch", "unregistered-agent"),))
    )
    engine = PlanningEngine(registry)
    result = engine.plan(PlanningRequest(objective="market overview"))

    orchestrator = AgentOrchestrator()

    summary = await orchestrator.execute(result.execution_plan)  # must not raise

    assert summary.results[0].status == ExecutionStatus.FAILED


async def test_expanded_sub_plan_executes_in_correct_dependency_order() -> None:
    registry = PlanRegistry()
    registry.register(
        PlanTemplate(
            template_id="sub",
            objective="deep research",
            steps=(
                _step("fetch", "news-collector"),
                _step("analyze", "company-research", depends_on=("fetch",)),
            ),
        )
    )
    registry.register(
        PlanTemplate(
            template_id="outer",
            objective="morning brief",
            steps=(
                PlanStep(step_id="research", sub_plan="deep research"),
                _step("summarize", "morning-brief-generator", depends_on=("research",)),
            ),
        )
    )
    engine = PlanningEngine(registry)
    result = engine.plan(PlanningRequest(objective="morning brief"))

    fetch_agent = FakeAgent(agent_id="news-collector")
    analyze_agent = FakeAgent(agent_id="company-research")
    summarize_agent = FakeAgent(agent_id="morning-brief-generator")
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("news-collector", fetch_agent)
    orchestrator.register_agent("company-research", analyze_agent)
    orchestrator.register_agent("morning-brief-generator", summarize_agent)

    summary = await orchestrator.execute(result.execution_plan)

    assert summary.overall_success is True
    by_id = {r.task_id: r for r in summary.results}
    assert by_id["research::fetch"].finish_time <= by_id["research::analyze"].start_time
    assert by_id["research::analyze"].finish_time <= by_id["summarize"].start_time
