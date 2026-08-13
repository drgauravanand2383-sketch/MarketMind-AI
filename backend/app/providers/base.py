"""Abstract contract every external data provider must implement.

BaseProvider defines the framework-level contract for pluggable data
providers (RSS, NSE, BSE, NewsAPI, Moneycontrol, Reuters, Bloomberg, Yahoo
Finance, and others). This module contains no provider-specific logic, no
HTTP requests, and no scraping — only the abstraction every provider
implementation will conform to.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.providers.models import ProviderConfig, ProviderResult

__all__ = ["BaseProvider"]


class BaseProvider(ABC):
    """Abstract base class every external data provider must implement.

    A provider is the framework-level unit of integration with one external
    data source. Concrete providers (RSS, NSE, NewsAPI, etc.) implement
    `fetch` and `health_check`; BaseProvider itself performs no I/O and
    contains no source-specific behavior.
    """

    def __init__(self, config: ProviderConfig) -> None:
        """Initialize the provider with its configuration.

        Args:
            config: The provider's configuration, injected at construction.
        """
        self._config = config

    @property
    def config(self) -> ProviderConfig:
        """This provider's configuration."""
        return self._config

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """The unique identifier this provider is registered under (e.g. 'rss')."""
        raise NotImplementedError

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """The human-readable name of this provider (e.g. 'RSS Feed Provider')."""
        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        """The version of this provider implementation."""
        raise NotImplementedError

    @abstractmethod
    async def fetch(self, **kwargs: object) -> ProviderResult:
        """Fetch raw data from this provider's external source.

        Args:
            **kwargs: Provider-specific fetch parameters, defined by each
                concrete provider.

        Returns:
            A ProviderResult wrapping whatever this provider fetched.
        """
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether this provider is configured and reachable."""
        raise NotImplementedError
