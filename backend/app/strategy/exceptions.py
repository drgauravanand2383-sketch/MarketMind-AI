"""Exception hierarchy for the Strategy Evaluation Engine's application layer.

Self-contained model constraints (unknown operator, unknown field, invalid
BETWEEN, empty IN/NOT_IN, missing value, non-positive weight, duplicate
rule id, out-of-range alignment/confidence) are enforced by
`app.strategy.models` itself and raise a plain `pydantic.ValidationError`
— see that module's docstring. This hierarchy covers only what
`StrategyEvaluationService` enforces: rules that need injected,
runtime-configurable state (a maximum strategy/rule count, duplicate
strategy names) or that depend on existing repository state (not found).
"""

from __future__ import annotations

__all__ = [
    "StrategyEngineError",
    "StrategyNotFoundError",
    "StrategyEvaluationNotFoundError",
    "DuplicateStrategyNameError",
    "MaxStrategiesExceededError",
    "MaxStrategyRulesExceededError",
]


class StrategyEngineError(Exception):
    """Base class for every error raised by the Strategy Evaluation Engine's application layer."""

    def __init__(self, message: str, *, strategy_id: str | None = None) -> None:
        self.strategy_id = strategy_id
        super().__init__(message)


class StrategyNotFoundError(StrategyEngineError):
    """Raised when no strategy exists for the given id."""

    def __init__(self, strategy_id: str) -> None:
        super().__init__(f"No strategy found with id {strategy_id!r}.", strategy_id=strategy_id)


class StrategyEvaluationNotFoundError(StrategyEngineError):
    """Raised when no evaluation result exists for the given request id."""

    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        super().__init__(f"No strategy evaluation result found for request id {request_id!r}.")


class DuplicateStrategyNameError(StrategyEngineError):
    """Raised when creating/duplicating a strategy to a name already in use.

    Only raised when `StrategyEvaluationService` was constructed with
    `enforce_unique_names=True` (the default).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A strategy named {name!r} already exists.")


class MaxStrategiesExceededError(StrategyEngineError):
    """Raised when creating a strategy would exceed the configured maximum
    number of registered strategies."""

    def __init__(self, limit: int, actual: int) -> None:
        self.limit = limit
        self.actual = actual
        super().__init__(
            f"Already have {actual} registered strategies, exceeding the configured maximum of {limit}."
        )


class MaxStrategyRulesExceededError(StrategyEngineError):
    """Raised when a strategy's rule count would exceed the configured maximum."""

    def __init__(self, strategy_id: str | None, limit: int, actual: int) -> None:
        self.limit = limit
        self.actual = actual
        super().__init__(
            f"Strategy has {actual} rules, exceeding the configured maximum of {limit}.",
            strategy_id=strategy_id,
        )
