"""Validation: `ConfigurationValidationService` (settings-level checks)
and `StartupValidationService` (dependency injection wiring, repository
registration, and model metadata discovery — composing
`ConfigurationValidationService` via injection)."""

from app.operations.validation.configuration import (
    DEFAULT_KNOWN_ENVIRONMENTS,
    DEFAULT_KNOWN_LLM_PROVIDERS,
    ConfigurationValidationService,
)
from app.operations.validation.models import ValidationCheck, ValidationReport, ValidationSeverity
from app.operations.validation.startup import DEFAULT_REQUIRED_COMPONENTS, StartupValidationService

__all__ = [
    "ValidationSeverity",
    "ValidationCheck",
    "ValidationReport",
    "ConfigurationValidationService",
    "DEFAULT_KNOWN_ENVIRONMENTS",
    "DEFAULT_KNOWN_LLM_PROVIDERS",
    "StartupValidationService",
    "DEFAULT_REQUIRED_COMPONENTS",
]
