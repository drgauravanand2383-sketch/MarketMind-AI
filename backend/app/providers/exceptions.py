"""Exception hierarchy for the provider framework.

All provider-related errors derive from ProviderError, giving calling code
a single type to catch broadly while still allowing specific handling for
configuration, connection, timeout, authentication, rate-limit, response,
and registry errors. No provider-specific error types are defined here.
"""

from __future__ import annotations

__all__ = [
    "ProviderError",
    "ProviderConfigurationError",
    "ProviderConnectionError",
    "ProviderTimeoutError",
    "ProviderAuthenticationError",
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ProviderNoDataError",
    "ProviderNotRegisteredError",
    "ProviderAlreadyRegisteredError",
]


class ProviderError(Exception):
    """Base class for all provider framework errors."""

    def __init__(self, message: str, *, provider_id: str | None = None) -> None:
        self.provider_id = provider_id
        super().__init__(message)


class ProviderConfigurationError(ProviderError):
    """Raised when a provider's configuration is invalid or incomplete."""


class ProviderConnectionError(ProviderError):
    """Raised when a provider cannot reach its external source."""


class ProviderTimeoutError(ProviderConnectionError):
    """Raised when a provider's request exceeds its configured timeout."""


class ProviderAuthenticationError(ProviderError):
    """Raised when a provider fails to authenticate with its external source."""


class ProviderRateLimitError(ProviderError):
    """Raised when a provider is rate-limited by its external source."""


class ProviderResponseError(ProviderError):
    """Raised when a provider receives a malformed or unexpected response."""


class ProviderNoDataError(ProviderError):
    """Raised when a provider was reached and responded successfully, but
    has no data at all for the requested identifier (e.g. an unknown or
    delisted ticker) — distinct from `ProviderResponseError` (the
    response itself was malformed/unparseable) and from a connection or
    timeout failure (Milestone 13 §7: "no data exists" must never be
    confused with "provider failed")."""


class ProviderNotRegisteredError(ProviderError):
    """Raised when the registry is asked for a provider_id that isn't registered."""

    def __init__(self, provider_id: str) -> None:
        super().__init__(
            f"No provider registered under id {provider_id!r}", provider_id=provider_id
        )


class ProviderAlreadyRegisteredError(ProviderError):
    """Raised when attempting to register a provider_id that is already registered."""

    def __init__(self, provider_id: str) -> None:
        super().__init__(
            f"A provider is already registered under id {provider_id!r}",
            provider_id=provider_id,
        )
