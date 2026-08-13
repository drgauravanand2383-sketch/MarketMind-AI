"""Exception hierarchy for the Multi-Agent Orchestrator.

All framework errors derive from `OrchestratorError`. None of these are
raised for one agent's own runtime failure during `execute()` — that's
captured as a `FAILED` `AgentExecutionResult` instead ("one failed agent
must not crash the orchestrator"). They're raised only for genuine
caller/configuration errors: registering a duplicate agent id, referencing
an agent id directly (via `execute_one()`) or a task dependency
(structurally, at `ExecutionPlan` construction time) that doesn't exist,
or an unexpected internal orchestration invariant violation.
"""

from __future__ import annotations

__all__ = [
    "OrchestratorError",
    "AgentAlreadyRegisteredError",
    "AgentNotRegisteredError",
    "InvalidExecutionPlanError",
    "OrchestratorExecutionError",
]


class OrchestratorError(Exception):
    """Base class for all Multi-Agent Orchestrator errors."""

    def __init__(self, message: str, *, agent_id: str | None = None) -> None:
        self.agent_id = agent_id
        super().__init__(message)


class AgentAlreadyRegisteredError(OrchestratorError):
    """Raised when registering an agent id that's already registered."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(f"An agent is already registered under id {agent_id!r}", agent_id=agent_id)


class AgentNotRegisteredError(OrchestratorError):
    """Raised by `execute_one()` when `agent_id` isn't registered.

    Within a full plan (`execute()`), an unregistered agent id referenced
    by a task is instead captured as that one task's own `FAILED` result —
    isolating the failure rather than aborting the whole plan. This
    exception is only for the direct, single-agent calling convention,
    where an unknown agent id is an immediate caller error.
    """

    def __init__(self, agent_id: str) -> None:
        super().__init__(f"No agent registered under id {agent_id!r}", agent_id=agent_id)


class InvalidExecutionPlanError(OrchestratorError):
    """Raised when an `ExecutionPlan` is structurally invalid.

    Covers a duplicate `task_id`, a dependency referencing an unknown
    `task_id`, a task depending on itself, or a dependency cycle — all
    checked eagerly at `ExecutionPlan` construction time (fail fast),
    never discovered mid-execution.
    """


class OrchestratorExecutionError(OrchestratorError):
    """Raised for a genuinely unexpected internal orchestration failure.

    Never raised for an individual agent's own failure (captured as a
    `FAILED` `AgentExecutionResult` instead) — only for an orchestration
    algorithm invariant violation that should be impossible given a
    validated `ExecutionPlan`.
    """
