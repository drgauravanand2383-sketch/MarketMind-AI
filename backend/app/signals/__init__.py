"""Signal Detection Engine: evaluates normalized Market Data Abstraction
Layer records against reusable, weighted signal definitions and produces
structured, scored, explainable signal results.

Detection and scoring only — no live provider connection, no trade
execution, no investment recommendation, no portfolio mutation, and no
alert generation exist anywhere in this package.
"""

from __future__ import annotations

from app.signals.engine import SignalDetectionService
from app.signals.exceptions import (
    DuplicateSignalNameError,
    MaxConditionsExceededError,
    SignalDefinitionNotFoundError,
    SignalError,
)
from app.signals.models import (
    ConditionEvaluation,
    MarketDataSnapshot,
    SignalBatchResult,
    SignalCategory,
    SignalCondition,
    SignalConditionGroup,
    SignalDefinition,
    SignalLogicType,
    SignalOperator,
    SignalPriority,
    SignalResult,
)

__all__ = [
    "SignalDetectionService",
    "SignalOperator",
    "SignalLogicType",
    "SignalCategory",
    "SignalPriority",
    "SignalConditionGroup",
    "SignalCondition",
    "SignalDefinition",
    "MarketDataSnapshot",
    "ConditionEvaluation",
    "SignalResult",
    "SignalBatchResult",
    "SignalError",
    "SignalDefinitionNotFoundError",
    "DuplicateSignalNameError",
    "MaxConditionsExceededError",
]
