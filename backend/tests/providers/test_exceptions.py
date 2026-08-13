"""Unit tests for the provider exception hierarchy."""

from __future__ import annotations

from app.providers.exceptions import (
    ProviderAlreadyRegisteredError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderError,
    ProviderNotRegisteredError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)


def test_all_provider_errors_derive_from_provider_error() -> None:
    for exc_cls in (
        ProviderConfigurationError,
        ProviderConnectionError,
        ProviderTimeoutError,
        ProviderAuthenticationError,
        ProviderRateLimitError,
        ProviderResponseError,
        ProviderNotRegisteredError,
        ProviderAlreadyRegisteredError,
    ):
        assert issubclass(exc_cls, ProviderError)


def test_timeout_error_is_a_connection_error() -> None:
    assert issubclass(ProviderTimeoutError, ProviderConnectionError)


def test_provider_error_carries_optional_provider_id() -> None:
    error = ProviderError("something went wrong", provider_id="rss")
    assert error.provider_id == "rss"
    assert str(error) == "something went wrong"


def test_not_registered_error_carries_provider_id() -> None:
    error = ProviderNotRegisteredError("nse")
    assert error.provider_id == "nse"
    assert "nse" in str(error)


def test_already_registered_error_carries_provider_id() -> None:
    error = ProviderAlreadyRegisteredError("rss")
    assert error.provider_id == "rss"
    assert "rss" in str(error)
