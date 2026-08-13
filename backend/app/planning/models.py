"""Typed models for the Agent Planning Engine.

The Planning Engine turns a `PlanningRequest` (an objective string plus
parameters) into an `app.orchestrator.models.ExecutionPlan` the existing
Multi-Agent Orchestrator can execute unmodified. It does this by looking up
a registered `PlanTemplate` for that objective and expanding it into
`AgentTask`s — deterministically, via exact objective matching only. No
semantic interpretation and no LLM are involved anywhere in this package.

Design note — generic step input: a `PlanStep.input_data` is a plain
`dict[str, Any]`, not a specific agent's request model. The Planning Engine
does not import (and per the sprint's own constraints, must not couple
itself to) any concrete agent's schema — that would make planning
agent-aware, contradicting "planning only, no reasoning." At plan-build
time each step's resolved parameters are wrapped in `StepInputPayload`, a
single generic `BaseModel` container, to satisfy `AgentTask.input_data:
BaseModel`. Translating a `StepInputPayload` into a concrete agent's own
request model is integration work for whoever wires a `PlanTemplate`'s
`agent_id`s to real registered agents (bootstrap-level, out of scope here)
— see the Sprint 43 completion report for this flagged as a known gap.

Design note — sub-plan expansion: a `PlanStep` may reference another
template via `sub_plan` (its objective) instead of `agent_id`. Expanding it
inlines that template's own steps, namespaced as `f"{step_id}::{sub_step_id}"`
to avoid collisions. A sub-plan's own entry points (its steps with no
explicit `depends_on`) additionally depend on whatever the *outer* step
itself depended on, so the sub-plan never starts before its own
prerequisites. Symmetrically, any other step in the outer template that
depends on the sub-plan step is rewired to depend on the sub-plan's own
exit points (its steps nothing inside the sub-plan depends on) — so
"depend on this sub-plan" means "wait for the whole sub-plan to finish."
This resolution happens via one local topological pass per template (see
`app.planning.planner._local_topological_order`), so a sub-plan step that
itself depends on another sub-plan step in the same template resolves
correctly regardless of declaration order.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.orchestrator.models import ExecutionPlan

__all__ = [
    "PlanDependency",
    "PlanStep",
    "PlanTemplate",
    "PlanningRequest",
    "PlanningResult",
    "StepInputPayload",
    "PlanningHealthStatus",
]


class PlanDependency(BaseModel):
    """A single dependency edge: the referencing step must run after `step_id`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(min_length=1)


class PlanStep(BaseModel):
    """One unit of work within a `PlanTemplate`.

    Exactly one of `agent_id` (run this agent) or `sub_plan` (inline another
    template's objective here) must be set.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(min_length=1)
    agent_id: str | None = None
    sub_plan: str | None = None
    input_data: dict[str, Any] = Field(default_factory=dict)
    depends_on: tuple[PlanDependency, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_step(self) -> PlanStep:
        if "::" in self.step_id:
            raise ValueError(
                f"step_id {self.step_id!r} may not contain '::' — that sequence is "
                "reserved for sub-plan expansion namespacing."
            )
        if (self.agent_id is None) == (self.sub_plan is None):
            raise ValueError(
                f"Step {self.step_id!r} must set exactly one of agent_id or sub_plan."
            )
        return self


def _validate_local_steps(objective: str, steps: tuple[PlanStep, ...]) -> None:
    """Validate one template's own steps in isolation: no duplicate step id,
    no dependency on a step id outside this same template, no cycle.

    This does not know about sub-plan expansion — a step referencing a
    `sub_plan` is just another node here. Cross-template concerns (unknown
    objective, circular sub-plan reference, dependencies left dangling by
    expansion) are only checked at planning time, once the registry is
    available — see `app.planning.planner.PlanningEngine`.
    """
    seen: set[str] = set()
    for step in steps:
        if step.step_id in seen:
            raise ValueError(
                f"Duplicate step_id {step.step_id!r} in plan template for objective {objective!r}."
            )
        seen.add(step.step_id)

    graph: dict[str, tuple[str, ...]] = {
        step.step_id: tuple(dep.step_id for dep in step.depends_on) for step in steps
    }
    for step_id, deps in graph.items():
        for dep in deps:
            if dep == step_id:
                raise ValueError(
                    f"Step {step_id!r} cannot depend on itself in template for objective {objective!r}."
                )
            if dep not in graph:
                raise ValueError(
                    f"Step {step_id!r} depends on unknown step_id {dep!r} "
                    f"in template for objective {objective!r}."
                )

    _WHITE, _GRAY, _BLACK = 0, 1, 2
    color: dict[str, int] = {step_id: _WHITE for step_id in graph}

    def _visit(step_id: str) -> None:
        color[step_id] = _GRAY
        for dep in graph[step_id]:
            if color[dep] == _GRAY:
                raise ValueError(
                    f"Dependency cycle detected involving step_id {step_id!r} "
                    f"in template for objective {objective!r}."
                )
            if color[dep] == _WHITE:
                _visit(dep)
        color[step_id] = _BLACK

    for step_id in graph:
        if color[step_id] == _WHITE:
            _visit(step_id)


class PlanTemplate(BaseModel):
    """A reusable, named plan for one objective: exact-matched, never inferred."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    description: str = ""
    steps: tuple[PlanStep, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_template(self) -> PlanTemplate:
        _validate_local_steps(self.objective, self.steps)
        return self


class PlanningRequest(BaseModel):
    """A caller's request to plan for one objective, with optional runtime parameters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class StepInputPayload(BaseModel):
    """The generic `AgentTask.input_data` payload the Planning Engine builds
    for every task: a step's template-defined `input_data`, overridden by
    the requester's own `parameters`. See the module docstring."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    parameters: dict[str, Any] = Field(default_factory=dict)


class PlanningResult(BaseModel):
    """The outcome of `PlanningEngine.plan()`: the resolved template identity
    plus a ready-to-execute `ExecutionPlan`."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    objective: str
    template_id: str
    step_count: int
    execution_plan: ExecutionPlan


class PlanningHealthStatus(BaseModel):
    """`PlanningEngine.health_check()`'s result. No plan is executed to produce this.

    `ready` mirrors `OrchestratorHealthStatus.ready` — true only when every
    registered template is currently structurally valid.
    """

    model_config = ConfigDict(extra="forbid")

    registered_objectives: tuple[str, ...] = Field(default_factory=tuple)
    valid_templates: tuple[str, ...] = Field(default_factory=tuple)
    invalid_templates: tuple[str, ...] = Field(default_factory=tuple)
    ready: bool
