"""Tests for app.auth.dependencies.providers: resolves already-configured
components from app.state, 503 when missing."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth.dependencies.providers import (
    get_authentication_service,
    get_authorization_service,
    get_current_principal,
    get_policy_evaluator,
)


class _FakeAppState:
    def __init__(self, **attrs: object) -> None:
        for key, value in attrs.items():
            setattr(self, key, value)


class _FakeApp:
    def __init__(self, **attrs: object) -> None:
        self.state = _FakeAppState(**attrs)


class _FakeRequestState:
    def __init__(self, **attrs: object) -> None:
        for key, value in attrs.items():
            setattr(self, key, value)


class _FakeRequest:
    def __init__(self, app_attrs: dict | None = None, state_attrs: dict | None = None) -> None:
        self.app = _FakeApp(**(app_attrs or {}))
        self.state = _FakeRequestState(**(state_attrs or {}))


def test_get_authentication_service_returns_configured_service() -> None:
    sentinel = object()
    request = _FakeRequest({"authentication_service": sentinel})

    assert get_authentication_service(request) is sentinel  # type: ignore[arg-type]


def test_get_authentication_service_raises_503_when_missing() -> None:
    request = _FakeRequest()
    with pytest.raises(HTTPException) as exc_info:
        get_authentication_service(request)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 503


def test_get_authorization_service_raises_503_when_missing() -> None:
    request = _FakeRequest()
    with pytest.raises(HTTPException):
        get_authorization_service(request)  # type: ignore[arg-type]


def test_get_policy_evaluator_raises_503_when_missing() -> None:
    request = _FakeRequest()
    with pytest.raises(HTTPException):
        get_policy_evaluator(request)  # type: ignore[arg-type]


def test_get_current_principal_returns_none_when_absent() -> None:
    request = _FakeRequest()
    assert get_current_principal(request) is None  # type: ignore[arg-type]


def test_get_current_principal_returns_the_attached_principal() -> None:
    sentinel = object()
    request = _FakeRequest(state_attrs={"principal": sentinel})
    assert get_current_principal(request) is sentinel  # type: ignore[arg-type]


def test_get_current_principal_never_raises() -> None:
    """Unlike every other provider here, a missing principal is a normal
    outcome (unauthenticated request), not a misconfiguration — no
    HTTPException path exists for this one."""
    request = _FakeRequest()
    result = get_current_principal(request)  # type: ignore[arg-type]
    assert result is None
