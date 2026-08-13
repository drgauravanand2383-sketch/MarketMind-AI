"""End-to-end tests for the Auth API (`/api/v1/auth`) — the first REST
exposure of `AuthenticationService` (Sprint 56), built for the frontend's
Milestone 1.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.models.user import UserStatus
from app.auth.repositories.postgres.repository import PostgresAuthRepository
from app.auth.services.authentication import AuthenticationService


async def _make_active_user(
    auth_repository: PostgresAuthRepository,
    auth_service: AuthenticationService,
    *,
    username: str = "alice",
    password: str = "password123",
) -> None:
    user = await auth_service.register(username, f"{username}@example.com", password)
    await auth_repository.update_user(user.model_copy(update={"status": UserStatus.ACTIVE}))


async def test_login_with_correct_credentials_returns_tokens_and_user(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    await _make_active_user(auth_repository, auth_service)

    response = client.post("/api/v1/auth/login", json={"username": "alice", "password": "password123"})

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["access_token"]["token"]
    assert data["refresh_token"]["token"]
    assert data["user"]["username"] == "alice"


async def test_login_with_wrong_password_returns_401(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    await _make_active_user(auth_repository, auth_service)

    response = client.post("/api/v1/auth/login", json={"username": "alice", "password": "wrong-password"})

    assert response.status_code == 401


def test_login_with_unknown_username_returns_401(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "password123"})
    assert response.status_code == 401


async def test_login_with_inactive_user_returns_401(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    await auth_service.register("bob", "bob@example.com", "password123")  # stays PENDING, never activated

    response = client.post("/api/v1/auth/login", json={"username": "bob", "password": "password123"})

    assert response.status_code == 401


def test_login_rejects_unknown_fields(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "password123", "bogus": True}
    )
    assert response.status_code == 422


async def test_refresh_with_valid_token_returns_new_tokens(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    await _make_active_user(auth_repository, auth_service)
    login_response = client.post("/api/v1/auth/login", json={"username": "alice", "password": "password123"})
    refresh_token = login_response.json()["data"]["refresh_token"]["token"]

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 201
    assert response.json()["data"]["access_token"]["token"]


def test_refresh_with_garbage_token_returns_401(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401


async def test_refresh_with_an_access_token_returns_401(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    """An access token presented where a refresh token is expected —
    `TokenTypeMismatchError`, a `TokenError` subclass."""
    await _make_active_user(auth_repository, auth_service)
    login_response = client.post("/api/v1/auth/login", json={"username": "alice", "password": "password123"})
    access_token = login_response.json()["data"]["access_token"]["token"]

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401


async def test_logout_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout", json={"refresh_token": "whatever"})
    assert response.status_code == 401


async def test_logout_revokes_the_refresh_token(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    await _make_active_user(auth_repository, auth_service)
    login_response = client.post("/api/v1/auth/login", json={"username": "alice", "password": "password123"})
    tokens = login_response.json()["data"]
    access_token = tokens["access_token"]["token"]
    refresh_token = tokens["refresh_token"]["token"]

    logout_response = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_response.status_code == 204

    refresh_after_logout = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_after_logout.status_code == 401
