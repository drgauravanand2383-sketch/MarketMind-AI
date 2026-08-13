"""PlanningEngine: converts a `PlanningRequest` into a `PlanningResult`
carrying an `app.orchestrator.models.ExecutionPlan`.

Planning only. No agent is executed here, no AI reasoning is performed, and
objective matching is exact-string-only — see the `app.planning.models`
module docstring for the sub-plan expansion and generic-payload design
notes this engine relies on.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.orchestrator.exceptions import InvalidExecutionPlanError
from app.orchestrator.models import AgentTask, ExecutionPlan
from app.planning.exceptions import InvalidPlanError, PlanningError
from app.planning.models import (
    PlanDependency,
    PlanningHealthStatus,
    PlanningRequest,
    PlanningResult,
    PlanStep,
    PlanTemplate,
    StepInputPayload,
)
from app.planning.registry import PlanRegistry

__all__ = ["PlanningEngine"]


def _local_topological_order(steps: tuple[PlanStep, ...]) -> list[PlanStep]:
    """Order `steps` so every step comes after everything it depends on.

    `steps` is one template's own step list — already guaranteed acyclic and
    internally resolvable by `PlanTemplate`'s own validator at construction
    time, so this never needs to detect a cycle itself; it exists purely to
    give `PlanningEngine._expand` a safe processing order in which every
    dependency has already been resolved (and, if it is a sub-plan step,
    already expanded) by the time a step that references it is processed.
    """
    by_id = {step.step_id: step for step in steps}
    indegree = {step.step_id: len(step.depends_on) for step in steps}
    dependents: dict[str, list[str]] = {step.step_id: [] for step in steps}
    for step in steps:
        for dep in step.depends_on:
            dependents[dep.step_id].append(step.step_id)

    queue = [step_id for step_id, degree in indegree.items() if degree == 0]
    ordered: list[PlanStep] = []
    while queue:
        current = queue.pop(0)
        ordered.append(by_id[current])
        for next_id in dependents[current]:
            indegree[next_id] -= 1
            if indegree[next_id] == 0:
                queue.append(next_id)
    return ordered


class PlanningEngine:
    """Deterministic, rule-based plan construction. Depends only on an
    injected `PlanRegistry` — no globals, no singleton."""

    def __init__(self, registry: PlanRegistry) -> None:
        self._registry = registry

    def plan(self, request: PlanningRequest) -> PlanningResult:
        """Look up the template for `request.objective`, expand it (inlining
        any sub-plans), and return a `PlanningResult` wrapping a validated
        `ExecutionPlan`.

        Raises:
            UnknownObjectiveError: no template is registered for
                `request.objective`, or for any objective referenced via a
                step's `sub_plan`.
            InvalidPlanError: the expanded plan has a duplicate step id, a
                dependency on a missing step, or a dependency cycle
                (including a circular chain of sub-plan references).
        """
        template = self._registry.get(request.objective)
        expanded_steps, _exit_ids = self._expand(
            request.objective, inherited_depends_on=(), prefix="", visiting=frozenset()
        )
        execution_plan = self._build_execution_plan(expanded_steps, request.parameters)
        return PlanningResult(
            objective=request.objective,
            template_id=template.template_id,
            step_count=len(expanded_steps),
            execution_plan=execution_plan,
        )

    def health_check(self) -> PlanningHealthStatus:
        """Attempt to plan every registered objective with no parameters,
        partitioning objectives into structurally valid and invalid, without
        executing anything."""
        objectives = self._registry.list_objectives()
        valid: list[str] = []
        invalid: list[str] = []
        for objective in objectives:
            try:
                self.plan(PlanningRequest(objective=objective))
            except PlanningError:
                invalid.append(objective)
            else:
                valid.append(objective)
        return PlanningHealthStatus(
            registered_objectives=objectives,
            valid_templates=tuple(valid),
            invalid_templates=tuple(invalid),
            ready=not invalid,
        )

    def _expand(
        self,
        objective: str,
        *,
        inherited_depends_on: tuple[str, ...],
        prefix: str,
        visiting: frozenset[str],
    ) -> tuple[list[PlanStep], tuple[str, ...]]:
        """Recursively flatten `objective`'s template into plain (non-sub-plan)
        `PlanStep`s, namespacing every step a sub-plan expansion introduces.

        Returns `(steps, exit_ids)`: `steps` is the fully resolved,
        namespaced step list for this objective's whole subtree; `exit_ids`
        are its own terminal step ids — the ones nothing else *inside this
        subtree* depends on. A sibling step that depends on a sub-plan step
        is rewired to depend on that sub-plan's `exit_ids` instead, so
        "depend on this sub-plan" means "depend on everything it doesn't
        internally depend on" — i.e. wait for the whole sub-plan. Steps with
        no explicit `depends_on` of their own (this subtree's own entry
        points) additionally receive `inherited_depends_on`, so a sub-plan
        never starts before whatever the step that referenced it required.
        """
        if objective in visiting:
            raise InvalidPlanError(
                f"Circular sub-plan reference detected at objective {objective!r}.",
                objective=objective,
            )
        template: PlanTemplate = self._registry.get(objective)
        visiting = visiting | {objective}

        locally_depended_upon = {
            dep.step_id for step in template.steps for dep in step.depends_on
        }
        substitution: dict[str, tuple[str, ...]] = {}
        result_steps: list[PlanStep] = []

        for step in _local_topological_order(template.steps):
            full_id = f"{prefix}{step.step_id}"
            if step.depends_on:
                resolved_deps = tuple(
                    resolved_id
                    for dep in step.depends_on
                    for resolved_id in substitution[dep.step_id]
                )
            else:
                resolved_deps = inherited_depends_on

            if step.sub_plan is not None:
                sub_steps, sub_exit_ids = self._expand(
                    step.sub_plan,
                    inherited_depends_on=resolved_deps,
                    prefix=f"{full_id}::",
                    visiting=visiting,
                )
                result_steps.extend(sub_steps)
                substitution[step.step_id] = sub_exit_ids
            else:
                result_steps.append(
                    step.model_copy(
                        update={
                            "step_id": full_id,
                            "depends_on": tuple(PlanDependency(step_id=d) for d in resolved_deps),
                        }
                    )
                )
                substitution[step.step_id] = (full_id,)

        exit_ids = tuple(
            resolved_id
            for step in template.steps
            if step.step_id not in locally_depended_upon
            for resolved_id in substitution[step.step_id]
        )
        return result_steps, exit_ids

    def _build_execution_plan(
        self, steps: list[PlanStep], parameters: Mapping[str, Any]
    ) -> ExecutionPlan:
        tasks = tuple(self._to_agent_task(step, parameters) for step in steps)
        try:
            return ExecutionPlan(tasks=tasks)
        except InvalidExecutionPlanError as exc:
            raise InvalidPlanError(str(exc)) from exc

    @staticmethod
    def _to_agent_task(step: PlanStep, parameters: Mapping[str, Any]) -> AgentTask:
        assert step.agent_id is not None  # guaranteed: sub_plan steps never survive _expand
        payload = {**step.input_data, **parameters}
        return AgentTask(
            task_id=step.step_id,
            agent_id=step.agent_id,
            input_data=StepInputPayload(parameters=payload),
            depends_on=tuple(dep.step_id for dep in step.depends_on),
        )
