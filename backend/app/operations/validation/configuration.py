"""ConfigurationValidationService: validates already-loaded settings
objects for release readiness.

Every field this service checks is already structurally validated by its
own `pydantic_settings.BaseSettings` class at construction time (e.g.
`PostgreSQLSettings.port` cannot be constructed outside `[1, 65535]`) —
this service exists for the checks pydantic's own field constraints
cannot express: cross-field concerns (duplicate URLs in a list),
values pydantic accepts but that are operationally risky (an insecure
placeholder secret still in place), and values intentionally left
un-typed as a closed enum by their own settings class (`LLMSettings
.provider`, by that class's own documented design) that still deserve an
advisory check at deployment time.

Never fetches configuration itself and never mutates any settings object
— this service is a pure, deterministic function of whatever settings
objects the caller passes in.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

from app.config.models import (
    AnthropicSettings,
    APISettings,
    LLMSettings,
    LoggingSettings,
    PostgreSQLSettings,
    RSSSettings,
)
from app.operations.logging.models import LogLevel
from app.operations.validation._report import build_report
from app.operations.validation.models import ValidationCheck, ValidationReport, ValidationSeverity

__all__ = ["ConfigurationValidationService", "DEFAULT_KNOWN_ENVIRONMENTS", "DEFAULT_KNOWN_LLM_PROVIDERS"]

DEFAULT_KNOWN_ENVIRONMENTS: frozenset[str] = frozenset({"development", "staging", "production", "test"})
DEFAULT_KNOWN_LLM_PROVIDERS: frozenset[str] = frozenset({"anthropic"})

_INSECURE_DEFAULT_SECRETS: frozenset[str] = frozenset({"change-me", "changeme", ""})


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_well_formed_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class ConfigurationValidationService:
    def __init__(
        self,
        *,
        known_environments: frozenset[str] = DEFAULT_KNOWN_ENVIRONMENTS,
        known_llm_providers: frozenset[str] = DEFAULT_KNOWN_LLM_PROVIDERS,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        self._known_environments = known_environments
        self._known_llm_providers = known_llm_providers
        self._now_fn = now_fn

    def validate(
        self,
        *,
        environment: str,
        postgres: PostgreSQLSettings,
        anthropic: AnthropicSettings | None,
        logging_settings: LoggingSettings,
        llm: LLMSettings,
        api: APISettings,
        rss: RSSSettings,
    ) -> ValidationReport:
        """`anthropic=None` means the caller could not construct
        `AnthropicSettings` at all — `api_key` has no default, so a
        missing `ANTHROPIC_API_KEY` env var raises at construction time
        rather than producing an empty string. That is itself the
        strongest possible "missing secret" signal, reported as a single
        check rather than requiring a constructed (and therefore
        necessarily valid) settings object just to detect its own
        absence."""
        checks: list[ValidationCheck] = [
            self._check_supported_value("environment", environment, self._known_environments),
            self._check_supported_value("logging.level", logging_settings.level, None),
            self._check_port_range("postgres.port", postgres.port),
            self._check_port_range("api.port", api.port),
            self._check_no_duplicates("rss.feed_urls", rss.feed_urls),
            self._check_not_default_secret("postgres.password", postgres.password.get_secret_value()),
            self._check_valid_urls("rss.feed_urls", rss.feed_urls),
            self._check_known_provider("llm.provider", llm.provider, self._known_llm_providers),
        ]
        if anthropic is not None:
            checks.append(self._check_required_secret("anthropic.api_key", anthropic.api_key.get_secret_value()))
            checks.append(self._check_not_default_secret("anthropic.api_key", anthropic.api_key.get_secret_value()))
        else:
            checks.append(
                ValidationCheck(
                    name="required:anthropic.api_key",
                    passed=False,
                    severity=ValidationSeverity.ERROR,
                    message="MISSING - ANTHROPIC_API_KEY is not set (AnthropicSettings failed to construct)",
                )
            )
        if postgres.database_url is not None:
            checks.append(self._check_valid_urls("postgres.database_url", [postgres.database_url], schemes={"postgresql", "postgresql+asyncpg"}))
        return build_report(checks, self._now_fn())

    # --- individual checks -----------------------------------------------------------

    def _check_required_secret(self, name: str, value: str) -> ValidationCheck:
        present = bool(value.strip())
        return ValidationCheck(
            name=f"required:{name}",
            passed=present,
            severity=ValidationSeverity.ERROR,
            message="present" if present else "MISSING - required setting is blank",
        )

    def _check_supported_value(self, name: str, value: str, supported: frozenset[str] | None) -> ValidationCheck:
        if supported is None:
            # LoggingSettings already enforces this at construction time (its own field_validator);
            # this check is a defense-in-depth restatement, always true for a constructed instance.
            supported = frozenset(level.value for level in LogLevel)
        ok = value in supported
        return ValidationCheck(
            name=f"supported_value:{name}",
            passed=ok,
            severity=ValidationSeverity.WARNING,
            message=f"{value!r} is supported" if ok else f"{value!r} is not one of {sorted(supported)}",
        )

    def _check_port_range(self, name: str, port: int) -> ValidationCheck:
        ok = 1 <= port <= 65535
        return ValidationCheck(
            name=f"range:{name}",
            passed=ok,
            severity=ValidationSeverity.ERROR,
            message=f"{port} is within [1, 65535]" if ok else f"{port} is outside the valid port range",
        )

    def _check_no_duplicates(self, name: str, values: list[str]) -> ValidationCheck:
        duplicates = {value for value in values if values.count(value) > 1}
        ok = not duplicates
        return ValidationCheck(
            name=f"duplicate:{name}",
            passed=ok,
            severity=ValidationSeverity.WARNING,
            message="no duplicates" if ok else f"duplicate entries: {sorted(duplicates)}",
        )

    def _check_not_default_secret(self, name: str, value: str) -> ValidationCheck:
        is_default = value.strip().lower() in _INSECURE_DEFAULT_SECRETS
        return ValidationCheck(
            name=f"missing_secret:{name}",
            passed=not is_default,
            severity=ValidationSeverity.WARNING,
            message="not a known insecure default" if not is_default else "still set to an insecure default value",
        )

    def _check_valid_urls(
        self, name: str, values: list[str], *, schemes: frozenset[str] | None = None
    ) -> ValidationCheck:
        if not values:
            return ValidationCheck(name=f"invalid_url:{name}", passed=True, severity=ValidationSeverity.INFO, message="no URLs configured")
        if schemes is not None:
            malformed = [v for v in values if urlparse(v).scheme not in schemes or not urlparse(v).netloc]
        else:
            malformed = [v for v in values if not _is_well_formed_url(v)]
        ok = not malformed
        return ValidationCheck(
            name=f"invalid_url:{name}",
            passed=ok,
            severity=ValidationSeverity.ERROR,
            message="all URLs well-formed" if ok else f"malformed URL(s): {malformed}",
        )

    def _check_known_provider(self, name: str, value: str, known: frozenset[str]) -> ValidationCheck:
        ok = value in known
        return ValidationCheck(
            name=f"unknown_provider:{name}",
            passed=ok,
            severity=ValidationSeverity.WARNING,
            message=f"{value!r} is a known provider" if ok else f"{value!r} is not among the known providers {sorted(known)}",
        )
