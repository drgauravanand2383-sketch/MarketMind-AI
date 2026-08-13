"""Performance benchmarks (Sprint 60) — measure only, per this sprint's
own constraint ("Measure only. Do not optimize business logic."). Every
assertion here is a generous upper bound meant to catch a catastrophic
regression (e.g. an accidental N+1, a blocking call on the hot path),
never a strict SLA — this sandboxed environment's hardware is not
representative of a production deployment, so thresholds are deliberately
loose. Each test prints its measured timing for a human reviewing
results; run with `-s` to see them.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.ws.connection_manager.manager import ConnectionManager
from app.auth.middleware import AuthenticationMiddleware
from app.auth.models.authentication import AuthenticatedPrincipal
from app.auth.policies import PolicyEvaluator, RequirePermission
from app.recommendations.engine import PortfolioRecommendationService
from app.recommendations.models import CandidateEvidence
from app.repositories.recommendations.postgres.models import Base as RecommendationBase
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository
from app.repositories.watchlist.postgres.models import Base as WatchlistBase
from app.repositories.watchlist.postgres.repository import PostgresWatchlistRepository
from app.watchlist.service import WatchlistService
from tests.api.ws.fakes import FakeWebSocket

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)
ITERATIONS = 50


def _report(name: str, total_seconds: float, iterations: int) -> None:
    average_ms = (total_seconds / iterations) * 1000
    print(f"\n[benchmark] {name}: {iterations} iterations, {average_ms:.3f} ms/iteration, {total_seconds:.3f}s total")


# --------------------------------------------------------------------------
# API startup
# --------------------------------------------------------------------------


def test_benchmark_api_startup() -> None:
    from app.main import create_app

    started_at = time.perf_counter()
    app = create_app()
    with TestClient(app):
        pass  # entering/exiting runs the real lifespan bootstrap/shutdown
    duration = time.perf_counter() - started_at

    _report("api_startup_and_shutdown", duration, 1)
    assert duration < 30.0  # generous: real bootstrap includes several `create_async_engine` calls


# --------------------------------------------------------------------------
# Health endpoint
# --------------------------------------------------------------------------


def test_benchmark_health_endpoint(client: TestClient) -> None:
    """Uses the shared, module-scoped `client` fixture — real
    `HealthCheckService`, fast fake repositories (see
    `tests/api/v1/conftest.py`'s own docstring for why: real repositories'
    `health_check()` would otherwise block on an unreachable database)."""
    client.get("/api/v1/health")  # warm up (first call pays import/JIT-ish costs)

    started_at = time.perf_counter()
    for _ in range(ITERATIONS):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
    duration = time.perf_counter() - started_at

    _report("health_endpoint", duration, ITERATIONS)
    assert duration / ITERATIONS < 0.5


# --------------------------------------------------------------------------
# Authentication middleware overhead
# --------------------------------------------------------------------------


def test_benchmark_authentication_middleware_overhead() -> None:
    """`AuthenticationMiddleware` with no `authentication_service`
    configured — isolates the middleware's own per-request overhead from
    any real token-verification cost (already benchmarked separately by
    the auth framework's own test suite)."""
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)

    @app.get("/probe")
    async def probe() -> dict:
        return {"ok": True}

    with TestClient(app) as client:
        client.get("/probe")  # warm up

        started_at = time.perf_counter()
        for _ in range(ITERATIONS):
            client.get("/probe")
        duration = time.perf_counter() - started_at

    _report("authentication_middleware", duration, ITERATIONS)
    assert duration / ITERATIONS < 0.5


# --------------------------------------------------------------------------
# Authorization policy evaluation
# --------------------------------------------------------------------------


def test_benchmark_policy_evaluation() -> None:
    evaluator = PolicyEvaluator()
    principal = AuthenticatedPrincipal(
        user_id="u1", username="bench", roles=("READER",), permissions=("watchlist:read",), token_id="t1"
    )
    policy = RequirePermission("watchlist:read")

    started_at = time.perf_counter()
    for _ in range(ITERATIONS * 100):  # pure in-memory, cheap enough for many more iterations
        evaluator.evaluate(policy, principal)
    duration = time.perf_counter() - started_at

    _report("policy_evaluation", duration, ITERATIONS * 100)
    assert duration / (ITERATIONS * 100) < 0.01


# --------------------------------------------------------------------------
# Repository access
# --------------------------------------------------------------------------


async def test_benchmark_repository_access() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(WatchlistBase.metadata.create_all)
    service = WatchlistService(PostgresWatchlistRepository(async_sessionmaker(engine, expire_on_commit=False)))

    watchlist = await service.create_watchlist("Benchmark Watchlist")

    started_at = time.perf_counter()
    for _ in range(ITERATIONS):
        await service.get_watchlist(watchlist.id)
    duration = time.perf_counter() - started_at

    _report("repository_access_get_watchlist", duration, ITERATIONS)
    assert duration / ITERATIONS < 0.5


# --------------------------------------------------------------------------
# Recommendation endpoint (service-level — the router itself is a thin
# wrapper already covered by the contract/integration test suites)
# --------------------------------------------------------------------------


async def test_benchmark_recommendation_generation() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(RecommendationBase.metadata.create_all)
    service = PortfolioRecommendationService(
        PostgresRecommendationRepository(async_sessionmaker(engine, expire_on_commit=False)), now_fn=lambda: NOW
    )
    evidence = [CandidateEvidence(ticker="AAPL", sector="Technology")]

    started_at = time.perf_counter()
    for i in range(ITERATIONS):
        request = await service.create_request(f"bench-{i}", watchlist_ids=("w1",))
        await service.generate_recommendations(request, evidence)
    duration = time.perf_counter() - started_at

    _report("recommendation_generation", duration, ITERATIONS)
    assert duration / ITERATIONS < 0.5


# --------------------------------------------------------------------------
# WebSocket connection establishment
# --------------------------------------------------------------------------


async def test_benchmark_websocket_connection_establishment() -> None:
    manager = ConnectionManager()
    principal = AuthenticatedPrincipal(user_id="u1", username="bench", roles=(), permissions=(), token_id="t1")

    started_at = time.perf_counter()
    connection_ids = []
    for _ in range(ITERATIONS):
        connection_ids.append(await manager.connect(FakeWebSocket(), principal))
    duration = time.perf_counter() - started_at

    _report("websocket_connect", duration, ITERATIONS)
    assert manager.connection_count == ITERATIONS
    assert duration / ITERATIONS < 0.1

    for connection_id in connection_ids:
        manager.disconnect(connection_id)
