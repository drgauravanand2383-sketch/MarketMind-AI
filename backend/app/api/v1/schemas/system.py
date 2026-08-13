"""HTTP-layer schemas for the system introspection endpoints (`/version`,
`/configuration`, `/capabilities`, `/services`).

Every field here is read directly from already-existing backend state
(`app.bootstrap.AppSettings`, `app.config.models.APISettings`/
`SchedulerSettings`, and which `app.state` components bootstrap
constructed) — no business logic, no new computation. `ConfigurationResponse`
deliberately excludes every secret-bearing settings section (PostgreSQL
credentials, the Anthropic API key, Redis credentials) — see its own
docstring.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "VersionResponse",
    "ConfigurationResponse",
    "CapabilitiesResponse",
    "ServiceEntry",
    "ServicesResponse",
]


class VersionResponse(BaseModel):
    """Response payload for `GET /api/v1/version`."""

    model_config = ConfigDict(extra="forbid")

    api_version: str
    application_version: str
    environment: str


class ConfigurationResponse(BaseModel):
    """Response payload for `GET /api/v1/configuration`.

    Exposes only non-secret, already-public-shape settings — every field
    here comes from `AppSettings`/`APISettings`/`SchedulerSettings`, none
    of which carry a `SecretStr`. `PostgreSQLSettings`, `AnthropicSettings`,
    and `RedisSettings` (all of which carry credentials) are never
    consulted by this endpoint at all, not merely redacted after the
    fact — there is no code path here that could leak one.
    """

    model_config = ConfigDict(extra="forbid")

    environment: str
    log_level: str
    api_version_prefix: str
    allowed_origins: tuple[str, ...]
    watchlist_max_size: int
    screening_max_filters: int
    signal_max_conditions: int
    alert_max_rules: int
    scheduler_enabled: bool
    rss_feed_count: int


class CapabilitiesResponse(BaseModel):
    """Response payload for `GET /api/v1/capabilities` — a coarse-grained
    feature-flag view of which major backend capabilities this deployment
    currently supports. Investment-engine flags are derived from whether
    bootstrap actually constructed that engine's service (`app.state
    .<name>_service is not None`); infrastructure capabilities this
    codebase does not yet implement (per every Sprint 44-55 constraint)
    are always reported `False` — never inferred, never a placeholder for
    something partially built."""

    model_config = ConfigDict(extra="forbid")

    capabilities: dict[str, bool] = Field(default_factory=dict)


class ServiceEntry(BaseModel):
    """One service's availability, mirroring `app.operations.health
    .models.ServiceHealth` but reported under the `/services` inventory
    endpoint rather than the `/health` diagnostic endpoint."""

    model_config = ConfigDict(extra="forbid")

    name: str
    available: bool


class ServicesResponse(BaseModel):
    """Response payload for `GET /api/v1/services`."""

    model_config = ConfigDict(extra="forbid")

    services: tuple[ServiceEntry, ...] = Field(default_factory=tuple)
