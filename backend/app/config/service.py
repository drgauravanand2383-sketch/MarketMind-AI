"""ConfigurationService — the read-only, injectable configuration service.

ConfigurationService wraps one `AppConfig` (app.config.models) and exposes
it two ways: as typed, per-domain properties for code that wants strong
typing, and as a flat `get(key, default)` lookup satisfying
`app.core.runtime.ConfigurationInterface`, so a ConfigurationService
instance can be injected directly into `AgentRuntime(configuration=...)`
in place of `app.bootstrap.SettingsConfiguration`.

There is no module-level singleton here: whoever assembles the
application (bootstrap code, or a test) constructs exactly one
ConfigurationService and passes it to everything that needs it. No
business logic is implemented in this module — it only reads already-
validated configuration values.
"""

from __future__ import annotations

from typing import Any

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

__all__ = ["ConfigurationService"]


class ConfigurationService:
    """Read-only access to the application's typed configuration.

    Construct with an explicit `AppConfig` to inject configuration from a
    non-env source (e.g. in tests); omit it to load configuration from the
    environment / `.env` (`AppConfig()`'s own defaults).
    """

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config if config is not None else AppConfig()

    @property
    def postgres(self) -> PostgreSQLSettings:
        return self._config.postgres

    @property
    def redis(self) -> RedisSettings:
        return self._config.redis

    @property
    def chromadb(self) -> ChromaDBSettings:
        return self._config.chromadb

    @property
    def anthropic(self) -> AnthropicSettings:
        return self._config.anthropic

    @property
    def embedding_provider(self) -> EmbeddingProviderSettings:
        return self._config.embedding_provider

    @property
    def rss(self) -> RSSSettings:
        return self._config.rss

    @property
    def logging(self) -> LoggingSettings:
        return self._config.logging

    @property
    def llm(self) -> LLMSettings:
        return self._config.llm

    @property
    def scheduler(self) -> SchedulerSettings:
        return self._config.scheduler

    @property
    def api(self) -> APISettings:
        return self._config.api

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value by dotted path (e.g. `"postgres.host"`).

        Satisfies `app.core.runtime.ConfigurationInterface`. Returns
        `default` for any key that isn't a two-part `"section.field"` path,
        an unknown section, or an unknown field — this method never raises
        for an unrecognized key.
        """
        section_name, _, field_name = key.partition(".")
        if not field_name:
            return default
        section = getattr(self._config, section_name, None)
        if section is None:
            return default
        return getattr(section, field_name, default)
