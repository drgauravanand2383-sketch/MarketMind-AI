"""Typed application configuration, loaded from environment variables / `.env`.

`AppConfig` (models.py) is the strongly-typed, read-only, validated
composition of every configuration domain. `ConfigurationService`
(service.py) is the injectable service that wraps it — pass one to
`app.core.runtime.AgentRuntime(configuration=...)` in place of
`app.bootstrap.SettingsConfiguration`.
"""

from app.config.models import (
    AnthropicSettings,
    APISettings,
    AppConfig,
    ChromaDBSettings,
    EmbeddingProviderSettings,
    LLMSettings,
    LoggingSettings,
    PostgreSQLSettings,
    RedisSettings,
    RSSSettings,
    SchedulerSettings,
)
from app.config.service import ConfigurationService

__all__ = [
    "PostgreSQLSettings",
    "RedisSettings",
    "ChromaDBSettings",
    "AnthropicSettings",
    "EmbeddingProviderSettings",
    "RSSSettings",
    "LoggingSettings",
    "LLMSettings",
    "SchedulerSettings",
    "APISettings",
    "AppConfig",
    "ConfigurationService",
]
