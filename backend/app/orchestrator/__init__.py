"""Multi-Agent Orchestrator — coordinates multiple agents during a single execution.

`AgentOrchestrator` (orchestrator.py) registers already-built `BaseAgent`
instances and executes them — singly (`execute_one()`) or via an
`ExecutionPlan` (`execute()`), in dependency order, wave by wave, isolating
each task's failure from every other. Orchestration only: no reasoning, no
AI-based routing, no planning — `ExecutionPlan` (models.py) is built by
the caller, not decided by this package.
"""

from app.orchestrator.exceptions import (
    AgentAlreadyRegisteredError,
    AgentNotRegisteredError,
    InvalidExecutionPlanError,
    OrchestratorError,
    OrchestratorExecutionError,
)
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
from app.orchestrator.orchestrator import AgentOrchestrator

__all__ = [
    "AgentOrchestrator",
    "AgentTask",
    "AgentExecutionResult",
    "ExecutionPlan",
    "ExecutionNode",
    "ExecutionGraph",
    "ExecutionSummary",
    "ExecutionStatus",
    "OrchestratorHealthStatus",
    "OrchestratorError",
    "AgentAlreadyRegisteredError",
    "AgentNotRegisteredError",
    "InvalidExecutionPlanError",
    "OrchestratorExecutionError",
]
