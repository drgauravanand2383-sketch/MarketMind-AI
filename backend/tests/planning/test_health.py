"""Tests for PlanningEngine.health_check()."""

from __future__ import annotations

from app.planning.models import PlanningHealthStatus, PlanStep, PlanTemplate
from app.planning.planner import PlanningEngine
from app.planning.registry import PlanRegistry


def _step(step_id: str, agent_id: str | None = None, sub_plan: str | None = None) -> PlanStep:
    return PlanStep(step_id=step_id, agent_id=agent_id, sub_plan=sub_plan)


def test_health_check_with_no_registered_templates() -> None:
    engine = PlanningEngine(PlanRegistry())

    status = engine.health_check()

    assert status == PlanningHealthStatus(
        registered_objectives=(), valid_templates=(), invalid_templates=(), ready=True
    )


def test_health_check_reports_registered_objectives() -> None:
    registry = PlanRegistry()
    registry.register(PlanTemplate(template_id="t1", objective="company research", steps=(_step("a", "agent"),)))
    registry.register(PlanTemplate(template_id="t2", objective="morning brief", steps=(_step("b", "agent"),)))
    engine = PlanningEngine(registry)

    status = engine.health_check()

    assert status.registered_objectives == ("company research", "morning brief")
    assert status.valid_templates == ("company research", "morning brief")
    assert status.invalid_templates == ()
    assert status.ready is True


def test_health_check_flags_a_template_with_a_dangling_sub_plan_reference() -> None:
    registry = PlanRegistry()
    registry.register(
        PlanTemplate(template_id="t1", objective="broken", steps=(_step("a", sub_plan="missing-objective"),))
    )
    engine = PlanningEngine(registry)

    status = engine.health_check()

    assert status.invalid_templates == ("broken",)
    assert status.valid_templates == ()
    assert status.ready is False


def test_health_check_partitions_valid_and_invalid_templates_independently() -> None:
    registry = PlanRegistry()
    registry.register(PlanTemplate(template_id="ok", objective="good", steps=(_step("a", "agent"),)))
    registry.register(
        PlanTemplate(template_id="bad", objective="broken", steps=(_step("a", sub_plan="missing"),))
    )
    engine = PlanningEngine(registry)

    status = engine.health_check()

    assert status.valid_templates == ("good",)
    assert status.invalid_templates == ("broken",)
    assert status.ready is False
