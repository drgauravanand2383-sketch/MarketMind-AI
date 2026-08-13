"""Tests for require_policy(): the HTTP bridge between pure Policy
objects and FastAPI route protection — 401 (unauthenticated), 403
(authenticated but denied), and pass-through (authorized) paths."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies.policy_guard import require_policy
from app.auth.policies import PolicyEvaluator, RequireRole
from app.auth.services.authentication import AuthenticationService
from tests.auth.conftest import make_active_user, make_role


def _build_app(auth_service: AuthenticationService) -> FastAPI:
    from app.auth.middleware import AuthenticationMiddleware

    app = FastAPI()
    app.state.authentication_service = auth_service
    app.state.policy_evaluator = PolicyEvaluator()
    app.add_middleware(AuthenticationMiddleware)

    @app.get("/admin")
    async def admin_only(principal=Depends(require_policy(RequireRole("ADMIN")))):
        return {"user": principal.username}

    return app


async def test_require_policy_returns_401_without_a_token(
    auth_service: AuthenticationService, repository,
) -> None:
    app = _build_app(auth_service)
    with TestClient(app) as client:
        response = client.get("/admin")

    assert response.status_code == 401


async def test_require_policy_returns_403_when_role_missing(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_role(repository, "r1", "VIEWER")
    await make_active_user(repository, auth_service, roles=("r1",))
    login = await auth_service.authenticate("alice", "password123")

    app = _build_app(auth_service)
    with TestClient(app) as client:
        response = client.get("/admin", headers={"Authorization": f"Bearer {login.access_token.token}"})

    assert response.status_code == 403
    assert "RequireRole" in response.json()["detail"]


async def test_require_policy_returns_200_when_role_present(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_role(repository, "r1", "ADMIN")
    await make_active_user(repository, auth_service, roles=("r1",))
    login = await auth_service.authenticate("alice", "password123")

    app = _build_app(auth_service)
    with TestClient(app) as client:
        response = client.get("/admin", headers={"Authorization": f"Bearer {login.access_token.token}"})

    assert response.status_code == 200
    assert response.json()["user"] == "alice"


async def test_require_policy_returns_401_for_an_expired_token(
    auth_service: AuthenticationService, repository, clock,
) -> None:
    from datetime import timedelta

    await make_role(repository, "r1", "ADMIN")
    await make_active_user(repository, auth_service, roles=("r1",))
    login = await auth_service.authenticate("alice", "password123")
    clock.advance(timedelta(hours=1))

    app = _build_app(auth_service)
    with TestClient(app) as client:
        response = client.get("/admin", headers={"Authorization": f"Bearer {login.access_token.token}"})

    assert response.status_code == 401
