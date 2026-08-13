"""Tests for HealthCheckService: aggregation of repository/service health
into ApplicationHealth/ReadinessStatus. Repositories are simple fakes
here — the point under test is aggregation, not any real repository's own
`health_check()` implementation (already covered by that repository's own
tests)."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from app.operations.health.models import DependencyHealth, HealthState
from app.operations.health.service import HealthCheckService

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


class _FakeRepository:
    def __init__(self, reachable: bool) -> None:
        self._reachable = reachable

    async def health_check(self) -> bool:
        return self._reachable


class _SlowRepository:
    """Simulates a repository whose `health_check()` takes real time to
    fail (e.g. an unreachable Postgres connection attempt) — used to prove
    repositories are checked concurrently, not sequentially."""

    def __init__(self, delay_seconds: float) -> None:
        self._delay_seconds = delay_seconds

    async def health_check(self) -> bool:
        await asyncio.sleep(self._delay_seconds)
        return False


class _RaisingRepository:
    async def health_check(self) -> bool:
        raise RuntimeError("connection refused")


def _service() -> HealthCheckService:
    return HealthCheckService(now_fn=lambda: NOW)


# --- check_repositories -----------------------------------------------------------


async def test_check_repositories_reports_healthy_when_reachable() -> None:
    service = _service()
    result = await service.check_repositories({"risk": _FakeRepository(True)})

    assert result[0].state == HealthState.HEALTHY


async def test_check_repositories_reports_unhealthy_when_unreachable() -> None:
    service = _service()
    result = await service.check_repositories({"risk": _FakeRepository(False)})

    assert result[0].state == HealthState.UNHEALTHY


async def test_check_repositories_reports_unhealthy_for_none() -> None:
    service = _service()
    result = await service.check_repositories({"risk": None})

    assert result[0].state == HealthState.UNHEALTHY
    assert result[0].message == "not configured"


async def test_check_repositories_never_raises_when_health_check_raises() -> None:
    service = _service()
    result = await service.check_repositories({"risk": _RaisingRepository()})

    assert result[0].state == HealthState.UNHEALTHY
    assert "connection refused" in result[0].message


async def test_check_repositories_sorted_by_name() -> None:
    service = _service()
    result = await service.check_repositories({"z": _FakeRepository(True), "a": _FakeRepository(True)})

    assert [r.name for r in result] == ["a", "z"]


async def test_check_repositories_runs_concurrently_not_sequentially() -> None:
    """Regression test: N slow/unreachable repositories must not multiply
    total latency by N (a real-world case — an unreachable Postgres with
    no repository-level connect timeout configured). Bound generously
    (5x one delay, for 5 repositories) to stay robust on a slow CI
    runner while still failing clearly against the old O(N) behavior
    (5 repositories * 0.2s would take >=1.0s sequentially)."""
    service = _service()
    delay = 0.2
    repositories = {str(i): _SlowRepository(delay) for i in range(5)}

    started = time.monotonic()
    result = await service.check_repositories(repositories)
    elapsed = time.monotonic() - started

    assert len(result) == 5
    assert all(r.state == HealthState.UNHEALTHY for r in result)
    assert elapsed < delay * 5 * 0.5


# --- check_services -----------------------------------------------------------


def test_check_services_healthy_when_constructed() -> None:
    service = _service()
    result = service.check_services({"risk_service": object()})

    assert result[0].state == HealthState.HEALTHY


def test_check_services_unhealthy_when_none() -> None:
    service = _service()
    result = service.check_services({"risk_service": None})

    assert result[0].state == HealthState.UNHEALTHY


# --- check_application -----------------------------------------------------------


async def test_check_application_healthy_when_everything_healthy() -> None:
    service = _service()
    result = await service.check_application({"risk": _FakeRepository(True)}, {"risk_service": object()})

    assert result.state == HealthState.HEALTHY
    assert result.checked_at == NOW


async def test_check_application_unhealthy_when_any_repository_unhealthy() -> None:
    service = _service()
    result = await service.check_application({"risk": _FakeRepository(False)}, {"risk_service": object()})

    assert result.state == HealthState.UNHEALTHY


async def test_check_application_degraded_dependency_does_not_mask_as_healthy() -> None:
    service = _service()
    dependency = DependencyHealth(name="cache", state=HealthState.DEGRADED, message="slow")
    result = await service.check_application({}, {}, (dependency,))

    assert result.state == HealthState.DEGRADED


async def test_check_application_with_no_components_is_healthy() -> None:
    service = _service()
    result = await service.check_application({}, {})

    assert result.state == HealthState.HEALTHY
    assert result.summary == "no components checked"


async def test_check_application_summary_counts_healthy_components() -> None:
    service = _service()
    result = await service.check_application(
        {"a": _FakeRepository(True), "b": _FakeRepository(False)}, {"c": object()}
    )

    assert result.summary == "2/3 component(s) healthy"


# --- check_readiness -----------------------------------------------------------


async def test_check_readiness_ready_when_everything_healthy() -> None:
    service = _service()
    result = await service.check_readiness({"risk": _FakeRepository(True)}, {"risk_service": object()})

    assert result.ready is True
    assert result.blocking_issues == ()


async def test_check_readiness_not_ready_when_repository_unhealthy() -> None:
    service = _service()
    result = await service.check_readiness({"risk": _FakeRepository(False)}, {})

    assert result.ready is False
    assert len(result.blocking_issues) == 1
    assert "risk" in result.blocking_issues[0]


async def test_check_readiness_degraded_dependency_does_not_block() -> None:
    service = _service()
    dependency = DependencyHealth(name="cache", state=HealthState.DEGRADED, message="slow")
    result = await service.check_readiness({}, {}, (dependency,))

    assert result.ready is True
