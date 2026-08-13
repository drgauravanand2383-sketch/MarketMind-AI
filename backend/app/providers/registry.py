"""Plugin registry for provider implementations.

ProviderRegistry maps provider IDs (e.g. "rss", "nse", "newsapi") to
BaseProvider subclasses, and constructs configured instances on demand. It
performs no I/O and contains no provider-specific logic — registration and
lookup only.
"""

from __future__ import annotations

from collections.abc import Callable

from app.providers.base import BaseProvider
from app.providers.exceptions import ProviderAlreadyRegisteredError, ProviderNotRegisteredError
from app.providers.models import ProviderConfig

__all__ = ["ProviderRegistry"]


class ProviderRegistry:
    """A registry of provider classes, keyed by provider_id.

    Supports both direct registration (`registry.register("rss", RSSProvider)`)
    and decorator-style registration (`@registry.register("rss")`).
    """

    def __init__(self) -> None:
        self._providers: dict[str, type[BaseProvider]] = {}

    def register(
        self, provider_id: str, provider_cls: type[BaseProvider] | None = None
    ) -> type[BaseProvider] | Callable[[type[BaseProvider]], type[BaseProvider]]:
        """Register a provider class under `provider_id`.

        Args:
            provider_id: The unique identifier to register the provider under.
            provider_cls: The provider class to register. If omitted, this
                method returns a decorator, enabling
                `@registry.register("rss")` usage on a class definition.

        Returns:
            The registered class (direct call), or a decorator that
            registers and returns the class (decorator usage).

        Raises:
            ProviderAlreadyRegisteredError: If `provider_id` is already registered.
        """

        def _register(cls: type[BaseProvider]) -> type[BaseProvider]:
            if provider_id in self._providers:
                raise ProviderAlreadyRegisteredError(provider_id)
            self._providers[provider_id] = cls
            return cls

        if provider_cls is not None:
            return _register(provider_cls)
        return _register

    def unregister(self, provider_id: str) -> None:
        """Remove a provider registration, if present. A no-op if absent."""
        self._providers.pop(provider_id, None)

    def is_registered(self, provider_id: str) -> bool:
        """Report whether `provider_id` currently has a registered provider class."""
        return provider_id in self._providers

    def get_provider_class(self, provider_id: str) -> type[BaseProvider]:
        """Look up the provider class registered under `provider_id`.

        Raises:
            ProviderNotRegisteredError: If no provider is registered under `provider_id`.
        """
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ProviderNotRegisteredError(provider_id) from exc

    def create(self, provider_id: str, config: ProviderConfig) -> BaseProvider:
        """Construct a configured provider instance for `provider_id`.

        Args:
            provider_id: The identifier of the provider class to instantiate.
            config: The configuration to construct the provider with.

        Raises:
            ProviderNotRegisteredError: If no provider is registered under `provider_id`.
        """
        provider_cls = self.get_provider_class(provider_id)
        return provider_cls(config)

    def list_providers(self) -> tuple[str, ...]:
        """List all currently registered provider IDs, sorted alphabetically."""
        return tuple(sorted(self._providers))
