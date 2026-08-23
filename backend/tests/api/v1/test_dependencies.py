"""Tests for `app.api.v1.dependencies.state`: resolves already-configured
components from `app.state`, 503 when missing — no component is ever
constructed here."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1.dependencies.state import (
    REPOSITORY_NAMES,
    SERVICE_NAMES,
    get_app_settings,
    get_configuration_validation_service,
    get_health_check_service,
    get_repositories_map,
    get_services_map,
    get_startup_validation_service,
)


class _FakeAppState:
    def __init__(self, **attrs: object) -> None:
        for key, value in attrs.items():
            setattr(self, key, value)


class _FakeApp:
    def __init__(self, **attrs: object) -> None:
        self.state = _FakeAppState(**attrs)


class _FakeRequest:
    def __init__(self, **attrs: object) -> None:
        self.app = _FakeApp(**attrs)


def test_repository_names_matches_bootstrap_app_state_attributes() -> None:
    assert len(REPOSITORY_NAMES) == 10
    assert "alert_rule_repository" in REPOSITORY_NAMES
    assert "alert_repository" in REPOSITORY_NAMES


def test_service_names_matches_bootstrap_app_state_attributes() -> None:
    assert len(SERVICE_NAMES) == 11
    assert "market_data_provider" in SERVICE_NAMES


def test_get_app_settings_returns_configured_settings() -> None:
    sentinel = object()
    request = _FakeRequest(settings=sentinel)

    assert get_app_settings(request) is sentinel  # type: ignore[arg-type]


def test_get_app_settings_raises_503_when_missing() -> None:
    request = _FakeRequest()

    with pytest.raises(HTTPException) as exc_info:
        get_app_settings(request)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 503


def test_get_health_check_service_raises_503_when_missing() -> None:
    request = _FakeRequest()

    with pytest.raises(HTTPException) as exc_info:
        get_health_check_service(request)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 503


def test_get_configuration_validation_service_raises_503_when_missing() -> None:
    request = _FakeRequest()

    with pytest.raises(HTTPException):
        get_configuration_validation_service(request)  # type: ignore[arg-type]


def test_get_startup_validation_service_raises_503_when_missing() -> None:
    request = _FakeRequest()

    with pytest.raises(HTTPException):
        get_startup_validation_service(request)  # type: ignore[arg-type]


def test_get_repositories_map_returns_none_for_every_missing_repository() -> None:
    request = _FakeRequest()

    result = get_repositories_map(request)  # type: ignore[arg-type]

    assert set(result.keys()) == set(REPOSITORY_NAMES)
    assert all(value is None for value in result.values())


def test_get_repositories_map_returns_configured_repository() -> None:
    sentinel = object()
    request = _FakeRequest(risk_repository=sentinel)

    result = get_repositories_map(request)  # type: ignore[arg-type]

    assert result["risk_repository"] is sentinel
    assert result["watchlist_repository"] is None


def test_get_services_map_returns_none_for_every_missing_service() -> None:
    request = _FakeRequest()

    result = get_services_map(request)  # type: ignore[arg-type]

    assert set(result.keys()) == set(SERVICE_NAMES)
    assert all(value is None for value in result.values())


def test_get_services_map_returns_configured_service() -> None:
    sentinel = object()
    request = _FakeRequest(risk_service=sentinel)

    result = get_services_map(request)  # type: ignore[arg-type]

    assert result["risk_service"] is sentinel
