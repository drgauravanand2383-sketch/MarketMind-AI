"""HealthCheckService: aggregates repository/service/dependency health
into `ApplicationHealth`/`ReadinessStatus`.

Exposes service methods only — no HTTP endpoint is defined anywhere in
this module or package (per this sprint's own "Expose service methods
only. Do NOT build HTTP endpoints." instruction); a future API sprint can
wrap these methods in a route without any change here.

Every repository's own reachability is reported via that repository's own
already-existing `health_check()` method (every `Base*Repository` in this
codebase already implements one — Screening through Explainability,
Sprints 44-53) — this service never opens a connection or recomputes
reachability itself, only calls and aggregates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Protocol

from app.operations.health.models import (
    ApplicationHealth,
    DependencyHealth,
    HealthState,
    ReadinessStatus,
    RepositoryHealth,
    ServiceHealth,
)

__all__ = ["HealthCheckService"]


class _HealthCheckable(Protocol):
    async def health_check(self) -> bool: ...


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class HealthCheckService:
    def __init__(self, *, now_fn: Callable[[], datetime] = _default_now) -> None:
        self._now_fn = now_fn

    async def check_repositories(
        self, repositories: dict[str, _HealthCheckable | None]
    ) -> tuple[RepositoryHealth, ...]:
        """Check every repository's own `health_check()`. A `None` entry
        (dependency injection failed to construct it) is reported
        `UNHEALTHY` without attempting a call; an exception raised by
        `health_check()` itself is also reported `UNHEALTHY`, never
        propagated."""
        results: list[RepositoryHealth] = []
        for name, repository in repositories.items():
            if repository is None:
                results.append(RepositoryHealth(name=name, state=HealthState.UNHEALTHY, message="not configured"))
                continue
            try:
                reachable = await repository.health_check()
            except Exception as exc:  # noqa: BLE001 - a health check must never raise
                results.append(RepositoryHealth(name=name, state=HealthState.UNHEALTHY, message=str(exc)))
                continue
            state = HealthState.HEALTHY if reachable else HealthState.UNHEALTHY
            message = "reachable" if reachable else "unreachable"
            results.append(RepositoryHealth(name=name, state=state, message=message))
        return tuple(sorted(results, key=lambda result: result.name))

    def check_services(self, services: dict[str, object | None]) -> tuple[ServiceHealth, ...]:
        """A service is `HEALTHY` if dependency injection constructed it
        (non-`None`), `UNHEALTHY` otherwise — services hold no external
        connection of their own to probe (their repository does)."""
        results = [
            ServiceHealth(
                name=name,
                state=HealthState.HEALTHY if service is not None else HealthState.UNHEALTHY,
                message="constructed" if service is not None else "not constructed",
            )
            for name, service in services.items()
        ]
        return tuple(sorted(results, key=lambda result: result.name))

    async def check_application(
        self,
        repositories: dict[str, _HealthCheckable | None],
        services: dict[str, object | None],
        dependencies: tuple[DependencyHealth, ...] = (),
    ) -> ApplicationHealth:
        repository_health = await self.check_repositories(repositories)
        service_health = self.check_services(services)
        overall = _aggregate_state(repository_health, service_health, dependencies)
        unhealthy = sum(
            1
            for group in (repository_health, service_health, dependencies)
            for item in group
            if item.state == HealthState.UNHEALTHY
        )
        total = len(repository_health) + len(service_health) + len(dependencies)
        return ApplicationHealth(
            state=overall,
            repositories=repository_health,
            services=service_health,
            dependencies=dependencies,
            checked_at=self._now_fn(),
            summary=f"{total - unhealthy}/{total} component(s) healthy" if total else "no components checked",
        )

    async def check_readiness(
        self,
        repositories: dict[str, _HealthCheckable | None],
        services: dict[str, object | None],
        dependencies: tuple[DependencyHealth, ...] = (),
    ) -> ReadinessStatus:
        application_health = await self.check_application(repositories, services, dependencies)
        blocking = tuple(
            f"{item.name}: {item.message}"
            for group in (application_health.repositories, application_health.services, application_health.dependencies)
            for item in group
            if item.state == HealthState.UNHEALTHY
        )
        return ReadinessStatus(ready=not blocking, application_health=application_health, blocking_issues=blocking)


def _aggregate_state(
    repository_health: tuple[RepositoryHealth, ...],
    service_health: tuple[ServiceHealth, ...],
    dependencies: tuple[DependencyHealth, ...],
) -> HealthState:
    states = [item.state for item in (*repository_health, *service_health, *dependencies)]
    if not states:
        return HealthState.HEALTHY
    if any(state == HealthState.UNHEALTHY for state in states):
        return HealthState.UNHEALTHY
    if any(state == HealthState.DEGRADED for state in states):
        return HealthState.DEGRADED
    return HealthState.HEALTHY
