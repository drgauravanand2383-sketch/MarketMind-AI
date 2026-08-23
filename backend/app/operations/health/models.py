"""Domain models for production health & readiness.

`HealthState` is used consistently across every health model in this
module — `HEALTHY`/`DEGRADED`/`UNHEALTHY` — so aggregation
(`app.operations.health.service.HealthCheckService`) never has to
reconcile different vocabularies between a repository's health, a
service's health, and an external dependency's health.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "HealthState",
    "RepositoryHealth",
    "ServiceHealth",
    "DependencyHealth",
    "ApplicationHealth",
    "ReadinessStatus",
]


class HealthState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class RepositoryHealth(BaseModel):
    """One repository's own reachability, as reported by that
    repository's own `health_check()` method — never recomputed or
    inferred, only relayed."""

    model_config = ConfigDict(extra="forbid")

    name: str
    state: HealthState
    message: str


class ServiceHealth(BaseModel):
    """One application-layer service's construction status — a service
    has no live `health_check()` of its own (it holds no external
    connection directly; its repository does), so this reports whether
    dependency injection successfully constructed it."""

    model_config = ConfigDict(extra="forbid")

    name: str
    state: HealthState
    message: str


class DependencyHealth(BaseModel):
    """One external dependency's (database, cache, vector store, LLM
    provider) reachability."""

    model_config = ConfigDict(extra="forbid")

    name: str
    state: HealthState
    message: str


class ApplicationHealth(BaseModel):
    """The aggregate health of the whole application: every checked
    repository, service, and external dependency, rolled up into one
    overall `HealthState`."""

    model_config = ConfigDict(extra="forbid")

    state: HealthState
    repositories: tuple[RepositoryHealth, ...] = Field(default_factory=tuple)
    services: tuple[ServiceHealth, ...] = Field(default_factory=tuple)
    dependencies: tuple[DependencyHealth, ...] = Field(default_factory=tuple)
    checked_at: datetime
    summary: str


class ReadinessStatus(BaseModel):
    """Whether the application is ready to serve traffic — `ready` is
    `False` whenever any repository or service is `UNHEALTHY`;
    `DEGRADED` components do not block readiness but are still surfaced
    via `application_health`."""

    model_config = ConfigDict(extra="forbid")

    ready: bool
    application_health: ApplicationHealth
    blocking_issues: tuple[str, ...] = Field(default_factory=tuple)
