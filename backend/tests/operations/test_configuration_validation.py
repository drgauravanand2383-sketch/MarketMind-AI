"""Tests for ConfigurationValidationService: required settings, supported
values, range validation, duplicate configuration, missing secrets,
invalid URLs, and unknown provider names."""

from __future__ import annotations

from datetime import UTC, datetime

from app.config.models import (
    AnthropicSettings,
    APISettings,
    AuthSettings,
    LLMSettings,
    LoggingSettings,
    PostgreSQLSettings,
    RSSSettings,
)
from app.operations.validation.configuration import ConfigurationValidationService
from app.operations.validation.models import ValidationSeverity

NOW = datetime(2026, 8, 7, tzinfo=UTC)


def _service() -> ConfigurationValidationService:
    return ConfigurationValidationService(now_fn=lambda: NOW)


def _validate(service: ConfigurationValidationService, **overrides: object):
    defaults: dict[str, object] = {
        "environment": "development",
        "postgres": PostgreSQLSettings(),
        "anthropic": AnthropicSettings(api_key="sk-real-key"),
        "logging_settings": LoggingSettings(),
        "llm": LLMSettings(),
        "api": APISettings(),
        "rss": RSSSettings(),
        "auth": AuthSettings(secret_key="a-real-jwt-secret"),
    }
    defaults.update(overrides)
    return service.validate(**defaults)


def _check(report, name: str):
    return next(c for c in report.checks if c.name == name)


# --- required settings -----------------------------------------------------------


def test_missing_anthropic_settings_fails_required_secret_check() -> None:
    report = _validate(_service(), anthropic=None)

    check = _check(report, "required:anthropic.api_key")
    assert check.passed is False
    assert check.severity == ValidationSeverity.ERROR
    assert report.passed is False


def test_present_anthropic_settings_passes_required_secret_check() -> None:
    report = _validate(_service())

    assert _check(report, "required:anthropic.api_key").passed is True


# --- supported values -----------------------------------------------------------


def test_known_environment_passes() -> None:
    report = _validate(_service(), environment="production")

    assert _check(report, "supported_value:environment").passed is True


def test_unknown_environment_is_a_warning_not_blocking() -> None:
    report = _validate(_service(), environment="not-a-real-environment")

    check = _check(report, "supported_value:environment")
    assert check.passed is False
    assert check.severity == ValidationSeverity.WARNING
    assert report.passed is True  # advisory only, does not block


def test_logging_level_always_passes_for_a_constructed_settings_object() -> None:
    report = _validate(_service())

    assert _check(report, "supported_value:logging.level").passed is True


# --- range validation -----------------------------------------------------------


def test_postgres_port_within_range_passes() -> None:
    report = _validate(_service(), postgres=PostgreSQLSettings(port=5432))

    assert _check(report, "range:postgres.port").passed is True


def test_api_port_within_range_passes() -> None:
    report = _validate(_service(), api=APISettings(port=8000))

    assert _check(report, "range:api.port").passed is True


# --- duplicate configuration -----------------------------------------------------------


def test_no_duplicate_feed_urls_passes() -> None:
    report = _validate(_service(), rss=RSSSettings(feed_urls=["https://a.com/feed", "https://b.com/feed"]))

    assert _check(report, "duplicate:rss.feed_urls").passed is True


def test_duplicate_feed_urls_fails_as_warning() -> None:
    report = _validate(
        _service(), rss=RSSSettings(feed_urls=["https://a.com/feed", "https://a.com/feed"])
    )

    check = _check(report, "duplicate:rss.feed_urls")
    assert check.passed is False
    assert check.severity == ValidationSeverity.WARNING


# --- missing secrets -----------------------------------------------------------


def test_default_postgres_password_flagged_as_insecure() -> None:
    report = _validate(_service(), postgres=PostgreSQLSettings())  # default password="change-me"

    check = _check(report, "missing_secret:postgres.password")
    assert check.passed is False
    assert check.severity == ValidationSeverity.WARNING


def test_real_postgres_password_not_flagged() -> None:
    report = _validate(_service(), postgres=PostgreSQLSettings(password="a-real-secret"))

    assert _check(report, "missing_secret:postgres.password").passed is True


def test_default_anthropic_key_placeholder_flagged_as_insecure() -> None:
    report = _validate(_service(), anthropic=AnthropicSettings(api_key="change-me"))

    assert _check(report, "missing_secret:anthropic.api_key").passed is False


def test_default_jwt_secret_key_flagged_as_insecure() -> None:
    """Regression test: `AuthSettings.secret_key` defaults to the
    publicly-documented placeholder `"change-me-in-production"`
    (`.env.example`) — deploying with it unchanged lets anyone forge a
    valid JWT for any user. Previously this default was never checked at
    all (unlike `postgres.password`/`anthropic.api_key`)."""
    report = _validate(_service(), auth=AuthSettings())  # default secret_key="change-me-in-production"

    check = _check(report, "missing_secret:auth.secret_key")
    assert check.passed is False
    assert check.severity == ValidationSeverity.WARNING


def test_real_jwt_secret_key_not_flagged() -> None:
    # `AuthSettings.secret_key` carries `validation_alias="SECRET_KEY"` (preserving
    # a previously-documented bare env var name) with no `populate_by_name` — same
    # footgun as `postgres.database_url` above: a direct constructor kwarg must use
    # that alias, not the python attribute name, or it is silently dropped
    # (`extra="ignore"`) and the field falls back to its insecure default.
    report = _validate(_service(), auth=AuthSettings(SECRET_KEY="a-real-jwt-secret"))

    assert _check(report, "missing_secret:auth.secret_key").passed is True


# --- production-only blocking secret check (Milestone 17 §7) -----------------------------------------------------------


def test_insecure_jwt_secret_in_production_is_a_blocking_error() -> None:
    """§7: an insecure default secret must not be silently accepted in a
    real `environment=production` deployment — unlike the general
    `missing_secret:*` check (WARNING, non-blocking, correct for local
    development), this is ERROR-severity and fails `report.passed`."""
    report = _validate(_service(), environment="production", auth=AuthSettings())

    check = _check(report, "production_secret:auth.secret_key")
    assert check.passed is False
    assert check.severity == ValidationSeverity.ERROR
    assert report.passed is False


def test_insecure_postgres_password_in_production_is_a_blocking_error() -> None:
    report = _validate(_service(), environment="production", postgres=PostgreSQLSettings())

    check = _check(report, "production_secret:postgres.password")
    assert check.passed is False
    assert check.severity == ValidationSeverity.ERROR
    assert report.passed is False


def test_real_secrets_in_production_pass_the_blocking_check() -> None:
    report = _validate(
        _service(), environment="production",
        auth=AuthSettings(SECRET_KEY="a-real-jwt-secret"),
        postgres=PostgreSQLSettings(password="a-real-secret"),
    )

    assert _check(report, "production_secret:auth.secret_key").passed is True
    assert _check(report, "production_secret:postgres.password").passed is True
    assert report.passed is True


def test_insecure_secret_outside_production_is_not_blocking() -> None:
    """The same insecure default in `environment=development` (or any
    non-production value) must not be escalated — local development with
    the documented placeholder secret is normal and must never fail this
    check."""
    report = _validate(_service(), environment="development", auth=AuthSettings())

    check = _check(report, "production_secret:auth.secret_key")
    assert check.passed is True
    assert check.severity == ValidationSeverity.INFO
    assert report.passed is True


# --- invalid URLs -----------------------------------------------------------


def test_well_formed_feed_urls_pass() -> None:
    report = _validate(_service(), rss=RSSSettings(feed_urls=["https://example.com/feed.xml"]))

    assert _check(report, "invalid_url:rss.feed_urls").passed is True


def test_malformed_feed_url_fails() -> None:
    report = _validate(_service(), rss=RSSSettings(feed_urls=["not-a-url"]))

    check = _check(report, "invalid_url:rss.feed_urls")
    assert check.passed is False
    assert check.severity == ValidationSeverity.ERROR
    assert report.passed is False  # ERROR severity blocks


def test_no_feed_urls_configured_is_informational() -> None:
    report = _validate(_service(), rss=RSSSettings(feed_urls=[]))

    check = _check(report, "invalid_url:rss.feed_urls")
    assert check.passed is True
    assert check.severity == ValidationSeverity.INFO


def test_valid_database_url_passes() -> None:
    # PostgreSQLSettings.database_url carries `validation_alias="DATABASE_URL"`
    # (preserving a previously-documented env var name) with no
    # `populate_by_name` — a direct constructor kwarg must use that alias,
    # not the python attribute name, to actually take effect.
    report = _validate(
        _service(),
        postgres=PostgreSQLSettings(DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db"),
    )

    assert _check(report, "invalid_url:postgres.database_url").passed is True


def test_malformed_database_url_fails() -> None:
    report = _validate(_service(), postgres=PostgreSQLSettings(DATABASE_URL="not-a-valid-url"))

    assert _check(report, "invalid_url:postgres.database_url").passed is False


def test_no_database_url_check_when_unset() -> None:
    report = _validate(_service(), postgres=PostgreSQLSettings(DATABASE_URL=None))

    assert all(c.name != "invalid_url:postgres.database_url" for c in report.checks)


# --- unknown provider names -----------------------------------------------------------


def test_known_llm_provider_passes() -> None:
    report = _validate(_service(), llm=LLMSettings(provider="anthropic"))

    assert _check(report, "unknown_provider:llm.provider").passed is True


def test_unknown_llm_provider_is_a_warning_not_blocking() -> None:
    report = _validate(_service(), llm=LLMSettings(provider="some-future-provider"))

    check = _check(report, "unknown_provider:llm.provider")
    assert check.passed is False
    assert check.severity == ValidationSeverity.WARNING
    assert report.passed is True


def test_configurable_known_providers_extends_the_allow_list() -> None:
    service = ConfigurationValidationService(known_llm_providers=frozenset({"anthropic", "openai"}), now_fn=lambda: NOW)
    report = _validate(service, llm=LLMSettings(provider="openai"))

    assert _check(report, "unknown_provider:llm.provider").passed is True


# --- determinism -----------------------------------------------------------


def test_validate_is_deterministic_for_identical_inputs() -> None:
    service = _service()
    first = _validate(service)
    second = _validate(service)

    assert first == second
