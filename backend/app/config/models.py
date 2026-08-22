"""Typed configuration schemas, loaded from environment variables / `.env`.

Each `*Settings` class is an independent `pydantic_settings.BaseSettings`
scoped to one configuration domain (PostgreSQL, Redis, ChromaDB, Anthropic,
Embedding Provider, RSS, Logging, Scheduler, API), reading only the
environment variables under its own prefix (e.g. `POSTGRES_*`). Existing,
previously-documented env var names that don't follow their domain's prefix
(`DATABASE_URL`, `REDIS_URL`, `CLAUDE_MODEL`, `LOG_LEVEL`, `ALLOWED_ORIGINS`)
are preserved via an explicit `validation_alias` rather than renamed, so
`.env.example` / any already-deployed `.env` keeps working unchanged.

`AppConfig` composes one instance of each into a single, frozen (read-only)
object. No field here is ever written to after construction; "reloading"
configuration means constructing a new `AppConfig`, not mutating this one.
No business logic is implemented in this module.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

__all__ = [
    "PostgreSQLSettings",
    "RedisSettings",
    "ChromaDBSettings",
    "AnthropicSettings",
    "EmbeddingProviderSettings",
    "RSSFeedSource",
    "RSSSettings",
    "LoggingSettings",
    "LLMSettings",
    "SchedulerSettings",
    "APISettings",
    "AuthSettings",
    "AppConfig",
]

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class PostgreSQLSettings(BaseSettings):
    """PostgreSQL connection configuration (`POSTGRES_*`)."""

    model_config = SettingsConfigDict(env_prefix="POSTGRES_", env_file=".env", extra="ignore", frozen=True)

    user: str = "marketmind"
    password: SecretStr = SecretStr("change-me")
    db: str = "marketmind"
    host: str = "localhost"
    port: int = Field(default=5432, ge=1, le=65535)
    # Previously documented without the POSTGRES_ prefix; preserved as-is.
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")


class RedisSettings(BaseSettings):
    """Redis connection configuration (`REDIS_*`)."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", env_file=".env", extra="ignore", frozen=True)

    host: str = "localhost"
    port: int = Field(default=6379, ge=1, le=65535)
    password: SecretStr | None = None
    # Previously documented without the REDIS_ prefix; preserved as-is.
    redis_url: str | None = Field(default=None, validation_alias="REDIS_URL")


class ChromaDBSettings(BaseSettings):
    """ChromaDB connection configuration (`CHROMA_*`)."""

    model_config = SettingsConfigDict(env_prefix="CHROMA_", env_file=".env", extra="ignore", frozen=True)

    host: str = "localhost"
    port: int = Field(default=8000, ge=1, le=65535)
    persist_directory: str = "./data/cache/chroma"
    collection_name: str = "marketmind_knowledge"


class AnthropicSettings(BaseSettings):
    """Claude API configuration (`ANTHROPIC_*`).

    `api_key` has no default: unlike the other sections (which have safe
    local-development defaults), there is no usable placeholder for a
    missing API key, so its absence is a genuine configuration error.

    `max_tokens`/`temperature`/`timeout` (Sprint 36) are the defaults
    `AnthropicProvider` (app.providers.anthropic) falls back to when a
    given request doesn't override them; they carry no prior undocumented
    env var name, so no `validation_alias` is needed for them the way
    `model` needs one for `CLAUDE_MODEL`.
    """

    model_config = SettingsConfigDict(env_prefix="ANTHROPIC_", env_file=".env", extra="ignore", frozen=True)

    api_key: SecretStr
    # Previously documented as CLAUDE_MODEL (not ANTHROPIC_MODEL); preserved as-is.
    model: str = Field(default="claude-sonnet-5", validation_alias="CLAUDE_MODEL")
    max_tokens: int = Field(default=1024, gt=0)
    temperature: float = Field(default=1.0, ge=0.0, le=1.0)
    timeout: float = Field(default=30.0, gt=0)


class EmbeddingProviderSettings(BaseSettings):
    """Default embedding provider configuration (`EMBEDDING_*`).

    No concrete embedding provider implementation is wired up yet (see
    `app.bootstrap.build_embedding_provider`); these are the defaults a
    future concrete provider would be constructed with.
    """

    model_config = SettingsConfigDict(env_prefix="EMBEDDING_", env_file=".env", extra="ignore", frozen=True)

    provider_id: str = "default"
    model: str = "text-embedding-3-small"
    timeout_seconds: float = Field(default=10.0, gt=0)
    max_retries: int = Field(default=2, ge=0)
    retry_backoff_seconds: float = Field(default=1.0, ge=0)


class RSSFeedSource(BaseModel):
    """One configured RSS/Atom feed, with optional provenance metadata
    (v1.2 Priority 6 — Company-Focused News Sources & Ingestion Quality).

    Lives here, not in `app.providers.rss`, because `app.config.models` is
    this codebase's one leaf configuration-schema module (no imports from
    elsewhere in the app — see this module's own docstring) and both
    `RSSSettings` below and `app.providers.rss.models.RSSProviderConfig`
    need the identical shape; `app.providers.rss.models` imports this
    class rather than redefining it, so the two settings paths
    (`AppSettings.rss_feed_urls` in `app.bootstrap`, actually wired to the
    running `RSSProvider`, and this `RSSSettings.feed_urls`, read by the
    configuration-validation/inspection endpoints) never drift apart.

    Backward compatible by construction: `RSS_FEED_URLS` stays one JSON
    array under one env var (no second config mechanism) — each element
    may be a bare URL string (pre-Priority-6 shape, `name`/`category`
    left `None`) or an object carrying `url` plus optional `name`/
    `category`/`tag`.
    """

    model_config = ConfigDict(extra="forbid")

    url: str
    name: str | None = None
    category: str | None = None
    tag: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_bare_url_string(cls, value: object) -> object:
        """A plain string (the only shape `RSS_FEED_URLS` supported
        before Priority 6) is treated as `{"url": value}` — every
        existing `.env` file with a plain URL array keeps working
        unchanged."""
        if isinstance(value, str):
            return {"url": value}
        return value


class RSSSettings(BaseSettings):
    """RSS provider configuration (`RSS_*`)."""

    model_config = SettingsConfigDict(env_prefix="RSS_", env_file=".env", extra="ignore", frozen=True)

    feed_urls: list[RSSFeedSource] = Field(default_factory=list)
    user_agent: str = "MarketMind-AI/1.0"


class LoggingSettings(BaseSettings):
    """Logging configuration (`LOG_LEVEL`)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    # Previously documented as LOG_LEVEL (no LOGGING_ prefix); preserved as-is.
    level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    @field_validator("level")
    @classmethod
    def _validate_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"level must be one of {sorted(_VALID_LOG_LEVELS)}, got {value!r}"
            )
        return normalized


class LLMSettings(BaseSettings):
    """LLM Service provider-selection configuration (`LLM_*`, Sprint 37).

    `provider` is a plain string, not a closed enum: which providers
    actually exist is a runtime concern of `app.services.llm.LLMService`'s
    own injected provider registry, not something this config schema
    should hardcode — adding a second provider later needs no change here.
    """

    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", extra="ignore", frozen=True)

    provider: str = "anthropic"


class SchedulerSettings(BaseSettings):
    """Scheduler subsystem configuration (`SCHEDULER_*`).

    Distinct from `app.scheduler.models.Schedule` (Sprint 31), which
    describes one registered workflow's own schedule. These are
    operational defaults for the Scheduler subsystem as a whole.
    """

    model_config = SettingsConfigDict(env_prefix="SCHEDULER_", env_file=".env", extra="ignore", frozen=True)

    enabled: bool = True
    default_interval_seconds: float = Field(default=3600.0, gt=0)


class APISettings(BaseSettings):
    """API server configuration (`API_*`, `ALLOWED_ORIGINS`)."""

    model_config = SettingsConfigDict(env_prefix="API_", env_file=".env", extra="ignore", frozen=True)

    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    v1_prefix: str = "/api/v1"
    # Previously documented without the API_ prefix, as a bare
    # comma-separated string rather than a JSON list; NoDecode disables
    # pydantic-settings' default JSON-decoding of list-typed env vars so
    # the raw string reaches `_split_comma_separated` below instead.
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"], validation_alias="ALLOWED_ORIGINS"
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        """`.env.example` documents a bare comma-separated string, not JSON."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


class SecurityHeadersSettings(BaseSettings):
    """Security response header configuration (`SECURITY_HEADERS_*`,
    Sprint 60).

    `content_security_policy` and `hsts_enabled` default to disabled —
    both are legitimately breaking to enable blindly: a strict CSP would
    break `/docs` (Swagger UI) and `/redoc` unless a deployer tunes it for
    their own asset hosting, and HSTS instructs browsers to refuse plain
    HTTP entirely, which is actively wrong to send from a development
    server that isn't behind TLS ("do not assume HTTPS in development").
    Every other header here is safe to always send and has no dev/prod
    split.
    """

    model_config = SettingsConfigDict(env_prefix="SECURITY_HEADERS_", env_file=".env", extra="ignore", frozen=True)

    x_content_type_options: str = "nosniff"
    x_frame_options: str = "DENY"
    referrer_policy: str = "strict-origin-when-cross-origin"
    permissions_policy: str = "geolocation=(), microphone=(), camera=()"
    content_security_policy: str | None = None
    hsts_enabled: bool = False
    hsts_max_age_seconds: int = Field(default=31536000, ge=0)
    hsts_include_subdomains: bool = True


class AuthSettings(BaseSettings):
    """Authentication & Authorization Framework configuration (`AUTH_*`,
    plus `SECRET_KEY`/`ALGORITHM`/`ACCESS_TOKEN_EXPIRE_MINUTES` — Sprint 56).

    `secret_key`/`algorithm`/`access_token_expire_minutes` were already
    documented in `.env.example`'s own "Security" section (predating this
    sprint) without an `AUTH_` prefix — preserved via `validation_alias`,
    the same pattern every other pre-existing bare env var name in this
    module already uses. `refresh_token_expire_minutes` and
    `clock_skew_tolerance_seconds` have no prior documented name and use
    the `AUTH_` prefix like any newly-introduced setting.

    `secret_key` is a `SecretStr` — never logged, never included in a
    `repr()`. `app.auth.security.secrets_loader.load_jwt_secret` is the
    single place `.get_secret_value()` is ever called on it.
    """

    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore", frozen=True)

    secret_key: SecretStr = Field(
        default=SecretStr("change-me-in-production"), validation_alias="SECRET_KEY"
    )
    algorithm: str = Field(default="HS256", validation_alias="ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=60, gt=0, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    refresh_token_expire_minutes: int = Field(default=60 * 24 * 7, gt=0)
    clock_skew_tolerance_seconds: int = Field(default=30, ge=0)


class AppConfig(BaseModel):
    """The complete, read-only application configuration.

    Each section independently loads its own environment variables (and
    `.env`) when constructed; passing an already-built section explicitly
    (e.g. `AppConfig(anthropic=AnthropicSettings(api_key=...))`) overrides
    that section's own env loading, which tests use for isolation and DI
    can use to supply configuration from a non-env source.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    postgres: PostgreSQLSettings = Field(default_factory=PostgreSQLSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    chromadb: ChromaDBSettings = Field(default_factory=ChromaDBSettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    embedding_provider: EmbeddingProviderSettings = Field(default_factory=EmbeddingProviderSettings)
    rss: RSSSettings = Field(default_factory=RSSSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    api: APISettings = Field(default_factory=APISettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
