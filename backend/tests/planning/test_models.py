"""Tests for the Planning Engine's typed models (app.planning.models)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.planning.models import PlanDependency, PlanStep, PlanTemplate


def _step(step_id: str, agent_id: str = "agent-a", depends_on: tuple[str, ...] = ()) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        agent_id=agent_id,
        depends_on=tuple(PlanDependency(step_id=d) for d in depends_on),
    )


# --- PlanStep -----------------------------------------------------------


def test_plan_step_requires_non_empty_step_id() -> None:
    with pytest.raises(ValidationError):
        PlanStep(step_id="", agent_id="a")


def test_plan_step_is_frozen() -> None:
    step = _step("s1")
    with pytest.raises(ValidationError):
        step.step_id = "changed"


def test_plan_step_rejects_both_agent_id_and_sub_plan() -> None:
    with pytest.raises(ValidationError):
        PlanStep(step_id="s1", agent_id="a", sub_plan="other-objective")


def test_plan_step_rejects_neither_agent_id_nor_sub_plan() -> None:
    with pytest.raises(ValidationError):
        PlanStep(step_id="s1")


def test_plan_step_accepts_sub_plan_alone() -> None:
    step = PlanStep(step_id="s1", sub_plan="other-objective")
    assert step.sub_plan == "other-objective"
    assert step.agent_id is None


def test_plan_step_rejects_reserved_namespacing_sequence_in_step_id() -> None:
    with pytest.raises(ValidationError):
        PlanStep(step_id="a::b", agent_id="a")


# --- PlanTemplate local validation -----------------------------------------------------------


def test_plan_template_accepts_a_valid_step_list() -> None:
    template = PlanTemplate(
        template_id="t1",
        objective="company research",
        steps=(_step("fetch"), _step("analyze", depends_on=("fetch",))),
    )
    assert len(template.steps) == 2


def test_plan_template_rejects_duplicate_step_id() -> None:
    with pytest.raises(ValidationError):
        PlanTemplate(template_id="t1", objective="obj", steps=(_step("a"), _step("a")))


def test_plan_template_rejects_dependency_on_unknown_step_id() -> None:
    with pytest.raises(ValidationError):
        PlanTemplate(
            template_id="t1", objective="obj", steps=(_step("a", depends_on=("does-not-exist",)),)
        )


def test_plan_template_rejects_self_dependency() -> None:
    with pytest.raises(ValidationError):
        PlanTemplate(template_id="t1", objective="obj", steps=(_step("a", depends_on=("a",)),))


def test_plan_template_rejects_two_step_cycle() -> None:
    with pytest.raises(ValidationError):
        PlanTemplate(
            template_id="t1",
            objective="obj",
            steps=(_step("a", depends_on=("b",)), _step("b", depends_on=("a",))),
        )


def test_plan_template_accepts_empty_steps() -> None:
    template = PlanTemplate(template_id="t1", objective="obj", steps=())
    assert template.steps == ()
