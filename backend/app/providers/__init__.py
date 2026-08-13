"""Provider framework: the common contract every external data source implements.

Supports future providers such as RSS, NSE, BSE, NewsAPI, Moneycontrol,
Reuters, Bloomberg, and Yahoo Finance — none of which are implemented here.
This package defines only the shared abstraction, configuration/result
models, exception hierarchy, and plugin registry.
"""

from app.providers.base import BaseProvider
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
from app.providers.models import ProviderConfig, ProviderResult
from app.providers.registry import ProviderRegistry

__all__ = [
    "BaseProvider",
    "ProviderRegistry",
    "ProviderConfig",
    "ProviderResult",
    "ProviderError",
    "ProviderConfigurationError",
    "ProviderConnectionError",
    "ProviderTimeoutError",
    "ProviderAuthenticationError",
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ProviderNotRegisteredError",
    "ProviderAlreadyRegisteredError",
]
