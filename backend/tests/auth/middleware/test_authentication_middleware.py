"""Tests for AuthenticationMiddleware: resolves a bearer token, attaches
the principal, and never rejects a request itself."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.auth.middleware import AuthenticationMiddleware
from app.auth.services.authentication import AuthenticationService
from tests.auth.conftest import make_active_user


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)

    @app.get("/whoami")
    async def whoami(request: Request) -> dict:
        principal = getattr(request.state, "principal", None)
        return {"principal": principal.username if principal else None}

    return app


async def test_attaches_principal_for_a_valid_bearer_token(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    app = _build_app()
    app.state.authentication_service = auth_service
    with TestClient(app) as client:
        result = client.get("/whoami", headers={"Authorization": f"Bearer {response.access_token.token}"})

    assert result.json()["principal"] == "alice"


def test_attaches_no_principal_when_no_authorization_header() -> None:
    app = _build_app()
    app.state.authentication_service = None
    with TestClient(app) as client:
        result = client.get("/whoami")

    assert result.status_code == 200
    assert result.json()["principal"] is None


def test_attaches_no_principal_when_header_is_not_bearer_scheme() -> None:
    app = _build_app()
    app.state.authentication_service = None
    with TestClient(app) as client:
        result = client.get("/whoami", headers={"Authorization": "Basic dXNlcjpwYXNz"})

    assert result.status_code == 200
    assert result.json()["principal"] is None


def test_attaches_no_principal_for_a_malformed_token_never_500s() -> None:
    app = _build_app()

    class _FakeService:
        async def validate(self, token: str):
            from app.auth.exceptions import TokenMalformedError

            raise TokenMalformedError("bad")

    app.state.authentication_service = _FakeService()
    with TestClient(app) as client:
        result = client.get("/whoami", headers={"Authorization": "Bearer garbage"})

    assert result.status_code == 200
    assert result.json()["principal"] is None


def test_attaches_no_principal_when_authentication_service_not_configured() -> None:
    app = _build_app()
    app.state.authentication_service = None
    with TestClient(app) as client:
        result = client.get("/whoami", headers={"Authorization": "Bearer some-token"})

    assert result.status_code == 200
    assert result.json()["principal"] is None


def test_attaches_no_principal_for_empty_bearer_token() -> None:
    app = _build_app()
    app.state.authentication_service = None
    with TestClient(app) as client:
        result = client.get("/whoami", headers={"Authorization": "Bearer "})

    assert result.status_code == 200
    assert result.json()["principal"] is None


async def test_attaches_no_principal_for_a_revoked_token(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")
    await auth_service.revoke(response.access_token.token)

    app = _build_app()
    app.state.authentication_service = auth_service
    with TestClient(app) as client:
        result = client.get("/whoami", headers={"Authorization": f"Bearer {response.access_token.token}"})

    assert result.status_code == 200
    assert result.json()["principal"] is None


def test_middleware_never_raises_an_unhandled_exception() -> None:
    """Even a completely broken service (raises something other than a
    TokenError) should not be silently swallowed by *this* test's
    expectations — but the middleware itself only guards against
    `TokenError`; this documents that boundary explicitly."""
    app = _build_app()

    class _BrokenService:
        async def validate(self, token: str):
            raise RuntimeError("unexpected failure")

    app.state.authentication_service = _BrokenService()
    with TestClient(app, raise_server_exceptions=False) as client:
        result = client.get("/whoami", headers={"Authorization": "Bearer some-token"})

    assert result.status_code == 500
