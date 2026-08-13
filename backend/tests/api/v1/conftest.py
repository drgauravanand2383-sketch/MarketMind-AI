"""Shared fixtures for `/api/v1` tests.

`client` runs the *real* application (`app.main.create_app()`, full
bootstrap via the real lifespan) — module-scoped so the relatively
expensive bootstrap sequence (APScheduler start/stop, every
`build_*_repository`/`build_*_service` call) runs once per test module,
not once per test. `get_repositories_map` is overridden with fast, fake,
always-reachable repositories via `app.dependency_overrides` — the exact
mechanism `app.api.intelligence.dependencies`'s own docstring already
documents as this codebase's established test-substitution pattern.
Without this override, every `/health`/`/ready` call would invoke all ten
real repositories' own `health_check()` against an unreachable local
PostgreSQL server; each one blocks for several seconds on asyncpg's
connection attempt, making the endpoint (and therefore the whole test
suite) unusably slow. `test_health.py` covers the genuinely-unhealthy
path separately, with its own isolated fake repositories.

`bare_client` wires only the `/api/v1` router, middleware, and exception
handlers onto a fresh `FastAPI()` with no bootstrap at all — `app.state`
is empty. Used to test the 503-on-missing-dependency path and
middleware/exception-handler behavior in isolation from the real backend.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.v1.dependencies.state import REPOSITORY_NAMES, get_repositories_map
from app.api.v1.exception_handlers import register_exception_handlers
from app.api.v1.middleware import register_middleware
from app.api.v1.router import router as v1_router
from app.main import create_app


class FakeHealthyRepository:
    """A minimal stand-in for any `Base*Repository` — instant, always-reachable."""

    async def health_check(self) -> bool:
        return True


def _fast_repositories_map(request: Request) -> dict[str, object]:
    return {name: FakeHealthyRepository() for name in REPOSITORY_NAMES}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_repositories_map] = _fast_repositories_map
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def bare_app() -> FastAPI:
    app = FastAPI()
    app.include_router(v1_router, prefix="/api/v1")
    register_middleware(app)
    register_exception_handlers(app)
    return app


@pytest.fixture
def bare_client(bare_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(bare_app) as test_client:
        yield test_client
