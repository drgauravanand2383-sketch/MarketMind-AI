"""HTTP-layer schemas for the Screening API.

Response bodies reuse `app.screening.models` directly (`ScreeningProfile`,
`ScreenResult`) wherever they already fit. `ScreeningEngine.create_profile()`
takes individual primitive arguments (no matching domain model), and
`update_profile()` is a whole-object replace with no partial-patch method
— both get dedicated schemas here.

`ScreeningEngine.evaluate_companies()` is synchronous, stateless, and
never persists anything — there is no `run`/`get_result`-by-id capability
in the frozen engine. By explicit product decision, a thin in-process,
HTTP-layer-only cache (`app.api.v1.schemas.result_store.InMemoryResultStore`)
fills this gap for `GET /screening/results/{result_id}` — the router
generates an id when caching a freshly computed run; no business logic
is added.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.screening.models import CompanyMetrics, LogicalGroup, ScreenFilter, ScreenResult

__all__ = [
    "CreateScreeningProfileRequest",
    "UpdateScreeningProfileRequest",
    "DuplicateScreeningProfileRequest",
    "RunScreeningRequest",
    "ScreeningRunEnvelope",
]


class CreateScreeningProfileRequest(BaseModel):
    """Request body for `POST /api/v1/screening/profiles`."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, examples=["Value Screen"])
    description: str = ""
    is_default: bool = False
    filters: tuple[ScreenFilter, ...] = ()
    groups: tuple[LogicalGroup, ...] = ()


class UpdateScreeningProfileRequest(BaseModel):
    """Request body for `PATCH /api/v1/screening/profiles/{profile_id}`.

    `ScreeningEngine.update_profile()` is a whole-object replace, not a
    partial-patch method — the router fetches the existing
    `ScreeningProfile`, applies only the fields set here via
    `model_copy(update=...)`, then calls `update_profile()` with the
    merged object.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    is_default: bool | None = None
    filters: tuple[ScreenFilter, ...] | None = None
    groups: tuple[LogicalGroup, ...] | None = None


class DuplicateScreeningProfileRequest(BaseModel):
    """Request body for `POST /api/v1/screening/profiles/{profile_id}/duplicate`.

    Frontend Milestone 4 addition: `ScreeningEngine.duplicate_profile()`
    existed since the engine was first built but was never reachable
    over REST — the same situation as Milestone 1's auth router and
    Milestone 3's notes-editing endpoint. Wraps that one existing method;
    no new logic."""

    model_config = ConfigDict(extra="forbid")

    new_name: str = Field(min_length=1, examples=["Value Screen (copy)"])


class RunScreeningRequest(BaseModel):
    """Request body for `POST /api/v1/screening/run`.

    `ScreeningEngine` never fetches market data itself — the caller
    supplies each company's metrics directly.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1)
    companies: list[CompanyMetrics] = Field(min_length=1)


class ScreeningRunEnvelope(BaseModel):
    """A screening run's results plus the id it was cached under —
    returned by both `POST /run` and `GET /results/{result_id}`."""

    model_config = ConfigDict(extra="forbid")

    result_id: str
    profile_id: str
    results: list[ScreenResult]
