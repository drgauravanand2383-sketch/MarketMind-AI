"""Tests for Request ID, Timing, structured logging integration, CORS,
and compression middleware."""

from __future__ import annotations

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.middleware.request_id import REQUEST_ID_HEADER
from app.api.v1.middleware.timing import PROCESS_TIME_HEADER


# --- Request ID -----------------------------------------------------------


def test_response_includes_a_request_id_header(client: TestClient) -> None:
    response = client.get("/api/v1/version")

    assert REQUEST_ID_HEADER in response.headers
    assert response.headers[REQUEST_ID_HEADER]


def test_request_id_is_echoed_back_when_supplied(client: TestClient) -> None:
    response = client.get("/api/v1/version", headers={REQUEST_ID_HEADER: "caller-supplied-id"})

    assert response.headers[REQUEST_ID_HEADER] == "caller-supplied-id"


def test_request_id_is_generated_when_not_supplied(client: TestClient) -> None:
    response = client.get("/api/v1/version")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", request_id)


def test_request_id_matches_the_response_body_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/version", headers={REQUEST_ID_HEADER: "match-me"})

    assert response.json()["meta"]["request_id"] == "match-me"


def test_each_request_gets_a_distinct_generated_id(client: TestClient) -> None:
    first = client.get("/api/v1/version").headers[REQUEST_ID_HEADER]
    second = client.get("/api/v1/version").headers[REQUEST_ID_HEADER]

    assert first != second


# --- Timing -----------------------------------------------------------


def test_response_includes_a_process_time_header(client: TestClient) -> None:
    response = client.get("/api/v1/version")

    assert PROCESS_TIME_HEADER in response.headers
    assert float(response.headers[PROCESS_TIME_HEADER]) >= 0


def test_process_time_records_through_the_profiler(client: TestClient) -> None:
    app = client.app
    profiler = app.state.profiler

    before = profiler.count("http.GET./api/v1/version")
    client.get("/api/v1/version")
    after = profiler.count("http.GET./api/v1/version")

    assert after == before + 1


def test_process_time_records_through_the_metrics_recorder(client: TestClient) -> None:
    from app.operations.metrics.models import METRIC_SERVICE_CALLS

    app = client.app
    recorder = app.state.metrics_recorder

    before = recorder.count(METRIC_SERVICE_CALLS)
    client.get("/api/v1/version")
    after = recorder.count(METRIC_SERVICE_CALLS)

    assert after == before + 1


# --- Structured logging integration -----------------------------------------------------------


def test_middleware_does_not_raise_without_a_structured_logger(bare_client: TestClient) -> None:
    """`bare_client` has no `app.state.structured_logger` configured —
    `RequestLoggingMiddleware` must degrade to a no-op, not raise."""
    response = bare_client.get("/api/v1/version")

    assert response.status_code in (200, 503)  # reaches a real handler either way, no 500


# --- CORS -----------------------------------------------------------


def test_cors_preflight_is_handled(client: TestClient) -> None:
    response = client.options(
        "/api/v1/version",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_headers_present_on_actual_request(client: TestClient) -> None:
    response = client.get("/api/v1/version", headers={"Origin": "http://localhost:3000"})

    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


# --- Compression -----------------------------------------------------------


def test_gzip_middleware_compresses_large_responses(client: TestClient) -> None:
    """`/api/v1/health`'s payload (every repository + service entry) is
    comfortably above the configured minimum compression size."""
    response = client.get("/api/v1/health", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert response.json()["data"]  # still decodes correctly


# --- Security headers (Sprint 60) -----------------------------------------------------------


def test_always_on_security_headers_are_present(client: TestClient) -> None:
    response = client.get("/api/v1/version")

    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert response.headers.get("Permissions-Policy") == "geolocation=(), microphone=(), camera=()"


def test_csp_and_hsts_are_absent_by_default(client: TestClient) -> None:
    """Both default to disabled — a blind CSP would break /docs, and HSTS
    is wrong to send over plain HTTP ("do not assume HTTPS in development")."""
    response = client.get("/api/v1/version")

    assert "Content-Security-Policy" not in response.headers
    assert "Strict-Transport-Security" not in response.headers


def test_security_headers_present_even_on_error_responses(client: TestClient) -> None:
    response = client.get("/api/v1/this-route-does-not-exist")

    assert response.status_code == 404
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


def test_csp_is_sent_when_configured() -> None:
    from fastapi import FastAPI

    from app.api.v1.middleware.security_headers import SecurityHeadersMiddleware
    from app.config.models import SecurityHeadersSettings

    app = FastAPI()
    app.add_middleware(
        SecurityHeadersMiddleware,
        settings=SecurityHeadersSettings(_env_file=None, content_security_policy="default-src 'self'"),
    )

    @app.get("/probe")
    async def probe() -> dict:
        return {"ok": True}

    with TestClient(app) as test_client:
        response = test_client.get("/probe")

    assert response.headers.get("Content-Security-Policy") == "default-src 'self'"


def test_hsts_is_sent_when_enabled() -> None:
    from fastapi import FastAPI

    from app.api.v1.middleware.security_headers import SecurityHeadersMiddleware
    from app.config.models import SecurityHeadersSettings

    app = FastAPI()
    app.add_middleware(
        SecurityHeadersMiddleware,
        settings=SecurityHeadersSettings(
            _env_file=None, hsts_enabled=True, hsts_max_age_seconds=600, hsts_include_subdomains=True
        ),
    )

    @app.get("/probe")
    async def probe() -> dict:
        return {"ok": True}

    with TestClient(app) as test_client:
        response = test_client.get("/probe")

    assert response.headers.get("Strict-Transport-Security") == "max-age=600; includeSubDomains"
