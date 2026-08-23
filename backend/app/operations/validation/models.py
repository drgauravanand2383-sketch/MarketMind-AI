"""Domain models shared by both `ConfigurationValidationService` and
`StartupValidationService` — one report shape for every validation
surface this sprint defines, so a caller inspects the same structure
regardless of which service produced it."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ValidationSeverity", "ValidationCheck", "ValidationReport"]


class ValidationSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ValidationCheck(BaseModel):
    """One individual validation rule's outcome."""

    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    severity: ValidationSeverity
    message: str


class ValidationReport(BaseModel):
    """The outcome of one validation run. `passed` is `True` only when
    every `ERROR`-severity check passed — a failed `WARNING`/`INFO`
    check is surfaced in `checks` but does not flip `passed` to `False`,
    since it is advisory rather than release-blocking."""

    model_config = ConfigDict(extra="forbid")

    checks: tuple[ValidationCheck, ...] = Field(default_factory=tuple)
    passed: bool
    generated_at: datetime
    summary: str
