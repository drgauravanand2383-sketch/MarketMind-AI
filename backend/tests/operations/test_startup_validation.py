"""Tests for StartupValidationService: dependency injection wiring,
repository registration, duplicate registration, aliased instances, and
model metadata discovery — plus composition of ConfigurationValidationService."""

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
from app.operations.validation.startup import StartupValidationService

NOW = datetime(2026, 8, 7, tzinfo=UTC)


def _service() -> StartupValidationService:
    return StartupValidationService(ConfigurationValidationService(now_fn=lambda: NOW), now_fn=lambda: NOW)


def _check(report, name: str):
    return next(c for c in report.checks if c.name == name)


# --- validate_components: registration -----------------------------------------------------------


def test_every_required_component_present_passes() -> None:
    service = _service()
    components = (("risk_service", object()), ("backtesting_service", object()))

    report = service.validate_components(components, required=frozenset({"risk_service", "backtesting_service"}))

    assert report.passed is True
    assert _check(report, "registered:risk_service").passed is True


def test_missing_required_component_fails() -> None:
    service = _service()
    components = (("risk_service", object()),)

    report = service.validate_components(components, required=frozenset({"risk_service", "backtesting_service"}))

    check = _check(report, "registered:backtesting_service")
    assert check.passed is False
    assert check.severity == ValidationSeverity.ERROR
    assert report.passed is False


def test_required_component_registered_as_none_fails() -> None:
    service = _service()
    components = (("risk_service", None),)

    report = service.validate_components(components, required=frozenset({"risk_service"}))

    assert _check(report, "registered:risk_service").passed is False


# --- validate_components: duplicate registration -----------------------------------------------------------


def test_duplicate_registration_detected() -> None:
    service = _service()
    components = (("risk_service", object()), ("risk_service", object()))

    report = service.validate_components(components, required=frozenset())

    check = _check(report, "duplicate_registration:risk_service")
    assert check.passed is False
    assert check.severity == ValidationSeverity.ERROR
    assert report.passed is False


def test_no_duplicate_registration_when_every_name_unique() -> None:
    service = _service()
    components = (("risk_service", object()), ("backtesting_service", object()))

    report = service.validate_components(components, required=frozenset())

    assert not [c for c in report.checks if c.name.startswith("duplicate_registration:")]


# --- validate_components: aliased instance -----------------------------------------------------------


def test_aliased_instance_detected() -> None:
    service = _service()
    shared = object()
    components = (("risk_service", shared), ("backtesting_service", shared))

    report = service.validate_components(components, required=frozenset())

    aliased = [c for c in report.checks if c.name.startswith("aliased_instance:")]
    assert len(aliased) == 1
    assert aliased[0].severity == ValidationSeverity.WARNING
    assert report.passed is True  # WARNING only, not blocking


def test_none_instances_never_flagged_as_aliased() -> None:
    service = _service()
    components = (("risk_service", None), ("backtesting_service", None))

    report = service.validate_components(components, required=frozenset())

    assert not [c for c in report.checks if c.name.startswith("aliased_instance:")]


def test_distinct_instances_never_flagged_as_aliased() -> None:
    service = _service()
    components = (("risk_service", object()), ("backtesting_service", object()))

    report = service.validate_components(components, required=frozenset())

    assert not [c for c in report.checks if c.name.startswith("aliased_instance:")]


# --- validate_metadata_discovery -----------------------------------------------------------


def test_metadata_discovery_passes_for_the_real_schema() -> None:
    service = _service()

    report = service.validate_metadata_discovery()

    assert report.passed is True
    assert _check(report, "model_metadata_discovery").passed is True
    assert _check(report, "model_metadata_uniqueness").passed is True


# --- validate_full -----------------------------------------------------------


def test_validate_full_composes_component_metadata_and_configuration_checks() -> None:
    service = _service()
    components = (("risk_service", object()),)

    report = service.validate_full(
        components,
        required=frozenset({"risk_service"}),
        environment="development",
        postgres=PostgreSQLSettings(),
        anthropic=AnthropicSettings(api_key="sk-real"),
        logging_settings=LoggingSettings(),
        llm=LLMSettings(),
        api=APISettings(),
        rss=RSSSettings(),
        auth=AuthSettings(secret_key="a-real-jwt-secret"),
    )

    names = {c.name for c in report.checks}
    assert "registered:risk_service" in names
    assert "model_metadata_discovery" in names
    assert "required:anthropic.api_key" in names


def test_validate_full_fails_when_any_composed_report_has_an_error() -> None:
    service = _service()
    components = (("risk_service", None),)  # missing required -> ERROR

    report = service.validate_full(
        components,
        required=frozenset({"risk_service"}),
        environment="development",
        postgres=PostgreSQLSettings(),
        anthropic=AnthropicSettings(api_key="sk-real"),
        logging_settings=LoggingSettings(),
        llm=LLMSettings(),
        api=APISettings(),
        rss=RSSSettings(),
        auth=AuthSettings(secret_key="a-real-jwt-secret"),
    )

    assert report.passed is False


def test_validate_full_is_deterministic() -> None:
    service = _service()
    components = (("risk_service", object()),)
    kwargs = dict(
        required=frozenset({"risk_service"}),
        environment="development",
        postgres=PostgreSQLSettings(),
        anthropic=AnthropicSettings(api_key="sk-real"),
        logging_settings=LoggingSettings(),
        llm=LLMSettings(),
        api=APISettings(),
        rss=RSSSettings(),
        auth=AuthSettings(secret_key="a-real-jwt-secret"),
    )

    first = service.validate_full(components, **kwargs)
    second = service.validate_full(components, **kwargs)

    assert first.passed == second.passed
    assert [c.name for c in first.checks] == [c.name for c in second.checks]
