"""HTTP-layer request schemas for the Strategy Evaluation API.

Response bodies reuse `app.strategy.models` directly (`InvestmentStrategy`,
`StrategyEvaluationResult`). `StrategyEvaluationService.create_strategy()`
takes individual primitive arguments (no matching domain model for
"create"), and `update_strategy()` is a whole-object replace with no
partial-patch method — so both get dedicated schemas here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.strategy.models import StrategyRule, StrategyType, StrategyWeighting

__all__ = ["CreateStrategyRequest", "UpdateStrategyRequest", "EvaluateStrategyRequest"]


class CreateStrategyRequest(BaseModel):
    """Request body for `POST /api/v1/strategies`."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, examples=["Momentum Growth"])
    description: str = ""
    strategy_type: StrategyType = StrategyType.CUSTOM
    enabled: bool = True
    weightings: StrategyWeighting = Field(default_factory=StrategyWeighting)
    rules: tuple[StrategyRule, ...] = ()


class UpdateStrategyRequest(BaseModel):
    """Request body for `PATCH /api/v1/strategies/{strategy_id}`.

    `StrategyEvaluationService.update_strategy()` is a whole-object
    replace, not a partial-patch method — the router fetches the existing
    `InvestmentStrategy`, applies only the fields set here via
    `model_copy(update=...)`, then calls `update_strategy()` with the
    merged object.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    strategy_type: StrategyType | None = None
    enabled: bool | None = None
    weightings: StrategyWeighting | None = None
    rules: tuple[StrategyRule, ...] | None = None


class EvaluateStrategyRequest(BaseModel):
    """Request body for `POST /api/v1/strategies/evaluate`."""

    model_config = ConfigDict(extra="forbid")

    recommendation_result_id: str = Field(min_length=1)
    strategy_ids: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Strategies to evaluate against. Empty means every strategy.",
    )
