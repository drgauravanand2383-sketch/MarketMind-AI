"""Orchestration workflows that coordinate already-implemented components end to end.

WorkflowEngine (engine.py) is the execution layer sitting above individual
workflow implementations (e.g. morning_pipeline/, morning_brief/) — it
registers and runs them by id, but knows nothing about what any specific
workflow does.
"""

from app.workflows.engine import (
    WorkflowAlreadyRegisteredError,
    WorkflowEngine,
    WorkflowNotRegisteredError,
    WorkflowProtocol,
)
from app.workflows.models import WorkflowExecutionResult

__all__ = [
    "WorkflowEngine",
    "WorkflowProtocol",
    "WorkflowExecutionResult",
    "WorkflowNotRegisteredError",
    "WorkflowAlreadyRegisteredError",
]
