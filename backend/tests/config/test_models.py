"""Tests for the typed configuration schemas (app.config.models).

Every construction below passes `_env_file=None` so a real `.env` on disk
is never consulted — only explicit `monkeypatch.setenv()` calls and each
class's own defaults are exercised.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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

# --- Defaults -----------------------------------------------------------


def test_postgres_defaults() -> None:
    settings = PostgreSQLSettings(_env_file=None)
    assert settings.host == "localhost"
    assert settings.port == 5432
    assert settings.user == "marketmind"
    assert settings.db == "marketmind"
    assert settings.database_url is None


def test_redis_defaults() -> None:
    settings = RedisSettings(_env_file=None)
    assert settings.host == "localhost"
    assert settings.port == 6379
    assert settings.password is None
    assert settings.redis_url is None


def test_chromadb_defaults() -> None:
    settings = ChromaDBSettings(_env_file=None)
    assert settings.host == "localhost"
    assert settings.port == 8000
    assert settings.persist_directory == "./data/cache/chroma"
    assert settings.collection_name == "marketmind_knowledge"


def test_embedding_provider_defaults() -> None:
    settings = EmbeddingProviderSettings(_env_file=None)
    assert settings.provider_id == "default"
    assert settings.max_retries == 2
    assert settings.retry_backoff_seconds == 1.0


def test_rss_defaults() -> None:
    settings = RSSSettings(_env_file=None)
    assert settings.feed_urls == []
    assert settings.user_agent == "MarketMind-AI/1.0"


def test_logging_defaults() -> None:
    settings = LoggingSettings(_env_file=None)
    assert settings.level == "INFO"


def test_scheduler_defaults() -> None:
    settings = SchedulerSettings(_env_file=None)
    assert settings.enabled is True
    assert settings.default_interval_seconds == 3600.0


def test_api_defaults() -> None:
    settings = APISettings(_env_file=None)
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000
    assert settings.v1_prefix == "/api/v1"
    assert settings.allowed_origins == ["http://localhost:3000"]


def test_llm_defaults() -> None:
    settings = LLMSettings(_env_file=None)
    assert settings.provider == "anthropic"


def test_llm_provider_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    settings = LLMSettings(_env_file=None)

    assert settings.provider == "openai"


# --- Env loading -----------------------------------------------------------


def test_postgres_loads_from_prefixed_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_USER", "svc")

    settings = PostgreSQLSettings(_env_file=None)

    assert settings.host == "db.internal"
    assert settings.port == 5433
    assert settings.user == "svc"


def test_postgres_database_url_loads_without_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """DATABASE_URL was documented (.env.example) before this section
    existed, without a POSTGRES_ prefix — preserved via validation_alias."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")

    settings = PostgreSQLSettings(_env_file=None)

    assert settings.database_url == "postgresql+asyncpg://u:p@host/db"


def test_redis_url_loads_without_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://:pw@host:6379/0")

    settings = RedisSettings(_env_file=None)

    assert settings.redis_url == "redis://:pw@host:6379/0"


def test_anthropic_model_loads_from_claude_model_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """Documented as CLAUDE_MODEL, not ANTHROPIC_MODEL — preserved via validation_alias."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-opus-5")

    settings = AnthropicSettings(_env_file=None)

    assert settings.model == "claude-opus-5"


def test_anthropic_max_tokens_temperature_timeout_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    settings = AnthropicSettings(_env_file=None)

    assert settings.max_tokens == 1024
    assert settings.temperature == 1.0
    assert settings.timeout == 30.0


def test_anthropic_max_tokens_temperature_timeout_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("ANTHROPIC_MAX_TOKENS", "2048")
    monkeypatch.setenv("ANTHROPIC_TEMPERATURE", "0.5")
    monkeypatch.setenv("ANTHROPIC_TIMEOUT", "60")

    settings = AnthropicSettings(_env_file=None)

    assert settings.max_tokens == 2048
    assert settings.temperature == 0.5
    assert settings.timeout == 60.0


def test_anthropic_temperature_out_of_range_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("ANTHROPIC_TEMPERATURE", "1.5")

    with pytest.raises(ValidationError):
        AnthropicSettings(_env_file=None)


def test_logging_level_loads_from_log_level_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")

    settings = LoggingSettings(_env_file=None)

    assert settings.level == "DEBUG"  # normalized to uppercase


def test_api_allowed_origins_loads_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """.env.example documents a bare comma-separated string, not a JSON list."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000, https://app.example.com")

    settings = APISettings(_env_file=None)

    assert settings.allowed_origins == ["http://localhost:3000", "https://app.example.com"]


def test_rss_feed_urls_loads_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RSS_FEED_URLS", '["https://a.example.com/feed", "https://b.example.com/feed"]')

    settings = RSSSettings(_env_file=None)

    assert [source.url for source in settings.feed_urls] == ["https://a.example.com/feed", "https://b.example.com/feed"]
    assert all(source.name is None and source.category is None for source in settings.feed_urls)


def test_rss_feed_urls_loads_json_list_with_source_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """v1.2 Priority 6: a mixed array (bare URL string alongside a rich
    object) is valid — the pre-Priority-6 shape and the new shape can
    coexist in the same `RSS_FEED_URLS` value."""
    monkeypatch.setenv(
        "RSS_FEED_URLS",
        '["https://a.example.com/feed", {"url": "https://b.example.com/feed", "name": "B News", "category": "Markets"}]',
    )

    settings = RSSSettings(_env_file=None)

    assert len(settings.feed_urls) == 2
    assert settings.feed_urls[0].url == "https://a.example.com/feed"
    assert settings.feed_urls[0].name is None
    assert settings.feed_urls[1].url == "https://b.example.com/feed"
    assert settings.feed_urls[1].name == "B News"
    assert settings.feed_urls[1].category == "Markets"


# --- Missing required values -----------------------------------------------------------


def test_anthropic_api_key_is_required() -> None:
    with pytest.raises(ValidationError):
        AnthropicSettings(_env_file=None)


def test_app_config_construction_fails_without_anthropic_api_key() -> None:
    with pytest.raises(ValidationError):
        AppConfig()


def test_app_config_constructs_when_anthropic_api_key_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    config = AppConfig()

    assert config.anthropic.api_key.get_secret_value() == "sk-test-key"


# --- Invalid values -----------------------------------------------------------


def test_postgres_port_out_of_range_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PORT", "70000")
    with pytest.raises(ValidationError):
        PostgreSQLSettings(_env_file=None)


def test_api_port_out_of_range_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_PORT", "0")
    with pytest.raises(ValidationError):
        APISettings(_env_file=None)


def test_logging_level_invalid_value_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "NOT_A_LEVEL")
    with pytest.raises(ValidationError):
        LoggingSettings(_env_file=None)


def test_scheduler_interval_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHEDULER_DEFAULT_INTERVAL_SECONDS", "0")
    with pytest.raises(ValidationError):
        SchedulerSettings(_env_file=None)


def test_embedding_timeout_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_TIMEOUT_SECONDS", "-1")
    with pytest.raises(ValidationError):
        EmbeddingProviderSettings(_env_file=None)


def test_unknown_field_is_silently_ignored() -> None:
    """extra="ignore" (matching app.bootstrap.AppSettings' existing
    convention) tolerates unrelated vars in a shared .env rather than
    forcing every deployer to scope each domain's file precisely."""
    settings = PostgreSQLSettings(_env_file=None, unexpected_field="x")
    assert not hasattr(settings, "unexpected_field")


# --- Read-only -----------------------------------------------------------


def test_postgres_settings_is_frozen() -> None:
    settings = PostgreSQLSettings(_env_file=None)
    with pytest.raises(ValidationError):
        settings.host = "changed"


def test_app_config_is_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    config = AppConfig()
    with pytest.raises(ValidationError):
        config.postgres = PostgreSQLSettings(_env_file=None)


# --- AppConfig composition -----------------------------------------------------------


def test_app_config_accepts_explicit_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    custom_postgres = PostgreSQLSettings(_env_file=None, host="explicit-host")

    config = AppConfig(postgres=custom_postgres)

    assert config.postgres.host == "explicit-host"
