"""AgentOrchestrator — coordinates multiple agents during a single execution.

Orchestration only: this module performs no reasoning, makes no AI-based
routing decisions, and does no planning — it only executes an
already-built `ExecutionPlan` (or a single agent, via `execute_one()`)
against already-registered `BaseAgent` instances, in dependency order,
isolating each task's failure from every other.

Execution algorithm: every task whose dependencies have already resolved
(succeeded, failed, or been skipped) runs concurrently as one "wave"; the
next wave starts once the current one finishes. A task depending on a
`FAILED` or `SKIPPED` task is itself recorded as `SKIPPED` — it never
runs, and its own failure to run never stops any independent branch of
the plan. `ExecutionPlan.sequential()`/`.parallel()`/`.mixed()` are three
ways to *build* a plan (see models.py); this one algorithm runs all three.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone

from pydantic import BaseModel

from app.agents.base import BaseAgent
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.orchestrator.exceptions import AgentAlreadyRegisteredError, AgentNotRegisteredError
from app.orchestrator.models import (
    AgentExecutionResult,
    AgentTask,
    ExecutionGraph,
    ExecutionNode,
    ExecutionPlan,
    ExecutionStatus,
    ExecutionSummary,
    OrchestratorHealthStatus,
)

__all__ = ["AgentOrchestrator"]


class AgentOrchestrator:
    """Registers agents and executes them — singly, or via an `ExecutionPlan`.

    No singleton, no global state: construct one instance and register
    each already-built `BaseAgent` explicitly. The orchestrator never
    constructs an agent itself.
    """

    def __init__(self, agents: Mapping[str, BaseAgent] | None = None) -> None:
        """Initialize, optionally with an initial set of already-built agents.

        Args:
            agents: An optional starting set of agent instances, keyed by
                agent id. Equivalent to calling `register_agent()` once
                per entry — provided as a convenience; `register_agent()`
                remains the primary way to add agents.
        """
        self._agents: dict[str, BaseAgent] = dict(agents) if agents else {}

    def register_agent(self, agent_id: str, agent: BaseAgent) -> None:
        """Register `agent` under `agent_id`.

        Raises:
            AgentAlreadyRegisteredError: If `agent_id` is already registered.
        """
        if agent_id in self._agents:
            raise AgentAlreadyRegisteredError(agent_id)
        self._agents[agent_id] = agent

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent registration, if present. A no-op if absent."""
        self._agents.pop(agent_id, None)

    def list_agents(self) -> tuple[str, ...]:
        """List all currently registered agent ids, sorted alphabetically."""
        return tuple(sorted(self._agents))

    def build_graph(
        self,
        plan: ExecutionPlan,
        results: Mapping[str, AgentExecutionResult] | None = None,
    ) -> ExecutionGraph:
        """Expose `plan`'s structure as an `ExecutionGraph`.

        Args:
            plan: The plan to describe.
            results: If supplied (typically after `execute()`), each
                node's `status` reflects that task's recorded outcome;
                otherwise every node's `status` is `None` (a purely
                structural, pre-execution view).
        """
        results = results or {}
        nodes = tuple(
            ExecutionNode(
                task_id=task.task_id,
                agent_id=task.agent_id,
                depends_on=task.depends_on,
                status=results[task.task_id].status if task.task_id in results else None,
            )
            for task in plan.tasks
        )
        return ExecutionGraph(nodes=nodes)

    async def execute_one(
        self, agent_id: str, input_data: BaseModel, *, initiated_by: str = "orchestrator"
    ) -> AgentExecutionResult:
        """Run exactly one registered agent directly, without a full plan.

        Unlike a task inside `execute()`, an unregistered `agent_id` here
        raises immediately — a direct, single-agent call is a simpler
        calling convention where an unknown agent is a caller error, not
        something to isolate and continue past.

        Raises:
            AgentNotRegisteredError: If `agent_id` isn't registered.
        """
        if agent_id not in self._agents:
            raise AgentNotRegisteredError(agent_id)

        execution_id = str(uuid.uuid4())
        task = AgentTask(task_id=execution_id, agent_id=agent_id, input_data=input_data)
        return await self._run_task(task, {}, execution_id, initiated_by)

    async def execute(
        self, plan: ExecutionPlan, *, initiated_by: str = "orchestrator"
    ) -> ExecutionSummary:
        """Execute every task in `plan`, wave by wave, in dependency order.

        One failed (or misconfigured — e.g. an unregistered agent id)
        task is recorded as `FAILED` and never aborts the rest of the
        plan; a task depending on one that didn't succeed is recorded as
        `SKIPPED`, also without aborting any independent branch.
        """
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        started_monotonic = time.monotonic()

        results: dict[str, AgentExecutionResult] = {}
        remaining = {task.task_id: task for task in plan.tasks}

        while remaining:
            ready = [
                task
                for task in remaining.values()
                if all(dependency in results for dependency in task.depends_on)
            ]
            wave_results = await asyncio.gather(
                *(self._run_task(task, results, execution_id, initiated_by) for task in ready)
            )
            for task, result in zip(ready, wave_results, strict=True):
                results[task.task_id] = result
                del remaining[task.task_id]

        completed_at = datetime.now(timezone.utc)
        ordered_results = tuple(results[task.task_id] for task in plan.tasks)

        success_count = sum(1 for result in ordered_results if result.status == ExecutionStatus.SUCCESS)
        failed_count = sum(1 for result in ordered_results if result.status == ExecutionStatus.FAILED)
        skipped_count = sum(1 for result in ordered_results if result.status == ExecutionStatus.SKIPPED)

        return ExecutionSummary(
            execution_id=execution_id,
            started_at=started_at,
            completed_at=completed_at,
            duration=time.monotonic() - started_monotonic,
            results=ordered_results,
            graph=self.build_graph(plan, results),
            success_count=success_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            overall_success=failed_count == 0,
        )

    async def health_check(self) -> OrchestratorHealthStatus:
        """Verify every registered agent's own `health_check()`. Executes no agent.

        An agent whose `health_check()` itself raises is treated as
        unhealthy, not as an orchestrator-crashing failure.
        """
        agent_ids = self.list_agents()

        async def _check(agent_id: str) -> bool:
            try:
                return await self._agents[agent_id].health_check()
            except Exception:  # noqa: BLE001 - one agent's broken health_check must not crash this
                return False

        outcomes = await asyncio.gather(*(_check(agent_id) for agent_id in agent_ids))

        healthy = tuple(agent_id for agent_id, ok in zip(agent_ids, outcomes, strict=True) if ok)
        unhealthy = tuple(agent_id for agent_id, ok in zip(agent_ids, outcomes, strict=True) if not ok)

        return OrchestratorHealthStatus(
            healthy_agents=healthy, unhealthy_agents=unhealthy, ready=len(unhealthy) == 0
        )

    async def _run_task(
        self,
        task: AgentTask,
        prior_results: Mapping[str, AgentExecutionResult],
        execution_id: str,
        initiated_by: str,
    ) -> AgentExecutionResult:
        """Run one task, isolating both its own failure and an unmet dependency."""
        blocking = [
            dependency
            for dependency in task.depends_on
            if prior_results[dependency].status != ExecutionStatus.SUCCESS
        ]
        if blocking:
            now = datetime.now(timezone.utc)
            return AgentExecutionResult(
                execution_id=execution_id,
                task_id=task.task_id,
                agent_id=task.agent_id,
                status=ExecutionStatus.SKIPPED,
                output=None,
                error=f"Skipped: dependency {blocking[0]!r} did not succeed.",
                start_time=now,
                finish_time=now,
                duration=0.0,
                dependencies=task.depends_on,
            )

        start_time = datetime.now(timezone.utc)
        start_monotonic = time.monotonic()

        agent = self._agents.get(task.agent_id)
        if agent is None:
            finish_time = datetime.now(timezone.utc)
            return AgentExecutionResult(
                execution_id=execution_id,
                task_id=task.task_id,
                agent_id=task.agent_id,
                status=ExecutionStatus.FAILED,
                output=None,
                error=f"No agent registered under id {task.agent_id!r}",
                start_time=start_time,
                finish_time=finish_time,
                duration=time.monotonic() - start_monotonic,
                dependencies=task.depends_on,
            )

        context = self._build_context(task, execution_id, initiated_by)
        try:
            output = await agent.run(context, task.input_data)
        except Exception as exc:  # noqa: BLE001 - one failed agent must not crash the orchestrator
            finish_time = datetime.now(timezone.utc)
            return AgentExecutionResult(
                execution_id=execution_id,
                task_id=task.task_id,
                agent_id=task.agent_id,
                status=ExecutionStatus.FAILED,
                output=None,
                error=str(exc),
                start_time=start_time,
                finish_time=finish_time,
                duration=time.monotonic() - start_monotonic,
                dependencies=task.depends_on,
            )

        finish_time = datetime.now(timezone.utc)
        return AgentExecutionResult(
            execution_id=execution_id,
            task_id=task.task_id,
            agent_id=task.agent_id,
            status=ExecutionStatus.SUCCESS,
            output=output,
            error=None,
            start_time=start_time,
            finish_time=finish_time,
            duration=time.monotonic() - start_monotonic,
            dependencies=task.depends_on,
        )

    def _build_context(self, task: AgentTask, execution_id: str, initiated_by: str) -> ExecutionContext:
        """Build a fresh ExecutionContext for one task's execution.

        Each task gets its own, freshly-generated `execution_id` (distinct
        even for tasks running concurrently in the same wave), but every
        task in one `execute()` call shares the same `trace_id` — the
        orchestrator run's own `execution_id` — so every agent invocation
        belonging to one orchestrated run can be correlated together.
        Mirrors `Scheduler`'s own established pattern (Sprint 31) of
        building a fresh `ExecutionContext` per triggered execution.
        """
        task_execution_id = str(uuid.uuid4())
        return ExecutionContext(
            workflow_id=task.agent_id,
            execution_id=task_execution_id,
            workflow_type="orchestrated_task",
            trigger=TriggerType.UPSTREAM_WORKFLOW,
            initiated_by=initiated_by,
            started_at=datetime.now(timezone.utc),
            trace_id=execution_id,
            participating_agents=(task.agent_id,),
            status=WorkflowStatus.RUNNING,
        )
