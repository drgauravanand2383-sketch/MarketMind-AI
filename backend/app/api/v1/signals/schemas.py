"""HTTP-layer schemas for the Signal Detection API.

Response bodies reuse `app.signals.models` directly (`SignalDefinition`,
`SignalBatchResult`) wherever they already fit.
`SignalDetectionService.create_signal_definition()` takes individual
primitive arguments (no matching domain model), and
`update_signal_definition()` is a whole-object replace with no
partial-patch method — both get dedicated schemas here.

`SignalDetectionService`'s evaluate methods are synchronous, stateless,
and never persist anything — there is no `get_result`-by-id capability in
the frozen engine. By explicit product decision, a thin in-process,
HTTP-layer-only cache (`app.api.v1.schemas.result_store.InMemoryResultStore`)
fills this gap for `GET /signals/results/{result_id}` — the router
generates an id when caching a freshly computed evaluation; no business
logic is added.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.signals.models import (
    MarketDataSnapshot,
    SignalBatchResult,
    SignalCondition,
    SignalConditionGroup,
    SignalPriority,
)

__all__ = [
    "CreateSignalDefinitionRequest",
    "UpdateSignalDefinitionRequest",
    "EvaluateSignalsRequest",
    "SignalEvaluationEnvelope",
]


class CreateSignalDefinitionRequest(BaseModel):
    """Request body for `POST /api/v1/signals/definitions`."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, examples=["RSI Oversold"])
    description: str = ""
    category: str = "CUSTOM"
    priority: SignalPriority = SignalPriority.MEDIUM
    enabled: bool = True
    conditions: tuple[SignalCondition, ...] = ()
    groups: tuple[SignalConditionGroup, ...] = ()


class UpdateSignalDefinitionRequest(BaseModel):
    """Request body for `PATCH /api/v1/signals/definitions/{definition_id}`.

    `SignalDetectionService.update_signal_definition()` is a whole-object
    replace, not a partial-patch method — the router fetches the existing
    `SignalDefinition`, applies only the fields set here via
    `model_copy(update=...)`, then calls `update_signal_definition()`
    with the merged object.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    category: str | None = None
    priority: SignalPriority | None = None
    enabled: bool | None = None
    conditions: tuple[SignalCondition, ...] | None = None
    groups: tuple[SignalConditionGroup, ...] | None = None


class EvaluateSignalsRequest(BaseModel):
    """Request body for `POST /api/v1/signals/evaluate`."""

    model_config = ConfigDict(extra="forbid")

    definition_id: str = Field(min_length=1)
    snapshots: list[MarketDataSnapshot] = Field(min_length=1)


class SignalEvaluationEnvelope(BaseModel):
    """A signal evaluation's batch result plus the id it was cached
    under — returned by both `POST /evaluate` and `GET /results/{result_id}`."""

    model_config = ConfigDict(extra="forbid")

    result_id: str
    definition_id: str
    batch_result: SignalBatchResult
