"""Tests for API-layer startup: the real `app.main.create_app()` +
lifespan sequence populates `app.state` with every component `/api/v1`
depends on, and middleware/exception handlers are actually registered —
not just that the underlying bootstrap sequence works (already covered
by `tests/lifecycle/`, Sprint 54)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.v1.middleware.logging import RequestLoggingMiddleware
from app.api.v1.middleware.request_id import RequestIDMiddleware
from app.api.v1.middleware.timing import TimingMiddleware


def test_create_app_returns_a_working_application() -> None:
    from app.main import create_app

    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/v1/version")
        assert response.status_code == 200


def test_lifespan_populates_every_component_v1_endpoints_depend_on(client: TestClient) -> None:
    app = client.app

    assert app.state.health_check_service is not None
    assert app.state.settings is not None
    assert app.state.structured_logger is not None
    assert app.state.metrics_recorder is not None
    assert app.state.profiler is not None


def test_v1_router_is_mounted_under_the_configured_prefix(client: TestClient) -> None:
    from app.config.models import APISettings

    prefix = APISettings().v1_prefix
    response = client.get(f"{prefix}/version")

    assert response.status_code == 200


def test_all_three_custom_middleware_are_registered() -> None:
    from app.main import create_app

    app = create_app()
    middleware_classes = {m.cls for m in app.user_middleware}

    assert RequestIDMiddleware in middleware_classes
    assert TimingMiddleware in middleware_classes
    assert RequestLoggingMiddleware in middleware_classes


def test_cors_and_gzip_middleware_are_registered() -> None:
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.middleware.gzip import GZipMiddleware

    from app.main import create_app

    app = create_app()
    middleware_classes = {m.cls for m in app.user_middleware}

    assert CORSMiddleware in middleware_classes
    assert GZipMiddleware in middleware_classes


def test_authentication_middleware_is_registered() -> None:
    """Sprint 56 adds `AuthenticationMiddleware` (resolves a bearer token
    and attaches a principal — never rejects a request itself; actual
    authorization stays policy-based). Superseded a Sprint 55 negative
    check that no auth middleware existed yet."""
    from app.auth.middleware import AuthenticationMiddleware
    from app.main import create_app

    app = create_app()
    middleware_classes = {m.cls for m in app.user_middleware}

    assert AuthenticationMiddleware in middleware_classes


def test_exception_handlers_are_registered() -> None:
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from app.main import create_app

    app = create_app()

    assert StarletteHTTPException in app.exception_handlers
    assert RequestValidationError in app.exception_handlers
    assert Exception in app.exception_handlers


def test_shutdown_completes_without_error() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app):
        pass  # lifespan startup + shutdown both run within this block
