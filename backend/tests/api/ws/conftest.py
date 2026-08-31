"""Shared fixtures for `app.api.ws` tests.

A self-contained app (real `AuthenticationMiddleware`-equivalent — the
`/ws` route authenticates by hand, see `app.api.ws.dependencies.auth` —
backed by real `AuthenticationService`/`AuthorizationService` on
in-memory SQLite) mounting only the `/ws` router, plus a real
`ConnectionManager`/`EventPublisher` pair. Mirrors the composition style
`tests/api/v1/watchlists/conftest.py` already established.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ws import router as ws_router
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.publishers.event_publisher import EventPublisher
from app.auth.policies import PolicyEvaluator
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService
from tests.api.v1._auth_fixtures import (  # noqa: F401 - re-exported as fixtures
    auth_repository,
    auth_service,
    authorization_service,
    make_authenticated_headers,
)

ALL_WS_PERMISSIONS = (
    "alerts:read",
    "backtest:read",
    "portfolio:read",
    "strategy:read",
    "explainability:read",
    "global_markets:read",
)


@pytest.fixture
def connection_manager() -> ConnectionManager:
    return ConnectionManager()


@pytest.fixture
def event_publisher(connection_manager: ConnectionManager) -> EventPublisher:
    return EventPublisher(connection_manager)


@pytest.fixture
def app(
    auth_service: AuthenticationService,
    authorization_service: AuthorizationService,
    connection_manager: ConnectionManager,
    event_publisher: EventPublisher,
) -> FastAPI:
    application = FastAPI()
    application.state.authentication_service = auth_service
    application.state.authorization_service = authorization_service
    application.state.policy_evaluator = PolicyEvaluator()
    application.state.connection_manager = connection_manager
    application.state.event_publisher = event_publisher
    application.include_router(ws_router)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def token(auth_repository, auth_service) -> str:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=ALL_WS_PERMISSIONS)
    return headers["Authorization"].removeprefix("Bearer ")
