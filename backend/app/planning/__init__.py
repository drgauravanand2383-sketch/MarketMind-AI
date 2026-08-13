"""Agent Planning Engine: converts a high-level objective into a
deterministic, validated `app.orchestrator.models.ExecutionPlan`.

Planning only — no agent execution, no AI reasoning, exact objective
matching only. See `app.planning.models` for the design notes behind
sub-plan expansion and the generic step-input payload.
"""

from __future__ import annotations

from app.planning.exceptions import (
    InvalidPlanError,
    PlanningError,
    PlanTemplateAlreadyRegisteredError,
    UnknownObjectiveError,
)
from app.planning.models import (
    PlanDependency,
    PlanningHealthStatus,
    PlanningRequest,
    PlanningResult,
    PlanStep,
    PlanTemplate,
    StepInputPayload,
)
from app.planning.planner import PlanningEngine
from app.planning.registry import PlanRegistry

__all__ = [
    "PlanningEngine",
    "PlanRegistry",
    "PlanDependency",
    "PlanStep",
    "PlanTemplate",
    "PlanningRequest",
    "PlanningResult",
    "StepInputPayload",
    "PlanningHealthStatus",
    "PlanningError",
    "PlanTemplateAlreadyRegisteredError",
    "UnknownObjectiveError",
    "InvalidPlanError",
]
